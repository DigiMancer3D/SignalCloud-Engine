#include "engine/benchmark/stress_safety.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <fstream>
#include <limits>
#include <optional>
#include <string>
#include <string_view>
#include <system_error>

namespace signalcloud::benchmark {
namespace {

std::uint64_t mebibytes_for_bytes(long double bytes) {
    if (!(bytes > 0.0L)) return 0;
    constexpr long double mib = 1024.0L * 1024.0L;
    const long double rounded = std::ceil(bytes / mib);
    if (rounded >= static_cast<long double>(std::numeric_limits<std::uint64_t>::max())) {
        return std::numeric_limits<std::uint64_t>::max();
    }
    return static_cast<std::uint64_t>(rounded);
}

std::string trim(std::string value) {
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.front()))) value.erase(value.begin());
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back()))) value.pop_back();
    return value;
}

std::string lowercase(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return value;
}

std::string read_text(const std::filesystem::path& path) {
    std::ifstream input(path);
    std::string value;
    std::getline(input, value);
    return trim(value);
}

std::optional<double> read_celsius(const std::filesystem::path& path) {
    std::ifstream input(path);
    long double raw = 0.0L;
    if (!(input >> raw)) return std::nullopt;
    double celsius = static_cast<double>(raw);
    if (std::abs(celsius) > 250.0) celsius /= 1000.0;
    if (!std::isfinite(celsius) || celsius < -20.0 || celsius > 150.0) return std::nullopt;
    return celsius;
}

bool contains_any(std::string_view text, const std::initializer_list<std::string_view>& tokens) {
    for (const auto token : tokens) {
        if (text.find(token) != std::string_view::npos) return true;
    }
    return false;
}

bool processor_or_gpu_sensor(std::string_view source, std::string_view label) {
    const std::string key = lowercase(std::string(source) + " " + std::string(label));
    if (contains_any(key, {"nvme", "ssd", "composite", "iwlwifi", "wifi", "wireless",
                           "battery", "bat0", "bat1", "pch", "ambient", "inlet", "dimm"})) {
        return false;
    }
    return contains_any(key, {"coretemp", "k10temp", "zenpower", "x86_pkg_temp", "package",
                              "cpu", "core", "tctl", "tdie", "soc", "gpu", "amdgpu",
                              "radeon", "nouveau", "nvidia", "junction", "edge"});
}

void append_sensor(ThermalSample& sample, ThermalSensorReading reading,
                   ThermalSensorPolicy policy) {
    sample.available = true;
    sample.sensor_count += 1U;
    if (reading.celsius > sample.observed_maximum_celsius || sample.observed_maximum_sensor.empty()) {
        sample.observed_maximum_celsius = reading.celsius;
        sample.observed_maximum_sensor = reading.identifier;
    }
    const bool selected = policy == ThermalSensorPolicy::all || reading.processor_or_gpu;
    if (selected) {
        sample.selected_available = true;
        sample.selected_sensor_count += 1U;
        if (reading.celsius > sample.maximum_celsius || sample.maximum_sensor.empty()) {
            sample.maximum_celsius = reading.celsius;
            sample.maximum_sensor = reading.identifier;
        }
    }
    sample.readings.push_back(std::move(reading));
}

}  // namespace

MemorySnapshot read_linux_memory_snapshot(const std::filesystem::path& meminfo) {
    MemorySnapshot result;
    std::ifstream input(meminfo);
    std::string key;
    std::uint64_t value_kib = 0;
    std::string unit;
    while (input >> key >> value_kib >> unit) {
        if (key == "MemTotal:") result.total_mib = value_kib / 1024ULL;
        if (key == "MemAvailable:") result.available_mib = value_kib / 1024ULL;
    }
    result.available = result.available_mib > 0;
    return result;
}

