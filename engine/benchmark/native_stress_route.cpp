#include "engine/benchmark/native_stress_route.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <deque>
#include <map>
#include <optional>
#include <queue>
#include <set>
#include <string_view>

namespace signalcloud::benchmark {
namespace {

using math::Vec3;

constexpr float kStandingEyeHeight = 1.62F;
constexpr float kCrouchedEyeHeight = 1.05F;

struct Edge {
    std::string source;
    std::string destination;
    bool portal{false};
    const world::RoomConnection* connection{nullptr};
    const world::PortalGate* gate{nullptr};
};

float distance(Vec3 a, Vec3 b) noexcept {
    return math::length(b - a);
}

const world::WalkArea* find_area(const world::LiminalLevel& level, std::string_view name) {
    for (const auto& area : level.areas()) {
        if (area.name == name) return &area;
    }
    return nullptr;
}

Vec3 zone_center(const world::LiminalLevel& level, std::string_view name) {
    if (const auto* area = find_area(level, name)) {
        const float x = (area->min_x + area->max_x) * 0.5F;
        const float z = (area->min_z + area->max_z) * 0.5F;
        const float ground = level.ground_height_at(x, z);
        return {x, ground + kStandingEyeHeight, z};
    }
    for (const auto& portal : level.portals()) {
        if (portal.destination_zone == name) return portal.destination;
        if (portal.source_zone == name) {
            const float ground = level.ground_height_at(portal.center.x, portal.center.z);
            return {portal.center.x, ground + kStandingEyeHeight, portal.center.z};
        }
    }
    return level.spawn_position();
}

void append_if_distinct(std::vector<RouteWaypoint>& out, RouteWaypoint waypoint) {
    if (!out.empty()) {
        const auto& previous = out.back();
        if (distance(previous.position, waypoint.position) < 0.08F &&
            previous.zone == waypoint.zone && previous.transition == waypoint.transition) {
            if (!waypoint.label.empty()) out.back().label = std::move(waypoint.label);
            return;
        }
    }
    out.push_back(std::move(waypoint));
}

std::vector<Edge> build_edges(const world::LiminalLevel& level) {
    std::vector<Edge> result;
    for (const auto& connection : level.connections()) {
        result.push_back({connection.zone_a, connection.zone_b, false, &connection, nullptr});
        if (connection.bidirectional) {
            result.push_back({connection.zone_b, connection.zone_a, false, &connection, nullptr});
        }
    }
    for (const auto& portal : level.portals()) {
        result.push_back({portal.source_zone, portal.destination_zone, true, nullptr, &portal});
    }
    return result;
}

std::vector<const Edge*> shortest_path(const std::vector<Edge>& edges,
                                       std::string_view source,
                                       std::string_view destination) {
    if (source == destination) return {};
    std::queue<std::string> frontier;
    std::map<std::string, const Edge*> arrived_by;
    std::set<std::string> visited;
    frontier.push(std::string(source));
    visited.insert(std::string(source));
    while (!frontier.empty()) {
        const std::string current = frontier.front();
        frontier.pop();
        for (const auto& edge : edges) {
            if (edge.source != current || visited.contains(edge.destination)) continue;
            visited.insert(edge.destination);
            arrived_by[edge.destination] = &edge;
            if (edge.destination == destination) {
                std::vector<const Edge*> path;
                std::string cursor(destination);
                while (cursor != source) {
                    const auto it = arrived_by.find(cursor);
                    if (it == arrived_by.end()) return {};
                    path.push_back(it->second);
                    cursor = it->second->source;
                }
                std::reverse(path.begin(), path.end());
                return path;
            }
            frontier.push(edge.destination);
        }
    }
    return {};
}



bool valid_zone_name(std::string_view zone) noexcept {
    return !zone.empty() && zone != "Signal Void";
}

const world::WalkArea* area_for_zone(const world::LiminalLevel& level,
                                     std::string_view zone) noexcept {
    if (!valid_zone_name(zone)) return nullptr;
    for (const auto& area : level.areas()) {
        if (area.name == zone) return &area;
    }
    return nullptr;
}

Vec3 safe_position_in_area(const world::LiminalLevel& level,
                           const world::WalkArea& area,
                           Vec3 preferred) noexcept {
    constexpr float eye_height = kStandingEyeHeight;
    constexpr float radius = 0.34F;
    const float half_x = std::max(0.0F, (area.max_x - area.min_x) * 0.5F);
    const float half_z = std::max(0.0F, (area.max_z - area.min_z) * 0.5F);
    const float margin_x = std::min(0.72F, std::max(0.08F, half_x * 0.45F));
    const float margin_z = std::min(0.72F, std::max(0.08F, half_z * 0.45F));
    const float min_x = area.min_x + margin_x;
    const float max_x = area.max_x - margin_x;
    const float min_z = area.min_z + margin_z;
    const float max_z = area.max_z - margin_z;

    auto make_candidate = [&](float x, float z) {
        Vec3 candidate{x, 0.0F, z};
        candidate.y = level.ground_height_at(x, z) + eye_height;
        return candidate;
    };
    auto usable = [&](Vec3 candidate) {
        const float feet = candidate.y - eye_height;
        return valid_zone_name(level.zone_name(candidate)) &&
               level.can_occupy_3d(candidate.x, candidate.z, feet,
                                   eye_height, radius, 0.34F);
    };

    const Vec3 clamped = make_candidate(
        std::clamp(preferred.x, std::min(min_x, max_x), std::max(min_x, max_x)),
        std::clamp(preferred.z, std::min(min_z, max_z), std::max(min_z, max_z)));
    if (usable(clamped)) return clamped;

    const float center_x = (area.min_x + area.max_x) * 0.5F;
    const float center_z = (area.min_z + area.max_z) * 0.5F;
    const Vec3 center = make_candidate(center_x, center_z);
    if (usable(center)) return center;

    // Search a small deterministic grid.  Authored rooms can have center
    // obstacles, but a stress-route recovery must still find a nearby legal
    // floor without allocating or querying custom PCP3 geometry.
    static constexpr std::array<float, 5> offsets{{0.0F, -0.55F, 0.55F, -0.82F, 0.82F}};
    for (const float oz : offsets) {
        for (const float ox : offsets) {
            const float x = std::clamp(center_x + ox * half_x,
                                       std::min(min_x, max_x), std::max(min_x, max_x));
            const float z = std::clamp(center_z + oz * half_z,
                                       std::min(min_z, max_z), std::max(min_z, max_z));
            const Vec3 candidate = make_candidate(x, z);
            if (usable(candidate)) return candidate;
        }
    }
    return center;
}

void append_edge(const world::LiminalLevel& level, const Edge& edge,
                 std::vector<RouteWaypoint>& out) {
    const Vec3 source_center = zone_center(level, edge.source);
    const Vec3 destination_center = zone_center(level, edge.destination);
    append_if_distinct(out, {source_center, edge.source, edge.source + " center", RouteTransition::continuous});

    if (edge.portal && edge.gate != nullptr) {
        const Vec3 forward = math::normalize_or(edge.gate->inward_normal, {0.0F, 0.0F, 1.0F});
        const Vec3 approach = edge.gate->center - forward * 1.65F;
        const Vec3 threshold = edge.gate->center;
        const float approach_eye = level.ground_height_at(approach.x, approach.z) + kStandingEyeHeight;
        const float threshold_eye = level.ground_height_at(threshold.x, threshold.z) + kStandingEyeHeight;
        const float destination_eye = level.ground_height_at(edge.gate->destination.x, edge.gate->destination.z) + kStandingEyeHeight;
        append_if_distinct(out, {{approach.x, approach_eye, approach.z},
                                 edge.source, edge.gate->name + " approach", RouteTransition::continuous});
        append_if_distinct(out, {{threshold.x, threshold_eye, threshold.z},
                                 edge.source, edge.gate->name + " threshold", RouteTransition::continuous});
        append_if_distinct(out, {{edge.gate->destination.x, destination_eye, edge.gate->destination.z}, edge.destination,
                                 edge.gate->name + " destination", RouteTransition::portal_jump});
        append_if_distinct(out, {destination_center, edge.destination,
                                 edge.destination + " center", RouteTransition::continuous});
        return;
    }

    if (edge.connection != nullptr) {
        const auto aperture = level.connection_aperture(*edge.connection, edge.source);
        const Vec3 normal = math::normalize_or(aperture.normal, {1.0F, 0.0F, 0.0F});
        const bool crouched = edge.connection->kind == world::ConnectionKind::window;
        const float ground = level.ground_height_at(aperture.center.x, aperture.center.z);
        const float desired_eye = ground + (crouched ? kCrouchedEyeHeight : kStandingEyeHeight);
        const float eye_y = std::clamp(desired_eye, aperture.bottom_y + 0.12F,
                                       std::max(aperture.bottom_y + 0.12F, aperture.top_y - 0.18F));
        const Vec3 source_side{aperture.center.x - normal.x * 1.8F, eye_y,
                               aperture.center.z - normal.z * 1.8F};
        const Vec3 opening{aperture.center.x, eye_y, aperture.center.z};
        const Vec3 destination_side{aperture.center.x + normal.x * 1.8F, eye_y,
                                    aperture.center.z + normal.z * 1.8F};
        append_if_distinct(out, {source_side, edge.source,
                                 edge.source + (crouched ? " window crouch approach" : " preview approach"),
                                 RouteTransition::continuous, crouched});
        append_if_distinct(out, {opening, edge.source,
                                 edge.source + " / " + edge.destination + (crouched ? " window aperture" : " aperture"),
                                 RouteTransition::continuous, crouched});
        append_if_distinct(out, {destination_side, edge.destination,
                                 edge.destination + (crouched ? " window landing" : " threshold entry"),
                                 RouteTransition::continuous, crouched});
        append_if_distinct(out, {destination_center, edge.destination,
                                 edge.destination + " center", RouteTransition::continuous});
    }
}

}  // namespace


void NativeStressRouteGuard::reset() noexcept {
    last_valid_position_ = {};
    last_valid_zone_.clear();
    have_last_valid_ = false;
    void_active_ = false;
    correction_count_ = 0U;
    void_entry_count_ = 0U;
}

RouteContainmentResult NativeStressRouteGuard::stabilize(
    const world::LiminalLevel& level,
    const RoutePose& pose,
    math::Vec3 attempted_position) {
    RouteContainmentResult result;
    result.position = attempted_position;
    result.raw_zone = std::string(level.zone_name(attempted_position));
    result.portal_handoff = pose.portal_jump;

    if (valid_zone_name(result.raw_zone)) {
        result.effective_zone = result.raw_zone;
        result.exited_void = void_active_;
        void_active_ = false;
        last_valid_position_ = attempted_position;
        last_valid_zone_ = result.effective_zone;
        have_last_valid_ = true;
        return result;
    }

    result.entered_void = !void_active_;
    if (result.entered_void) ++void_entry_count_;
    void_active_ = true;

    const world::WalkArea* expected = area_for_zone(level, pose.zone);
    if (expected != nullptr) {
        const Vec3 candidate = safe_position_in_area(level, *expected, attempted_position);
        const float feet = candidate.y - kStandingEyeHeight;
        if (valid_zone_name(level.zone_name(candidate)) &&
            level.can_occupy_3d(candidate.x, candidate.z, feet,
                                kStandingEyeHeight, 0.34F, 0.34F)) {
            result.position = candidate;
            result.effective_zone = expected->name;
            result.used_expected_zone = true;
        } else if (have_last_valid_) {
            result.position = last_valid_position_;
            result.effective_zone = last_valid_zone_;
            result.used_last_valid = true;
        } else {
            result.position = candidate;
            result.effective_zone = expected->name;
            result.used_expected_zone = true;
        }
    } else if (have_last_valid_) {
        result.position = last_valid_position_;
        result.effective_zone = last_valid_zone_;
        result.used_last_valid = true;
    } else if (!level.areas().empty()) {
        result.position = safe_position_in_area(level, level.areas().front(), attempted_position);
        result.effective_zone = level.areas().front().name;
        result.used_expected_zone = true;
    } else {
        result.effective_zone = pose.zone;
    }

    if (!valid_zone_name(result.effective_zone) && have_last_valid_) {
        result.position = last_valid_position_;
        result.effective_zone = last_valid_zone_;
        result.used_last_valid = true;
    }

    result.corrected = true;
    ++correction_count_;
    if (valid_zone_name(result.effective_zone)) {
        last_valid_position_ = result.position;
        last_valid_zone_ = result.effective_zone;
        have_last_valid_ = true;
    }
    return result;
}

NativeStressRoute NativeStressRoute::build(const world::LiminalLevel& level) {
    NativeStressRoute route;
    const auto edges = build_edges(level);
    std::vector<std::string> preferred{
        "Reception Tape", "Corridor Junction", "Fallen Office", "Nested Room Matrix",
        "Long Signal Hall", "Vertical Flood Shaft", "Submerged Service Tunnel",
        "Open Pressure Cavity", "Submerged Boundary Lab", "Threshold Gallery",
        "Raised Window Annex", "Broken Passage Annex", "Reception Tape",
        "Service Loop", "Almond Concourse", "Hum Hall", "Reception Tape",
        "Scavenger Exchange", "Reception Tape", "Live-Fire Signal Range", "Reception Tape"
    };
    for (const auto& area : level.areas()) {
        if (std::find(preferred.begin(), preferred.end(), area.name) == preferred.end()) {
            preferred.push_back(area.name);
        }
    }
    preferred.push_back("Reception Tape");

    std::string current = "Reception Tape";
    append_if_distinct(route.waypoints_, {zone_center(level, current), current,
                                         "Stress route start", RouteTransition::continuous});
    for (const auto& target : preferred) {
        if (target == current) continue;
        const auto path = shortest_path(edges, current, target);
        if (path.empty()) continue;
        for (const auto* edge : path) append_edge(level, *edge, route.waypoints_);
        current = target;
    }

    route.cumulative_.reserve(route.waypoints_.size());
    route.total_length_ = 0.0F;
    route.cumulative_.push_back(0.0F);
    for (std::size_t i = 1; i < route.waypoints_.size(); ++i) {
        if (route.waypoints_[i].transition != RouteTransition::portal_jump) {
            route.total_length_ += distance(route.waypoints_[i - 1].position,
                                            route.waypoints_[i].position);
        } else {
            route.total_length_ += 0.01F;
        }
        route.cumulative_.push_back(route.total_length_);
    }
    return route;
}

std::size_t NativeStressRoute::zone_count() const noexcept {
    std::set<std::string> zones;
    for (const auto& waypoint : waypoints_) zones.insert(waypoint.zone);
    return zones.size();
}

RoutePose NativeStressRoute::pose_at(float distance_along) const noexcept {
    RoutePose result;
    if (waypoints_.empty()) return result;
    if (waypoints_.size() == 1U || total_length_ <= 0.0F) {
        result.position = waypoints_.front().position;
        result.look_at = result.position + Vec3{0.0F, 0.0F, -1.0F};
        result.zone = waypoints_.front().zone;
        result.label = waypoints_.front().label;
        return result;
    }
    float wrapped = std::fmod(std::max(0.0F, distance_along), total_length_);
    auto upper = std::upper_bound(cumulative_.begin(), cumulative_.end(), wrapped);
    std::size_t index = upper == cumulative_.begin() ? 0U
        : static_cast<std::size_t>(std::distance(cumulative_.begin(), upper) - 1);
    index = std::min(index, waypoints_.size() - 2U);
    const auto& a = waypoints_[index];
    const auto& b = waypoints_[index + 1U];
    const float segment = std::max(0.0001F, cumulative_[index + 1U] - cumulative_[index]);
    float t = std::clamp((wrapped - cumulative_[index]) / segment, 0.0F, 1.0F);
    if (b.transition == RouteTransition::portal_jump) t = t < 0.5F ? 0.0F : 1.0F;
    result.position = a.position + (b.position - a.position) * t;
    const Vec3 current_direction = math::normalize_or(b.position - a.position, {0.0F, 0.0F, -1.0F});
    Vec3 next_direction = current_direction;
    if (index + 2U < waypoints_.size()) {
        next_direction = math::normalize_or(waypoints_[index + 2U].position - b.position, current_direction);
    }
    const float turn_t = std::clamp((t - 0.48F) / 0.52F, 0.0F, 1.0F);
    const float eased_turn = turn_t * turn_t * (3.0F - 2.0F * turn_t);
    constexpr float pi = 3.14159265358979323846F;
    const float current_yaw = std::atan2(current_direction.z, current_direction.x);
    const float next_yaw = std::atan2(next_direction.z, next_direction.x);
    float yaw_delta = std::remainder(next_yaw - current_yaw, 2.0F * pi);
    if (std::abs(yaw_delta + pi) < 0.0001F) yaw_delta = pi;
    const float current_pitch = std::asin(std::clamp(current_direction.y, -1.0F, 1.0F));
    const float next_pitch = std::asin(std::clamp(next_direction.y, -1.0F, 1.0F));
    const float yaw = current_yaw + yaw_delta * eased_turn;
    const float pitch = current_pitch + (next_pitch - current_pitch) * eased_turn;
    const float horizontal = std::cos(pitch);
    const Vec3 look_direction{horizontal * std::cos(yaw), std::sin(pitch), horizontal * std::sin(yaw)};
    result.look_at = result.position + look_direction * 6.0F;
    result.zone = t < 0.5F ? a.zone : b.zone;
    result.label = t < 0.5F ? a.label : b.label;
    result.segment_index = index;
    result.segment_progress = t;
    result.portal_jump = b.transition == RouteTransition::portal_jump && t >= 0.5F;
    result.crouched = t < 0.5F ? a.crouched : b.crouched;
    return result;
}

}  // namespace signalcloud::benchmark
