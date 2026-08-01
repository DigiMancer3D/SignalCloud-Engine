#include "engine/world/threat_navigation.hpp"

#include "engine/world/liminal_level.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <queue>
#include <string>
#include <utility>
#include <vector>

namespace signalcloud::world {
namespace {

constexpr float kEpsilon = 0.0001F;

float distance_xz(math::Vec3 a, math::Vec3 b) noexcept {
    const float dx = a.x - b.x;
    const float dz = a.z - b.z;
    return std::sqrt(dx * dx + dz * dz);
}

const WalkArea* find_area(const LiminalLevel& level, std::string_view zone) noexcept {
    for (const auto& area : level.areas()) {
        if (area.name == zone) return &area;
    }
    return nullptr;
}

bool zone_accepts(const LiminalLevel& level, math::Vec3 position,
                  std::string_view zone) noexcept {
    return level.zone_name(position) == zone;
}

math::Vec3 surface_position(const LiminalLevel& level, math::Vec3 position,
                            bool can_swim) noexcept {
    if (const auto* water = level.water_at(position.x, position.z); water != nullptr && can_swim) {
        position.y = water->surface_y - 0.30F;
    } else {
        position.y = level.ground_height_at(position.x, position.z);
    }
    return position;
}

bool is_glass(std::string_view name) noexcept {
    return name.find("GLASS") != std::string_view::npos ||
           name.find("Glass") != std::string_view::npos ||
           name.find("glass") != std::string_view::npos;
}

float orientation(float ax, float az, float bx, float bz,
                  float cx, float cz) noexcept {
    return (bx - ax) * (cz - az) - (bz - az) * (cx - ax);
}

bool segments_intersect_xz(math::Vec3 a, math::Vec3 b,
                           math::Vec3 c, math::Vec3 d) noexcept {
    const float o1 = orientation(a.x, a.z, b.x, b.z, c.x, c.z);
    const float o2 = orientation(a.x, a.z, b.x, b.z, d.x, d.z);
    const float o3 = orientation(c.x, c.z, d.x, d.z, a.x, a.z);
    const float o4 = orientation(c.x, c.z, d.x, d.z, b.x, b.z);
    return ((o1 > kEpsilon && o2 < -kEpsilon) || (o1 < -kEpsilon && o2 > kEpsilon)) &&
           ((o3 > kEpsilon && o4 < -kEpsilon) || (o3 < -kEpsilon && o4 > kEpsilon));
}

bool segment_hits_aabb(math::Vec3 start, math::Vec3 end,
                       const SolidObstacle& obstacle) noexcept {
    const float dx = end.x - start.x;
    const float dz = end.z - start.z;
    float t_min = 0.0F;
    float t_max = 1.0F;

    const auto clip = [&](float origin, float delta, float minimum, float maximum,
                          float& low, float& high) noexcept {
        if (std::abs(delta) <= kEpsilon) return origin >= minimum && origin <= maximum;
        const float inverse = 1.0F / delta;
        float t0 = (minimum - origin) * inverse;
        float t1 = (maximum - origin) * inverse;
        if (t0 > t1) std::swap(t0, t1);
        low = std::max(low, t0);
        high = std::min(high, t1);
        return low <= high;
    };

    return clip(start.x, dx, obstacle.min_x, obstacle.max_x, t_min, t_max) &&
           clip(start.z, dz, obstacle.min_z, obstacle.max_z, t_min, t_max) &&
           t_max >= 0.0F && t_min <= 1.0F;
}

struct Grid {
    const WalkArea* area{nullptr};
    float spacing{0.90F};
    int width{0};
    int height{0};

    [[nodiscard]] std::size_t index(int x, int z) const noexcept {
        return static_cast<std::size_t>(z * width + x);
    }

    [[nodiscard]] bool contains(int x, int z) const noexcept {
        return x >= 0 && z >= 0 && x < width && z < height;
    }

