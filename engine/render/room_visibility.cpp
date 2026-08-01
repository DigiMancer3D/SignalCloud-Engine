#include "engine/render/room_visibility.hpp"

#include <algorithm>
#include <cmath>
#include <set>
#include <tuple>

namespace signalcloud::render {
namespace {

float distance_xz(math::Vec3 a, math::Vec3 b) noexcept {
    const float dx = a.x - b.x;
    const float dz = a.z - b.z;
    return std::sqrt(dx * dx + dz * dz);
}

RoomVisibilitySelection select_impl(const PointCloud& cloud,
                                    std::string_view active_zone,
                                    std::uint32_t equivalent_fill_points,
                                    std::uint32_t resident_equivalent_points,
                                    bool tactical_mode,
                                    math::Vec3 viewer_position,
                                    float distance_limit,
                                    bool use_distance,
                                    const std::vector<PreviewRequest>& previews) {
    RoomVisibilitySelection result;
    result.resident_points = cloud.points().size();
    result.distance_limit = distance_limit;
    const float denominator = static_cast<float>(
        std::max<std::uint32_t>(1U, resident_equivalent_points));
    result.fill_ratio = std::clamp(
        static_cast<float>(equivalent_fill_points) / denominator, 0.01F, 1.0F);

    std::set<std::string> submitted_zones;
    std::set<std::size_t> active_range_firsts;
    auto append_scaled = [&](const PointRange& range, float extra_ratio,
                             const PreviewAperture& aperture, bool active_range) {
        if (range.count == 0U) return false;
        if (active_range && active_range_firsts.contains(range.first)) return false;
        const float ratio = std::clamp(result.fill_ratio * extra_ratio, 0.005F, 1.0F);
        const auto scaled = static_cast<std::size_t>(std::llround(
            static_cast<double>(range.count) * static_cast<double>(ratio)));
        const std::size_t count = std::clamp<std::size_t>(scaled, 1U, range.count);
        result.ranges.push_back({range.first, count, aperture});
        result.submitted_points += count;
        ++result.submitted_ranges;
        submitted_zones.insert(range.zone);
        if (active_range) active_range_firsts.insert(range.first);
        else ++result.preview_ranges;
        return true;
    };
    auto append_preview_spread = [&](const PointRange& range, float extra_ratio,
                                     const PreviewAperture& aperture) {
        if (range.count == 0U) return false;
        const float ratio = std::clamp(result.fill_ratio * extra_ratio, 0.005F, 1.0F);
        const auto scaled = static_cast<std::size_t>(std::llround(
            static_cast<double>(range.count) * static_cast<double>(ratio)));
        const std::size_t desired = std::clamp<std::size_t>(scaled, 1U, range.count);
        // A prefix-only draw range can contain no points inside a narrow, close
        // oblique aperture even though the destination was technically staged.
        // Distribute bounded contiguous windows across the entire authored room
        // range so every material/surface band remains represented.
        const std::size_t window_count = std::clamp<std::size_t>(
            desired / 192U + 1U, 1U, 12U);
        std::size_t remaining = desired;
        bool appended = false;
        for (std::size_t window = 0U; window < window_count && remaining > 0U; ++window) {
            const std::size_t bin_begin = range.first + range.count * window / window_count;
            const std::size_t bin_end = range.first + range.count * (window + 1U) / window_count;
            const std::size_t bin_count = std::max<std::size_t>(1U, bin_end - bin_begin);
            const std::size_t windows_left = window_count - window;
            const std::size_t requested = (remaining + windows_left - 1U) / windows_left;
            const std::size_t count = std::min(requested, bin_count);
            const std::size_t first = bin_begin + (bin_count - count) / 2U;
            result.ranges.push_back({first, count, aperture});
            result.submitted_points += count;
            ++result.submitted_ranges;
            ++result.preview_ranges;
            submitted_zones.insert(range.zone);
            remaining -= count;
            appended = true;
        }
        return appended;
    };
    const PreviewAperture no_aperture{};

    if (tactical_mode) {
        for (const auto& range : cloud.ranges()) append_scaled(range, 1.0F, no_aperture, true);
        result.submitted_rooms = submitted_zones.size();
        return result;
    }

    const auto candidates = cloud.ranges_for(active_zone);
    if (!candidates.empty()) {
        const PointRange* nearest = nullptr;
        float nearest_distance = 0.0F;
        for (const auto* range : candidates) {
            const float distance = distance_xz(viewer_position, range->center);
            if (nearest == nullptr || distance < nearest_distance) {
                nearest = range;
                nearest_distance = distance;
            }
            if (!use_distance || range->radius <= 0.0F ||
                distance <= distance_limit + range->radius) {
                append_scaled(*range, 1.0F, no_aperture, true);
            }
        }
        if (result.ranges.empty() && nearest != nullptr) {
            append_scaled(*nearest, 1.0F, no_aperture, true);
        }
    } else if (!cloud.ranges().empty()) {
        append_scaled(cloud.ranges().front(), 1.0F, no_aperture, true);
    } else if (!cloud.points().empty()) {
        PointRange fallback{"fallback", 0U, cloud.points().size(), viewer_position, 0.0F};
        append_scaled(fallback, 1.0F, no_aperture, true);
    }

    for (const PreviewRequest& preview : previews) {
        if (preview.zone.empty() || preview.zone == active_zone || preview.strength <= 0.0F) continue;

        // Keep the source-side threshold band resident while its destination is
        // previewed. This prevents the wall/frame around an opening from being
        // culled one step before the destination preview disappears.
        const PointRange* source_anchor = nullptr;
        float source_anchor_distance = 0.0F;
        for (const auto* range : candidates) {
            const float distance = distance_xz(preview.opening_center, range->center);
            if (source_anchor == nullptr || distance < source_anchor_distance) {
                source_anchor = range;
                source_anchor_distance = distance;
            }
        }
        if (source_anchor != nullptr) {
            append_scaled(*source_anchor, 1.0F, no_aperture, true);
            ++result.anchored_source_ranges;
        }

        const auto destination_ranges = cloud.ranges_for(preview.zone);
        if (destination_ranges.empty()) continue;
        const PointRange* nearest = nullptr;
        float nearest_distance = 0.0F;
        PreviewAperture aperture;
        aperture.enabled = true;
        aperture.viewer_position = preview.viewer_position;
        aperture.opening_center = preview.opening_center;
        aperture.opening_normal = preview.opening_normal;
        aperture.half_width = std::max(0.25F, preview.half_width);
        aperture.bottom_y = preview.bottom_y;
        aperture.top_y = std::max(preview.bottom_y + 0.25F, preview.top_y);
        aperture.strength = std::clamp(preview.strength, 0.0F, 1.0F);

        bool preview_submitted = false;
        for (const auto* range : destination_ranges) {
            const float distance = distance_xz(preview.opening_center, range->center);
            if (nearest == nullptr || distance < nearest_distance) {
                nearest = range;
                nearest_distance = distance;
            }
            if (distance <= distance_limit * 0.75F + range->radius) {
                preview_submitted |= append_preview_spread(*range, preview.strength, aperture);
            }
        }
        if (!preview_submitted && nearest != nullptr) {
            preview_submitted = append_preview_spread(*nearest, preview.strength, aperture);
        }
        if (preview_submitted) ++result.preview_rooms;
    }

    result.submitted_rooms = submitted_zones.size();
    return result;
}

}  // namespace

bool preview_aperture_visible(const PreviewAperture& aperture, math::Vec3 point) noexcept {
    if (!aperture.enabled) return true;
    const math::Vec3 normal = math::normalize_or(aperture.opening_normal, {1.0F, 0.0F, 0.0F});
    const math::Vec3 tangent{-normal.z, 0.0F, normal.x};
    const math::Vec3 ray = point - aperture.viewer_position;
    const float denominator = math::dot(ray, normal);
    const float plane_distance = math::dot(aperture.opening_center - aperture.viewer_position, normal);
    const float viewer_lateral = std::abs(math::dot(
        aperture.viewer_position - aperture.opening_center, tangent));
    const bool crossed_threshold = plane_distance < -0.02F && plane_distance > -1.45F &&
        viewer_lateral <= aperture.half_width + 0.90F;
    if (crossed_threshold) return true;
    if (std::abs(denominator) <= 0.00001F) return false;
    const float t = plane_distance / denominator;
    if (!(t > -0.015F && t < 1.035F)) return false;
    const math::Vec3 hit = aperture.viewer_position + ray * t;
    const float lateral = std::abs(math::dot(hit - aperture.opening_center, tangent));
    const bool beyond_opening = math::dot(point - aperture.opening_center, normal) >= -0.14F;
    return beyond_opening && lateral <= aperture.half_width + 0.18F &&
        hit.y >= aperture.bottom_y - 0.14F && hit.y <= aperture.top_y + 0.14F;
}

RoomVisibilitySelection select_room_ranges(const PointCloud& cloud,
                                            std::string_view active_zone,
                                            std::uint32_t equivalent_fill_points,
                                            std::uint32_t resident_equivalent_points,
                                            bool tactical_mode) {
    return select_impl(cloud, active_zone, equivalent_fill_points,
                       resident_equivalent_points, tactical_mode,
                       {}, 0.0F, false, {});
}

RoomVisibilitySelection select_room_ranges(const PointCloud& cloud,
                                            std::string_view active_zone,
                                            std::uint32_t equivalent_fill_points,
                                            std::uint32_t resident_equivalent_points,
                                            bool tactical_mode,
                                            math::Vec3 viewer_position,
                                            float distance_limit,
                                            const std::vector<PreviewRequest>& previews) {
    return select_impl(cloud, active_zone, equivalent_fill_points,
                       resident_equivalent_points, tactical_mode,
                       viewer_position, std::max(1.0F, distance_limit), true, previews);
}


void enforce_submitted_point_cap(RoomVisibilitySelection& selection,
                                 std::size_t maximum_points) {
    selection.submitted_point_cap = maximum_points;
    if (maximum_points == 0U || selection.submitted_points <= maximum_points) return;

    const std::size_t original = selection.submitted_points;
    std::vector<DrawRange> trimmed;
    trimmed.reserve(selection.ranges.size());
    std::size_t remaining = maximum_points;
    for (const DrawRange& range : selection.ranges) {
        if (remaining == 0U) break;
        DrawRange kept = range;
        kept.count = std::min(kept.count, remaining);
        if (kept.count == 0U) continue;
        trimmed.push_back(kept);
        remaining -= kept.count;
    }
    selection.ranges = std::move(trimmed);
    selection.submitted_points = maximum_points - remaining;
    selection.submitted_ranges = selection.ranges.size();
    selection.points_trimmed = original - selection.submitted_points;
    selection.cap_applied = selection.points_trimmed > 0U;
}

void enforce_submitted_point_cap_balanced(RoomVisibilitySelection& selection,
                                          std::size_t maximum_points) {
    selection.submitted_point_cap = maximum_points;
    selection.balanced_cap_applied = false;
    if (maximum_points == 0U || selection.submitted_points <= maximum_points) return;

    const std::size_t original = selection.submitted_points;
    const std::size_t range_count = selection.ranges.size();
    if (range_count == 0U) {
        selection.submitted_points = 0U;
        selection.submitted_ranges = 0U;
        selection.points_trimmed = original;
        selection.cap_applied = original > 0U;
        selection.balanced_cap_applied = selection.cap_applied;
        return;
    }

    const std::size_t target = std::min(maximum_points, original);
    std::vector<std::size_t> counts(range_count, 0U);
    std::vector<std::pair<double, std::size_t>> remainders;
    remainders.reserve(range_count);

    const double ratio = static_cast<double>(target) / static_cast<double>(original);
    const bool can_keep_every_range = target >= range_count;
    std::size_t assigned = 0U;
    for (std::size_t i = 0; i < range_count; ++i) {
        const std::size_t available = selection.ranges[i].count;
        if (available == 0U) continue;
        const double exact = static_cast<double>(available) * ratio;
        std::size_t count = static_cast<std::size_t>(std::floor(exact));
        if (can_keep_every_range) count = std::max<std::size_t>(1U, count);
        count = std::min(count, available);
        counts[i] = count;
        assigned += count;
        remainders.emplace_back(exact - std::floor(exact), i);
    }

    // Minimum-one guarantees can exceed very small caps. Remove extras from
    // the largest retained ranges while keeping as many rooms represented as
    // possible. This path is not expected for current million-point caps but
    // keeps the helper correct for tests and future profiles.
    while (assigned > target) {
        auto it = std::max_element(counts.begin(), counts.end());
        if (it == counts.end() || *it == 0U) break;
        if (can_keep_every_range && *it <= 1U) break;
        --(*it);
        --assigned;
    }

    std::sort(remainders.begin(), remainders.end(), [](const auto& a, const auto& b) {
        if (a.first != b.first) return a.first > b.first;
        return a.second < b.second;
    });
    for (const auto& [fraction, index] : remainders) {
        (void)fraction;
        if (assigned >= target) break;
        if (counts[index] >= selection.ranges[index].count) continue;
        ++counts[index];
        ++assigned;
    }

    std::vector<DrawRange> balanced;
    balanced.reserve(range_count);
    for (std::size_t i = 0; i < range_count; ++i) {
        if (counts[i] == 0U) continue;
        DrawRange kept = selection.ranges[i];
        kept.count = counts[i];
        balanced.push_back(kept);
    }

    selection.ranges = std::move(balanced);
    selection.submitted_points = assigned;
    selection.submitted_ranges = selection.ranges.size();
    selection.points_trimmed = original - assigned;
    selection.cap_applied = selection.points_trimmed > 0U;
    selection.balanced_cap_applied = selection.cap_applied;
}


bool full_map_selection_is_stable(
    const RoomVisibilitySelection& selection,
    const PointCloud& cloud) noexcept {
    if (cloud.points().empty()) return selection.submitted_points == 0U;
    if (selection.submitted_points == 0U || selection.ranges.empty()) return false;

    std::size_t summed = 0U;
    for (const DrawRange& selected : selection.ranges) {
        if (selected.count == 0U || selected.first >= cloud.points().size()) return false;
        if (selected.count > cloud.points().size() - selected.first) return false;
        summed += selected.count;
    }
    if (summed != selection.submitted_points) return false;

    for (const PointRange& resident : cloud.ranges()) {
        if (resident.count == 0U) continue;
        const std::size_t resident_end = resident.first + resident.count;
        bool represented = false;
        for (const DrawRange& selected : selection.ranges) {
            const std::size_t selected_end = selected.first + selected.count;
            if (selected.first < resident_end && resident.first < selected_end) {
                represented = true;
                break;
            }
        }
        if (!represented) return false;
    }
    return true;
}

bool restore_balanced_full_map_selection(
    RoomVisibilitySelection& selection,
    const PointCloud& cloud,
    std::uint32_t equivalent_fill_points,
    std::uint32_t resident_equivalent_points,
    std::size_t maximum_points) {
    if (full_map_selection_is_stable(selection, cloud)) return false;
    selection = select_room_ranges(cloud, {}, equivalent_fill_points,
                                   resident_equivalent_points, true);
    enforce_submitted_point_cap_balanced(selection, maximum_points);
    return true;
}

}  // namespace signalcloud::render
