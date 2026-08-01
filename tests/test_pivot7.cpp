#include "engine/render/point_cloud.hpp"
#include "engine/render/room_visibility.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/world_seed.hpp"

#include <cmath>
#include <iostream>
#include <string>
#include <vector>

int main() {
    using namespace signalcloud;
    int failures = 0;
    auto check = [&](bool condition, const char* message) {
        if (!condition) {
            std::cerr << "FAIL: " << message << '\n';
            ++failures;
        }
    };

    const auto seed = world::mix_seed(0xA11D0A1ULL, {7, 0, 1}, 4);
    const auto level = world::LiminalLevel::make_pivot7_thresholds(seed);
    check(level.areas().size() >= 23U, "Pivot 7 adds the threshold gallery and two annexes");
    check(level.connections().size() >= 10U, "Pivot 7 declares threshold connection metadata");
    check(level.zone_name({694.0F, 1.72F, -142.0F}) == "Threshold Gallery",
          "threshold quick-access spawn resolves to the gallery");
    check(level.zone_name({716.0F, 1.72F, -132.0F}) == "Raised Window Annex",
          "raised-window annex has its own zone");

    const world::RoomConnection* window_connection = nullptr;
    for (const auto& connection : level.connections()) {
        if (connection.kind == world::ConnectionKind::window &&
            connection.zone_a == "Threshold Gallery") {
            window_connection = &connection;
            break;
        }
    }
    check(window_connection != nullptr, "raised window connection exists");
    if (window_connection != nullptr) {
        const auto aperture = level.connection_aperture(*window_connection, "Threshold Gallery");
        check(aperture.normal.x > 0.90F && std::abs(aperture.normal.z) < 0.10F,
              "window aperture points from gallery toward the east annex");
        check(aperture.bottom_y > 0.80F && aperture.top_y > 2.70F,
              "window aperture has an elevated sill and usable head clearance");
    }

    const auto near_previews = level.connection_previews(
        "Threshold Gallery", {704.0F, 1.72F, -132.0F});
    bool found_window_preview = false;
    for (const auto& preview : near_previews) {
        if (preview.destination_zone == "Raised Window Annex") {
            found_window_preview = true;
            check(preview.normal.x > 0.90F && preview.half_width > 2.0F,
                  "preview carries the authored aperture geometry");
            check(preview.viewer_position.x < preview.center.x,
                  "preview stores the source-side viewer position");
        }
    }
    check(found_window_preview, "approaching the raised window requests a clipped annex preview");

    const auto side_previews = level.connection_previews(
        "Threshold Gallery", {694.0F, 1.72F, -118.0F});
    bool leaked_window_preview = false;
    for (const auto& preview : side_previews) {
        if (preview.destination_zone == "Raised Window Annex") leaked_window_preview = true;
    }
    check(!leaked_window_preview, "window preview is rejected outside the opening approach cone");

    // The sill blocks a grounded capsule, but a jumping capsule with feet above
    // 0.90m can pass through the raised opening below the lintel.
    check(!level.can_occupy_3d(708.0F, -132.0F, 0.0F, 1.72F, 0.31F, 0.34F),
          "raised-window sill blocks a grounded player");
    check(level.can_occupy_3d(708.0F, -132.0F, 0.98F, 1.72F, 0.31F, 0.34F),
          "jumping player fits through the raised-window aperture");
    check(level.can_occupy_3d(680.0F, -132.0F, 0.0F, 1.72F, 0.31F, 0.34F),
          "broken passage remains open at floor level");
    check(!level.can_occupy_3d(686.5F, -124.0F, 0.0F, 1.72F, 0.31F, 0.34F),
          "glass cubicle remains physically solid");

    const auto cloud = render::PointCloud::make_liminal_level(level, {420'000U, seed});
    check(cloud.points().size() > 420'000U,
          "shared threshold/wall ownership duplicates only required boundary points");
    check(!cloud.ranges_for("Threshold Gallery").empty() &&
          !cloud.ranges_for("Raised Window Annex").empty(),
          "threshold zones receive independent streamed ranges");

    std::vector<render::PreviewRequest> requests;
    for (const auto& preview : near_previews) {
        requests.push_back({std::string(preview.destination_zone), preview.center, preview.strength,
                            preview.viewer_position, preview.normal, preview.half_width,
                            preview.bottom_y, preview.top_y});
    }
    const auto selection = render::select_room_ranges(
        cloud, "Threshold Gallery", 420'000U, 420'000U, false,
        {704.0F, 1.72F, -132.0F}, 38.0F, requests);
    check(selection.preview_rooms >= 1U && selection.preview_ranges >= 1U,
          "threshold selection submits clipped preview ranges");
    check(selection.anchored_source_ranges >= 1U,
          "source-side threshold band is retained while previewing");
    bool has_clipped_range = false;
    for (const auto& range : selection.ranges) {
        if (range.aperture.enabled) {
            has_clipped_range = true;
            check(range.aperture.half_width > 2.0F &&
                  range.aperture.bottom_y > 0.80F,
                  "draw range retains aperture clipping bounds");
        }
    }
    check(has_clipped_range, "at least one draw range is aperture clipped");

    if (failures == 0) {
        std::cout << "All SignalCloud Pivot 7 Threshold Aperture tests passed.\n";
        return 0;
    }
    return 1;
}
