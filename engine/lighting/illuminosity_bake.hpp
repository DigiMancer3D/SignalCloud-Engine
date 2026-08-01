#pragma once

#include "engine/lighting/illuminosity_runtime.hpp"

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <string_view>
#include <vector>

namespace signalcloud::lighting {

struct IlluminosityBakeRequest {
    math::Vec3 center{};
    std::string zone{"Reception Tape"};
    std::size_t grid_size{7U};
    float spacing{1.5F};
};

struct IlluminosityBakeSample {
    math::Vec3 position{};
    float illuminosity_percent{0.0F};
    float visibility{0.0F};
    std::size_t contributing_lights{0U};
    std::string quality_band;
};

struct IlluminosityBakeSummary {
    IlluminosityBakeRequest request{};
    std::vector<IlluminosityBakeSample> samples;
    float minimum_illuminosity_percent{0.0F};
    float maximum_illuminosity_percent{0.0F};
    float average_illuminosity_percent{0.0F};
    std::size_t readable_samples{0U};
    std::size_t dark_samples{0U};
    std::uint64_t deterministic_signature{0U};
};

[[nodiscard]] IlluminosityBakeSummary bake_illuminosity_grid(
    const IlluminosityRuntime& runtime, const IlluminosityBakeRequest& request);

bool write_illuminosity_bake_report(
    const std::filesystem::path& project_root,
    const std::filesystem::path& output_path,
    const IlluminosityRuntime& runtime,
    const IlluminosityBakeSummary& summary,
    std::string* error = nullptr);

}  // namespace signalcloud::lighting
