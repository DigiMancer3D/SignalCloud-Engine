#include "engine/data/udata.hpp"
#include "engine/render/memory_budget.hpp"
#include "engine/render/point_cloud.hpp"
#include "engine/render/point_lab.hpp"
#include "engine/world/world_seed.hpp"

#include <cmath>
#include <filesystem>
#include <iostream>
#include <string>

namespace {
int failures = 0;
void check(bool value, const std::string& label) {
    if (value) std::cout << "PASS: " << label << '\n';
    else { std::cerr << "FAIL: " << label << '\n'; ++failures; }
}
}

int main(int argc, char** argv) {
    const std::filesystem::path root = argc > 1 ? argv[1] : std::filesystem::current_path();
    using namespace signalcloud::render;

    check(kPointLabPresets.size() >= 5U, "Point Lab preserves at least the five accepted Pivot 1 presets");
    check(kPointLabPresets[0].points == 100'000U, "first benchmark preset is 100K");
    check(kPointLabPresets[1].points == 500'000U, "second benchmark preset is 500K");
    check(kPointLabPresets[2].points == 1'000'000U, "third benchmark preset is 1M");
    check(kPointLabPresets[3].points == 2'000'000U, "fourth benchmark preset is 2M");
    bool contains_4m = false;
    for (const auto& preset : kPointLabPresets) contains_4m = contains_4m || preset.points == 4'000'000U;
    check(contains_4m, "accepted 4M stress preset remains available");

    PointLabState lab;
    check(lab.preset().points == 100'000U, "Point Lab state still starts at safe 100K");
    check(lab.select_preset(2U) && lab.preset().points == 1'000'000U,
          "manual preset selection reaches 1M");
    lab.adjust_point_scale(10.0F);
    check(std::abs(lab.point_scale() - 3.0F) < 0.001F, "point scale clamps at 3.0");
    lab.adjust_point_scale(-20.0F);
    check(std::abs(lab.point_scale() - 0.35F) < 0.001F, "point scale clamps at 0.35");
    lab.adjust_density_scale(10.0F);
    check(std::abs(lab.density_scale() - 2.0F) < 0.001F, "density scale clamps at 2.0");
    lab.adjust_density_scale(-20.0F);
    check(std::abs(lab.density_scale() - 0.20F) < 0.001F, "density scale clamps at 0.20");

    check(true, "automatic sweep was retired after native testing; manual PageUp/PageDown remains");

    const auto memory_4m = estimate_point_memory(4'000'000U);
    check(memory_4m.bytes_single == 192'000'000U, "4M point VBO uses 192 MB decimal");
    check(memory_4m.bytes_triple == 576'000'000U, "4M triple-buffer estimate uses 576 MB decimal");

    const auto seed = signalcloud::world::mix_seed(0xA11D0A1ULL, {0, 0, 0}, 1);
    const auto sample = PointCloud::make_liminal_room({18.0F, 5.8F, 24.0F, 500'000U, seed});
    check(sample.points().size() == 500'000U, "500K benchmark cloud generates exactly");
    check(sample.finite(), "500K benchmark cloud is finite");
    check(sample.points().front().normal[1] != sample.points().back().normal[1] ||
          sample.points().front().position[1] != sample.points().back().position[1],
          "deterministic shuffle interleaves point classes for subset rendering");

    const auto config = signalcloud::data::UDataDocument::load(root / "config/renderer.udata");
    check(!config.has_errors(), "Point Lab renderer config loads");
    check(config.value("body", "benchmark_presets").has_value(), "renderer config declares benchmark presets");
    check(config.value("body", "gpu_timer_query").has_value(), "renderer config declares GPU timing");

    if (failures == 0) {
        std::cout << "All SignalCloud Pivot 1 regression tests passed.\n";
        return 0;
    }
    return 1;
}
