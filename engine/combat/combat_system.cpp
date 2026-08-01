#include "engine/combat/combat_system.hpp"

#include "engine/world/liminal_level.hpp"
#include "engine/world/threat_navigation.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>

namespace signalcloud::combat {
namespace {
constexpr std::string_view kCombatZone = "Live-Fire Signal Range";
constexpr float kPi = 3.14159265358979323846F;
constexpr float kDogSightCosine = 0.42F;

float distance_xz(math::Vec3 a, math::Vec3 b) noexcept {
    const float dx = a.x - b.x;
    const float dz = a.z - b.z;
    return std::sqrt(dx * dx + dz * dz);
}

math::Vec3 flat_direction(math::Vec3 from, math::Vec3 to,
                          math::Vec3 fallback = {1.0F, 0.0F, 0.0F}) noexcept {
    return math::normalize_or({to.x - from.x, 0.0F, to.z - from.z}, fallback);
}

math::Vec3 right_of(math::Vec3 forward) noexcept {
    forward = math::normalize_or({forward.x, 0.0F, forward.z}, {1.0F, 0.0F, 0.0F});
    return {-forward.z, 0.0F, forward.x};
}

math::Vec3 local_to_world(math::Vec3 origin, math::Vec3 forward,
                          math::Vec3 local) noexcept {
    forward = math::normalize_or({forward.x, 0.0F, forward.z}, {1.0F, 0.0F, 0.0F});
    const math::Vec3 right = right_of(forward);
    return origin + forward * local.x + math::Vec3{0.0F, local.y, 0.0F} + right * local.z;
}

math::Vec3 turn_toward(math::Vec3 current, math::Vec3 desired, float amount) noexcept {
    current = math::normalize_or({current.x, 0.0F, current.z}, {1.0F, 0.0F, 0.0F});
    desired = math::normalize_or({desired.x, 0.0F, desired.z}, current);
    return math::normalize_or(current * (1.0F - amount) + desired * amount, desired);
}

std::uint32_t hash32(std::uint64_t value) noexcept {
    value ^= value >> 33U;
    value *= 0xff51afd7ed558ccdULL;
    value ^= value >> 33U;
    value *= 0xc4ceb9fe1a85ec53ULL;
    value ^= value >> 33U;
    return static_cast<std::uint32_t>(value ^ (value >> 32U));
}

float unit_hash(std::uint64_t value) noexcept {
    return static_cast<float>(hash32(value) & 0x00FFFFFFU) /
           static_cast<float>(0x01000000U);
}

render::PointGpu point(math::Vec3 p, float radius, float r, float g, float b,
                       float alpha = 1.0F, float density = 1.0F) noexcept {
    return {{p.x, p.y, p.z}, radius, {r, g, b, alpha},
            {0.0F, 1.0F, 0.0F}, density};
}

void add_ellipsoid(std::vector<render::PointGpu>& out, math::Vec3 center,
                   math::Vec3 scale, std::uint32_t count, std::uint64_t seed,
                   float r, float g, float b, float radius) {
    out.reserve(out.size() + count);
    for (std::uint32_t i = 0; i < count; ++i) {
        const float u = unit_hash(seed + static_cast<std::uint64_t>(i) * 3U);
        const float v = unit_hash(seed + static_cast<std::uint64_t>(i) * 3U + 1U);
        const float shell = 0.74F + unit_hash(seed + static_cast<std::uint64_t>(i) * 3U + 2U) * 0.26F;
        const float theta = u * 2.0F * kPi;
        const float cos_phi = v * 2.0F - 1.0F;
        const float sin_phi = std::sqrt(std::max(0.0F, 1.0F - cos_phi * cos_phi));
        const math::Vec3 p{
            center.x + std::cos(theta) * sin_phi * scale.x * shell,
            center.y + cos_phi * scale.y * shell,
            center.z + std::sin(theta) * sin_phi * scale.z * shell,
        };
        const float variation = 0.82F + unit_hash(seed ^ (static_cast<std::uint64_t>(i) << 7U)) * 0.28F;
        out.push_back(point(p, radius * (0.78F + 0.46F * u),
                            std::clamp(r * variation, 0.0F, 1.0F),
                            std::clamp(g * variation, 0.0F, 1.0F),
                            std::clamp(b * variation, 0.0F, 1.0F), 0.96F, 1.0F));
    }
}

void add_oriented_ellipsoid(std::vector<render::PointGpu>& out, math::Vec3 origin,
                            math::Vec3 forward, math::Vec3 local_center,
                            math::Vec3 scale, std::uint32_t count, std::uint64_t seed,
                            float r, float g, float b, float radius) {
    out.reserve(out.size() + count);
    for (std::uint32_t i = 0; i < count; ++i) {
        const float u = unit_hash(seed + static_cast<std::uint64_t>(i) * 3U);
        const float v = unit_hash(seed + static_cast<std::uint64_t>(i) * 3U + 1U);
        const float shell = 0.72F + unit_hash(seed + static_cast<std::uint64_t>(i) * 3U + 2U) * 0.28F;
        const float theta = u * 2.0F * kPi;
        const float cos_phi = v * 2.0F - 1.0F;
        const float sin_phi = std::sqrt(std::max(0.0F, 1.0F - cos_phi * cos_phi));
        const math::Vec3 local{
            local_center.x + std::cos(theta) * sin_phi * scale.x * shell,
            local_center.y + cos_phi * scale.y * shell,
            local_center.z + std::sin(theta) * sin_phi * scale.z * shell,
        };
        const float variation = 0.84F + unit_hash(seed ^ (static_cast<std::uint64_t>(i) << 6U)) * 0.24F;
        out.push_back(point(local_to_world(origin, forward, local),
                            radius * (0.78F + 0.42F * u),
                            std::clamp(r * variation, 0.0F, 1.0F),
                            std::clamp(g * variation, 0.0F, 1.0F),
                            std::clamp(b * variation, 0.0F, 1.0F), 0.96F, 1.0F));
    }
}

void add_line(std::vector<render::PointGpu>& out, math::Vec3 a, math::Vec3 b,
              std::uint32_t count, float r, float g, float blue, float radius,
              float alpha = 0.94F) {
    if (count == 0U) return;
    for (std::uint32_t i = 0; i < count; ++i) {
        const float t = count == 1U ? 0.0F : static_cast<float>(i) / static_cast<float>(count - 1U);
        out.push_back(point(a + (b - a) * t, radius, r, g, blue, alpha, 1.0F));
    }
}

void add_joint(std::vector<render::PointGpu>& out, math::Vec3 position,
               std::uint64_t seed, float r, float g, float b) {
    add_ellipsoid(out, position, {0.11F, 0.11F, 0.11F}, 32U, seed, r, g, b, 0.035F);
}

void add_arc(std::vector<render::PointGpu>& out, math::Vec3 origin,
             math::Vec3 forward, float radius, float start_angle, float end_angle,
             std::uint32_t count, float height, float r, float g, float b,
             float point_radius) {
    const math::Vec3 right = right_of(forward);
    for (std::uint32_t i = 0; i < count; ++i) {
        const float t = count == 1U ? 0.0F : static_cast<float>(i) / static_cast<float>(count - 1U);
        const float angle = start_angle + (end_angle - start_angle) * t;
        const math::Vec3 direction = math::normalize_or(forward * std::cos(angle) + right * std::sin(angle));
        const math::Vec3 p = origin + direction * radius + math::Vec3{0.0F, height + std::sin(t * kPi) * 0.18F, 0.0F};
        out.push_back(point(p, point_radius, r, g, b, 0.94F - t * 0.34F, 1.0F));
    }

}

float creature_body_height(CreatureKind kind) noexcept {
    return kind == CreatureKind::hash_dog ? 1.28F : 0.82F;
}

float creature_step_height(CreatureKind kind) noexcept {
    return kind == CreatureKind::hash_dog ? 0.62F : 0.28F;
}

math::Vec3 rotate_xz(math::Vec3 direction, float radians) noexcept {
    const float cosine = std::cos(radians);
    const float sine = std::sin(radians);
    return math::normalize_or({direction.x * cosine - direction.z * sine,
                               0.0F,
                               direction.x * sine + direction.z * cosine}, direction);
}

void align_creature_to_surface(CombatEntity& entity,
                               const world::LiminalLevel& level) noexcept {
    if (const auto* water = level.water_at(entity.position.x, entity.position.z); water != nullptr) {
        entity.swimming = true;
        const float depth = std::max(0.0F, water->surface_y - water->bottom_y);
        entity.position.y = water->surface_y - std::min(0.38F, depth * 0.18F);
    } else {
        entity.swimming = false;
        entity.position.y = level.ground_height_at(entity.position.x, entity.position.z);
    }
}

bool separated_from_entities(const std::vector<CombatEntity>& entities,
                             const CombatEntity& self,
                             math::Vec3 candidate) noexcept {
    for (const auto& other : entities) {
        if (&other == &self || !other.alive || other.zone != self.zone) continue;
        const float minimum = (self.radius + other.radius) * 0.72F;
        if (distance_xz(candidate, other.position) < minimum) return false;
    }
    return true;
}

bool try_creature_move(CombatEntity& entity,
                       math::Vec3 desired_direction,
                       float movement,
                       float dt,
                       const world::LiminalLevel& level,
                       const std::vector<CombatEntity>& entities) noexcept {
    desired_direction = math::normalize_or({desired_direction.x, 0.0F, desired_direction.z},
                                           entity.forward);
    const float side_sign = (entity.id & 1U) == 0U ? 1.0F : -1.0F;
    const std::array<float, 11> angles{{
        0.0F,
        side_sign * 0.42F, -side_sign * 0.42F,
        side_sign * 0.82F, -side_sign * 0.82F,
        side_sign * 1.18F, -side_sign * 1.18F,
        side_sign * 1.57F, -side_sign * 1.57F,
        side_sign * 2.18F, 3.14159265359F,
    }};
    for (float angle : angles) {
        const math::Vec3 direction = rotate_xz(desired_direction, angle);
        math::Vec3 candidate = entity.position + direction * movement;
        if (!world::threat_position_is_valid(level, candidate, entity.zone,
                                             entity.radius * 0.86F,
                                             creature_body_height(entity.kind),
                                             creature_step_height(entity.kind), true)) continue;
        if (!separated_from_entities(entities, entity, candidate)) continue;
        entity.position = candidate;
        align_creature_to_surface(entity, level);
        entity.velocity = direction * (movement / std::max(0.0001F, dt));
        entity.forward = turn_toward(entity.forward, direction, 0.55F);
        entity.blocked_seconds = 0.0F;
        entity.stuck_seconds = std::max(0.0F, entity.stuck_seconds - dt * 2.0F);
        return true;
    }
    entity.velocity = {};
    entity.blocked_seconds += dt;
    entity.stuck_seconds += dt;
    return false;
}

void separate_creatures(std::vector<CombatEntity>& entities,
                        const world::LiminalLevel& level,
                        std::string_view active_zone) noexcept {
    for (std::size_t i = 0; i < entities.size(); ++i) {
        auto& a = entities[i];
        if (!a.alive || a.zone != active_zone) continue;
        for (std::size_t j = i + 1U; j < entities.size(); ++j) {
            auto& b = entities[j];
            if (!b.alive || b.zone != active_zone) continue;
            math::Vec3 delta{b.position.x - a.position.x, 0.0F, b.position.z - a.position.z};
            float distance = math::length(delta);
            const float required = (a.radius + b.radius) * 0.78F;
            if (distance >= required) continue;
            if (distance < 0.001F) {
                delta = (a.id & 1U) == 0U ? math::Vec3{1.0F, 0.0F, 0.0F}
                                           : math::Vec3{0.0F, 0.0F, 1.0F};
                distance = 1.0F;
            }
            const math::Vec3 normal = delta / distance;
            const float push = (required - distance) * 0.55F + 0.02F;
            const math::Vec3 a_candidate = a.position - normal * push;
            const math::Vec3 b_candidate = b.position + normal * push;
            if (world::threat_position_is_valid(level, a_candidate, a.zone,
                                                a.radius * 0.84F,
                                                creature_body_height(a.kind),
                                                creature_step_height(a.kind), true)) {
                a.position = a_candidate;
                align_creature_to_surface(a, level);
            }
            if (world::threat_position_is_valid(level, b_candidate, b.zone,
                                                b.radius * 0.84F,
                                                creature_body_height(b.kind),
                                                creature_step_height(b.kind), true)) {
                b.position = b_candidate;
                align_creature_to_surface(b, level);
            }
            a.repath_seconds = 0.0F;
            b.repath_seconds = 0.0F;
        }
    }
}

}  // namespace

std::string_view creature_kind_name(CreatureKind kind) noexcept {
    switch (kind) {
        case CreatureKind::hash_dog: return "HASH DOG";
        case CreatureKind::formless_shadow: return "FORMLESS SHADOW";
    }
    return "UNKNOWN";
}

std::string_view creature_state_name(CreatureState state) noexcept {
    switch (state) {
        case CreatureState::idle: return "IDLE";
        case CreatureState::investigate: return "INVESTIGATE";
        case CreatureState::hunt: return "HUNT";
        case CreatureState::attack: return "ATTACK";
        case CreatureState::dodge: return "DODGE";
        case CreatureState::dead: return "DEAD";
    }
    return "UNKNOWN";
}

std::string_view attack_visual_name(AttackVisualKind kind) noexcept {
    switch (kind) {
        case AttackVisualKind::none: return "NONE";
        case AttackVisualKind::claw_arc: return "CLAW ARC";
        case AttackVisualKind::shadow_lance: return "SHADOW LANCE";
    }
    return "UNKNOWN";
}

PerceptionEnvelope perception_envelope(
    CreatureKind kind, float base_sight_radius, float base_hearing_radius,
    float creature_sensor_y, float target_y, float noise_distance) noexcept {
    const float body_height = creature_body_height(kind);
    const float downward_difference = creature_sensor_y - target_y;
    const bool advantage = downward_difference >= body_height * 0.5F;
    const float extra = advantage
        ? std::clamp((downward_difference - body_height * 0.5F) /
                     std::max(0.25F, body_height * 2.0F), 0.0F, 1.0F)
        : 0.0F;

    PerceptionEnvelope result;
    result.downward_advantage = advantage;
    result.effective_sight_radius = base_sight_radius *
        (advantage ? 1.35F + extra * 0.30F : 1.0F);
    result.maximum_hearing_radius = base_hearing_radius *
        (advantage ? 2.0F : 1.0F);
    const float normalized_distance = std::clamp(
        noise_distance / std::max(0.1F, result.maximum_hearing_radius), 0.0F, 1.0F);
    result.required_loudness = advantage
        ? 0.30F + normalized_distance * 0.95F
        : std::max(0.35F, normalized_distance);
    return result;
}

CombatSystem CombatSystem::make_pivot9() {
    CombatSystem result;
    result.reset();
    return result;
}

CombatSystem CombatSystem::make_pivot10() {
    CombatSystem result;
    result.reset();
    return result;
}

void CombatSystem::reset() {
    entities_.clear();
    proofs_.clear();

    CombatEntity dog;
    dog.id = 1U;
    dog.kind = CreatureKind::hash_dog;
    dog.position = {1012.0F, 0.0F, -160.0F};
    dog.home = dog.position;
    dog.target = {1015.0F, 0.0F, -160.0F};
    dog.forward = {1.0F, 0.0F, 0.0F};
    dog.health = 100.0F;
    dog.maximum_health = 100.0F;
    dog.radius = 1.15F;
    dog.hearing_radius = 31.0F;
    dog.sight_radius = 20.0F;
    dog.attack_range = 1.75F;
    dog.zone = std::string(kCombatZone);
    dog.patrol_half_x = 22.0F;
    dog.patrol_half_z = 18.0F;
    dog.world_managed = false;
    entities_.push_back(dog);

    CombatEntity shadow;
    shadow.id = 2U;
    shadow.kind = CreatureKind::formless_shadow;
    shadow.position = {1002.0F, 0.0F, -151.0F};
    shadow.home = shadow.position;
    shadow.target = {1005.0F, 0.0F, -151.0F};
    shadow.forward = {0.0F, 0.0F, -1.0F};
    shadow.health = 135.0F;
    shadow.maximum_health = 135.0F;
    shadow.radius = 1.55F;
    shadow.hearing_radius = 38.0F;
    shadow.sight_radius = 24.0F;
    shadow.attack_range = 7.5F;
    shadow.zone = std::string(kCombatZone);
    shadow.patrol_half_x = 22.0F;
    shadow.patrol_half_z = 18.0F;
    shadow.world_managed = false;
    entities_.push_back(shadow);

    last_noise_position_ = {};
    last_noise_zone_.clear();
    last_noise_loudness_ = 0.0F;
    noise_seconds_ = 0.0F;
    fire_cooldown_ = 0.0F;
    reload_seconds_ = 0.0F;
    magazine_ = 12;
    reserve_ammo_ = 48;
    claimed_proofs_ = 0;
    kills_ = 0;
    next_proof_id_ = 1;
    next_entity_id_ = 3;
    tracer_seconds_ = 0.0F;
    melee_swing_seconds_ = 0.0F;
    attack_visual_kind_ = AttackVisualKind::none;
    attack_visual_seconds_ = 0.0F;
    last_hint_ = "Range quiet";
    last_world_visual_count_ = 0U;
    last_viewmodel_visual_count_ = 0U;
}

void CombatSystem::reset_wave() noexcept {
    const std::uint32_t previous_claims = claimed_proofs_;
    const std::uint32_t previous_kills = kills_;
    reset();
    claimed_proofs_ = previous_claims;
    kills_ = previous_kills;
    last_hint_ = "Signal range wave reset";
}


std::uint64_t CombatSystem::spawn_world_entity(CreatureKind kind, math::Vec3 position,
                                               std::string_view zone,
                                               float patrol_half_x,
                                               float patrol_half_z) {
    CombatEntity entity;
    entity.id = next_entity_id_++;
    entity.kind = kind;
    entity.position = position;
    entity.home = position;
    entity.target = position;
    entity.zone = std::string(zone);
    entity.world_managed = true;
    entity.last_seen_position = position;
    entity.route_goal = position;
    entity.patrol_half_x = std::max(2.0F, patrol_half_x);
    entity.patrol_half_z = std::max(2.0F, patrol_half_z);
    entity.forward = kind == CreatureKind::hash_dog
        ? math::Vec3{1.0F, 0.0F, 0.0F}
        : math::Vec3{0.0F, 0.0F, -1.0F};
    if (kind == CreatureKind::hash_dog) {
        entity.health = 100.0F;
        entity.maximum_health = 100.0F;
        entity.radius = 1.15F;
        entity.hearing_radius = 31.0F;
        entity.sight_radius = 20.0F;
        entity.attack_range = 1.75F;
    } else {
        entity.health = 135.0F;
        entity.maximum_health = 135.0F;
        entity.radius = 1.55F;
        entity.hearing_radius = 38.0F;
        entity.sight_radius = 24.0F;
        entity.attack_range = 7.5F;
    }
    entities_.push_back(std::move(entity));
    last_hint_ = "A world threat formed in the active room";
    return entities_.back().id;
}

std::uint32_t CombatSystem::despawn_world_entities(std::string_view zone) noexcept {
    const auto before = entities_.size();
    entities_.erase(std::remove_if(entities_.begin(), entities_.end(),
        [&](const CombatEntity& entity) {
            return entity.world_managed && entity.zone == zone;
        }), entities_.end());
    return static_cast<std::uint32_t>(before - entities_.size());
}

bool CombatSystem::migrate_one_world_entity(std::string_view source_zone,
                                            std::string_view destination_zone,
                                            math::Vec3 destination_home,
                                            float patrol_half_x,
                                            float patrol_half_z) noexcept {
    for (auto& entity : entities_) {
        if (!entity.world_managed || !entity.alive || entity.zone != source_zone) continue;
        entity.threshold_pending = false;
        entity.threshold_destination_zone.clear();
        entity.threshold_seconds = 0.0F;
        entity.threshold_total_seconds = 0.0F;
        entity.zone = std::string(destination_zone);
        entity.position = destination_home;
        entity.home = destination_home;
        entity.target = destination_home;
        entity.patrol_half_x = std::max(2.0F, patrol_half_x);
        entity.patrol_half_z = std::max(2.0F, patrol_half_z);
        entity.state = CreatureState::investigate;
        entity.alert_seconds = 4.5F;
        entity.memory_seconds = 5.5F;
        entity.last_seen_position = destination_home;
        entity.route_goal = destination_home;
        entity.route.clear();
        entity.route_index = 0U;
        entity.repath_seconds = 0.0F;
        entity.blocked_seconds = 0.0F;
        entity.stuck_seconds = 0.0F;
        entity.attack_cooldown = 0.75F;
        return true;
    }
    return false;
}

std::uint32_t CombatSystem::migrate_pursuing_world_entities(
    std::string_view source_zone, std::string_view destination_zone,
    math::Vec3 destination_home, float patrol_half_x, float patrol_half_z,
    std::uint32_t maximum_count) noexcept {
    std::uint32_t migrated = 0U;
    for (auto& entity : entities_) {
        if (migrated >= maximum_count) break;
        if (!entity.world_managed || !entity.alive || entity.zone != source_zone) continue;
        const bool pursuing = entity.state == CreatureState::hunt ||
                              entity.state == CreatureState::attack ||
                              entity.state == CreatureState::investigate ||
                              entity.memory_seconds > 0.0F || entity.alert_seconds > 0.0F;
        if (!pursuing) continue;
        entity.threshold_pending = false;
        entity.threshold_destination_zone.clear();
        entity.threshold_seconds = 0.0F;
        entity.threshold_total_seconds = 0.0F;
        entity.zone = std::string(destination_zone);
        entity.position = destination_home;
        entity.home = destination_home;
        entity.target = destination_home;
        entity.last_seen_position = destination_home;
        entity.route_goal = destination_home;
        entity.route.clear();
        entity.route_index = 0U;
        entity.patrol_half_x = std::max(2.0F, patrol_half_x);
        entity.patrol_half_z = std::max(2.0F, patrol_half_z);
        entity.state = CreatureState::investigate;
        entity.memory_seconds = 5.5F;
        entity.alert_seconds = 5.5F;
        entity.repath_seconds = 0.0F;
        entity.blocked_seconds = 0.0F;
        entity.stuck_seconds = 0.0F;
        entity.attack_cooldown = 0.85F + static_cast<float>(migrated) * 0.22F;
        ++migrated;
    }
    return migrated;
}


std::uint32_t CombatSystem::queue_threshold_pursuit(
    const world::LiminalLevel& level,
    std::string_view source_zone,
    std::string_view destination_zone,
    math::Vec3 source_threshold,
    math::Vec3 destination_entry,
    math::Vec3 destination_forward,
    float patrol_half_x,
    float patrol_half_z,
    float pursuit_window_seconds,
    std::uint32_t maximum_count) {
    std::uint32_t queued = 0U;
    const float window = std::clamp(pursuit_window_seconds, 0.5F, 6.0F);
    destination_forward = math::normalize_or(
        {destination_forward.x, 0.0F, destination_forward.z},
        {0.0F, 0.0F, -1.0F});

    for (auto& entity : entities_) {
        if (queued >= maximum_count) break;
        if (!entity.world_managed || !entity.alive || entity.zone != source_zone ||
            entity.threshold_pending) continue;
        const bool pursuing = entity.state == CreatureState::hunt ||
                              entity.state == CreatureState::attack ||
                              entity.state == CreatureState::investigate ||
                              entity.memory_seconds > 0.0F ||
                              entity.alert_seconds > 0.0F;
        if (!pursuing) continue;

        world::ThreatNavigationRequest request;
        request.start = entity.position;
        request.zone = entity.zone;
        request.radius = entity.radius * 0.86F;
        request.body_height = creature_body_height(entity.kind);
        request.step_height = creature_step_height(entity.kind);
        request.can_swim = true;
        // Portal trigger centers can sit inside the wall aperture reserve. Recover
        // a creature-specific, collision-valid waiting point on the source side
        // rather than treating the raw trigger center as navigable ground.
        const math::Vec3 navigable_threshold =
            world::nearest_valid_threat_position(
                level, source_threshold, entity.zone, request.radius,
                request.body_height, request.step_height, request.can_swim);
        request.goal = navigable_threshold;
        request.grid_spacing = entity.kind == CreatureKind::hash_dog ? 0.82F : 0.98F;
        const auto route = world::plan_threat_route(level, request);
        if (!route.reached_goal_cell && route.waypoints.empty()) continue;

        std::vector<math::Vec3> path = route.waypoints;
        if (path.empty() || distance_xz(path.back(), navigable_threshold) > 0.45F) {
            if (!world::threat_motion_line_clear(
                    level, path.empty() ? entity.position : path.back(),
                    navigable_threshold, entity.zone, request.radius,
                    request.body_height, request.step_height, request.can_swim)) {
                continue;
            }
            path.push_back(navigable_threshold);
        }

        float route_distance = 0.0F;
        math::Vec3 previous = entity.position;
        for (const auto& waypoint : path) {
            route_distance += distance_xz(previous, waypoint);
            previous = waypoint;
        }
        const float speed = entity.kind == CreatureKind::hash_dog ? 2.45F : 1.90F;
        const float estimated_seconds = route_distance / std::max(0.1F, speed);
        if (estimated_seconds > window + 0.001F) continue;

        entity.threshold_pending = true;
        entity.threshold_destination_zone = std::string(destination_zone);
        entity.threshold_destination = destination_entry;
        entity.threshold_preview_position = destination_entry + destination_forward * 1.55F;
        entity.threshold_preview_forward = destination_forward;
        entity.threshold_seconds = window;
        entity.threshold_total_seconds = window;
        entity.route = std::move(path);
        entity.route_index = 0U;
        entity.route_goal = navigable_threshold;
        entity.target = navigable_threshold;
        entity.state = CreatureState::investigate;
        entity.alert_seconds = std::max(entity.alert_seconds, window + 1.5F);
        entity.memory_seconds = std::max(entity.memory_seconds, window + 2.0F);
        entity.patrol_half_x = std::max(2.0F, patrol_half_x);
        entity.patrol_half_z = std::max(2.0F, patrol_half_z);
        entity.attack_cooldown = std::max(entity.attack_cooldown, 0.65F);
        ++queued;
    }
    return queued;
}

ThresholdPursuitUpdate CombatSystem::update_threshold_pursuits(
    float dt_seconds, const world::LiminalLevel& level,
    std::string_view player_zone) {
    ThresholdPursuitUpdate result;
    const float dt = std::clamp(dt_seconds, 0.0F, 0.10F);
    for (auto& entity : entities_) {
        if (!entity.alive || !entity.threshold_pending) continue;

        if (entity.zone == player_zone) {
            entity.threshold_pending = false;
            entity.threshold_destination_zone.clear();
            entity.threshold_seconds = 0.0F;
            entity.threshold_total_seconds = 0.0F;
            entity.route.clear();
            entity.route_index = 0U;
            entity.repath_seconds = 0.0F;
            entity.state = CreatureState::hunt;
            ++result.cancelled;
            continue;
        }

        entity.threshold_seconds = std::max(0.0F, entity.threshold_seconds - dt);
        float remaining_move = (entity.kind == CreatureKind::hash_dog ? 2.45F : 1.90F) * dt;
        while (remaining_move > 0.0001F && entity.route_index < entity.route.size()) {
            const math::Vec3 waypoint = entity.route[entity.route_index];
            const float distance = distance_xz(entity.position, waypoint);
            if (distance <= 0.08F) {
                entity.position = waypoint;
                ++entity.route_index;
                continue;
            }
            const math::Vec3 direction = flat_direction(entity.position, waypoint, entity.forward);
            const float movement = std::min(remaining_move, distance);
            const math::Vec3 candidate = entity.position + direction * movement;
            if (!world::threat_position_is_valid(
                    level, candidate, entity.zone, entity.radius * 0.86F,
                    creature_body_height(entity.kind), creature_step_height(entity.kind), true)) {
                entity.threshold_pending = false;
                entity.threshold_destination_zone.clear();
                entity.route.clear();
                entity.route_index = 0U;
                entity.state = CreatureState::investigate;
                entity.repath_seconds = 0.0F;
                ++result.expired;
                break;
            }
            entity.position = candidate;
            align_creature_to_surface(entity, level);
            entity.forward = turn_toward(entity.forward, direction, 0.62F);
            entity.velocity = direction * (movement / std::max(0.0001F, dt));
            entity.gait_phase += movement *
                (entity.kind == CreatureKind::hash_dog ? 5.4F : 2.8F);
            remaining_move -= movement;
            if (movement + 0.001F >= distance) ++entity.route_index;
        }
        if (!entity.threshold_pending) continue;

        const float progress = entity.threshold_total_seconds > 0.001F
            ? 1.0F - entity.threshold_seconds / entity.threshold_total_seconds
            : 1.0F;
        entity.threshold_preview_position = entity.threshold_destination +
            entity.threshold_preview_forward * (1.75F - progress * 1.35F);

        if (entity.route_index >= entity.route.size()) {
            entity.zone = entity.threshold_destination_zone;
            entity.position = world::nearest_valid_threat_position(
                level, entity.threshold_destination, entity.zone,
                entity.radius * 0.86F, creature_body_height(entity.kind),
                creature_step_height(entity.kind), true);
            entity.home = entity.position;
            entity.target = entity.position;
            entity.last_seen_position = entity.position;
            entity.forward = entity.threshold_preview_forward;
            entity.route.clear();
            entity.route_index = 0U;
            entity.route_goal = entity.position;
            entity.threshold_pending = false;
            entity.threshold_destination_zone.clear();
            entity.threshold_seconds = 0.0F;
            entity.threshold_total_seconds = 0.0F;
            entity.state = CreatureState::investigate;
            entity.memory_seconds = 5.5F;
            entity.alert_seconds = 5.5F;
            entity.repath_seconds = 0.0F;
            entity.blocked_seconds = 0.0F;
            entity.stuck_seconds = 0.0F;
            entity.attack_cooldown = std::max(entity.attack_cooldown, 0.75F);
            ++result.arrived;
        } else if (entity.threshold_seconds <= 0.0F) {
            entity.threshold_pending = false;
            entity.threshold_destination_zone.clear();
            entity.threshold_seconds = 0.0F;
            entity.threshold_total_seconds = 0.0F;
            entity.route.clear();
            entity.route_index = 0U;
            entity.state = CreatureState::investigate;
            entity.repath_seconds = 0.0F;
            ++result.expired;
        }
    }
    return result;
}

std::size_t CombatSystem::living_in_zone(std::string_view zone) const noexcept {
    return static_cast<std::size_t>(std::count_if(entities_.begin(), entities_.end(),
        [&](const CombatEntity& entity) { return entity.alive && entity.zone == zone; }));
}

std::size_t CombatSystem::world_entity_count() const noexcept {
    return static_cast<std::size_t>(std::count_if(entities_.begin(), entities_.end(),
        [](const CombatEntity& entity) { return entity.alive && entity.world_managed; }));
}

std::size_t CombatSystem::pending_threshold_count() const noexcept {
    return static_cast<std::size_t>(std::count_if(
        entities_.begin(), entities_.end(),
        [](const CombatEntity& entity) {
            return entity.alive && entity.world_managed && entity.threshold_pending;
        }));
}

bool CombatSystem::entity_position_is_finite() const noexcept {
    for (const auto& entity : entities_) {
        if (!std::isfinite(entity.position.x) || !std::isfinite(entity.position.y) ||
            !std::isfinite(entity.position.z) || !std::isfinite(entity.forward.x) ||
            !std::isfinite(entity.forward.z)) return false;
    }
    return true;
}

void CombatSystem::on_player_recovery_started() noexcept {
    tracer_seconds_ = 0.0F;
    melee_swing_seconds_ = 0.0F;
    attack_visual_seconds_ = 0.0F;
    attack_visual_kind_ = AttackVisualKind::none;
    noise_seconds_ = 0.0F;
    last_noise_loudness_ = 0.0F;
    for (auto& entity : entities_) {
        entity.attack_cooldown = std::max(entity.attack_cooldown, 2.0F);
        entity.threshold_pending = false;
        entity.threshold_destination_zone.clear();
        entity.threshold_seconds = 0.0F;
        entity.threshold_total_seconds = 0.0F;
        entity.route.clear();
        entity.route_index = 0U;
        if (entity.alive) entity.state = CreatureState::idle;
    }
}

void CombatSystem::on_player_recovered() noexcept {
    on_player_recovery_started();
    fire_cooldown_ = 0.65F;
    last_hint_ = "Threat signal reset after recovery";
}

void CombatSystem::update_timers(float dt_seconds) noexcept {
    const float dt = std::clamp(dt_seconds, 0.0F, 0.5F);
    fire_cooldown_ = std::max(0.0F, fire_cooldown_ - dt);
    reload_seconds_ = std::max(0.0F, reload_seconds_ - dt);
    tracer_seconds_ = std::max(0.0F, tracer_seconds_ - dt);
    melee_swing_seconds_ = std::max(0.0F, melee_swing_seconds_ - dt);
    attack_visual_seconds_ = std::max(0.0F, attack_visual_seconds_ - dt);
    if (attack_visual_seconds_ <= 0.0F) attack_visual_kind_ = AttackVisualKind::none;
    noise_seconds_ = std::max(0.0F, noise_seconds_ - dt);
    if (noise_seconds_ <= 0.0F) last_noise_loudness_ = 0.0F;
    for (auto& entity : entities_) {
        entity.attack_cooldown = std::max(0.0F, entity.attack_cooldown - dt);
        entity.alert_seconds = std::max(0.0F, entity.alert_seconds - dt);
        entity.dodge_cooldown = std::max(0.0F, entity.dodge_cooldown - dt);
        entity.dodge_seconds = std::max(0.0F, entity.dodge_seconds - dt);
        entity.deformation = std::max(0.0F, entity.deformation - dt * 2.8F);
        entity.memory_seconds = std::max(0.0F, entity.memory_seconds - dt);
        entity.repath_seconds = std::max(0.0F, entity.repath_seconds - dt);
        if (entity.state == CreatureState::dodge && entity.dodge_seconds <= 0.0F && entity.alive) {
            entity.state = entity.alert_seconds > 0.0F ? CreatureState::hunt : CreatureState::idle;
            entity.velocity = {};
        }
    }
}

void CombatSystem::emit_noise(math::Vec3 position, float loudness,
                              std::string_view source_zone) {
    if (loudness <= 0.0F) return;
    last_noise_position_ = position;
    last_noise_loudness_ = std::clamp(loudness, 0.0F, 2.0F);
    last_noise_zone_ = std::string(source_zone);
    noise_seconds_ = 2.8F + last_noise_loudness_ * 1.4F;
}

CombatUpdate CombatSystem::update(float dt_seconds, math::Vec3 player_position,
                                  std::string_view active_zone,
                                  const world::LiminalLevel* level) {
    update_timers(dt_seconds);
    CombatUpdate result;
    const float dt = std::clamp(dt_seconds, 0.0F, 0.05F);
    for (auto& entity : entities_) {
        if (!entity.alive || entity.zone != active_zone || entity.threshold_pending) continue;

        if (level != nullptr) {
            if (!world::threat_position_is_valid(*level, entity.position, entity.zone,
                                                 entity.radius * 0.86F,
                                                 creature_body_height(entity.kind),
                                                 creature_step_height(entity.kind), true)) {
                entity.position = world::nearest_valid_threat_position(
                    *level, entity.position, entity.zone, entity.radius * 0.86F,
                    creature_body_height(entity.kind), creature_step_height(entity.kind), true);
                entity.route.clear();
                entity.route_index = 0U;
                entity.repath_seconds = 0.0F;
                entity.blocked_seconds = 0.0F;
            }
            align_creature_to_surface(entity, *level);
        }

        if (entity.state == CreatureState::dodge && entity.dodge_seconds > 0.0F) {
            const float dodge_speed = math::length(entity.dodge_velocity);
            const math::Vec3 dodge_direction = math::normalize_or(entity.dodge_velocity, entity.forward);
            bool moved = false;
            if (level != nullptr) {
                moved = try_creature_move(entity, dodge_direction, dodge_speed * dt,
                                          dt, *level, entities_);
            } else {
                entity.position += entity.dodge_velocity * dt;
                entity.velocity = entity.dodge_velocity;
                moved = true;
            }
            entity.gait_phase += dt * 10.0F;
            if (!moved) {
                entity.dodge_seconds = 0.0F;
                entity.state = entity.memory_seconds > 0.0F
                    ? CreatureState::hunt : CreatureState::investigate;
                entity.repath_seconds = 0.0F;
            }
            continue;
        }

        const float player_distance = distance_xz(entity.position, player_position);
        const float player_body_y = player_position.y - 0.66F;
        const float creature_body_y = entity.position.y +
            (entity.kind == CreatureKind::hash_dog ? 0.70F : 0.48F);
        const float vertical_separation = std::abs(player_body_y - creature_body_y);
        const float noise_distance = distance_xz(entity.position, last_noise_position_);
        const float creature_sensor_y = entity.position.y +
            creature_body_height(entity.kind) * 0.72F;
        const auto player_perception = perception_envelope(
            entity.kind, entity.sight_radius, entity.hearing_radius,
            creature_sensor_y, player_body_y, noise_distance);
        const auto noise_perception = perception_envelope(
            entity.kind, entity.sight_radius, entity.hearing_radius,
            creature_sensor_y, last_noise_position_.y, noise_distance);
        const bool normal_hearing = noise_distance <=
            entity.hearing_radius * std::max(0.35F, last_noise_loudness_);
        const bool elevated_hearing = noise_perception.downward_advantage &&
            noise_distance <= noise_perception.maximum_hearing_radius &&
            last_noise_loudness_ >= noise_perception.required_loudness;
        const bool heard = noise_seconds_ > 0.0F && last_noise_zone_ == active_zone &&
                           (normal_hearing || elevated_hearing);
        const math::Vec3 to_player = flat_direction(entity.position, player_position, entity.forward);
        const float view_dot = math::dot(entity.forward, to_player);
        const float sight_cosine = entity.kind == CreatureKind::hash_dog ? kDogSightCosine : -0.10F;
        const bool visible_line = level == nullptr || world::threat_sensor_line_clear(
            *level, entity.position + math::Vec3{0.0F, 0.78F, 0.0F},
            player_position - math::Vec3{0.0F, 0.35F, 0.0F}, true);
        const bool saw = player_distance <= player_perception.effective_sight_radius &&
                         view_dot >= sight_cosine && visible_line;

        if (heard) {
            entity.target = last_noise_position_;
            entity.last_seen_position = last_noise_position_;
            entity.memory_seconds = std::max(entity.memory_seconds, 4.5F);
            entity.alert_seconds = std::max(entity.alert_seconds, 4.0F);
            if (entity.state == CreatureState::idle) entity.state = CreatureState::investigate;
            result.heard_noise = true;
        }
        if (saw) {
            entity.target = player_position;
            entity.last_seen_position = player_position;
            entity.memory_seconds = entity.kind == CreatureKind::hash_dog ? 5.8F : 7.2F;
            entity.state = CreatureState::hunt;
            entity.alert_seconds = std::max(entity.alert_seconds, 3.0F);
        } else if (!heard && entity.memory_seconds > 0.0F) {
            entity.target = entity.last_seen_position;
            if (entity.state != CreatureState::attack) entity.state = CreatureState::investigate;
        } else if (!heard && entity.memory_seconds <= 0.0F &&
                   (entity.state == CreatureState::hunt || entity.state == CreatureState::attack ||
                    entity.state == CreatureState::investigate)) {
            // The memory timer is the complete search contract. Once it expires,
            // never keep steering toward a stale coordinate merely because a wall
            // or glass enclosure prevented the creature from reaching it.
            entity.state = CreatureState::idle;
            entity.target = entity.home;
            entity.route.clear();
            entity.route_index = 0U;
            entity.repath_seconds = 0.0F;
            entity.blocked_seconds = 0.0F;
        }

        if (entity.state == CreatureState::idle) {
            const float orbit = entity.gait_phase * 0.22F + static_cast<float>(entity.id) * 1.7F;
            entity.target = {entity.home.x + std::cos(orbit) * 2.1F,
                             entity.home.y,
                             entity.home.z + std::sin(orbit) * 2.1F};
        }

        math::Vec3 navigation_target = entity.target;
        const float body_height = creature_body_height(entity.kind);
        const float step_height = creature_step_height(entity.kind);
        if (level != nullptr &&
            (entity.state == CreatureState::idle || entity.state == CreatureState::investigate ||
             entity.state == CreatureState::hunt)) {
            const bool direct_clear = world::threat_motion_line_clear(
                *level, entity.position, entity.target, entity.zone,
                entity.radius * 0.86F, body_height, step_height, true);
            if (direct_clear) {
                entity.route.clear();
                entity.route_index = 0U;
                navigation_target = entity.target;
            } else {
                const bool goal_changed = distance_xz(entity.route_goal, entity.target) > 1.15F;
                if (entity.repath_seconds <= 0.0F || entity.route.empty() || goal_changed ||
                    entity.blocked_seconds > 0.22F) {
                    world::ThreatNavigationRequest request;
                    request.start = entity.position;
                    request.goal = entity.target;
                    request.zone = entity.zone;
                    request.radius = entity.radius * 0.86F;
                    request.body_height = body_height;
                    request.step_height = step_height;
                    request.can_swim = true;
                    request.grid_spacing = entity.kind == CreatureKind::hash_dog ? 0.82F : 0.98F;
                    const auto route = world::plan_threat_route(*level, request);
                    entity.route = route.waypoints;
                    entity.route_index = 0U;
                    entity.route_goal = entity.target;
                    entity.repath_seconds = entity.kind == CreatureKind::hash_dog ? 0.34F : 0.48F;
                    entity.blocked_seconds = 0.0F;
                }
                while (entity.route_index < entity.route.size() &&
                       distance_xz(entity.position, entity.route[entity.route_index]) < 0.62F) {
                    ++entity.route_index;
                }
                if (entity.route_index < entity.route.size()) {
                    navigation_target = entity.route[entity.route_index];
                }
            }
        }

        const math::Vec3 desired = flat_direction(entity.position, navigation_target, entity.forward);
        const float turn_speed = entity.kind == CreatureKind::hash_dog ? 7.5F : 4.0F;
        entity.forward = turn_toward(entity.forward, desired, std::clamp(turn_speed * dt, 0.0F, 1.0F));

        const bool attack_height_ok = entity.kind == CreatureKind::hash_dog
            ? vertical_separation <= 1.18F : vertical_separation <= 5.5F;
        const bool attack_line_ok = entity.kind == CreatureKind::hash_dog
            ? visible_line : (level == nullptr || world::threat_sensor_line_clear(
                *level, entity.position + math::Vec3{0.0F, 0.70F, 0.0F},
                player_position - math::Vec3{0.0F, 0.35F, 0.0F}, true));
        if ((entity.state == CreatureState::hunt || entity.state == CreatureState::investigate) &&
            saw && player_distance <= entity.attack_range && attack_height_ok && attack_line_ok &&
            math::dot(entity.forward, to_player) > 0.52F) {
            entity.state = CreatureState::attack;
        }
        if (entity.state == CreatureState::attack) {
            if (!saw || player_distance > entity.attack_range * 1.25F ||
                !attack_height_ok || !attack_line_ok) {
                entity.state = entity.memory_seconds > 0.0F
                    ? CreatureState::hunt : CreatureState::investigate;
            } else if (entity.attack_cooldown <= 0.0F) {
                const float damage = entity.kind == CreatureKind::hash_dog ? 9.0F : 10.0F;
                result.player_damage += damage;
                result.enemy_attack = true;
                entity.attack_cooldown = entity.kind == CreatureKind::hash_dog ? 1.05F : 1.55F;
                attack_visual_start_ = entity.position + math::Vec3{0.0F, 1.05F, 0.0F};
                attack_visual_end_ = player_position + math::Vec3{0.0F, 1.02F, 0.0F};
                attack_visual_kind_ = entity.kind == CreatureKind::hash_dog
                    ? AttackVisualKind::claw_arc : AttackVisualKind::shadow_lance;
                attack_visual_seconds_ = entity.kind == CreatureKind::hash_dog ? 0.20F : 0.38F;
                last_hint_ = entity.kind == CreatureKind::hash_dog
                    ? "Claw arc from the dog's facing side"
                    : "A sharp shadow lance tears across the signal";
            }
        }

        if (entity.state == CreatureState::idle || entity.state == CreatureState::investigate ||
            entity.state == CreatureState::hunt) {
            float speed = entity.kind == CreatureKind::hash_dog ? 2.45F : 1.65F;
            if (entity.swimming) speed = entity.kind == CreatureKind::hash_dog ? 1.75F : 1.90F;
            const float waypoint_distance = distance_xz(entity.position, navigation_target);
            const float facing = math::dot(entity.forward, desired);
            entity.velocity = {};
            if (waypoint_distance > 0.30F && facing > 0.20F) {
                const float movement = speed * dt *
                    std::clamp((facing + 0.35F) / 1.35F, 0.28F, 1.0F);
                bool moved = false;
                if (level != nullptr) {
                    moved = try_creature_move(entity, entity.forward, movement, dt, *level, entities_);
                } else {
                    entity.position += entity.forward * movement;
                    entity.velocity = entity.forward * speed;
                    moved = true;
                }
                if (moved) {
                    entity.gait_phase += movement *
                        (entity.kind == CreatureKind::hash_dog ? 5.4F : 2.8F);
                } else {
                    entity.gait_phase += dt * 0.55F;
                    if (entity.blocked_seconds > 0.42F) {
                        entity.route.clear();
                        entity.route_index = 0U;
                        entity.repath_seconds = 0.0F;
                        entity.forward = rotate_xz(entity.forward,
                            (entity.id & 1U) == 0U ? 1.05F : -1.05F);
                    }
                    if (entity.stuck_seconds > 4.0F && entity.memory_seconds <= 0.0F) {
                        entity.state = CreatureState::idle;
                        entity.target = entity.home;
                        entity.stuck_seconds = 0.0F;
                    }
                }
            } else {
                entity.gait_phase += dt * 0.55F;
                entity.blocked_seconds = std::max(0.0F, entity.blocked_seconds - dt);
            }
        }
    }

    if (level != nullptr) separate_creatures(entities_, *level, active_zone);
    if (result.heard_noise && !result.enemy_attack) last_hint_ = "Something turned toward the sound";
    result.hint = last_hint_;
    return result;
}

CombatEntity* CombatSystem::closest_ray_hit(math::Vec3 origin, math::Vec3 direction,
                                            float maximum_range, float* distance_out,
                                            std::string_view active_zone) noexcept {
    direction = math::normalize_or(direction);
    CombatEntity* best = nullptr;
    float best_distance = maximum_range;
    for (auto& entity : entities_) {
        if (!entity.alive || entity.zone != active_zone) continue;
        const math::Vec3 center{entity.position.x, entity.position.y + 1.05F, entity.position.z};
        const math::Vec3 oc = origin - center;
        const float b = math::dot(oc, direction);
        const float c = math::dot(oc, oc) - entity.radius * entity.radius;
        const float discriminant = b * b - c;
        if (discriminant < 0.0F) continue;
        float distance = -b - std::sqrt(discriminant);
        if (distance < 0.0F) distance = -b + std::sqrt(discriminant);
        if (distance < 0.0F || distance > best_distance) continue;
        best = &entity;
        best_distance = distance;
    }
    if (distance_out != nullptr) *distance_out = best_distance;
    return best;
}

CombatEntity* CombatSystem::closest_melee_target(math::Vec3 origin, math::Vec3 direction,
                                                 float range, std::string_view active_zone) noexcept {
    direction = math::normalize_or({direction.x, 0.0F, direction.z});
    CombatEntity* best = nullptr;
    float best_distance = range;
    for (auto& entity : entities_) {
        if (!entity.alive || entity.zone != active_zone) continue;
        math::Vec3 to{entity.position.x - origin.x, 0.0F, entity.position.z - origin.z};
        const float distance = math::length(to);
        if (distance > best_distance || distance < 0.001F) continue;
        if (math::dot(math::normalize_or(to), direction) < 0.28F) continue;
        best = &entity;
        best_distance = distance;
    }
    return best;
}

void CombatSystem::begin_reaction_dodge(CombatEntity& entity,
                                        math::Vec3 incoming_direction) noexcept {
    if (!entity.alive || entity.dodge_cooldown > 0.0F) return;
    incoming_direction = math::normalize_or({incoming_direction.x, 0.0F, incoming_direction.z}, entity.forward);
    const math::Vec3 side = right_of(incoming_direction);
    const float sign = ((entity.hit_reactions + static_cast<std::uint32_t>(entity.id)) % 2U == 0U) ? 1.0F : -1.0F;
    entity.state = CreatureState::dodge;
    if (entity.kind == CreatureKind::hash_dog) {
        entity.dodge_seconds = 0.24F;
        entity.dodge_cooldown = 1.10F;
        entity.dodge_velocity = side * (sign * 5.4F) - incoming_direction * 1.8F;
        entity.deformation = 0.18F;
    } else {
        entity.dodge_seconds = 0.38F;
        entity.dodge_cooldown = 0.92F;
        entity.dodge_velocity = side * (sign * 6.2F) - incoming_direction * 0.8F;
        entity.deformation = 1.0F;
    }
    last_hint_ = entity.kind == CreatureKind::hash_dog
        ? "Hash Dog jumped sideways from the hit"
        : "Formless Shadow collapsed, split, and flowed aside";
}

void CombatSystem::kill_entity(CombatEntity& entity) {
    entity.alive = false;
    entity.state = CreatureState::dead;
    entity.health = 0.0F;
    entity.velocity = {};
    ++kills_;
    DeathProof proof;
    proof.id = next_proof_id_++;
    proof.signature = (entity.id * 0x9E3779B97F4A7C15ULL) ^
                      (static_cast<std::uint64_t>(kills_) << 32U) ^ 0x58415250524F4F46ULL;
    proof.source_kind = entity.kind;
    proof.position = {entity.position.x, entity.position.y + 0.82F, entity.position.z};
    proof.zone = entity.zone;
    proof.value = entity.kind == CreatureKind::hash_dog ? 18.0F : 31.0F;
    proofs_.push_back(proof);
    last_hint_ = "Live 3D death proof stabilized";
}

FireResult CombatSystem::fire_primary(math::Vec3 origin, math::Vec3 direction,
                                      int weapon_slot, bool scanner_reveal,
                                      std::string_view active_zone) {
    FireResult result;
    direction = math::normalize_or(direction);
    if (fire_cooldown_ > 0.0F) {
        result.message = "Weapon recovering";
        return result;
    }

    if (weapon_slot == 2) {
        result.fired = true;
        fire_cooldown_ = 0.52F;
        melee_swing_seconds_ = 0.36F;
        emit_noise(origin, 0.38F, active_zone);
        tracer_start_ = origin;
        tracer_end_ = origin + direction * 2.6F;
        CombatEntity* target = closest_melee_target(origin, direction, 2.65F, active_zone);
        if (target == nullptr) {
            result.impact = tracer_end_;
            result.message = "Signal prybar missed";
            return result;
        }
        result.hit = true;
        result.entity_id = target->id;
        result.damage = target->kind == CreatureKind::formless_shadow ? 16.0F : 44.0F;
        if (target->kind == CreatureKind::formless_shadow && !scanner_reveal) {
            result.damage *= 0.35F;
            result.shadow_resisted = true;
        }
        target->health -= result.damage;
        ++target->hit_reactions;
        result.impact = {target->position.x, 1.05F, target->position.z};
        if (target->health <= 0.0F) {
            kill_entity(*target);
            result.killed = true;
        } else if (target->hit_reactions % 2U == 0U) {
            begin_reaction_dodge(*target, flat_direction(origin, target->position));
            result.reaction_dodge = target->state == CreatureState::dodge;
        }
        result.message = result.killed ? "Prybar broke the signal form" :
                         (result.reaction_dodge ? "Prybar impact; target dodged away" : "Prybar impact");
        return result;
    }

    result.fired = true;
    fire_cooldown_ = 0.18F;
    if (magazine_ <= 0) {
        result.dry_fire = true;
        result.message = "Service pistol dry";
        fire_cooldown_ = 0.28F;
        return result;
    }
    --magazine_;
    emit_noise(origin, 1.0F, active_zone);
    float distance = 42.0F;
    CombatEntity* target = closest_ray_hit(origin, direction, 42.0F, &distance, active_zone);
    tracer_start_ = origin;
    tracer_end_ = origin + direction * distance;
    tracer_seconds_ = 0.11F;
    if (target == nullptr) {
        result.impact = tracer_end_;
        result.message = "Shot lost into the point field";
        return result;
    }

    result.hit = true;
    result.entity_id = target->id;
    result.damage = target->kind == CreatureKind::hash_dog ? 36.0F : 27.0F;
    if (target->kind == CreatureKind::formless_shadow && !scanner_reveal) {
        result.damage *= 0.25F;
        result.shadow_resisted = true;
    }
    target->health -= result.damage;
    ++target->hit_reactions;
    result.impact = origin + direction * distance;
    tracer_end_ = result.impact;
    if (target->health <= 0.0F) {
        kill_entity(*target);
        result.killed = true;
    } else if (target->hit_reactions % 2U == 0U) {
        begin_reaction_dodge(*target, flat_direction(origin, target->position));
        result.reaction_dodge = target->state == CreatureState::dodge;
    }
    result.message = result.killed ? "Entity collapsed into a death proof" :
                     (result.shadow_resisted ? "Shadow dispersed most of the shot" :
                     (result.reaction_dodge ? "Signal hit confirmed; target reacted" : "Signal hit confirmed"));
    return result;
}

void CombatSystem::add_reserve_ammo(int rounds) noexcept {
    if (rounds <= 0) return;
    reserve_ammo_ = std::min(240, reserve_ammo_ + rounds);
    last_hint_ = "Reserve ammunition increased";
}

void CombatSystem::reload() noexcept {
    if (magazine_ >= 12 || reserve_ammo_ <= 0) return;
    const int needed = 12 - magazine_;
    const int loaded = std::min(needed, reserve_ammo_);
    magazine_ += loaded;
    reserve_ammo_ -= loaded;
    fire_cooldown_ = std::max(fire_cooldown_, 0.62F);
    reload_seconds_ = 0.62F;
    last_hint_ = "Service pistol reloaded";
}

bool CombatSystem::claim_near(math::Vec3 position, std::string_view active_zone, float radius) noexcept {
    for (auto& proof : proofs_) {
        if (proof.claimed || proof.zone != active_zone || distance_xz(proof.position, position) > radius) continue;
        proof.claimed = true;
        ++claimed_proofs_;
        last_hint_ = "Death proof claimed for future XAR exchange";
        return true;
    }
    return false;
}

math::Vec3 CombatSystem::void_position(std::string_view active_zone) const noexcept {
    for (const auto& entity : entities_) {
        if (entity.alive && entity.zone == active_zone && entity.kind == CreatureKind::formless_shadow) {
            return {entity.position.x, 0.72F, entity.position.z};
        }
    }
    return {};
}

float CombatSystem::void_radius(std::string_view active_zone) const noexcept {
    for (const auto& entity : entities_) {
        if (entity.alive && entity.zone == active_zone && entity.kind == CreatureKind::formless_shadow) {
            return 2.75F + entity.deformation * 1.25F;
        }
    }
    return 0.0F;
}

float CombatSystem::void_strength(std::string_view active_zone) const noexcept {
    return void_radius(active_zone) > 0.0F ? 0.92F : 0.0F;
}

std::vector<render::PointGpu> CombatSystem::build_visual_points(
    float time_seconds, std::string_view active_zone) const {
    std::vector<render::PointGpu> points;
    points.reserve(9000U);

    for (const auto& stored_entity : entities_) {
        const bool active_entity = stored_entity.alive && stored_entity.zone == active_zone;
        const bool preview_only = stored_entity.alive && !active_entity &&
            stored_entity.threshold_pending &&
            stored_entity.threshold_destination_zone == active_zone;
        if (!active_entity && !preview_only) continue;

        CombatEntity entity = stored_entity;
        if (preview_only) {
            entity.position = stored_entity.threshold_preview_position;
            entity.forward = stored_entity.threshold_preview_forward;
            entity.velocity = entity.forward *
                (entity.kind == CreatureKind::hash_dog ? 1.35F : 1.05F);
            entity.state = CreatureState::investigate;
        }
        const std::size_t entity_visual_begin = points.size();
        if (entity.kind == CreatureKind::hash_dog) {
            const float moving = std::clamp(math::length(entity.velocity) / 2.45F, 0.0F, 1.0F);
            const float bob = std::sin(entity.gait_phase * 2.0F) * 0.07F * moving;
            const math::Vec3 origin{entity.position.x, entity.position.y, entity.position.z};
            add_oriented_ellipsoid(points, origin, entity.forward, {0.0F, 0.95F + bob, 0.0F},
                                   {1.24F, 0.53F, 0.49F}, 900U,
                                   entity.id * 100003U, 0.84F, 0.24F, 0.12F, 0.040F);
            add_oriented_ellipsoid(points, origin, entity.forward, {0.65F, 1.02F + bob, 0.0F},
                                   {0.64F, 0.58F, 0.54F}, 300U,
                                   entity.id * 100009U, 0.90F, 0.29F, 0.13F, 0.043F);
            add_oriented_ellipsoid(points, origin, entity.forward, {1.16F, 1.24F + bob, 0.0F},
                                   {0.48F, 0.43F, 0.40F}, 320U,
                                   entity.id * 100019U, 0.96F, 0.38F, 0.16F, 0.046F);
            add_oriented_ellipsoid(points, origin, entity.forward, {1.52F, 1.12F + bob, 0.0F},
                                   {0.34F, 0.24F, 0.27F}, 150U,
                                   entity.id * 100021U, 0.78F, 0.22F, 0.10F, 0.039F);

            const std::array<float, 4> leg_x{{-0.68F, -0.68F, 0.62F, 0.62F}};
            const std::array<float, 4> leg_z{{-0.36F, 0.36F, -0.36F, 0.36F}};
            for (std::size_t i = 0; i < leg_x.size(); ++i) {
                const float phase = entity.gait_phase + (i == 0U || i == 3U ? 0.0F : kPi);
                const float swing = std::sin(phase) * 0.30F * moving;
                const float lift = std::max(0.0F, std::cos(phase)) * 0.14F * moving;
                const math::Vec3 hip = local_to_world(origin, entity.forward,
                    {leg_x[i], 0.86F + bob, leg_z[i]});
                const math::Vec3 knee = local_to_world(origin, entity.forward,
                    {leg_x[i] + swing * 0.44F, 0.48F + lift, leg_z[i]});
                const math::Vec3 paw = local_to_world(origin, entity.forward,
                    {leg_x[i] + swing, 0.13F + lift, leg_z[i]});
                add_line(points, hip, knee, 58U, 0.95F, 0.34F, 0.14F, 0.032F);
                add_line(points, knee, paw, 58U, 0.74F, 0.18F, 0.09F, 0.031F);
                add_joint(points, hip, entity.id * 400003U + i * 31U, 1.0F, 0.62F, 0.25F);
                add_joint(points, knee, entity.id * 400019U + i * 37U, 0.96F, 0.46F, 0.18F);
                add_oriented_ellipsoid(points, origin, entity.forward,
                    {leg_x[i] + swing + 0.10F, 0.12F + lift, leg_z[i]},
                    {0.25F, 0.10F, 0.17F}, 60U, entity.id * 500009U + i * 53U,
                    0.68F, 0.14F, 0.08F, 0.032F);
            }

            const float tail_sway = std::sin(entity.gait_phase * 0.72F) * 0.48F;
            const math::Vec3 tail_root = local_to_world(origin, entity.forward, {-1.10F, 1.08F + bob, 0.0F});
            const math::Vec3 tail_mid = local_to_world(origin, entity.forward, {-1.52F, 1.31F + bob, tail_sway * 0.34F});
            const math::Vec3 tail_tip = local_to_world(origin, entity.forward, {-1.92F, 1.54F + bob, tail_sway});
            add_line(points, tail_root, tail_mid, 75U, 0.84F, 0.24F, 0.12F, 0.037F);
            add_line(points, tail_mid, tail_tip, 75U, 0.90F, 0.31F, 0.15F, 0.034F);

            const math::Vec3 left_eye = local_to_world(origin, entity.forward, {1.47F, 1.40F + bob, -0.18F});
            const math::Vec3 right_eye = local_to_world(origin, entity.forward, {1.47F, 1.40F + bob, 0.18F});
            const math::Vec3 nose = local_to_world(origin, entity.forward, {1.83F, 1.14F + bob, 0.0F});
            add_ellipsoid(points, left_eye, {0.08F, 0.07F, 0.07F}, 42U,
                          entity.id * 700001U, 0.98F, 0.92F, 0.32F, 0.031F);
            add_ellipsoid(points, right_eye, {0.08F, 0.07F, 0.07F}, 42U,
                          entity.id * 700003U, 0.98F, 0.92F, 0.32F, 0.031F);
            add_ellipsoid(points, nose, {0.11F, 0.09F, 0.10F}, 54U,
                          entity.id * 700009U, 0.08F, 0.03F, 0.02F, 0.033F);
            add_oriented_ellipsoid(points, origin, entity.forward, {1.12F, 1.65F + bob, -0.25F},
                                   {0.18F, 0.30F, 0.14F}, 70U,
                                   entity.id * 800011U, 0.88F, 0.26F, 0.13F, 0.034F);
            add_oriented_ellipsoid(points, origin, entity.forward, {1.12F, 1.65F + bob, 0.25F},
                                   {0.18F, 0.30F, 0.14F}, 70U,
                                   entity.id * 800021U, 0.88F, 0.26F, 0.13F, 0.034F);
        } else {
            const math::Vec3 origin{entity.position.x, 0.0F, entity.position.z};
            const math::Vec3 right = right_of(entity.forward);
            const float moving = std::clamp(math::length(entity.velocity) / 1.65F, 0.0F, 1.0F);
            const float collapse = std::clamp(entity.deformation, 0.0F, 1.0F);
            for (std::uint32_t i = 0; i < 1900U; ++i) {
                const float u = unit_hash(entity.id * 200003U + i * 4U);
                const float v = unit_hash(entity.id * 200003U + i * 4U + 1U);
                const float w = unit_hash(entity.id * 200003U + i * 4U + 2U);
                const float longitudinal = (u * 2.0F - 1.0F) * (1.55F + moving * 1.20F);
                float lateral = (v * 2.0F - 1.0F) * (1.35F + collapse * 1.30F);
                const float split = collapse > 0.05F ? (lateral >= 0.0F ? 0.75F : -0.75F) * collapse : 0.0F;
                lateral += split;
                const float leading = std::clamp((longitudinal + 2.4F) / 4.8F, 0.0F, 1.0F);
                const float floor_height = 0.06F + w * (0.18F + collapse * 0.10F);
                const float rise = (1.0F - collapse) *
                    std::pow(std::max(0.0F, 1.0F - std::abs(lateral) / 1.8F), 2.0F) *
                    (0.35F + leading * 1.75F);
                const float ripple = std::sin(longitudinal * 3.1F + lateral * 4.2F +
                                              time_seconds * 3.4F + w * 5.0F) * 0.12F;
                math::Vec3 p = origin + entity.forward * longitudinal + right * lateral;
                p.y = floor_height + rise + ripple * (1.0F - collapse * 0.8F);
                const float tail_fade = std::clamp(0.45F + leading * 0.70F, 0.22F, 1.0F);
                const float flicker = 0.42F + 0.58F * unit_hash(entity.id * 300007U + i);
                points.push_back(point(p, 0.025F + u * 0.040F,
                    0.16F + 0.30F * flicker, 0.04F + 0.16F * flicker,
                    0.34F + 0.54F * flicker, tail_fade * (0.40F + 0.50F * flicker), 0.92F));
            }
            for (std::uint32_t i = 0; i < 260U; ++i) {
                const float t = static_cast<float>(i) / 259.0F;
                const float side = i % 2U == 0U ? 1.0F : -1.0F;
                math::Vec3 p = origin - entity.forward * (1.2F + t * 2.6F) +
                               right * side * (0.18F + t * 0.75F);
                p.y = 0.08F + std::sin(t * 12.0F + time_seconds * 4.0F) * 0.07F;
                points.push_back(point(p, 0.024F + (1.0F - t) * 0.022F,
                                       0.34F, 0.08F, 0.62F, 0.62F * (1.0F - t), 0.88F));
            }
        }
        if (preview_only) {
            const float progress = stored_entity.threshold_total_seconds > 0.001F
                ? 1.0F - stored_entity.threshold_seconds /
                  stored_entity.threshold_total_seconds
                : 1.0F;
            const float alpha_scale = 0.24F + std::clamp(progress, 0.0F, 1.0F) * 0.48F;
            for (std::size_t index = entity_visual_begin; index < points.size(); ++index) {
                auto& visual = points[index];
                visual.color[0] = std::clamp(visual.color[0] * 0.45F + 0.08F, 0.0F, 1.0F);
                visual.color[1] = std::clamp(visual.color[1] * 0.58F + 0.18F, 0.0F, 1.0F);
                visual.color[2] = std::clamp(visual.color[2] * 0.72F + 0.28F, 0.0F, 1.0F);
                visual.color[3] *= alpha_scale;
                visual.density *= 0.78F;
            }
            const float pulse = 0.45F + 0.35F *
                std::sin(time_seconds * 8.0F + static_cast<float>(entity.id));
            add_line(points,
                     stored_entity.threshold_destination + math::Vec3{0.0F, 0.12F, 0.0F},
                     entity.position + math::Vec3{0.0F, 0.12F, 0.0F},
                     72U, 0.10F, 0.72F + pulse * 0.20F, 1.0F,
                     0.022F, 0.26F + progress * 0.38F);
        }
    }

    for (const auto& proof : proofs_) {
        if (proof.claimed || proof.zone != active_zone) continue;
        for (std::uint32_t i = 0; i < 520U; ++i) {
            const float t = static_cast<float>(i) / 520.0F * 2.0F * kPi;
            const float p = 2.0F * t + static_cast<float>(proof.id) * 0.23F;
            const float q = 3.0F * t - static_cast<float>(proof.id) * 0.17F;
            const math::Vec3 position{
                proof.position.x + std::cos(p) * (0.62F + 0.18F * std::cos(q)),
                proof.position.y + std::sin(q) * 0.58F + std::sin(time_seconds * 1.8F + t) * 0.05F,
                proof.position.z + std::sin(p) * (0.62F + 0.18F * std::cos(q)),
            };
            points.push_back(point(position, 0.034F, 0.20F, 0.96F, 0.78F, 0.94F, 1.0F));
        }
    }

    if (tracer_seconds_ > 0.0F) {
        add_line(points, tracer_start_, tracer_end_, 150U, 1.0F, 0.90F, 0.48F, 0.030F);
    }
    if (melee_swing_seconds_ > 0.0F) {
        const math::Vec3 direction = flat_direction(tracer_start_, tracer_end_);
        add_arc(points, tracer_start_, direction, 1.25F, -1.12F, 1.05F,
                260U, -0.18F, 0.96F, 0.62F, 0.18F, 0.038F);
        add_arc(points, tracer_start_, direction, 2.10F, -1.04F, 0.92F,
                220U, 0.02F, 1.0F, 0.86F, 0.34F, 0.030F);
    }

    if (attack_visual_kind_ == AttackVisualKind::claw_arc && attack_visual_seconds_ > 0.0F) {
        const math::Vec3 forward = flat_direction(attack_visual_start_, attack_visual_end_);
        add_arc(points, attack_visual_end_, forward, 0.85F, -1.35F, 0.45F,
                130U, 0.15F, 1.0F, 0.22F, 0.10F, 0.042F);
        add_arc(points, attack_visual_end_, forward, 1.05F, -0.92F, 0.88F,
                130U, 0.32F, 1.0F, 0.44F, 0.14F, 0.034F);
    } else if (attack_visual_kind_ == AttackVisualKind::shadow_lance && attack_visual_seconds_ > 0.0F) {
        const math::Vec3 direction = math::normalize_or(attack_visual_end_ - attack_visual_start_);
        const math::Vec3 side = math::normalize_or(math::cross(direction, {0.0F, 1.0F, 0.0F}), {1.0F, 0.0F, 0.0F});
        add_line(points, attack_visual_start_, attack_visual_end_, 180U,
                 0.92F, 0.18F, 1.0F, 0.036F);
        for (int lane = -2; lane <= 2; ++lane) {
            const float offset = static_cast<float>(lane) * 0.12F;
            add_line(points, attack_visual_start_ + side * offset,
                     attack_visual_end_ + side * (offset * 0.08F), 90U,
                     0.72F + 0.05F * static_cast<float>(lane + 2),
                     0.24F, 1.0F, 0.026F, 0.76F);
        }
        for (std::uint32_t i = 0; i < 120U; ++i) {
            const float t = static_cast<float>(i) / 119.0F;
            const float angle = t * 2.0F * kPi;
            const float width = (1.0F - t) * 0.55F;
            const math::Vec3 p = attack_visual_end_ - direction * (t * 0.85F) +
                side * std::cos(angle) * width + math::Vec3{0.0F, std::sin(angle) * width, 0.0F};
            points.push_back(point(p, 0.032F, 0.94F, 0.48F, 1.0F, 0.88F, 1.0F));
        }
    }

    last_world_visual_count_ = points.size();
    return points;
}

std::vector<render::PointGpu> CombatSystem::build_viewmodel_points(
    float time_seconds, const ViewmodelPose& pose) const {
    std::vector<render::PointGpu> points;
    points.reserve(7200U);

    const math::Vec3 forward = math::normalize_or(pose.forward);
    const math::Vec3 right = math::normalize_or(pose.right, {1.0F, 0.0F, 0.0F});
    const math::Vec3 up = math::normalize_or(math::cross(right, forward), {0.0F, 1.0F, 0.0F});
    const float move = std::clamp(pose.movement_amount, 0.0F, 1.0F);
    const float cadence = pose.sprinting ? 11.5F : (pose.swimming ? 4.2F : 7.2F);
    const float bob_scale = pose.sprinting ? 0.055F : (pose.swimming ? 0.035F : 0.028F);
    const float bob_y = std::sin(time_seconds * cadence) * bob_scale * move;
    const float bob_x = std::cos(time_seconds * cadence * 0.5F) * bob_scale * 0.75F * move;
    const float crouch_drop = pose.crouched ? 0.09F : 0.0F;
    const float recoil = tracer_seconds_ > 0.0F && pose.weapon_slot == 1
        ? std::clamp(tracer_seconds_ / 0.11F, 0.0F, 1.0F) * 0.085F : 0.0F;
    const float reload_roll = reload_seconds_ > 0.0F ? std::sin((1.0F - reload_seconds_ / 0.62F) * kPi) : 0.0F;

    const math::Vec3 center = pose.camera_position + forward * (0.33F - recoil) -
                              up * (0.34F + crouch_drop - bob_y) + right * bob_x;
    const math::Vec3 left_shoulder = center - right * 0.25F - forward * 0.12F + up * 0.08F;
    const math::Vec3 right_shoulder = center + right * 0.25F - forward * 0.12F + up * 0.08F;
    math::Vec3 left_hand = center + forward * 0.37F - right * 0.13F - up * 0.08F;
    math::Vec3 right_hand = center + forward * 0.42F + right * 0.14F - up * 0.07F;
    if (pose.weapon_slot == 1) {
        left_hand = left_hand - forward * 0.07F;
        right_hand += right * reload_roll * 0.18F - up * reload_roll * 0.10F;
    }

    const math::Vec3 left_elbow = (left_shoulder + left_hand) * 0.5F - up * 0.10F - right * 0.08F;
    const math::Vec3 right_elbow = (right_shoulder + right_hand) * 0.5F - up * 0.10F + right * 0.08F;
    add_line(points, left_shoulder, left_elbow, 210U, 0.48F, 0.30F, 0.22F, 0.024F);
    add_line(points, left_elbow, left_hand, 220U, 0.72F, 0.44F, 0.30F, 0.024F);
    add_line(points, right_shoulder, right_elbow, 210U, 0.48F, 0.30F, 0.22F, 0.024F);
    add_line(points, right_elbow, right_hand, 220U, 0.72F, 0.44F, 0.30F, 0.024F);
    add_ellipsoid(points, left_elbow, {0.065F, 0.065F, 0.065F}, 90U, 910001U,
                  0.90F, 0.63F, 0.42F, 0.030F);
    add_ellipsoid(points, right_elbow, {0.065F, 0.065F, 0.065F}, 90U, 910003U,
                  0.90F, 0.63F, 0.42F, 0.030F);
    add_ellipsoid(points, left_hand, {0.10F, 0.08F, 0.07F}, 150U, 920001U,
                  0.91F, 0.66F, 0.46F, 0.032F);
    add_ellipsoid(points, right_hand, {0.10F, 0.08F, 0.07F}, 150U, 920003U,
                  0.91F, 0.66F, 0.46F, 0.032F);
    // Pivot 12 separates the fingers from the palm so the hands read as hands
    // rather than two unresolved point-cloud balls.
    for (int finger = 0; finger < 4; ++finger) {
        const float lane = (static_cast<float>(finger) - 1.5F) * 0.025F;
        add_line(points, left_hand + right * lane + forward * 0.015F,
                 left_hand + right * lane + forward * (0.12F + static_cast<float>(finger) * 0.008F),
                 34U, 0.92F, 0.67F, 0.47F, 0.016F);
        add_line(points, right_hand + right * lane + forward * 0.015F,
                 right_hand + right * lane + forward * (0.12F + static_cast<float>(3 - finger) * 0.008F),
                 34U, 0.92F, 0.67F, 0.47F, 0.016F);
    }

    if (pose.weapon_slot == 1) {
        const math::Vec3 weapon_origin = right_hand - right * 0.02F + forward * 0.08F;
        const math::Vec3 gun_forward = math::normalize_or(forward - up * 0.035F);
        for (std::uint32_t i = 0; i < 1050U; ++i) {
            const float u = unit_hash(930001U + i * 4U);
            const float v = unit_hash(930001U + i * 4U + 1U);
            const float w = unit_hash(930001U + i * 4U + 2U);
            const math::Vec3 p = weapon_origin + gun_forward * (u * 0.42F) +
                right * ((v * 2.0F - 1.0F) * 0.085F) +
                up * ((w * 2.0F - 1.0F) * 0.075F);
            points.push_back(point(p, 0.020F + u * 0.012F, 0.30F, 0.34F, 0.38F, 0.98F, 1.0F));
        }
        const math::Vec3 barrel_end = weapon_origin + gun_forward * 0.58F;
        add_line(points, weapon_origin + gun_forward * 0.30F, barrel_end,
                 310U, 0.48F, 0.54F, 0.60F, 0.024F);
        add_line(points, weapon_origin + gun_forward * 0.10F,
                 weapon_origin + gun_forward * 0.04F - up * 0.29F,
                 280U, 0.20F, 0.23F, 0.26F, 0.025F);
        add_line(points, left_hand, weapon_origin + gun_forward * 0.22F,
                 180U, 0.78F, 0.50F, 0.34F, 0.024F);

        const float ammo_ratio = static_cast<float>(magazine_) / 12.0F;
        const std::array<float, 3> ammo_color = ammo_ratio <= 0.001F
            ? std::array<float, 3>{1.0F, 0.10F, 0.08F}
            : (ammo_ratio <= 0.25F ? std::array<float, 3>{1.0F, 0.74F, 0.08F}
                                  : std::array<float, 3>{0.22F, 1.0F, 0.32F});
        for (int i = 0; i < 12; ++i) {
            const float active = i < magazine_ ? 1.0F : 0.18F;
            const math::Vec3 p = weapon_origin + gun_forward * (0.10F + static_cast<float>(i) * 0.022F) +
                                 right * 0.004F + up * 0.112F;
            points.push_back(point(p, 0.031F, ammo_color[0] * active,
                                   ammo_color[1] * active, ammo_color[2] * active, 0.98F, 1.0F));
        }
        if (tracer_seconds_ > 0.0F) {
            add_ellipsoid(points, barrel_end, {0.08F, 0.08F, 0.08F}, 170U,
                          940001U, 1.0F, 0.84F, 0.32F, 0.034F);
        }
    } else {
        float progress = melee_swing_seconds_ > 0.0F
            ? 1.0F - std::clamp(melee_swing_seconds_ / 0.36F, 0.0F, 1.0F) : 0.34F;
        const float angle = -0.92F + progress * 2.18F;
        const math::Vec3 tool_direction = math::normalize_or(
            forward * std::cos(angle) + right * std::sin(angle) + up * 0.26F);
        const math::Vec3 grip = (left_hand + right_hand) * 0.5F + right * 0.10F + forward * 0.08F;
        const math::Vec3 shaft_start = grip - tool_direction * 0.18F;
        const math::Vec3 tip = grip + tool_direction * 1.04F;
        // Dark steel core plus a bright safety edge keeps the prybar readable
        // against both the tan hands and the yellow liminal environment.
        add_line(points, shaft_start, tip, 980U,
                 0.14F, 0.17F, 0.20F, 0.036F);
        add_line(points, shaft_start + right * 0.018F, tip + right * 0.018F, 760U,
                 1.0F, 0.42F, 0.08F, 0.018F);
        const math::Vec3 hook_right = math::normalize_or(math::cross(tool_direction, up), right);
        add_arc(points, tip, tool_direction, 0.24F, -0.18F, 1.72F,
                260U, 0.0F, 1.0F, 0.48F, 0.08F, 0.034F);
        add_line(points, left_hand, grip - hook_right * 0.055F,
                 170U, 0.80F, 0.52F, 0.35F, 0.022F);
        add_line(points, right_hand, grip + hook_right * 0.055F,
                 170U, 0.80F, 0.52F, 0.35F, 0.022F);
        if (melee_swing_seconds_ > 0.0F) {
            for (int ribbon = 0; ribbon < 4; ++ribbon) {
                const float radius = 0.54F + static_cast<float>(ribbon) * 0.15F;
                add_arc(points, grip, forward, radius, -1.22F, angle,
                        190U, static_cast<float>(ribbon) * 0.030F,
                        1.0F, 0.82F - static_cast<float>(ribbon) * 0.12F,
                        0.18F, 0.028F - static_cast<float>(ribbon) * 0.003F);
            }
        }
    }

    if (pose.pitch_degrees < -34.0F) {
        const math::Vec3 pelvis = pose.camera_position - up * 1.02F + forward * 0.10F;
        const math::Vec3 left_knee = pelvis - up * 0.48F - right * 0.18F + forward * 0.08F;
        const math::Vec3 right_knee = pelvis - up * 0.48F + right * 0.18F + forward * 0.08F;
        const float step = std::sin(time_seconds * cadence) * 0.12F * move;
        const math::Vec3 left_foot = left_knee - up * 0.54F - right * 0.03F + forward * (0.16F + step);
        const math::Vec3 right_foot = right_knee - up * 0.54F + right * 0.03F + forward * (0.16F - step);
        add_line(points, pelvis - right * 0.12F, left_knee, 170U, 0.24F, 0.28F, 0.32F, 0.031F);
        add_line(points, pelvis + right * 0.12F, right_knee, 170U, 0.24F, 0.28F, 0.32F, 0.031F);
        add_line(points, left_knee, left_foot, 170U, 0.18F, 0.21F, 0.24F, 0.030F);
        add_line(points, right_knee, right_foot, 170U, 0.18F, 0.21F, 0.24F, 0.030F);
        add_line(points, left_foot, left_foot + forward * 0.26F, 120U, 0.12F, 0.14F, 0.16F, 0.031F);
        add_line(points, right_foot, right_foot + forward * 0.26F, 120U, 0.12F, 0.14F, 0.16F, 0.031F);
    }

    last_viewmodel_visual_count_ = points.size();
    return points;
}

}  // namespace signalcloud::combat
