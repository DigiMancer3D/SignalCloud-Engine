#include "engine/data/udata.hpp"
#include "engine/render/adaptive_budget.hpp"
#include "engine/render/local_siren.hpp"
#include "engine/render/point_cloud.hpp"
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

    const auto seed = world::mix_seed(0xA11D0A1ULL, {0, 0, 0}, 4);
    const auto level = world::LiminalLevel::make_pivot5_traversal(seed);
    check(level.areas().size() == 13U, "Pivot 5 adds a deterministic thirteenth traversal room");
    check(level.water_regions().size() == 2U, "lab exposes shallow and deep water regions");
    check(level.portals().size() >= 17U, "portal graph includes lab entrance and return gates");
    check(level.zone_name(level.traversal_lab_spawn()) == "Traversal & Water Lab", "lab spawn resolves to the lab zone");

    const auto* green = level.obstacle_at(631.5F, -162.5F);
    const auto* cyan = level.obstacle_at(636.5F, -162.5F);
    const auto* amber = level.obstacle_at(641.5F, -162.5F);
    const auto* red = level.obstacle_at(648.0F, -162.5F);
    check(green && std::abs(green->height - 0.25F) < 0.001F, "green step height is 0.25m");
    check(cyan && std::abs(cyan->height - 0.55F) < 0.001F, "cyan jump box height is 0.55m");
    check(amber && std::abs(amber->height - 0.90F) < 0.001F, "amber running-jump box height is 0.90m");
    check(red && std::abs(red->height - 1.35F) < 0.001F, "red block marks the current mantle limit");
    check(level.ground_height_at(631.5F, -162.5F) == 0.25F, "platform top becomes analytical ground");
    check(level.water_at(633.0F, -138.0F) != nullptr, "shallow water query succeeds");
    check(level.water_at(648.0F, -138.0F) != nullptr, "deep water query succeeds");
    check(level.ground_height_at(648.0F, -138.0F) < -2.0F, "deep pool uses a sunken floor");

    world::PlayerController player(level.traversal_lab_spawn());
    world::PlayerMoveInput idle;
    player.update(idle, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
    check(player.water_state() == world::WaterState::dry, "lab spawn begins dry");
    player.teleport({633.0F, 0.65F, -138.0F});
    for (int i = 0; i < 60; ++i) player.update(idle, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
    check(player.water_state() != world::WaterState::dry, "player enters water physics state");
    player.teleport({648.0F, 0.40F, -138.0F});
    world::PlayerMoveInput swim;
    swim.jump_pressed = true;
    player.update(swim, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
    check(player.water_state() == world::WaterState::swimming, "deep pool activates swimming");

    render::LocalSirenSource siren;
    siren.toggle();
    const auto& lab = level.areas().back();
    for (int i = 0; i < 30; ++i) siren.update(1.0 / 60.0, lab);
    check(siren.active() && siren.intensity() > 0.0F, "moving local siren produces a pulse");
    check(siren.effect_at(siren.position()) > 0.0F, "local siren affects points at its center");
    check(siren.effect_at({0.0F, 0.0F, 0.0F}) == 0.0F, "local siren is range-limited");

    const auto cloud = render::PointCloud::make_liminal_level(level, {300'000U, seed});
    check(cloud.points().size() == 300'000U && cloud.finite(), "water-aware point cloud keeps exact finite count");
    check(cloud.ranges().size() == level.areas().size(), "room streaming includes the traversal lab range");
    bool has_water_marker = false;
    for (const auto& point : cloud.points()) {
        if (point.density < 0.0F) { has_water_marker = true; break; }
    }
    check(has_water_marker, "water and reflection points use the negative-density shader marker");

    const auto intel = render::recommend_point_budget("Intel", "Mesa Intel UHD", 4, 6);
    check(intel.gameplay_points >= 3'000'000U, "accepted streamed Intel/Mesa default remains at or above the Pivot 5 3M floor");

    const auto traversal_config = data::UDataDocument::load(root / "config/traversal.udata");
    const auto siren_config = data::UDataDocument::load(root / "config/sirens.udata");
    check(!traversal_config.has_errors(), "Pivot 5 traversal config loads");
    check(!siren_config.has_errors(), "Pivot 5 siren config loads");

    if (failures == 0) {
        std::cout << "All SignalCloud Pivot 5 Traversal & Water Lab tests passed.\n";
        return 0;
    }
    return 1;
}
