#include "engine/combat/combat_system.hpp"
#include "engine/economy/economy_system.hpp"
#include "engine/ui/tactical_memory_map.hpp"
#include "engine/world/liminal_level.hpp"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>
#include <string_view>

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

    auto level = world::LiminalLevel::make_pivot11_scavenging(0xA12A4ULL);
    combat::CombatSystem combat = combat::CombatSystem::make_pivot10();
    economy::EconomySystem economy = economy::EconomySystem::make_pivot12();
    ui::TacticalMemoryMap map;

    const std::string start(level.zone_name(level.spawn_position()));
    map.reset(level, start);
    check(map.visited_zone(start), "starting room is remembered immediately");
    check(map.stats().visited_rooms == 0U,
          "statistics wait for the first compact-map rebuild");

    const auto first = map.build_points(level, level.spawn_position(), {0.0F, 0.0F, -1.0F},
                                        start, combat, economy, 0.0F);
    check(finite_points(first), "compact map points are finite");
    check(first.size() < 32'000U, "compact map remains below its 32K point budget");
    check(map.stats().visited_rooms == 1U, "first rebuild reports one visited room");
    const auto rebuilds = map.stats().static_rebuilds;

    const auto second = map.build_points(level, level.spawn_position(), {1.0F, 0.0F, 0.0F},
                                         start, combat, economy, 1.0F);
    check(finite_points(second), "player-arrow refresh remains finite");
    check(map.stats().static_rebuilds == rebuilds,
          "unchanged map knowledge does not rebuild static geometry every frame");

    check(map.observe_scan(level, start), "scanner discovers at least one adjacent room");
    const auto scanned = map.build_points(level, level.spawn_position(), {0.0F, 0.0F, -1.0F},
                                          start, combat, economy, 2.0F);
    check(map.stats().scanned_rooms > 0U, "scanner previews persist in tactical memory");
    check(scanned.size() < 32'000U, "scanned map stays inside compact point budget");

    std::string destination;
    for (const auto& portal : level.portals()) {
        if (portal.source_zone == start) {
            destination = portal.destination_zone;
            break;
        }
    }
    if (!destination.empty()) {
        map.observe_zone(level, destination);
        const auto visited = map.build_points(level, level.spawn_position(), {0.0F, 0.0F, -1.0F},
                                              destination, combat, economy, 3.0F);
        check(map.visited_zone(destination), "entered room becomes permanently visited");
        check(map.stats().visited_rooms >= 2U, "visited-room count grows monotonically");
        check(visited.size() >= first.size(), "remembered map does not retract after discovery");
    }

    const auto matrix = map.view_projection(16.0F / 9.0F, level);
    for (float value : matrix.m) check(std::isfinite(value), "map projection remains finite");

    if (failures != 0) {
        std::cerr << failures << " Pivot 12 a4 checks failed.\n";
        return EXIT_FAILURE;
    }
    std::cout << "All SignalCloud Pivot 12 a4 compact tactical-memory checks passed.\n";
    return EXIT_SUCCESS;
}
