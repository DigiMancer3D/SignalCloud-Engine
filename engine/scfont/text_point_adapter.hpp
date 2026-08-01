#pragma once

#include "engine/math/vec.hpp"
#include "engine/render/point_types.hpp"
#include "engine/scfont/scfont.hpp"

#include <array>
#include <cstddef>
#include <string_view>
#include <vector>

namespace signalcloud::font {

struct Rgba {
    float r{1.0F};
    float g{1.0F};
    float b{1.0F};
    float a{1.0F};
};

struct TextPointStyle {
    float point_radius{0.0022F};
    float opacity{1.0F};
    std::array<float, 3> tint{1.0F, 1.0F, 1.0F};
    bool replace_rgb{false};
    float density{1.0F};
};

struct TextBasis {
    math::Vec3 origin{};
    math::Vec3 right{1.0F, 0.0F, 0.0F};
    math::Vec3 up{0.0F, 1.0F, 0.0F};
    math::Vec3 depth{0.0F, 0.0F, 1.0F};
};

[[nodiscard]] Rgba unpack_rgba(std::uint32_t value) noexcept;

std::size_t append_simple_text_points(
    std::vector<render::PointGpu>& output, const Font& font, std::string_view text,
    const TextBasis& basis, float scale, const TextPointStyle& style,
    std::size_t maximum_points = 12'000U);

std::size_t append_rich_text_points(
    std::vector<render::PointGpu>& output, const Font& font, std::string_view text,
    const TextBasis& basis, float scale, const TextPointStyle& style,
    std::size_t maximum_points = 24'000U);

struct DistanceEasedBillboardPlacement {
    math::Vec3 anchor{};
    float apparent_width_ratio{0.42F};
    float near_factor{0.0F};
};

// Keeps a world sign near its authored X/Z position while translating it
// vertically with approach distance. Apparent size changes only inside a
// narrow bounded range so the sign rises instead of zooming at the player.
[[nodiscard]] DistanceEasedBillboardPlacement distance_eased_billboard_placement(
    math::Vec3 authored_anchor, math::Vec3 camera_position,
    float near_distance = 1.0F, float far_distance = 12.0F,
    float near_vertical_offset = 0.78F, float far_vertical_offset = -0.08F,
    float near_apparent_width = 0.46F, float far_apparent_width = 0.38F) noexcept;

struct BillboardTextStats {
    float camera_distance{0.0F};
    float world_width{0.0F};
    float world_height{0.0F};
    float scale{0.0F};
    float point_radius{0.0F};
    std::size_t text_points{0U};
    std::size_t backplate_points{0U};
};

BillboardTextStats append_constant_apparent_billboard(
    std::vector<render::PointGpu>& output, const Font& font, std::string_view text,
    math::Vec3 anchor, math::Vec3 camera_position, float apparent_width_ratio,
    const TextPointStyle& text_style, bool double_backplate = true,
    std::size_t maximum_points = 12'000U);

}  // namespace signalcloud::font
