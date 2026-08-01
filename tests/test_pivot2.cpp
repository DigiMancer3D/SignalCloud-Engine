#include "engine/data/udata.hpp"
#include "engine/render/adaptive_budget.hpp"
#include "engine/render/memory_budget.hpp"
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
void check(bool value, const std::string& label) {
    if (value) std::cout << "PASS: " << label << '\n';
    else { std::cerr << "FAIL: " << label << '\n'; ++failures; }
}
}

int main(int argc, char** argv) {
    const std::filesystem::path root = argc > 1 ? argv[1] : std::filesystem::current_path();
    using namespace signalcloud;

    const auto intel = render::recommend_point_budget("Intel", "Mesa Intel UHD Graphics", 4, 6);
    check(intel.gameplay_points >= 2'000'000U, "streamed Intel/Mesa gameplay budget remains at or above the accepted 2M floor");
    const auto discrete = render::recommend_point_budget("NVIDIA Corporation", "GeForce RTX", 4, 6);
    check(discrete.gameplay_points == 2'000'000U, "discrete GPU gameplay budget selects 2M");
    const auto software = render::recommend_point_budget("Mesa", "llvmpipe", 4, 5);
    check(software.gameplay_points == 100'000U, "software renderer budget selects 100K");

    bool has_3m = false;
    bool has_8m = false;
    for (const auto& preset : render::kPointLabPresets) {
        has_3m = has_3m || preset.points == 3'000'000U;
        has_8m = has_8m || preset.points == 8'000'000U;
    }
    check(render::kPointLabPresets.size() == 7U, "Pivot 2 Point Lab exposes seven presets");
    check(has_3m, "Point Lab includes the requested 3M stress tier");
    check(has_8m, "Point Lab includes the requested 8M stress tier");
    const auto eight_mib = render::estimate_point_memory(8'000'000U);
    check(eight_mib.bytes_single == 384'000'000U, "8M single VBO memory is calculated correctly");

    const auto seed = world::mix_seed(0xA11D0A1ULL, {0, 0, 0}, 2);
    const auto level = world::LiminalLevel::make_pivot2_demo(seed);
    check(level.areas().size() == 5U, "demo level contains five connected zones");
    check(level.walls().size() >= 20U, "demo level provides analytical wall segments");
    check(level.obstacles().size() == 3U, "demo level provides solid interior obstacles");
    check(level.can_occupy(level.spawn_position().x, level.spawn_position().z, 0.34F),
          "spawn point is occupiable");
    check(level.can_occupy(0.0F, -4.0F, 0.34F), "north corridor opening is traversable");
    check(level.can_occupy(14.0F, -22.5F, 0.34F), "Window Hall is traversable");
    check(!level.can_occupy(-7.9F, 5.0F, 0.34F), "outer reception wall blocks the player capsule");
    check(!level.can_occupy(-3.5F, -24.8F, 0.34F), "support obstacle blocks the player capsule");
    check(level.zone_name({24.0F, 1.72F, -22.0F}) == "Deep Room", "zone lookup identifies Deep Room");

    world::PlayerController player(level.spawn_position());
    world::PlayerMoveInput jump;
    jump.jump_pressed = true;
    player.update(jump, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
    check(!player.grounded() && player.position().y > level.spawn_position().y,
          "grounded player can jump");
    for (int i = 0; i < 240; ++i) {
        player.update({}, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
    }
    check(player.grounded() && std::abs(player.position().y - level.spawn_position().y) < 0.001F,
          "gravity returns the player to the floor");

    player.reset(level.spawn_position());
    world::PlayerMoveInput left;
    left.right = -1.0F;
    for (int i = 0; i < 300; ++i) {
        player.update(left, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
    }
    check(player.position().x > -7.8F, "collision sliding prevents walking through the west wall");

    const auto cloud = render::PointCloud::make_liminal_level(level, {250'000U, seed});
    check(cloud.points().size() == 250'000U, "multi-zone point cloud generates exact count");
    check(cloud.finite(), "multi-zone point cloud contains finite data");
    check(cloud.stats().wall_points > cloud.stats().floor_points,
          "multi-zone cloud allocates the largest share to walls and obstacles");

    const auto renderer_config = data::UDataDocument::load(root / "config/renderer.udata");
    const auto movement_config = data::UDataDocument::load(root / "config/movement.udata");
    check(!renderer_config.has_errors(), "Pivot 2 renderer config loads");
    check(!movement_config.has_errors(), "Pivot 2 movement config loads");
    check(renderer_config.value("body", "adaptive_gameplay_budget").has_value(),
          "renderer config declares adaptive gameplay budget");
    check(movement_config.value("body", "jump_velocity").has_value(),
          "movement config declares jump velocity");

    if (failures == 0) {
        std::cout << "All SignalCloud Pivot 2 Liminal Slice tests passed.\n";
        return 0;
    }
    return 1;
}