MemoryGuardDecision evaluate_memory_guard(
    std::uint64_t requested_points,
    const MemorySnapshot& snapshot,
    const MemoryGuardConfig& config) {
    MemoryGuardDecision decision;
    decision.requested_points = requested_points;
    decision.telemetry_available = snapshot.available;
    decision.total_mib = snapshot.total_mib;
    decision.available_mib = snapshot.available_mib;

    const long double copies = static_cast<long double>(std::max<std::uint32_t>(1U, config.buffered_copies));
    const long double overhead = std::clamp(config.overhead_factor, 1.0, 4.0);
    const long double bytes_per_point = static_cast<long double>(std::max<std::uint64_t>(1U, config.bytes_per_point));
    decision.estimated_allocation_mib = mebibytes_for_bytes(
        static_cast<long double>(requested_points) * bytes_per_point * copies * overhead);

    if (!snapshot.available) {
        decision.allowed = true;
        decision.reason = "MEMORY_TELEMETRY_UNAVAILABLE";
        return decision;
    }

    const double percent = std::clamp(config.max_ram_percent, 1.0, 95.0);
    const std::uint64_t percent_limit = static_cast<std::uint64_t>(
        static_cast<long double>(snapshot.total_mib) * static_cast<long double>(percent / 100.0));
    const std::uint64_t reserve_limit = snapshot.available_mib > config.reserve_mib
        ? snapshot.available_mib - config.reserve_mib : 0ULL;
    decision.allowed_allocation_mib = std::min(percent_limit, reserve_limit);

    const long double allowed_bytes = static_cast<long double>(decision.allowed_allocation_mib) * 1024.0L * 1024.0L;
    const long double divisor = bytes_per_point * copies * overhead;
    decision.safe_point_limit = divisor > 0.0L
        ? static_cast<std::uint64_t>(std::max<long double>(0.0L, std::floor(allowed_bytes / divisor)))
        : 0ULL;

    decision.allowed = requested_points <= decision.safe_point_limit;
    decision.reason = decision.allowed ? "MEMORY_OK" : "MEMORY_GUARD_REFUSAL";
    return decision;
}

ThermalSensorPolicy parse_thermal_sensor_policy(const std::string& value) noexcept {
    const std::string normalized = lowercase(value);
    return normalized == "all" ? ThermalSensorPolicy::all : ThermalSensorPolicy::processor_gpu;
}

const char* thermal_sensor_policy_name(ThermalSensorPolicy policy) noexcept {
    return policy == ThermalSensorPolicy::all ? "all" : "processor-gpu";
}

ThermalSample read_linux_thermal_sample(
    const std::filesystem::path& sys_root,
    ThermalSensorPolicy policy) {
    ThermalSample sample;
    std::error_code error;

    const auto thermal_root = sys_root / "class/thermal";
    if (std::filesystem::is_directory(thermal_root, error)) {
        for (const auto& zone : std::filesystem::directory_iterator(thermal_root, error)) {
            if (error) break;
            if (!zone.is_directory(error)) continue;
            const std::string directory_name = zone.path().filename().string();
            if (!directory_name.starts_with("thermal_zone")) continue;
            const auto celsius = read_celsius(zone.path() / "temp");
            if (!celsius) continue;
            const std::string type = read_text(zone.path() / "type");
            ThermalSensorReading reading;
            reading.identifier = directory_name + ":" + (type.empty() ? "unlabelled" : type);
            reading.label = type.empty() ? "unlabelled" : type;
            reading.source = "thermal";
            reading.celsius = *celsius;
            reading.processor_or_gpu = processor_or_gpu_sensor(reading.source, reading.label);
            append_sensor(sample, std::move(reading), policy);
        }
    }

    const auto hwmon_root = sys_root / "class/hwmon";
    error.clear();
    if (std::filesystem::is_directory(hwmon_root, error)) {
        for (const auto& hwmon : std::filesystem::directory_iterator(hwmon_root, error)) {
            if (error) break;
            if (!hwmon.is_directory(error)) continue;
            const std::string hwmon_name = read_text(hwmon.path() / "name");
            for (const auto& candidate : std::filesystem::directory_iterator(hwmon.path(), error)) {
                if (error) break;
                if (!candidate.is_regular_file(error)) continue;
                const std::string filename = candidate.path().filename().string();
                if (!filename.starts_with("temp") || !filename.ends_with("_input")) continue;
                const auto celsius = read_celsius(candidate.path());
                if (!celsius) continue;
                const std::string prefix = filename.substr(0U, filename.size() - std::string("_input").size());
                std::string label = read_text(hwmon.path() / (prefix + "_label"));
                if (label.empty()) label = prefix;
                ThermalSensorReading reading;
                reading.identifier = (hwmon_name.empty() ? hwmon.path().filename().string() : hwmon_name) + ":" + label;
                reading.label = label;
                reading.source = hwmon_name.empty() ? "hwmon" : hwmon_name;
                reading.celsius = *celsius;
                reading.processor_or_gpu = processor_or_gpu_sensor(reading.source, reading.label);
                append_sensor(sample, std::move(reading), policy);
            }
            error.clear();
        }
    }
    return sample;
}

