#include "engine/combat/combat_system.hpp"
#include "engine/economy/economy_system.hpp"
#include "engine/render/adaptive_budget.hpp"
#include "engine/render/adaptive_residency.hpp"
#include "engine/render/point_cloud.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/player_controller.hpp"
#include "engine/world/recovery_system.hpp"
#include "engine/world/threat_director.hpp"
#include "engine/world/world_seed.hpp"

#include <cmath>
#include <cstdint>
#include <iostream>
#include <string_view>

namespace {
int failures = 0;
void check(bool condition, std::string_view label) {
    std::cout << (condition ? "PASS: " : "FAIL: ") << label << '\n';
    if (!condition) ++failures;
}
const signalcloud::world::WalkArea* find_area(const signalcloud::world::LiminalLevel& level,
                                               std::string_view name) {
    for (const auto& area : level.areas()) if (area.name == name) return &area;
    return nullptr;
}
}

int main() {
    using namespace signalcloud;
    const auto seed = world::mix_seed(0xA12D0A1ULL, {13, 0, 0}, 4);
    const auto level = world::LiminalLevel::make_pivot11_scavenging(seed);

    const auto intel = render::recommend_point_budget("Intel", "Mesa Intel UHD Graphics", 4, 6);
    check(intel.gameplay_points == 8'000'000U,
          "verified Intel/Mesa profile starts at the 8M resident tier");

    auto combat = combat::CombatSystem::make_pivot10();
    auto director = world::ThreatDirector::make_pivot13(level);
    const auto* hall = find_area(level, "Long Signal Hall");
    check(hall != nullptr, "Long Signal Hall exists for world-threat testing");
    if (hall != nullptr) {
        math::Vec3 player{(hall->min_x + hall->max_x) * 0.5F,
                          level.ground_height_at((hall->min_x + hall->max_x) * 0.5F,
                                                 (hall->min_z + hall->max_z) * 0.5F),
                          (hall->min_z + hall->max_z) * 0.5F};
        for (int i = 0; i < 70; ++i) {
            (void)director.update(0.1F, level, combat, player, "Long Signal Hall", false);
        }
        check(combat.world_entity_count() >= 1U,
              "threat director forms a managed enemy after room-entry grace");
        check(combat.living_in_zone("Long Signal Hall") >= 1U,
              "world threat is assigned to the active ordinary room");
        const auto protected_before = combat.world_entity_count();
        for (int i = 0; i < 80; ++i) {
            (void)director.update(0.1F, level, combat, level.spawn_position(),
                                  "Reception Tape", false);
        }
        check(combat.world_entity_count() <= protected_before,
              "protected room does not create new world threats");
    }
    check(world::zone_is_protected("Reception Tape"), "Reception Tape remains protected");
    check(world::zone_is_protected("Scavenger Exchange"), "Scavenger Exchange remains protected");
    check(!world::zone_is_protected("Long Signal Hall"), "ordinary traversal rooms remain threat-enabled");

    world::PlayerController player_controller(level.spawn_position());
    auto economy = economy::EconomySystem::make_pivot12();
    world::RecoverySystem recovery;
    player_controller.apply_damage(150.0F, world::DamageCause::combat);
    auto event = recovery.update(0.016F, player_controller, level, economy, combat,
                                 "Long Signal Hall");
    check(event.death_started, "zero health starts the recovery handshake");
    check(recovery.controls_locked(), "controls lock during blackout");
    check(recovery.cause() == world::DamageCause::combat, "death cause remains available to the AR mask");
    bool respawned = false;
    for (int i = 0; i < 30; ++i) {
        event = recovery.update(0.1F, player_controller, level, economy, combat,
                                "Long Signal Hall");
        respawned = respawned || event.respawned;
    }
    check(respawned, "recovery handshake respawns after the blackout interval");
    check(player_controller.health() > 0.0F, "recovered player returns with playable health");
    check(std::abs(player_controller.position().x - level.spawn_position().x) < 0.01F,
          "recovery returns to Reception Tape spawn");

    render::AdaptiveResidencyController residency(8'000'000U);
    bool premature_fallback = false;
    for (int i = 0; i < 90; ++i) {
        const auto decision = residency.update(0.1F, 30.0F, 31.0, false, false);
        premature_fallback = premature_fallback || decision.requested_points.has_value();
    }
    check(!premature_fallback, "8M fallback is never applied in a dangerous room");
    check(residency.fallback_pending(), "sustained pressure queues a deferred fallback");
    const auto fallback = residency.update(0.1F, 30.0F, 31.0, true, false);
    check(fallback.requested_points == 4'000'000U,
          "queued fallback applies at the first protected room");
    residency.record_loaded(4'000'000U);
    check(residency.current_points() == 4'000'000U,
          "adaptive controller records the loaded fallback tier");

    const auto cloud = render::PointCloud::make_liminal_level(level, {120'000U, seed});
    check(cloud.finite(), "point cloud remains finite after point-owner copy cleanup");
    check(cloud.points().size() >= 120'000U, "point cloud keeps the requested diagnostic population");

    return failures == 0 ? 0 : 1;
}
