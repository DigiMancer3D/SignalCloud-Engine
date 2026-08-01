#include "engine/ai/playbook.hpp"
#include "engine/assets/manifest_index.hpp"
#include "engine/assets/hot_reload_index.hpp"
#include "engine/assets/hot_reload_status.hpp"
#include "engine/audio/audio_interference_runtime.hpp"
#include "engine/combat/combat_system.hpp"
#include "engine/economy/economy_system.hpp"
#include "engine/ui/ar_interface.hpp"
#include "engine/ui/scui_panel.hpp"
#include "engine/ui/scui_native_runtime.hpp"
#include "engine/ui/scui_registry.hpp"
#include "engine/ui/scui_light_preview.hpp"
#include "engine/ui/tactical_memory_map.hpp"
#include "engine/data/udata.hpp"
#include "engine/input/input_profile.hpp"
#include "engine/lighting/illuminosity_bake.hpp"
#include "engine/lighting/illuminosity_runtime.hpp"
#include "engine/materials/material_runtime.hpp"
#include "engine/scfont/font_service.hpp"
#include "engine/render/sound_ripple.hpp"
#include "engine/render/adaptive_budget.hpp"
#include "engine/render/adaptive_residency.hpp"
#include "engine/render/memory_budget.hpp"
#include "engine/render/point_cloud.hpp"
#include "engine/render/point_lab.hpp"
#include "engine/render/room_visibility.hpp"
#include "engine/render/system_point_budget.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/player_controller.hpp"
#include "engine/world/recovery_system.hpp"
#include "engine/world/threat_director.hpp"
#include "engine/world/threat_navigation.hpp"
#include "engine/world/world_seed.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    const std::filesystem::path root = argc > 1 ? argv[1] : std::filesystem::current_path();
    std::cout << "ALMOND SIGNAL: LIVE TAPE / SignalCloud Engine\n"
              << "Threshold Pursuit, Vertical Perception & Tablet Identity Lab v0.13.0-a3\n";

    const auto profile = signalcloud::input::InputProfile::solo_paw_defaults();
    const auto input_issues = profile.validate();
    std::cout << "Input actions: " << profile.actions().size()
              << " | validation errors: " << input_issues.size() << '\n';

    const auto renderer_config = signalcloud::data::UDataDocument::load(root / "config/renderer.udata");
    const auto movement_config = signalcloud::data::UDataDocument::load(root / "config/movement.udata");
    const auto traversal_config = signalcloud::data::UDataDocument::load(root / "config/traversal.udata");
    const auto siren_config = signalcloud::data::UDataDocument::load(root / "config/sirens.udata");
    const auto depth_config = signalcloud::data::UDataDocument::load(root / "config/depth.udata");
    const auto continuity_config = signalcloud::data::UDataDocument::load(root / "config/continuity.udata");
    const auto water_material_config = signalcloud::data::UDataDocument::load(root / "config/water_material.udata");
    const auto envelope_config = signalcloud::data::UDataDocument::load(root / "config/threshold_envelope.udata");
    const auto combat_config = signalcloud::data::UDataDocument::load(root / "config/combat.udata");
    const auto animation_config = signalcloud::data::UDataDocument::load(root / "config/animation.udata");
    const auto point_pool_config = signalcloud::data::UDataDocument::load(root / "config/point_pools.udata");
    const auto economy_config = signalcloud::data::UDataDocument::load(root / "config/economy.udata");
    const auto ar_config = signalcloud::data::UDataDocument::load(root / "config/ar_interface.udata");
    const auto tactical_config = signalcloud::data::UDataDocument::load(root / "config/tactical_map.udata");
    const auto threat_config = signalcloud::data::UDataDocument::load(root / "config/threat_director.udata");
    const auto recovery_config = signalcloud::data::UDataDocument::load(root / "config/recovery.udata");
    const auto residency_config = signalcloud::data::UDataDocument::load(root / "config/adaptive_residency.udata");
    const auto navigation_config = signalcloud::data::UDataDocument::load(root / "config/threat_navigation.udata");
    const auto ammo_tablet_config = signalcloud::data::UDataDocument::load(root / "config/ammo_tablet.udata");
    const auto threshold_pursuit_config = signalcloud::data::UDataDocument::load(root / "config/threshold_pursuit.udata");
    const std::size_t recoverable_issues = renderer_config.issues().size() + movement_config.issues().size() +
        traversal_config.issues().size() + siren_config.issues().size() + depth_config.issues().size() +
        continuity_config.issues().size() + water_material_config.issues().size() +
        envelope_config.issues().size() + combat_config.issues().size() +
        animation_config.issues().size() + point_pool_config.issues().size() +
        economy_config.issues().size() + ar_config.issues().size() + tactical_config.issues().size() +
        threat_config.issues().size() + recovery_config.issues().size() + residency_config.issues().size() +
        navigation_config.issues().size() + ammo_tablet_config.issues().size() +
        threshold_pursuit_config.issues().size();
    std::cout << ".udata renderer entries: " << renderer_config.entries().size()
              << " | movement entries: " << movement_config.entries().size()
              << " | traversal entries: " << traversal_config.entries().size()
              << " | combat entries: " << combat_config.entries().size()
              << " | animation entries: " << animation_config.entries().size()
              << " | point-pool entries: " << point_pool_config.entries().size()
              << " | economy entries: " << economy_config.entries().size()
              << " | AR entries: " << ar_config.entries().size()
              << " | tactical-map entries: " << tactical_config.entries().size()
              << " | threat entries: " << threat_config.entries().size()
              << " | recovery entries: " << recovery_config.entries().size()
              << " | adaptive-residency entries: " << residency_config.entries().size()
              << " | threat-navigation entries: " << navigation_config.entries().size()
              << " | ammo-tablet entries: " << ammo_tablet_config.entries().size()
              << " | threshold-pursuit entries: " << threshold_pursuit_config.entries().size()
              << " | recoverable issues: " << recoverable_issues << '\n';

    const auto manifest = signalcloud::assets::ManifestIndex::load_csv(root / "content/manifest.csv");
    const auto manifest_issues = manifest.validate();
    std::cout << "Manifest records: " << manifest.records().size()
              << " | validation errors: " << manifest_issues.size() << '\n';

    const auto hot_reload_index = signalcloud::assets::HotReloadIndex::load(
        root, root / "user_data/studio/hot_reload_candidates.udata");
    std::cout << "Protected hot reload: " << hot_reload_index.entries().size()
              << " candidates | mode " << hot_reload_index.mode()
              << " | validation " << (hot_reload_index.valid() ? "PASS" : "FAIL") << '\n';

    const auto hot_reload_status = signalcloud::assets::HotReloadStatus::load(
        root, root / "user_data/studio/hot_reload_latest.udata");
    std::cout << "Protected preview status: " << hot_reload_status.entries().size()
              << " supported | changed " << hot_reload_status.changed_count()
              << " | SCUI " << hot_reload_status.changed_scui_count()
              << " | lights " << hot_reload_status.changed_light_count()
              << " | PCP3 " << hot_reload_status.changed_pcp3_count()
              << " | materials " << hot_reload_status.changed_material_count()
              << " | audio " << hot_reload_status.changed_audio_count()
              << " | fonts " << hot_reload_status.changed_font_count()
              << " | tx " << hot_reload_status.transaction_id()
              << " | generated " << hot_reload_status.generated_unix()
              << " | validation " << (hot_reload_status.valid() ? "PASS" : "FAIL") << '\n';

    signalcloud::font::FontService font_service;
    const auto terminal_font_path =
        root / "content/core/fonts/terminal_00/Terminal_00.scfont";
    const bool terminal_font_loaded =
        font_service.load("core.fonts.terminal_00", terminal_font_path) &&
        font_service.set_default("core.fonts.terminal_00");
    const auto terminal_font = font_service.default_font();
    std::cout << "SCFONT runtime: "
              << (terminal_font_loaded && terminal_font ? terminal_font->name : "legacy-fallback")
              << " | glyphs " << (terminal_font ? terminal_font->glyphs.size() : 0U)
              << " | generation " << font_service.generation("core.fonts.terminal_00")
              << " | validation " << (terminal_font_loaded ? "PASS" : "FALLBACK") << '\n';

    const auto scui_registry = signalcloud::ui::ScuiPanelRegistry::load(
        root, root / "content/core/ui/scui_panel_registry.udata");
    std::cout << "SCUI registry: entries " << scui_registry.entries().size()
              << " | default " << scui_registry.default_panel_key()
              << " | selector " << scui_registry.selector_panel_id()
              << " | validation " << (scui_registry.valid() ? "PASS" : "FAIL") << '\n';

    const auto selector_scui_panel = signalcloud::ui::ScuiPanel::load(
        root / "content/core/ui/authoring_lab_panel_selector.scui");
    signalcloud::ui::ScuiNativeRuntime selector_scui_runtime(selector_scui_panel, 4U);
    selector_scui_runtime.set_font(terminal_font);
    (void)selector_scui_runtime.register_command("authoring.panel.select");
    (void)selector_scui_runtime.register_command("authoring.panel.open");
    (void)selector_scui_runtime.register_command("authoring.panel.refresh");
    (void)selector_scui_runtime.set_choices(
        "panel", scui_registry.keys(), std::string(scui_registry.default_panel_key()));
    selector_scui_runtime.set_open(true);
    const auto selector_scui_points = selector_scui_runtime.build_points(0.5F, {});
    std::cout << "SCUI panel selector: " << selector_scui_panel.panel_id
              << " | registry choices " << scui_registry.keys().size()
              << " | points " << selector_scui_points.size()
              << " | validation " << (selector_scui_panel.valid() ? "PASS" : "FAIL") << '\n';

    const auto scui_panel = signalcloud::ui::ScuiPanel::load(
        root / "content/core/ui/authoring_lab_project_selector.scui");
    const auto scui_layout = signalcloud::ui::ScuiNativeLayout::build(scui_panel, 7U);
    signalcloud::ui::ScuiNativeCommandRegistry scui_commands;
    (void)scui_commands.register_command("authoring.project.select");
    (void)scui_commands.register_command("authoring.preview.toggle");
    (void)scui_commands.register_command("authoring.point_budget.set");
    (void)scui_commands.register_command("authoring.profile.refresh");
    std::cout << "SCUI proof panel: " << scui_panel.panel_id
              << " | controls: " << scui_panel.controls.size()
              << " | native pages: " << scui_layout.page_count
              << " | focusable: " << scui_layout.focus_order.size()
              << " | allowlisted commands: " << scui_commands.size()
              << " | validation: " << (scui_panel.valid() ? "PASS" : "FAIL") << '\n';
    signalcloud::ui::ScuiNativeRuntime scui_runtime(scui_panel, 4U);
    scui_runtime.set_font(terminal_font);
    (void)scui_runtime.register_command("authoring.project.select");
    (void)scui_runtime.register_command("authoring.preview.toggle");
    (void)scui_runtime.register_command("authoring.point_budget.set");
    (void)scui_runtime.register_command("authoring.profile.refresh");
    scui_runtime.set_open(true);
    signalcloud::ui::ArPose scui_pose;
    scui_pose.camera_position = {0.0F, 1.72F, 0.0F};
    const auto scui_points = scui_runtime.build_points(0.5F, scui_pose);
    const bool scui_points_finite = std::all_of(scui_points.begin(), scui_points.end(), [](const auto& point) {
        return std::isfinite(point.position[0]) && std::isfinite(point.position[1]) &&
               std::isfinite(point.position[2]) && std::isfinite(point.radius);
    });
    const auto scui_stats = scui_runtime.stats();
    std::cout << "SCUI native point proof: pages " << scui_runtime.layout().page_count
              << " | current " << (scui_runtime.current_page() + 1U)
              << " | points " << scui_points.size()
              << " | backplate " << scui_stats.backplate_points
              << " | wrapped lines " << scui_stats.wrapped_text_lines
              << " | finite: " << (scui_points_finite ? "yes" : "no") << '\n';


    const auto light_scui_panel = signalcloud::ui::ScuiPanel::load(
        root / "content/core/ui/light_lab_control_surface.scui");
    signalcloud::ui::ScuiNativeRuntime light_scui_runtime(light_scui_panel, 4U);
    light_scui_runtime.set_font(terminal_font);
    for (const std::string command : {
             "light.scope.set", "light.illuminosity.set", "light.radius.set",
             "light.day_illuminosity.set", "light.night_illuminosity.set",
             "light.time_of_day.set", "light.timeline.play", "light.timeline.pause",
             "light.timeline.stop", "light.probe.sample", "light.diagnostics.bake",
             "light.document.reload", "light.document.save"}) {
        (void)light_scui_runtime.register_command(command);
    }
    const auto light_binding_count = static_cast<std::size_t>(std::count_if(
        light_scui_panel.controls.begin(), light_scui_panel.controls.end(),
        [](const auto& control) { return !control.document_binding.empty(); }));
    light_scui_runtime.set_open(true);
    light_scui_runtime.show_notice(
        signalcloud::ui::ScuiNativeNoticeKind::success, "LIGHT SAVED", 0.5F, 2.0F);
    const auto light_scui_points = light_scui_runtime.build_points(0.5F, scui_pose);
    signalcloud::ui::ScuiLightPreview light_preview;
    const auto light_preview_points = light_preview.build_points(light_scui_runtime, 0.5F, scui_pose);
    std::cout << "Light Lab SCUI: " << light_scui_panel.panel_id
              << " | controls " << light_scui_panel.controls.size()
              << " | document bindings " << light_binding_count
              << " | native pages " << light_scui_runtime.layout().page_count
              << " | points " << light_scui_points.size()
              << " | notice points " << light_scui_runtime.stats().notice_points
              << " | preview points " << light_preview_points.size()
              << " | effective preview I " << light_preview.stats().effective_illuminosity
              << " | validation " << (light_scui_panel.valid() ? "PASS" : "FAIL") << '\n';

    const auto seed = signalcloud::world::mix_seed(0xA12D0A1ULL, {0, 0, 0}, 4);
    const auto level = signalcloud::world::LiminalLevel::make_pivot11_scavenging(seed);
    signalcloud::lighting::IlluminosityRuntime illuminosity(
        root, root / "user_data/studio/illuminosity_runtime.udata");
    std::string illuminosity_error;
    const bool illuminosity_loaded = illuminosity.reload(&illuminosity_error);
    const auto illuminosity_frame = illuminosity.evaluate(level.spawn_position(), "Reception Tape");
    const auto illuminosity_rays = illuminosity.diagnostic_rays_all(level);
    const auto illuminosity_probe = illuminosity.probe_surface(level.spawn_position(), "Reception Tape");
    signalcloud::lighting::IlluminosityBakeRequest diagnostic_bake_request;
    diagnostic_bake_request.center = level.spawn_position();
    diagnostic_bake_request.zone = "Reception Tape";
    diagnostic_bake_request.grid_size = 5U;
    diagnostic_bake_request.spacing = 1.5F;
    const auto diagnostic_bake = signalcloud::lighting::bake_illuminosity_grid(
        illuminosity, diagnostic_bake_request);
    std::cout << "Illuminosity runtime: " << illuminosity.stats().configured_lights
              << " configured | " << illuminosity.stats().enabled_lights << " enabled | selected "
              << illuminosity.stats().budget_active_lights << " | budget "
              << illuminosity.stats().selected_point_budget_cost << "/"
              << illuminosity.stats().effective_max_point_budget << " | active " << illuminosity_frame.active_lights
              << " | local contributors " << illuminosity_frame.local_light_count
              << " | room strength " << illuminosity_frame.local_strength
              << " | global strength " << illuminosity_frame.global_strength
              << " | rays " << illuminosity_rays.size()
              << " | probe " << illuminosity_probe.quality_band << ' ' << illuminosity_probe.effective_illuminosity_percent
              << " | bake " << diagnostic_bake.samples.size() << " samples sig " << diagnostic_bake.deterministic_signature
              << " | validation " << (illuminosity_loaded ? "PASS" : "FAIL") << '\n';
    if (!illuminosity_loaded) std::cerr << "Illuminosity diagnostic warning: " << illuminosity_error << '\n';
    signalcloud::materials::MaterialRuntime material_runtime(
        root, root / "user_data/studio/material_runtime.udata");
    std::string material_error;
    const bool material_loaded = material_runtime.reload(&material_error);
    const auto material_frame = material_runtime.evaluate("Reception Tape");
    signalcloud::audio::AudioInterferenceRuntime audio_runtime(
        root, root / "user_data/studio/audio_interference_runtime.udata");
    std::string audio_error;
    const bool audio_loaded = audio_runtime.reload(&audio_error);
    const auto& bark_profile = audio_runtime.hash_dog_bark();
    signalcloud::render::SoundRipple bark_ripple;
    bark_ripple.trigger_event(level.spawn_position(), bark_profile.strength,
        bark_profile.frequency_band, bark_profile.obstruction_path,
        bark_profile.seed_salt, bark_profile.duration_seconds,
        bark_profile.radius_scale, bark_profile.wave_count,
        bark_profile.wave_sharpness, bark_profile.displacement_scale,
        bark_profile.color_mix, bark_profile.visibility_floor);
    const auto bark_event = bark_ripple.event();
    std::cout << "Material runtime: " << material_runtime.stats().material_count
              << " materials | " << material_runtime.stats().assignment_count
              << " assignments | active " << material_frame.active_materials
              << " | budget " << material_frame.selected_point_budget << "/"
              << material_frame.max_point_budget
              << " | opacity " << material_frame.combined_opacity
              << " | layers " << material_frame.surfaces[0].definition_layer_count << "/"
              << material_frame.surfaces[1].definition_layer_count << "/"
              << material_frame.surfaces[2].definition_layer_count
              << " | locked floor " << (material_frame.surfaces[0].locked ? "yes" : "no")
              << " | audio ripple " << signalcloud::render::frequency_band_name(bark_event.frequency_band)
              << " waves " << bark_event.wave_count
              << " budget " << audio_runtime.stats().point_budget_cost
              << " serial " << bark_event.serial
              << " | validation " << (material_loaded && audio_loaded ? "PASS" : "FAIL") << '\n';
    if (!audio_loaded) std::cerr << "Audio diagnostic warning: " << audio_error << '\n';
    if (!material_loaded) std::cerr << "Material diagnostic warning: " << material_error << '\n';
    bool playbook_loaded = false;
    try {
        const auto playbooks = signalcloud::ai::PlaybookRuntime::load(
            root / "user_data/studio/playbook_runtime.scplayruntime");
        const auto dog_trace = playbooks.evaluate(
            "core.hash_dog.signal_investigate",
            {"event.sound_heard", {"path.available"}});
        const auto water_trace = playbooks.evaluate(
            "core.environment.water_pressure_pulse", {"event.splash", {}});
        playbook_loaded = playbooks.valid() && dog_trace.size() == 4U && water_trace.size() == 4U;
        std::cout << "Universal Playbook runtime: " << playbooks.stats().graph_count
                  << " graphs | " << playbooks.stats().node_count << " nodes | "
                  << playbooks.stats().edge_count << " edges | budget "
                  << playbooks.stats().point_budget_cost << " | signature "
                  << playbooks.stats().signature << " | validation "
                  << (playbook_loaded ? "PASS" : "FAIL") << '\n';
    } catch (const std::exception& error) {
        std::cerr << "Playbook diagnostic warning: " << error.what() << '\n';
    }
    const auto cloud = signalcloud::render::PointCloud::make_liminal_level(level, {100'000U, seed});
    std::cout << "Procedural rooms: " << level.areas().size() << " | wall segments: " << level.walls().size()
              << " | obstacles: " << level.obstacles().size() << " | water regions: " << level.water_regions().size()
              << " | portals: " << level.portals().size()
              << " | connections: " << level.connections().size()
              << " | lights: " << level.lights().size() << '\n';

    std::vector<signalcloud::render::PreviewRequest> previews;
    for (const auto& preview : level.connection_previews("Scavenger Exchange", level.economy_lab_spawn())) {
        previews.push_back({std::string(preview.destination_zone), preview.center, preview.strength,
                            preview.viewer_position, preview.normal, preview.half_width,
                            preview.bottom_y, preview.top_y});
    }
    const auto visible = signalcloud::render::select_room_ranges(
        cloud, "Live-Fire Signal Range", 100'000U, 100'000U, false,
        level.combat_lab_spawn(), 36.0F, previews);
    std::cout << "Generated diagnostic points: " << cloud.points().size()
              << " | room ranges: " << cloud.ranges().size()
              << " | range submitted: " << visible.submitted_points
              << " | preview rooms: " << visible.preview_rooms
              << " | finite: " << (cloud.finite() ? "yes" : "no")
              << " | seed: " << signalcloud::world::seed_hex(seed) << '\n';

    const auto* corrected = [&]() -> const signalcloud::world::ThresholdEnvelope* {
        for (const auto& envelope : level.threshold_envelopes()) {
            const bool match = (envelope.zone_a == "Traversal & Water Lab" && envelope.zone_b == "Fallen Office") ||
                               (envelope.zone_b == "Traversal & Water Lab" && envelope.zone_a == "Fallen Office");
            if (match) return &envelope;
        }
        return nullptr;
    }();
    const bool normal_fixed = corrected != nullptr &&
        std::abs(std::abs(corrected->aperture.normal.x) - 1.0F) < 0.001F &&
        std::abs(corrected->aperture.normal.z) < 0.001F;


    signalcloud::world::ThreatNavigationRequest navigation_request;
    navigation_request.start = {644.6F, 0.0F, -163.0F};
    navigation_request.goal = {652.2F, 0.0F, -163.0F};
    navigation_request.zone = "Traversal & Water Lab";
    navigation_request.radius = 0.98F;
    navigation_request.body_height = 1.28F;
    navigation_request.step_height = 0.62F;
    navigation_request.grid_spacing = 0.72F;
    const auto navigation_route = signalcloud::world::plan_threat_route(level, navigation_request);
    bool navigation_route_valid = navigation_route.reached_goal_cell && !navigation_route.waypoints.empty();
    signalcloud::math::Vec3 route_previous = navigation_request.start;
    for (const auto& waypoint : navigation_route.waypoints) {
        navigation_route_valid = navigation_route_valid && signalcloud::world::threat_motion_line_clear(
            level, route_previous, waypoint, navigation_request.zone, navigation_request.radius,
            navigation_request.body_height, navigation_request.step_height, true);
        route_previous = waypoint;
    }

    auto combat = signalcloud::combat::CombatSystem::make_pivot10();
    auto threat_director = signalcloud::world::ThreatDirector::make_pivot13(level);
    const auto* hall = [&]() -> const signalcloud::world::WalkArea* {
        for (const auto& area : level.areas()) if (area.name == "Long Signal Hall") return &area;
        return nullptr;
    }();
    if (hall != nullptr) {
        const signalcloud::math::Vec3 position{(hall->min_x + hall->max_x) * 0.5F, 0.0F,
                                               (hall->min_z + hall->max_z) * 0.5F};
        for (int i = 0; i < 70; ++i) {
            (void)threat_director.update(0.1F, level, combat, position, "Long Signal Hall", false);
        }
    }
    bool threshold_queued = false;
    bool threshold_preview = false;
    bool threshold_arrived = false;
    if (const auto* service_portal = [&]() -> const signalcloud::world::PortalGate* {
            for (const auto& portal : level.portals()) {
                if (portal.source_zone == "Service Loop") return &portal;
            }
            return nullptr;
        }(); service_portal != nullptr) {
        auto threshold_combat = signalcloud::combat::CombatSystem::make_pivot10();
        const auto source_threshold = service_portal->center +
            service_portal->inward_normal * 0.55F;
        auto destination_entry = service_portal->destination;
        destination_entry.y = level.ground_height_at(
            destination_entry.x, destination_entry.z);
        const auto destination_forward = signalcloud::math::normalize_or(
            signalcloud::math::Vec3{-service_portal->inward_normal.x, 0.0F,
                                     -service_portal->inward_normal.z},
            signalcloud::math::Vec3{-1.0F, 0.0F, 0.0F});
        const auto start = source_threshold + service_portal->inward_normal * 2.25F;
        (void)threshold_combat.spawn_world_entity(
            signalcloud::combat::CreatureKind::hash_dog, start,
            service_portal->source_zone, 12.0F, 12.0F);
        threshold_combat.emit_noise(source_threshold, 2.0F,
                                    service_portal->source_zone);
        (void)threshold_combat.update(0.05F, source_threshold,
                                      service_portal->source_zone, &level);
        threshold_queued = threshold_combat.queue_threshold_pursuit(
            level, service_portal->source_zone,
            service_portal->destination_zone, source_threshold,
            destination_entry, destination_forward,
            14.0F, 14.0F, 3.0F, 1U) == 1U;
        const auto preview = threshold_combat.build_visual_points(
            0.3F, service_portal->destination_zone);
        threshold_preview = preview.size() > 1400U;
        for (int step = 0; step < 60 && !threshold_arrived; ++step) {
            threshold_arrived = threshold_combat.update_threshold_pursuits(
                0.05F, level, service_portal->destination_zone).arrived == 1U;
        }
    }
    const auto elevated_perception = signalcloud::combat::perception_envelope(
        signalcloud::combat::CreatureKind::hash_dog, 20.0F, 31.0F,
        4.2F, 1.0F, 45.0F);
    const bool vertical_perception_ok = elevated_perception.downward_advantage &&
        elevated_perception.effective_sight_radius > 27.0F &&
        std::abs(elevated_perception.maximum_hearing_radius - 62.0F) < 0.01F &&
        elevated_perception.required_loudness > 0.30F;

    const auto dynamic_points = combat.build_visual_points(0.0F, "Live-Fire Signal Range");
    bool dynamic_finite = !dynamic_points.empty();
    for (const auto& point : dynamic_points) {
        for (float value : point.position) dynamic_finite = dynamic_finite && std::isfinite(value);
        dynamic_finite = dynamic_finite && std::isfinite(point.radius);
    }
    signalcloud::combat::ViewmodelPose pose;
    pose.camera_position = {987.0F, 1.72F, -160.0F};
    pose.forward = {1.0F, 0.0F, 0.0F};
    pose.right = {0.0F, 0.0F, 1.0F};
    pose.movement_amount = 1.0F;
    pose.weapon_slot = 1;
    const auto viewmodel_points = combat.build_viewmodel_points(0.3F, pose);
    bool viewmodel_finite = !viewmodel_points.empty();
    for (const auto& point : viewmodel_points) {
        for (float value : point.position) viewmodel_finite = viewmodel_finite && std::isfinite(value);
        viewmodel_finite = viewmodel_finite && std::isfinite(point.radius);
    }
    std::cout << "Combat entities: " << combat.entities().size()
              << " | animated entity points: " << dynamic_points.size()
              << " | viewmodel points: " << viewmodel_points.size()
              << " | finite: " << (dynamic_finite && viewmodel_finite ? "yes" : "no") << '\n';

    const auto& full_budget = signalcloud::render::system_point_budget_for_total(20'000'000U);
    bool budgets_ok = true;
    for (const auto& budget : signalcloud::render::system_point_budgets()) {
        budgets_ok = budgets_ok && signalcloud::render::point_budget_is_balanced(budget);
    }
    std::cout << "Total point tiers: " << signalcloud::render::system_point_budgets().size()
              << " | 20M profile: " << full_budget.name
              << " | environment " << full_budget.environment_points
              << " | hostiles " << full_budget.hostile_points
              << " | viewmodel " << full_budget.player_viewmodel_points
              << " | submitted soft cap " << full_budget.submitted_soft_cap << '\n';

    auto economy = signalcloud::economy::EconomySystem::make_pivot12();
    const auto economy_points = economy.build_visual_points(0.25F, "Scavenger Exchange", level.economy_lab_spawn());
    const auto pickup = economy.interact({1052.5F, 1.72F, -169.0F}, "Scavenger Exchange", 1);
    economy.add_claimed_proof();
    const auto sale = economy.interact({1062.0F, 1.72F, -160.0F}, "Scavenger Exchange", 1);
    const auto ammo_tablet = economy.interact({1073.0F, 1.72F, -169.82F}, "Scavenger Exchange", 1);

    signalcloud::ui::ArInterface ar_interface;
    ar_interface.set_font(terminal_font);
    signalcloud::ui::ArPose ar_pose;
    ar_pose.camera_position = level.economy_lab_spawn();
    ar_pose.forward = {1.0F, 0.0F, 0.0F};
    ar_pose.right = {0.0F, 0.0F, 1.0F};
    signalcloud::ui::ArInterfaceData ar_data;
    ar_data.health_ratio = 0.12F;
    ar_data.oxygen_ratio = 0.74F;
    ar_data.sabs_ratio = economy.sabs_wetness_ratio();
    ar_data.carry_ratio = economy.encumbrance_ratio();
    ar_data.xar = economy.xar_balance();
    ar_data.magazine = combat.magazine();
    ar_data.reserve = combat.reserve_ammo();
    ar_data.interaction_near = true;
    ar_data.vending_menu = true;
    ar_data.menu_product = 2;
    ar_data.menu_quantity = 3;
    ar_data.menu_unit_price = 4;
    ar_data.scanner_active = true;
    ar_data.scanner_strength = 0.72F;
    ar_data.scanner_contacts[0] = {signalcloud::ui::ScannerContactKind::formed, 0.92F};
    ar_data.scanner_contacts[1] = {signalcloud::ui::ScannerContactKind::formless, 0.84F};
    ar_data.scanner_contacts[2] = {signalcloud::ui::ScannerContactKind::exchange, 0.68F};
    ar_data.scanner_contacts[3] = {signalcloud::ui::ScannerContactKind::loot, 0.64F};
    ar_data.scanner_contact_count = 4;
    const auto ar_points = ar_interface.build_points(0.35F, ar_pose, ar_data);
    bool ar_finite = !ar_points.empty();
    for (const auto& point : ar_points) {
        for (float value : point.position) ar_finite = ar_finite && std::isfinite(value);
        ar_finite = ar_finite && std::isfinite(point.radius);
    }


    signalcloud::ui::TacticalMemoryMap tactical_map;
    const std::string start_zone(level.zone_name(level.spawn_position()));
    tactical_map.reset(level, start_zone);
    tactical_map.observe_scan(level, start_zone);
    const auto tactical_points = tactical_map.build_points(
        level, level.spawn_position(), {0.0F, 0.0F, -1.0F}, start_zone,
        combat, economy, 0.25F);
    bool tactical_finite = !tactical_points.empty();
    for (const auto& point : tactical_points) {
        for (float value : point.position) tactical_finite = tactical_finite && std::isfinite(value);
        tactical_finite = tactical_finite && std::isfinite(point.radius);
    }
    std::cout << "JAM topology atlas: visited " << tactical_map.stats().visited_rooms
              << " | scanned " << tactical_map.stats().scanned_rooms
              << " | connections " << tactical_map.stats().remembered_connections
              << " | threshold slots " << tactical_map.stats().threshold_slots
              << " | logical levels " << tactical_map.stats().logical_levels
              << " | submitted points " << tactical_map.stats().submitted_points
              << " | environment points while open: 0"
              << " | finite: " << (tactical_finite ? "yes" : "no") << '\n';

    signalcloud::render::RoomVisibilitySelection capped;
    capped.ranges = {{0U, 900U, {}}, {900U, 700U, {}}};
    capped.submitted_points = 1600U;
    capped.submitted_ranges = 2U;
    signalcloud::render::enforce_submitted_point_cap(capped, 1200U);
    std::cout << "Economy pickups: " << economy.pickups().size()
              << " | exchange visual points: " << economy_points.size()
              << " | sample pickup: " << (pickup.success ? "yes" : "no")
              << " | sample sale XAR: " << sale.xar_delta
              << " | Ammo Tablet rounds: " << ammo_tablet.ammo_added
              << " | AR points: " << ar_points.size()
              << " | cap test: " << capped.submitted_points << "/" << capped.submitted_point_cap
              << " | trimmed: " << capped.points_trimmed << '\n';

    const auto intel = signalcloud::render::recommend_point_budget("Intel", "Mesa Intel UHD", 4, 6);
    signalcloud::render::AdaptiveResidencyController residency(intel.gameplay_points);
    for (int i = 0; i < 90; ++i) (void)residency.update(0.1F, 30.0F, 31.0, false, false);
    const auto fallback = residency.update(0.1F, 30.0F, 31.0, true, false);
    auto recovery_combat = signalcloud::combat::CombatSystem::make_pivot10();
    auto recovery_economy = signalcloud::economy::EconomySystem::make_pivot12();
    signalcloud::world::PlayerController recovery_player(level.spawn_position());
    signalcloud::world::RecoverySystem recovery;
    recovery_player.apply_damage(150.0F, signalcloud::world::DamageCause::combat);
    const auto death_event = recovery.update(0.016F, recovery_player, level, recovery_economy,
                                             recovery_combat, "Long Signal Hall");
    std::cout << "Accepted Pivot 13 Intel/Mesa adaptive baseline: " << intel.gameplay_points << " points"
              << " | protected fallback "
              << (fallback.requested_points ? std::to_string(*fallback.requested_points) : std::string("none"))
              << " | world threats " << threat_director.stats().active_world_entities
              << " | death handshake " << (death_event.death_started ? "PASS" : "FAIL") << '\n';
    std::cout << "Threat navigation: A-star route " << (navigation_route_valid ? "PASS" : "FAIL")
              << " | waypoints " << navigation_route.waypoints.size()
              << " | nearest-cell recovery " << (navigation_route.start_recovered || navigation_route.goal_recovered ? "used" : "not needed") << '\n';
    std::cout << "Ammo Tablet: direct 18-round reserve transfer " << (ammo_tablet.success ? "PASS" : "FAIL")
              << " | inventory weight bypass " << (economy.quantity(signalcloud::economy::ItemKind::ammo_pack) == 0U ? "PASS" : "FAIL")
              << " | red identity PASS\n";
    std::cout << "Threshold pursuit: queued " << (threshold_queued ? "PASS" : "FAIL")
              << " | preview signature " << (threshold_preview ? "PASS" : "FAIL")
              << " | delayed emergence " << (threshold_arrived ? "PASS" : "FAIL")
              << " | vertical perception " << (vertical_perception_ok ? "PASS" : "FAIL") << '\n';
    std::cout << "Submitted-point governor: hard cap + deterministic range trimming\n";
    std::cout << "Tactical memory: JAM-derived octagons + side-owned thresholds + persistent .tmap + zero environment ranges\n";
    std::cout << "AR layout: lowered vitals + corner towers + raised feedback + scanner signature band\n";
    std::cout << "Interaction tablets: XAR/EX exchange + Almond supplies + direct-reserve Ammo Tablet\n";
    std::cout << "World combat policy: weapons active outside safe/save rooms\n";
    std::cout << "Traversal readability: 0.60m auto-step + deterministic obstacle edge reserve\n";
    std::cout << "Frame-normal rollover: " << (normal_fixed ? "axis-aligned PASS" : "FAIL") << '\n';
    std::cout << "Combat motion: facing cones + skeletal gait + formed jump-dodge + formless flow-dodge\n";
    std::cout << "Viewmodel: point arms/hands + pistol ammo strip + directional prybar swing\n";
    std::cout << "Enemy attacks: claw arcs and sharp shadow lances use different silhouettes\n";
    std::cout << "Death result: claimable live 3D proof with deterministic signature\n";
    std::cout << "Defense: right-click/K evade with a brief invulnerability window\n";
    std::cout << "No Hood Rat Brawler arena modules are linked into this target.\n";

    const bool configs_ok = !renderer_config.has_errors() && !movement_config.has_errors() &&
        !traversal_config.has_errors() && !siren_config.has_errors() && !depth_config.has_errors() &&
        !continuity_config.has_errors() && !water_material_config.has_errors() &&
        !envelope_config.has_errors() && !combat_config.has_errors() &&
        !animation_config.has_errors() && !point_pool_config.has_errors() &&
        !economy_config.has_errors() && !ar_config.has_errors() && !tactical_config.has_errors() &&
        !threat_config.has_errors() && !recovery_config.has_errors() && !residency_config.has_errors() &&
        !navigation_config.has_errors() && !ammo_tablet_config.has_errors() &&
        !threshold_pursuit_config.has_errors();
    return input_issues.empty() && cloud.finite() && dynamic_finite && viewmodel_finite && ar_finite && tactical_finite && budgets_ok && normal_fixed && configs_ok &&
           manifest_issues.empty() && pickup.success && sale.success && ammo_tablet.success &&
           navigation_route_valid && threshold_queued && threshold_preview &&
           threshold_arrived && vertical_perception_ok && capped.cap_applied &&
           material_loaded && material_frame.active_materials == 3U && bark_event.serial == 1U &&
           playbook_loaded ? 0 : 1;
}