ThermalGuardDecision evaluate_thermal_guard(
    const ThermalSample& sample,
    const ThermalGuardConfig& config) {
    ThermalGuardDecision decision;
    decision.maximum_celsius = sample.maximum_celsius;
    decision.observed_maximum_celsius = sample.observed_maximum_celsius;
    decision.sensor_count = sample.sensor_count;
    decision.selected_sensor_count = sample.selected_sensor_count;
    decision.maximum_sensor = sample.maximum_sensor;
    decision.observed_maximum_sensor = sample.observed_maximum_sensor;
    if (!config.telemetry_enabled || !sample.available) {
        decision.state = ThermalState::unavailable;
        decision.reason = "thermal_data_unavailable";
        return decision;
    }
    if (!sample.selected_available) {
        decision.state = ThermalState::unavailable;
        decision.reason = "thermal_guard_sensor_untrusted";
        return decision;
    }

    const double safe = std::clamp(config.safe_celsius, 30.0, 120.0);
    const double fail = std::max(safe + 1.0, std::clamp(config.fail_celsius, 31.0, 130.0));
    const double force_stop = std::max(fail + 1.0, std::clamp(config.force_stop_celsius, 32.0, 140.0));
    if (sample.maximum_celsius >= force_stop) {
        decision.state = ThermalState::force_stop;
        decision.profile_failure = config.profile_fail_enabled;
        decision.abort_required = config.force_stop_enabled;
        decision.reason = config.force_stop_enabled ? "THERMAL_FORCE_STOP_PENDING" :
            (config.profile_fail_enabled ? "THERMAL_FAIL_THRESHOLD" : "THERMAL_FORCE_THRESHOLD_OBSERVED");
    } else if (sample.maximum_celsius >= fail) {
        decision.state = ThermalState::failed;
        decision.profile_failure = config.profile_fail_enabled;
        decision.reason = config.profile_fail_enabled ? "THERMAL_FAIL_THRESHOLD" : "THERMAL_FAIL_THRESHOLD_OBSERVED";
    } else if (sample.maximum_celsius >= safe) {
        decision.state = ThermalState::warning;
        decision.reason = "THERMAL_ABOVE_SAFE";
    } else {
        decision.state = ThermalState::normal;
        decision.reason = "THERMAL_OK";
    }
    return decision;
}

const char* thermal_state_name(ThermalState state) noexcept {
    switch (state) {
        case ThermalState::normal: return "normal";
        case ThermalState::warning: return "warning";
        case ThermalState::failed: return "failed";
        case ThermalState::force_stop: return "force-stop";
        case ThermalState::unavailable: return "unavailable";
    }
    return "unavailable";
}

}  // namespace signalcloud::benchmark