    [[nodiscard]] math::Vec3 position(int x, int z) const noexcept {
        return {area->min_x + (static_cast<float>(x) + 0.5F) * spacing,
                0.0F,
                area->min_z + (static_cast<float>(z) + 0.5F) * spacing};
    }

    [[nodiscard]] std::pair<int, int> cell(math::Vec3 position_value) const noexcept {
        const int x = std::clamp(static_cast<int>((position_value.x - area->min_x) / spacing),
                                 0, width - 1);
        const int z = std::clamp(static_cast<int>((position_value.z - area->min_z) / spacing),
                                 0, height - 1);
        return {x, z};
    }
};

std::pair<int, int> nearest_valid_cell(const Grid& grid,
                                       const LiminalLevel& level,
                                       math::Vec3 requested,
                                       const ThreatNavigationRequest& request,
                                       bool* recovered) noexcept {
    auto [origin_x, origin_z] = grid.cell(requested);
    const auto valid = [&](int x, int z) noexcept {
        if (!grid.contains(x, z)) return false;
        return threat_position_is_valid(level, grid.position(x, z), request.zone,
                                        request.radius, request.body_height,
                                        request.step_height, request.can_swim);
    };
    if (valid(origin_x, origin_z)) {
        if (recovered != nullptr) *recovered = false;
        return {origin_x, origin_z};
    }

    const int maximum_ring = std::max(grid.width, grid.height);
    for (int ring = 1; ring <= maximum_ring; ++ring) {
        for (int dz = -ring; dz <= ring; ++dz) {
            for (int dx = -ring; dx <= ring; ++dx) {
                if (std::max(std::abs(dx), std::abs(dz)) != ring) continue;
                const int x = origin_x + dx;
                const int z = origin_z + dz;
                if (valid(x, z)) {
                    if (recovered != nullptr) *recovered = true;
                    return {x, z};
                }
            }
        }
    }
    if (recovered != nullptr) *recovered = true;
    return {origin_x, origin_z};
}

}  // namespace

bool threat_position_is_valid(const LiminalLevel& level,
                              math::Vec3 position,
                              std::string_view zone,
                              float radius,
                              float body_height,
                              float step_height,
                              bool can_swim) noexcept {
    if (zone.empty() || zone == "Signal Void") return false;
    if (!zone_accepts(level, position, zone)) return false;
    if (!can_swim && level.water_at(position.x, position.z) != nullptr) return false;
    const float feet_y = level.ground_height_at(position.x, position.z);
    return level.can_occupy_3d(position.x, position.z, feet_y,
                               body_height, radius, step_height);
}

math::Vec3 nearest_valid_threat_position(const LiminalLevel& level,
                                         math::Vec3 position,
                                         std::string_view zone,
                                         float radius,
                                         float body_height,
                                         float step_height,
                                         bool can_swim) noexcept {
    if (threat_position_is_valid(level, position, zone, radius, body_height,
                                 step_height, can_swim)) {
        return surface_position(level, position, can_swim);
    }
    constexpr std::array<float, 7> rings{{0.45F, 0.80F, 1.20F, 1.70F, 2.30F, 3.10F, 4.20F}};
    constexpr int spokes = 24;
    for (float ring : rings) {
        for (int index = 0; index < spokes; ++index) {
            const float angle = static_cast<float>(index) * 6.28318530718F /
                                static_cast<float>(spokes);
            math::Vec3 candidate{position.x + std::cos(angle) * ring,
                                 position.y,
                                 position.z + std::sin(angle) * ring};
            if (threat_position_is_valid(level, candidate, zone, radius,
                                         body_height, step_height, can_swim)) {
                return surface_position(level, candidate, can_swim);
            }
        }
    }
    if (const auto* area = find_area(level, zone); area != nullptr) {
        math::Vec3 center{(area->min_x + area->max_x) * 0.5F, 0.0F,
                          (area->min_z + area->max_z) * 0.5F};
        if (threat_position_is_valid(level, center, zone, radius, body_height,
                                     step_height, can_swim)) {
            return surface_position(level, center, can_swim);
        }
    }
    return surface_position(level, position, can_swim);
}

bool threat_motion_line_clear(const LiminalLevel& level,
                              math::Vec3 start,
                              math::Vec3 end,
                              std::string_view zone,
                              float radius,
                              float body_height,
                              float step_height,
                              bool can_swim) noexcept {
    const float distance = distance_xz(start, end);
    const int samples = std::max(1, static_cast<int>(std::ceil(distance / 0.28F)));
    for (int index = 1; index <= samples; ++index) {
        const float t = static_cast<float>(index) / static_cast<float>(samples);
        math::Vec3 sample = start + (end - start) * t;
        if (!threat_position_is_valid(level, sample, zone, radius,
                                      body_height, step_height, can_swim)) return false;
    }
    return true;
}

bool threat_sensor_line_clear(const LiminalLevel& level,
                              math::Vec3 start,
                              math::Vec3 end,
                              bool glass_is_transparent) noexcept {
    const float low_y = std::min(start.y, end.y);
    const float high_y = std::max(start.y, end.y);
    for (const auto& obstacle : level.obstacles()) {
        if (glass_is_transparent && is_glass(obstacle.name)) continue;
        if (high_y <= 0.0F || low_y >= obstacle.height) continue;
        if (segment_hits_aabb(start, end, obstacle)) return false;
    }
    for (const auto& wall : level.walls()) {
        if (high_y <= wall.base_y || low_y >= wall.height) continue;
        if (segments_intersect_xz(start, end, wall.start, wall.end)) return false;
    }
    return true;
}

ThreatNavigationResult plan_threat_route(const LiminalLevel& level,
                                         const ThreatNavigationRequest& request) {
    ThreatNavigationResult result;
    const auto* area = find_area(level, request.zone);
    if (area == nullptr) return result;

    Grid grid;
    grid.area = area;
    grid.spacing = std::clamp(request.grid_spacing, 0.55F, 1.40F);
    grid.width = std::clamp(static_cast<int>(std::ceil((area->max_x - area->min_x) /
                                                      grid.spacing)), 1, 160);
    grid.height = std::clamp(static_cast<int>(std::ceil((area->max_z - area->min_z) /
                                                       grid.spacing)), 1, 160);
    const std::size_t cell_count = static_cast<std::size_t>(grid.width * grid.height);

    const auto [start_x, start_z] = nearest_valid_cell(grid, level, request.start,
                                                       request, &result.start_recovered);
    const auto [goal_x, goal_z] = nearest_valid_cell(grid, level, request.goal,
                                                     request, &result.goal_recovered);
    const std::size_t start_index = grid.index(start_x, start_z);
    const std::size_t goal_index = grid.index(goal_x, goal_z);

    std::vector<float> g_score(cell_count, std::numeric_limits<float>::infinity());
    std::vector<std::int32_t> parent(cell_count, -1);
    std::vector<std::uint8_t> closed(cell_count, 0U);
    struct OpenNode { float f{0.0F}; std::size_t index{0U}; };
    struct Compare { bool operator()(const OpenNode& a, const OpenNode& b) const noexcept {
        if (a.f == b.f) return a.index > b.index;
        return a.f > b.f;
    }};
    std::priority_queue<OpenNode, std::vector<OpenNode>, Compare> open;
    g_score[start_index] = 0.0F;
    open.push({distance_xz(grid.position(start_x, start_z), grid.position(goal_x, goal_z)),
               start_index});

    constexpr std::array<std::array<int, 2>, 8> directions{{
        {{1, 0}}, {{-1, 0}}, {{0, 1}}, {{0, -1}},
        {{1, 1}}, {{1, -1}}, {{-1, 1}}, {{-1, -1}},
    }};
    const auto valid_cell = [&](int x, int z) noexcept {
        return grid.contains(x, z) &&
               threat_position_is_valid(level, grid.position(x, z), request.zone,
                                        request.radius, request.body_height,
                                        request.step_height, request.can_swim);
    };

    std::size_t best_index = start_index;
    float best_heuristic = distance_xz(grid.position(start_x, start_z),
                                       grid.position(goal_x, goal_z));
    const std::size_t maximum_expansions = std::clamp<std::size_t>(
        request.maximum_expansions, 64U, cell_count);

    while (!open.empty() && result.expanded_nodes < maximum_expansions) {
        const auto current = open.top();
        open.pop();
        if (closed[current.index] != 0U) continue;
        closed[current.index] = 1U;
        ++result.expanded_nodes;
        if (current.index == goal_index) {
            best_index = goal_index;
            result.reached_goal_cell = true;
            break;
        }
        const int current_x = static_cast<int>(current.index % static_cast<std::size_t>(grid.width));
        const int current_z = static_cast<int>(current.index / static_cast<std::size_t>(grid.width));
        for (const auto& direction : directions) {
            const int next_x = current_x + direction[0];
            const int next_z = current_z + direction[1];
            if (!valid_cell(next_x, next_z)) continue;
            if (direction[0] != 0 && direction[1] != 0 &&
                (!valid_cell(current_x + direction[0], current_z) ||
                 !valid_cell(current_x, current_z + direction[1]))) continue;
            const std::size_t next_index = grid.index(next_x, next_z);
            if (closed[next_index] != 0U) continue;
            const float step_cost = direction[0] != 0 && direction[1] != 0 ? 1.41421356F : 1.0F;
            const float tentative = g_score[current.index] + step_cost;
            if (tentative + 0.0001F >= g_score[next_index]) continue;
            g_score[next_index] = tentative;
            parent[next_index] = static_cast<std::int32_t>(current.index);
            const float heuristic = distance_xz(grid.position(next_x, next_z),
                                                grid.position(goal_x, goal_z)) / grid.spacing;
            if (heuristic < best_heuristic) {
                best_heuristic = heuristic;
                best_index = next_index;
            }
            open.push({tentative + heuristic, next_index});
        }
    }

    std::vector<math::Vec3> reverse_path;
    for (std::size_t cursor = best_index; cursor != start_index;) {
        const int x = static_cast<int>(cursor % static_cast<std::size_t>(grid.width));
        const int z = static_cast<int>(cursor / static_cast<std::size_t>(grid.width));
        reverse_path.push_back(surface_position(level, grid.position(x, z), request.can_swim));
        const std::int32_t next = parent[cursor];
        if (next < 0) break;
        cursor = static_cast<std::size_t>(next);
    }
    std::reverse(reverse_path.begin(), reverse_path.end());

    // String-pull the grid path so entities turn at obstacle corners instead of
    // visibly following every grid cell.
    math::Vec3 anchor = surface_position(level, request.start, request.can_swim);
    std::size_t index = 0U;
    while (index < reverse_path.size()) {
        std::size_t furthest = index;
        for (std::size_t candidate = index; candidate < reverse_path.size(); ++candidate) {
            if (!threat_motion_line_clear(level, anchor, reverse_path[candidate],
                                          request.zone, request.radius,
                                          request.body_height, request.step_height,
                                          request.can_swim)) break;
            furthest = candidate;
        }
        result.waypoints.push_back(reverse_path[furthest]);
        anchor = reverse_path[furthest];
        index = furthest + 1U;
        if (result.waypoints.size() >= 48U) break;
    }
    if (result.reached_goal_cell && !result.waypoints.empty()) {
        math::Vec3 exact_goal = surface_position(level, request.goal, request.can_swim);
        if (threat_motion_line_clear(level, result.waypoints.back(), exact_goal,
                                     request.zone, request.radius, request.body_height,
                                     request.step_height, request.can_swim)) {
            result.waypoints.back() = exact_goal;
        }
    }
    return result;
}

}  // namespace signalcloud::world
