#include "engine/ai/playbook.hpp"
#include "engine/assets/hot_reload_index.hpp"
#include "engine/assets/hot_reload_status.hpp"
#include "engine/audio/splash_audio.hpp"
#include "engine/audio/audio_interference_runtime.hpp"
#include "engine/benchmark/machine_profile.hpp"
#include "engine/combat/combat_system.hpp"
#include "engine/economy/economy_system.hpp"
#include "engine/lighting/illuminosity_bake.hpp"
#include "engine/lighting/illuminosity_runtime.hpp"
#include "engine/items/tupd_runtime.hpp"
#include "engine/materials/material_runtime.hpp"
#include "engine/ui/ar_interface.hpp"
#include "engine/ui/scui_native_runtime.hpp"
#include "engine/ui/scui_binding_store.hpp"
#include "engine/ui/scui_registry.hpp"
#include "engine/ui/scui_light_preview.hpp"
#include "engine/ui/tactical_memory_map.hpp"
#include "engine/ui/tupd_ghost_preview.hpp"
#include "engine/pcp3/pcp3_asset.hpp"
#include "engine/platform/capability_report.hpp"
#include "engine/platform/first_person_camera.hpp"
#include "engine/platform/video_backend.hpp"
#include "engine/render/adaptive_budget.hpp"
#include "engine/render/adaptive_residency.hpp"
#include "engine/render/gl_api.hpp"
#include "engine/render/memory_budget.hpp"
#include "engine/render/local_siren.hpp"
#include "engine/render/point_cloud.hpp"
#include "engine/render/point_lab.hpp"
#include "engine/render/point_renderer.hpp"
#include "engine/render/room_visibility.hpp"
#include "engine/render/signal_interference.hpp"
#include "engine/render/sound_ripple.hpp"
#include "engine/render/system_point_budget.hpp"
#include "engine/render/water_disturbance.hpp"
#include "engine/scfont/font_service.hpp"
#include "engine/scfont/text_point_adapter.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/player_controller.hpp"
#include "engine/world/recovery_system.hpp"
#include "engine/world/threat_director.hpp"
#include "engine/world/world_seed.hpp"

#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>

#include <algorithm>
#include <array>
#include <charconv>
#include <cctype>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <system_error>
#include <vector>

namespace {

struct RuntimeOptions {
    signalcloud::platform::VideoBackend backend{signalcloud::platform::VideoBackend::automatic};
    std::filesystem::path root{std::filesystem::current_path()};
    std::optional<std::uint32_t> point_override;
};

bool is_safe_room(std::string_view zone) noexcept {
    return signalcloud::world::zone_is_protected(zone);
}

signalcloud::ui::ArDangerKind danger_kind_for(signalcloud::world::DamageCause cause) noexcept {
    using signalcloud::ui::ArDangerKind;
    using signalcloud::world::DamageCause;
    switch (cause) {
        case DamageCause::drowning: return ArDangerKind::drowning;
        case DamageCause::pressure: return ArDangerKind::pressure;
        case DamageCause::fall: return ArDangerKind::fall;
        case DamageCause::poison: return ArDangerKind::poison;
        case DamageCause::treason: return ArDangerKind::treason;
        case DamageCause::none:
        case DamageCause::combat: return ArDangerKind::combat;
    }
    return ArDangerKind::combat;
}

float distance_xz(signalcloud::math::Vec3 a, signalcloud::math::Vec3 b) noexcept {
    const float dx = a.x - b.x;
    const float dz = a.z - b.z;
    return std::sqrt(dx * dx + dz * dz);
}

void populate_scanner_contacts(
    signalcloud::ui::ArInterfaceData& data,
    const signalcloud::world::LiminalLevel& level,
    const signalcloud::combat::CombatSystem& combat,
    const signalcloud::economy::EconomySystem& economy,
    std::string_view current_zone,
    signalcloud::math::Vec3 player_position) {
    using signalcloud::ui::ScannerContactKind;
    data.scanner_contact_count = 0;
    if (!data.scanner_active) return;

    std::array<bool, 6> seen{};
    auto add = [&](ScannerContactKind kind, float strength, bool allow_duplicate = false) {
        const auto index = static_cast<std::size_t>(kind);
        if (kind == ScannerContactKind::none ||
            data.scanner_contact_count >= static_cast<int>(data.scanner_contacts.size())) return;
        if (!allow_duplicate && index < seen.size() && seen[index]) return;
        data.scanner_contacts[static_cast<std::size_t>(data.scanner_contact_count++)] =
            {kind, std::clamp(strength, 0.12F, 1.0F)};
        if (index < seen.size()) seen[index] = true;
    };

    auto add_destination = [&](std::string_view destination, float strength) {
        bool hostile_present = false;
        for (const auto& entity : combat.entities()) {
            if (!entity.alive || entity.zone != destination) continue;
            add(entity.kind == signalcloud::combat::CreatureKind::hash_dog
                    ? ScannerContactKind::formed
                    : ScannerContactKind::formless,
                strength, true);
            hostile_present = true;
        }
        if (destination == "Scavenger Exchange") {
            add(ScannerContactKind::exchange, strength);
            bool loot_available = false;
            for (const auto& pickup : economy.pickups()) {
                loot_available = loot_available || !pickup.collected;
            }
            if (loot_available) add(ScannerContactKind::loot, strength);
        } else if (!hostile_present) {
            add(ScannerContactKind::room, strength);
        }
    };

    add_destination(current_zone, 1.0F);

    for (const auto& preview : level.connection_previews(current_zone, player_position)) {
        add(ScannerContactKind::room, preview.strength);
        add_destination(preview.destination_zone, preview.strength);
    }

    for (const auto& portal : level.portals()) {
        if (portal.source_zone != current_zone) continue;
        const float range = 13.0F;
        const float distance = distance_xz(player_position, portal.center);
        if (distance > range) continue;
        const float strength = 1.0F - distance / range;
        add(ScannerContactKind::room, strength);
        add_destination(portal.destination_zone, strength);
    }
}

signalcloud::ui::ArFeedbackKind feedback_for_economy_event(
    const signalcloud::economy::EconomyEvent& event) noexcept {
    using signalcloud::ui::ArFeedbackKind;
    if (!event.success) return ArFeedbackKind::failure;
    if (event.xar_delta > 0) return ArFeedbackKind::sale;
    if (event.xar_delta < 0) return ArFeedbackKind::purchase;
    if (event.health_restored > 0.0F || event.oxygen_restored > 0.0F ||
        event.ammo_added > 0 || event.sabs_wetness_added > 0.0F) return ArFeedbackKind::use;
    return ArFeedbackKind::pickup;
}

RuntimeOptions parse_args(int argc, char** argv) {
    RuntimeOptions options;
    for (int i = 1; i < argc; ++i) {
        const std::string_view arg(argv[i]);
        constexpr std::string_view video_prefix = "--video=";
        constexpr std::string_view root_prefix = "--root=";
        constexpr std::string_view points_prefix = "--points=";
        if (arg.starts_with(video_prefix)) {
            if (const auto parsed = signalcloud::platform::parse_video_backend(arg.substr(video_prefix.size()))) {
                options.backend = *parsed;
            }
        } else if (arg.starts_with(root_prefix)) {
            options.root = std::filesystem::path(std::string(arg.substr(root_prefix.size())));
        } else if (arg.starts_with(points_prefix)) {
            std::uint32_t value = 0;
            const auto text = arg.substr(points_prefix.size());
            const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
            if (result.ec == std::errc{} && result.ptr == text.data() + text.size()) options.point_override = value;
        }
    }
    return options;
}

void append_button_log(const std::filesystem::path& path, double time_seconds, Uint8 button,
                       bool down, int clicks) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream output(path, std::ios::app);
    output << time_seconds << " button=" << static_cast<int>(button)
           << " state=" << (down ? "down" : "up") << " clicks=" << clicks << '\n';
}

void append_zone_log(const std::filesystem::path& path, double time_seconds, std::string_view zone,
                     signalcloud::math::Vec3 position) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream output(path, std::ios::app);
    output << std::fixed << std::setprecision(3) << time_seconds << " zone=" << zone
           << " position=" << position.x << ',' << position.y << ',' << position.z << '\n';
}

void append_portal_log(const std::filesystem::path& path, double time_seconds,
                       const signalcloud::world::PortalGate& portal,
                       signalcloud::math::Vec3 from, signalcloud::math::Vec3 to) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream output(path, std::ios::app);
    output << std::fixed << std::setprecision(3) << time_seconds
           << " portal=" << portal.id << " kind=" << signalcloud::world::portal_kind_name(portal.kind)
           << " source=\"" << portal.source_zone << "\" destination=\"" << portal.destination_zone << "\""
           << " from=" << from.x << ',' << from.y << ',' << from.z
           << " to=" << to.x << ',' << to.y << ',' << to.z << '\n';
}

void write_layout_report(const std::filesystem::path& path,
                         const signalcloud::world::LiminalLevel& level) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream output(path, std::ios::trunc);
    output << "ALMOND SIGNAL: LIVE TAPE / SignalCloud Engine\n"
           << "Pivot 13 a3 threshold pursuit, vertical perception, adaptive 8M baseline, and JAM memory\n\n"
           << "Seed: " << signalcloud::world::seed_hex(level.seed()) << '\n'
           << "Layout signature: " << signalcloud::world::seed_hex(level.layout_signature()) << '\n'
           << "Rooms: " << level.areas().size() << '\n'
           << "Portals: " << level.portals().size() << "\n\n";
    for (const auto& portal : level.portals()) {
        output << portal.id << " [" << signalcloud::world::portal_kind_name(portal.kind) << "] "
               << portal.source_zone << " -> " << portal.destination_zone << '\n';
    }
}

bool ensure_csv_schema(const std::filesystem::path& path, std::string_view header) {
    std::filesystem::create_directories(path.parent_path());
    if (!std::filesystem::exists(path) || std::filesystem::file_size(path) == 0U) return true;
    std::ifstream input(path);
    std::string current;
    std::getline(input, current);
    if (current == header) return false;
    const auto legacy = path.parent_path() /
        (path.stem().string() + ".legacy_schema_" + std::to_string(SDL_GetTicks()) + path.extension().string());
    std::error_code error;
    std::filesystem::rename(path, legacy, error);
    if (error) {
        std::filesystem::remove(path, error);
    }
    return true;
}

void append_benchmark(const std::filesystem::path& path, double time_seconds,
                      const signalcloud::render::PointLabState& lab, float fps,
                      double gpu_ms, std::size_t allocated_bytes, double generation_ms,
                      bool scanner, bool tactical, std::string_view reason) {
    constexpr std::string_view header = "time_seconds,reason,preset,points,fps,gpu_ms,vbo_mib,generation_ms,point_scale,density_scale,scanner,tactical";
    const bool needs_header = ensure_csv_schema(path, header);
    std::ofstream output(path, std::ios::app);
    if (needs_header) output << header << '\n';
    const double mib = static_cast<double>(allocated_bytes) / (1024.0 * 1024.0);
    output << std::fixed << std::setprecision(3)
           << time_seconds << ',' << reason << ',' << lab.preset().name << ',' << lab.preset().points << ','
           << fps << ',' << gpu_ms << ',' << mib << ',' << generation_ms << ','
           << lab.point_scale() << ',' << lab.density_scale() << ','
           << (scanner ? 1 : 0) << ',' << (tactical ? 1 : 0) << '\n';
}

void write_budget_report(const std::filesystem::path& path,
                         const signalcloud::platform::CapabilityReport& capability,
                         const signalcloud::render::AdaptivePointBudget& budget,
                         std::optional<std::uint32_t> override_points) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream output(path, std::ios::trunc);
    output << "ALMOND SIGNAL: LIVE TAPE / SignalCloud Engine\n"
           << "Pivot 13 a3 adaptive 8M environment plus threshold pursuit, vertical perception, AR, ammo-tablet, and recovery pools\n\n"
           << "Vendor: " << capability.vendor << '\n'
           << "Renderer: " << capability.renderer << '\n'
           << "Profile: " << budget.profile << '\n'
           << "Recommended gameplay points: " << budget.gameplay_points << '\n'
           << "Reason: " << budget.rationale << '\n';
    if (override_points) output << "Command-line override: " << *override_points << '\n';
    const auto& full = signalcloud::render::system_point_budget_for_total(20'000'000U);
    output << "\nTotal resident profile: " << full.name << " (" << full.total_points << ")\n"
           << "Environment pool: " << full.environment_points << '\n'
           << "Hostile pool: " << full.hostile_points << '\n'
           << "Player/viewmodel pool: " << full.player_viewmodel_points << '\n'
           << "Friendly/NPC pool: " << full.friendly_npc_points << '\n'
           << "Object/effect pool: " << full.object_effect_points << '\n'
           << "Submitted soft cap: " << full.submitted_soft_cap << '\n'
           << "Important: resident pool caps are not simultaneous per-frame draw counts.\n";
}

void append_stream_log(const std::filesystem::path& path, double time_seconds,
                       std::string_view zone, std::size_t resident_points,
                       std::size_t submitted_points, std::size_t submitted_rooms,
                       const signalcloud::render::SignalInterference& signal, float fps,
                       double gpu_ms, bool tactical, std::size_t submitted_ranges,
                       std::size_t preview_rooms, std::size_t preview_ranges,
                       std::size_t anchored_ranges, float distance_limit, float light_influence,
                       std::size_t submitted_cap, std::size_t points_trimmed, bool cap_applied) {
    constexpr std::string_view header = "time_seconds,zone,resident_points,submitted_points,submitted_rooms,submitted_ranges,preview_rooms,preview_ranges,anchored_ranges,signal_mode,equivalent_fill,signal_level,fps,gpu_ms,tactical,distance_limit,light_influence,submitted_cap,points_trimmed,cap_applied";
    const bool needs_header = ensure_csv_schema(path, header);
    std::ofstream output(path, std::ios::app);
    if (needs_header) output << header << '\n';
    output << std::fixed << std::setprecision(3) << time_seconds << ',' << zone << ','
           << resident_points << ',' << submitted_points << ',' << submitted_rooms << ','
           << submitted_ranges << ',' << preview_rooms << ',' << preview_ranges << ','
           << anchored_ranges << ','
           << signalcloud::render::signal_mode_name(signal.mode()) << ','
           << signal.equivalent_points() << ',' << signal.level() << ',' << fps << ','
           << gpu_ms << ',' << (tactical ? 1 : 0) << ',' << distance_limit << ','
           << light_influence << ',' << submitted_cap << ',' << points_trimmed << ','
           << (cap_applied ? 1 : 0) << '\n';
}


void append_traversal_log(const std::filesystem::path& path, double time_seconds,
                          const signalcloud::world::PlayerController& player,
                          std::string_view zone, std::string_view event_name) {
    constexpr std::string_view header = "time_seconds,event,zone,x,y,z,vertical_velocity,grounded,crouched,water_state,immersion,ground_height,depenetrations,recovery_surface,surface";
    const bool needs_header = ensure_csv_schema(path, header);
    std::ofstream output(path, std::ios::app);
    if (needs_header) output << header << '\n';
    const auto pos = player.position();
    output << std::fixed << std::setprecision(3) << time_seconds << ',' << event_name << ',' << zone << ','
           << pos.x << ',' << pos.y << ',' << pos.z << ',' << player.vertical_velocity() << ','
           << (player.grounded() ? 1 : 0) << ',' << (player.crouched() ? 1 : 0) << ','
           << signalcloud::world::water_state_name(player.water_state()) << ','
           << player.immersion() << ',' << player.ground_height() << ','
           << player.depenetration_count() << ",\"" << player.last_recovery_surface() << "\",\""
           << player.surface_name() << "\"\n";
}


void append_depth_log(const std::filesystem::path& path, double time_seconds,
                      std::string_view event_name, std::string_view zone,
                      const signalcloud::world::PlayerController& player,
                      float distance_limit) {
    constexpr std::string_view header = "time_seconds,event,zone,x,y,z,health,oxygen_seconds,oxygen_ratio,depth,pressure_dps,water_viscosity,water_state,jump_kind,save_jumps,bomb_entries,depth_tech,rescues,distance_limit";
    const bool needs_header = ensure_csv_schema(path, header);
    std::ofstream output(path, std::ios::app);
    if (needs_header) output << header << '\n';
    const auto pos = player.position();
    output << std::fixed << std::setprecision(3) << time_seconds << ',' << event_name << ',' << zone << ','
           << pos.x << ',' << pos.y << ',' << pos.z << ','
           << player.health() << ',' << player.oxygen_seconds() << ',' << player.oxygen_ratio() << ','
           << player.water_depth() << ',' << player.pressure_damage_per_second() << ','
           << player.water_viscosity() << ','
           << signalcloud::world::water_state_name(player.water_state()) << ','
           << signalcloud::world::jump_kind_name(player.last_jump_kind()) << ','
           << player.save_jump_count() << ',' << player.bomb_entry_count() << ','
           << (player.has_almond_depth_tech() ? 1 : 0) << ',' << player.rescue_count() << ','
           << distance_limit << '\n';
}

