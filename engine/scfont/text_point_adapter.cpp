#include "engine/scfont/text_point_adapter.hpp"

#include <algorithm>
#include <cmath>

namespace signalcloud::font {
namespace {

render::PointGpu make_point(const PositionedPoint& source, math::Vec3 position,
                            const TextPointStyle& style) noexcept {
    const Rgba packed = unpack_rgba(source.color);
    const float r = style.replace_rgb ? style.tint[0] : packed.r * style.tint[0];
    const float g = style.replace_rgb ? style.tint[1] : packed.g * style.tint[1];
    const float b = style.replace_rgb ? style.tint[2] : packed.b * style.tint[2];
    const float alpha = std::clamp(source.alpha * packed.a * style.opacity, 0.0F, 1.0F);
    const float radius = std::max(0.00025F, style.point_radius);
    return {{position.x, position.y, position.z}, radius,
            {std::clamp(r, 0.0F, 1.0F), std::clamp(g, 0.0F, 1.0F),
             std::clamp(b, 0.0F, 1.0F), alpha},
            {0.0F, 1.0F, 0.0F}, style.density};
}

std::size_t append_points(std::vector<render::PointGpu>& output, const Font& font,
                          std::string_view text, const TextBasis& basis, float scale,
                          const TextPointStyle& style, std::size_t maximum_points,
                          bool rich) {
    if (maximum_points == 0U) return 0U;
    const LayoutResult layout = layout_utf8(font, text, scale, maximum_points);
    const std::size_t before = output.size();
    output.reserve(output.size() + layout.points.size());
    for (const auto& source : layout.points) {
        math::Vec3 position = basis.origin + basis.right * source.x - basis.up * source.y;
        if (rich) position = position + basis.depth * source.z;
        output.push_back(make_point(source, position, style));
    }
    return output.size() - before;
}

}  // namespace

DistanceEasedBillboardPlacement distance_eased_billboard_placement(
    math::Vec3 authored_anchor, math::Vec3 camera_position,
    float near_distance, float far_distance,
    float near_vertical_offset, float far_vertical_offset,
    float near_apparent_width, float far_apparent_width) noexcept {
    DistanceEasedBillboardPlacement placement;
    const float safe_near = std::max(0.0F, near_distance);
    const float safe_far = std::max(safe_near + 0.001F, far_distance);
    const float dx = camera_position.x - authored_anchor.x;
    const float dz = camera_position.z - authored_anchor.z;
    const float horizontal_distance = std::sqrt(dx * dx + dz * dz);
    const float linear = std::clamp(
        (horizontal_distance - safe_near) / (safe_far - safe_near), 0.0F, 1.0F);
    const float smooth_far = linear * linear * (3.0F - 2.0F * linear);
    placement.near_factor = 1.0F - smooth_far;
    const auto mix = [](float far_value, float near_value, float near_factor) {
        return far_value + (near_value - far_value) * near_factor;
    };
    placement.anchor = authored_anchor;
    placement.anchor.y += mix(far_vertical_offset, near_vertical_offset, placement.near_factor);
    placement.apparent_width_ratio = std::clamp(
        mix(far_apparent_width, near_apparent_width, placement.near_factor), 0.08F, 0.82F);
    return placement;
}

Rgba unpack_rgba(std::uint32_t value) noexcept {
    constexpr float inv = 1.0F / 255.0F;
    return {
        static_cast<float>((value >> 24U) & 0xFFU) * inv,
        static_cast<float>((value >> 16U) & 0xFFU) * inv,
        static_cast<float>((value >> 8U) & 0xFFU) * inv,
        static_cast<float>(value & 0xFFU) * inv,
    };
}

std::size_t append_simple_text_points(
    std::vector<render::PointGpu>& output, const Font& font, std::string_view text,
    const TextBasis& basis, float scale, const TextPointStyle& style,
    std::size_t maximum_points) {
    return append_points(output, font, text, basis, scale, style, maximum_points, false);
}

std::size_t append_rich_text_points(
    std::vector<render::PointGpu>& output, const Font& font, std::string_view text,
    const TextBasis& basis, float scale, const TextPointStyle& style,
    std::size_t maximum_points) {
    return append_points(output, font, text, basis, scale, style, maximum_points, true);
}

BillboardTextStats append_constant_apparent_billboard(
    std::vector<render::PointGpu>& output, const Font& font, std::string_view text,
    math::Vec3 anchor, math::Vec3 camera_position, float apparent_width_ratio,
    const TextPointStyle& text_style, bool double_backplate,
    std::size_t maximum_points) {
    BillboardTextStats stats;
    const std::size_t output_start = output.size();
    const LayoutResult unit = layout_utf8(font, text, 1.0F, maximum_points);
    if (unit.width <= 0.0001F || unit.height <= 0.0001F || maximum_points == 0U) return stats;

    const math::Vec3 to_camera = camera_position - anchor;
    stats.camera_distance = std::max(0.001F, math::length(to_camera));
    // Keep the sign's apparent size stable even at close range. A5a3r1
    // clamped every camera distance below one metre to one metre, so walking
    // closer made the sign explode across the screen. Only protect the exact
    // zero-distance case; normal near/far movement now scales continuously.
    const float effective_distance = std::clamp(stats.camera_distance, 0.08F, 80.0F);
    stats.world_width = effective_distance * std::clamp(apparent_width_ratio, 0.08F, 0.82F);
    stats.scale = stats.world_width / unit.width;
    stats.world_height = unit.height * stats.scale;
    // Point sprites are sized below the authored grid spacing. The previous
    // 0.34 ratio, amplified by the renderer's density multiplier, joined
    // neighbouring dots into solid bars at ordinary room-sign distances.
    stats.point_radius = std::max(0.00035F, stats.scale * 0.19F);

    const math::Vec3 depth = math::normalize_or(to_camera, {0.0F, 0.0F, 1.0F});
    const math::Vec3 world_up{0.0F, 1.0F, 0.0F};
    const math::Vec3 right = math::normalize_or(math::cross(world_up, depth), {1.0F, 0.0F, 0.0F});
    const math::Vec3 up = math::normalize_or(math::cross(depth, right), world_up);

    if (double_backplate) {
        // Put both plates behind the rearmost authored layer. Rich text layers
        // above the base may extend away from the camera and must not be cut off.
        const float nearest_safe_plate = std::max(
            0.055F, -unit.minimum_z * stats.scale + std::max(0.018F, stats.point_radius * 2.5F));
        const float plate_width = stats.world_width * 1.13F;
        const float plate_height = stats.world_height * 1.42F;
        const float step = std::max(0.004F, plate_width / 72.0F);
        const std::size_t columns = std::clamp<std::size_t>(
            static_cast<std::size_t>(std::ceil(plate_width / step)) + 1U, 4U, 90U);
        const std::size_t rows = std::clamp<std::size_t>(
            static_cast<std::size_t>(std::ceil(plate_height / step)) + 1U, 3U, 48U);
        const auto add_plate = [&](float depth_offset, float phase, std::array<float, 4> color) {
            const std::size_t before = output.size();
            for (std::size_t row = 0U; row < rows; ++row) {
                const float v = rows == 1U ? 0.5F : static_cast<float>(row) / static_cast<float>(rows - 1U);
                const float y = (0.5F - v) * plate_height + phase;
                const float stagger = (row % 2U == 0U) ? 0.0F : step * 0.5F;
                for (std::size_t column = 0U; column < columns; ++column) {
                    if (output.size() - output_start >= maximum_points) return output.size() - before;
                    const float u = columns == 1U ? 0.5F :
                        static_cast<float>(column) / static_cast<float>(columns - 1U);
                    const float x = (u - 0.5F) * plate_width + stagger + phase;
                    const math::Vec3 position = anchor + right * x + up * y - depth * depth_offset;
                    output.push_back({{position.x, position.y, position.z}, step * 0.78F,
                                      {color[0], color[1], color[2], color[3]},
                                      {depth.x, depth.y, depth.z}, 4.20F});
                }
            }
            return output.size() - before;
        };
        stats.backplate_points += add_plate(nearest_safe_plate + 0.025F, 0.0F, {0.006F, 0.026F, 0.022F, 1.0F});
        stats.backplate_points += add_plate(nearest_safe_plate, step * 0.27F, {0.010F, 0.045F, 0.034F, 1.0F});
    }

    TextBasis basis;
    basis.right = right;
    basis.up = up;
    basis.depth = depth;
    basis.origin = anchor - right * (stats.world_width * 0.5F) + up * (stats.world_height * 0.5F);
    TextPointStyle style = text_style;
    style.point_radius = stats.point_radius;
    style.density = 4.0F;  // stable world-text render class sentinel
    const std::size_t generated = output.size() - output_start;
    const std::size_t remaining = generated < maximum_points ? maximum_points - generated : 0U;
    stats.text_points = append_rich_text_points(output, font, text, basis, stats.scale, style, remaining);
    return stats;
}

}  // namespace signalcloud::font
