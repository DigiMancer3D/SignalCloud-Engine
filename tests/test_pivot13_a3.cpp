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
    const auto seed = world::mix_seed(0xA13D0A3ULL, {13, 0, 3}, 7);
    const auto level = world::LiminalLevel::make_pivot11_scavenging(seed);

    const world::PortalGate* service_portal = nullptr;
    for (const auto& portal : level.portals()) {
        if (portal.source_zone == "Service Loop") {
            service_portal = &portal;
            break;
        }
    }
    check(service_portal != nullptr,
          "test layout exposes a Service Loop threshold");
    if (service_portal == nullptr) return 1;

    const auto source_threshold =
        service_portal->center + service_portal->inward_normal * 0.55F;
    auto destination_entry = service_portal->destination;
    destination_entry.y = level.ground_height_at(
        destination_entry.x, destination_entry.z);
    const auto destination_forward = math::normalize_or(
        {-service_portal->inward_normal.x, 0.0F,
         -service_portal->inward_normal.z},
        {-1.0F, 0.0F, 0.0F});
    const auto dog_start =
        source_threshold + service_portal->inward_normal * 2.25F;

    auto pursuit = combat::CombatSystem::make_pivot10();
    const auto dog_id = pursuit.spawn_world_entity(
        combat::CreatureKind::hash_dog, dog_start,
        service_portal->source_zone, 12.0F, 12.0F);
    pursuit.emit_noise(source_threshold, 2.0F, service_portal->source_zone);
    (void)pursuit.update(0.05F, source_threshold,
                         service_portal->source_zone, &level);

    const auto queued = pursuit.queue_threshold_pursuit(
        level, service_portal->source_zone,
        service_portal->destination_zone,
        source_threshold, destination_entry, destination_forward,
        14.0F, 14.0F, 3.0F, 1U);
    const auto* queued_dog = find_entity(pursuit, dog_id);
    check(queued == 1U && queued_dog != nullptr && queued_dog->threshold_pending,
          "alert Hash Dog queues a three-second threshold pursuit");
    check(queued_dog != nullptr &&
          queued_dog->zone == service_portal->source_zone,
          "queued pursuit does not teleport into the destination room immediately");

    const auto preview_points = pursuit.build_visual_points(
        0.4F, service_portal->destination_zone);
    check(preview_points.size() > 1400U,
          "destination preview exposes a recognizable pursuing creature silhouette");
    bool translucent_preview = false;
    for (const auto& point : preview_points) {
        if (point.color[3] < 0.80F && point.color[2] > point.color[0]) {
            translucent_preview = true;
            break;
        }
    }
    check(translucent_preview,
          "threshold silhouette is tinted and translucent instead of appearing fully arrived");

    std::uint32_t arrivals = 0U;
    for (int step = 0; step < 60 && arrivals == 0U; ++step) {
        const auto update = pursuit.update_threshold_pursuits(
            0.05F, level, service_portal->destination_zone);
        arrivals += update.arrived;
    }
    const auto* arrived_dog = find_entity(pursuit, dog_id);
    check(arrivals == 1U && arrived_dog != nullptr &&
          arrived_dog->zone == service_portal->destination_zone &&
          !arrived_dog->threshold_pending,
          "creature enters only after physically completing the threshold route");
    check(arrived_dog != nullptr && distance_xz(
          arrived_dog->position, destination_entry) < 2.5F,
          "completed pursuit emerges near the destination threshold");

    auto too_slow = combat::CombatSystem::make_pivot10();
    (void)too_slow.spawn_world_entity(combat::CreatureKind::hash_dog,
        dog_start, service_portal->source_zone, 12.0F, 12.0F);
    too_slow.emit_noise(source_threshold, 2.0F,
                        service_portal->source_zone);
    (void)too_slow.update(0.05F, source_threshold,
                          service_portal->source_zone, &level);
    const auto rejected = too_slow.queue_threshold_pursuit(
        level, service_portal->source_zone,
        service_portal->destination_zone,
        source_threshold, destination_entry, destination_forward,
        14.0F, 14.0F, 0.60F, 1U);
    check(rejected == 0U && too_slow.pending_threshold_count() == 0U,
          "enemy whose physical route exceeds the pursuit window remains behind");

    const auto level_sight = combat::perception_envelope(
        combat::CreatureKind::hash_dog, 20.0F, 31.0F,
        2.0F, 1.8F, 24.0F);
    const auto elevated_sight = combat::perception_envelope(
        combat::CreatureKind::hash_dog, 20.0F, 31.0F,
        4.2F, 1.0F, 45.0F);
    check(!level_sight.downward_advantage &&
          std::abs(level_sight.effective_sight_radius - 20.0F) < 0.01F,
          "ordinary same-level sight retains the accepted radius");
    check(elevated_sight.downward_advantage &&
          elevated_sight.effective_sight_radius > 27.0F,
          "creature elevated by half its body height gains downward sight distance");
    check(std::abs(elevated_sight.maximum_hearing_radius - 62.0F) < 0.01F &&
          elevated_sight.required_loudness > 0.30F,
          "elevated hearing reaches at most double distance and requires louder sound farther out");

    const bool blocked_line = world::threat_sensor_line_clear(
        level, {644.2F, 2.2F, -163.0F}, {652.4F, 0.8F, -163.0F}, true);
    check(!blocked_line,
          "downward sight extension still obeys authored wall and obstacle line-of-sight");

    auto economy = economy::EconomySystem::make_pivot12();
    const auto terminal_points = economy.build_visual_points(
        0.2F, "Scavenger Exchange", {1073.0F, 1.72F, -169.82F});
    std::size_t red_points = 0U;
    for (const auto& point : terminal_points) {
        const math::Vec3 position{point.position[0], point.position[1], point.position[2]};
        if (distance_xz(position, {1073.0F, 1.18F, -169.82F}) < 2.0F &&
            point.color[0] > 0.72F && point.color[0] > point.color[1] * 1.8F) {
            ++red_points;
        }
    }
    check(red_points > 200U,
          "Ammo Tablet carries a permanent red kiosk identity distinct from the other tablets");

    check(pursuit.entity_position_is_finite(),
          "threshold pursuit and preview preserve finite entity transforms");
    return failures == 0 ? 0 : 1;
}
