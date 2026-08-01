#include "engine/benchmark/stress_safety.hpp"

#include <cassert>
#include <filesystem>
#include <fstream>

int main(int argc, char** argv) {
    namespace fs = std::filesystem;
    using namespace signalcloud::benchmark;

    const fs::path root = argc > 1 ? fs::path(argv[1]) : fs::current_path();
    const fs::path temp = root / "reports" / "a9a3r1_stress_safety_test";
    fs::remove_all(temp);
    fs::create_directories(temp / "sys/class/thermal/thermal_zone0");
    fs::create_directories(temp / "sys/class/hwmon/hwmon0");
    fs::create_directories(temp / "sys/class/hwmon/hwmon1");
    {
        std::ofstream out(temp / "meminfo");
        out << "MemTotal:       67108864 kB\nMemAvailable:   50331648 kB\n";
    }
    {
        std::ofstream(temp / "sys/class/thermal/thermal_zone0/temp") << "78000\n";
        std::ofstream(temp / "sys/class/thermal/thermal_zone0/type") << "x86_pkg_temp\n";
        std::ofstream(temp / "sys/class/hwmon/hwmon0/name") << "coretemp\n";
        std::ofstream(temp / "sys/class/hwmon/hwmon0/temp1_input") << "81000\n";
        std::ofstream(temp / "sys/class/hwmon/hwmon0/temp1_label") << "Package id 0\n";
        std::ofstream(temp / "sys/class/hwmon/hwmon1/name") << "nvme\n";
        std::ofstream(temp / "sys/class/hwmon/hwmon1/temp1_input") << "98000\n";
        std::ofstream(temp / "sys/class/hwmon/hwmon1/temp1_label") << "Composite\n";
    }

    const auto memory = read_linux_memory_snapshot(temp / "meminfo");
    assert(memory.available);
    assert(memory.total_mib == 65536U);
    assert(memory.available_mib == 49152U);

    MemoryGuardConfig memory_config;
    memory_config.max_ram_percent = 88.0;
    memory_config.reserve_mib = 4096U;
    const auto accepted = evaluate_memory_guard(8'000'000U, memory, memory_config);
    assert(accepted.allowed);
    assert(accepted.reason == "MEMORY_OK");
    assert(accepted.safe_point_limit >= 8'000'000U);

    MemorySnapshot small{8192U, 5000U, true};
    const auto refused = evaluate_memory_guard(20'000'000U, small, memory_config);
    assert(!refused.allowed);
    assert(refused.reason == "MEMORY_GUARD_REFUSAL");
    assert(refused.safe_point_limit < 20'000'000U);

    const auto selected = read_linux_thermal_sample(
        temp / "sys", ThermalSensorPolicy::processor_gpu);
    assert(selected.available);
    assert(selected.selected_available);
    assert(selected.sensor_count == 3U);
    assert(selected.selected_sensor_count == 2U);
    assert(selected.maximum_celsius == 81.0);
    assert(selected.observed_maximum_celsius == 98.0);
    assert(selected.maximum_sensor.find("coretemp") != std::string::npos);
    assert(selected.observed_maximum_sensor.find("nvme") != std::string::npos);

    const auto all = read_linux_thermal_sample(temp / "sys", ThermalSensorPolicy::all);
    assert(all.maximum_celsius == 98.0);
    assert(all.selected_sensor_count == 3U);

    ThermalGuardConfig config;
    config.safe_celsius = 80.0;
    config.fail_celsius = 95.0;
    config.force_stop_celsius = 105.0;
    const auto warning = evaluate_thermal_guard(selected, config);
    assert(warning.state == ThermalState::warning);
    assert(!warning.profile_failure);
    assert(!warning.abort_required);
    assert(warning.reason == "THERMAL_ABOVE_SAFE");

    config.profile_fail_enabled = true;
    const auto failed = evaluate_thermal_guard(all, config);
    assert(failed.state == ThermalState::failed);
    assert(failed.profile_failure);
    assert(!failed.abort_required);
    assert(failed.reason == "THERMAL_FAIL_THRESHOLD");

    ThermalSample hot = all;
    hot.maximum_celsius = 108.0;
    config.force_stop_enabled = false;
    const auto observed_force = evaluate_thermal_guard(hot, config);
    assert(observed_force.state == ThermalState::force_stop);
    assert(!observed_force.abort_required);

    config.force_stop_enabled = true;
    const auto forced = evaluate_thermal_guard(hot, config);
    assert(forced.state == ThermalState::force_stop);
    assert(forced.abort_required);
    assert(forced.reason == "THERMAL_FORCE_STOP_PENDING");

    ThermalSample absent{};
    const auto unavailable = evaluate_thermal_guard(absent, config);
    assert(unavailable.state == ThermalState::unavailable);
    assert(!unavailable.abort_required);

    assert(parse_thermal_sensor_policy("all") == ThermalSensorPolicy::all);
    assert(parse_thermal_sensor_policy("processor-gpu") == ThermalSensorPolicy::processor_gpu);
    fs::remove_all(temp);
    return 0;
}
