#pragma once

#include "engine/math/vec.hpp"
#include "engine/physics/showcase_runtime.hpp"
#include "engine/render/point_types.hpp"

#include <cstddef>
#include <string_view>
#include <vector>

namespace signalcloud::physics {

enum class ShowcaseViewMode { source, density, material, light };

struct ShowcaseBounds {
    math::Vec3 minimum{};
    math::Vec3 maximum{};
    math::Vec3 center{};
    math::Vec3 half_extents{0.5F, 0.5F, 0.5F};
    float radius{0.5F};
    bool valid{false};
};

struct ShowcaseVisualizationOptions {
    ShowcaseViewMode view_mode{ShowcaseViewMode::source};
    float lod_fraction{1.0F};
    float point_scale{1.0F};
    bool collision_outline{true};
    bool actor_preview{false};
};

[[nodiscard]] ShowcaseBounds showcase_bounds(
    const std::vector<render::PointGpu>& points) noexcept;

[[nodiscard]] ShowcaseViewMode parse_showcase_view_mode(std::string_view value) noexcept;
[[nodiscard]] std::string_view showcase_view_mode_name(ShowcaseViewMode mode) noexcept;

[[nodiscard]] std::vector<render::PointGpu> build_showcase_frame_points(
    const std::vector<render::PointGpu>& source,
    const ShowcaseBounds& bounds,
    const PhysicsProfile& profile,
    const ShowcaseState& state,
    const ShowcaseVisualizationOptions& options,
    float time_seconds);

[[nodiscard]] std::size_t showcase_lod_count(
    std::size_t source_count, float lod_fraction) noexcept;

}  // namespace signalcloud::physics
