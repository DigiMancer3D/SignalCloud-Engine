#pragma once

#include <cstdint>
#include <filesystem>
#include <map>
#include <string>
#include <vector>

namespace signalcloud::benchmark {

enum class WorkloadAxis : std::uint8_t {
    none,
    lights,
    material_layers,
    sound_ripples,
    animated_actors,
    playbook_evaluations,
    tupd_test_objects,
    scui_panels,
};

struct WorkloadRegistrySnapshot {
    bool valid{false};
    std::uint64_t enabled_asset_count{0};
    std::string registry_sha256;
    std::map<std::string, std::uint64_t> feature_channels;
};

struct WorkloadRampPoint {
    WorkloadAxis axis{WorkloadAxis::none};
    std::uint32_t level{0};
    std::uint32_t step{0};
    std::uint32_t step_count{0};
    std::string label;
};

[[nodiscard]] WorkloadRegistrySnapshot load_workload_registry(
    const std::filesystem::path& path);
[[nodiscard]] std::vector<WorkloadRampPoint> build_workload_ramps(
    const WorkloadRegistrySnapshot& registry);
[[nodiscard]] const char* workload_axis_name(WorkloadAxis axis) noexcept;

}  // namespace signalcloud::benchmark