void append_combat_log(const std::filesystem::path& path, double time_seconds,
                       std::string_view event_name, std::string_view zone, int weapon_slot,
                       const signalcloud::combat::CombatSystem& combat,
                       const signalcloud::world::PlayerController& player,
                       const signalcloud::combat::FireResult* shot = nullptr) {
    constexpr std::string_view header = "time_seconds,event,zone,weapon,magazine,reserve,entity_id,damage,killed,player_health,evades,kills,claimed_proofs,hint";
    const bool needs_header = ensure_csv_schema(path, header);
    std::ofstream output(path, std::ios::app);
    if (needs_header) output << header << '\n';
    output << std::fixed << std::setprecision(3) << time_seconds << ',' << event_name << ','
           << zone << ',' << weapon_slot << ',' << combat.magazine() << ','
           << combat.reserve_ammo() << ',' << (shot ? shot->entity_id : 0U) << ','
           << (shot ? shot->damage : 0.0F) << ',' << (shot && shot->killed ? 1 : 0) << ','
           << player.health() << ',' << player.evade_count() << ',' << combat.kills() << ','
           << combat.claimed_proofs() << ",\"" << combat.last_hint() << "\"\n";
}

void append_economy_log(const std::filesystem::path& path, double time_seconds,
                        std::string_view event_name, std::string_view zone,
                        const signalcloud::economy::EconomySystem& economy,
                        std::string_view message) {
    constexpr std::string_view header = "time_seconds,event,zone,xar,carry_weight,scrap,proofs,almond_water,ammo_packs,sabs_patches,sabs_wetness_ratio,movement_scale,message";
    const bool needs_header = ensure_csv_schema(path, header);
    std::ofstream output(path, std::ios::app);
    if (needs_header) output << header << '\n';
    output << std::fixed << std::setprecision(3) << time_seconds << ',' << event_name << ','
           << zone << ',' << economy.xar_balance() << ',' << economy.carried_weight() << ','
           << economy.quantity(signalcloud::economy::ItemKind::signal_scrap) << ','
           << economy.quantity(signalcloud::economy::ItemKind::death_proof) << ','
           << economy.quantity(signalcloud::economy::ItemKind::almond_water) << ','
           << economy.quantity(signalcloud::economy::ItemKind::ammo_pack) << ','
           << economy.quantity(signalcloud::economy::ItemKind::sabs_patch) << ','
           << economy.sabs_wetness_ratio() << ',' << economy.movement_scale() << ",\""
           << message << "\"\n";
}

const signalcloud::world::WalkArea& active_area_for(const signalcloud::world::LiminalLevel& level,
                                                     std::string_view zone) {
    for (const auto& area : level.areas()) if (area.name == zone) return area;
    return level.areas().front();
}

bool create_context(SDL_Window* window, SDL_GLContext& context, int major, int minor) {
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, major);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, minor);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 24);
    context = SDL_GL_CreateContext(window);
    return context != nullptr;
}

std::optional<std::size_t> preset_index_for(std::uint32_t points) {
    for (std::size_t i = 0; i < signalcloud::render::kPointLabPresets.size(); ++i) {
        if (signalcloud::render::kPointLabPresets[i].points == points) return i;
    }
    return std::nullopt;
}

}  // namespace

