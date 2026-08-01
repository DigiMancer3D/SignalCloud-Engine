#include "engine/render/point_cloud.hpp"
#include "engine/render/room_visibility.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/world_seed.hpp"

#include <cmath>
#include <iostream>
#include <string>
#include <vector>

namespace {

bool near(float a, float b, float epsilon = 0.06F) {
    return std::abs(a - b) <= epsilon;
}

}  // namespace

int main() {
    using namespace signalcloud;
    int failures = 0;
    auto check = [&](bool condition, const char* message) {
        if (!condition) {
            std::cerr << "FAIL: " << message << '\n';
            ++failures;
        }
    };

    const auto seed = world::mix_seed(0xA11D0A1ULL, {8, 0, 1}, 4);
    const auto level = world::LiminalLevel::make_pivot8_submerged(seed);
    check(level.areas().size() >= 24U, "Pivot 8 adds the submerged boundary laboratory");
    check(level.water_regions().size() >= 6U, "Pivot 8 adds a dedicated boundary-water volume");
    check(level.connections().size() >= 11U, "Pivot 8 adds the cavity-to-wet-lab connection");
    check(level.zone_name(level.submerged_lab_spawn()) == "Submerged Boundary Lab",
          "submerged quick-access spawn resolves to the new laboratory");

    // The three accepted water transitions now have real structural wall pieces
    // around their opening. The aperture center remains open, while positions to
    // either side are blocked at the same depth.
    check(level.can_occupy_3d(792.45F, -164.0F, 0.10F, 1.72F, 0.31F, 0.34F),
          "long-hall to shaft aperture remains traversable beyond the launch ledge");
    check(!level.can_occupy_3d(792.0F, -164.0F, -2.0F, 1.72F, 0.31F, 0.34F),
          "wall below the dry-room shaft opening is solid");
    check(!level.can_occupy_3d(792.0F, -170.0F, -2.0F, 1.72F, 0.31F, 0.34F),
          "long-hall to shaft side wall is solid");
    check(level.can_occupy_3d(810.0F, -164.0F, -3.0F, 1.72F, 0.31F, 0.34F),
          "shaft to service-tunnel aperture remains traversable");
    check(!level.can_occupy_3d(810.0F, -170.0F, -3.0F, 1.72F, 0.31F, 0.34F),
          "shaft to service-tunnel side wall is solid");
    check(level.can_occupy_3d(870.0F, -164.0F, -3.0F, 1.72F, 0.31F, 0.34F),
          "service-tunnel to cavity aperture remains traversable");
    check(!level.can_occupy_3d(870.0F, -176.0F, -3.0F, 1.72F, 0.31F, 0.34F),
          "service-tunnel to cavity surrounding wall is solid");
    check(level.can_occupy_3d(926.0F, -164.0F, -2.0F, 1.72F, 0.31F, 0.34F),
          "cavity to wet-lab aperture remains traversable");
    check(!level.can_occupy_3d(926.0F, -174.0F, -2.0F, 1.72F, 0.31F, 0.34F),
          "wet-lab surrounding wall remains solid");

    std::size_t wet_side_segments = 0U;
    std::size_t wet_lintels = 0U;
    for (const auto& wall : level.walls()) {
        if (near(wall.start.x, wall.end.x) &&
            (near(wall.start.x, 792.0F) || near(wall.start.x, 810.0F) ||
             near(wall.start.x, 870.0F) || near(wall.start.x, 926.0F))) {
            const float z0 = std::min(wall.start.z, wall.end.z);
            const float z1 = std::max(wall.start.z, wall.end.z);
            if (z1 <= -166.0F + 0.08F || z0 >= -162.0F - 0.08F) ++wet_side_segments;
            if (wall.base_y > 3.0F && z0 < -163.9F && z1 > -164.1F) ++wet_lintels;
        }
    }
    check(wet_side_segments >= 8U, "all wet apertures own surrounding side-wall segments");
    check(wet_lintels >= 3U, "sub-ceiling wet apertures own visible lintels");

    const auto previews = level.connection_previews(
        "Open Pressure Cavity", {922.0F, 0.2F, -164.0F});
    bool found_wet_preview = false;
    std::vector<render::PreviewRequest> requests;
    for (const auto& preview : previews) {
        requests.push_back({std::string(preview.destination_zone), preview.center, preview.strength,
                            preview.viewer_position, preview.normal, preview.half_width,
                            preview.bottom_y, preview.top_y});
        if (preview.destination_zone == "Submerged Boundary Lab") {
            found_wet_preview = true;
            check(preview.half_width > 2.4F && near(preview.bottom_y, -4.2F),
                  "wet-lab preview starts at the higher connected traversal floor");
        }
    }
    check(found_wet_preview, "approaching the cavity wall previews the wet laboratory");

    const auto cloud = render::PointCloud::make_liminal_level(level, {500'000U, seed});
    check(cloud.finite(), "Pivot 8 point cloud remains finite");
    check(cloud.stats().submerged_floor_points == 20'000U,
          "four percent of the requested point budget forms the submerged floor layer");
    check(cloud.stats().submerged_wall_points == 20'000U,
          "four percent of the requested point budget forms the submerged wall layer");
    check(!cloud.ranges_for("Submerged Boundary Lab").empty(),
          "wet laboratory receives streamed point ranges");

    std::size_t submerged_floor_points = 0U;
    std::size_t submerged_wall_points = 0U;
    for (const auto& point : cloud.points()) {
        if (point.density >= -1.05F) continue;
        if (point.normal[1] > 0.58F) ++submerged_floor_points;
        if (std::abs(point.normal[1]) < 0.20F &&
            (std::abs(point.normal[0]) > 0.50F || std::abs(point.normal[2]) > 0.50F)) {
            ++submerged_wall_points;
        }
    }
    check(submerged_floor_points > 10'000U,
          "static underwater floor points are present in the generated cloud");
    check(submerged_wall_points > 10'000U,
          "static underwater wall-film points are present in the generated cloud");

    const auto selection = render::select_room_ranges(
        cloud, "Open Pressure Cavity", 500'000U, 500'000U, false,
        {922.0F, 0.2F, -164.0F}, 34.0F, requests);
    check(selection.preview_rooms >= 1U && selection.preview_ranges >= 1U,
          "wet destination is submitted through an aperture-clipped preview");
    check(selection.anchored_source_ranges >= 1U,
          "cavity-side wet threshold remains anchored during preview");

    if (failures == 0) {
        std::cout << "All SignalCloud Pivot 8 Submerged Boundary tests passed.\n";
        return 0;
    }
    return 1;
}
