#include "engine/combat/combat_system.hpp"
#include "engine/economy/economy_system.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/threat_navigation.hpp"
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
float distance_xz(signalcloud::math::Vec3 a, signalcloud::math::Vec3 b) {
    const float dx = a.x - b.x;
    const float dz = a.z - b.z;
    return std::sqrt(dx * dx + dz * dz);
}
const signalcloud::combat::CombatEntity* find_entity(
    const signalcloud::combat::CombatSystem& combat, std::uint64_t id) {
    for (const auto& entity : combat.entities()) if (entity.id == id) return &entity;
    return nullptr;
}
}

int main() {
    using namespace signalcloud;
    const auto seed = world::mix_seed(0xA12D0A2ULL, {13, 0, 2}, 5);
    const auto level = world::LiminalLevel::make_pivot11_scavenging(seed);

    world::ThreatNavigationRequest request;
    request.start = {644.6F, 0.0F, -163.0F};
    request.goal = {652.2F, 0.0F, -163.0F};
    request.zone = "Traversal & Water Lab";
    request.radius = 0.98F;
    request.body_height = 1.28F;
    request.step_height = 0.62F;
    request.grid_spacing = 0.72F;
    const auto route = world::plan_threat_route(level, request);
    check(route.reached_goal_cell, "A* threat route reaches the far side of a tall floor box");
    check(!route.waypoints.empty(), "obstacle route contains usable waypoints");
    bool route_valid = true;
    math::Vec3 previous = request.start;
    for (const auto& waypoint : route.waypoints) {
        route_valid = route_valid && world::threat_position_is_valid(
            level, waypoint, request.zone, request.radius,
            request.body_height, request.step_height, true);
        route_valid = route_valid && world::threat_motion_line_clear(
            level, previous, waypoint, request.zone, request.radius,
            request.body_height, request.step_height, true);
        previous = waypoint;
    }
    check(route_valid, "planned threat route never crosses walls or solid boxes");

    auto combat = combat::CombatSystem::make_pivot10();
    const auto dog_id = combat.spawn_world_entity(
        combat::CreatureKind::hash_dog, request.start, request.zone, 18.0F, 18.0F);
    combat.emit_noise(request.goal, 2.0F, request.zone);
    bool dog_valid = true;
    for (int i = 0; i < 240; ++i) {
        (void)combat.update(0.05F, request.goal + math::Vec3{0.0F, 1.72F, 0.0F},
                            request.zone, &level);
        const auto* dog = find_entity(combat, dog_id);
        if (dog == nullptr) { dog_valid = false; break; }
        dog_valid = dog_valid && world::threat_position_is_valid(
            level, dog->position, request.zone, dog->radius * 0.86F,
            1.28F, 0.62F, true);
    }
    const auto* routed_dog = find_entity(combat, dog_id);
    check(dog_valid, "Hash Dog remains outside static geometry throughout pursuit");
    check(routed_dog != nullptr && routed_dog->position.x > 650.0F,
          "Hash Dog routes around the box instead of locking to its first face");


    auto recovery_from_geometry = combat::CombatSystem::make_pivot10();
    const math::Vec3 embedded_spawn{628.2F, 0.0F, -168.5F};
    check(!world::threat_position_is_valid(level, embedded_spawn, request.zone,
                                           0.98F, 1.28F, 0.62F, true),
          "fixture spawn begins inside the authored wall collision margin");
    const auto embedded_id = recovery_from_geometry.spawn_world_entity(
        combat::CreatureKind::hash_dog, embedded_spawn, request.zone, 18.0F, 18.0F);
    (void)recovery_from_geometry.update(0.016F, request.start + math::Vec3{0.0F, 1.72F, 0.0F},
                                        request.zone, &level);
    const auto* recovered_dog = find_entity(recovery_from_geometry, embedded_id);
    check(recovered_dog != nullptr && world::threat_position_is_valid(
              level, recovered_dog->position, request.zone, recovered_dog->radius * 0.86F,
              1.28F, 0.62F, true),
          "embedded world threat recovers to a valid surface instead of de-spawning through geometry");

    auto dodge_collision = combat::CombatSystem::make_pivot10();
    const auto dodge_id = dodge_collision.spawn_world_entity(
        combat::CreatureKind::hash_dog, {644.8F, 0.0F, -162.0F},
        request.zone, 18.0F, 18.0F);
    const math::Vec3 shot_origin{642.6F, 1.05F, -162.0F};
    const math::Vec3 shot_direction{1.0F, 0.0F, 0.0F};
    (void)dodge_collision.fire_primary(shot_origin, shot_direction, 1, true, request.zone);
    (void)dodge_collision.update(0.25F, request.goal + math::Vec3{0.0F, 1.72F, 0.0F},
                                  request.zone, &level);
    (void)dodge_collision.fire_primary(shot_origin, shot_direction, 1, true, request.zone);
    bool dodge_valid = true;
    for (int i = 0; i < 24; ++i) {
        (void)dodge_collision.update(0.05F, request.goal + math::Vec3{0.0F, 1.72F, 0.0F},
                                      request.zone, &level);
        const auto* dodger = find_entity(dodge_collision, dodge_id);
        if (dodger == nullptr) { dodge_valid = false; break; }
        dodge_valid = dodge_valid && world::threat_position_is_valid(
            level, dodger->position, request.zone, dodger->radius * 0.86F,
            1.28F, 0.62F, true);
    }
    check(dodge_valid, "formed dodge movement cannot evade through the nearby box or wall");

    auto memory = combat::CombatSystem::make_pivot10();
    const auto memory_id = memory.spawn_world_entity(
        combat::CreatureKind::hash_dog, request.start, request.zone, 18.0F, 18.0F);
    memory.emit_noise(request.goal, 2.0F, request.zone);
    for (int i = 0; i < 240; ++i) {
        (void)memory.update(0.05F, {900.0F, 1.72F, -400.0F}, request.zone, &level);
    }
    const auto* memory_dog = find_entity(memory, memory_id);
    check(memory_dog != nullptr && memory_dog->memory_seconds <= 0.001F &&
          memory_dog->state != combat::CreatureState::hunt &&
          memory_dog->state != combat::CreatureState::attack,
          "last-seen pursuit expires instead of pinning an abandoned player coordinate forever");

    auto crowd = combat::CombatSystem::make_pivot10();
    const auto dog_a = crowd.spawn_world_entity(combat::CreatureKind::hash_dog,
        {688.0F, 0.0F, -166.0F}, "Corridor Junction", 10.0F, 10.0F);
    const auto dog_b = crowd.spawn_world_entity(combat::CreatureKind::hash_dog,
        {688.2F, 0.0F, -166.1F}, "Corridor Junction", 10.0F, 10.0F);
    crowd.emit_noise({702.0F, 0.0F, -166.0F}, 2.0F, "Corridor Junction");
    for (int i = 0; i < 80; ++i) {
        (void)crowd.update(0.05F, {702.0F, 1.72F, -166.0F},
                           "Corridor Junction", &level);
    }
    const auto* a = find_entity(crowd, dog_a);
    const auto* b = find_entity(crowd, dog_b);
    check(a != nullptr && b != nullptr && distance_xz(a->position, b->position) > 1.20F,
          "formed creatures separate instead of deadlocking into one collision body");

    auto pursuit = combat::CombatSystem::make_pivot10();
    const auto pursuing_id = pursuit.spawn_world_entity(combat::CreatureKind::hash_dog,
        {482.0F, 0.0F, -150.0F}, "Service Loop", 10.0F, 10.0F);
    pursuit.emit_noise({487.0F, 0.0F, -150.0F}, 2.0F, "Service Loop");
    (void)pursuit.update(0.10F, {487.0F, 1.72F, -150.0F}, "Service Loop", &level);
    const auto migrated = pursuit.migrate_pursuing_world_entities(
        "Service Loop", "Almond Concourse", {322.0F, 0.0F, -150.0F},
        12.0F, 12.0F, 1U);
    const auto* migrated_dog = find_entity(pursuit, pursuing_id);
    check(migrated == 1U && migrated_dog != nullptr &&
          migrated_dog->zone == "Almond Concourse",
          "alert world threat deterministically follows a connected room transition");

    auto water_combat = combat::CombatSystem::make_pivot10();
    const auto water_dog = water_combat.spawn_world_entity(
        combat::CreatureKind::hash_dog, {835.0F, 0.0F, -164.0F},
        "Submerged Service Tunnel", 20.0F, 4.0F);
    float underwater_damage = 0.0F;
    for (int i = 0; i < 80; ++i) {
        const auto update = water_combat.update(
            0.05F, {835.4F, -3.4F, -164.0F},
            "Submerged Service Tunnel", &level);
        underwater_damage += update.player_damage;
    }
    const auto* swimming_dog = find_entity(water_combat, water_dog);
    check(swimming_dog != nullptr && swimming_dog->swimming,
          "Hash Dog uses a water-surface movement state in flooded rooms");
    check(underwater_damage == 0.0F,
          "surface Hash Dog cannot bite a deeply submerged player without contact");

    auto economy = economy::EconomySystem::make_pivot12();
    const auto ammo = economy.interact({1073.0F, 1.72F, -169.82F},
                                       "Scavenger Exchange", 1);
    check(ammo.success && ammo.ammo_added == 18 && ammo.xar_delta == -5,
          "Ammo Tablet buys a direct 18-round reserve transfer for 5 XAR");
    check(economy.quantity(economy::ItemKind::ammo_pack) == 0U,
          "Ammo Tablet bypasses weighted inventory and cannot be blocked by carry capacity");

    check(combat.entity_position_is_finite() && crowd.entity_position_is_finite() &&
          water_combat.entity_position_is_finite(),
          "navigation, separation, and swimming retain finite entity transforms");
    return failures == 0 ? 0 : 1;
}