int main(int argc, char** argv) {
    const RuntimeOptions options = parse_args(argc, argv);
    const auto profile_target_hint = signalcloud::benchmark::read_active_profile_target_hint(options.root);
    SDL_SetAppMetadata("ALMOND SIGNAL: LIVE TAPE", "0.13.0-a9a1r1", "io.digimancer3d.almondsignal");
    if (const auto hint = signalcloud::platform::sdl_driver_hint(options.backend)) {
        SDL_SetHint(SDL_HINT_VIDEO_DRIVER, std::string(*hint).c_str());
    }
    if (!SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS)) {
        std::cerr << "SDL initialization failed: " << SDL_GetError() << '\n';
        return 2;
    }
    const bool audio_subsystem_ready = SDL_InitSubSystem(SDL_INIT_AUDIO);
    if (!audio_subsystem_ready) {
        std::cerr << "Audio subsystem warning: " << SDL_GetError()
                  << " (visual splash events remain enabled)\n";
    }

    SDL_Window* window = SDL_CreateWindow("ALMOND SIGNAL: LIVE TAPE - Pivot 13 a3 Threshold Pursuit & Vertical Perception",
                                           profile_target_hint.width, profile_target_hint.height,
                                           SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY);
    if (window == nullptr) {
        std::cerr << "Window creation failed: " << SDL_GetError() << '\n';
        SDL_Quit();
        return 3;
    }

    SDL_GLContext context = nullptr;
    if (!create_context(window, context, 4, 3) && !create_context(window, context, 3, 3)) {
        std::cerr << "OpenGL context creation failed: " << SDL_GetError() << '\n';
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 4;
    }
    SDL_GL_MakeCurrent(window, context);
    SDL_GL_SetSwapInterval(1);

    signalcloud::render::GLApi gl;
    std::string gl_error;
    if (!gl.load(&gl_error)) {
        std::cerr << gl_error << '\n';
        SDL_GL_DestroyContext(context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 5;
    }

    const char* video_driver = SDL_GetCurrentVideoDriver();
    const auto capability = signalcloud::platform::collect_capability_report(
        gl, video_driver ? video_driver : "unknown");
    std::string report_error;
    signalcloud::platform::write_capability_report(
        capability, options.root / "reports/capability_report.txt", &report_error);
    std::cout << capability.text;
    if (!report_error.empty()) std::cerr << "Report warning: " << report_error << '\n';

    const auto capability_budget = signalcloud::render::recommend_point_budget(
        capability.vendor, capability.renderer, capability.gl_major, capability.gl_minor);
    const signalcloud::benchmark::MachineProfileContext profile_context{
        capability.vendor,
        capability.renderer,
        capability.version,
        video_driver ? video_driver : "unknown",
        capability.gl_major,
        capability.gl_minor,
        profile_target_hint.width,
        profile_target_hint.height,
        signalcloud::benchmark::hash_machine_profile_content_manifest(options.root / "content/manifest.csv"),
    };
    const auto machine_profile = signalcloud::benchmark::load_active_or_conservative(
        options.root, profile_context, capability_budget, profile_target_hint.target_fps);
    std::optional<std::uint32_t> accepted_override;
    if (options.point_override && preset_index_for(*options.point_override)) {
        accepted_override = options.point_override;
    } else if (options.point_override) {
        std::cerr << "Ignoring unsupported point override " << *options.point_override
                  << "; use a declared Point Lab preset.\n";
    }
    const std::uint32_t gameplay_points = accepted_override.value_or(
        machine_profile.profile.recommended.environment_points);
    const signalcloud::render::AdaptivePointBudget effective_budget{
        gameplay_points,
        machine_profile.profile.status + "-" + machine_profile.profile.gpu_class,
        machine_profile.reason,
    };
    write_budget_report(options.root / "reports/pivot13_budget.txt", capability,
                        effective_budget, accepted_override);
    std::cout << "Machine profile target: " << profile_target_hint.width << 'x'
              << profile_target_hint.height << " @ " << profile_target_hint.target_fps << " FPS"
              << (profile_target_hint.from_active_profile ? " | bootstrapped from active profile"
                                                          : " | default startup target") << '\n';
    std::cout << "Machine profile: " << machine_profile.profile.status
              << " | source " << machine_profile.profile.source_kind
              << " | ruleset " << machine_profile.profile.ruleset_id
              << " | fingerprint " << machine_profile.profile.fingerprint
              << " | " << machine_profile.reason << '\n';
    std::cout << "Pivot 13 a3 point profile: " << effective_budget.profile
              << " | gameplay points: " << gameplay_points
              << " | protected fallback: "
              << machine_profile.profile.recommended.protected_fallback_points
              << " | submitted soft cap: "
              << machine_profile.profile.recommended.submitted_soft_cap << '\n';

    std::uint32_t tape_index = 0U;
    auto level_seed = signalcloud::world::mix_seed(0xA12D0A1ULL, {0, 0, 0}, 4);
    auto level = signalcloud::world::LiminalLevel::make_pivot11_scavenging(level_seed);
    write_layout_report(options.root / "reports/pivot13_layout.txt", level);
    signalcloud::render::PointLabState point_lab;
    if (const auto index = preset_index_for(gameplay_points)) point_lab.select_preset(*index);

    auto cloud = signalcloud::render::PointCloud::make_liminal_level(level, {gameplay_points, level_seed});
    signalcloud::render::PointRenderer renderer;
    std::string render_error;
    if (!renderer.initialize(gl, cloud, &render_error)) {
        std::cerr << render_error << '\n';
        SDL_GL_DestroyContext(context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 6;
    }

    double last_generation_ms = 0.0;
    auto load_selected_preset = [&]() -> bool {
        std::ostringstream loading;
        loading << "ALMOND SIGNAL | GENERATING " << point_lab.preset().name
                << " LIMINAL CLOUD (" << point_lab.preset().points << " points)";
        SDL_SetWindowTitle(window, loading.str().c_str());
        SDL_PumpEvents();
        const auto started = std::chrono::steady_clock::now();
        auto next = signalcloud::render::PointCloud::make_liminal_level(
            level, {point_lab.preset().points, level_seed});
        const auto generated = std::chrono::steady_clock::now();
        std::string upload_error;
        if (!renderer.upload_cloud(next, &upload_error)) {
            std::cerr << "Point preset upload failed: " << upload_error << '\n';
            return false;
        }
        cloud = std::move(next);
        const auto finished = std::chrono::steady_clock::now();
        last_generation_ms = std::chrono::duration<double, std::milli>(finished - started).count();
        const double generation_only_ms = std::chrono::duration<double, std::milli>(generated - started).count();
        std::cout << "Pivot 13 a3 resident preset " << point_lab.preset().name << " loaded: "
                  << renderer.resident_count() << " resident points | generation " << generation_only_ms
                  << " ms | generation+upload " << last_generation_ms << " ms\n";
        return true;
    };

    signalcloud::platform::FirstPersonCamera camera;
    signalcloud::world::PlayerController player(level.spawn_position());
    signalcloud::combat::CombatSystem combat = signalcloud::combat::CombatSystem::make_pivot10();
    signalcloud::economy::EconomySystem economy = signalcloud::economy::EconomySystem::make_pivot12();
    std::vector<std::string> pcp3_warnings;
    auto pcp3_assets = signalcloud::pcp3::discover_assets(options.root, &pcp3_warnings);
    const auto suppress_legacy_welcome_cloud = [](std::vector<signalcloud::pcp3::Asset>& assets) {
        for (auto& asset : assets) {
            if (asset.metadata.asset_id == "a3_preview_marker") {
                // A5a3r2 renders this marker through the native SCFONT path.
                // Preserve its validated PCP3 metadata as the authored anchor,
                // but suppress the old fixed-scale blob cloud.
                asset.metadata.auto_preview_in_game = false;
            }
        }
    };
    suppress_legacy_welcome_cloud(pcp3_assets);
    if (!pcp3_assets.empty()) {
        std::cout << "Point Cloud Paint++ assets discovered: " << pcp3_assets.size() << '\n';
    }
    for (const auto& warning : pcp3_warnings) {
        std::cerr << "PCP3 asset warning: " << warning << '\n';
    }
    signalcloud::pcp3::RuntimeInteractionState pcp3_interactions;
    signalcloud::pcp3::RuntimeEncounterState pcp3_encounters;
    auto threat_director = signalcloud::world::ThreatDirector::make_pivot13(level);
    signalcloud::world::RecoverySystem recovery;
    signalcloud::render::AdaptiveResidencyController residency(point_lab.preset().points);
    signalcloud::ui::ArInterface ar_interface;
    signalcloud::font::FontService font_service;
    const auto core_font_path = options.root / "content/core/fonts/terminal_00/Terminal_00.scfont";
    if (font_service.load("core.fonts.terminal_00", core_font_path) &&
        font_service.set_default("core.fonts.terminal_00")) {
        const auto loaded_font = font_service.default_font();
        std::cout << "SCFONT runtime ready: " << (loaded_font ? loaded_font->name : std::string("unknown"))
                  << " | glyphs " << (loaded_font ? loaded_font->glyphs.size() : 0U)
                  << " | generation " << font_service.generation(font_service.default_font_id()) << '\n';
    } else {
        std::cerr << "SCFONT warning: Terminal_00 could not be loaded; legacy point alphabet remains active.\n";
        for (const auto& issue : font_service.issues()) {
            std::cerr << "SCFONT " << issue.font_id << ": " << issue.message << '\n';
        }
    }
    ar_interface.set_font(font_service.default_font());
    try {
        const auto playbooks = signalcloud::ai::PlaybookRuntime::load(
            options.root / "user_data/studio/playbook_runtime.scplayruntime");
        std::cout << "Universal Playbook runtime ready: " << playbooks.stats().graph_count
                  << " graphs | " << playbooks.stats().node_count << " nodes | "
                  << playbooks.stats().edge_count << " edges | budget "
                  << playbooks.stats().point_budget_cost << " | signature "
                  << playbooks.stats().signature
                  << " | Hash Dog compatibility consumer staged for A6a2\n";
    } catch (const std::exception& error) {
        std::cerr << "Playbook runtime warning: " << error.what()
                  << " (existing behavior remains active)\n";
    }
    const auto hot_reload_index = signalcloud::assets::HotReloadIndex::load(
        options.root, options.root / "user_data/studio/hot_reload_candidates.udata");
    if (hot_reload_index.valid()) {
        std::cout << "Protected authoring hot-reload discovery: "
                  << hot_reload_index.entries().size() << " validated candidates; normal saves excluded.\n";
    } else {
        for (const auto& issue : hot_reload_index.errors()) {
            std::cerr << "Hot-reload index warning: " << issue << '\n';
        }
    }

    const auto scui_registry_path = options.root / "content/core/ui/scui_panel_registry.udata";
    auto scui_registry = signalcloud::ui::ScuiPanelRegistry::load(options.root, scui_registry_path);
    for (const auto& issue : scui_registry.issues()) {
        std::cerr << "SCUI registry " << issue.location << ": " << issue.message << '\n';
    }
    if (scui_registry.valid()) {
        std::cout << "SCUI panel registry ready: " << scui_registry.entries().size()
                  << " trusted authoring panels.\n";
    }
    const auto registered_path = [&](std::string_view key, std::string_view fallback) {
        const auto* entry = scui_registry.find(key);
        return options.root / (entry != nullptr ? entry->relative_path : std::filesystem::path(fallback));
    };
    const auto register_entry_commands = [&](signalcloud::ui::ScuiNativeRuntime& runtime,
                                             std::string_view key,
                                             const std::vector<std::string>& fallback) {
        const auto* entry = scui_registry.find(key);
        const auto& commands = entry != nullptr && !entry->commands.empty() ? entry->commands : fallback;
        for (const auto& command : commands) (void)runtime.register_command(command);
    };

    auto selector_panel = signalcloud::ui::ScuiPanel::load(
        options.root / "content/core/ui/authoring_lab_panel_selector.scui");
    signalcloud::ui::ScuiNativeRuntime panel_selector_scui(std::move(selector_panel), 4U);
    panel_selector_scui.set_font(font_service.default_font());
    (void)panel_selector_scui.register_command("authoring.panel.select");
    (void)panel_selector_scui.register_command("authoring.panel.open");
    (void)panel_selector_scui.register_command("authoring.panel.refresh");
    if (scui_registry.valid()) {
        (void)panel_selector_scui.set_choices(
            "panel", scui_registry.keys(), std::string(scui_registry.default_panel_key()));
        (void)panel_selector_scui.set_number(
            "registry_count", static_cast<double>(scui_registry.entries().size()));
    }

    const auto project_scui_path = registered_path(
        "project-selector", "content/core/ui/authoring_lab_project_selector.scui");
    signalcloud::ui::ScuiNativeRuntime project_scui(
        signalcloud::ui::ScuiPanel::load(project_scui_path), 4U);
    project_scui.set_font(font_service.default_font());
    (void)project_scui.register_command("authoring.project.select");
    (void)project_scui.register_command("authoring.preview.toggle");
    (void)project_scui.register_command("authoring.point_budget.set");
    (void)project_scui.register_command("authoring.profile.refresh");
    register_entry_commands(project_scui, "project-selector", {
        "authoring.project.select", "authoring.preview.toggle",
        "authoring.point_budget.set", "authoring.profile.refresh"});
    if (!project_scui.valid()) {
        std::cerr << "Native SCUI proof panel could not be loaded; F8 panel disabled.\n";
        for (const auto& issue : project_scui.panel().issues) {
            std::cerr << "SCUI " << issue.location << ": " << issue.message << '\n';
        }
    } else {
        std::cout << "Native point SCUI ready: F8 opens the non-destructive Authoring Lab proof panel.\n";
    }

    const auto light_scui_path = registered_path(
        "light-lab", "content/core/ui/light_lab_control_surface.scui");
    signalcloud::ui::ScuiNativeRuntime light_scui(
        signalcloud::ui::ScuiPanel::load(light_scui_path), 4U);
    light_scui.set_font(font_service.default_font());
    register_entry_commands(light_scui, "light-lab", {
        "light.scope.set", "light.illuminosity.set", "light.radius.set",
        "light.day_illuminosity.set", "light.night_illuminosity.set",
        "light.time_of_day.set", "light.timeline.play", "light.timeline.pause",
        "light.timeline.stop", "light.probe.sample", "light.diagnostics.bake",
        "light.document.reload", "light.document.save"});
    const auto* light_registry_entry = scui_registry.find("light-lab");
    const std::filesystem::path light_state_relative =
        light_registry_entry != nullptr && !light_registry_entry->native_state_path.empty()
            ? light_registry_entry->native_state_path
            : std::filesystem::path("user_data/studio/light_lab_native_state.udata");
    const std::string light_default_document =
        light_registry_entry != nullptr && !light_registry_entry->default_document.empty()
            ? light_registry_entry->default_document.generic_string()
            : "content/core/lights/authoring_lab_default.slight";
    signalcloud::ui::ScuiNativeBindingStore light_scui_store(
        options.root / light_state_relative, light_default_document);
    std::string light_state_error;
    if (!light_scui_store.load(light_scui, &light_state_error)) {
        std::cerr << "Light Lab native overlay warning: " << light_state_error << '\n';
    }
    if (light_scui.valid()) {
        std::cout << "Native Light Lab SCUI ready: F7 opens it in protected safe rooms.\n";
    }
    if (panel_selector_scui.valid()) {
        std::cout << "Native Authoring Lab registry selector ready: F6 opens it in protected safe rooms.\n";
    }

    const auto tupd_scui_path = registered_path(
        "tupd-workbench", "content/core/ui/tupd_workbench.scui");
    signalcloud::ui::ScuiNativeRuntime tupd_scui(
        signalcloud::ui::ScuiPanel::load(tupd_scui_path), 4U);
    tupd_scui.set_font(font_service.default_font());
    register_entry_commands(tupd_scui, "tupd-workbench", {
        "tupd.recipe.select", "tupd.test-action.select", "tupd.preview", "tupd.commit",
        "tupd.instance.equip", "tupd.instance.test", "tupd.instance.clear",
        "tupd.ghost.view", "tupd.ghost.toggle",
        "tupd.reset", "tupd.export", "tupd.reload"});
    std::vector<signalcloud::items::TupdRecipe> tupd_recipes;
    std::vector<std::string> tupd_recipe_keys;
    std::size_t tupd_recipe_index = 0U;
    std::size_t tupd_test_action_index = 0U;
    signalcloud::items::TupdSandboxSession tupd_sandbox;
    signalcloud::items::TupdPreview tupd_preview;
    signalcloud::ui::TupdGhostPreview tupd_ghost_preview;
    auto tupd_ghost_inspection_mode = signalcloud::ui::TupdGhostInspectionMode::result;
    bool tupd_ghost_exploded = false;
    const auto reload_tupd_catalog = [&]() {
        tupd_recipes.clear();
        tupd_recipe_keys.clear();
        for (const auto& path : signalcloud::items::discover_tupd_recipes(options.root)) {
            signalcloud::items::TupdRecipe recipe;
            std::string recipe_error;
            if (signalcloud::items::load_tupd_recipe(path, recipe, &recipe_error)) {
                tupd_recipe_keys.push_back(recipe.recipe_id);
                tupd_recipes.push_back(std::move(recipe));
            } else {
                std::cerr << "Tupd recipe skipped: " << path << " | " << recipe_error << '\n';
            }
        }
        if (tupd_recipes.empty()) {
            tupd_recipe_index = 0U;
            tupd_preview = {};
            return false;
        }
        const std::string selected = tupd_scui.string("recipe_key").value_or(tupd_recipe_keys.front());
        const auto found = std::find(tupd_recipe_keys.begin(), tupd_recipe_keys.end(), selected);
        tupd_recipe_index = found == tupd_recipe_keys.end()
            ? 0U : static_cast<std::size_t>(std::distance(tupd_recipe_keys.begin(), found));
        (void)tupd_scui.set_choices("recipe", tupd_recipe_keys, tupd_recipe_keys[tupd_recipe_index]);
        tupd_test_action_index = 0U;
        const auto& actions = tupd_recipes[tupd_recipe_index].test_actions;
        (void)tupd_scui.set_choices("test_action", actions, actions.empty() ? std::string{} : actions.front());
        tupd_sandbox.reset();
        tupd_preview = tupd_sandbox.preview(tupd_recipes[tupd_recipe_index]);
        return true;
    };
    const auto sync_tupd_scui = [&]() {
        if (tupd_recipes.empty()) return;
        (void)tupd_scui.set_string("recipe_key", tupd_recipes[tupd_recipe_index].recipe_id);
        const auto& actions = tupd_recipes[tupd_recipe_index].test_actions;
        const std::string selected_action = actions.empty() ? std::string{} : actions[tupd_test_action_index % actions.size()];
        (void)tupd_scui.set_choices("test_action", actions, selected_action);
        (void)tupd_scui.set_string("test_action_key", selected_action);
        (void)tupd_scui.set_number("condition_before", tupd_preview.condition_before);
        (void)tupd_scui.set_number("condition_after", tupd_preview.condition_after);
        (void)tupd_scui.set_number("stability_percent", tupd_preview.stability_percent);
        (void)tupd_scui.set_number("weight_delta", tupd_preview.weight_delta);
        (void)tupd_scui.set_number("point_budget", static_cast<double>(tupd_preview.point_budget));
        const auto tape = tupd_sandbox.inventory().items.find("consumable.tupd-tape");
        (void)tupd_scui.set_number("test_tapes", tape == tupd_sandbox.inventory().items.end() ? 0.0 : tape->second);
        (void)tupd_scui.set_number("test_xar", tupd_sandbox.inventory().xar);
        double result_state = 0.0;
        double test_count = 0.0;
        if (tupd_sandbox.result_instance()) {
            const auto& instance = *tupd_sandbox.result_instance();
            result_state = instance.broken ? 3.0 : ((instance.equipped || instance.spawned) ? 2.0 : 1.0);
            test_count = static_cast<double>(instance.test_count);
        }
        (void)tupd_scui.set_number("result_state", result_state);
        (void)tupd_scui.set_number("test_count", test_count);
        (void)tupd_scui.set_string(
            "ghost_view_key",
            std::string(signalcloud::ui::tupd_ghost_inspection_name(tupd_ghost_inspection_mode)));
        (void)tupd_scui.set_number("ghost_exploded", tupd_ghost_exploded ? 1.0 : 0.0);
    };
    (void)reload_tupd_catalog();
    sync_tupd_scui();
    if (tupd_scui.valid() && !tupd_recipes.empty()) {
        std::cout << "Native Tupd Authoring SCUI ready: F5 opens an isolated A8a3r1 sandbox with assembled/exploded inspection in protected safe rooms | recipes "
                  << tupd_recipes.size() << ".\n";
    }

    signalcloud::ui::ScuiLightPreview light_scui_preview;
    signalcloud::materials::MaterialRuntime material_runtime(
        options.root, options.root / "user_data/studio/material_runtime.udata");
    std::string material_error;
    if (material_runtime.reload(&material_error)) {
        const auto& material_stats = material_runtime.stats();
        std::cout << "Material runtime ready: " << material_stats.material_count
                  << " materials | " << material_stats.assignment_count << " assignments | budget "
                  << material_stats.selected_point_budget << "/" << material_stats.max_point_budget
                  << " | mode " << material_stats.mode << " | signature " << material_stats.signature << '\n';
        const auto proof_materials = material_runtime.evaluate("Reception Tape");
        const auto& wall_pattern = proof_materials.surfaces[1];
        std::cout << "Wallpaper pattern: " << signalcloud::materials::pattern_mode_name(wall_pattern.pattern_mode)
                  << " | spacing " << wall_pattern.primary_spacing << "/" << wall_pattern.secondary_spacing
                  << " | breakup " << wall_pattern.breakup_strength
                  << " | displacement " << wall_pattern.displacement_weight << '\n';
        std::ofstream report(options.root / "reports/material_runtime.txt", std::ios::trunc);
        report << "source_graph=" << material_stats.source_graph << '\n'
               << "mode=" << material_stats.mode << '\n'
               << "material_count=" << material_stats.material_count << '\n'
               << "assignment_count=" << material_stats.assignment_count << '\n'
               << "selected_materials=" << material_stats.selected_materials << '\n'
               << "selected_point_budget=" << material_stats.selected_point_budget << '\n'
               << "max_point_budget=" << material_stats.max_point_budget << '\n'
               << "warning_count=" << material_stats.warning_count << '\n'
               << "signature=" << material_stats.signature << '\n'
               << "wall_pattern=" << signalcloud::materials::pattern_mode_name(wall_pattern.pattern_mode) << '\n'
               << "wall_primary_spacing=" << wall_pattern.primary_spacing << '\n'
               << "wall_secondary_spacing=" << wall_pattern.secondary_spacing << '\n'
               << "wall_breakup_strength=" << wall_pattern.breakup_strength << '\n'
               << "wall_displacement_weight=" << wall_pattern.displacement_weight << '\n';
    } else {
        std::cerr << "Material runtime warning: " << material_error
                  << " (neutral material defaults remain active)\n";
    }
    signalcloud::audio::AudioInterferenceRuntime audio_interference_runtime(
        options.root, options.root / "user_data/studio/audio_interference_runtime.udata");
    std::string audio_interference_error;
    if (audio_interference_runtime.reload(&audio_interference_error)) {
        const auto& audio_stats = audio_interference_runtime.stats();
        const auto& bark = audio_interference_runtime.hash_dog_bark();
        std::cout << "Audio interference runtime ready: " << audio_stats.profile_count
                  << " profile | band " << signalcloud::render::frequency_band_name(bark.frequency_band)
                  << " | waves " << bark.wave_count
                  << " | budget " << audio_stats.point_budget_cost
                  << " | signature " << audio_stats.signature << '\n';
        std::ofstream report(options.root / "reports/audio_interference_runtime.txt", std::ios::trunc);
        report << "source_profile=" << audio_stats.source_profile << '\n'
               << "profile_count=" << audio_stats.profile_count << '\n'
               << "warning_count=" << audio_stats.warning_count << '\n'
               << "signature=" << audio_stats.signature << '\n'
               << "frequency_band=" << signalcloud::render::frequency_band_name(bark.frequency_band) << '\n'
               << "wave_count=" << bark.wave_count << '\n'
               << "wave_sharpness=" << bark.wave_sharpness << '\n'
               << "displacement_scale=" << bark.displacement_scale << '\n'
               << "color_mix=" << bark.color_mix << '\n'
               << "hearing_loudness=" << bark.hearing_loudness << '\n'
               << "cooldown_seconds=" << bark.cooldown_seconds << '\n'
               << "point_budget_cost=" << bark.point_budget_cost << '\n';
    } else {
        std::cerr << "Audio interference runtime warning: " << audio_interference_error
                  << " (safe built-in bark profile remains active)\n";
    }
    signalcloud::lighting::IlluminosityRuntime illuminosity_runtime(
        options.root, options.root / "user_data/studio/illuminosity_runtime.udata");
    std::string illuminosity_error;
    if (illuminosity_runtime.reload(&illuminosity_error)) {
        const auto& light_stats = illuminosity_runtime.stats();
        std::cout << "Illuminosity runtime ready: " << light_stats.configured_lights
                  << " configured | " << light_stats.enabled_lights << " enabled | selected "
                  << light_stats.budget_active_lights << " | budget "
                  << light_stats.selected_point_budget_cost << "/" << light_stats.effective_max_point_budget
                  << " | source " << light_stats.source_document
                  << " | signature " << light_stats.deterministic_signature << '\n';
        const auto rays = illuminosity_runtime.diagnostic_rays_all(level);
        std::ofstream report(options.root / "reports/illuminosity_runtime.txt", std::ios::trunc);
        report << "source=" << light_stats.source_document << '\n'
               << "configured_lights=" << light_stats.configured_lights << '\n'
               << "enabled_lights=" << light_stats.enabled_lights << '\n'
               << "point_budget_cost=" << light_stats.point_budget_cost << '\n'
               << "selected_point_budget_cost=" << light_stats.selected_point_budget_cost << '\n'
               << "effective_max_point_budget=" << light_stats.effective_max_point_budget << '\n'
               << "budget_active_lights=" << light_stats.budget_active_lights << '\n'
               << "budget_limited_lights=" << light_stats.budget_limited_lights << '\n'
               << "warning_count=" << light_stats.warning_count << '\n'
               << "diagnostic_rays=" << rays.size() << '\n'
               << "deterministic_signature=" << light_stats.deterministic_signature << '\n';
    } else {
        std::cerr << "Illuminosity runtime warning: " << illuminosity_error
                  << " (safe neutral renderer defaults remain active)\n";
    }

    enum class NativeScuiKind { none, panel_selector, project_selector, light_lab, tupd_workbench };
    NativeScuiKind active_scui_kind = NativeScuiKind::none;
    auto active_native_scui = [&]() -> signalcloud::ui::ScuiNativeRuntime* {
        if (active_scui_kind == NativeScuiKind::panel_selector) return &panel_selector_scui;
        if (active_scui_kind == NativeScuiKind::project_selector) return &project_scui;
        if (active_scui_kind == NativeScuiKind::light_lab) return &light_scui;
        if (active_scui_kind == NativeScuiKind::tupd_workbench) return &tupd_scui;
        return nullptr;
    };
    auto native_scui_open = [&]() -> bool {
        const auto* runtime = active_native_scui();
        return runtime != nullptr && runtime->open();
    };
    camera.set_position(player.position());
    signalcloud::ui::TacticalMemoryMap tactical_map;
    tactical_map.set_storage_root(options.root / "user_data/tactical_maps");
    std::array<bool, SDL_SCANCODE_COUNT> keys{};
    bool running = true;
    bool mouse_captured = true;
    bool mouse_capture_before_scui = true;
    bool system_cursor_visible_before_scui = false;
    bool raw_probe = true;
    bool tactical = false;
    bool scanner = false;
    bool lab_mode = false;
    bool detailed_title = false;
    bool jump_pressed = false;
    bool primary_held = false;
    bool quick_action_pressed = false;
    bool reload_pressed = false;
    bool use_item_pressed = false;
    int weapon_slot = 1;
    int belt_slot = 1;
    float movement_amount = 0.0F;
    bool player_sprinting = false;
    float pulse = 0.0F;
    float safe_lock_cooldown = 0.0F;
    float fps = 0.0F;
    double fps_time = 0.0;
    int fps_frames = 0;
    double previous = static_cast<double>(SDL_GetTicksNS()) / 1'000'000'000.0;
    double portal_ready_time = previous;
    const auto benchmark_path = options.root / "reports/point_lab_benchmark.csv";
    std::string current_zone(level.zone_name(player.position()));
    tactical_map.reset(level, current_zone);
    signalcloud::render::SignalInterference signal_interference;
    signalcloud::render::LocalSirenSource local_siren;
    signalcloud::render::WaterDisturbance water_disturbance;
    signalcloud::render::SoundRipple sound_ripple;
    float hash_dog_bark_cooldown = 2.5F;
    std::uint32_t hash_dog_bark_events = 0U;
    signalcloud::audio::SplashAudio splash_audio;
    if (audio_subsystem_ready && !splash_audio.initialize()) {
        std::cerr << "Splash audio warning: " << SDL_GetError()
                  << " (visual and AI-audibility events remain enabled)\n";
    }
    signal_interference.update(0.0, point_lab.preset().points);
    signalcloud::render::RoomVisibilitySelection visibility;
    const auto stream_log_path = options.root / "reports/room_stream_trace.csv";
    const auto traversal_log_path = options.root / "reports/traversal_trace.csv";
    const auto depth_log_path = options.root / "reports/depth_trace.csv";
    const auto combat_log_path = options.root / "reports/combat_trace.csv";
    const auto economy_log_path = options.root / "reports/economy_trace.csv";
    double next_stream_log_time = previous;
    double next_traversal_log_time = previous;
    double next_depth_log_time = previous;
    std::uint32_t last_water_entry_serial = player.water_entry_serial();
    std::uint32_t last_save_jump_count = player.save_jump_count();
    std::uint32_t last_tech_pickup_count = player.tech_pickup_count();
    std::uint32_t last_rescue_count = player.rescue_count();
    float current_distance_limit = 46.0F;
    append_zone_log(options.root / "reports/zone_trace.log", previous, current_zone, player.position());
    SDL_SetWindowRelativeMouseMode(window, mouse_captured);

    const auto scui_kind_key = [](NativeScuiKind kind) -> std::string_view {
        if (kind == NativeScuiKind::project_selector) return "project-selector";
        if (kind == NativeScuiKind::light_lab) return "light-lab";
        if (kind == NativeScuiKind::tupd_workbench) return "tupd-workbench";
        return {};
    };
    const auto scui_kind_label = [](NativeScuiKind kind) -> std::string_view {
        if (kind == NativeScuiKind::panel_selector) return "Authoring Lab panel selector";
        if (kind == NativeScuiKind::project_selector) return "Project Selector";
        if (kind == NativeScuiKind::light_lab) return "Illuminosity Light Lab";
        if (kind == NativeScuiKind::tupd_workbench) return "Tupd Authoring Workbench";
        return "SCUI";
    };
    auto set_native_scui_open = [&](NativeScuiKind kind) {
        const bool was_open = native_scui_open();
        if (kind != NativeScuiKind::none) {
            bool safe_room_only = kind == NativeScuiKind::panel_selector;
            const std::string_view registry_key = scui_kind_key(kind);
            if (!registry_key.empty()) {
                if (const auto* entry = scui_registry.find(registry_key); entry != nullptr) {
                    safe_room_only = entry->safe_room_only;
                }
            }
            if (safe_room_only && !is_safe_room(current_zone)) {
                if (kind == NativeScuiKind::light_lab) {
                    std::cout << "Native Light Lab SCUI is limited to protected safe rooms.\n";
                } else {
                    std::cout << "Native " << scui_kind_label(kind)
                              << " is limited to protected safe rooms.\n";
                }
                return;
            }
            active_scui_kind = kind;
            auto* runtime = active_native_scui();
            if (runtime == nullptr || !runtime->valid()) {
                active_scui_kind = NativeScuiKind::none;
                return;
            }
            panel_selector_scui.set_open(runtime == &panel_selector_scui);
            project_scui.set_open(runtime == &project_scui);
            light_scui.set_open(runtime == &light_scui);
            tupd_scui.set_open(runtime == &tupd_scui);
            if (runtime == &tupd_scui && !tupd_recipes.empty()) {
                tupd_preview = tupd_sandbox.preview(tupd_recipes[tupd_recipe_index]);
                sync_tupd_scui();
                std::cout << "Tupd sandbox normal save: "
                          << (tupd_sandbox.normal_save_unchanged() ? "UNCHANGED" : "ERROR") << '\n';
            }
            if (!was_open) {
                mouse_capture_before_scui = mouse_captured;
                system_cursor_visible_before_scui = SDL_CursorVisible();
            }
            mouse_captured = false;
            tactical = false;
            primary_held = false;
            keys.fill(false);
            if (economy.vending_menu_active()) economy.close_vending_menu();
            SDL_SetWindowRelativeMouseMode(window, false);
            (void)SDL_HideCursor();
            std::cout << "Native " << scui_kind_label(kind)
                      << " opened: arrows/Tab navigate, Enter/Space confirms, mouse selects, F5/F6/F7/F8/Escape closes, F9 reloads staged preview; system cursor hidden.\n";
        } else {
            panel_selector_scui.set_open(false);
            project_scui.set_open(false);
            light_scui.set_open(false);
            tupd_scui.set_open(false);
            active_scui_kind = NativeScuiKind::none;
            keys.fill(false);
            primary_held = false;
            mouse_captured = mouse_capture_before_scui;
            SDL_SetWindowRelativeMouseMode(window, mouse_captured);
            if (mouse_captured || !system_cursor_visible_before_scui) (void)SDL_HideCursor();
            else (void)SDL_ShowCursor();
            std::cout << "Native point SCUI closed; gameplay input restored.\n";
        }
    };

    const auto reload_registered_scui = [&](NativeScuiKind kind, const std::filesystem::path& path) -> bool {
        auto replacement = signalcloud::ui::ScuiNativeRuntime(signalcloud::ui::ScuiPanel::load(path), 4U);
        replacement.set_font(font_service.default_font());
        if (!replacement.valid()) return false;
        if (kind == NativeScuiKind::panel_selector) {
            (void)replacement.register_command("authoring.panel.select");
            (void)replacement.register_command("authoring.panel.open");
            (void)replacement.register_command("authoring.panel.refresh");
            if (scui_registry.valid()) {
                (void)replacement.set_choices("panel", scui_registry.keys(), panel_selector_scui.string("panel_key"));
                (void)replacement.set_number("registry_count", static_cast<double>(scui_registry.entries().size()));
            }
            replacement.set_open(active_scui_kind == kind);
            panel_selector_scui = std::move(replacement);
            return true;
        }
        if (kind == NativeScuiKind::project_selector) {
            register_entry_commands(replacement, "project-selector", {
                "authoring.project.select", "authoring.preview.toggle",
                "authoring.point_budget.set", "authoring.profile.refresh"});
            replacement.set_open(active_scui_kind == kind);
            project_scui = std::move(replacement);
            return true;
        }
        if (kind == NativeScuiKind::light_lab) {
            register_entry_commands(replacement, "light-lab", {
                "light.scope.set", "light.illuminosity.set", "light.radius.set",
                "light.day_illuminosity.set", "light.night_illuminosity.set",
                "light.time_of_day.set", "light.timeline.play", "light.timeline.pause",
                "light.timeline.stop", "light.probe.sample", "light.diagnostics.bake",
                "light.document.reload", "light.document.save"});
            replacement.set_open(active_scui_kind == kind);
            light_scui = std::move(replacement);
            std::string state_error;
            (void)light_scui_store.load(light_scui, &state_error);
            return true;
        }
        if (kind == NativeScuiKind::tupd_workbench) {
            register_entry_commands(replacement, "tupd-workbench", {
                "tupd.recipe.select", "tupd.test-action.select", "tupd.preview", "tupd.commit",
                "tupd.instance.equip", "tupd.instance.test", "tupd.instance.clear",
                "tupd.reset", "tupd.export", "tupd.reload"});
            replacement.set_open(active_scui_kind == kind);
            tupd_scui = std::move(replacement);
            (void)tupd_scui.set_choices("recipe", tupd_recipe_keys,
                tupd_recipes.empty() ? std::string{} : tupd_recipes[tupd_recipe_index].recipe_id);
            sync_tupd_scui();
            return true;
        }
        return false;
    };

    const auto apply_staged_hot_reload = [&](double now_seconds) {
        if (!is_safe_room(current_zone)) {
            std::cout << "Protected preview reload is limited to safe rooms.\n";
            return;
        }
        const auto status_path = options.root / "user_data/studio/hot_reload_latest.udata";
        const auto status = signalcloud::assets::HotReloadStatus::load(options.root, status_path);
        auto* active = active_native_scui();
        if (!status.valid()) {
            if (active != nullptr) active->show_notice(signalcloud::ui::ScuiNativeNoticeKind::warning,
                                                       "STAGE RELOAD IN STUDIO", static_cast<float>(now_seconds), 2.6F);
            std::cout << "Protected preview reload status is unavailable; run ./scripts/stage_hot_reload_preview.sh or use Asset Doctor.\n";
            return;
        }
        bool applied = false;
        bool scui_applied = false;
        bool light_applied = false;
        bool material_applied = false;
        bool audio_applied = false;
        bool font_applied = false;
        std::size_t pcp3_applied = 0U;
        std::string apply_error;
        const auto changed_scui = [&](const std::filesystem::path& path) {
            const auto relative = path.lexically_relative(options.root).generic_string();
            return status.changed_for_path(relative) != nullptr;
        };
        if (active_scui_kind == NativeScuiKind::panel_selector &&
            changed_scui(options.root / "content/core/ui/authoring_lab_panel_selector.scui")) {
            scui_applied = reload_registered_scui(active_scui_kind,
                options.root / "content/core/ui/authoring_lab_panel_selector.scui");
            applied = applied || scui_applied;
        } else if (active_scui_kind == NativeScuiKind::project_selector && changed_scui(project_scui_path)) {
            scui_applied = reload_registered_scui(active_scui_kind, project_scui_path);
            applied = applied || scui_applied;
        } else if (active_scui_kind == NativeScuiKind::light_lab && changed_scui(light_scui_path)) {
            scui_applied = reload_registered_scui(active_scui_kind, light_scui_path);
            applied = applied || scui_applied;
        } else if (active_scui_kind == NativeScuiKind::tupd_workbench && changed_scui(tupd_scui_path)) {
            scui_applied = reload_registered_scui(active_scui_kind, tupd_scui_path);
            applied = applied || scui_applied;
        }
        if (const auto* light = status.changed_light_set(); light != nullptr) {
            bool light_controls_applied = false;
            bool light_runtime_applied = false;
            signalcloud::ui::ScuiNativeBindingStore staged_store(
                options.root / light->staged_state_path, light_default_document);
            std::string stage_error;
            if (staged_store.load(light_scui, &stage_error)) {
                light_controls_applied = true;
            } else {
                apply_error = stage_error;
                std::cerr << "Protected Light Lab control reload failed: " << stage_error << '\n';
            }

            signalcloud::lighting::IlluminosityRuntime staged_runtime(
                options.root, options.root / light->compiled_runtime_path);
            stage_error.clear();
            if (staged_runtime.reload(&stage_error)) {
                illuminosity_runtime = std::move(staged_runtime);
                light_runtime_applied = true;
            } else {
                apply_error = stage_error;
                std::cerr << "Protected Illuminosity runtime reload failed: " << stage_error << '\n';
            }
            light_applied = light_controls_applied && light_runtime_applied;
            applied = applied || light_applied;
        }
        if (const auto* material = status.changed_material_set(); material != nullptr) {
            signalcloud::materials::MaterialRuntime staged_runtime(
                options.root, options.root / material->compiled_runtime_path);
            std::string stage_error;
            if (staged_runtime.reload(&stage_error)) {
                material_runtime = std::move(staged_runtime);
                material_applied = true;
                applied = true;
            } else {
                apply_error = stage_error;
                std::cerr << "Protected material runtime reload failed: " << stage_error << '\n';
            }
        }
        if (const auto* audio = status.changed_audio_profile(); audio != nullptr) {
            signalcloud::audio::AudioInterferenceRuntime staged_runtime(
                options.root, options.root / audio->compiled_runtime_path);
            std::string stage_error;
            if (staged_runtime.reload(&stage_error)) {
                audio_interference_runtime = std::move(staged_runtime);
                audio_applied = true;
                applied = true;
            } else {
                apply_error = stage_error;
                std::cerr << "Protected audio-interference runtime reload failed: " << stage_error << '\n';
            }
        }
        if (const auto* changed_font = status.changed_font(); changed_font != nullptr) {
            const std::string font_id = changed_font->asset_id.empty()
                ? std::string(font_service.default_font_id()) : changed_font->asset_id;
            const auto candidate_path = options.root / changed_font->relative_path;
            const bool loaded = font_service.snapshot(font_id)
                ? font_service.reload(font_id, candidate_path)
                : font_service.load(font_id, candidate_path);
            if (loaded) {
                if (font_service.default_font_id().empty()) (void)font_service.set_default(font_id);
                const auto snapshot = font_service.default_font();
                panel_selector_scui.set_font(snapshot);
                project_scui.set_font(snapshot);
                light_scui.set_font(snapshot);
                tupd_scui.set_font(snapshot);
                ar_interface.set_font(snapshot);
                font_applied = true;
                applied = true;
            } else {
                apply_error = font_service.issues().empty()
                    ? "font validation failed" : font_service.issues().back().message;
                std::cerr << "Protected SCFONT reload failed: " << apply_error << '\n';
            }
        }
        const auto changed_pcp3 = status.changed_pcp3_projects();
        if (!changed_pcp3.empty()) {
            std::vector<std::string> refresh_warnings;
            auto refreshed_assets = signalcloud::pcp3::discover_assets(options.root, &refresh_warnings);
            if (refresh_warnings.empty()) {
                pcp3_assets = std::move(refreshed_assets);
                suppress_legacy_welcome_cloud(pcp3_assets);
                pcp3_interactions.reset();
                pcp3_encounters.reset();
                pcp3_applied = changed_pcp3.size();
                applied = true;
            } else {
                apply_error = refresh_warnings.front();
                for (const auto& warning : refresh_warnings) {
                    std::cerr << "Protected PCP3 preview reload failed: " << warning << '\n';
                }
            }
        }
        active = active_native_scui();
        if (active != nullptr) {
            active->show_notice(
                applied ? signalcloud::ui::ScuiNativeNoticeKind::success
                        : signalcloud::ui::ScuiNativeNoticeKind::info,
                applied ? "PREVIEW RELOADED" : "NO STAGED CHANGE",
                static_cast<float>(now_seconds), 2.2F);
        }

        const auto receipt_path = options.root / "user_data/studio/hot_reload_applied.udata";
        const auto receipt_temp = std::filesystem::path(receipt_path.string() + ".tmp");
        std::filesystem::create_directories(receipt_path.parent_path());
        {
            std::ofstream receipt(receipt_temp, std::ios::trunc);
            receipt << "@udata 1\n\n[receipt]\n"
                    << "schema_name: \"signalcloud.hot-reload-applied\";\n"
                    << "schema_major: 1;\n"
                    << "transaction_id: \"" << status.transaction_id() << "\";\n"
                    << "generated_unix: " << status.generated_unix() << ";\n"
                    << "applied: " << (applied ? "true" : "false") << ";\n"
                    << "scui_applied: " << (scui_applied ? "true" : "false") << ";\n"
                    << "light_applied: " << (light_applied ? "true" : "false") << ";\n"
                    << "light_runtime_signature: " << illuminosity_runtime.stats().deterministic_signature << ";\n"
                    << "light_point_budget_cost: " << illuminosity_runtime.stats().point_budget_cost << ";\n"
                    << "material_applied: " << (material_applied ? "true" : "false") << ";\n"
                    << "material_runtime_signature: \"" << material_runtime.stats().signature << "\";\n"
                    << "material_point_budget_cost: " << material_runtime.stats().selected_point_budget << ";\n"
                    << "audio_applied: " << (audio_applied ? "true" : "false") << ";\n"
                    << "audio_runtime_signature: \"" << audio_interference_runtime.stats().signature << "\";\n"
                    << "audio_point_budget_cost: " << audio_interference_runtime.stats().point_budget_cost << ";\n"
                    << "font_applied: " << (font_applied ? "true" : "false") << ";\n"
                    << "font_id: \"" << font_service.default_font_id() << "\";\n"
                    << "font_generation: " << font_service.generation(font_service.default_font_id()) << ";\n"
                    << "pcp3_applied_count: " << pcp3_applied << ";\n"
                    << "staged_changed_count: " << status.changed_count() << ";\n"
                    << "staged_pcp3_count: " << status.changed_pcp3_count() << ";\n"
                    << "staged_material_count: " << status.changed_material_count() << ";\n"
                    << "staged_audio_count: " << status.changed_audio_count() << ";\n"
                    << "staged_font_count: " << status.changed_font_count() << ";\n"
                    << "active_zone: \"" << current_zone << "\";\n"
                    << "error: \"" << apply_error << "\";\n";
        }
        std::error_code receipt_error;
        std::filesystem::remove(receipt_path, receipt_error);
        receipt_error.clear();
        std::filesystem::rename(receipt_temp, receipt_path, receipt_error);
        if (receipt_error) {
            std::cerr << "Protected preview receipt write failed: " << receipt_error.message() << '\n';
        }
        std::cout << "Protected preview reload: " << (applied ? "applied" : "no matching change")
                  << " | tx " << status.transaction_id()
                  << " | staged changes " << status.changed_count()
                  << " | SCUI " << (scui_applied ? 1 : 0)
                  << " | light " << (light_applied ? 1 : 0)
                  << " | material " << (material_applied ? 1 : 0)
                  << " | audio " << (audio_applied ? 1 : 0)
                  << " | font " << (font_applied ? 1 : 0)
                  << " | PCP3 " << pcp3_applied << '\n';
    };

    auto select_preset = [&](std::size_t index, std::string_view reason) {
        if (index >= signalcloud::render::kPointLabPresets.size()) return;
        if (point_lab.preset_index() == index) {
            append_benchmark(benchmark_path, previous, point_lab, fps, renderer.last_gpu_ms(),
                             renderer.allocated_bytes(), last_generation_ms, scanner, tactical, reason);
            return;
        }
        append_benchmark(benchmark_path, previous, point_lab, fps, renderer.last_gpu_ms(),
                         renderer.allocated_bytes(), last_generation_ms, scanner, tactical, "preset_exit");
        point_lab.select_preset(index);
        if (!load_selected_preset()) running = false;
        else residency.record_loaded(point_lab.preset().points);
    };

    while (running) {
        const double now = static_cast<double>(SDL_GetTicksNS()) / 1'000'000'000.0;
        const float dt = static_cast<float>(std::clamp(now - previous, 0.0, 0.1));
        previous = now;
        pulse = std::max(0.0F, pulse - dt * 2.4F);
        safe_lock_cooldown = std::max(0.0F, safe_lock_cooldown - dt);
        jump_pressed = false;
        quick_action_pressed = false;
        reload_pressed = false;
        use_item_pressed = false;
        bool interact_pressed = false;

        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_QUIT) running = false;
            if (event.type == SDL_EVENT_KEY_DOWN || event.type == SDL_EVENT_KEY_UP) {
                const bool down = event.type == SDL_EVENT_KEY_DOWN;
                if (event.key.scancode < SDL_SCANCODE_COUNT && (!native_scui_open() || !down)) {
                    keys[event.key.scancode] = down;
                }
                if (down && !event.key.repeat) {
                    if (event.key.scancode == SDL_SCANCODE_F10) running = false;
                    if (event.key.scancode == SDL_SCANCODE_F5 &&
                        (event.key.mod & SDL_KMOD_SHIFT) == 0) {
                        set_native_scui_open(active_scui_kind == NativeScuiKind::tupd_workbench
                            ? NativeScuiKind::none : NativeScuiKind::tupd_workbench);
                        continue;
                    }
                    if (event.key.scancode == SDL_SCANCODE_F6) {
                        set_native_scui_open(active_scui_kind == NativeScuiKind::panel_selector
                            ? NativeScuiKind::none : NativeScuiKind::panel_selector);
                        continue;
                    }
                    if (event.key.scancode == SDL_SCANCODE_F8) {
                        set_native_scui_open(active_scui_kind == NativeScuiKind::project_selector
                            ? NativeScuiKind::none : NativeScuiKind::project_selector);
                        continue;
                    }
                    if (event.key.scancode == SDL_SCANCODE_F7) {
                        set_native_scui_open(active_scui_kind == NativeScuiKind::light_lab
                            ? NativeScuiKind::none : NativeScuiKind::light_lab);
                        continue;
                    }
                    if (event.key.scancode == SDL_SCANCODE_F9) {
                        apply_staged_hot_reload(now);
                        continue;
                    }
                    if (native_scui_open()) {
                        auto& native_scui = *active_native_scui();
                        if (event.key.scancode == SDL_SCANCODE_ESCAPE || event.key.scancode == SDL_SCANCODE_K) {
                            set_native_scui_open(NativeScuiKind::none);
                        } else if (event.key.scancode == SDL_SCANCODE_UP) {
                            (void)native_scui.handle_key(signalcloud::ui::ScuiNativeKey::focus_previous);
                        } else if (event.key.scancode == SDL_SCANCODE_DOWN) {
                            (void)native_scui.handle_key(signalcloud::ui::ScuiNativeKey::focus_next);
                        } else if (event.key.scancode == SDL_SCANCODE_TAB) {
                            const bool shift = (event.key.mod & SDL_KMOD_SHIFT) != 0;
                            (void)native_scui.handle_key(shift
                                ? signalcloud::ui::ScuiNativeKey::focus_previous
                                : signalcloud::ui::ScuiNativeKey::focus_next);
                        } else if (event.key.scancode == SDL_SCANCODE_LEFT) {
                            (void)native_scui.handle_key(signalcloud::ui::ScuiNativeKey::adjust_previous);
                        } else if (event.key.scancode == SDL_SCANCODE_RIGHT) {
                            (void)native_scui.handle_key(signalcloud::ui::ScuiNativeKey::adjust_next);
                        } else if (event.key.scancode == SDL_SCANCODE_PAGEUP) {
                            (void)native_scui.handle_key(signalcloud::ui::ScuiNativeKey::page_previous);
                        } else if (event.key.scancode == SDL_SCANCODE_PAGEDOWN) {
                            (void)native_scui.handle_key(signalcloud::ui::ScuiNativeKey::page_next);
                        } else if (event.key.scancode == SDL_SCANCODE_RETURN ||
                                   event.key.scancode == SDL_SCANCODE_SPACE ||
                                   event.key.scancode == SDL_SCANCODE_J) {
                            (void)native_scui.handle_key(signalcloud::ui::ScuiNativeKey::confirm);
                        }
                        continue;
                    }
                    if (event.key.scancode == SDL_SCANCODE_F1) {
                        mouse_captured = !mouse_captured;
                        SDL_SetWindowRelativeMouseMode(window, mouse_captured);
                    }
                    if (event.key.scancode == SDL_SCANCODE_F2) raw_probe = !raw_probe;
                    if (event.key.scancode == SDL_SCANCODE_F3 && !economy.vending_menu_active()) tactical = !tactical;
                    if (event.key.scancode == SDL_SCANCODE_F4 && !economy.vending_menu_active()) lab_mode = !lab_mode;
                    if (event.key.scancode == SDL_SCANCODE_F12) detailed_title = !detailed_title;
                    if (economy.vending_menu_active()) {
                        if (event.key.scancode == SDL_SCANCODE_LEFT) economy.adjust_menu_product(-1);
                        if (event.key.scancode == SDL_SCANCODE_RIGHT) economy.adjust_menu_product(1);
                        if (event.key.scancode == SDL_SCANCODE_UP) economy.adjust_menu_quantity(1);
                        if (event.key.scancode == SDL_SCANCODE_DOWN) economy.adjust_menu_quantity(-1);
                        if (event.key.scancode == SDL_SCANCODE_J || event.key.scancode == SDL_SCANCODE_RETURN) {
                            interact_pressed = true;
                        }
                        if (event.key.scancode == SDL_SCANCODE_K || event.key.scancode == SDL_SCANCODE_ESCAPE) {
                            economy.close_vending_menu();
                            ar_interface.notify(signalcloud::ui::ArFeedbackKind::failure, 0);
                        }
                    }
                    if (event.key.scancode == SDL_SCANCODE_PAGEUP) {
                        const std::size_t next = (point_lab.preset_index() + 1U) % signalcloud::render::kPointLabPresets.size();
                        select_preset(next, "manual_next");
                    }
                    if (event.key.scancode == SDL_SCANCODE_PAGEDOWN) {
                        const std::size_t count = signalcloud::render::kPointLabPresets.size();
                        const std::size_t next = (point_lab.preset_index() + count - 1U) % count;
                        select_preset(next, "manual_previous");
                    }
                    if (event.key.scancode == SDL_SCANCODE_LEFTBRACKET) point_lab.adjust_point_scale(-0.10F);
                    if (event.key.scancode == SDL_SCANCODE_RIGHTBRACKET) point_lab.adjust_point_scale(0.10F);
                    if (event.key.scancode == SDL_SCANCODE_SEMICOLON) point_lab.adjust_density_scale(-0.10F);
                    if (event.key.scancode == SDL_SCANCODE_APOSTROPHE) point_lab.adjust_density_scale(0.10F);
                    if (event.key.scancode == SDL_SCANCODE_B) {
                        append_benchmark(benchmark_path, now, point_lab, fps, renderer.last_gpu_ms(),
                                         renderer.allocated_bytes(), last_generation_ms, scanner, tactical,
                                         "manual_snapshot");
                    }
                    if (event.key.scancode == SDL_SCANCODE_C) {
                        scanner = !scanner;
                        std::cout << (scanner
                            ? "Scanner active: extended view plus adjacent-room, hostile, exchange, and loot signatures\n"
                            : "Scanner inactive\n");
                    }
                    if (event.key.scancode == SDL_SCANCODE_I) {
                        signal_interference.cycle_mode();
                        std::cout << "Signal mode: " << signalcloud::render::signal_mode_name(signal_interference.mode()) << '\n';
                    }
                    if (event.key.scancode == SDL_SCANCODE_Y) {
                        signal_interference.trigger_siren();
                        std::cout << "Signal disruption: SIREN SCATTER\n";
                    }
                    if (event.key.scancode == SDL_SCANCODE_U) {
                        local_siren.toggle();
                        std::cout << "Moving range siren: " << (local_siren.active() ? "ON" : "OFF") << '\n';
                    }
                    if (event.key.scancode == SDL_SCANCODE_L) {
                        player.teleport(level.traversal_lab_spawn());
                        camera.set_position(player.position());
                        camera.set_yaw_degrees(-90.0F);
                        camera.set_pitch_degrees(0.0F);
                        portal_ready_time = now + 0.80;
                        current_zone = std::string(level.zone_name(player.position()));
                        tactical_map.observe_zone(level, current_zone);
                        append_traversal_log(traversal_log_path, now, player, current_zone, "LAB_TELEPORT");
                        std::cout << "Traversal & Water Lab quick access\n";
                    }
                    if (event.key.scancode == SDL_SCANCODE_F5 &&
                        (event.key.mod & SDL_KMOD_SHIFT) != 0) {
                        player.teleport(level.depth_lab_spawn());
                        camera.set_position(player.position());
                        camera.set_yaw_degrees(0.0F);
                        camera.set_pitch_degrees(0.0F);
                        portal_ready_time = now + 0.80;
                        current_zone = std::string(level.zone_name(player.position()));
                        tactical_map.observe_zone(level, current_zone);
                        append_depth_log(depth_log_path, now, "DEPTH_LAB_TELEPORT",
                                         current_zone, player, current_distance_limit);
                        std::cout << "Room Complex & Depth Lab quick access\n";
                    }
                    if (event.key.scancode == SDL_SCANCODE_H) {
                        player.teleport(level.threshold_lab_spawn());
                        camera.set_position(player.position());
                        camera.set_yaw_degrees(90.0F);
                        camera.set_pitch_degrees(0.0F);
                        portal_ready_time = now + 0.80;
                        current_zone = std::string(level.zone_name(player.position()));
                        tactical_map.observe_zone(level, current_zone);
                        append_depth_log(depth_log_path, now, "THRESHOLD_LAB_TELEPORT",
                                         current_zone, player, current_distance_limit);
                        std::cout << "Threshold Aperture & Material Lab quick access\n";
                    }
                    if (event.key.scancode == SDL_SCANCODE_M) {
                        player.teleport(level.submerged_lab_spawn());
                        camera.set_position(player.position());
                        camera.set_yaw_degrees(0.0F);
                        camera.set_pitch_degrees(-8.0F);
                        portal_ready_time = now + 0.80;
                        current_zone = std::string(level.zone_name(player.position()));
                        tactical_map.observe_zone(level, current_zone);
                        append_depth_log(depth_log_path, now, "SUBMERGED_LAB_TELEPORT",
                                         current_zone, player, current_distance_limit);
                        std::cout << "Submerged Boundary & Structural Envelope quick access\n";
                    }
                    if (event.key.scancode == SDL_SCANCODE_F) interact_pressed = true;
                    if (event.key.scancode == SDL_SCANCODE_K && !economy.vending_menu_active()) quick_action_pressed = true;
                    if (event.key.scancode == SDL_SCANCODE_R) reload_pressed = true;
                    if (event.key.scancode == SDL_SCANCODE_V) use_item_pressed = true;
                    if (event.key.scancode == SDL_SCANCODE_O) {
                        player.teleport(level.combat_lab_spawn());
                        camera.set_position(player.position());
                        camera.set_yaw_degrees(0.0F);
                        camera.set_pitch_degrees(0.0F);
                        portal_ready_time = now + 0.80;
                        current_zone = std::string(level.zone_name(player.position()));
                        tactical_map.observe_zone(level, current_zone);
                        std::cout << "Live-Fire Signal Range quick access\n";
                    }
                    if (event.key.scancode == SDL_SCANCODE_F6) {
                        player.teleport(level.economy_lab_spawn());
                        camera.set_position(player.position());
                        camera.set_yaw_degrees(0.0F);
                        camera.set_pitch_degrees(0.0F);
                        portal_ready_time = now + 0.80;
                        current_zone = std::string(level.zone_name(player.position()));
                        tactical_map.observe_zone(level, current_zone);
                        std::cout << "Scavenger Exchange quick access\n";
                    }
                    if (event.key.scancode == SDL_SCANCODE_P) {
                        combat.reset_wave();
                        std::cout << "Combat wave reset\n";
                    }
                    if (event.key.scancode == SDL_SCANCODE_SPACE) jump_pressed = true;
                    if (event.key.scancode == SDL_SCANCODE_F11) {
                        player.reset(level.spawn_position());
                        combat.reset();
                        economy.reset();
                        threat_director.reset(level);
                        recovery.reset();
                        residency.reset(point_lab.preset().points);
                        camera.set_position(player.position());
                        last_water_entry_serial = player.water_entry_serial();
                        last_save_jump_count = player.save_jump_count();
                        last_tech_pickup_count = player.tech_pickup_count();
                        last_rescue_count = player.rescue_count();
                    }
                    if (event.key.scancode == SDL_SCANCODE_N) {
                        ++tape_index;
                        level_seed = signalcloud::world::mix_seed(0xA12D0A1ULL,
                            {static_cast<int>(tape_index), 0, 0}, 4);
                        level = signalcloud::world::LiminalLevel::make_pivot11_scavenging(level_seed);
                        write_layout_report(options.root / "reports/pivot13_layout.txt", level);
                        if (!load_selected_preset()) running = false;
                        player.reset(level.spawn_position());
                        combat.reset();
                        economy.reset();
                        threat_director.reset(level);
                        recovery.reset();
                        residency.reset(point_lab.preset().points);
                        camera.set_position(player.position());
                        last_water_entry_serial = player.water_entry_serial();
                        last_save_jump_count = player.save_jump_count();
                        last_tech_pickup_count = player.tech_pickup_count();
                        last_rescue_count = player.rescue_count();
                        camera.set_yaw_degrees(-90.0F);
                        camera.set_pitch_degrees(0.0F);
                        portal_ready_time = now + 0.75;
                        current_zone = std::string(level.zone_name(player.position()));
                        tactical_map.reset(level, current_zone);
                        append_zone_log(options.root / "reports/zone_trace.log", now, current_zone, player.position());
                        std::cout << "Generated tape layout " << tape_index
                                  << " | seed " << signalcloud::world::seed_hex(level_seed)
                                  << " | signature " << signalcloud::world::seed_hex(level.layout_signature()) << '\n';
                    }
                    if (event.key.scancode == SDL_SCANCODE_ESCAPE && mouse_captured &&
                        !economy.vending_menu_active()) {
                        mouse_captured = false;
                        SDL_SetWindowRelativeMouseMode(window, false);
                    }
                }
            }
            if (event.type == SDL_EVENT_MOUSE_MOTION && native_scui_open()) {
                auto& native_scui = *active_native_scui();
                int window_width = 1;
                int window_height = 1;
                SDL_GetWindowSize(window, &window_width, &window_height);
                const float nx = std::clamp(event.motion.x / static_cast<float>(std::max(1, window_width)), 0.0F, 1.0F);
                const float ny = std::clamp(event.motion.y / static_cast<float>(std::max(1, window_height)), 0.0F, 1.0F);
                (void)native_scui.handle_pointer_move(nx, ny);
                continue;
            }
            if (event.type == SDL_EVENT_MOUSE_MOTION && mouse_captured && !tactical) {
                if (economy.vending_menu_active()) {
                    economy.move_menu_cursor(event.motion.xrel * 0.0018F,
                                             -event.motion.yrel * 0.0018F);
                } else {
                    camera.apply_mouse_delta(event.motion.xrel, event.motion.yrel);
                }
            }
            if (event.type == SDL_EVENT_MOUSE_BUTTON_DOWN || event.type == SDL_EVENT_MOUSE_BUTTON_UP) {
                const bool down = event.type == SDL_EVENT_MOUSE_BUTTON_DOWN;
                if (native_scui_open()) {
                    auto& native_scui = *active_native_scui();
                    if (down && event.button.button == SDL_BUTTON_LEFT) {
                        int window_width = 1;
                        int window_height = 1;
                        SDL_GetWindowSize(window, &window_width, &window_height);
                        const float nx = std::clamp(event.button.x / static_cast<float>(std::max(1, window_width)), 0.0F, 1.0F);
                        const float ny = std::clamp(event.button.y / static_cast<float>(std::max(1, window_height)), 0.0F, 1.0F);
                        (void)native_scui.handle_pointer_activate(nx, ny);
                    }
                    if (down && event.button.button == SDL_BUTTON_RIGHT) set_native_scui_open(NativeScuiKind::none);
                    continue;
                }
                if (!mouse_captured && down && event.button.button == SDL_BUTTON_LEFT) {
                    mouse_captured = true;
                    SDL_SetWindowRelativeMouseMode(window, true);
                }
                if (economy.vending_menu_active()) {
                    if (down && event.button.button == SDL_BUTTON_LEFT) interact_pressed = true;
                    if (down && event.button.button == SDL_BUTTON_RIGHT) {
                        economy.close_vending_menu();
                        ar_interface.notify(signalcloud::ui::ArFeedbackKind::failure, 0);
                    }
                    primary_held = false;
                } else {
                    if (event.button.button == SDL_BUTTON_LEFT) {
                        primary_held = down && mouse_captured;
                    }
                    if (down && event.button.button == SDL_BUTTON_RIGHT) quick_action_pressed = true;
                }
                if (raw_probe) append_button_log(options.root / "reports/input_probe.log", now,
                                                 event.button.button, down, event.button.clicks);
            }
            if (event.type == SDL_EVENT_MOUSE_WHEEL) {
                float y = event.wheel.y;
                if (event.wheel.direction == SDL_MOUSEWHEEL_FLIPPED) y = -y;
                if (native_scui_open()) {
                    auto& native_scui = *active_native_scui();
                    (void)native_scui.handle_wheel(y);
                    continue;
                }
                if (economy.vending_menu_active()) {
                    if (y > 0.0F) economy.adjust_menu_quantity(1);
                    if (y < 0.0F) economy.adjust_menu_quantity(-1);
                } else {
                    if (y > 0.0F) weapon_slot = weapon_slot % 2 + 1;
                    if (y < 0.0F) belt_slot = belt_slot % 6 + 1;
                }
            }
        }

        if (auto* native_scui = active_native_scui(); native_scui != nullptr) {
            for (const auto& scui_event : native_scui->take_events()) {
                if (scui_event.command_id == "authoring.panel.refresh") {
                    auto refreshed = signalcloud::ui::ScuiPanelRegistry::load(options.root, scui_registry_path);
                    if (refreshed.valid()) {
                        scui_registry = std::move(refreshed);
                        (void)panel_selector_scui.set_choices(
                            "panel", scui_registry.keys(), panel_selector_scui.string("panel_key"));
                        (void)panel_selector_scui.set_number(
                            "registry_count", static_cast<double>(scui_registry.entries().size()));
                        panel_selector_scui.show_notice(
                            signalcloud::ui::ScuiNativeNoticeKind::success,
                            "REGISTRY RELOADED", static_cast<float>(now));
                    } else {
                        panel_selector_scui.show_notice(
                            signalcloud::ui::ScuiNativeNoticeKind::failure,
                            "REGISTRY FAILED", static_cast<float>(now), 2.4F);
                    }
                }
                if (scui_event.command_id == "authoring.panel.select" ||
                    scui_event.command_id == "authoring.panel.open") {
                    const std::string key = panel_selector_scui.string("panel_key").value_or("");
                    if (key == "project-selector") {
                        set_native_scui_open(NativeScuiKind::project_selector);
                        project_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::success,
                                                 "PROJECT PANEL READY", static_cast<float>(now));
                    } else if (key == "light-lab") {
                        set_native_scui_open(NativeScuiKind::light_lab);
                        if (active_scui_kind == NativeScuiKind::light_lab) {
                            light_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::success,
                                                   "LIGHT PREVIEW READY", static_cast<float>(now));
                        }
                    } else if (key == "tupd-workbench") {
                        set_native_scui_open(NativeScuiKind::tupd_workbench);
                        if (active_scui_kind == NativeScuiKind::tupd_workbench) {
                            tupd_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::success,
                                                  "TUPD SANDBOX READY", static_cast<float>(now));
                        }
                    } else {
                        panel_selector_scui.show_notice(
                            signalcloud::ui::ScuiNativeNoticeKind::warning,
                            "PANEL NOT AVAILABLE", static_cast<float>(now), 2.2F);
                    }
                }
                if (scui_event.command_id == "authoring.profile.refresh") {
                    const double current = native_scui->number("profile_progress").value_or(72.0);
                    (void)native_scui->set_number("profile_progress", std::min(100.0, current + 7.0));
                    native_scui->show_notice(signalcloud::ui::ScuiNativeNoticeKind::success,
                                             "PROFILE REFRESHED", static_cast<float>(now));
                }
                if (scui_event.command_id == "light.time_of_day.set") {
                    illuminosity_runtime.set_time_of_day(static_cast<float>(
                        light_scui.number("time_of_day").value_or(0.35)));
                }
                if (scui_event.command_id == "light.timeline.play") {
                    illuminosity_runtime.play_day_night();
                    light_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::success,
                                           "TIMELINE PLAYING", static_cast<float>(now), 2.0F);
                }
                if (scui_event.command_id == "light.timeline.pause") {
                    illuminosity_runtime.pause_day_night(true);
                    light_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::info,
                                           "TIMELINE PAUSED", static_cast<float>(now), 2.0F);
                }
                if (scui_event.command_id == "light.timeline.stop") {
                    illuminosity_runtime.stop_day_night(0.35F);
                    (void)light_scui.set_number("time_of_day", 0.35);
                    light_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::success,
                                           "TIMELINE STOPPED", static_cast<float>(now), 2.0F);
                }
                if (scui_event.command_id == "light.probe.sample") {
                    const auto probe = illuminosity_runtime.probe_surface(player.position(), current_zone);
                    std::ostringstream notice;
                    notice << probe.quality_band << ' ' << std::fixed << std::setprecision(0)
                           << probe.effective_illuminosity_percent << " I%";
                    light_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::success,
                                           notice.str(), static_cast<float>(now), 2.6F);
                    std::cout << "Illuminosity surface probe: zone " << current_zone
                              << " | quality " << probe.quality_band
                              << " | I " << probe.effective_illuminosity_percent
                              << " | visibility " << probe.visibility
                              << " | contributors " << probe.contributing_lights << '\n';
                }
                if (scui_event.command_id == "light.diagnostics.bake") {
                    signalcloud::lighting::IlluminosityBakeRequest request;
                    request.center = player.position();
                    request.zone = current_zone;
                    request.grid_size = 7U;
                    request.spacing = 1.25F;
                    const auto summary = signalcloud::lighting::bake_illuminosity_grid(
                        illuminosity_runtime, request);
                    std::string bake_error;
                    const auto bake_path = options.root / "user_data/studio/illuminosity_bake_latest.json";
                    if (signalcloud::lighting::write_illuminosity_bake_report(
                            options.root, bake_path, illuminosity_runtime, summary, &bake_error)) {
                        light_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::success,
                                               "DIAGNOSTICS BAKED", static_cast<float>(now), 2.4F);
                        std::cout << "Illuminosity diagnostic bake: " << summary.samples.size()
                                  << " samples | avg " << summary.average_illuminosity_percent
                                  << " | signature " << summary.deterministic_signature
                                  << " | " << bake_path << '\n';
                    } else {
                        light_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::failure,
                                               "BAKE FAILED", static_cast<float>(now), 2.8F);
                        std::cerr << "Illuminosity diagnostic bake failed: " << bake_error << '\n';
                    }
                }
                if (scui_event.command_id == "light.document.save") {
                    std::string save_error;
                    if (light_scui_store.save(light_scui, &save_error)) {
                        std::cout << "Light Lab native overlay saved: " << light_scui_store.path() << '\n';
                        light_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::success,
                                               "LIGHT SAVED", static_cast<float>(now), 2.0F);
                    } else {
                        std::cerr << "Light Lab native overlay save failed: " << save_error << '\n';
                        light_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::failure,
                                               "SAVE FAILED", static_cast<float>(now), 2.8F);
                    }
                }
                if (scui_event.command_id == "light.document.reload") {
                    std::string reload_error;
                    if (!light_scui_store.load(light_scui, &reload_error)) {
                        std::cerr << "Light Lab native overlay reload failed: " << reload_error << '\n';
                        light_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::failure,
                                               "RELOAD FAILED", static_cast<float>(now), 2.8F);
                    } else {
                        light_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::success,
                                               "LIGHT RELOADED", static_cast<float>(now), 1.8F);
                    }
                }
                if (scui_event.command_id == "tupd.recipe.select") {
                    const std::string key = tupd_scui.string("recipe_key").value_or("");
                    const auto found = std::find(tupd_recipe_keys.begin(), tupd_recipe_keys.end(), key);
                    if (found != tupd_recipe_keys.end()) {
                        tupd_recipe_index = static_cast<std::size_t>(
                            std::distance(tupd_recipe_keys.begin(), found));
                        tupd_sandbox.reset();
                        tupd_test_action_index = 0U;
                        tupd_preview = tupd_sandbox.preview(tupd_recipes[tupd_recipe_index]);
                        sync_tupd_scui();
                        tupd_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::success,
                                              "RECIPE PREVIEWED", static_cast<float>(now));
                    }
                }
                if (scui_event.command_id == "tupd.test-action.select") {
                    const std::string key = tupd_scui.string("test_action_key").value_or("");
                    const auto& actions = tupd_recipes[tupd_recipe_index].test_actions;
                    const auto found = std::find(actions.begin(), actions.end(), key);
                    if (found != actions.end()) {
                        tupd_test_action_index = static_cast<std::size_t>(std::distance(actions.begin(), found));
                        sync_tupd_scui();
                        tupd_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::success,
                                              "TEST ACTION SELECTED", static_cast<float>(now));
                    }
                }
                if (scui_event.command_id == "tupd.preview") {
                    tupd_preview = tupd_sandbox.preview(tupd_recipes[tupd_recipe_index]);
                    sync_tupd_scui();
                    tupd_scui.show_notice(
                        tupd_preview.valid ? signalcloud::ui::ScuiNativeNoticeKind::success
                                           : signalcloud::ui::ScuiNativeNoticeKind::failure,
                        tupd_preview.valid ? "PREVIEW VALID" : "PREVIEW BLOCKED",
                        static_cast<float>(now), 2.4F);
                }
                // A8a1 compatibility wording retained for regression: SANDBOX COMMITTED.
                // A8a2 reports the more precise RESULT CREATED / NOT EQUIPPED state.
                if (scui_event.command_id == "tupd.commit") {
                    const auto receipt = tupd_sandbox.commit(tupd_recipes[tupd_recipe_index]);
                    tupd_preview = tupd_sandbox.last_preview();
                    sync_tupd_scui();
                    std::string receipt_error;
                    (void)signalcloud::items::write_tupd_receipt_atomic(
                        options.root / "user_data/studio/tupd_sandbox_receipt_latest.json",
                        receipt, &receipt_error);
                    const bool normal_save_unchanged = tupd_sandbox.normal_save_unchanged();
                    tupd_scui.show_notice(
                        receipt.committed && normal_save_unchanged
                            ? signalcloud::ui::ScuiNativeNoticeKind::success
                            : signalcloud::ui::ScuiNativeNoticeKind::failure,
                        receipt.committed && normal_save_unchanged
                            ? "RESULT CREATED / NOT EQUIPPED" : "COMMIT REJECTED",
                        static_cast<float>(now), 2.8F);
                    if (tupd_sandbox.result_instance()) {
                        (void)signalcloud::items::save_tupd_instance_atomic(
                            options.root / "user_data/studio/tupd_sandbox_instance_latest.tupdinstance",
                            *tupd_sandbox.result_instance(), &receipt_error);
                    }
                }
                if (scui_event.command_id == "tupd.instance.equip") {
                    const bool applied = tupd_sandbox.equip_or_spawn_result();
                    sync_tupd_scui();
                    std::string save_error;
                    if (tupd_sandbox.result_instance()) {
                        (void)signalcloud::items::save_tupd_instance_atomic(
                            options.root / "user_data/studio/tupd_sandbox_instance_latest.tupdinstance",
                            *tupd_sandbox.result_instance(), &save_error);
                    }
                    tupd_scui.show_notice(
                        applied ? signalcloud::ui::ScuiNativeNoticeKind::success : signalcloud::ui::ScuiNativeNoticeKind::failure,
                        applied && tupd_sandbox.result_instance()
                            ? signalcloud::items::tupd_instance_state(*tupd_sandbox.result_instance())
                            : "COMMIT A RESULT FIRST",
                        static_cast<float>(now), 2.4F);
                }
                if (scui_event.command_id == "tupd.instance.test") {
                    const auto& actions = tupd_recipes[tupd_recipe_index].test_actions;
                    const auto action = actions.empty()
                        ? signalcloud::items::TupdTestAction::unknown
                        : signalcloud::items::parse_tupd_test_action(actions[tupd_test_action_index % actions.size()]);
                    const auto test = tupd_sandbox.test_result(action);
                    sync_tupd_scui();
                    std::string save_error;
                    if (tupd_sandbox.result_instance()) {
                        (void)signalcloud::items::save_tupd_instance_atomic(
                            options.root / "user_data/studio/tupd_sandbox_instance_latest.tupdinstance",
                            *tupd_sandbox.result_instance(), &save_error);
                    }
                    tupd_scui.show_notice(
                        test.accepted ? signalcloud::ui::ScuiNativeNoticeKind::success : signalcloud::ui::ScuiNativeNoticeKind::failure,
                        test.outcome, static_cast<float>(now), 2.8F);
                }
                if (scui_event.command_id == "tupd.ghost.view") {
                    const std::string view = tupd_scui.string("ghost_view_key").value_or("RESULT");
                    tupd_ghost_inspection_mode = signalcloud::ui::parse_tupd_ghost_inspection_mode(view);
                    sync_tupd_scui();
                    tupd_scui.show_notice(
                        signalcloud::ui::ScuiNativeNoticeKind::success,
                        std::string("GHOST VIEW ") + std::string(signalcloud::ui::tupd_ghost_inspection_name(tupd_ghost_inspection_mode)),
                        static_cast<float>(now), 2.0F);
                }
                if (scui_event.command_id == "tupd.ghost.toggle") {
                    tupd_ghost_exploded = !tupd_ghost_exploded;
                    sync_tupd_scui();
                    tupd_scui.show_notice(
                        signalcloud::ui::ScuiNativeNoticeKind::success,
                        tupd_ghost_exploded ? "GHOST EXPLODED" : "GHOST ASSEMBLED",
                        static_cast<float>(now), 2.0F);
                }
                if (scui_event.command_id == "tupd.instance.clear") {
                    tupd_sandbox.clear_result();
                    sync_tupd_scui();
                    tupd_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::success,
                                          "RESULT CLEARED", static_cast<float>(now));
                }
                if (scui_event.command_id == "tupd.reset") {
                    tupd_sandbox.reset();
                    tupd_preview = tupd_sandbox.preview(tupd_recipes[tupd_recipe_index]);
                    sync_tupd_scui();
                    tupd_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::success,
                                          "TEST INVENTORY RESET", static_cast<float>(now));
                }
                if (scui_event.command_id == "tupd.reload") {
                    if (reload_tupd_catalog()) {
                        sync_tupd_scui();
                        tupd_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::success,
                                              "RECIPE CATALOG RELOADED", static_cast<float>(now));
                    } else {
                        tupd_scui.show_notice(signalcloud::ui::ScuiNativeNoticeKind::failure,
                                              "NO VALID RECIPE", static_cast<float>(now), 2.6F);
                    }
                }
                if (scui_event.command_id == "tupd.export") {
                    const auto& recipe = tupd_recipes[tupd_recipe_index];
                    std::string slug;
                    for (const char c : recipe.recipe_id) {
                        const unsigned char byte = static_cast<unsigned char>(c);
                        slug.push_back(std::isalnum(byte) ? static_cast<char>(std::tolower(byte)) : '_');
                    }
                    while (!slug.empty() && slug.back() == '_') slug.pop_back();
                    if (slug.empty()) slug = "tupd_recipe";
                    const auto folder = options.root / "content/user/tupd" / ("ingame_" + slug);
                    const auto recipe_path = folder / ("ingame_" + slug + ".tupd");
                    std::string export_error;
                    bool exported = signalcloud::items::save_tupd_recipe_atomic(recipe_path, recipe, &export_error);
                    if (exported) {
                        std::filesystem::create_directories(folder);
                        const auto envelope_path = std::filesystem::path(recipe_path.string() + ".asset.udata");
                        std::ofstream envelope(envelope_path, std::ios::trunc);
                        envelope << "@udata 1\n\n[asset]\n"
                                 << "asset_id: \"user.tupd.ingame_" << slug << "\";\n"
                                 << "asset_type: \"tupd_recipe\";\n"
                                 << "family: \"items\";\n"
                                 << "pack: \"user\";\n"
                                 << "license_id: \"LicenseRef-User-Authored\";\n"
                                 << "dependencies: [];\n"
                                 << "hot_reload: \"disabled\";\n"
                                 << "data_only: true;\n"
                                 << "source_path: \"" << recipe_path.lexically_relative(options.root / "content").generic_string() << "\";\n";
                        exported = static_cast<bool>(envelope);
                        if (exported && tupd_sandbox.result_instance()) {
                            const auto instance_path = folder / ("ingame_" + slug + ".tupdinstance");
                            exported = signalcloud::items::save_tupd_instance_atomic(
                                instance_path, *tupd_sandbox.result_instance(), &export_error);
                            if (exported) {
                                std::ofstream instance_envelope(instance_path.string() + ".asset.udata", std::ios::trunc);
                                instance_envelope << "@udata 1\n\n[asset]\n"
                                                  << "asset_id: \"user.tupd.ingame_" << slug << ".instance\";\n"
                                                  << "asset_type: \"tupd_instance\";\n"
                                                  << "family: \"items\";\n"
                                                  << "pack: \"user\";\n"
                                                  << "license_id: \"LicenseRef-User-Authored\";\n"
                                                  << "dependencies: [\"user.tupd.ingame_" << slug << "\"];\n"
                                                  << "hot_reload: \"authoring-only\";\n"
                                                  << "data_only: true;\n"
                                                  << "source_path: \"" << instance_path.lexically_relative(options.root / "content").generic_string() << "\";\n";
                                exported = static_cast<bool>(instance_envelope);
                            }
                        }
                    }
                    tupd_scui.show_notice(
                        exported ? signalcloud::ui::ScuiNativeNoticeKind::success
                                 : signalcloud::ui::ScuiNativeNoticeKind::failure,
                        exported ? (tupd_sandbox.result_instance() ? "RECIPE + RESULT EXPORTED" : "MANAGED RECIPE EXPORTED") : "EXPORT FAILED",
                        static_cast<float>(now), 2.8F);
                    if (!exported && !export_error.empty()) std::cerr << "Tupd export failed: " << export_error << '\n';
                }
                std::cout << "SCUI native command: " << scui_event.command_id
                          << " control=" << scui_event.control_id
                          << " payload=" << scui_event.payload_json
                          << " tx=" << scui_event.transaction_id << '\n';
            }
        }

        if (!tactical) {
            signalcloud::world::PlayerMoveInput movement;
            movement.forward = (keys[SDL_SCANCODE_W] ? 1.0F : 0.0F) - (keys[SDL_SCANCODE_S] ? 1.0F : 0.0F);
            movement.right = (keys[SDL_SCANCODE_D] ? 1.0F : 0.0F) - (keys[SDL_SCANCODE_A] ? 1.0F : 0.0F);
            movement.sprint = keys[SDL_SCANCODE_LSHIFT];
            movement.jump_pressed = jump_pressed;
            movement.descend = keys[SDL_SCANCODE_LCTRL];
            movement.interact_pressed = interact_pressed;
            movement.quick_action_pressed = quick_action_pressed;
            movement.speed_scale = economy.movement_scale();
            if (economy.vending_menu_active() || recovery.controls_locked() || native_scui_open()) {
                movement.forward = 0.0F;
                movement.right = 0.0F;
                movement.sprint = false;
                movement.jump_pressed = false;
                movement.descend = false;
                movement.interact_pressed = false;
                movement.quick_action_pressed = false;
            }
            movement_amount = std::clamp(std::sqrt(movement.forward * movement.forward +
                                                   movement.right * movement.right), 0.0F, 1.0F);
            player_sprinting = movement.sprint && movement_amount > 0.05F;
            player.update(movement, camera.forward(), dt, level);
            camera.set_position(player.position());

            if (player.save_jump_count() != last_save_jump_count) {
                last_save_jump_count = player.save_jump_count();
                append_depth_log(depth_log_path, now, "SAVE_JUMP", current_zone,
                                 player, current_distance_limit);
                std::cout << "SAVE JUMP: coyote-window forward recovery\n";
            }
            if (player.water_entry_serial() != last_water_entry_serial) {
                last_water_entry_serial = player.water_entry_serial();
                water_disturbance.trigger(player.last_water_entry_position(),
                                          player.last_water_entry_strength(),
                                          player.last_water_entry_was_bomb());
                splash_audio.play(player.last_water_entry_strength(),
                                  player.last_water_entry_was_bomb());
                sound_ripple.trigger(player.last_water_entry_position(),
                                     player.last_water_entry_was_bomb() ? 1.0F : 0.52F,
                                     player.last_water_entry_was_bomb() ? 1.15F : 0.72F);
                combat.emit_noise(player.last_water_entry_position(),
                                  player.last_water_entry_was_bomb() ? 1.15F : 0.55F,
                                  current_zone);
                append_depth_log(depth_log_path, now,
                                 player.last_water_entry_was_bomb() ? "BOMB_SPLASH" : "SPLASH",
                                 current_zone, player, current_distance_limit);
                std::cout << (player.last_water_entry_was_bomb()
                                  ? "WATER BOMB: loud splash event (AI-audible hook)\n"
                                  : "Water splash event\n");
            }
            if (player.tech_pickup_count() != last_tech_pickup_count) {
                last_tech_pickup_count = player.tech_pickup_count();
                append_depth_log(depth_log_path, now, "ALMOND_DEPTH_TECH",
                                 current_zone, player, current_distance_limit);
                std::cout << "Almo-Lung & Pressure Cuff equipped\n";
            }
            if (player.rescue_count() != last_rescue_count) {
                last_rescue_count = player.rescue_count();
                camera.set_position(player.position());
                append_depth_log(depth_log_path, now, "DEPTH_RESCUE",
                                 current_zone, player, current_distance_limit);
                std::cout << "Depth lab rescue: oxygen/pressure failure\n";
            }
        }

        if (!tactical && now >= portal_ready_time) {
            bool custom_portal_used = false;
            if (const auto transfer = signalcloud::pcp3::world_portal_transfer(
                    pcp3_assets, current_zone, signalcloud::pcp3::PreviewPurpose::game,
                    player.position(), interact_pressed)) {
                const auto from = player.position();
                player.teleport(transfer->destination);
                camera.set_position(player.position());
                camera.set_yaw_degrees(transfer->destination_yaw_degrees);
                camera.set_pitch_degrees(0.0F);
                portal_ready_time = now + transfer->cooldown_seconds;
                custom_portal_used = true;
                std::ofstream log(options.root / "reports/pcp3_world_portal_trace.log", std::ios::app);
                log << now << " source_asset=\"" << transfer->source_asset_id
                    << "\" source_portal=\"" << transfer->source_portal_id
                    << "\" destination_asset=\"" << transfer->destination_asset_id
                    << "\" destination_portal=\"" << transfer->destination_portal_id
                    << "\" destination_zone=\"" << transfer->destination_zone
                    << "\" from=" << from.x << ',' << from.y << ',' << from.z
                    << " to=" << player.position().x << ',' << player.position().y << ',' << player.position().z << '\n';
                std::cout << "PCP3 portal " << transfer->source_asset_id << '/' << transfer->source_portal_id
                          << " -> " << transfer->destination_asset_id << '/' << transfer->destination_portal_id
                          << " [" << transfer->destination_zone << "]\n";
            }
            if (!custom_portal_used) {
                if (const auto* portal = level.portal_at(player.position())) {
                    const auto from = player.position();
                    player.teleport(portal->destination);
                    camera.set_position(player.position());
                    camera.set_yaw_degrees(portal->destination_yaw_degrees);
                    camera.set_pitch_degrees(0.0F);
                    portal_ready_time = now + 0.80;
                    append_portal_log(options.root / "reports/portal_trace.log", now, *portal, from, player.position());
                    std::cout << "Portal " << portal->id << " [" << signalcloud::world::portal_kind_name(portal->kind)
                              << "]: " << portal->source_zone << " -> " << portal->destination_zone << '\n';
                }
            }
        }

        const std::string next_zone(level.zone_name(player.position()));
        if (next_zone != current_zone) {
            current_zone = next_zone;
            tactical_map.observe_zone(level, current_zone);
            append_zone_log(options.root / "reports/zone_trace.log", now, current_zone, player.position());
            std::cout << "Entered zone: " << current_zone << '\n';
        }

        if (scanner) tactical_map.observe_scan(level, current_zone);

        if (!recovery.controls_locked()) {
            const auto threat_event = threat_director.update(
                dt, level, combat, player.position(), current_zone, scanner);
            if (!threat_event.message.empty()) {
                std::cout << "Threat director: " << threat_event.message << '\n';
            }
        }

        if (!tactical) {
            if (reload_pressed) {
                combat.reload();
                append_combat_log(combat_log_path, now, "RELOAD", current_zone,
                                  weapon_slot, combat, player);
            }
            const bool attack_requested = !economy.vending_menu_active() &&
                                          !recovery.controls_locked() &&
                                          (primary_held || keys[SDL_SCANCODE_J]);
            if (attack_requested) {
                if (is_safe_room(current_zone)) {
                    if (safe_lock_cooldown <= 0.0F) {
                        safe_lock_cooldown = 0.55F;
                        ar_interface.notify(signalcloud::ui::ArFeedbackKind::safe_lock, 0);
                        std::cout << "Weapon safety lock active in " << current_zone << '\n';
                    }
                } else {
                    const auto shot = combat.fire_primary(camera.position(), camera.forward(),
                                                          weapon_slot, scanner, current_zone);
                    if (shot.fired) {
                        pulse = 0.34F;
                        sound_ripple.trigger(player.position(),
                                             weapon_slot == 1 ? 0.92F : 0.42F,
                                             weapon_slot == 1 ? 1.0F : 0.56F);
                        append_combat_log(combat_log_path, now,
                                          shot.hit ? (shot.killed ? "KILL" : "HIT") :
                                          (shot.dry_fire ? "DRY" : "MISS"),
                                          current_zone, weapon_slot, combat, player, &shot);
                        std::cout << shot.message << '\n';
                    }
                }
            }
            if (!recovery.controls_locked() && interact_pressed && !is_safe_room(current_zone) &&
                combat.claim_near(player.position(), current_zone)) {
                economy.add_claimed_proof();
                ar_interface.notify(signalcloud::ui::ArFeedbackKind::pickup, 1);
                append_combat_log(combat_log_path, now, "PROOF_CLAIM", current_zone,
                                  weapon_slot, combat, player);
                std::cout << "Death proof secured for the Scavenger Exchange\n";
            }

            if (!recovery.controls_locked() && interact_pressed && current_zone == "Scavenger Exchange") {
                const auto event_result = economy.interact(player.position(), current_zone, belt_slot);
                if (event_result.handled) {
                    if (event_result.ammo_added > 0) combat.add_reserve_ammo(event_result.ammo_added);
                    std::cout << event_result.message << '\n';
                    const int feedback_value = event_result.xar_delta != 0
                        ? static_cast<int>(std::abs(event_result.xar_delta))
                        : static_cast<int>(event_result.quantity);
                    ar_interface.notify(feedback_for_economy_event(event_result), feedback_value);
                    pulse = event_result.success ? 0.28F : 0.10F;
                    append_economy_log(economy_log_path, now,
                                       event_result.success ? "INTERACT_OK" : "INTERACT_NO",
                                       current_zone, economy, event_result.message);
                }
            }
            if (!recovery.controls_locked() && use_item_pressed) {
                const auto event_result = economy.use_belt_item(belt_slot);
                if (event_result.ammo_added > 0) combat.add_reserve_ammo(event_result.ammo_added);
                if (event_result.health_restored > 0.0F) player.restore_health(event_result.health_restored);
                if (event_result.oxygen_restored > 0.0F) player.restore_oxygen(event_result.oxygen_restored);
                std::cout << event_result.message << '\n';
                ar_interface.notify(feedback_for_economy_event(event_result),
                                    static_cast<int>(event_result.quantity));
                append_economy_log(economy_log_path, now,
                                   event_result.success ? "USE_OK" : "USE_NO",
                                   current_zone, economy, event_result.message);
            }

            signalcloud::combat::CombatUpdate combat_update;
            if (!recovery.controls_locked()) {
                combat_update = combat.update(dt, player.position(), current_zone, &level);
                if (combat_update.player_damage > 0.0F) {
                    const float before = player.health();
                    player.apply_damage(combat_update.player_damage, signalcloud::world::DamageCause::combat);
                    if (player.health() < before) {
                        append_combat_log(combat_log_path, now, "PLAYER_HIT", current_zone,
                                          weapon_slot, combat, player);
                        sound_ripple.trigger(player.position(), 0.48F, 0.72F);
                    }
                }
            } else {
                combat.update_timers(dt);
            }

            hash_dog_bark_cooldown = std::max(0.0F, hash_dog_bark_cooldown - dt);
            if (hash_dog_bark_cooldown <= 0.0F && !is_safe_room(current_zone)) {
                for (const auto& entity : combat.entities()) {
                    if (!entity.alive || entity.kind != signalcloud::combat::CreatureKind::hash_dog ||
                        entity.zone != current_zone ||
                        (entity.state != signalcloud::combat::CreatureState::hunt &&
                         entity.state != signalcloud::combat::CreatureState::attack &&
                         entity.state != signalcloud::combat::CreatureState::investigate)) {
                        continue;
                    }
                    // A5a1 compatibility proof: the shipped Hash Dog profile defaults to
                    // signalcloud::render::FrequencyBand::low, while A5a3 keeps the band authored.
                    const auto& bark_profile = audio_interference_runtime.hash_dog_bark();
                    const std::uint32_t bark_seed = static_cast<std::uint32_t>(entity.id) ^
                        (hash_dog_bark_events + 1U) * 0x9E3779B9U ^ bark_profile.seed_salt;
                    sound_ripple.trigger_event(entity.position, bark_profile.strength, bark_profile.frequency_band,
                        bark_profile.obstruction_path, bark_seed, bark_profile.duration_seconds,
                        bark_profile.radius_scale, bark_profile.wave_count,
                        bark_profile.wave_sharpness, bark_profile.displacement_scale,
                        bark_profile.color_mix, bark_profile.visibility_floor);
                    combat.emit_noise(entity.position, bark_profile.hearing_loudness, current_zone);
                    ++hash_dog_bark_events;
                    hash_dog_bark_cooldown = bark_profile.cooldown_seconds;
                    std::cout << "Hash Dog bark: bounded low-band signal ripple | authored "
                              << signalcloud::render::frequency_band_name(bark_profile.frequency_band)
                              << " band | waves " << bark_profile.wave_count
                              << " | AI hearing event " << hash_dog_bark_events
                              << " | seed " << bark_seed << '\n';
                    break;
                }
            }

            const std::string death_zone_before_recovery = current_zone;
            const auto recovery_event = recovery.update(
                dt, player, level, economy, combat, current_zone);
            if (recovery_event.death_started) {
                primary_held = false;
                scanner = false;
                tactical = false;
                append_combat_log(combat_log_path, now, "PLAYER_DEATH", current_zone,
                                  weapon_slot, combat, player);
                std::cout << recovery_event.message << " | cause "
                          << signalcloud::world::damage_cause_name(recovery.cause())
                          << " | XAR lost " << recovery_event.xar_lost
                          << " | scrap lost " << recovery_event.scrap_lost << '\n';
            }
            if (recovery_event.respawned) {
                const std::string defeated_zone = recovery.death_zone().empty()
                    ? death_zone_before_recovery : std::string(recovery.death_zone());
                threat_director.on_player_recovered(combat, defeated_zone);
                camera.set_position(player.position());
                camera.set_yaw_degrees(-90.0F);
                camera.set_pitch_degrees(0.0F);
                current_zone = std::string(level.zone_name(player.position()));
                tactical_map.observe_zone(level, current_zone);
                portal_ready_time = now + 1.0;
                append_zone_log(options.root / "reports/zone_trace.log", now, current_zone, player.position());
                append_combat_log(combat_log_path, now, "PLAYER_RECOVERED", current_zone,
                                  weapon_slot, combat, player);
                std::cout << recovery_event.message << '\n';
            }
            std::string dynamic_error;
            auto dynamic_points = combat.build_visual_points(static_cast<float>(now), current_zone);
            auto economy_points = economy.build_visual_points(static_cast<float>(now), current_zone, player.position());
            dynamic_points.insert(dynamic_points.end(), economy_points.begin(), economy_points.end());
            signalcloud::pcp3::RuntimeContext pcp3_context;
            pcp3_context.time_seconds = now;
            pcp3_context.scanner_active = scanner;
            pcp3_context.debug_evidence = scanner;
            pcp3_context.interaction_pressed = interact_pressed;
            pcp3_context.viewer_position = player.position();
            pcp3_context.interaction_state = &pcp3_interactions;
            pcp3_context.encounter_state = &pcp3_encounters;
            auto pcp3_points = signalcloud::pcp3::points_for_zone(
                pcp3_assets, current_zone, signalcloud::pcp3::PreviewPurpose::game,
                pcp3_context, 350'000U);
            dynamic_points.insert(dynamic_points.end(), pcp3_points.begin(), pcp3_points.end());
            const auto welcome_asset = std::find_if(
                pcp3_assets.begin(), pcp3_assets.end(), [](const auto& asset) {
                    return asset.metadata.asset_id == "a3_preview_marker" && asset.metadata.enabled;
                });
            const auto font = font_service.default_font();
            if (welcome_asset != pcp3_assets.end() && font &&
                signalcloud::math::length(welcome_asset->metadata.preview_position - player.position()) <= 20.0F) {
                signalcloud::font::TextPointStyle welcome_style;
                welcome_style.opacity = 1.0F;
                welcome_style.tint = {0.18F, 1.0F, 0.43F};
                welcome_style.replace_rgb = true;
                welcome_style.density = 4.0F;
                const auto welcome_placement = signalcloud::font::distance_eased_billboard_placement(
                    welcome_asset->metadata.preview_position, camera.position());
                (void)signalcloud::font::append_constant_apparent_billboard(
                    dynamic_points, *font, "WELCOME",
                    welcome_placement.anchor, camera.position(),
                    welcome_placement.apparent_width_ratio,
                    welcome_style, true, 8'000U);
            }
            for (const auto& interaction_event : pcp3_interactions.take_events()) {
                if (!interaction_event.console_log) continue;
                std::cout << "PCP3 interaction: " << interaction_event.asset_id << " trigger "
                          << (interaction_event.trigger_index + 1U) << " -> " << interaction_event.action;
                if (!interaction_event.target.empty()) std::cout << " (" << interaction_event.target << ")";
                std::cout << '\n';
            }
            for (const auto& encounter_event : pcp3_encounters.take_events()) {
                if (!encounter_event.console_log) continue;
                std::cout << "PCP3 encounter: " << encounter_event.encounter_id << " -> " << encounter_event.kind;
                if (!encounter_event.referenced_asset_id.empty()) std::cout << " (" << encounter_event.referenced_asset_id << ")";
                if (encounter_event.kind == "reward_hook") {
                    std::cout << " [telemetry only: proofs " << encounter_event.reward_proofs
                              << ", XAR " << encounter_event.reward_xar << ", scrap " << encounter_event.reward_scrap << "]";
                }
                std::cout << '\n';
            }
            if (!renderer.upload_dynamic_points(dynamic_points, &dynamic_error)) {
                std::cerr << "Dynamic entity upload failed: " << dynamic_error << '\n';
                running = false;
            }
            const auto camera_forward = camera.forward();
            signalcloud::math::Vec3 flat_forward{camera_forward.x, 0.0F, camera_forward.z};
            flat_forward = signalcloud::math::normalize_or(flat_forward, {0.0F, 0.0F, -1.0F});
            const auto camera_right = signalcloud::math::normalize_or(
                signalcloud::math::cross(flat_forward, {0.0F, 1.0F, 0.0F}), {1.0F, 0.0F, 0.0F});
            signalcloud::combat::ViewmodelPose viewmodel_pose;
            viewmodel_pose.camera_position = camera.position();
            viewmodel_pose.forward = camera_forward;
            viewmodel_pose.right = camera_right;
            viewmodel_pose.pitch_degrees = camera.pitch_degrees();
            viewmodel_pose.movement_amount = movement_amount;
            viewmodel_pose.sprinting = player_sprinting;
            viewmodel_pose.crouched = player.crouched();
            viewmodel_pose.swimming = player.water_state() == signalcloud::world::WaterState::swimming;
            viewmodel_pose.weapon_slot = weapon_slot;
            signalcloud::ui::ArPose ar_pose;
            ar_pose.camera_position = camera.position();
            ar_pose.forward = camera_forward;
            ar_pose.right = camera_right;
            signalcloud::ui::ArInterfaceData ar_data;
            ar_data.health_ratio = std::clamp(player.health() / 100.0F, 0.0F, 1.0F);
            ar_data.oxygen_ratio = std::clamp(player.oxygen_ratio(), 0.0F, 1.0F);
            ar_data.sabs_ratio = std::clamp(economy.sabs_wetness_ratio(), 0.0F, 1.0F);
            ar_data.carry_ratio = std::clamp(economy.encumbrance_ratio(), 0.0F, 1.0F);
            ar_data.xar = economy.xar_balance();
            ar_data.magazine = combat.magazine();
            ar_data.reserve = combat.reserve_ammo();
            ar_data.weapon_slot = weapon_slot;
            ar_data.belt_slot = belt_slot;
            ar_data.interaction_near = economy.interaction_target(
                player.position(), current_zone, 1.4F) != signalcloud::economy::InteractionTarget::none;
            ar_data.safe_room = is_safe_room(current_zone);
            ar_data.vending_menu = economy.vending_menu_active();
            ar_data.menu_product = economy.menu_product();
            ar_data.menu_quantity = economy.menu_quantity();
            ar_data.menu_unit_price = economy.menu_unit_price();
            ar_data.menu_cursor_x = economy.menu_cursor_x();
            ar_data.menu_cursor_y = economy.menu_cursor_y();
            ar_data.detailed_hint = detailed_title;
            ar_data.scanner_active = scanner;
            ar_data.scanner_strength = economy.scanner_strength();
            ar_data.danger_kind = danger_kind_for(recovery.phase() == signalcloud::world::RecoveryPhase::alive
                ? player.last_damage_cause() : recovery.cause());
            ar_data.recovery_active = recovery.phase() != signalcloud::world::RecoveryPhase::alive;
            ar_data.recovery_progress = recovery.progress();
            ar_data.blackout_strength = recovery.blackout_strength();
            populate_scanner_contacts(ar_data, level, combat, economy, current_zone, player.position());

            std::vector<signalcloud::render::PointGpu> viewmodel_points;
            if (native_scui_open()) {
                viewmodel_points = active_native_scui()->build_points(static_cast<float>(now), ar_pose);
                if (active_scui_kind == NativeScuiKind::light_lab) {
                    auto light_preview_points = light_scui_preview.build_points(
                        light_scui, static_cast<float>(now), ar_pose);
                    viewmodel_points.insert(viewmodel_points.end(),
                                            light_preview_points.begin(), light_preview_points.end());
                }
                if (active_scui_kind == NativeScuiKind::tupd_workbench && !tupd_recipes.empty()) {
                    const auto* tupd_instance = tupd_sandbox.result_instance() ? &*tupd_sandbox.result_instance() : nullptr;
                    const auto* tupd_test = tupd_sandbox.last_test() ? &*tupd_sandbox.last_test() : nullptr;
                    auto ghost_points = tupd_ghost_preview.build_points(
                        tupd_recipes[tupd_recipe_index], tupd_preview,
                        static_cast<float>(now), ar_pose, tupd_instance, tupd_test,
                        tupd_ghost_inspection_mode, tupd_ghost_exploded);
                    viewmodel_points.insert(viewmodel_points.end(),
                                            ghost_points.begin(), ghost_points.end());
                }
            } else {
                viewmodel_points = recovery.controls_locked()
                    ? std::vector<signalcloud::render::PointGpu>{}
                    : combat.build_viewmodel_points(static_cast<float>(now), viewmodel_pose);
                auto ar_points = ar_interface.build_points(static_cast<float>(now), ar_pose, ar_data);
                viewmodel_points.insert(viewmodel_points.end(), ar_points.begin(), ar_points.end());
            }
            std::string viewmodel_error;
            if (!renderer.upload_viewmodel_points(viewmodel_points, &viewmodel_error)) {
                std::cerr << "Viewmodel point upload failed: " << viewmodel_error << '\n';
                running = false;
            }
        } else {
            std::string map_error;
            auto map_points = tactical_map.build_points(
                level, player.position(), camera.forward(), current_zone,
                combat, economy, static_cast<float>(now));
            if (!renderer.upload_dynamic_points(map_points, &map_error)) {
                std::cerr << "Tactical memory-map upload failed: " << map_error << '\n';
                running = false;
            }
            if (!renderer.upload_viewmodel_points({}, &map_error)) {
                std::cerr << "Tactical viewmodel clear failed: " << map_error << '\n';
                running = false;
            }
        }

        signal_interference.update(dt, point_lab.preset().points);
        economy.update(dt, scanner);
        ar_interface.update(dt);
        local_siren.update(dt, active_area_for(level, current_zone));
        water_disturbance.update(dt);
        sound_ripple.update(dt);
        illuminosity_runtime.apply_authoring_override(
            light_scui.string("light_scope").value_or("room"),
            static_cast<float>(light_scui.number("light_i").value_or(96.0)),
            static_cast<float>(light_scui.number("light_radius").value_or(12.0)),
            static_cast<float>(light_scui.number("day_i").value_or(95.0)),
            static_cast<float>(light_scui.number("night_i").value_or(18.0)),
            std::numeric_limits<float>::quiet_NaN());
        illuminosity_runtime.update(dt);
        if (illuminosity_runtime.day_night().playing) {
            (void)light_scui.set_number("time_of_day", illuminosity_runtime.day_night().time_of_day);
        }
        const auto authored_light_frame = illuminosity_runtime.evaluate(player.position(), current_zone);
        renderer.set_illuminosity_frame(authored_light_frame);
        const auto authored_material_frame = material_runtime.evaluate(current_zone);
        renderer.set_material_frame(authored_material_frame);
        const auto audio_event = sound_ripple.event();
        renderer.set_audio_interference(audio_event);

        current_distance_limit = 46.0F;
        if (current_zone == "Long Signal Hall") current_distance_limit = 38.0F;
        if (current_zone == "Submerged Service Tunnel") current_distance_limit = 30.0F;
        if (current_zone == "Open Pressure Cavity") current_distance_limit = 34.0F;
        if (current_zone == "Submerged Boundary Lab") current_distance_limit = 32.0F;
        if (player.water_state() == signalcloud::world::WaterState::swimming) {
            current_distance_limit /= std::sqrt(std::max(0.65F, player.water_viscosity()));
        }
        const auto local_light = level.strongest_light(player.position(), current_zone);
        current_distance_limit += local_light.influence * 18.0F;
        current_distance_limit += authored_light_frame.local_strength * 10.0F +
                                  authored_light_frame.global_strength * 4.0F;
        if (scanner) current_distance_limit += 16.0F * economy.scanner_strength();
        std::vector<signalcloud::render::PreviewRequest> preview_requests;
        for (const auto& preview : level.connection_previews(current_zone, player.position())) {
            preview_requests.push_back({std::string(preview.destination_zone),
                                        preview.center, preview.strength,
                                        preview.viewer_position, preview.normal,
                                        preview.half_width, preview.bottom_y, preview.top_y});
        }
        if (tactical) {
            visibility = {};
            visibility.resident_points = renderer.resident_count();
            visibility.submitted_points = tactical_map.stats().submitted_points;
            visibility.submitted_rooms = tactical_map.stats().visited_rooms +
                                         tactical_map.stats().scanned_rooms;
            visibility.submitted_ranges = tactical_map.stats().remembered_connections;
            visibility.submitted_point_cap = 16'000U;
            renderer.set_draw_ranges({});
        } else {
            visibility = signalcloud::render::select_room_ranges(
                cloud, current_zone, signal_interference.equivalent_points(),
                point_lab.preset().points, false, player.position(), current_distance_limit,
                preview_requests);
            const auto& active_pool_budget = signalcloud::render::system_point_budget_for_total(
                std::max<std::uint32_t>(4'000'000U, point_lab.preset().points));
            signalcloud::render::enforce_submitted_point_cap(
                visibility, active_pool_budget.submitted_soft_cap);
            renderer.set_draw_ranges(visibility.ranges);
        }
        renderer.set_tactical_marker(player.position());

        int width = 1280;
        int height = 720;
        SDL_GetWindowSizeInPixels(window, &width, &height);
        const float aspect = height > 0 ? static_cast<float>(width) / static_cast<float>(height) : 16.0F / 9.0F;
        const auto matrix = tactical ? tactical_map.view_projection(aspect, level) : camera.view_projection(aspect);
        renderer.render(matrix, static_cast<float>(now), pulse, scanner, tactical,
                        point_lab.point_scale(), point_lab.density_scale(),
                        signal_interference.level(), local_siren.position(), local_siren.radius(),
                        local_siren.intensity(), water_disturbance.position(),
                        water_disturbance.radius(), water_disturbance.intensity(),
                        water_disturbance.bomb(), local_light.position,
                        local_light.radius, local_light.influence,
                        sound_ripple.position(), sound_ripple.radius(),
                        sound_ripple.intensity(), combat.void_position(current_zone),
                        combat.void_radius(current_zone), combat.void_strength(current_zone),
                        width, height);
        SDL_GL_SwapWindow(window);

        fps_time += dt;
        ++fps_frames;
        if (fps_time >= 0.5) {
            fps = static_cast<float>(static_cast<double>(fps_frames) / fps_time);
            fps_frames = 0;
            fps_time = 0.0;
            std::ostringstream title;
            title << std::fixed << std::setprecision(1);
            if (!detailed_title) {
                title << "ALMOND SIGNAL | "
                      << (tactical ? tactical_map.mode_label() : (lab_mode ? "POINT LAB" : current_zone))
                      << " | " << point_lab.preset().name
                      << " | " << static_cast<int>(fps) << " FPS"
                      << (scanner ? " | SCAN" : "")
                      << (native_scui_open() ? " | SCUI" : "")
                      << (recovery.controls_locked() ? " | RECOVER" : "")
                      << " | F12";
            } else {
                title << "ALMOND SIGNAL DIAG | " << current_zone
                      << " | " << point_lab.preset().name
                      << " RES " << renderer.resident_count()
                      << " SUB " << (tactical ? tactical_map.stats().submitted_points : renderer.point_count())
                      << " CAP " << visibility.submitted_point_cap
                      << (visibility.cap_applied ? " TRIM " : " ")
                      << "| " << static_cast<int>(fps) << " FPS GPU " << renderer.last_gpu_ms() << "ms"
                      << " | POS " << player.position().x << ',' << player.position().y << ',' << player.position().z
                      << " | RANGE " << current_distance_limit
                      << " LIGHT " << local_light.influence
                      << " | LOAD " << economy.carried_weight() << '/' << economy.capacity()
                      << " SABS " << static_cast<int>(economy.sabs_wetness_ratio() * 100.0F) << '%'
                      << " THR " << threat_director.stats().active_world_entities
                      << " P " << threat_director.stats().current_zone_pressure
                      << (recovery.controls_locked() ? " RECOVER" : "")
                      << (native_scui_open() ? " | SCUI P" + std::to_string(active_native_scui()->current_page() + 1U)
                                                    + " PTS " + std::to_string(active_native_scui()->stats().generated_points)
                                             : "")
                      << (tactical ? " | MAP ROOMS " + std::to_string(tactical_map.stats().visited_rooms)
                                           + "+" + std::to_string(tactical_map.stats().scanned_rooms)
                                           + " LVL " + std::to_string(tactical_map.stats().logical_levels)
                                           + " SLOT " + std::to_string(tactical_map.stats().threshold_slots)
                                           + " PTS " + std::to_string(tactical_map.stats().submitted_points)
                                  : " | VM " + std::to_string(combat.last_viewmodel_visual_count())
                                           + " ENT " + std::to_string(combat.last_world_visual_count()))
                      << " | F12 COMPACT";
            }
            SDL_SetWindowTitle(window, title.str().c_str());
            if (now >= next_stream_log_time) {
                append_stream_log(stream_log_path, now, current_zone, renderer.resident_count(),
                                  tactical ? tactical_map.stats().submitted_points : renderer.point_count(), visibility.submitted_rooms,
                                  signal_interference, fps, renderer.last_gpu_ms(), tactical,
                                  visibility.submitted_ranges, visibility.preview_rooms,
                                  visibility.preview_ranges, visibility.anchored_source_ranges,
                                  current_distance_limit, local_light.influence,
                                  visibility.submitted_point_cap, visibility.points_trimmed,
                                  visibility.cap_applied);
                next_stream_log_time = now + 1.0;
            }
            if (now >= next_traversal_log_time) {
                append_traversal_log(traversal_log_path, now, player, current_zone, "SAMPLE");
                next_traversal_log_time = now + 0.5;
            }
            if (now >= next_depth_log_time) {
                append_depth_log(depth_log_path, now, "SAMPLE", current_zone,
                                 player, current_distance_limit);
                next_depth_log_time = now + 0.5;
            }
        }

        const auto residency_decision = residency.update(
            dt, fps, renderer.last_gpu_ms(), is_safe_room(current_zone), tactical);
        if (residency_decision.requested_points) {
            if (const auto fallback_index = preset_index_for(*residency_decision.requested_points)) {
                std::cout << "Adaptive residency: " << residency_decision.reason
                          << " -> " << *residency_decision.requested_points << " points\n";
                select_preset(*fallback_index, "adaptive_protected_fallback");
            }
        }
        SDL_Delay(1);
    }

    append_benchmark(benchmark_path, previous, point_lab, fps, renderer.last_gpu_ms(),
                     renderer.allocated_bytes(), last_generation_ms, scanner, tactical, "session_end");
    // SplashAudio owns SDL resources. Destroy them before SDL_Quit; Pivot 6
    // left this to the C++ destructor after subsystem shutdown, which could
    // produce an end-of-session segmentation fault.
    splash_audio.shutdown();
    renderer.shutdown();
    SDL_SetWindowRelativeMouseMode(window, false);
    (void)SDL_ShowCursor();
    SDL_GL_DestroyContext(context);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
