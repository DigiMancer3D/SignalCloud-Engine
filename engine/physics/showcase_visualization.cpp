#include "engine/physics/showcase_visualization.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>

namespace signalcloud::physics {
namespace {

using render::PointGpu;
using math::Vec3;

constexpr float kTau = 6.28318530717958647692F;
constexpr float kStageHalf = 7.5F;

PointGpu make_point(Vec3 position, float radius, std::array<float, 4> color,
                    float density = 1.0F) noexcept {
    return {{position.x, position.y, position.z}, radius,
            {color[0], color[1], color[2], color[3]},
            {0.0F, 1.0F, 0.0F}, density};
}

Vec3 rotate_y(Vec3 value, float yaw) noexcept {
    const float c = std::cos(yaw);
    const float s = std::sin(yaw);
    return {value.x * c - value.z * s, value.y, value.x * s + value.z * c};
}

void append_line(std::vector<PointGpu>& out, Vec3 a, Vec3 b,
                 std::array<float, 4> color, float radius = 0.012F,
                 float spacing = 0.075F, float density = 4.10F) {
    const Vec3 delta = b - a;
    const float distance = math::length(delta);
    const std::size_t steps = std::max<std::size_t>(2U,
        static_cast<std::size_t>(std::ceil(distance / std::max(0.01F, spacing))));
    for (std::size_t index = 0; index <= steps; ++index) {
        const float t = static_cast<float>(index) / static_cast<float>(steps);
        out.push_back(make_point(a + delta * t, radius, color, density));
    }
}

void append_circle(std::vector<PointGpu>& out, Vec3 center, float radius,
                   int axis, std::array<float, 4> color,
                   float point_radius = 0.012F) {
    constexpr std::size_t samples = 96U;
    for (std::size_t index = 0; index < samples; ++index) {
        const float angle = kTau * static_cast<float>(index) / static_cast<float>(samples);
        Vec3 p = center;
        const float c = std::cos(angle) * radius;
        const float s = std::sin(angle) * radius;
        if (axis == 0) { p.y += c; p.z += s; }
        else if (axis == 1) { p.x += c; p.z += s; }
        else { p.x += c; p.y += s; }
        out.push_back(make_point(p, point_radius, color, 4.10F));
    }
}

void append_box_outline(std::vector<PointGpu>& out, Vec3 center, Vec3 half,
                        float yaw, std::array<float, 4> color) {
    const std::array<Vec3, 8> local{{
        {-half.x, -half.y, -half.z}, { half.x, -half.y, -half.z},
        { half.x,  half.y, -half.z}, {-half.x,  half.y, -half.z},
        {-half.x, -half.y,  half.z}, { half.x, -half.y,  half.z},
        { half.x,  half.y,  half.z}, {-half.x,  half.y,  half.z},
    }};
    std::array<Vec3, 8> corners{};
    for (std::size_t index = 0; index < local.size(); ++index) {
        corners[index] = center + rotate_y(local[index], yaw);
    }
    constexpr std::array<std::array<int, 2>, 12> edges{{
        {{0,1}}, {{1,2}}, {{2,3}}, {{3,0}},
        {{4,5}}, {{5,6}}, {{6,7}}, {{7,4}},
        {{0,4}}, {{1,5}}, {{2,6}}, {{3,7}},
    }};
    for (const auto& edge : edges) append_line(out, corners[edge[0]], corners[edge[1]], color);
}

void append_collision(std::vector<PointGpu>& out, const PhysicsProfile& raw_profile,
                      const ShowcaseState& state) {
    const PhysicsProfile profile = normalize_profile(raw_profile);
    const Vec3 center = state.position;
    const std::array<float, 4> color{0.20F, 0.94F, 0.84F, 0.96F};
    if (profile.shape == "sphere") {
        append_circle(out, center, profile.collision_radius, 0, color);
        append_circle(out, center, profile.collision_radius, 1, color);
        append_circle(out, center, profile.collision_radius, 2, color);
    } else if (profile.shape == "capsule") {
        const float radius = profile.collision_radius;
        const float half_body = profile.collision_half_extents.y;
        const Vec3 top{center.x, center.y + half_body, center.z};
        const Vec3 bottom{center.x, center.y - half_body, center.z};
        append_circle(out, top, radius, 1, color);
        append_circle(out, bottom, radius, 1, color);
        append_circle(out, top, radius, 0, color);
        append_circle(out, bottom, radius, 0, color);
        for (const float sx : {-1.0F, 1.0F}) {
            for (const float sz : {-1.0F, 1.0F}) {
                const Vec3 local{sx * radius, 0.0F, sz * radius};
                append_line(out, bottom + rotate_y(local, state.yaw_radians),
                            top + rotate_y(local, state.yaw_radians), color);
            }
        }
    } else {
        append_box_outline(out, center, profile.collision_half_extents,
                           state.yaw_radians, color);
    }
}

std::array<float, 4> density_color(float density) noexcept {
    const float normalized = std::clamp((density + 1.0F) / 5.0F, 0.0F, 1.0F);
    return {0.16F + 0.84F * normalized,
            0.92F - 0.58F * normalized,
            0.96F - 0.74F * normalized, 1.0F};
}

std::array<float, 4> material_color(const PointGpu& point, float time) noexcept {
    const float grain = 0.5F + 0.5F * std::sin(
        point.position[0] * 2.19F + point.position[1] * 1.37F +
        point.position[2] * 1.71F + time * 0.35F);
    return {std::clamp(point.color[0] * (0.74F + 0.30F * grain) + 0.04F, 0.0F, 1.0F),
            std::clamp(point.color[1] * (0.70F + 0.22F * grain) + 0.07F, 0.0F, 1.0F),
            std::clamp(point.color[2] * (0.68F + 0.38F * grain) + 0.11F, 0.0F, 1.0F),
            point.color[3]};
}

std::array<float, 4> light_color(const PointGpu& point, Vec3 position, float time) noexcept {
    const Vec3 light{std::cos(time * 0.63F) * 4.0F, 5.6F,
                     std::sin(time * 0.63F) * 4.0F};
    const float distance = math::length(position - light);
    const float amount = std::clamp(1.0F - distance / 9.0F, 0.12F, 1.0F);
    return {std::clamp(point.color[0] * (0.28F + amount * 1.05F), 0.0F, 1.0F),
            std::clamp(point.color[1] * (0.24F + amount * 0.92F), 0.0F, 1.0F),
            std::clamp(point.color[2] * (0.32F + amount * 1.22F), 0.0F, 1.0F),
            point.color[3]};
}

void append_stage(std::vector<PointGpu>& out) {
    constexpr int half = 8;
    constexpr int samples = 64;
    for (int line = -half; line <= half; ++line) {
        const float axis = static_cast<float>(line);
        const float bright = line == 0 ? 0.54F : 0.20F;
        for (int index = 0; index <= samples; ++index) {
            const float value = -static_cast<float>(half) + 2.0F * static_cast<float>(half) *
                                static_cast<float>(index) / static_cast<float>(samples);
            out.push_back(make_point({axis, 0.0F, value}, 0.008F,
                {bright * 0.75F, bright * 0.90F, bright, 0.58F}, 0.88F));
            out.push_back(make_point({value, 0.0F, axis}, 0.008F,
                {bright * 0.75F, bright * 0.90F, bright, 0.58F}, 0.88F));
        }
    }
    const std::array<float, 4> boundary{0.64F, 0.32F, 0.22F, 0.78F};
    append_line(out, {-kStageHalf, 0.02F, -kStageHalf}, { kStageHalf, 0.02F, -kStageHalf}, boundary, 0.010F);
    append_line(out, { kStageHalf, 0.02F, -kStageHalf}, { kStageHalf, 0.02F,  kStageHalf}, boundary, 0.010F);
    append_line(out, { kStageHalf, 0.02F,  kStageHalf}, {-kStageHalf, 0.02F,  kStageHalf}, boundary, 0.010F);
    append_line(out, {-kStageHalf, 0.02F,  kStageHalf}, {-kStageHalf, 0.02F, -kStageHalf}, boundary, 0.010F);
    append_line(out, {0.0F, 0.0F, 0.0F}, {2.2F, 0.0F, 0.0F}, {0.96F, 0.22F, 0.22F, 0.95F}, 0.014F);
    append_line(out, {0.0F, 0.0F, 0.0F}, {0.0F, 2.2F, 0.0F}, {0.24F, 0.96F, 0.36F, 0.95F}, 0.014F);
    append_line(out, {0.0F, 0.0F, 0.0F}, {0.0F, 0.0F, 2.2F}, {0.28F, 0.52F, 1.0F, 0.95F}, 0.014F);
}

Vec3 actor_deform(Vec3 local, const ShowcaseBounds& bounds, float time) noexcept {
    const float height = std::max(0.001F, bounds.maximum.y - bounds.minimum.y);
    const float vertical = std::clamp((local.y + bounds.half_extents.y) / height, 0.0F, 1.0F);
    const float phase = time * 2.35F;
    const float width = std::max(0.25F, bounds.half_extents.x);
    const float depth = std::max(0.20F, bounds.half_extents.z);
    const float planted_t = std::clamp((vertical - 0.02F) / 0.23F, 0.0F, 1.0F);
    const float planted = planted_t * planted_t * (3.0F - 2.0F * planted_t);
    local.x += std::sin(phase + vertical * 2.8F) * width * 0.22F * planted;
    local.z += std::cos(phase * 0.77F + vertical * 3.6F) * depth * 0.18F * planted;
    local.y += std::sin(phase * 1.35F + vertical * 5.0F) * height * 0.035F * planted;
    const float twist = std::sin(phase * 0.82F) * 0.42F * vertical;
    return rotate_y(local, twist);
}

}  // namespace

ShowcaseBounds showcase_bounds(const std::vector<PointGpu>& points) noexcept {
    ShowcaseBounds result;
    if (points.empty()) return result;
    Vec3 minimum{std::numeric_limits<float>::max(), std::numeric_limits<float>::max(),
                 std::numeric_limits<float>::max()};
    Vec3 maximum{std::numeric_limits<float>::lowest(), std::numeric_limits<float>::lowest(),
                 std::numeric_limits<float>::lowest()};
    std::size_t finite_count = 0U;
    for (const auto& point : points) {
        const Vec3 p{point.position[0], point.position[1], point.position[2]};
        if (!std::isfinite(p.x) || !std::isfinite(p.y) || !std::isfinite(p.z)) continue;
        minimum.x = std::min(minimum.x, p.x);
        minimum.y = std::min(minimum.y, p.y);
        minimum.z = std::min(minimum.z, p.z);
        maximum.x = std::max(maximum.x, p.x);
        maximum.y = std::max(maximum.y, p.y);
        maximum.z = std::max(maximum.z, p.z);
        ++finite_count;
    }
    if (finite_count == 0U) return result;
    result.minimum = minimum;
    result.maximum = maximum;
    result.center = (minimum + maximum) * 0.5F;
    result.half_extents = {
        std::max(0.02F, (maximum.x - minimum.x) * 0.5F),
        std::max(0.02F, (maximum.y - minimum.y) * 0.5F),
        std::max(0.02F, (maximum.z - minimum.z) * 0.5F),
    };
    result.radius = std::max(0.02F, math::length(result.half_extents));
    result.valid = true;
    return result;
}

ShowcaseViewMode parse_showcase_view_mode(std::string_view value) noexcept {
    if (value == "density") return ShowcaseViewMode::density;
    if (value == "material") return ShowcaseViewMode::material;
    if (value == "light") return ShowcaseViewMode::light;
    return ShowcaseViewMode::source;
}

std::string_view showcase_view_mode_name(ShowcaseViewMode mode) noexcept {
    switch (mode) {
        case ShowcaseViewMode::density: return "density";
        case ShowcaseViewMode::material: return "material";
        case ShowcaseViewMode::light: return "light";
        case ShowcaseViewMode::source: return "source";
    }
    return "source";
}

std::size_t showcase_lod_count(std::size_t source_count, float lod_fraction) noexcept {
    if (source_count == 0U) return 0U;
    const float safe = std::clamp(std::isfinite(lod_fraction) ? lod_fraction : 1.0F,
                                  0.01F, 1.0F);
    return std::max<std::size_t>(1U, static_cast<std::size_t>(
        std::ceil(static_cast<double>(source_count) * static_cast<double>(safe))));
}

std::vector<PointGpu> build_showcase_frame_points(
    const std::vector<PointGpu>& source, const ShowcaseBounds& bounds,
    const PhysicsProfile& raw_profile, const ShowcaseState& state,
    const ShowcaseVisualizationOptions& raw_options, float time_seconds) {
    ShowcaseVisualizationOptions options = raw_options;
    options.lod_fraction = std::clamp(std::isfinite(options.lod_fraction) ? options.lod_fraction : 1.0F,
                                      0.01F, 1.0F);
    options.point_scale = std::clamp(std::isfinite(options.point_scale) ? options.point_scale : 1.0F,
                                    0.25F, 4.0F);
    const PhysicsProfile profile = normalize_profile(raw_profile);
    std::vector<PointGpu> output;
    append_stage(output);
    if (source.empty() || !bounds.valid) {
        if (options.collision_outline) append_collision(output, profile, state);
        return output;
    }

    const std::size_t target_count = showcase_lod_count(source.size(), options.lod_fraction);
    const double stride = static_cast<double>(source.size()) / static_cast<double>(target_count);
    output.reserve(output.size() + target_count + 2600U);
    const float actor_bob = options.actor_preview ? 0.10F * std::sin(time_seconds * 2.7F) : 0.0F;
    for (std::size_t draw_index = 0U; draw_index < target_count; ++draw_index) {
        const std::size_t source_index = std::min(source.size() - 1U,
            static_cast<std::size_t>(std::floor(static_cast<double>(draw_index) * stride)));
        PointGpu point = source[source_index];
        Vec3 local{point.position[0] - bounds.center.x,
                   point.position[1] - bounds.center.y,
                   point.position[2] - bounds.center.z};
        if (options.actor_preview) local = actor_deform(local, bounds, time_seconds);
        local = rotate_y(local, state.yaw_radians);
        Vec3 position = local + state.position + Vec3{0.0F, actor_bob, 0.0F};
        point.position[0] = position.x;
        point.position[1] = position.y;
        point.position[2] = position.z;
        // PCP3 authoring radii are editor-friendly values. The native renderer
        // expects world-space radii that it converts into point-sprite pixels.
        // Normalizing once here prevents every starter from becoming a field
        // of 52-pixel discs while retaining the user point-scale control.
        point.radius = std::clamp(point.radius * 0.012F, 0.006F, 0.032F);
        std::array<float, 4> color{point.color[0], point.color[1], point.color[2], point.color[3]};
        if (options.view_mode == ShowcaseViewMode::density) color = density_color(point.density);
        else if (options.view_mode == ShowcaseViewMode::material) color = material_color(point, time_seconds);
        else if (options.view_mode == ShowcaseViewMode::light) color = light_color(point, position, time_seconds);
        if (options.actor_preview) {
            const float pulse = 0.88F + 0.12F * std::sin(time_seconds * 3.0F + static_cast<float>(source_index) * 0.013F);
            color[1] = std::min(1.0F, color[1] * pulse + 0.05F);
            color[2] = std::min(1.0F, color[2] * (1.06F + 0.08F * pulse));
        }
        if (state.broken) {
            color[0] = std::min(1.0F, color[0] * 1.18F + 0.18F);
            color[1] *= 0.70F;
            color[2] *= 0.70F;
            const float scatter = 0.05F + 0.12F * std::sin(static_cast<float>(source_index) * 1.618F);
            point.position[0] += local.x * scatter;
            point.position[2] += local.z * scatter;
        }
        for (int channel = 0; channel < 4; ++channel) point.color[channel] = color[channel];
        output.push_back(point);
    }

    if (options.collision_outline) append_collision(output, profile, state);

    // Motion evidence remains in stage space even when camera follow is on.
    const Vec3 floor_marker{state.position.x, 0.025F, state.position.z};
    append_circle(output, floor_marker, 0.22F, 1, {1.0F, 0.66F, 0.22F, 0.92F}, 0.010F);
    const float speed = math::length(state.velocity);
    if (speed > 0.05F) {
        append_line(output, state.position,
                    state.position + state.velocity * (1.35F / std::max(1.0F, speed)),
                    {1.0F, 0.72F, 0.26F, 0.95F}, 0.012F);
    }
    if (options.actor_preview) {
        append_circle(output, state.position + Vec3{0.0F, showcase_support_height(profile) + 0.55F, 0.0F},
                      0.34F, 1, {0.60F, 0.44F, 1.0F, 0.92F}, 0.010F);
    }
    if (options.view_mode == ShowcaseViewMode::light) {
        const Vec3 light{std::cos(time_seconds * 0.63F) * 4.0F, 5.6F,
                         std::sin(time_seconds * 0.63F) * 4.0F};
        append_circle(output, light, 0.24F, 0, {1.0F, 0.88F, 0.36F, 1.0F}, 0.012F);
        append_circle(output, light, 0.24F, 1, {1.0F, 0.88F, 0.36F, 1.0F}, 0.012F);
    }
    return output;
}

}  // namespace signalcloud::physics
