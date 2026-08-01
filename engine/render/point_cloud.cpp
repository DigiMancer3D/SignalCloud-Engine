#include "engine/render/point_cloud.hpp"

#include "engine/math/vec.hpp"
#include "engine/world/liminal_level.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <iterator>
#include <limits>
#include <optional>
#include <set>
#include <string_view>
#include <vector>

namespace signalcloud::render {
namespace {

class XorShift64 {
public:
    explicit XorShift64(std::uint64_t seed) : state_(seed == 0 ? 0x9E3779B97F4A7C15ULL : seed) {}
    std::uint64_t next() noexcept {
        state_ ^= state_ << 13U;
        state_ ^= state_ >> 7U;
        state_ ^= state_ << 17U;
        return state_;
    }
    float unit() noexcept {
        return static_cast<float>((next() >> 40U) & 0xFFFFFFU) / static_cast<float>(0xFFFFFFU);
    }
    float range(float low, float high) noexcept { return low + (high - low) * unit(); }
private:
    std::uint64_t state_;
};

PointGpu make_point(float x, float y, float z, float radius,
                    float r, float g, float b, float a,
                    float nx, float ny, float nz, float density) {
    return {{x, y, z}, radius, {r, g, b, a}, {nx, ny, nz}, density};
}

float segment_length(const world::WallSegment& wall) noexcept {
    return math::length(wall.end - wall.start);
}

std::size_t weighted_index(const std::vector<float>& cumulative, float value) {
    const auto it = std::lower_bound(cumulative.begin(), cumulative.end(), value);
    return it == cumulative.end() ? cumulative.size() - 1U : static_cast<std::size_t>(it - cumulative.begin());
}

std::vector<float> area_cumulative(const std::vector<world::WalkArea>& areas) {
    std::vector<float> result;
    result.reserve(areas.size());
    float total = 0.0F;
    for (const auto& area : areas) {
        total += std::max(0.001F, (area.max_x - area.min_x) * (area.max_z - area.min_z));
        result.push_back(total);
    }
    return result;
}

std::vector<float> wall_cumulative(const std::vector<world::WallSegment>& walls) {
    std::vector<float> result;
    result.reserve(walls.size());
    float total = 0.0F;
    for (const auto& wall : walls) {
        total += std::max(0.001F, segment_length(wall) * wall.height);
        result.push_back(total);
    }
    return result;
}

void deterministic_shuffle(std::vector<PointGpu>& points, XorShift64& rng) {
    for (std::size_t i = points.size(); i > 1U; --i) {
        const std::size_t j = static_cast<std::size_t>(rng.next() % static_cast<std::uint64_t>(i));
        std::swap(points[i - 1U], points[j]);
    }
}

int preview_priority(const PointGpu& point) noexcept {
    const float ny = point.normal[1];
    const float brightness = (point.color[0] + point.color[1] + point.color[2]) / 3.0F;
    // Ground/water and bright fixtures appear first in a doorway preview.
    if (point.density < 0.0F || ny > 0.58F || brightness > 0.82F) return 0;
    // Walls and obstacle faces establish the destination silhouette next.
    if (std::abs(ny) < 0.48F) return 1;
    // Ceilings follow after the route is readable.
    if (ny < -0.55F) return 2;
    return 3;
}

void order_for_progressive_fill(std::vector<PointGpu>& points, XorShift64& rng) {
    deterministic_shuffle(points, rng);
    std::stable_sort(points.begin(), points.end(), [](const PointGpu& a, const PointGpu& b) {
        return preview_priority(a) < preview_priority(b);
    });
}

}  // namespace

PointCloud PointCloud::make_liminal_room(const LiminalRoomSpec& spec) {
    PointCloud cloud;
    cloud.points_.reserve(spec.point_count);
    cloud.stats_.seed = spec.seed;
    cloud.stats_.total_points = spec.point_count;

    XorShift64 rng(spec.seed);
    const float half_w = spec.width * 0.5F;
    const float half_d = spec.depth * 0.5F;
    const std::uint32_t wall_count = spec.point_count * 58U / 100U;
    const std::uint32_t floor_count = spec.point_count * 20U / 100U;
    const std::uint32_t ceiling_count = spec.point_count * 12U / 100U;
    const std::uint32_t dust_count = spec.point_count - wall_count - floor_count - ceiling_count;
    cloud.stats_.wall_points = wall_count;
    cloud.stats_.floor_points = floor_count;
    cloud.stats_.ceiling_points = ceiling_count;
    cloud.stats_.dust_points = dust_count;

    auto palette = [&](float brightness) {
        const float variance = rng.range(-0.055F, 0.055F);
        return std::clamp(brightness + variance, 0.08F, 1.0F);
    };

    for (std::uint32_t i = 0; i < wall_count; ++i) {
        const int face = static_cast<int>(rng.next() % 4U);
        float x = 0.0F;
        float y = rng.range(0.0F, spec.height);
        float z = 0.0F;
        float nx = 0.0F;
        float nz = 0.0F;
        if (face == 0) { x = -half_w; z = rng.range(-half_d, half_d); nx = 1.0F; }
        if (face == 1) { x = half_w; z = rng.range(-half_d, half_d); nx = -1.0F; }
        if (face == 2) { z = -half_d; x = rng.range(-half_w, half_w); nz = 1.0F; }
        if (face == 3) { z = half_d; x = rng.range(-half_w, half_w); nz = -1.0F; }
        const float stain = 0.82F - 0.16F * std::abs(std::sin((x + z) * 0.72F));
        cloud.points_.push_back(make_point(x, y, z, rng.range(0.026F, 0.054F),
            palette(stain), palette(stain * 0.91F), palette(stain * 0.50F),
            rng.range(0.74F, 1.0F), nx, 0.0F, nz, rng.range(0.65F, 1.0F)));
    }

    for (std::uint32_t i = 0; i < floor_count; ++i) {
        const float x = rng.range(-half_w, half_w);
        const float z = rng.range(-half_d, half_d);
        const float tile = (static_cast<int>((x + half_w) / 1.5F) + static_cast<int>((z + half_d) / 1.5F)) % 2 == 0 ? 0.36F : 0.30F;
        cloud.points_.push_back(make_point(x, 0.0F, z, rng.range(0.022F, 0.048F),
            palette(tile), palette(tile * 0.95F), palette(tile * 0.72F),
            rng.range(0.68F, 0.95F), 0.0F, 1.0F, 0.0F, rng.range(0.55F, 0.92F)));
    }

    for (std::uint32_t i = 0; i < ceiling_count; ++i) {
        const float x = rng.range(-half_w, half_w);
        const float z = rng.range(-half_d, half_d);
        const bool light_strip = std::fmod(std::abs(x), 5.0F) < 0.55F && std::fmod(std::abs(z), 7.0F) < 2.1F;
        const float base = light_strip ? 0.93F : 0.48F;
        cloud.points_.push_back(make_point(x, spec.height, z, rng.range(0.022F, 0.045F),
            palette(base), palette(base * 0.92F), palette(base * 0.62F),
            light_strip ? 1.0F : rng.range(0.62F, 0.86F), 0.0F, -1.0F, 0.0F,
            light_strip ? 1.0F : rng.range(0.52F, 0.80F)));
    }

    for (std::uint32_t i = 0; i < dust_count; ++i) {
        const float x = rng.range(-half_w, half_w);
        const float y = rng.range(0.15F, spec.height - 0.15F);
        const float z = rng.range(-half_d, half_d);
        cloud.points_.push_back(make_point(x, y, z, rng.range(0.008F, 0.024F),
            0.70F, 0.66F, 0.42F, rng.range(0.08F, 0.26F),
            0.0F, 1.0F, 0.0F, rng.range(0.12F, 0.38F)));
    }

    deterministic_shuffle(cloud.points_, rng);
    cloud.ranges_.push_back({"Pivot Room", 0U, cloud.points_.size()});
    return cloud;
}

PointCloud PointCloud::make_liminal_level(const world::LiminalLevel& level,
                                          const LiminalLevelPointSpec& spec) {
    PointCloud cloud;
    cloud.points_.reserve(spec.point_count);
    cloud.stats_.seed = spec.seed;
    cloud.stats_.total_points = spec.point_count;

    const std::uint32_t floor_count = spec.point_count * 19U / 100U;
    const std::uint32_t ceiling_count = spec.point_count * 16U / 100U;
    const std::uint32_t connection_count = level.connections().empty() ? 0U : spec.point_count * 1U / 100U;
    const std::uint32_t dust_count = spec.point_count * (level.connections().empty() ? 3U : 2U) / 100U;
    const std::uint32_t portal_count = level.portals().empty() ? 0U : spec.point_count * 3U / 100U;
    const std::uint32_t threshold_structure_count = level.threshold_envelopes().empty()
        ? 0U : spec.point_count * 3U / 100U;
    const std::uint32_t water_count = level.water_regions().empty() ? 0U : spec.point_count * 5U / 100U;
    const std::uint32_t reflection_count = level.water_regions().empty() ? 0U : spec.point_count * 2U / 100U;
    const std::uint32_t submerged_floor_count = level.water_regions().empty() ? 0U : spec.point_count * 4U / 100U;
    const std::uint32_t submerged_wall_count = level.water_regions().empty() ? 0U : spec.point_count * 4U / 100U;
    const std::uint32_t wall_count = spec.point_count - floor_count - ceiling_count - dust_count -
                                     portal_count - connection_count - threshold_structure_count -
                                     water_count - reflection_count - submerged_floor_count -
                                     submerged_wall_count;
    cloud.stats_.wall_points = wall_count;
    cloud.stats_.floor_points = floor_count;
    cloud.stats_.ceiling_points = ceiling_count;
    cloud.stats_.dust_points = dust_count;
    cloud.stats_.portal_points = portal_count;
    cloud.stats_.threshold_structure_points = threshold_structure_count;
    cloud.stats_.water_surface_points = water_count;
    cloud.stats_.water_volume_points = reflection_count;
    cloud.stats_.submerged_floor_points = submerged_floor_count;
    cloud.stats_.submerged_wall_points = submerged_wall_count;

    XorShift64 rng(spec.seed);
    std::vector<std::vector<std::size_t>> point_owners;
    point_owners.reserve(spec.point_count + connection_count);
    auto push_point = [&](PointGpu point, const std::vector<std::size_t>& owners = {}) {
        cloud.points_.push_back(std::move(point));
        point_owners.push_back(owners);
    };
    auto named_owner = [&](std::string_view name) -> std::optional<std::size_t> {
        for (std::size_t i = 0; i < level.areas().size(); ++i) {
            if (level.areas()[i].name == name) return i;
        }
        return std::nullopt;
    };
    auto specific_owner = [&](float x, float z) -> std::optional<std::size_t> {
        std::optional<std::size_t> best;
        float best_area = std::numeric_limits<float>::max();
        for (std::size_t i = 0; i < level.areas().size(); ++i) {
            const auto& area = level.areas()[i];
            if (x < area.min_x - 0.02F || x > area.max_x + 0.02F ||
                z < area.min_z - 0.02F || z > area.max_z + 0.02F) continue;
            const float size = std::max(0.001F, (area.max_x - area.min_x) *
                                                (area.max_z - area.min_z));
            if (!best || size < best_area) { best = i; best_area = size; }
        }
        return best;
    };
    auto wall_owners = [&](const world::WallSegment& wall) {
        std::vector<std::size_t> owners;
        const math::Vec3 midpoint{(wall.start.x + wall.end.x) * 0.5F, 0.0F,
                                  (wall.start.z + wall.end.z) * 0.5F};
        constexpr float probe = 0.24F;
        for (float direction : {1.0F, -1.0F}) {
            const auto owner = specific_owner(midpoint.x + wall.inward_normal.x * probe * direction,
                                              midpoint.z + wall.inward_normal.z * probe * direction);
            if (owner && std::find(owners.begin(), owners.end(), *owner) == owners.end()) {
                owners.push_back(*owner);
            }
        }
        if (owners.empty()) {
            const auto fallback = specific_owner(midpoint.x, midpoint.z);
            if (fallback) owners.push_back(*fallback);
        }
        return owners;
    };
    const auto area_weights = area_cumulative(level.areas());
    const auto wall_weights = wall_cumulative(level.walls());
    const float total_area = area_weights.empty() ? 1.0F : area_weights.back();
    const float total_wall = wall_weights.empty() ? 1.0F : wall_weights.back();

    struct ThresholdPanelCandidate {
        const world::ThresholdEnvelope* envelope{nullptr};
        const world::WallSegment* panel{nullptr};
    };
    std::vector<ThresholdPanelCandidate> threshold_panels;
    std::vector<float> threshold_panel_weights;
    float total_threshold_panel = 0.0F;
    for (const auto& envelope : level.threshold_envelopes()) {
        for (const auto& panel : envelope.panels) {
            const float weight = std::max(0.001F, segment_length(panel) *
                                                  (panel.height - panel.base_y));
            total_threshold_panel += weight;
            threshold_panels.push_back({&envelope, &panel});
            threshold_panel_weights.push_back(total_threshold_panel);
        }
    }

    struct WetWallCandidate {
        std::size_t wall_index{0};
        std::size_t water_index{0};
        float weight{0.0F};
    };
    std::vector<WetWallCandidate> wet_walls;
    std::vector<float> wet_wall_weights;
    float total_wet_wall = 0.0F;
    constexpr float wet_edge_slop = 0.08F;
    for (std::size_t water_index = 0; water_index < level.water_regions().size(); ++water_index) {
        const auto& water = level.water_regions()[water_index];
        for (std::size_t wall_index = 0; wall_index < level.walls().size(); ++wall_index) {
            const auto& wall = level.walls()[wall_index];
            const float min_x = std::min(wall.start.x, wall.end.x);
            const float max_x = std::max(wall.start.x, wall.end.x);
            const float min_z = std::min(wall.start.z, wall.end.z);
            const float max_z = std::max(wall.start.z, wall.end.z);
            if (max_x < water.min_x - wet_edge_slop ||
                min_x > water.max_x + wet_edge_slop ||
                max_z < water.min_z - wet_edge_slop ||
                min_z > water.max_z + wet_edge_slop) {
                continue;
            }
            const float submerged_low = std::max(wall.base_y, water.bottom_y);
            const float submerged_high = std::min(wall.height, water.surface_y);
            if (submerged_high <= submerged_low + 0.02F) continue;
            const float weight = std::max(0.001F, segment_length(wall) *
                                                    (submerged_high - submerged_low));
            total_wet_wall += weight;
            wet_walls.push_back({wall_index, water_index, weight});
            wet_wall_weights.push_back(total_wet_wall);
        }
    }

    auto varied = [&](float base, float amount = 0.055F) {
        return std::clamp(base + rng.range(-amount, amount), 0.03F, 1.0F);
    };

    for (std::uint32_t i = 0; i < floor_count; ++i) {
        const std::size_t index = weighted_index(area_weights, rng.range(0.0F, total_area));
        const auto& area = level.areas()[index];
        const float x = rng.range(area.min_x, area.max_x);
        const float z = rng.range(area.min_z, area.max_z);
        const int tile_x = static_cast<int>(std::floor((x - area.min_x) / 1.35F));
        const int tile_z = static_cast<int>(std::floor((z - area.min_z) / 1.35F));
        const float base = ((tile_x + tile_z) & 1) == 0 ? 0.34F : 0.285F;
        push_point(make_point(x, level.ground_height_at(x, z), z, rng.range(0.018F, 0.043F),
            varied(base), varied(base * 0.94F), varied(base * 0.70F), rng.range(0.70F, 0.98F),
            0.0F, 1.0F, 0.0F, rng.range(0.58F, 0.96F)), {index});
    }

    for (std::uint32_t i = 0; i < ceiling_count; ++i) {
        const std::size_t index = weighted_index(area_weights, rng.range(0.0F, total_area));
        const auto& area = level.areas()[index];
        const float x = rng.range(area.min_x, area.max_x);
        const float z = rng.range(area.min_z, area.max_z);
        const float local_x = x - area.min_x;
        const float local_z = z - area.min_z;
        const bool light = std::fmod(std::abs(local_x), 4.7F) < 0.34F &&
                           std::fmod(std::abs(local_z), 6.2F) < 1.65F;
        const float base = light ? 0.96F : 0.49F;
        push_point(make_point(x, level.ceiling_height(), z, rng.range(0.018F, 0.040F),
            varied(base, 0.035F), varied(base * 0.93F, 0.035F), varied(base * 0.62F, 0.035F),
            light ? 1.0F : rng.range(0.58F, 0.86F), 0.0F, -1.0F, 0.0F,
            light ? 1.0F : rng.range(0.48F, 0.82F)), {index});
    }

    const std::uint32_t obstacle_points = wall_count * 13U / 100U;
    const std::uint32_t ideal_edge_points = static_cast<std::uint32_t>(
        level.obstacles().size() * 12U * 16U);
    const std::uint32_t edge_point_budget = std::min(obstacle_points / 2U, ideal_edge_points);
    const std::uint32_t random_obstacle_points = obstacle_points - edge_point_budget;
    const std::uint32_t structural_wall_points = wall_count - obstacle_points;
    for (std::uint32_t i = 0; i < structural_wall_points; ++i) {
        const std::size_t index = weighted_index(wall_weights, rng.range(0.0F, total_wall));
        const auto& wall = level.walls()[index];
        const float t = rng.unit();
        const float x = wall.start.x + (wall.end.x - wall.start.x) * t;
        const float z = wall.start.z + (wall.end.z - wall.start.z) * t;
        const float y = rng.range(wall.base_y, wall.height);
        const float stain = 0.80F - 0.15F * std::abs(std::sin(x * 0.43F + z * 0.69F + y * 0.28F));
        push_point(make_point(x, y, z, rng.range(0.020F, 0.050F),
            varied(stain), varied(stain * 0.90F), varied(stain * 0.49F), rng.range(0.72F, 1.0F),
            wall.inward_normal.x, wall.inward_normal.y, wall.inward_normal.z, rng.range(0.64F, 1.0F)),
            wall_owners(wall));
    }

    for (std::uint32_t i = 0; i < random_obstacle_points; ++i) {
        const auto& obstacle = level.obstacles()[static_cast<std::size_t>(rng.next() % level.obstacles().size())];
        const int face = static_cast<int>(rng.next() % 5U);
        float x = 0.0F;
        float y = rng.range(0.0F, obstacle.height);
        float z = 0.0F;
        math::Vec3 normal{};
        if (face == 0) { x = obstacle.min_x; z = rng.range(obstacle.min_z, obstacle.max_z); normal = {-1.0F, 0.0F, 0.0F}; }
        else if (face == 1) { x = obstacle.max_x; z = rng.range(obstacle.min_z, obstacle.max_z); normal = {1.0F, 0.0F, 0.0F}; }
        else if (face == 2) { z = obstacle.min_z; x = rng.range(obstacle.min_x, obstacle.max_x); normal = {0.0F, 0.0F, -1.0F}; }
        else if (face == 3) { z = obstacle.max_z; x = rng.range(obstacle.min_x, obstacle.max_x); normal = {0.0F, 0.0F, 1.0F}; }
        else { x = rng.range(obstacle.min_x, obstacle.max_x); z = rng.range(obstacle.min_z, obstacle.max_z); y = obstacle.height; normal = {0.0F, 1.0F, 0.0F}; }
        float red = obstacle.height < 1.5F ? 0.31F : 0.42F;
        float green = red * 0.82F;
        float blue = red * 0.38F;
        if (obstacle.name.find("GLASS") != std::string::npos) { red = 0.18F; green = 0.64F; blue = 0.96F; }
        else if (obstacle.name.find("GREEN") != std::string::npos) { red = 0.20F; green = 0.92F; blue = 0.34F; }
        else if (obstacle.name.find("CYAN") != std::string::npos) { red = 0.18F; green = 0.86F; blue = 0.96F; }
        else if (obstacle.name.find("AMBER") != std::string::npos) { red = 0.98F; green = 0.65F; blue = 0.16F; }
        else if (obstacle.name.find("RED") != std::string::npos) { red = 0.96F; green = 0.20F; blue = 0.18F; }
        else if (obstacle.name.find("WATER EXIT") != std::string::npos) { red = 0.42F; green = 0.72F; blue = 0.96F; }
        else if (obstacle.name.find("ALMOND TECH") != std::string::npos) { red = 0.18F; green = 0.96F; blue = 0.78F; }
        else if (obstacle.name.find("SAVE JUMP") != std::string::npos) { red = 0.76F; green = 0.38F; blue = 0.98F; }
        const auto owner = specific_owner((obstacle.min_x + obstacle.max_x) * 0.5F,
                                           (obstacle.min_z + obstacle.max_z) * 0.5F);
        push_point(make_point(x, y, z, rng.range(0.022F, 0.052F),
            varied(red), varied(green), varied(blue), rng.range(0.74F, 0.98F),
            normal.x, normal.y, normal.z, rng.range(0.66F, 1.0F)),
            owner ? std::vector<std::size_t>{*owner} : std::vector<std::size_t>{});
    }

    // Pivot 12 reserves deterministic edge points for every solid obstacle.
    // The older random-face sampling could leave a box corner temporarily
    // unreadable at long distance or during signal-density changes. These edge
    // points remain sparse, but guarantee that the silhouette survives LOD.
    for (std::size_t obstacle_index = 0; obstacle_index < level.obstacles().size(); ++obstacle_index) {
        const auto& obstacle = level.obstacles()[obstacle_index];
        float red = obstacle.height < 1.5F ? 0.34F : 0.46F;
        float green = red * 0.82F;
        float blue = red * 0.42F;
        if (obstacle.name.find("GLASS") != std::string::npos) { red = 0.18F; green = 0.68F; blue = 1.0F; }
        else if (obstacle.name.find("GREEN") != std::string::npos) { red = 0.20F; green = 0.96F; blue = 0.36F; }
        else if (obstacle.name.find("CYAN") != std::string::npos) { red = 0.18F; green = 0.88F; blue = 1.0F; }
        else if (obstacle.name.find("AMBER") != std::string::npos) { red = 1.0F; green = 0.68F; blue = 0.18F; }
        else if (obstacle.name.find("RED") != std::string::npos) { red = 1.0F; green = 0.22F; blue = 0.18F; }
        else if (obstacle.name.find("THIN") != std::string::npos) { red = 0.28F; green = 0.92F; blue = 0.74F; }
        else if (obstacle.name.find("AUTO STEP") != std::string::npos) { red = 0.30F; green = 0.94F; blue = 0.42F; }
        const auto owner = specific_owner((obstacle.min_x + obstacle.max_x) * 0.5F,
                                           (obstacle.min_z + obstacle.max_z) * 0.5F);
        const std::vector<std::size_t> owners = owner
            ? std::vector<std::size_t>{*owner} : std::vector<std::size_t>{};
        const std::array<math::Vec3, 8> corners{{
            {obstacle.min_x, 0.0F, obstacle.min_z},
            {obstacle.max_x, 0.0F, obstacle.min_z},
            {obstacle.max_x, 0.0F, obstacle.max_z},
            {obstacle.min_x, 0.0F, obstacle.max_z},
            {obstacle.min_x, obstacle.height, obstacle.min_z},
            {obstacle.max_x, obstacle.height, obstacle.min_z},
            {obstacle.max_x, obstacle.height, obstacle.max_z},
            {obstacle.min_x, obstacle.height, obstacle.max_z},
        }};
        constexpr std::array<std::array<int, 2>, 12> edges{{
            {{0,1}}, {{1,2}}, {{2,3}}, {{3,0}},
            {{4,5}}, {{5,6}}, {{6,7}}, {{7,4}},
            {{0,4}}, {{1,5}}, {{2,6}}, {{3,7}},
        }};
        const std::size_t total_edges = level.obstacles().size() * edges.size();
        const std::uint32_t base_samples = total_edges == 0U ? 0U
            : edge_point_budget / static_cast<std::uint32_t>(total_edges);
        const std::uint32_t extra_samples = total_edges == 0U ? 0U
            : edge_point_budget % static_cast<std::uint32_t>(total_edges);
        for (std::size_t edge_index = 0; edge_index < edges.size(); ++edge_index) {
            const std::size_t global_edge = obstacle_index * edges.size() + edge_index;
            const std::uint32_t edge_samples = base_samples +
                (global_edge < static_cast<std::size_t>(extra_samples) ? 1U : 0U);
            if (edge_samples == 0U) continue;
            const auto a = corners[static_cast<std::size_t>(edges[edge_index][0])];
            const auto b = corners[static_cast<std::size_t>(edges[edge_index][1])];
            for (std::uint32_t sample = 0; sample < edge_samples; ++sample) {
                const float t = edge_samples == 1U ? 0.5F :
                    static_cast<float>(sample) / static_cast<float>(edge_samples - 1U);
                const auto p = a + (b - a) * t;
                push_point(make_point(p.x, p.y, p.z, 0.030F,
                    red, green, blue, 0.92F, 0.0F, 1.0F, 0.0F, 1.18F), owners);
            }
        }
    }

    // Pivot 8 a2 reserves a deterministic portion of the point budget for the
    // structural envelopes surrounding every physical connection. These points
    // are owned by both rooms, so a wall, sill, or lintel cannot vanish when the
    // active streamed room changes.
    if (!threshold_panels.empty()) {
        for (std::uint32_t i = 0; i < threshold_structure_count; ++i) {
            const std::size_t candidate_index = weighted_index(
                threshold_panel_weights, rng.range(0.0F, total_threshold_panel));
            const auto& candidate = threshold_panels[candidate_index];
            const auto& panel = *candidate.panel;
            const float t = rng.unit();
            const float x = panel.start.x + (panel.end.x - panel.start.x) * t;
            const float z = panel.start.z + (panel.end.z - panel.start.z) * t;
            const float y = rng.range(panel.base_y, panel.height);
            const float stain = 0.83F - 0.12F *
                std::abs(std::sin(x * 0.41F + z * 0.67F + y * 0.31F));
            std::vector<std::size_t> owners;
            if (const auto owner = named_owner(candidate.envelope->zone_a)) owners.push_back(*owner);
            if (const auto owner = named_owner(candidate.envelope->zone_b);
                owner && std::find(owners.begin(), owners.end(), *owner) == owners.end()) {
                owners.push_back(*owner);
            }
            push_point(make_point(x, y, z, rng.range(0.019F, 0.046F),
                varied(stain, 0.035F), varied(stain * 0.91F, 0.035F),
                varied(stain * 0.51F, 0.035F), rng.range(0.78F, 1.0F),
                panel.inward_normal.x, panel.inward_normal.y, panel.inward_normal.z,
                rng.range(0.78F, 1.0F)), std::move(owners));
        }
    }

    for (std::uint32_t i = 0; i < portal_count; ++i) {
        const auto& portal = level.portals()[static_cast<std::size_t>(rng.next() % level.portals().size())];
        const math::Vec3 tangent{-portal.inward_normal.z, 0.0F, portal.inward_normal.x};
        const int frame_part = static_cast<int>(rng.next() % 3U);
        float lateral = 0.0F;
        float y = 0.0F;
        if (frame_part == 0) {
            lateral = -portal.half_width;
            y = rng.range(0.0F, portal.height);
        } else if (frame_part == 1) {
            lateral = portal.half_width;
            y = rng.range(0.0F, portal.height);
        } else {
            lateral = rng.range(-portal.half_width, portal.half_width);
            y = portal.height;
        }
        const math::Vec3 position = portal.center + tangent * lateral + portal.inward_normal * 0.025F;
        const bool window = portal.kind == world::PortalKind::window;
        const bool drop = portal.kind == world::PortalKind::drop;
        const float red = drop ? 0.92F : (window ? 0.48F : 0.22F);
        const float green = drop ? 0.31F : (window ? 0.38F : 0.92F);
        const float blue = drop ? 0.28F : (window ? 0.98F : 0.78F);
        const auto owner = named_owner(portal.source_zone);
        push_point(make_point(position.x, y, position.z, rng.range(0.040F, 0.082F),
            varied(red, 0.025F), varied(green, 0.025F), varied(blue, 0.025F), rng.range(0.88F, 1.0F),
            portal.inward_normal.x, portal.inward_normal.y, portal.inward_normal.z, rng.range(0.88F, 1.0F)),
            owner ? std::vector<std::size_t>{*owner} : std::vector<std::size_t>{});
    }


    for (std::uint32_t i = 0; i < connection_count; ++i) {
        const auto& connection = level.connections()[static_cast<std::size_t>(rng.next() % level.connections().size())];
        const world::ThresholdEnvelope* envelope = nullptr;
        for (const auto& candidate : level.threshold_envelopes()) {
            if (candidate.zone_a == connection.zone_a && candidate.zone_b == connection.zone_b) {
                envelope = &candidate;
                break;
            }
        }
        const auto aperture = envelope != nullptr
            ? envelope->aperture
            : level.connection_aperture(connection, connection.zone_a);
        const math::Vec3 tangent{-aperture.normal.z, 0.0F, aperture.normal.x};
        const int frame_part = static_cast<int>(rng.next() % 4U);
        float lateral = 0.0F;
        float y = aperture.bottom_y;
        if (frame_part == 0) {
            lateral = -aperture.half_width;
            y = rng.range(aperture.bottom_y, aperture.top_y);
        } else if (frame_part == 1) {
            lateral = aperture.half_width;
            y = rng.range(aperture.bottom_y, aperture.top_y);
        } else if (frame_part == 2) {
            lateral = rng.range(-aperture.half_width, aperture.half_width);
            y = aperture.top_y;
        } else {
            lateral = rng.range(-aperture.half_width, aperture.half_width);
            y = aperture.bottom_y;
        }
        const math::Vec3 position = aperture.center + tangent * lateral;
        float red = 0.78F;
        float green = 0.74F;
        float blue = 0.46F;
        if (connection.kind == world::ConnectionKind::framed_doorway) { red = 0.28F; green = 0.88F; blue = 0.80F; }
        else if (connection.kind == world::ConnectionKind::window) { red = 0.24F; green = 0.70F; blue = 0.98F; }
        else if (connection.kind == world::ConnectionKind::hole) { red = 0.72F; green = 0.28F; blue = 0.92F; }
        else if (connection.kind == world::ConnectionKind::passage) { red = 0.86F; green = 0.60F; blue = 0.32F; }
        else if (connection.kind == world::ConnectionKind::glass) { red = 0.20F; green = 0.64F; blue = 0.98F; }
        std::vector<std::size_t> owners;
        if (const auto owner = named_owner(connection.zone_a)) owners.push_back(*owner);
        if (const auto owner = named_owner(connection.zone_b);
            owner && std::find(owners.begin(), owners.end(), *owner) == owners.end()) owners.push_back(*owner);
        push_point(make_point(position.x, y, position.z, rng.range(0.032F, 0.072F),
            varied(red, 0.025F), varied(green, 0.025F), varied(blue, 0.025F),
            rng.range(0.82F, 1.0F), aperture.normal.x, 0.0F, aperture.normal.z,
            rng.range(0.82F, 1.0F)), owners);
    }

    for (std::uint32_t i = 0; i < water_count; ++i) {
        const auto& water = level.water_regions()[static_cast<std::size_t>(rng.next() % level.water_regions().size())];
        const float x = rng.range(water.min_x, water.max_x);
        const float z = rng.range(water.min_z, water.max_z);
        const bool deep = water.bottom_y < -1.5F;
        const float thickness = std::clamp((water.viscosity - 0.75F) / 0.90F, 0.0F, 1.0F);
        const float blue = deep ? 0.68F : 0.80F;
        const float green = 0.34F + thickness * 0.38F;
        const float red = 0.10F + thickness * 0.10F;
        const auto owner = specific_owner(x, z);
        push_point(make_point(x, water.surface_y, z, rng.range(0.020F, 0.052F),
            varied(red, 0.025F), varied(green, 0.035F), varied(blue - thickness * 0.24F, 0.045F),
            rng.range(0.38F, 0.76F), 0.0F, 1.0F, 0.0F,
            -rng.range(0.62F, 1.0F) * water.viscosity),
            owner ? std::vector<std::size_t>{*owner} : std::vector<std::size_t>{});
    }

    for (std::uint32_t i = 0; i < reflection_count; ++i) {
        const auto& water = level.water_regions()[static_cast<std::size_t>(rng.next() % level.water_regions().size())];
        const float x = rng.range(water.min_x, water.max_x);
        const float z = rng.range(water.min_z, water.max_z);
        const float y = water.surface_y - rng.range(0.06F, std::min(1.6F, water.surface_y - water.bottom_y));
        const float stripe = 0.5F + 0.5F * std::sin(x * 0.7F + z * 0.4F);
        const auto owner = specific_owner(x, z);
        push_point(make_point(x, y, z, rng.range(0.014F, 0.038F),
            varied(0.34F + stripe * 0.18F), varied(0.42F + stripe * 0.18F), varied(0.52F + stripe * 0.20F),
            rng.range(0.10F, 0.32F), 0.0F, -1.0F, 0.0F, -rng.range(0.22F, 0.52F)),
            owner ? std::vector<std::size_t>{*owner} : std::vector<std::size_t>{});
    }

    // Pivot 8 adds a persistent submerged substrate. These points are not a
    // second water surface: they cling to the bottom and to authored wall
    // segments that actually intersect the water volume. Because the wall layer
    // is sampled from real structural segments, doorway and corridor apertures
    // remain open instead of being filled by a rectangular water-box shell.
    const std::uint32_t effective_submerged_floor_count = submerged_floor_count +
        (wet_walls.empty() ? submerged_wall_count : 0U);
    for (std::uint32_t i = 0; i < effective_submerged_floor_count; ++i) {
        const auto& water = level.water_regions()[
            static_cast<std::size_t>(rng.next() % level.water_regions().size())];
        const float x = rng.range(water.min_x, water.max_x);
        const float z = rng.range(water.min_z, water.max_z);
        const float thickness = std::clamp((water.viscosity - 0.75F) / 0.90F, 0.0F, 1.0F);
        const float depth = std::max(0.2F, water.surface_y - water.bottom_y);
        const float blue = 0.60F + std::min(0.18F, depth * 0.012F);
        const float green = 0.28F + thickness * 0.34F;
        const float red = 0.045F + thickness * 0.075F;
        const auto owner = specific_owner(x, z);
        push_point(make_point(x, water.bottom_y + rng.range(0.008F, 0.032F), z,
            rng.range(0.018F, 0.046F),
            varied(red, 0.018F), varied(green, 0.030F), varied(blue, 0.038F),
            rng.range(0.30F, 0.66F), 0.0F, 1.0F, 0.0F,
            -rng.range(1.16F, 1.52F) * water.viscosity),
            owner ? std::vector<std::size_t>{*owner} : std::vector<std::size_t>{});
    }

    if (!wet_walls.empty()) {
        for (std::uint32_t i = 0; i < submerged_wall_count; ++i) {
            const std::size_t candidate_index = weighted_index(
                wet_wall_weights, rng.range(0.0F, total_wet_wall));
            const auto& candidate = wet_walls[candidate_index];
            const auto& wall = level.walls()[candidate.wall_index];
            const auto& water = level.water_regions()[candidate.water_index];
            const float t = rng.unit();
            const float x = wall.start.x + (wall.end.x - wall.start.x) * t;
            const float z = wall.start.z + (wall.end.z - wall.start.z) * t;
            const float low = std::max(wall.base_y, water.bottom_y);
            const float high = std::min(wall.height, water.surface_y);
            const float y = rng.range(low, high);
            const float thickness = std::clamp((water.viscosity - 0.75F) / 0.90F, 0.0F, 1.0F);
            const float depth_ratio = std::clamp(
                (water.surface_y - y) /
                    std::max(0.20F, water.surface_y - water.bottom_y),
                0.0F, 1.0F);
            const float red = 0.055F + thickness * 0.060F;
            const float green = 0.30F + thickness * 0.30F + depth_ratio * 0.05F;
            const float blue = 0.66F - thickness * 0.12F + depth_ratio * 0.08F;
            auto owners = wall_owners(wall);
            if (level.connections().empty() && owners.size() > 1U) owners.resize(1U);
            push_point(make_point(x, y, z, rng.range(0.018F, 0.046F),
                varied(red, 0.018F), varied(green, 0.028F), varied(blue, 0.035F),
                rng.range(0.26F, 0.60F),
                wall.inward_normal.x, wall.inward_normal.y, wall.inward_normal.z,
                -rng.range(1.18F, 1.62F) * water.viscosity),
                std::move(owners));
        }
    }

    for (std::uint32_t i = 0; i < dust_count; ++i) {
        const std::size_t index = weighted_index(area_weights, rng.range(0.0F, total_area));
        const auto& area = level.areas()[index];
        push_point(make_point(rng.range(area.min_x, area.max_x),
            rng.range(0.18F, level.ceiling_height() - 0.18F), rng.range(area.min_z, area.max_z),
            rng.range(0.006F, 0.020F), 0.69F, 0.66F, 0.43F, rng.range(0.05F, 0.22F),
            0.0F, 1.0F, 0.0F, rng.range(0.10F, 0.34F)), {index});
    }

    // Pivot 6 keeps the full tape resident, groups ordinary rooms into one
    // contiguous range, and splits only very long/large test spaces into spatial
    // bands. This makes draw-distance submission measurable without changing the
    // accepted one-range behavior for earlier procedural rooms.
    std::vector<std::vector<PointGpu>> room_points(level.areas().size());
    auto room_index = [&](const PointGpu& point) -> std::size_t {
        const float x = point.position[0];
        const float z = point.position[2];
        constexpr float edge_slop = 0.12F;
        for (std::size_t i = 0; i < level.areas().size(); ++i) {
            const auto& area = level.areas()[i];
            if (x >= area.min_x - edge_slop && x <= area.max_x + edge_slop &&
                z >= area.min_z - edge_slop && z <= area.max_z + edge_slop) return i;
        }
        std::size_t best = 0U;
        float best_distance = std::numeric_limits<float>::max();
        for (std::size_t i = 0; i < level.areas().size(); ++i) {
            const auto& area = level.areas()[i];
            const float cx = (area.min_x + area.max_x) * 0.5F;
            const float cz = (area.min_z + area.max_z) * 0.5F;
            const float dx = x - cx;
            const float dz = z - cz;
            const float distance = dx * dx + dz * dz;
            if (distance < best_distance) { best_distance = distance; best = i; }
        }
        return best;
    };
    for (std::size_t point_index = 0; point_index < cloud.points_.size(); ++point_index) {
        const auto& owners = point_owners[point_index];
        if (owners.empty()) {
            room_points[room_index(cloud.points_[point_index])].push_back(std::move(cloud.points_[point_index]));
            continue;
        }
        for (std::size_t owner_index = 0; owner_index < owners.size(); ++owner_index) {
            if (owners[owner_index] >= room_points.size()) continue;
            if (owner_index + 1U == owners.size()) {
                room_points[owners[owner_index]].push_back(std::move(cloud.points_[point_index]));
            } else {
                room_points[owners[owner_index]].push_back(cloud.points_[point_index]);
            }
        }
    }
    cloud.points_.clear();
    cloud.points_.reserve(spec.point_count + connection_count * 2U);
    cloud.ranges_.clear();

    auto is_connected_complex = [](std::string_view name) {
        return name == "Traversal & Water Lab" || name == "Fallen Office" ||
               name == "Corridor Junction" || name == "Nested Room Matrix" ||
               name == "Long Signal Hall" || name == "Vertical Flood Shaft" ||
               name == "Submerged Service Tunnel" || name == "Open Pressure Cavity" ||
               name == "Threshold Gallery" || name == "Raised Window Annex" ||
               name == "Broken Passage Annex" || name == "Submerged Boundary Lab";
    };

    const bool supports_continuity = !level.connections().empty();
    for (std::size_t i = 0; i < room_points.size(); ++i) {
        const auto& area = level.areas()[i];
        const float width = area.max_x - area.min_x;
        const float depth = area.max_z - area.min_z;
        const bool split_x = width >= depth;
        const float long_dimension = std::max(width, depth);
        const bool banded = supports_continuity &&
                            (is_connected_complex(area.name) || long_dimension >= 36.0F);
        const std::size_t band_count = banded
            ? std::clamp<std::size_t>(
                static_cast<std::size_t>(std::ceil(long_dimension / 15.0F)), 2U, 10U)
            : 1U;
        std::vector<std::vector<PointGpu>> bands(band_count);
        for (auto& point : room_points[i]) {
            const float coordinate = split_x ? point.position[0] : point.position[2];
            const float low = split_x ? area.min_x : area.min_z;
            const float normalized = std::clamp((coordinate - low) / std::max(0.001F, long_dimension),
                                                0.0F, 0.999999F);
            const std::size_t band = std::min<std::size_t>(
                band_count - 1U, static_cast<std::size_t>(normalized * static_cast<float>(band_count)));
            bands[band].push_back(std::move(point));
        }
        for (std::size_t band = 0; band < bands.size(); ++band) {
            order_for_progressive_fill(bands[band], rng);
            const std::size_t first = cloud.points_.size();
            cloud.points_.insert(cloud.points_.end(),
                                 std::make_move_iterator(bands[band].begin()),
                                 std::make_move_iterator(bands[band].end()));
            const float fraction0 = static_cast<float>(band) / static_cast<float>(band_count);
            const float fraction1 = static_cast<float>(band + 1U) / static_cast<float>(band_count);
            const float center_coordinate = (split_x ? area.min_x : area.min_z) +
                                            long_dimension * (fraction0 + fraction1) * 0.5F;
            math::Vec3 center{
                split_x ? center_coordinate : (area.min_x + area.max_x) * 0.5F,
                0.0F,
                split_x ? (area.min_z + area.max_z) * 0.5F : center_coordinate
            };
            const float band_length = long_dimension / static_cast<float>(band_count);
            const float short_dimension = std::min(width, depth);
            const float radius = 0.5F * std::sqrt(band_length * band_length +
                                                  short_dimension * short_dimension);
            cloud.ranges_.push_back({area.name, first, bands[band].size(), center, radius});
        }
    }
    cloud.stats_.total_points = static_cast<std::uint32_t>(
        std::min<std::size_t>(cloud.points_.size(), std::numeric_limits<std::uint32_t>::max()));
    return cloud;
}

const PointRange* PointCloud::range_for(std::string_view zone) const noexcept {
    for (const auto& range : ranges_) if (range.zone == zone) return &range;
    return nullptr;
}

std::vector<const PointRange*> PointCloud::ranges_for(std::string_view zone) const {
    std::vector<const PointRange*> result;
    for (const auto& range : ranges_) {
        if (range.zone == zone) result.push_back(&range);
    }
    return result;
}

bool PointCloud::finite() const noexcept {
    for (const PointGpu& point : points_) {
        for (float value : point.position) if (!std::isfinite(value)) return false;
        for (float value : point.color) if (!std::isfinite(value)) return false;
        for (float value : point.normal) if (!std::isfinite(value)) return false;
        if (!std::isfinite(point.radius) || !std::isfinite(point.density)) return false;
    }
    return true;
}

}  // namespace signalcloud::render
