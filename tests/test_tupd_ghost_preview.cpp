#include "engine/items/tupd_runtime.hpp"
#include "engine/ui/tupd_ghost_preview.hpp"

#include <cmath>
#include <filesystem>
#include <iostream>
#include <string>

namespace {
int fail(std::string_view message) {
    std::cerr << "Tupd ghost preview test failure: " << message << '\n';
    return 1;
}
}

int main(int argc, char** argv) {
    namespace fs = std::filesystem;
    const fs::path root = argc > 1 ? fs::path(argv[1]) : fs::current_path();
    signalcloud::items::TupdRecipe recipe;
    std::string error;
    if (!signalcloud::items::load_tupd_recipe(
            root / "content/starter/tupd/compatible_signal_grip/compatible_signal_grip.tupd",
            recipe, &error)) {
        return fail(error);
    }
    const auto preview = signalcloud::items::preview_tupd(
        recipe, signalcloud::items::make_tupd_test_inventory());
    signalcloud::ui::ArPose pose;
    pose.camera_position = {2.0F, 1.8F, 4.0F};
    pose.forward = {0.0F, 0.0F, -1.0F};
    pose.right = {1.0F, 0.0F, 0.0F};
    signalcloud::ui::TupdGhostPreview ghost;
    const auto points = ghost.build_points(recipe, preview, 0.75F, pose);
    const auto stats = ghost.stats();
    if (points.empty() || stats.generated_points != points.size() ||
        stats.body_points == 0U || stats.connector_points == 0U || !stats.valid_preview) {
        return fail("valid ghost result geometry");
    }
    for (const auto& value : points) {
        if (!std::isfinite(value.position[0]) || !std::isfinite(value.position[1]) ||
            !std::isfinite(value.position[2]) || !std::isfinite(value.radius)) {
            return fail("non-finite ghost point");
        }
    }

    signalcloud::items::TupdRecipe forced;
    if (!signalcloud::items::load_tupd_recipe(
            root / "content/starter/tupd/forced_office_bracket/forced_office_bracket.tupd",
            forced, &error)) {
        return fail(error);
    }
    const auto forced_preview = signalcloud::items::preview_tupd(
        forced, signalcloud::items::make_tupd_test_inventory());
    const auto forced_points = ghost.build_points(forced, forced_preview, 1.25F, pose);
    if (forced_points.empty() || !ghost.stats().forced_preview) {
        return fail("forced ghost result warning geometry");
    }

    std::cout << "A8a1 Tupd ghost preview: bounded camera-relative result PASS\n";
    return 0;
}
