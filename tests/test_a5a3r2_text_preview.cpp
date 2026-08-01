#include "engine/render/point_cloud.hpp"
#include "engine/render/room_visibility.hpp"
#include "engine/scfont/scfont.hpp"
#include "engine/scfont/text_point_adapter.hpp"
#include "engine/ui/ar_interface.hpp"
#include "engine/ui/scui_native_runtime.hpp"
#include "engine/ui/scui_panel.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/world_seed.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <string>
#include <string_view>
#include <vector>

namespace {
int failures = 0;

void check(bool condition, const std::string& message) {
    if (condition) std::cout << "PASS: " << message << '\n';
    else {
        std::cerr << "FAIL: " << message << '\n';
        ++failures;
    }
}

bool destination_present(const std::vector<signalcloud::world::ConnectionPreview>& previews,
                         std::string_view destination) {
    return std::any_of(previews.begin(), previews.end(), [&](const auto& preview) {
        return preview.destination_zone == destination;
    });
}

std::size_t visible_preview_points(
    const signalcloud::render::PointCloud& cloud,
    const signalcloud::render::RoomVisibilitySelection& selection) {
    std::size_t visible = 0U;
    for (const auto& range : selection.ranges) {
        if (!range.aperture.enabled) continue;
        const std::size_t end = std::min(cloud.points().size(), range.first + range.count);
        for (std::size_t index = range.first; index < end; ++index) {
            const auto& point = cloud.points()[index];
            if (signalcloud::render::preview_aperture_visible(
                    range.aperture, {point.position[0], point.position[1], point.position[2]})) {
                ++visible;
            }
        }
    }
    return visible;
}

std::vector<signalcloud::render::PreviewRequest> requests_for(
    const std::vector<signalcloud::world::ConnectionPreview>& previews) {
    std::vector<signalcloud::render::PreviewRequest> requests;
    for (const auto& preview : previews) {
        requests.push_back({std::string(preview.destination_zone), preview.center, preview.strength,
                            preview.viewer_position, preview.normal, preview.half_width,
                            preview.bottom_y, preview.top_y});
    }
    return requests;
}
}

