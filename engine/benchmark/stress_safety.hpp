#pragma once

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace signalcloud::benchmark {

struct MemorySnapshot {
    std::uint64_t total_mib{0};
    std::uint64_t available_mib{0};
    bool available{false};
};

struct MemoryGuardConfig {
    double max_ram_percent{88.0};
    std::uint64_t reserve_mib{4096};
    std::uint64_t bytes_per_point{48};
    std::uint32_t buffered_copies{3};
    double overhead_factor{1.15};
};

struct MemoryGuardDecision {
    bool allowed{true};
    bool telemetry_available{false};
    std::uint64_t requested_points{0};
    std::uint64_t safe_point_limit{0};
    std::uint64_t total_mib{0};
    std::uint64_t available_mib{0};
    std::uint64_t allowed_allocation_mib{0};
    std::uint64_t estimated_allocation_mib{0};
    std::string reason{"MEMORY_OK"};
};

[[nodiscard]] MemorySnapshot read_linux_memory_snapshot(
    const std::filesystem::path& meminfo = "/proc/meminfo");
[[nodiscard]] MemoryGuardDecision evaluate_memory_guard(
    std::uint64_t requested_points,
    const MemorySnapshot& snapshot,
    const MemoryGuardConfig& config);

enum class ThermalSensorPolicy : std::uint8_t {
    processor_gpu,
    all,
};

struct ThermalSensorReading {
    std::string identifier;
    std::string label;
    std::string source;
    double celsius{0.0};
    bool processor_or_gpu{false};
};

struct ThermalSample {
    bool available{false};
    bool selected_available{false};
    double maximum_celsius{0.0};
    double observed_maximum_celsius{0.0};
    std::size_t sensor_count{0};
    std::size_t selected_sensor_count{0};
    std::string maximum_sensor;
    std::string observed_maximum_sensor;
    std::vector<ThermalSensorReading> readings;
};

enum class ThermalState : std::uint8_t {
    unavailable,
    normal,
    warning,
    failed,
    force_stop,
};

struct ThermalGuardConfig {
    bool telemetry_enabled{true};
    bool profile_fail_enabled{false};
    bool force_stop_enabled{false};
    ThermalSensorPolicy sensor_policy{ThermalSensorPolicy::processor_gpu};
    double safe_celsius{85.0};
    double fail_celsius{100.0};
    double force_stop_celsius{105.0};
};

struct ThermalGuardDecision {
    ThermalState state{ThermalState::unavailable};
    bool profile_failure{false};
    bool abort_required{false};
    double maximum_celsius{0.0};
    double observed_maximum_celsius{0.0};
    std::size_t sensor_count{0};
    std::size_t selected_sensor_count{0};
    std::string maximum_sensor;
    std::string observed_maximum_sensor;
    std::string reason{"thermal_data_unavailable"};
};

[[nodiscard]] ThermalSensorPolicy parse_thermal_sensor_policy(
    const std::string& value) noexcept;
[[nodiscard]] const char* thermal_sensor_policy_name(
    ThermalSensorPolicy policy) noexcept;
[[nodiscard]] ThermalSample read_linux_thermal_sample(
    const std::filesystem::path& sys_root = "/sys",
    ThermalSensorPolicy policy = ThermalSensorPolicy::processor_gpu);
[[nodiscard]] ThermalGuardDecision evaluate_thermal_guard(
    const ThermalSample& sample,
    const ThermalGuardConfig& config);
[[nodiscard]] const char* thermal_state_name(ThermalState state) noexcept;

}  // namespace signalcloud::benchmark
