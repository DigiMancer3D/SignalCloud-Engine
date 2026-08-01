#include "engine/ui/showcase_info_overlay.hpp"

#include "engine/scfont/text_point_adapter.hpp"

#include <algorithm>
#include <array>
#include <cmath>

namespace signalcloud::ui {
namespace {

render::PointGpu overlay_point(math::Vec3 position, float radius,
                               std::array<float, 4> color,
                               float density = 5.0F) noexcept {
    return {{position.x, position.y, position.z}, radius,
            {color[0], color[1], color[2], color[3]},
            {0.0F, 1.0F, 0.0F}, density};
}

}  // namespace

ShowcaseInfoOverlayStats append_showcase_info_overlay(
    std::vector<render::PointGpu>& output,
    const font::Font& font,
    std::string_view text,
    const ShowcaseInfoOverlayCamera& camera,
    std::size_t maximum_points) {
    ShowcaseInfoOverlayStats stats;
    if (text.empty() || maximum_points == 0U) return stats;

    constexpr float distance = 0.72F;
    const math::Vec3 forward = math::normalize_or(camera.center - camera.eye,
                                                   {0.0F, 0.0F, -1.0F});
    const math::Vec3 right = math::normalize_or(
        math::cross(forward, {0.0F, 1.0F, 0.0F}), {1.0F, 0.0F, 0.0F});
    const math::Vec3 up = math::normalize_or(math::cross(right, forward),
                                             {0.0F, 1.0F, 0.0F});
    const math::Vec3 plane_center = camera.eye + forward * distance;
    const float safe_fov = std::clamp(camera.vertical_fov_radians, 0.35F, 2.20F);
    const float half_height = std::tan(safe_fov * 0.5F) * distance;
    const float half_width = half_height * std::clamp(camera.aspect, 0.4F, 4.0F);
    const float margin_x = std::max(0.026F, half_width * 0.035F);
    const float margin_y = std::max(0.026F, half_height * 0.055F);

    const auto layout = font::layout_utf8(font, text, 1.0F, maximum_points);
    if (layout.width <= 0.0F || layout.height <= 0.0F) return stats;
    const float available_width = std::max(0.08F, half_width * 2.0F - margin_x * 2.0F);
    const float available_height = std::max(0.08F, half_height * 2.0F - margin_y * 2.0F);
    stats.scale = std::min({0.00435F,
                            available_width / layout.width,
                            available_height / layout.height});
    stats.width = layout.width * stats.scale;
    stats.height = layout.height * stats.scale;

    constexpr float pad_x = 0.024F;
    constexpr float pad_y = 0.020F;
    const math::Vec3 origin = plane_center - right * (half_width - margin_x) +
                              up * (half_height - margin_y);
    const float plate_width = stats.width + pad_x * 2.0F;
    const float plate_height = stats.height + pad_y * 2.0F;
    const math::Vec3 plate_top_left = origin - right * pad_x + up * pad_y +
                                      forward * 0.0025F;
    const std::size_t columns = std::clamp<std::size_t>(
        static_cast<std::size_t>(std::ceil(plate_width / 0.010F)) + 1U, 8U, 120U);
    const std::size_t rows = std::clamp<std::size_t>(
        static_cast<std::size_t>(std::ceil(plate_height / 0.010F)) + 1U, 6U, 64U);

    const std::size_t plate_budget = maximum_points > layout.points.size()
        ? maximum_points - layout.points.size() : 0U;
    const std::size_t requested_plate_points = columns * rows * 2U;
    if (plate_budget >= requested_plate_points) {
        const auto add_plate = [&](float depth, std::size_t phase,
                                   std::array<float, 4> color) {
            const std::size_t before = output.size();
            for (std::size_t row = 0U; row < rows; ++row) {
                const float v = rows == 1U ? 0.0F :
                    static_cast<float>(row) / static_cast<float>(rows - 1U);
                const float y = v * plate_height;
                const float stagger = ((row + phase) % 2U == 0U)
                    ? 0.0F : plate_width / static_cast<float>(columns) * 0.5F;
                for (std::size_t column = 0U; column < columns; ++column) {
                    const float u = columns == 1U ? 0.0F :
                        static_cast<float>(column) / static_cast<float>(columns - 1U);
                    const float x = std::min(plate_width, u * plate_width + stagger);
                    const math::Vec3 position = plate_top_left + right * x - up * y +
                                                forward * depth;
                    output.push_back(overlay_point(position, 0.00115F, color));
                }
            }
            stats.backplate_points += output.size() - before;
        };
        add_plate(0.0030F, 0U, {0.002F, 0.010F, 0.013F, 0.98F});
        add_plate(0.0015F, 1U, {0.004F, 0.022F, 0.025F, 0.96F});
    }

    font::TextBasis basis;
    basis.origin = origin;
    basis.right = right;
    basis.up = up;
    basis.depth = forward;
    font::TextPointStyle style;
    style.point_radius = 0.00135F;
    style.opacity = 1.0F;
    style.tint = {0.69F, 1.0F, 0.95F};
    style.replace_rgb = true;
    style.density = 1.15F;
    const std::size_t remaining = maximum_points > stats.backplate_points
        ? maximum_points - stats.backplate_points : 0U;
    stats.text_points = font::append_simple_text_points(
        output, font, text, basis, stats.scale, style, remaining);
    return stats;
}

}  // namespace signalcloud::ui