int main(int argc, char** argv) {
    using namespace signalcloud;
    const std::filesystem::path root = argc > 1 ? argv[1] : std::filesystem::current_path();
    const auto seed = world::mix_seed(0xA5A3A2ULL, {5, 3, 2}, 4);
    const auto level = world::LiminalLevel::make_pivot11_scavenging(seed);
    const auto cloud = render::PointCloud::make_liminal_level(level, {520'000U, seed});

    std::size_t sides_tested = 0U;
    std::size_t oblique_failures = 0U;
    std::size_t crossed_failures = 0U;
    std::size_t minimum_visible = static_cast<std::size_t>(-1);
    for (const auto& connection : level.connections()) {
        const auto test_side = [&](std::string_view source, std::string_view destination) {
            const auto aperture = level.connection_aperture(connection, source);
            const math::Vec3 tangent{-aperture.normal.z, 0.0F, aperture.normal.x};
            for (float sign : {-1.0F, 1.0F}) {
                // Close side-angle position from the screenshot class: beside the
                // opening rather than centred and closer than the old tests used.
                const math::Vec3 oblique = aperture.center - aperture.normal * 0.34F +
                    tangent * sign * (aperture.half_width + 0.52F) + math::Vec3{0.0F, 1.72F, 0.0F};
                const auto previews = level.connection_previews(source, oblique);
                if (!destination_present(previews, destination)) {
                    ++oblique_failures;
                } else {
                    const auto selection = render::select_room_ranges(
                        cloud, source, 520'000U, 520'000U, false, oblique, 42.0F,
                        requests_for(previews));
                    const auto visible = visible_preview_points(cloud, selection);
                    minimum_visible = std::min(minimum_visible, visible);
                    if (visible < 8U) ++oblique_failures;
                }
                ++sides_tested;
            }

            // Room ownership can remain on the source for a fraction of a step
            // after crossing the exact threshold plane. The preview must not
            // turn black during that handoff.
            const math::Vec3 crossed = aperture.center + aperture.normal * 0.42F +
                tangent * (aperture.half_width * 0.40F) + math::Vec3{0.0F, 1.72F, 0.0F};
            const auto crossed_previews = level.connection_previews(source, crossed);
            if (!destination_present(crossed_previews, destination)) {
                ++crossed_failures;
            } else {
                const auto selection = render::select_room_ranges(
                    cloud, source, 520'000U, 520'000U, false, crossed, 42.0F,
                    requests_for(crossed_previews));
                if (visible_preview_points(cloud, selection) < 8U) ++crossed_failures;
            }
        };
        test_side(connection.zone_a, connection.zone_b);
        if (connection.bidirectional) test_side(connection.zone_b, connection.zone_a);
    }
    check(sides_tested >= 40U && oblique_failures == 0U,
          "every doorway side submits visible destination points from both close oblique edges");
    check(crossed_failures == 0U,
          "preview remains visible while geometric threshold crossing and room ownership hand off");
    check(minimum_visible >= 8U,
          "preview tests validate actual aperture-visible points instead of only non-empty ranges");

    const auto terminal = std::make_shared<const font::Font>(
        font::load_scfont(root / "content/core/fonts/terminal_00/Terminal_00.scfont"));
    auto panel = ui::ScuiPanel::load(root / "content/core/ui/authoring_lab_project_selector.scui");
    ui::ScuiNativeRuntime scui(std::move(panel), 4U);
    scui.set_font(terminal);
    scui.set_open(true);
    ui::ArPose pose;
    pose.camera_position = {0.0F, 1.72F, 0.0F};
    pose.forward = {0.0F, 0.0F, -1.0F};
    pose.right = {1.0F, 0.0F, 0.0F};
    const auto scui_points = scui.build_points(1.0F, pose);
    std::size_t font_points = 0U;
    std::size_t solid_backplate_points = 0U;
    float maximum_font_radius = 0.0F;
    bool rear_plane = false;
    bool front_plane = false;
    for (const auto& point : scui_points) {
        if (std::abs(point.density - 1.05F) < 0.001F) {
            ++font_points;
            maximum_font_radius = std::max(maximum_font_radius, point.radius);
        }
        if (point.density >= 4.5F) {
            ++solid_backplate_points;
            rear_plane = rear_plane || point.position[2] < -0.689F;
            front_plane = front_plane || (point.position[2] > -0.689F && point.position[2] < -0.680F);
        }
    }
    check(scui.external_font_active() && font_points > 300U,
          "SCUI title, labels, values, and footer use Terminal_00 Simple text");
    check(maximum_font_radius <= 0.00216F,
          "SCUI font sprites remain below authored grid spacing and do not form text blocks");
    check(solid_backplate_points > 7'000U && rear_plane && front_plane,
          "SCUI uses two depth-separated solid point-backplate sheets");
    check(scui_points.size() < 40'000U,
          "font and occluding backplate stay inside a bounded native SCUI point budget");

    ui::ArInterface ar;
    ar.set_font(terminal);
    ui::ArInterfaceData ar_data;
    ar_data.xar = 27;
    ar_data.magazine = 8;
    ar_data.weapon_slot = 1;
    ar_data.safe_room = true;
    ar_data.interaction_near = true;
    const auto ar_points = ar.build_points(1.0F, pose, ar_data);
    const auto ar_font_points = std::count_if(ar_points.begin(), ar_points.end(), [](const auto& point) {
        return std::abs(point.density - 1.05F) < 0.001F && point.radius <= 0.00236F;
    });
    const auto interaction_rich_points = std::count_if(ar_points.begin(), ar_points.end(), [](const auto& point) {
        return std::abs(point.density - 1.08F) < 0.001F;
    });
    const auto interaction_plate_points = std::count_if(ar_points.begin(), ar_points.end(), [](const auto& point) {
        return point.density >= 5.0F && point.position[1] < 1.70F;
    });
    check(ar.external_font_active() && ar_font_points > 20,
          "in-game AR numbers use the same readable Terminal_00 Simple text path");
    check(interaction_rich_points > 5U && interaction_plate_points > 100U,
          "interaction F uses Rich text with a point-native plate inside its key square");

    ar_data.interaction_near = false;
    ar_data.vending_menu = true;
    const auto vending_points = ar.build_points(1.0F, pose, ar_data);
    const auto vending_plate_points = std::count_if(vending_points.begin(), vending_points.end(), [](const auto& point) {
        return point.density >= 5.0F;
    });
    check(vending_plate_points > 2'000U && vending_points.size() < 10'000U,
          "AR vending menu has a dense bounded two-sheet readability backplate");

    font::TextPointStyle style;
    style.tint = {0.18F, 1.0F, 0.43F};
    style.replace_rgb = true;
    std::vector<render::PointGpu> close_sign;
    std::vector<render::PointGpu> room_sign;
    const auto close_stats = font::append_constant_apparent_billboard(
        close_sign, *terminal, "WELCOME", {0.0F, 1.5F, 0.0F}, {0.0F, 1.5F, 0.22F},
        0.42F, style, true, 8'000U);
    const auto room_stats = font::append_constant_apparent_billboard(
        room_sign, *terminal, "WELCOME", {0.0F, 1.5F, 0.0F}, {0.0F, 1.5F, 5.5F},
        0.42F, style, true, 8'000U);
    const float close_ratio = close_stats.world_width / close_stats.camera_distance;
    const float room_ratio = room_stats.world_width / room_stats.camera_distance;
    check(std::abs(close_ratio - room_ratio) < 0.001F,
          "the low-level billboard adapter retains constant-apparent sizing when requested");
    check(close_stats.point_radius / close_stats.scale < 0.25F &&
              room_stats.point_radius / room_stats.scale < 0.25F,
          "WELCOME font dots remain visibly separated at every distance");

    const auto near_placement = font::distance_eased_billboard_placement(
        {0.0F, 1.82F, -4.5F}, {0.0F, 1.72F, -3.55F});
    const auto far_placement = font::distance_eased_billboard_placement(
        {0.0F, 1.82F, -4.5F}, {0.0F, 1.72F, 8.0F});
    check(near_placement.anchor.y > far_placement.anchor.y + 0.70F,
          "WELCOME rises as the camera approaches and lowers at room distance");
    check(near_placement.apparent_width_ratio > far_placement.apparent_width_ratio &&
              near_placement.apparent_width_ratio - far_placement.apparent_width_ratio <= 0.09F,
          "WELCOME grows and shrinks only inside a narrow apparent-size range");
    check(std::abs(near_placement.anchor.x) < 0.001F &&
              std::abs(near_placement.anchor.z + 4.5F) < 0.001F,
          "WELCOME distance easing changes height without sliding forward or backward");

    if (failures == 0) {
        std::cout << "All A5a3r2 oblique preview, SCFONT UI, backplate, AR, and sign checks passed.\n";
        return 0;
    }
    return 1;
}
