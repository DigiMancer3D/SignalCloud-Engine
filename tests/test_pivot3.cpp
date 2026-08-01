#include "engine/data/udata.hpp"
#include "engine/platform/first_person_camera.hpp"
#include "engine/render/adaptive_budget.hpp"
#include "engine/render/point_cloud.hpp"
#include "engine/render/point_lab.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/player_controller.hpp"
#include "engine/world/world_seed.hpp"

#include <cmath>
#include <filesystem>
#include <iostream>
#include <string>

namespace {
int failures = 0;
void check(bool condition, const std::string& message) {
    if (condition) std::cout << "PASS: " << message << '\n';
    else { std::cerr << "FAIL: " << message << '\n'; ++failures; }
}
}

int main(int argc, char** argv) {
    const std::filesystem::path root = argc > 1 ? argv[1] : std::filesystem::current_path();
    using namespace signalcloud;

    const auto accepted = render::recommend_point_budget("Intel", "Mesa Intel UHD Graphics", 4, 6);
    check(accepted.gameplay_points >= 2'000'000U, "streamed Intel/Mesa gameplay remains at or above the accepted 2M floor");
    check(render::kPointLabPresets.back().points == 8'000'000U, "8M remains the absolute showcase ceiling");

    const auto seed = world::mix_seed(0xA11D0A1ULL, {0, 0, 0}, 3);
    const auto same_seed = world::mix_seed(0xA11D0A1ULL, {0, 0, 0}, 3);
    const auto next_seed = world::mix_seed(0xA11D0A1ULL, {1, 0, 0}, 3);
    const auto level = world::LiminalLevel::make_pivot3_procedural(seed, 12U);
    const auto repeated = world::LiminalLevel::make_pivot3_procedural(same_seed, 12U);
    const auto different = world::LiminalLevel::make_pivot3_procedural(next_seed, 12U);

    check(level.areas().size() == 12U, "procedural tape contains twelve room chunks");
    check(level.portals().size() == 15U, "portal graph contains twelve route gates plus three Matrix choices");
    check(level.layout_signature() == repeated.layout_signature(), "same seed reproduces the same layout signature");
    check(level.layout_signature() != different.layout_signature(), "new tape seed changes the layout signature");
    check(level.zone_name(level.spawn_position()) == "Reception Tape", "spawn begins in Reception Tape");
    check(level.can_occupy(level.spawn_position().x, level.spawn_position().z, 0.48F),
          "wider Pivot 3 player capsule fits at spawn");

    bool all_destinations_safe = true;
    bool all_sources_detectable = true;
    for (const auto& portal : level.portals()) {
        all_destinations_safe = all_destinations_safe &&
            level.can_occupy(portal.destination.x, portal.destination.z, 0.48F);
        const auto probe = portal.center + portal.inward_normal * 0.55F;
        all_sources_detectable = all_sources_detectable && level.portal_at(probe) != nullptr;
    }
    check(all_destinations_safe, "every portal destination is analytically occupiable");
    check(all_sources_detectable, "every portal trigger is detectable from inside its source room");

    world::PlayerController player(level.spawn_position());
    check(player.collision_radius() >= 0.47F, "wall standoff radius prevents camera contact with sparse point walls");
    const auto& first_portal = level.portals().front();
    player.teleport(first_portal.destination);
    check(std::abs(player.position().x - first_portal.destination.x) < 0.001F &&
          std::abs(player.position().z - first_portal.destination.z) < 0.001F,
          "player controller accepts deterministic portal transit");

    platform::FirstPersonCamera camera;
    camera.set_yaw_degrees(33.0F);
    camera.set_pitch_degrees(120.0F);
    check(std::abs(camera.yaw_degrees() - 33.0F) < 0.001F, "portal transit can assign camera yaw");
    check(camera.pitch_degrees() <= 84.0F, "portal camera pitch remains clamped");

    const auto cloud = render::PointCloud::make_liminal_level(level, {300'000U, seed});
    check(cloud.points().size() == 300'000U, "procedural portal cloud preserves exact point count");
    check(cloud.finite(), "procedural portal cloud contains finite data");
    check(cloud.stats().portal_points == 9'000U, "three percent of Pivot 3 points identify portal frames");

    const auto renderer_config = data::UDataDocument::load(root / "config/renderer.udata");
    const auto movement_config = data::UDataDocument::load(root / "config/movement.udata");
    const auto portal_config = data::UDataDocument::load(root / "config/portals.udata");
    check(!renderer_config.has_errors() && !movement_config.has_errors() && !portal_config.has_errors(),
          "Pivot 3 renderer, movement, and portal configs load without errors");
    check(renderer_config.value("body", "near_wall_splat_boost").has_value(),
          "renderer config records close-wall splat reinforcement");
    check(portal_config.value("body", "room_count").has_value(),
          "portal config records procedural room count");

    if (failures == 0) {
        std::cout << "All SignalCloud Pivot 3 Portal Graph tests passed.\n";
        return 0;
    }
    return 1;
}
