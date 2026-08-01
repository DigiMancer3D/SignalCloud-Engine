#include "engine/materials/material_runtime.hpp"

#include <filesystem>
#include <iostream>
#include <string>

namespace {
int failures = 0;
void check(bool condition, const char* message) {
    if (!condition) {
        ++failures;
        std::cerr << "FAIL: " << message << '\n';
    }
}
}

int main(int argc, char** argv) {
    const std::filesystem::path root = argc > 1 ? argv[1] : ".";
    signalcloud::materials::MaterialRuntime runtime(
        root, root / "user_data/studio/material_runtime.udata");
    std::string error;
    check(runtime.reload(&error), "A5a2 material runtime loads");
    const auto first = runtime.evaluate("Reception Tape");
    const auto second = runtime.evaluate("Reception Tape");
    const auto& floor = first.surfaces[0];
    const auto& wall = first.surfaces[1];
    const auto& ceiling = first.surfaces[2];

    check(floor.pattern_mode == signalcloud::materials::PatternMode::fiber_rows,
          "carpet uses fiber-row pattern mode");
    check(floor.displacement_weight > 0.9F && floor.primary_spacing < 0.8F,
          "carpet keeps dense rows and full displacement");
    check(wall.pattern_mode == signalcloud::materials::PatternMode::wallpaper_breakup,
          "wallpaper uses broad breakup pattern mode");
    check(wall.primary_spacing >= 3.0F && wall.secondary_spacing >= 1.8F,
          "wallpaper bands remain broadly spaced");
    check(wall.breakup_strength >= 0.35F && wall.displacement_weight <= 0.05F,
          "wallpaper is visually broken up and nearly flat");
    check(ceiling.pattern_mode == signalcloud::materials::PatternMode::flat_tiles,
          "ceiling uses flat tile pattern mode");
    check(ceiling.displacement_weight == 0.0F,
          "ceiling pattern cannot create geometric ripple");
    check(first.surfaces[1].primary_spacing == second.surfaces[1].primary_spacing &&
          first.surfaces[1].seed == second.surfaces[1].seed,
          "wall pattern parameters are deterministic across evaluations");
    check(signalcloud::materials::pattern_mode_name(wall.pattern_mode) == "wallpaper_breakup",
          "pattern mode diagnostics are stable");

    if (failures == 0) {
        std::cout << "SignalCloud A5a2 deterministic surface pattern tests PASS\n";
    }
    return failures == 0 ? 0 : 1;
}
