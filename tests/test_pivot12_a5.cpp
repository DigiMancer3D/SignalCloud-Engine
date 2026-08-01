#include "engine/combat/combat_system.hpp"
#include "engine/economy/economy_system.hpp"
#include "engine/ui/tactical_memory_map.hpp"
#include "engine/world/liminal_level.hpp"

#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <set>
#include <string>
#include <string_view>
#include <tuple>

namespace {
int failures = 0;

void check(bool condition, std::string_view message) {
    if (!condition) {
        ++failures;
        std::cerr << "FAIL: " << message << '\n';
    }
}

bool finite_points(const std::vector<signalcloud::render::PointGpu>& points) {
    if (points.empty()) return false;
    for (const auto& point : points) {
        for (float value : point.position) if (!std::isfinite(value)) return false;
        if (!std::isfinite(point.radius) || point.radius <= 0.0F) return false;
    }
    return true;
}
}  // namespace

int main() {
    using namespace signalcloud;

    auto level = world::LiminalLevel::make_pivot11_scavenging(0xCE4E7BA015301C88ULL);
    combat::CombatSystem combat = combat::CombatSystem::make_pivot10();
    economy::EconomySystem economy = economy::EconomySystem::make_pivot12();

    const auto test_root = std::filesystem::temp_directory_path() /
        "signalcloud_pivot12_a5_tmap_test";
    std::error_code ec;
    std::filesystem::remove_all(test_root, ec);

    ui::TacticalMemoryMap map;
    map.set_storage_root(test_root);
    const std::string start(level.zone_name(level.spawn_position()));
    map.reset(level, start);

    const auto first = map.build_points(level, level.spawn_position(),
                                        {0.0F, 0.0F, -1.0F},
                                        start, combat, economy, 0.0F);
    check(finite_points(first), "JAM atlas points are finite");
    check(first.size() < 16'000U, "JAM atlas stays below the 16K preferred cap");
    check(map.node_snapshot(start).has_value(), "starting room receives a topology node");
    const int north_side = map.facing_side(start, {0.0F, 0.0F, -1.0F});
    const int east_side = map.facing_side(start, {1.0F, 0.0F, 0.0F});
    check(north_side != east_side, "player arrow distinguishes different facing directions");

    check(map.observe_scan(level, start), "scanner discovers adjacent topology nodes");
    const auto scanned = map.build_points(level, level.spawn_position(),
                                          {1.0F, 0.0F, 0.0F},
                                          start, combat, economy, 1.0F);
    check(finite_points(scanned), "scanned topology remains finite");
    check(map.stats().scanned_rooms >= 5U,
          "Reception scan remembers its multiple adjacent rooms");
    check(map.threshold_count(start) >= 5U,
          "multi-threshold Reception Tape preserves its separate exits");
    check(map.stats().topology_nodes == map.stats().visited_rooms + map.stats().scanned_rooms,
          "known rooms map one-to-one to topology nodes");
    check(map.stats().threshold_slots >= map.stats().remembered_connections * 2U,
          "connections are represented by endpoint threshold slots, not center lines");

    std::set<std::tuple<int, int, int>> occupied;
    for (const auto& area : level.areas()) {
        const auto snapshot = map.node_snapshot(area.name);
        if (!snapshot.has_value()) continue;
        check(occupied.insert({snapshot->grid_x, snapshot->grid_z,
                               snapshot->logical_level}).second,
              "known octagons never occupy the same logical coordinate");
    }

    map.observe_zone(level, "Service Loop");
    map.observe_scan(level, "Service Loop");
    const auto service_points = map.build_points(
        level, {480.0F, 1.72F, -150.0F},
        {0.0F, 0.0F, -1.0F}, "Service Loop",
        combat, economy, 2.0F);
    check(finite_points(service_points), "drop-expanded atlas remains finite");
    const auto service = map.node_snapshot("Service Loop");
    const auto concourse = map.node_snapshot("Almond Concourse");
    check(service.has_value() && concourse.has_value(),
          "drop scan creates both endpoint nodes");
    if (service.has_value() && concourse.has_value()) {
        check(concourse->logical_level == service->logical_level - 1,
              "JAM diagonal drop moves one logical level downward");
        check(concourse->grid_x != service->grid_x &&
              concourse->grid_z != service->grid_z,
              "level-changing connection uses a diagonal placement");
    }

    for (const auto& area : level.areas()) map.observe_zone(level, area.name);
    const auto full_atlas = map.build_points(
        level, level.spawn_position(), {0.0F, 0.0F, -1.0F},
        start, combat, economy, 2.5F);
    check(finite_points(full_atlas), "complete authored atlas remains finite");
    check(full_atlas.size() < 16'000U,
          "complete 26-room atlas remains below the 16K cap");
    check(map.stats().topology_nodes == level.areas().size(),
          "complete authored room set maps to one octagon per room");
    check(map.stats().logical_levels >= 2U,
          "complete atlas retains at least the base and lower drop levels");

    check(!map.memory_path().empty() && std::filesystem::exists(map.memory_path()),
          "event-driven atlas writes its simplified .tmap memory");
    const auto saved_path = map.memory_path();
    const auto saved_nodes = map.stats().topology_nodes;

    ui::TacticalMemoryMap reloaded;
    reloaded.set_storage_root(test_root);
    reloaded.reset(level, start);
    const auto restored = reloaded.build_points(level, level.spawn_position(),
                                                {0.0F, 0.0F, -1.0F},
                                                start, combat, economy, 3.0F);
    check(finite_points(restored), "reloaded .tmap renders finite points");
    check(reloaded.stats().memory_loads == 1U,
          "matching seed/layout restores tactical memory");
    check(reloaded.stats().topology_nodes >= saved_nodes,
          "restored tactical memory does not retract known rooms");
    check(reloaded.memory_path() == saved_path,
          "seed and layout signature select a stable .tmap path");

    const auto rebuilds = reloaded.stats().static_rebuilds;
    const auto facing_refresh = reloaded.build_points(
        level, level.spawn_position(), {0.0F, 0.0F, 1.0F},
        start, combat, economy, 4.0F);
    check(finite_points(facing_refresh), "facing-only refresh remains finite");
    check(reloaded.stats().static_rebuilds == rebuilds,
          "moving/facing updates do not rebuild static atlas geometry");

    const auto matrix = reloaded.view_projection(16.0F / 9.0F, level);
    for (float value : matrix.m) check(std::isfinite(value), "atlas projection remains finite");

    std::filesystem::remove_all(test_root, ec);

    if (failures != 0) {
        std::cerr << failures << " Pivot 12 a5 checks failed.\n";
        return EXIT_FAILURE;
    }
    std::cout << "All SignalCloud Pivot 12 a5 JAM topology-atlas checks passed.\n";
    return EXIT_SUCCESS;
}
