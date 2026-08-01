#pragma once

#include "engine/math/vec.hpp"
#include "engine/render/point_cloud.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace signalcloud::render {

struct PreviewAperture {
    bool enabled{false};
    math::Vec3 viewer_position{};
    math::Vec3 opening_center{};
    math::Vec3 opening_normal{1.0F, 0.0F, 0.0F};
    float half_width{1.5F};
    float bottom_y{0.0F};
    float top_y{3.2F};
    float strength{0.0F};
};

struct DrawRange {
    std::size_t first{0};
    std::size_t count{0};
    PreviewAperture aperture{};
};

struct PreviewRequest {
    std::string zone;
    math::Vec3 opening_center{};
    float strength{0.0F};
    math::Vec3 viewer_position{};
    math::Vec3 opening_normal{1.0F, 0.0F, 0.0F};
    float half_width{1.5F};
    float bottom_y{0.0F};
    float top_y{3.2F};
};


// CPU mirror of the native preview aperture visibility rule. It is used by
// regression tests and diagnostics to verify that close oblique approaches
// receive actual visible destination points, not merely a non-empty range.
[[nodiscard]] bool preview_aperture_visible(
    const PreviewAperture& aperture, math::Vec3 point) noexcept;

struct RoomVisibilitySelection {
    std::vector<DrawRange> ranges;
    std::size_t resident_points{0};
    std::size_t submitted_points{0};
    std::size_t submitted_rooms{0};
    std::size_t submitted_ranges{0};
    std::size_t preview_rooms{0};
    std::size_t preview_ranges{0};
    std::size_t anchored_source_ranges{0};
    float fill_ratio{1.0F};
    float distance_limit{0.0F};
    std::size_t submitted_point_cap{0};
    std::size_t points_trimmed{0};
    bool cap_applied{false};
    bool balanced_cap_applied{false};
};

[[nodiscard]] RoomVisibilitySelection select_room_ranges(
    const PointCloud& cloud,
    std::string_view active_zone,
    std::uint32_t equivalent_fill_points,
    std::uint32_t resident_equivalent_points,
    bool tactical_mode);

[[nodiscard]] RoomVisibilitySelection select_room_ranges(
    const PointCloud& cloud,
    std::string_view active_zone,
    std::uint32_t equivalent_fill_points,
    std::uint32_t resident_equivalent_points,
    bool tactical_mode,
    math::Vec3 viewer_position,
    float distance_limit,
    const std::vector<PreviewRequest>& previews = {});

void enforce_submitted_point_cap(RoomVisibilitySelection& selection,
                                 std::size_t maximum_points);

// Full-map stress submission must retain a representative prefix from every
// room range. Sequential truncation can leave the current route room with no
// points even while telemetry still reports a non-empty global selection.
void enforce_submitted_point_cap_balanced(RoomVisibilitySelection& selection,
                                          std::size_t maximum_points);

// A full-map submission is stable only when every resident room range still
// has at least one overlapping draw range and the submitted count is nonzero.
// This deliberately does not depend on the current logical zone; transient
// threshold space ("Signal Void") must never collapse a global submission.
[[nodiscard]] bool full_map_selection_is_stable(
    const RoomVisibilitySelection& selection,
    const PointCloud& cloud) noexcept;

// Rebuild a malformed/empty full-map submission from the resident cloud using
// the balanced cap. Returns true only when a restore was required.
bool restore_balanced_full_map_selection(
    RoomVisibilitySelection& selection,
    const PointCloud& cloud,
    std::uint32_t equivalent_fill_points,
    std::uint32_t resident_equivalent_points,
    std::size_t maximum_points);

}  // namespace signalcloud::render
