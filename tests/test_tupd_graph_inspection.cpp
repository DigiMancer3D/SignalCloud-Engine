#include "engine/items/tupd_runtime.hpp"
#include "engine/ui/tupd_ghost_preview.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <limits>
#include <set>
#include <string>

namespace {
int fail(std::string_view message) {
    std::cerr << "Tupd A8a3 graph inspection test failure: " << message << '\n';
    return 1;
}

signalcloud::math::Vec3 bounds_center(const std::vector<signalcloud::render::PointGpu>& points) {
    signalcloud::math::Vec3 minimum{
        std::numeric_limits<float>::max(),
        std::numeric_limits<float>::max(),
        std::numeric_limits<float>::max(),
    };
    signalcloud::math::Vec3 maximum{
        std::numeric_limits<float>::lowest(),
        std::numeric_limits<float>::lowest(),
        std::numeric_limits<float>::lowest(),
    };
    for (const auto& point : points) {
        minimum.x = std::min(minimum.x, point.position[0]);
        minimum.y = std::min(minimum.y, point.position[1]);
        minimum.z = std::min(minimum.z, point.position[2]);
        maximum.x = std::max(maximum.x, point.position[0]);
        maximum.y = std::max(maximum.y, point.position[1]);
        maximum.z = std::max(maximum.z, point.position[2]);
    }
    return (minimum + maximum) * 0.5F;
}

bool near(signalcloud::math::Vec3 a, signalcloud::math::Vec3 b, float epsilon = 0.0001F) {
    return std::abs(a.x - b.x) <= epsilon &&
           std::abs(a.y - b.y) <= epsilon &&
           std::abs(a.z - b.z) <= epsilon;
}
}

int main(int argc, char** argv) {
    namespace fs = std::filesystem;
    const fs::path root = argc > 1 ? fs::path(argv[1]) : fs::current_path();
    signalcloud::items::TupdRecipe recipe;
    std::string error;
    if (!signalcloud::items::load_tupd_recipe(
            root / "content/starter/tupd/forced_office_bracket/forced_office_bracket.tupd",
            recipe, &error)) {
        return fail(error);
    }
    const auto preview = signalcloud::items::preview_tupd(
        recipe, signalcloud::items::make_tupd_test_inventory());
    if (!preview.valid || !preview.forced) return fail("forced starter preview");

    signalcloud::ui::ArPose pose;
    pose.camera_position = {1.0F, 1.6F, 4.0F};
    pose.forward = {0.0F, 0.0F, -1.0F};
    pose.right = {1.0F, 0.0F, 0.0F};
    signalcloud::ui::TupdGhostPreview ghost;

    const auto assembled = ghost.build_points(
        recipe, preview, 0.5F, pose, nullptr, nullptr,
        signalcloud::ui::TupdGhostInspectionMode::result, false);
    const auto assembled_stats = ghost.stats();
    const auto exploded = ghost.build_points(
        recipe, preview, 0.5F, pose, nullptr, nullptr,
        signalcloud::ui::TupdGhostInspectionMode::result, true);
    const auto exploded_stats = ghost.stats();
    if (assembled.empty() || exploded.empty() || exploded.size() <= assembled.size()) {
        return fail("exploded mode must add visible separation guides");
    }
    if (assembled_stats.exploded || !exploded_stats.exploded) {
        return fail("exploded state reporting");
    }

    std::set<std::string> names;
    auto mode = signalcloud::ui::TupdGhostInspectionMode::result;
    for (int index = 0; index < 4; ++index) {
        names.emplace(signalcloud::ui::tupd_ghost_inspection_name(mode));
        const auto points = ghost.build_points(recipe, preview, 1.0F, pose, nullptr, nullptr, mode, true);
        if (points.empty() || ghost.stats().inspection_mode != mode) {
            return fail("inspection mode geometry and stats");
        }
        mode = signalcloud::ui::next_tupd_ghost_inspection_mode(mode);
    }
    if (names.size() != 4U || mode != signalcloud::ui::TupdGhostInspectionMode::result) {
        return fail("four-mode deterministic cycle");
    }
    if (signalcloud::ui::parse_tupd_ghost_inspection_mode("SOCKETS") !=
        signalcloud::ui::TupdGhostInspectionMode::sockets) {
        return fail("inspection parser");
    }

    signalcloud::ui::TupdGhostPlacement world_placement;
    world_placement.mode = signalcloud::ui::TupdGhostPlacementMode::world_stage;
    world_placement.world_center = {0.0F, 1.15F, 0.0F};
    const auto world_a = ghost.build_points(
        recipe, preview, 0.5F, pose, nullptr, nullptr,
        signalcloud::ui::TupdGhostInspectionMode::result, false, world_placement);
    pose.camera_position = {-18.0F, 9.0F, 27.0F};
    pose.forward = {1.0F, -0.2F, 0.4F};
    pose.right = {0.0F, 0.0F, 1.0F};
    const auto world_b = ghost.build_points(
        recipe, preview, 0.5F, pose, nullptr, nullptr,
        signalcloud::ui::TupdGhostInspectionMode::result, false, world_placement);
    if (world_a.size() != world_b.size() || !near(bounds_center(world_a), bounds_center(world_b))) {
        return fail("world-stage placement must remain fixed while the camera orbits");
    }

    std::cout << "A8a3r1 Tupd fitted world-space inspection PASS\n";
    return 0;
}
