#include "engine/world/threat_director.hpp"

#include "engine/combat/combat_system.hpp"
#include "engine/world/liminal_level.hpp"

#include <algorithm>
#include <array>
#include <cmath>

namespace signalcloud::world {
namespace {

float zone_pressure(std::string_view name) noexcept {
    if (name == "Live-Fire Signal Range") return 1.0F;
    if (name == "Open Pressure Cavity" || name == "Long Signal Hall" ||
        name == "Hum Hall" || name == "Echo Archive") return 0.86F;
    if (name == "Nested Room Matrix" || name == "Fallen Office" ||
        name == "Submerged Boundary Lab") return 0.68F;
    if (name.find("Water") != std::string_view::npos ||
        name.find("Flood") != std::string_view::npos ||
        name.find("Tunnel") != std::string_view::npos) return 0.58F;
    return 0.42F;
}

std::uint64_t mix64(std::uint64_t value) noexcept {
    value ^= value >> 30U;
    value *= 0xbf58476d1ce4e5b9ULL;
    value ^= value >> 27U;
    value *= 0x94d049bb133111ebULL;
    return value ^ (value >> 31U);
}

struct ThresholdRoute {
    math::Vec3 source_threshold{};
    math::Vec3 destination_entry{};
    math::Vec3 destination_forward{0.0F, 0.0F, -1.0F};
};

std::optional<ThresholdRoute> threshold_route_between(
    const LiminalLevel& level, std::string_view source_zone,
    std::string_view destination_zone) noexcept {
    for (const auto& portal : level.portals()) {
        if (portal.source_zone != source_zone ||
            portal.destination_zone != destination_zone) continue;
        ThresholdRoute result;
        result.source_threshold = portal.center + portal.inward_normal * 0.55F;
        const PortalGate* reverse = nullptr;
        for (const auto& candidate : level.portals()) {
            if (candidate.source_zone == destination_zone &&
                candidate.destination_zone == source_zone) {
                reverse = &candidate;
                break;
            }
        }
        if (reverse != nullptr) {
            result.destination_forward = math::normalize_or(
                {reverse->inward_normal.x, 0.0F, reverse->inward_normal.z},
                {0.0F, 0.0F, -1.0F});
            result.destination_entry = reverse->center +
                result.destination_forward * 1.35F;
        } else {
            const float radians = portal.destination_yaw_degrees *
                3.14159265358979323846F / 180.0F;
            result.destination_forward =
                {std::cos(radians), 0.0F, std::sin(radians)};
            result.destination_entry = portal.destination;
        }
        result.source_threshold.y = level.ground_height_at(
            result.source_threshold.x, result.source_threshold.z);
        result.destination_entry.y = level.ground_height_at(
            result.destination_entry.x, result.destination_entry.z);
        return result;
    }

    for (const auto& connection : level.connections()) {
        const bool forward = connection.zone_a == source_zone &&
                             connection.zone_b == destination_zone;
        const bool reverse = connection.bidirectional &&
                             connection.zone_b == source_zone &&
                             connection.zone_a == destination_zone;
        if (!forward && !reverse) continue;
        const auto aperture = level.connection_aperture(connection, source_zone);
        ThresholdRoute result;
        result.destination_forward = math::normalize_or(
            {aperture.normal.x, 0.0F, aperture.normal.z},
            {0.0F, 0.0F, -1.0F});
        result.source_threshold = aperture.center -
            result.destination_forward * 0.70F;
        result.destination_entry = aperture.center +
            result.destination_forward * 1.15F;
        result.source_threshold.y = level.ground_height_at(
            result.source_threshold.x, result.source_threshold.z);
        result.destination_entry.y = level.ground_height_at(
            result.destination_entry.x, result.destination_entry.z);
        return result;
    }
    return std::nullopt;
}

}  // namespace

bool zone_is_protected(std::string_view zone) noexcept {
    return zone == "Reception Tape" || zone == "Scavenger Exchange" ||
           zone.find("Safe") != std::string_view::npos ||
           zone.find("Save") != std::string_view::npos ||
           zone.find("Exchange") != std::string_view::npos;
}

ThreatDirector ThreatDirector::make_pivot13(const LiminalLevel& level) {
    ThreatDirector result;
    result.reset(level);
    return result;
}

void ThreatDirector::reset(const LiminalLevel& level) {
    zones_.clear();
    zones_.reserve(level.areas().size());
    for (const auto& area : level.areas()) {
        ZoneState zone;
        zone.name = area.name;
        zone.center = {(area.min_x + area.max_x) * 0.5F,
                       level.ground_height_at((area.min_x + area.max_x) * 0.5F,
                                              (area.min_z + area.max_z) * 0.5F),
                       (area.min_z + area.max_z) * 0.5F};
        zone.half_x = std::max(2.2F, (area.max_x - area.min_x) * 0.42F);
        zone.half_z = std::max(2.2F, (area.max_z - area.min_z) * 0.42F);
        zone.pressure = zone_pressure(area.name);
        zones_.push_back(std::move(zone));
    }
    current_zone_.clear();
    previous_zone_.clear();
    grace_remaining_ = 0.0F;
    global_spawn_cooldown_ = 0.0F;
    transition_serial_ = 0U;
    stats_ = {};
}

ThreatDirector::ZoneState* ThreatDirector::find_zone(std::string_view name) noexcept {
    for (auto& zone : zones_) if (zone.name == name) return &zone;
    return nullptr;
}

const ThreatDirector::ZoneState* ThreatDirector::find_zone(std::string_view name) const noexcept {
    for (const auto& zone : zones_) if (zone.name == name) return &zone;
    return nullptr;
}

int ThreatDirector::desired_population(const ZoneState& zone) const noexcept {
    if (zone.name == "Live-Fire Signal Range") return 2;
    if (zone.pressure >= 0.80F) return 2;
    return 1;
}

bool ThreatDirector::zones_are_connected(const LiminalLevel& level,
                                         std::string_view a,
                                         std::string_view b) const noexcept {
    if (a.empty() || b.empty() || a == b) return false;
    for (const auto& connection : level.connections()) {
        if ((connection.zone_a == a && connection.zone_b == b) ||
            (connection.bidirectional && connection.zone_a == b && connection.zone_b == a)) {
            return true;
        }
    }
    for (const auto& portal : level.portals()) {
        if ((portal.source_zone == a && portal.destination_zone == b) ||
            (portal.source_zone == b && portal.destination_zone == a)) return true;
    }
    return false;
}

std::optional<math::Vec3> ThreatDirector::choose_spawn(
    const LiminalLevel& level, const ZoneState& zone,
    math::Vec3 player_position, combat::CreatureKind kind) const noexcept {
    constexpr std::array<math::Vec3, 20> offsets{{
        {0.72F, 0.0F, 0.72F}, {-0.72F, 0.0F, -0.72F},
        {0.72F, 0.0F, -0.72F}, {-0.72F, 0.0F, 0.72F},
        {0.88F, 0.0F, 0.18F}, {-0.88F, 0.0F, -0.18F},
        {0.18F, 0.0F, 0.88F}, {-0.18F, 0.0F, -0.88F},
        {0.46F, 0.0F, -0.82F}, {-0.46F, 0.0F, 0.82F},
        {0.62F, 0.0F, 0.0F}, {-0.62F, 0.0F, 0.0F},
        {0.0F, 0.0F, 0.62F}, {0.0F, 0.0F, -0.62F},
        {0.35F, 0.0F, 0.18F}, {-0.35F, 0.0F, -0.18F},
        {0.18F, 0.0F, -0.35F}, {-0.18F, 0.0F, 0.35F},
        {0.0F, 0.0F, 0.0F}, {0.28F, 0.0F, 0.28F},
    }};
    const std::size_t start_index = static_cast<std::size_t>(
        mix64(transition_serial_ ^ static_cast<std::uint64_t>(kind)) % offsets.size());
    for (std::size_t i = 0; i < offsets.size(); ++i) {
        const auto& offset = offsets[(start_index + i) % offsets.size()];
        math::Vec3 candidate{
            zone.center.x + offset.x * zone.half_x,
            0.0F,
            zone.center.z + offset.z * zone.half_z,
        };
        if (std::hypot(candidate.x - player_position.x,
                       candidate.z - player_position.z) < 7.5F) continue;
        if (level.zone_name(candidate) != zone.name) continue;
        if (!level.can_occupy(candidate.x, candidate.z,
                              kind == combat::CreatureKind::hash_dog ? 1.02F : 1.20F)) continue;
        const auto* water = level.water_at(candidate.x, candidate.z);
        if (kind == combat::CreatureKind::hash_dog && water != nullptr) continue;
        candidate.y = water == nullptr
            ? level.ground_height_at(candidate.x, candidate.z)
            : water->surface_y - 0.30F;
        return candidate;
    }
    return std::nullopt;
}

ThreatDirectorEvent ThreatDirector::update(float dt_seconds,
                                           const LiminalLevel& level,
                                           combat::CombatSystem& combat,
                                           math::Vec3 player_position,
                                           std::string_view active_zone,
                                           bool scanner_active) {
    ThreatDirectorEvent event;
    const float dt = std::clamp(dt_seconds, 0.0F, 0.10F);
    global_spawn_cooldown_ = std::max(0.0F, global_spawn_cooldown_ - dt);
    grace_remaining_ = std::max(0.0F, grace_remaining_ - dt);
    for (auto& zone : zones_) {
        zone.spawn_cooldown = std::max(0.0F, zone.spawn_cooldown - dt);
        if (zone.name == active_zone) zone.inactive_seconds = 0.0F;
        else zone.inactive_seconds += dt;
    }

    const auto threshold_update = combat.update_threshold_pursuits(
        dt, level, active_zone);
    if (threshold_update.arrived > 0U) {
        stats_.migrations += threshold_update.arrived;
        event.migrated = true;
        event.message = threshold_update.arrived > 1U
            ? "Tracked threats emerged through the dark threshold"
            : "A tracked threat emerged through the dark threshold";
    } else if (threshold_update.expired > 0U) {
        stats_.threshold_failures += threshold_update.expired;
        event.pursuit_expired = true;
        event.message = threshold_update.expired > 1U
            ? "Threat trails broke before reaching the threshold"
            : "A threat trail broke before reaching the threshold";
    } else if (threshold_update.cancelled > 0U) {
        event.message = "A threshold pursuer turned back when the player returned";
    }

    if (current_zone_ != active_zone) {
        previous_zone_ = current_zone_;
        current_zone_ = std::string(active_zone);
        ++transition_serial_;
        if (auto* zone = find_zone(current_zone_)) ++zone->visits;
        grace_remaining_ = scanner_active ? 2.6F : 4.2F;

        if (!zone_is_protected(current_zone_) && !zone_is_protected(previous_zone_) &&
            zones_are_connected(level, previous_zone_, current_zone_)) {
            if (const auto* destination = find_zone(current_zone_);
                destination != nullptr) {
                const auto threshold = threshold_route_between(
                    level, previous_zone_, current_zone_);
                if (threshold) {
                    const std::uint32_t queued = combat.queue_threshold_pursuit(
                        level, previous_zone_, current_zone_,
                        threshold->source_threshold, threshold->destination_entry,
                        threshold->destination_forward,
                        destination->half_x, destination->half_z,
                        3.0F, 2U);
                    if (queued > 0U) {
                        stats_.threshold_queues += queued;
                        event.pursuit_queued = true;
                        event.message = queued > 1U
                            ? "Pursuing threats are finding the threshold; signatures visible for three seconds"
                            : "A pursuing threat is finding the threshold; its signature is visible for three seconds";
                    } else if (combat.living_in_zone(previous_zone_) > 0U) {
                        ++stats_.threshold_failures;
                        event.pursuit_expired = true;
                        event.message = "The pursuing threat could not find this threshold within three seconds";
                    }
                }
            }
        }
    }

    for (auto& zone : zones_) {
        if (zone.name == current_zone_ || zone.inactive_seconds < 24.0F) continue;
        const std::uint32_t retired = combat.despawn_world_entities(zone.name);
        if (retired > 0U) {
            stats_.retired_entities += retired;
            event.retired = true;
            if (event.message.empty()) event.message = "Distant world threats dissolved back into the tape";
        }
        zone.inactive_seconds = 0.0F;
    }

    const auto* zone = find_zone(current_zone_);
    if (zone == nullptr || zone_is_protected(current_zone_) || grace_remaining_ > 0.0F) {
        stats_.active_world_entities = static_cast<std::uint32_t>(combat.world_entity_count());
        stats_.current_zone_pressure = zone == nullptr ? 0.0F : zone->pressure;
        return event;
    }

    const int desired = desired_population(*zone);
    const std::size_t living = combat.living_in_zone(current_zone_);
    if (current_zone_ != "Live-Fire Signal Range" &&
        static_cast<int>(living) < desired && combat.world_entity_count() < 12U &&
        global_spawn_cooldown_ <= 0.0F && zone->spawn_cooldown <= 0.0F) {
        const std::uint64_t roll = mix64(level.seed() ^ transition_serial_ ^
                                         static_cast<std::uint64_t>(stats_.world_spawns + 1U));
        const auto kind = (zone->pressure > 0.72F && (roll & 1U) != 0U)
            ? combat::CreatureKind::formless_shadow
            : combat::CreatureKind::hash_dog;
        const auto spawn = choose_spawn(level, *zone, player_position, kind);
        if (spawn) {
            combat.spawn_world_entity(kind, *spawn, current_zone_, zone->half_x, zone->half_z);
            ++stats_.world_spawns;
            global_spawn_cooldown_ = 9.5F;
            if (auto* mutable_zone = find_zone(current_zone_)) mutable_zone->spawn_cooldown = 11.0F;
            event.spawned = true;
            event.message = kind == combat::CreatureKind::hash_dog
                ? "A Hash Dog formed on a clear surface inside the active room"
                : "A Formless Shadow condensed along the active room surface";
        } else {
            global_spawn_cooldown_ = 2.0F;
        }
    }

    stats_.active_world_entities = static_cast<std::uint32_t>(combat.world_entity_count());
    stats_.threatened_zones = 0U;
    for (const auto& candidate : zones_) {
        if (combat.living_in_zone(candidate.name) > 0U &&
            candidate.name != "Live-Fire Signal Range") ++stats_.threatened_zones;
    }
    stats_.current_zone_pressure = zone->pressure;
    return event;
}

void ThreatDirector::on_player_recovered(combat::CombatSystem& combat,
                                         std::string_view death_zone) {
    if (!death_zone.empty() && death_zone != "Live-Fire Signal Range") {
        const std::uint32_t retired = combat.despawn_world_entities(death_zone);
        stats_.retired_entities += retired;
    }
    current_zone_.clear();
    previous_zone_.clear();
    grace_remaining_ = 6.5F;
    global_spawn_cooldown_ = 7.0F;
}

}  // namespace signalcloud::world
