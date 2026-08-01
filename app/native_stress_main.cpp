#include "engine/ai/playbook.hpp"
#include "engine/audio/audio_interference_runtime.hpp"
#include "engine/benchmark/machine_profile.hpp"
#include "engine/benchmark/native_stress_route.hpp"
#include "engine/benchmark/stress_safety.hpp"
#include "engine/benchmark/workload_ramp.hpp"
#include "engine/combat/combat_system.hpp"
#include "engine/economy/economy_system.hpp"
#include "engine/lighting/illuminosity_runtime.hpp"
#include "engine/items/tupd_runtime.hpp"
#include "engine/materials/material_runtime.hpp"
#include "engine/pcp3/pcp3_asset.hpp"
#include "engine/platform/capability_report.hpp"
#include "engine/platform/first_person_camera.hpp"
#include "engine/platform/video_backend.hpp"
#include "engine/render/gl_api.hpp"
#include "engine/render/local_siren.hpp"
#include "engine/render/point_cloud.hpp"
#include "engine/render/point_renderer.hpp"
#include "engine/render/room_visibility.hpp"
#include "engine/render/signal_interference.hpp"
#include "engine/render/sound_ripple.hpp"
#include "engine/render/system_point_budget.hpp"
#include "engine/render/water_disturbance.hpp"
#include "engine/scfont/font_service.hpp"
#include "engine/ui/ar_interface.hpp"
#include "engine/ui/scui_panel.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/player_controller.hpp"
#include "engine/world/recovery_system.hpp"
#include "engine/world/threat_director.hpp"
#include "engine/world/world_seed.hpp"

#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <numeric>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {

namespace fs = std::filesystem;
using signalcloud::math::Vec3;

struct Options {
    signalcloud::platform::VideoBackend backend{signalcloud::platform::VideoBackend::automatic};
    fs::path root{fs::current_path()};
    std::string mode{"all"};
    std::string progressive_range{"normal"};
    std::string run_class{"developer"};
    bool progressive{true};
    bool scanner_stages{true};
    bool presentation{true};
    bool profile_promotion{false};
    bool scare_finale{true};
    bool death_finale{true};
    bool workload_ramps{true};
    bool thermal_read{true};
    bool thermal_profile_fail{false};
    bool thermal_force_stop{false};
    std::uint32_t max_points{8'000'000U};
    int target_fps{60};
    int width{1280};
    int height{720};
    double campaign_seconds{120.0};
    double scare_seconds{30.0};
    double max_ram_percent{88.0};
    double light_budget_scale{1.0};
    std::uint64_t memory_reserve_mib{4096};
    double cpu_advisory_percent{91.0};
    double gpu_advisory_percent{97.0};
    std::string thermal_sensor_policy{"processor-gpu"};
    double thermal_safe_celsius{85.0};
    double thermal_fail_celsius{100.0};
    double thermal_force_stop_celsius{105.0};
    double thermal_force_hold_seconds{10.0};
    fs::path thermal_sys_root{"/sys"};
    fs::path session_dir;
    fs::path stop_file;
    fs::path heartbeat_file;
};

enum class StageKind : std::uint8_t {
    benchmark,
    scare_finale,
    death_finale,
};

struct StageSpec {
    std::string mode;
    std::string label;
    std::uint32_t points{500'000U};
    int entities{0};
    bool scanner{false};
    double seconds{10.0};
    StageKind kind{StageKind::benchmark};
    signalcloud::benchmark::WorkloadAxis workload_axis{signalcloud::benchmark::WorkloadAxis::none};
    std::uint32_t workload_level{0};
};

struct FpsSummary {
    double average{0.0};
    double highest{0.0};
    double lowest{0.0};
    double one_percent_low{0.0};
    double target_seconds{0.0};
    double low_seconds{0.0};
    double high_seconds{0.0};
    double longest_target{0.0};
    double longest_low{0.0};
    double longest_high{0.0};
};

struct StageSummary {
    StageSpec spec;
    FpsSummary fps;
    double elapsed{0.0};
    double generation_ms{0.0};
    std::size_t resident_points{0};
    std::size_t peak_submitted_points{0};
    std::size_t peak_renderer_submitted_points{0};
    std::size_t peak_submitted_rooms{0};
    std::size_t peak_preview_rooms{0};
    std::size_t peak_trimmed_points{0};
    double peak_gpu_ms{0.0};
    std::size_t zones_seen{0};
    double route_distance_start{0.0};
    double route_distance_end{0.0};
    int full_siren_pulses{0};
    int full_map_recoveries{0};
    std::size_t route_containment_corrections{0};
    std::size_t signal_void_entries{0};
    std::string death_cause;
    std::uint64_t workload_operations{0};
    bool guard_refused{false};
    std::string guard_reason;
    std::uint64_t memory_available_mib{0};
    std::uint64_t memory_allowed_mib{0};
    std::uint64_t memory_estimated_mib{0};
    std::uint64_t memory_safe_point_limit{0};
    bool thermal_data_available{false};
    double thermal_start_celsius{0.0};
    double thermal_peak_celsius{0.0};
    double thermal_observed_peak_celsius{0.0};
    double thermal_end_celsius{0.0};
    std::string thermal_state{"unavailable"};
    std::string thermal_sensor;
    std::string thermal_observed_sensor;
    std::size_t thermal_sensor_count{0};
    std::size_t thermal_selected_sensor_count{0};
    bool thermal_profile_failure{false};
    bool thermal_guard_triggered{false};
    double thermal_force_elapsed_seconds{0.0};
    double cpu_peak_percent{0.0};
    double gpu_frame_budget_peak_percent{0.0};
    bool passed{false};
    std::string failure;
};

struct CameraAngleSmoother {
    float yaw{0.0F};
    float pitch{0.0F};
    float yaw_velocity{0.0F};
    float pitch_velocity{0.0F};
    bool initialized{false};

    static float wrap_delta(float delta) noexcept {
        while (delta > 180.0F) delta -= 360.0F;
        while (delta < -180.0F) delta += 360.0F;
        return delta;
    }

    void update(float target_yaw, float target_pitch, float dt, bool presentation) noexcept {
        if (!initialized) {
            yaw = target_yaw;
            pitch = target_pitch;
            initialized = true;
            return;
        }
        const float safe_dt = std::clamp(dt, 0.0F, 0.10F);
        const float response = presentation ? 7.5F : 11.5F;
        const float damping = presentation ? 5.8F : 7.2F;
        const float max_velocity = presentation ? 95.0F : 165.0F;
        const float yaw_error = wrap_delta(target_yaw - yaw);
        const float pitch_error = std::clamp(target_pitch - pitch, -90.0F, 90.0F);
        yaw_velocity += (yaw_error * response - yaw_velocity * damping) * safe_dt;
        pitch_velocity += (pitch_error * response - pitch_velocity * damping) * safe_dt;
        yaw_velocity = std::clamp(yaw_velocity, -max_velocity, max_velocity);
        pitch_velocity = std::clamp(pitch_velocity, -max_velocity * 0.65F, max_velocity * 0.65F);
        yaw += yaw_velocity * safe_dt;
        pitch = std::clamp(pitch + pitch_velocity * safe_dt, -82.0F, 82.0F);
    }
};

bool create_context(SDL_Window* window, SDL_GLContext& context, int major, int minor) {
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, major);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, minor);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 24);
    context = SDL_GL_CreateContext(window);
    return context != nullptr;
}

std::optional<std::uint64_t> parse_u64(std::string_view text) {
    std::uint64_t value = 0;
    const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
    if (result.ec == std::errc{} && result.ptr == text.data() + text.size()) return value;
    return std::nullopt;
}

std::optional<double> parse_double(std::string_view text) {
    try {
        std::size_t used = 0;
        const double value = std::stod(std::string(text), &used);
        if (used == text.size()) return value;
    } catch (...) {
    }
    return std::nullopt;
}

struct CpuTimes {
    std::uint64_t total{0};
    std::uint64_t idle{0};
    bool available{false};
};

CpuTimes read_linux_cpu_times(const fs::path& stat_path = "/proc/stat") {
    CpuTimes result;
    std::ifstream input(stat_path);
    std::string cpu;
    std::array<std::uint64_t, 10U> values{};
    if (!(input >> cpu) || cpu != "cpu") return result;
    for (auto& value : values) {
        if (!(input >> value)) value = 0U;
    }
    result.idle = values[3] + values[4];
    result.total = std::accumulate(values.begin(), values.end(), std::uint64_t{0});
    result.available = result.total > 0U;
    return result;
}

double cpu_usage_percent(const CpuTimes& previous, const CpuTimes& current) {
    if (!previous.available || !current.available || current.total <= previous.total) return 0.0;
    const std::uint64_t total_delta = current.total - previous.total;
    const std::uint64_t idle_delta = current.idle >= previous.idle ? current.idle - previous.idle : 0U;
    if (total_delta == 0U) return 0.0;
    const double busy = 1.0 - static_cast<double>(std::min(idle_delta, total_delta)) /
        static_cast<double>(total_delta);
    return std::clamp(busy * 100.0, 0.0, 100.0);
}

Options parse_args(int argc, char** argv) {
    Options options;
    for (int i = 1; i < argc; ++i) {
        const std::string_view arg(argv[i]);
        const auto value_after = [&](std::string_view prefix) -> std::optional<std::string_view> {
            if (!arg.starts_with(prefix)) return std::nullopt;
            return arg.substr(prefix.size());
        };

        if (const auto value = value_after("--video=")) {
            if (const auto parsed = signalcloud::platform::parse_video_backend(*value)) options.backend = *parsed;
            continue;
        }
        if (const auto value = value_after("--root=")) {
            options.root = fs::path(std::string(*value));
            continue;
        }
        if (const auto value = value_after("--session-dir=")) {
            options.session_dir = fs::path(std::string(*value));
            continue;
        }
        if (const auto value = value_after("--stop-file=")) {
            options.stop_file = fs::path(std::string(*value));
            continue;
        }
        if (const auto value = value_after("--heartbeat-file=")) {
            options.heartbeat_file = fs::path(std::string(*value));
            continue;
        }
        if (const auto value = value_after("--mode=")) {
            options.mode = std::string(*value);
            continue;
        }
        if (const auto value = value_after("--run-class=")) {
            const std::string parsed(*value);
            if (parsed == "quick" || parsed == "standard" || parsed == "official" || parsed == "developer") {
                options.run_class = parsed;
            }
            continue;
        }
        if (const auto value = value_after("--progressive-range=")) {
            options.progressive_range = std::string(*value);
            continue;
        }
        if (const auto value = value_after("--max-points=")) {
            if (const auto parsed = parse_u64(*value)) {
                options.max_points = static_cast<std::uint32_t>(
                    std::min<std::uint64_t>(*parsed, std::numeric_limits<std::uint32_t>::max()));
            }
            continue;
        }
        if (const auto value = value_after("--target-fps=")) {
            if (const auto parsed = parse_u64(*value)) {
                options.target_fps = static_cast<int>(std::clamp<std::uint64_t>(*parsed, 15, 360));
            }
            continue;
        }
        if (const auto value = value_after("--campaign-seconds=")) {
            if (const auto parsed = parse_double(*value)) options.campaign_seconds = std::clamp(*parsed, 30.0, 540.0);
            continue;
        }
        if (const auto value = value_after("--scare-seconds=")) {
            if (const auto parsed = parse_double(*value)) {
                options.scare_seconds = *parsed < 45.0 ? 30.0 : (*parsed < 75.0 ? 60.0 : 90.0);
            }
            continue;
        }
        if (const auto value = value_after("--resolution=")) {
            const auto separator = value->find('x');
            if (separator != std::string_view::npos) {
                if (const auto parsed_width = parse_u64(value->substr(0, separator))) {
                    options.width = static_cast<int>(*parsed_width);
                }
                if (const auto parsed_height = parse_u64(value->substr(separator + 1))) {
                    options.height = static_cast<int>(*parsed_height);
                }
            }
            continue;
        }
        if (const auto value = value_after("--max-ram-percent=")) {
            if (const auto parsed = parse_double(*value)) options.max_ram_percent = std::clamp(*parsed, 10.0, 95.0);
            continue;
        }
        if (const auto value = value_after("--light-budget-scale=")) {
            if (const auto parsed = parse_double(*value)) options.light_budget_scale = std::clamp(*parsed, 0.10, 2.0);
            continue;
        }
        if (const auto value = value_after("--memory-reserve-mib=")) {
            if (const auto parsed = parse_u64(*value)) options.memory_reserve_mib = *parsed;
            continue;
        }
        if (const auto value = value_after("--cpu-advisory-percent=")) {
            if (const auto parsed = parse_double(*value)) options.cpu_advisory_percent = std::clamp(*parsed, 10.0, 100.0);
            continue;
        }
        if (const auto value = value_after("--gpu-advisory-percent=")) {
            if (const auto parsed = parse_double(*value)) options.gpu_advisory_percent = std::clamp(*parsed, 10.0, 100.0);
            continue;
        }
        if (const auto value = value_after("--thermal-sensor-policy=")) {
            options.thermal_sensor_policy = std::string(*value);
            continue;
        }
        if (const auto value = value_after("--thermal-safe-c=")) {
            if (const auto parsed = parse_double(*value)) options.thermal_safe_celsius = std::clamp(*parsed, 30.0, 120.0);
            continue;
        }
        if (const auto value = value_after("--thermal-fail-c=")) {
            if (const auto parsed = parse_double(*value)) options.thermal_fail_celsius = std::clamp(*parsed, 31.0, 130.0);
            continue;
        }
        if (const auto value = value_after("--thermal-force-stop-c=")) {
            if (const auto parsed = parse_double(*value)) options.thermal_force_stop_celsius = std::clamp(*parsed, 32.0, 140.0);
            continue;
        }
        if (const auto value = value_after("--thermal-force-hold-seconds=")) {
            if (const auto parsed = parse_double(*value)) options.thermal_force_hold_seconds = std::clamp(*parsed, 0.0, 120.0);
            continue;
        }
        // Legacy A9a3 command-line compatibility.
        if (const auto value = value_after("--thermal-warning-c=")) {
            if (const auto parsed = parse_double(*value)) options.thermal_safe_celsius = std::clamp(*parsed, 30.0, 120.0);
            continue;
        }
        if (const auto value = value_after("--thermal-critical-c=")) {
            if (const auto parsed = parse_double(*value)) {
                options.thermal_fail_celsius = std::clamp(*parsed, 31.0, 130.0);
                options.thermal_force_stop_celsius = std::clamp(*parsed + 5.0, 32.0, 140.0);
            }
            continue;
        }
        if (const auto value = value_after("--thermal-sys-root=")) {
            options.thermal_sys_root = fs::path(std::string(*value));
            continue;
        }

        if (arg == "--no-progressive") options.progressive = false;
        else if (arg == "--progressive") options.progressive = true;
        else if (arg == "--no-scanner-stages") options.scanner_stages = false;
        else if (arg == "--scanner-stages") options.scanner_stages = true;
        else if (arg == "--no-presentation") options.presentation = false;
        else if (arg == "--presentation") options.presentation = true;
        else if (arg == "--scare-finale") options.scare_finale = true;
        else if (arg == "--no-scare-finale") options.scare_finale = false;
        else if (arg == "--death-finale") options.death_finale = true;
        else if (arg == "--no-death-finale") options.death_finale = false;
        else if (arg == "--workload-ramps") options.workload_ramps = true;
        else if (arg == "--no-workload-ramps") options.workload_ramps = false;
        else if (arg == "--thermal-read") options.thermal_read = true;
        else if (arg == "--no-thermal-read") options.thermal_read = false;
        else if (arg == "--thermal-profile-fail") options.thermal_profile_fail = true;
        else if (arg == "--no-thermal-profile-fail") options.thermal_profile_fail = false;
        else if (arg == "--thermal-force-stop") options.thermal_force_stop = true;
        else if (arg == "--no-thermal-force-stop") options.thermal_force_stop = false;
        // Legacy A9a3 guard flag enables both threshold failure and force stop.
        else if (arg == "--thermal-guard") {
            options.thermal_profile_fail = true;
            options.thermal_force_stop = true;
        }
        else if (arg == "--no-thermal-guard") {
            options.thermal_profile_fail = false;
            options.thermal_force_stop = false;
        }
        else if (arg == "--promote-profile") options.profile_promotion = true;
    }
    return options;
}

fs::path safe_session_directory(const Options& options) {
    const fs::path report_root = fs::absolute(options.root / "reports/native_stress_runs").lexically_normal();
    fs::path selected = options.session_dir;
    if (selected.empty()) {
        const auto timestamp = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
        selected = report_root / ("native_" + std::to_string(timestamp));
    }
    if (!selected.is_absolute()) selected = options.root / selected;
    selected = fs::absolute(selected).lexically_normal();
    const auto relative = selected.lexically_relative(report_root);
    if (relative.empty() || relative.native().starts_with("..")) {
        throw std::runtime_error("native stress session directory escapes reports/native_stress_runs");
    }
    fs::create_directories(selected);
    return selected;
}

void atomic_write_text(const fs::path& path, const std::string& text) {
    fs::create_directories(path.parent_path());
    const fs::path temporary = path.string() + ".tmp";
    {
        std::ofstream out(temporary, std::ios::trunc);
        out << text;
    }
    std::error_code error;
    fs::rename(temporary, path, error);
    if (error) {
        fs::remove(path, error);
        fs::rename(temporary, path, error);
    }
}

void write_run_state(const Options& options, std::string_view state, std::string_view reason,
                     std::size_t completed_stages, std::size_t total_stages,
                     std::string_view current_stage = {}) {
    if (options.session_dir.empty()) return;
    std::ostringstream out;
    out << "{\n"
        << "  \"schema\": \"signalcloud_native_stress_session\",\n"
        << "  \"schema_version\": 1,\n"
        << "  \"state\": \"" << state << "\",\n"
        << "  \"reason\": \"" << reason << "\",\n"
        << "  \"completed_stages\": " << completed_stages << ",\n"
        << "  \"total_stages\": " << total_stages << ",\n"
        << "  \"current_stage\": \"" << current_stage << "\",\n"
        << "  \"profile_promotion_allowed\": "
        << (state == "completed" ? "true" : "false") << "\n"
        << "}\n";
    atomic_write_text(options.session_dir / "RUN_STATE.json", out.str());
}

void write_watchdog_heartbeat(const Options& options, double runtime, const StageSpec& stage,
                              double stage_elapsed, std::size_t completed_stages,
                              std::size_t total_stages, std::string_view phase) {
    if (options.heartbeat_file.empty()) return;
    std::ostringstream out;
    out << "{\n"
        << "  \"schema\": \"signalcloud_native_stress_heartbeat\",\n"
        << "  \"runtime_seconds\": " << runtime << ",\n"
        << "  \"stage_elapsed_seconds\": " << stage_elapsed << ",\n"
        << "  \"completed_stages\": " << completed_stages << ",\n"
        << "  \"total_stages\": " << total_stages << ",\n"
        << "  \"mode\": \"" << stage.mode << "\",\n"
        << "  \"stage\": \"" << stage.label << "\",\n"
        << "  \"phase\": \"" << phase << "\"\n"
        << "}\n";
    atomic_write_text(options.heartbeat_file, out.str());
}

void reset_stage_journal(const Options& options) {
    if (options.session_dir.empty()) return;
    std::ofstream out(options.session_dir / "STAGE_JOURNAL.csv", std::ios::trunc);
    out << "mode,stage,stage_kind,workload_axis,workload_level,workload_operations,points,entities,scanner,seconds,avg_fps,highest_fps,lowest_fps,one_percent_low,target_seconds,longest_target_seconds,low_seconds,longest_low_seconds,high_seconds,longest_high_seconds,generation_ms,peak_gpu_ms,resident_points,submitted_points_peak,renderer_submitted_points_peak,submitted_rooms_peak,preview_rooms_peak,trimmed_points_peak,full_map_recoveries,route_containment_corrections,signal_void_entries,zones_seen,route_distance_start,route_distance_end,route_distance_delta,full_siren_pulses,death_cause,guard_refused,guard_reason,memory_available_mib,memory_allowed_mib,memory_estimated_mib,memory_safe_point_limit,thermal_available,thermal_start_c,thermal_peak_c,thermal_observed_peak_c,thermal_end_c,thermal_state,thermal_sensor,thermal_observed_sensor,thermal_sensor_count,thermal_selected_sensor_count,thermal_profile_failure,thermal_guard_triggered,thermal_force_elapsed_seconds,cpu_peak_percent,gpu_frame_budget_peak_percent,passed,failure\n";
}

void append_stage_journal(const Options& options, const StageSummary& r) {
    if (options.session_dir.empty()) return;
    std::ofstream out(options.session_dir / "STAGE_JOURNAL.csv", std::ios::app);
    const char* kind = r.spec.kind == StageKind::scare_finale ? "scare_finale"
        : (r.spec.kind == StageKind::death_finale ? "death_finale" : "benchmark");
    out << r.spec.mode << ',' << '"' << r.spec.label << '"' << ',' << kind << ','
        << signalcloud::benchmark::workload_axis_name(r.spec.workload_axis) << ','
        << r.spec.workload_level << ',' << r.workload_operations << ',' << r.spec.points << ','
        << r.spec.entities << ',' << (r.spec.scanner ? 1 : 0) << ',' << r.elapsed << ','
        << r.fps.average << ',' << r.fps.highest << ',' << r.fps.lowest << ','
        << r.fps.one_percent_low << ',' << r.fps.target_seconds << ',' << r.fps.longest_target << ','
        << r.fps.low_seconds << ',' << r.fps.longest_low << ',' << r.fps.high_seconds << ','
        << r.fps.longest_high << ',' << r.generation_ms << ',' << r.peak_gpu_ms << ','
        << r.resident_points << ',' << r.peak_submitted_points << ','
        << r.peak_renderer_submitted_points << ',' << r.peak_submitted_rooms << ','
        << r.peak_preview_rooms << ',' << r.peak_trimmed_points << ','
        << r.full_map_recoveries << ',' << r.route_containment_corrections << ','
        << r.signal_void_entries << ',' << r.zones_seen << ','
        << r.route_distance_start << ',' << r.route_distance_end << ','
        << (r.route_distance_end - r.route_distance_start) << ',' << r.full_siren_pulses << ','
        << '"' << r.death_cause << '"' << ',' << (r.guard_refused ? 1 : 0) << ','
        << '"' << r.guard_reason << '"' << ',' << r.memory_available_mib << ','
        << r.memory_allowed_mib << ',' << r.memory_estimated_mib << ','
        << r.memory_safe_point_limit << ',' << (r.thermal_data_available ? 1 : 0) << ','
        << r.thermal_start_celsius << ',' << r.thermal_peak_celsius << ','
        << r.thermal_observed_peak_celsius << ',' << r.thermal_end_celsius << ','
        << r.thermal_state << ',' << '"' << r.thermal_sensor << '"' << ','
        << '"' << r.thermal_observed_sensor << '"' << ',' << r.thermal_sensor_count << ','
        << r.thermal_selected_sensor_count << ',' << (r.thermal_profile_failure ? 1 : 0) << ','
        << (r.thermal_guard_triggered ? 1 : 0) << ',' << r.thermal_force_elapsed_seconds << ','
        << r.cpu_peak_percent << ',' << r.gpu_frame_budget_peak_percent << ','
        << (r.passed ? 1 : 0) << ',' << '"' << r.failure << '"' << '\n';
}

bool stop_file_requested(const Options& options) {
    return !options.stop_file.empty() && fs::exists(options.stop_file);
}

signalcloud::benchmark::MemoryGuardDecision stage_memory_guard(
    const Options& options, std::uint32_t requested_points) {
    const auto snapshot = signalcloud::benchmark::read_linux_memory_snapshot();
    signalcloud::benchmark::MemoryGuardConfig config;
    config.max_ram_percent = options.max_ram_percent;
    config.reserve_mib = options.memory_reserve_mib;
    config.bytes_per_point = sizeof(signalcloud::render::PointGpu);
    config.buffered_copies = 3U;
    config.overhead_factor = 1.15;
    return signalcloud::benchmark::evaluate_memory_guard(requested_points, snapshot, config);
}

signalcloud::benchmark::ThermalGuardDecision current_thermal_guard(const Options& options) {
    signalcloud::benchmark::ThermalGuardConfig config;
    config.telemetry_enabled = options.thermal_read;
    config.profile_fail_enabled = options.thermal_profile_fail;
    config.force_stop_enabled = options.thermal_force_stop;
    config.sensor_policy = signalcloud::benchmark::parse_thermal_sensor_policy(options.thermal_sensor_policy);
    config.safe_celsius = options.thermal_safe_celsius;
    config.fail_celsius = options.thermal_fail_celsius;
    config.force_stop_celsius = options.thermal_force_stop_celsius;
    const auto sample = options.thermal_read
        ? signalcloud::benchmark::read_linux_thermal_sample(options.thermal_sys_root, config.sensor_policy)
        : signalcloud::benchmark::ThermalSample{};
    return signalcloud::benchmark::evaluate_thermal_guard(sample, config);
}

void apply_thermal_decision(
    StageSummary& summary,
    const signalcloud::benchmark::ThermalGuardDecision& decision,
    bool starting_sample = false,
    bool ending_sample = false) {
    summary.thermal_data_available = summary.thermal_data_available || decision.sensor_count > 0U;
    summary.thermal_sensor_count = std::max(summary.thermal_sensor_count, decision.sensor_count);
    summary.thermal_selected_sensor_count = std::max(
        summary.thermal_selected_sensor_count, decision.selected_sensor_count);
    summary.thermal_observed_peak_celsius = std::max(
        summary.thermal_observed_peak_celsius, decision.observed_maximum_celsius);
    if (!decision.observed_maximum_sensor.empty() &&
        (summary.thermal_observed_sensor.empty() ||
         decision.observed_maximum_celsius >= summary.thermal_observed_peak_celsius)) {
        summary.thermal_observed_sensor = decision.observed_maximum_sensor;
    }
    if (decision.state != signalcloud::benchmark::ThermalState::unavailable) {
        if (starting_sample) summary.thermal_start_celsius = decision.maximum_celsius;
        if (ending_sample) summary.thermal_end_celsius = decision.maximum_celsius;
        if (decision.maximum_celsius >= summary.thermal_peak_celsius || summary.thermal_sensor.empty()) {
            summary.thermal_peak_celsius = decision.maximum_celsius;
            summary.thermal_sensor = decision.maximum_sensor;
        }
        summary.thermal_state = signalcloud::benchmark::thermal_state_name(decision.state);
    } else if (summary.thermal_state == "unavailable") {
        summary.thermal_state = signalcloud::benchmark::thermal_state_name(decision.state);
    }
    summary.thermal_profile_failure = summary.thermal_profile_failure || decision.profile_failure;
}

double progressive_multiplier(std::string_view value) {
    if (value == "2x") return 2.0;
    if (value == "3x") return 3.0;
    if (value == "5x") return 5.0;
    if (value == "10x") return 10.0;
    if (value == "25x") return 25.0;
    if (value == "50x") return 50.0;
    if (value == "100x") return 100.0;
    if (value == "full-map") return std::numeric_limits<double>::infinity();
    return 1.0;
}

std::vector<std::uint32_t> native_point_tiers(std::uint32_t maximum) {
    const std::vector<std::uint32_t> declared{100'000U, 500'000U, 1'000'000U, 2'000'000U, 3'000'000U, 4'000'000U, 8'000'000U, 10'000'000U, 12'000'000U, 16'000'000U, 20'000'000U, 24'000'000U, 32'000'000U};
    std::vector<std::uint32_t> result;
    for (const auto value : declared) if (value <= maximum) result.push_back(value);
    if (result.empty() || result.back() != maximum) result.push_back(maximum);
    return result;
}

std::vector<StageSpec> build_stages(const Options& options, std::uint32_t point_ceiling) {
    std::vector<StageSpec> stages;
    auto add_campaign = [&](std::string mode) {
        if (mode == "traditional") {
            stages.push_back({mode, "Real room baseline", std::min<std::uint32_t>(500'000U, point_ceiling), 0, false, 0.0});
            stages.push_back({mode, "Real lighting and water", std::min<std::uint32_t>(2'000'000U, point_ceiling), 1, false, 0.0});
        } else if (mode == "cloud") {
            for (auto points : native_point_tiers(point_ceiling)) {
                stages.push_back({mode, "Real room cloud " + std::to_string(points), points, 0, false, 0.0});
                if (options.scanner_stages && points >= 1'000'000U) {
                    stages.push_back({mode, "Scanner reveal " + std::to_string(points), points, 0, true, 0.0});
                }
            }
        } else if (mode == "game") {
            const std::uint32_t points = std::min<std::uint32_t>(8'000'000U, point_ceiling);
            for (int entities : {1, 2, 4, 6, 8}) {
                stages.push_back({mode, "Real systems population " + std::to_string(entities), points, entities, entities >= 4 && options.scanner_stages, 0.0});
            }
        } else if (mode == "hybrid") {
            const auto tiers = native_point_tiers(point_ceiling);
            const std::size_t begin = tiers.size() > 5U ? tiers.size() - 5U : 0U;
            int entities = 2;
            for (std::size_t i = begin; i < tiers.size(); ++i) {
                stages.push_back({mode, "Real hybrid " + std::to_string(tiers[i]), tiers[i], entities, options.scanner_stages && (i % 2U == 1U), 0.0});
                entities = std::min(10, entities + 2);
            }
        } else if (mode == "workload") {
            const auto registry = signalcloud::benchmark::load_workload_registry(
                options.root / "user_data/machine_profiles/workload_registry.udata");
            const auto ramp = signalcloud::benchmark::build_workload_ramps(registry);
            const std::uint32_t points = std::min<std::uint32_t>(8'000'000U, point_ceiling);
            for (const auto& point : ramp) {
                int entities = 1;
                bool scanner = false;
                if (point.axis == signalcloud::benchmark::WorkloadAxis::animated_actors) {
                    entities = static_cast<int>(std::min<std::uint32_t>(point.level, 32U));
                } else if (point.axis == signalcloud::benchmark::WorkloadAxis::playbook_evaluations) {
                    entities = static_cast<int>(std::min<std::uint32_t>(std::max(1U, point.level / 2U), 16U));
                } else if (point.axis == signalcloud::benchmark::WorkloadAxis::sound_ripples ||
                           point.axis == signalcloud::benchmark::WorkloadAxis::scui_panels) {
                    scanner = options.scanner_stages;
                }
                stages.push_back({mode, point.label, points, entities, scanner, 0.0,
                                  StageKind::benchmark, point.axis, point.level});
            }
        }
    };
    if (options.mode == "all") {
        add_campaign("traditional"); add_campaign("cloud"); add_campaign("game"); add_campaign("hybrid");
        if (options.workload_ramps) add_campaign("workload");
    } else add_campaign(options.mode);
    std::map<std::string, int> counts;
    for (const auto& stage : stages) ++counts[stage.mode];
    for (auto& stage : stages) stage.seconds = options.campaign_seconds / std::max(1, counts[stage.mode]);

    const std::uint32_t finale_points = std::min<std::uint32_t>(8'000'000U, point_ceiling);
    if (options.scare_finale) {
        const double first_full_siren = std::max(options.scare_seconds * 0.55, options.scare_seconds - 15.0);
        const double third_full_siren_finished = first_full_siren + 10.0 + 4.0;
        stages.push_back({"finale", "Night / dual-siren scare sequence", finale_points, 4, true,
                          std::max(options.scare_seconds, third_full_siren_finished), StageKind::scare_finale});
    }
    if (options.death_finale) {
        stages.push_back({"finale", "Round-robin live-tape collapse", finale_points, 0, false,
                          3.0, StageKind::death_finale});
    }
    return stages;
}

struct DeathFinaleSelection {
    signalcloud::ui::ArDangerKind danger{signalcloud::ui::ArDangerKind::combat};
    std::string label{"COMBAT"};
    int next_index{1};
};

DeathFinaleSelection select_death_finale(const fs::path& root) {
    const fs::path cycle_path = root / "config/native_stress_death_cycle.txt";
    int index = 0;
    std::ifstream input(cycle_path);
    if (input) input >> index;
    index = ((index % 6) + 6) % 6;
    static constexpr std::array<signalcloud::ui::ArDangerKind, 6> kinds{{
        signalcloud::ui::ArDangerKind::combat,
        signalcloud::ui::ArDangerKind::drowning,
        signalcloud::ui::ArDangerKind::pressure,
        signalcloud::ui::ArDangerKind::fall,
        signalcloud::ui::ArDangerKind::poison,
        signalcloud::ui::ArDangerKind::treason,
    }};
    static constexpr std::array<std::string_view, 6> labels{{
        "COMBAT", "DROWNING", "PRESSURE", "FALL", "POISON", "TREASON"
    }};
    return {kinds[static_cast<std::size_t>(index)], std::string(labels[static_cast<std::size_t>(index)]), (index + 1) % 6};
}

void advance_death_finale(const fs::path& root, int next_index) {
    const fs::path cycle_path = root / "config/native_stress_death_cycle.txt";
    fs::create_directories(cycle_path.parent_path());
    const fs::path temporary = cycle_path.string() + ".tmp";
    std::ofstream output(temporary, std::ios::trunc);
    output << next_index << '\n';
    output.close();
    std::error_code error;
    fs::rename(temporary, cycle_path, error);
    if (error) {
        fs::remove(cycle_path, error);
        fs::rename(temporary, cycle_path, error);
    }
}

const signalcloud::world::WalkArea* find_area(const signalcloud::world::LiminalLevel& level, std::string_view zone) {
    for (const auto& area : level.areas()) if (area.name == zone) return &area;
    return nullptr;
}

void spawn_real_entities(signalcloud::combat::CombatSystem& combat,
                         const signalcloud::world::LiminalLevel& level,
                         std::string_view zone, Vec3 camera_position, int count) {
    combat.despawn_world_entities(zone);
    if (count <= 0 || signalcloud::world::zone_is_protected(zone)) return;
    const auto* area = find_area(level, zone);
    if (area == nullptr) return;
    const float half_x = std::max(2.0F, (area->max_x - area->min_x) * 0.42F);
    const float half_z = std::max(2.0F, (area->max_z - area->min_z) * 0.42F);
    for (int i = 0; i < count; ++i) {
        const float angle = static_cast<float>(i) * 2.399963F;
        const float radius = 3.2F + static_cast<float>(i % 3) * 1.15F;
        Vec3 position{camera_position.x + std::cos(angle) * radius,
                      camera_position.y,
                      camera_position.z + std::sin(angle) * radius};
        position.x = std::clamp(position.x, area->min_x + 0.8F, area->max_x - 0.8F);
        position.z = std::clamp(position.z, area->min_z + 0.8F, area->max_z - 0.8F);
        position.y = level.ground_height_at(position.x, position.z) + 1.0F;
        if (!level.can_occupy(position.x, position.z, 0.5F)) continue;
        const auto kind = i % 3 == 2 ? signalcloud::combat::CreatureKind::formless_shadow
                                     : signalcloud::combat::CreatureKind::hash_dog;
        combat.spawn_world_entity(kind, position, zone, half_x, half_z);
    }
}

FpsSummary summarize_fps(const std::vector<double>& samples, int target_fps, double dt_total) {
    FpsSummary result;
    if (samples.empty()) return result;
    result.average = std::accumulate(samples.begin(), samples.end(), 0.0) / static_cast<double>(samples.size());
    result.highest = *std::max_element(samples.begin(), samples.end());
    result.lowest = *std::min_element(samples.begin(), samples.end());
    auto sorted = samples;
    std::sort(sorted.begin(), sorted.end());
    const std::size_t low_index = std::min(sorted.size() - 1U, static_cast<std::size_t>(std::floor(static_cast<double>(sorted.size()) * 0.01)));
    result.one_percent_low = sorted[low_index];
    const double low = static_cast<double>(target_fps) * 0.92;
    const double high = static_cast<double>(target_fps) * 1.08;
    const double sample_seconds = dt_total / static_cast<double>(samples.size());
    double current_low = 0.0, current_target = 0.0, current_high = 0.0;
    for (double fps : samples) {
        if (fps < low) {
            result.low_seconds += sample_seconds; current_low += sample_seconds;
            current_target = 0.0; current_high = 0.0;
            result.longest_low = std::max(result.longest_low, current_low);
        } else if (fps > high) {
            result.high_seconds += sample_seconds; current_high += sample_seconds;
            current_low = 0.0; current_target = 0.0;
            result.longest_high = std::max(result.longest_high, current_high);
        } else {
            result.target_seconds += sample_seconds; current_target += sample_seconds;
            current_low = 0.0; current_high = 0.0;
            result.longest_target = std::max(result.longest_target, current_target);
        }
    }
    return result;
}

void reset_visibility_trace(const Options& options) {
    const fs::path path = options.root / "reports/native_stress_visibility_trace.csv";
    fs::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::trunc);
    out << "runtime_seconds,stage,zone,full_map,resident_points,selected_points,renderer_points,"
           "selected_rooms,draw_ranges,point_cap,trimmed_points,balanced_cap,recovery\n";
}

void append_visibility_trace(const Options& options, double runtime, const StageSpec& stage,
                             std::string_view zone, bool full_map,
                             const signalcloud::render::RoomVisibilitySelection& visibility,
                             std::size_t renderer_points, bool recovery) {
    const fs::path path = options.root / "reports/native_stress_visibility_trace.csv";
    std::ofstream out(path, std::ios::app);
    out << std::fixed << std::setprecision(3) << runtime << ','
        << '"' << stage.label << '"' << ',' << '"' << zone << '"' << ','
        << (full_map ? 1 : 0) << ',' << visibility.resident_points << ','
        << visibility.submitted_points << ',' << renderer_points << ','
        << visibility.submitted_rooms << ',' << visibility.ranges.size() << ','
        << visibility.submitted_point_cap << ',' << visibility.points_trimmed << ','
        << (visibility.balanced_cap_applied ? 1 : 0) << ',' << (recovery ? 1 : 0) << '\n';
}

void reset_route_containment_trace(const Options& options) {
    const fs::path path = options.root / "reports/native_stress_route_containment_trace.csv";
    fs::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::trunc);
    out << "runtime_seconds,stage,segment,progress,portal_jump,event,raw_zone,expected_zone,effective_zone,"
           "attempted_x,attempted_y,attempted_z,corrected_x,corrected_y,corrected_z,"
           "used_expected_zone,used_last_valid\n";
}

void append_route_containment_trace(
    const Options& options,
    double runtime,
    const StageSpec& stage,
    const signalcloud::benchmark::RoutePose& pose,
    Vec3 attempted,
    const signalcloud::benchmark::RouteContainmentResult& result,
    std::string_view event) {
    const fs::path path = options.root / "reports/native_stress_route_containment_trace.csv";
    std::ofstream out(path, std::ios::app);
    out << std::fixed << std::setprecision(3) << runtime << ','
        << '"' << stage.label << '"' << ',' << pose.segment_index << ','
        << pose.segment_progress << ',' << (pose.portal_jump ? 1 : 0) << ','
        << '"' << event << '"' << ',' << '"' << result.raw_zone << '"' << ','
        << '"' << pose.zone << '"' << ',' << '"' << result.effective_zone << '"' << ','
        << attempted.x << ',' << attempted.y << ',' << attempted.z << ','
        << result.position.x << ',' << result.position.y << ',' << result.position.z << ','
        << (result.used_expected_zone ? 1 : 0) << ','
        << (result.used_last_valid ? 1 : 0) << '\n';
}

void write_live_status(const Options& options, double runtime, const StageSpec& stage,
                       double stage_elapsed, float displayed_fps, double route_distance,
                       Vec3 camera_position, int floor_level, std::string_view alert,
                       std::string_view zone, const StageSummary& summary,
                       const signalcloud::render::RoomVisibilitySelection& visibility,
                       std::size_t renderer_submitted_points, int full_map_recoveries,
                       std::string_view raw_zone,
                       std::size_t route_containment_corrections,
                       std::size_t signal_void_entries,
                       int entities, bool scanner, bool night_active,
                       bool local_siren_active, int full_siren_pulses,
                       std::uint32_t authored_light_budget, float authored_local_strength,
                       float authored_global_strength,
                       std::uint32_t material_point_budget, std::size_t active_materials,
                       std::uint32_t sound_interference_serial,
                       std::uint32_t audio_interference_budget, std::uint32_t audio_wave_count,
                       std::string_view death_cause, std::string_view finale_phase) {
    const fs::path path = options.root / "reports/native_stress_live.json";
    fs::create_directories(path.parent_path());
    const fs::path temporary = path.string() + ".tmp";
    std::ofstream out(temporary, std::ios::trunc);
    out << "{\n"
        << "  \"runtime_seconds\": " << runtime << ",\n"
        << "  \"stage_elapsed_seconds\": " << stage_elapsed << ",\n"
        << "  \"stage_duration_seconds\": " << stage.seconds << ",\n"
        << "  \"fps\": " << displayed_fps << ",\n"
        << "  \"target_fps\": " << options.target_fps << ",\n"
        << "  \"route_distance\": " << route_distance << ",\n"
        << "  \"camera_y\": " << camera_position.y << ",\n"
        << "  \"floor_level\": " << floor_level << ",\n"
        << "  \"alert\": \"" << alert << "\",\n"
        << "  \"mode\": \"" << stage.mode << "\",\n"
        << "  \"stage\": \"" << stage.label << "\",\n"
        << "  \"workload_axis\": \"" << signalcloud::benchmark::workload_axis_name(stage.workload_axis) << "\",\n"
        << "  \"workload_level\": " << stage.workload_level << ",\n"
        << "  \"workload_operations\": " << summary.workload_operations << ",\n"
        << "  \"location\": \"" << zone << "\",\n"
        << "  \"resident_points\": " << summary.resident_points << ",\n"
        << "  \"submitted_points\": " << visibility.submitted_points << ",\n"
        << "  \"renderer_submitted_points\": " << renderer_submitted_points << ",\n"
        << "  \"submitted_rooms\": " << visibility.submitted_rooms << ",\n"
        << "  \"draw_ranges\": " << visibility.ranges.size() << ",\n"
        << "  \"balanced_full_map_cap\": " << (visibility.balanced_cap_applied ? "true" : "false") << ",\n"
        << "  \"full_map_recoveries\": " << full_map_recoveries << ",\n"
        << "  \"raw_location\": \"" << raw_zone << "\",\n"
        << "  \"route_containment_corrections\": " << route_containment_corrections << ",\n"
        << "  \"signal_void_entries\": " << signal_void_entries << ",\n"
        << "  \"preview_rooms\": " << visibility.preview_rooms << ",\n"
        << "  \"entities\": " << entities << ",\n"
        << "  \"scanner\": " << (scanner ? "true" : "false") << ",\n"
        << "  \"night_active\": " << (night_active ? "true" : "false") << ",\n"
        << "  \"local_siren_active\": " << (local_siren_active ? "true" : "false") << ",\n"
        << "  \"full_siren_pulses\": " << full_siren_pulses << ",\n"
        << "  \"authored_light_budget\": " << authored_light_budget << ",\n"
        << "  \"authored_local_strength\": " << authored_local_strength << ",\n"
        << "  \"authored_global_strength\": " << authored_global_strength << ",\n"
        << "  \"material_point_budget\": " << material_point_budget << ",\n"
        << "  \"active_materials\": " << active_materials << ",\n"
        << "  \"sound_interference_serial\": " << sound_interference_serial << ",\n"
        << "  \"audio_interference_budget\": " << audio_interference_budget << ",\n"
        << "  \"audio_wave_count\": " << audio_wave_count << ",\n"
        << "  \"memory_available_mib\": " << summary.memory_available_mib << ",\n"
        << "  \"memory_allowed_mib\": " << summary.memory_allowed_mib << ",\n"
        << "  \"memory_estimated_mib\": " << summary.memory_estimated_mib << ",\n"
        << "  \"memory_safe_point_limit\": " << summary.memory_safe_point_limit << ",\n"
        << "  \"thermal_available\": " << (summary.thermal_data_available ? "true" : "false") << ",\n"
        << "  \"thermal_peak_celsius\": " << summary.thermal_peak_celsius << ",\n"
        << "  \"thermal_observed_peak_celsius\": " << summary.thermal_observed_peak_celsius << ",\n"
        << "  \"thermal_state\": \"" << summary.thermal_state << "\",\n"
        << "  \"thermal_sensor\": \"" << summary.thermal_sensor << "\",\n"
        << "  \"thermal_observed_sensor\": \"" << summary.thermal_observed_sensor << "\",\n"
        << "  \"thermal_sensor_count\": " << summary.thermal_sensor_count << ",\n"
        << "  \"thermal_selected_sensor_count\": " << summary.thermal_selected_sensor_count << ",\n"
        << "  \"thermal_sensor_policy\": \"" << options.thermal_sensor_policy << "\",\n"
        << "  \"thermal_safe_celsius\": " << options.thermal_safe_celsius << ",\n"
        << "  \"thermal_fail_celsius\": " << options.thermal_fail_celsius << ",\n"
        << "  \"thermal_force_stop_celsius\": " << options.thermal_force_stop_celsius << ",\n"
        << "  \"thermal_force_hold_seconds\": " << options.thermal_force_hold_seconds << ",\n"
        << "  \"thermal_force_elapsed_seconds\": " << summary.thermal_force_elapsed_seconds << ",\n"
        << "  \"thermal_profile_failure\": " << (summary.thermal_profile_failure ? "true" : "false") << ",\n"
        << "  \"cpu_peak_percent\": " << summary.cpu_peak_percent << ",\n"
        << "  \"cpu_advisory_percent\": " << options.cpu_advisory_percent << ",\n"
        << "  \"gpu_frame_budget_peak_percent\": " << summary.gpu_frame_budget_peak_percent << ",\n"
        << "  \"gpu_advisory_percent\": " << options.gpu_advisory_percent << ",\n"
        << "  \"death_cause\": \"" << death_cause << "\",\n"
        << "  \"finale_phase\": \"" << finale_phase << "\",\n"
        << "  \"progressive\": " << (options.progressive ? "true" : "false") << ",\n"
        << "  \"progressive_range\": \"" << options.progressive_range << "\"\n"
        << "}\n";
    out.close();
    std::error_code error;
    fs::rename(temporary, path, error);
    if (error) {
        fs::remove(path, error);
        fs::rename(temporary, path, error);
    }
    if (!options.session_dir.empty()) {
        std::error_code copy_error;
        fs::copy_file(path, options.session_dir / "LIVE_SNAPSHOT.json",
                      fs::copy_options::overwrite_existing, copy_error);
    }
}


std::uint32_t snap_profile_tier(std::uint32_t sustainable_points, std::string_view gpu_class) {
    static constexpr std::array<std::uint32_t, 7U> tiers{{
        100'000U, 500'000U, 1'000'000U, 2'000'000U, 3'000'000U, 4'000'000U, 8'000'000U,
    }};
    if (gpu_class == "integrated" && sustainable_points >= 8'000'000U) return 8'000'000U;
    const auto safety_target = static_cast<std::uint32_t>(static_cast<double>(sustainable_points) * 0.85);
    std::uint32_t selected = tiers.front();
    for (const auto tier : tiers) {
        if (tier <= safety_target && tier <= sustainable_points) selected = tier;
    }
    return selected;
}

std::uint32_t combined_profile_budget(std::uint32_t environment_points) {
    if (environment_points >= 8'000'000U) return 20'000'000U;
    if (environment_points >= 4'000'000U) return 12'000'000U;
    if (environment_points >= 2'000'000U) return 8'000'000U;
    return 4'000'000U;
}

std::uint32_t protected_profile_fallback(std::uint32_t environment_points) {
    if (environment_points >= 8'000'000U) return 4'000'000U;
    if (environment_points >= 4'000'000U) return 2'000'000U;
    if (environment_points >= 2'000'000U) return 1'000'000U;
    return 100'000U;
}

signalcloud::benchmark::MachineProfile build_profile_candidate(
    const Options& options,
    const std::vector<StageSummary>& results,
    const signalcloud::platform::CapabilityReport& capability,
    std::string_view video_driver,
    const signalcloud::lighting::IlluminosityRuntimeStats& light_stats,
    const signalcloud::materials::MaterialRuntimeStats& material_stats,
    bool run_completed) {
    const signalcloud::benchmark::MachineProfileContext context{
        capability.vendor,
        capability.renderer,
        capability.version,
        std::string(video_driver),
        capability.gl_major,
        capability.gl_minor,
        options.width,
        options.height,
        signalcloud::benchmark::hash_machine_profile_content_manifest(options.root / "content/manifest.csv"),
    };
    signalcloud::benchmark::MachineProfile profile;
    profile.status = "candidate";
    profile.source_kind = "engine-native-stress";
    profile.run_class = options.run_class;
    profile.ruleset_id = std::string(signalcloud::benchmark::kMachineProfileRuleset);
    profile.fingerprint = signalcloud::benchmark::make_machine_fingerprint(context);
    profile.content_hash = context.content_hash;
    profile.gpu_class = signalcloud::benchmark::classify_gpu(capability.vendor, capability.renderer);
    profile.resolution_width = options.width;
    profile.resolution_height = options.height;
    profile.target_fps = options.target_fps;

    bool route_pass = true;
    bool memory_guard_safe = true;
    bool thermal_guard_safe = true;
    std::uint32_t passed_stages = 0U;
    std::uint32_t failed_stages = 0U;
    std::map<signalcloud::benchmark::WorkloadAxis, std::uint32_t> workload_limits;
    for (const auto& result : results) {
        if (result.spec.kind != StageKind::benchmark) continue;
        if (result.guard_refused) {
            if (result.guard_reason == "MEMORY_GUARD_REFUSAL") {
                memory_guard_safe = memory_guard_safe && true;
                continue;
            }
            thermal_guard_safe = false;
            ++failed_stages;
            continue;
        }
        if (result.thermal_profile_failure || result.thermal_guard_triggered) {
            thermal_guard_safe = false;
        }
        const bool route_completed = result.route_distance_end > result.route_distance_start + 0.5;
        const bool stage_completed = result.elapsed + 0.15 >= result.spec.seconds;
        const bool fatal_upload = result.failure.find("POINT_UPLOAD_FAILED") != std::string::npos;
        if (stage_completed && route_completed && !fatal_upload) {
            profile.burst_environment_points = std::max(profile.burst_environment_points, result.spec.points);
            profile.burst_entities = std::max(profile.burst_entities, result.spec.entities);
        }
        if (result.passed) {
            ++passed_stages;
            profile.sustainable_environment_points = std::max(
                profile.sustainable_environment_points, result.spec.points);
            profile.sustainable_entities = std::max(profile.sustainable_entities, result.spec.entities);
            if (result.spec.workload_axis != signalcloud::benchmark::WorkloadAxis::none) {
                workload_limits[result.spec.workload_axis] = std::max(
                    workload_limits[result.spec.workload_axis], result.spec.workload_level);
            }
        } else {
            ++failed_stages;
        }
        const bool recovered_void_entries =
            result.signal_void_entries <= result.route_containment_corrections;
        if (result.failure == "ROUTE_DID_NOT_PROGRESS" || !recovered_void_entries) route_pass = false;
    }

    const std::uint32_t recommendation = snap_profile_tier(
        profile.sustainable_environment_points, profile.gpu_class);
    profile.recommended.environment_points = recommendation;
    profile.recommended.combined_point_budget = combined_profile_budget(recommendation);
    profile.recommended.protected_fallback_points = protected_profile_fallback(recommendation);
    profile.recommended.submitted_soft_cap = signalcloud::render::system_point_budget_for_total(
        profile.recommended.combined_point_budget).submitted_soft_cap;
    profile.recommended.full_rate_entities = std::max(1, profile.sustainable_entities / 2);
    profile.recommended.reduced_rate_entities = std::max(
        profile.recommended.full_rate_entities, profile.sustainable_entities);
    const auto workload_limit = [&](signalcloud::benchmark::WorkloadAxis axis, std::uint32_t fallback) {
        const auto match = workload_limits.find(axis);
        return match == workload_limits.end() ? fallback : std::max(1U, match->second);
    };
    profile.recommended.active_lights = std::min<std::uint32_t>(
        workload_limit(signalcloud::benchmark::WorkloadAxis::lights, 4U),
        static_cast<std::uint32_t>(std::max<std::size_t>(1U, light_stats.enabled_lights)));
    profile.recommended.material_layers = std::min<std::uint32_t>(
        workload_limit(signalcloud::benchmark::WorkloadAxis::material_layers, 3U),
        static_cast<std::uint32_t>(std::max<std::size_t>(1U, material_stats.selected_materials)));
    profile.recommended.sound_ripples = workload_limit(
        signalcloud::benchmark::WorkloadAxis::sound_ripples, 3U);
    profile.recommended.animated_actors = workload_limit(
        signalcloud::benchmark::WorkloadAxis::animated_actors,
        static_cast<std::uint32_t>(std::max(1, profile.sustainable_entities)));
    profile.recommended.playbook_evaluations = workload_limit(
        signalcloud::benchmark::WorkloadAxis::playbook_evaluations,
        static_cast<std::uint32_t>(std::max(8, profile.sustainable_entities * 2)));
    profile.recommended.tupd_test_objects = workload_limit(
        signalcloud::benchmark::WorkloadAxis::tupd_test_objects, 2U);
    profile.recommended.scui_panels = workload_limit(
        signalcloud::benchmark::WorkloadAxis::scui_panels, 3U);

    profile.validation.completed = run_completed;
    profile.validation.route_pass = route_pass && passed_stages > 0U;
    profile.validation.frame_pacing_pass = profile.sustainable_environment_points > 0U;
    profile.validation.memory_guard_pass = memory_guard_safe && thermal_guard_safe &&
        profile.burst_environment_points <= options.max_points;
    profile.validation.content_hash_pass = !profile.content_hash.empty();
    profile.validation.passed_stages = passed_stages;
    profile.validation.failed_stages = failed_stages;
    return profile;
}

void write_results(const Options& options, const std::vector<StageSummary>& results,
                   const signalcloud::benchmark::NativeStressRoute& route,
                   const signalcloud::platform::CapabilityReport& capability,
                   std::string_view video_driver,
                   const signalcloud::lighting::IlluminosityRuntimeStats& light_stats,
                   const signalcloud::materials::MaterialRuntimeStats& material_stats,
                   const signalcloud::audio::AudioInterferenceStats& audio_stats,
                   bool run_completed, std::string_view completion_reason) {
    const fs::path& dir = options.session_dir;
    fs::create_directories(dir);
    std::ofstream csv(dir / "NATIVE_STRESS_RESULTS.csv", std::ios::trunc);
    csv << "mode,stage,stage_kind,workload_axis,workload_level,workload_operations,points,entities,scanner,seconds,avg_fps,highest_fps,lowest_fps,one_percent_low,target_seconds,longest_target_seconds,low_seconds,longest_low_seconds,high_seconds,longest_high_seconds,generation_ms,peak_gpu_ms,resident_points,submitted_points_peak,renderer_submitted_points_peak,submitted_rooms_peak,preview_rooms_peak,trimmed_points_peak,full_map_recoveries,route_containment_corrections,signal_void_entries,zones_seen,route_distance_start,route_distance_end,route_distance_delta,full_siren_pulses,death_cause,guard_refused,guard_reason,memory_available_mib,memory_allowed_mib,memory_estimated_mib,memory_safe_point_limit,thermal_available,thermal_start_c,thermal_peak_c,thermal_observed_peak_c,thermal_end_c,thermal_state,thermal_sensor,thermal_observed_sensor,thermal_sensor_count,thermal_selected_sensor_count,thermal_profile_failure,thermal_guard_triggered,thermal_force_elapsed_seconds,cpu_peak_percent,gpu_frame_budget_peak_percent,passed,failure\n";
    for (const auto& r : results) {
        const char* kind = r.spec.kind == StageKind::scare_finale ? "scare_finale"
            : (r.spec.kind == StageKind::death_finale ? "death_finale" : "benchmark");
        csv << r.spec.mode << ',' << '"' << r.spec.label << '"' << ',' << kind << ','
            << signalcloud::benchmark::workload_axis_name(r.spec.workload_axis) << ','
            << r.spec.workload_level << ',' << r.workload_operations << ',' << r.spec.points << ','
            << r.spec.entities << ',' << (r.spec.scanner ? 1 : 0) << ',' << r.elapsed << ','
            << r.fps.average << ',' << r.fps.highest << ',' << r.fps.lowest << ','
            << r.fps.one_percent_low << ',' << r.fps.target_seconds << ',' << r.fps.longest_target << ','
            << r.fps.low_seconds << ',' << r.fps.longest_low << ',' << r.fps.high_seconds << ','
            << r.fps.longest_high << ',' << r.generation_ms << ',' << r.peak_gpu_ms << ','
            << r.resident_points << ',' << r.peak_submitted_points << ','
            << r.peak_renderer_submitted_points << ',' << r.peak_submitted_rooms << ','
            << r.peak_preview_rooms << ',' << r.peak_trimmed_points << ','
            << r.full_map_recoveries << ',' << r.route_containment_corrections << ','
            << r.signal_void_entries << ',' << r.zones_seen << ','
            << r.route_distance_start << ',' << r.route_distance_end << ','
            << (r.route_distance_end - r.route_distance_start) << ',' << r.full_siren_pulses << ','
            << '"' << r.death_cause << '"' << ',' << (r.guard_refused ? 1 : 0) << ','
            << '"' << r.guard_reason << '"' << ',' << r.memory_available_mib << ','
            << r.memory_allowed_mib << ',' << r.memory_estimated_mib << ','
            << r.memory_safe_point_limit << ',' << (r.thermal_data_available ? 1 : 0) << ','
            << r.thermal_start_celsius << ',' << r.thermal_peak_celsius << ','
            << r.thermal_observed_peak_celsius << ',' << r.thermal_end_celsius << ','
            << r.thermal_state << ',' << '"' << r.thermal_sensor << '"' << ','
            << '"' << r.thermal_observed_sensor << '"' << ',' << r.thermal_sensor_count << ','
            << r.thermal_selected_sensor_count << ',' << (r.thermal_profile_failure ? 1 : 0) << ','
            << (r.thermal_guard_triggered ? 1 : 0) << ',' << r.thermal_force_elapsed_seconds << ','
            << r.cpu_peak_percent << ',' << r.gpu_frame_budget_peak_percent << ','
            << (r.passed ? 1 : 0) << ',' << '"' << r.failure << '"' << '\n';
    }
    std::size_t memory_refusals = 0U;
    std::size_t thermal_fail_events = 0U;
    std::size_t thermal_guard_events = 0U;
    bool thermal_available = false;
    double thermal_peak = 0.0;
    double thermal_observed_peak = 0.0;
    double cpu_peak = 0.0;
    double gpu_budget_peak = 0.0;
    std::string thermal_peak_sensor;
    std::string thermal_observed_peak_sensor;
    std::map<signalcloud::benchmark::WorkloadAxis, std::uint32_t> workload_pass_limits;
    for (const auto& result : results) {
        if (result.guard_reason == "MEMORY_GUARD_REFUSAL") ++memory_refusals;
        if (result.thermal_profile_failure) ++thermal_fail_events;
        if (result.thermal_guard_triggered) ++thermal_guard_events;
        thermal_available = thermal_available || result.thermal_data_available;
        if (result.thermal_peak_celsius >= thermal_peak && !result.thermal_sensor.empty()) {
            thermal_peak = result.thermal_peak_celsius;
            thermal_peak_sensor = result.thermal_sensor;
        }
        if (result.thermal_observed_peak_celsius >= thermal_observed_peak &&
            !result.thermal_observed_sensor.empty()) {
            thermal_observed_peak = result.thermal_observed_peak_celsius;
            thermal_observed_peak_sensor = result.thermal_observed_sensor;
        }
        cpu_peak = std::max(cpu_peak, result.cpu_peak_percent);
        gpu_budget_peak = std::max(gpu_budget_peak, result.gpu_frame_budget_peak_percent);
        if (result.passed && result.spec.workload_axis != signalcloud::benchmark::WorkloadAxis::none) {
            workload_pass_limits[result.spec.workload_axis] = std::max(
                workload_pass_limits[result.spec.workload_axis], result.spec.workload_level);
        }
    }
    std::ofstream workload_report(dir / "WORKLOAD_RAMP_REPORT.md", std::ios::trunc);
    workload_report << "# SignalCloud Workload Ramp Report\n\n"
                    << "- Registry source: `user_data/machine_profiles/workload_registry.udata`\n"
                    << "- Workload stages: ";
    std::size_t workload_stage_count = 0U;
    for (const auto& result : results) {
        if (result.spec.workload_axis != signalcloud::benchmark::WorkloadAxis::none) ++workload_stage_count;
    }
    workload_report << workload_stage_count << "\n\n"
                    << "| Axis | Highest passing level |\n|---|---:|\n";
    for (const auto axis : {signalcloud::benchmark::WorkloadAxis::lights,
                            signalcloud::benchmark::WorkloadAxis::material_layers,
                            signalcloud::benchmark::WorkloadAxis::sound_ripples,
                            signalcloud::benchmark::WorkloadAxis::animated_actors,
                            signalcloud::benchmark::WorkloadAxis::playbook_evaluations,
                            signalcloud::benchmark::WorkloadAxis::tupd_test_objects,
                            signalcloud::benchmark::WorkloadAxis::scui_panels}) {
        workload_report << '|' << signalcloud::benchmark::workload_axis_name(axis) << '|'
                        << workload_pass_limits[axis] << "|\n";
    }
    std::ofstream safety_report(dir / "SAFETY_GUARD_REPORT.md", std::ios::trunc);
    safety_report << "# SignalCloud Stress Safety Report\n\n"
                  << "- Memory guard refusals: " << memory_refusals << "\n"
                  << "- Memory reserve: " << options.memory_reserve_mib << " MiB\n"
                  << "- Maximum RAM share: " << options.max_ram_percent << "%\n"
                  << "- CPU advisory ceiling: " << options.cpu_advisory_percent
                  << "% (real Linux system CPU telemetry; advisory only)\n"
                  << "- GPU advisory ceiling: " << options.gpu_advisory_percent
                  << "% (renderer GPU-frame-budget pressure; advisory only)\n"
                  << "- Observed CPU peak: " << cpu_peak << "%\n"
                  << "- Observed GPU frame-budget peak: " << gpu_budget_peak << "%\n"
                  << "- Thermal telemetry: " << (thermal_available ? "available" : "thermal_data_unavailable") << "\n"
                  << "- Thermal sensor policy: `" << options.thermal_sensor_policy << "`\n"
                  << "- Selected thermal peak: " << thermal_peak << " C"
                  << (thermal_peak_sensor.empty() ? "" : " from `" + thermal_peak_sensor + "`") << "\n"
                  << "- All-sensor observed peak: " << thermal_observed_peak << " C"
                  << (thermal_observed_peak_sensor.empty() ? "" : " from `" + thermal_observed_peak_sensor + "`") << "\n"
                  << "- Thermal fail-mark events: " << thermal_fail_events << "\n"
                  << "- Thermal force-stop events: " << thermal_guard_events << "\n"
                  << "- Thermal threshold authority: safe " << options.thermal_safe_celsius
                  << " C / fail " << options.thermal_fail_celsius << " C / force stop "
                  << options.thermal_force_stop_celsius << " C after "
                  << options.thermal_force_hold_seconds << " sustained seconds\n"
                  << "- Thermal profile-fail enforcement: " << (options.thermal_profile_fail ? "on" : "off") << "\n"
                  << "- Thermal force-stop enforcement: " << (options.thermal_force_stop ? "on" : "off") << "\n";
    std::ofstream report(dir / "NATIVE_STRESS_REPORT.md", std::ios::trunc);
    report << "# SignalCloud Engine-Native Stress Report\n\n"
           << "- Run status: "
           << (run_completed ? "**COMPLETED**" : "**INTERRUPTED — NOT ELIGIBLE FOR PROFILE PROMOTION**")
           << "\n"
           << "- Completion reason: `" << completion_reason << "`\n"
           << "- Renderer: `" << capability.renderer << "`\n"
           << "- OpenGL: `" << capability.version << "`\n"
           << "- Route length: " << route.length() << " metres\n"
           << "- Route zones: " << route.zone_count() << "\n"
           << "- Run class: `" << options.run_class << "`\n"
           << "- Ruleset: `" << signalcloud::benchmark::kMachineProfileRuleset << "`\n"
           << "- Authored light budget: " << light_stats.point_budget_cost
           << " points across " << light_stats.enabled_lights << " enabled lights\n"
           << "- Authored light source: `" << light_stats.source_document << "`\n"
           << "- Material budget: " << material_stats.selected_point_budget << "/"
           << material_stats.max_point_budget << " points across "
           << material_stats.selected_materials << " selected materials\n"
           << "- Texture graph: `" << material_stats.source_graph << "`\n"
           << "- Audio-interference budget: " << audio_stats.point_budget_cost
           << " points from `" << audio_stats.source_profile << "`\n"
           << "- Progressive handling: " << (options.progressive ? "on" : "off") << "\n"
           << "- Progressive range: `" << options.progressive_range << "`\n"
           << "- Scare finale: " << (options.scare_finale ? "on" : "off")
           << " (" << options.scare_seconds << " requested seconds)\n"
           << "- Death finale: " << (options.death_finale ? "on" : "off") << "\n"
           << "- Workload-specific ramps: " << (options.workload_ramps ? "on" : "off") << "\n"
           << "- Memory guard refusals: " << memory_refusals << "\n"
           << "- Maximum RAM share: " << options.max_ram_percent << "% with "
           << options.memory_reserve_mib << " MiB reserve\n"
           << "- CPU advisory ceiling / observed peak: " << options.cpu_advisory_percent
           << "% / " << cpu_peak << "%\n"
           << "- GPU frame-budget advisory / observed peak: " << options.gpu_advisory_percent
           << "% / " << gpu_budget_peak << "%\n"
           << "- Thermal telemetry: " << (thermal_available ? "available" : "thermal_data_unavailable") << "\n"
           << "- Thermal sensor policy: `" << options.thermal_sensor_policy << "`\n"
           << "- Selected thermal peak: " << thermal_peak << " C"
           << (thermal_peak_sensor.empty() ? "" : " from `" + thermal_peak_sensor + "`") << "\n"
           << "- All-sensor observed peak: " << thermal_observed_peak << " C"
           << (thermal_observed_peak_sensor.empty() ? "" : " from `" + thermal_observed_peak_sensor + "`") << "\n"
           << "- Thermal authority: safe " << options.thermal_safe_celsius
           << " C / fail " << options.thermal_fail_celsius << " C / force stop "
           << options.thermal_force_stop_celsius << " C after " << options.thermal_force_hold_seconds
           << " sustained seconds\n"
           << "- Thermal fail marks / force stops: " << thermal_fail_events << " / "
           << thermal_guard_events << "\n\n"
           << "| Mode | Stage | Workload | Level | Points | Entities | Avg FPS | Low | High | Memory MiB | CPU % | GPU budget % | Thermal C | Sensor | Guard | Route m | Pass |\n"
           << "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---|\n";
    for (const auto& r : results) {
        report << '|' << r.spec.mode << '|' << r.spec.label << '|'
               << signalcloud::benchmark::workload_axis_name(r.spec.workload_axis) << '|'
               << r.spec.workload_level << '|' << r.spec.points << '|' << r.spec.entities << '|'
               << std::fixed << std::setprecision(1) << r.fps.average << '|' << r.fps.lowest << '|'
               << r.fps.highest << '|' << r.memory_estimated_mib << '|'
               << r.cpu_peak_percent << '|' << r.gpu_frame_budget_peak_percent << '|'
               << r.thermal_peak_celsius << '|' << r.thermal_sensor << '|'
               << (r.guard_refused ? r.guard_reason
                   : (r.thermal_guard_triggered ? "THERMAL_FORCE_STOP"
                      : (r.thermal_profile_failure ? "THERMAL_FAIL_THRESHOLD" : "none"))) << '|'
               << (r.route_distance_end - r.route_distance_start) << '|'
               << (r.guard_refused ? "REFUSED" : (r.passed ? "PASS" : "FAIL")) << "|\n";
    }
    std::ofstream latest(options.root / "reports/native_stress_latest_path.txt", std::ios::trunc);
    latest << dir.string() << '\n';
    const bool write_candidate = run_completed && (options.profile_promotion || options.run_class != "developer");
    if (write_candidate) {
        const auto candidate = build_profile_candidate(
            options, results, capability, video_driver, light_stats, material_stats, run_completed);
        const auto paths = signalcloud::benchmark::machine_profile_paths(options.root);
        std::string profile_error;
        if (!signalcloud::benchmark::save_machine_profile_atomic(candidate, paths.candidate, &profile_error)) {
            std::cerr << "Machine-profile candidate warning: " << profile_error << '\n';
        } else {
            std::string validation_reason;
            const signalcloud::benchmark::MachineProfileContext profile_context{
                capability.vendor,
                capability.renderer,
                capability.version,
                std::string(video_driver),
                capability.gl_major,
                capability.gl_minor,
                options.width,
                options.height,
                candidate.content_hash,
            };
            const bool valid_candidate = signalcloud::benchmark::validate_profile_candidate(
                candidate, profile_context, &validation_reason);
            std::ofstream profile_note(dir / "MACHINE_PROFILE_CANDIDATE.md", std::ios::trunc);
            profile_note << "# Machine Profile Candidate\n\n"
                         << "- Status: " << (valid_candidate ? "VALID" : "REJECTED") << "\n"
                         << "- Run class: `" << candidate.run_class << "`\n"
                         << "- Ruleset: `" << candidate.ruleset_id << "`\n"
                         << "- Fingerprint: `" << candidate.fingerprint << "`\n"
                         << "- Burst environment points: " << candidate.burst_environment_points << "\n"
                         << "- Sustainable environment points: " << candidate.sustainable_environment_points << "\n"
                         << "- Recommended environment points: " << candidate.recommended.environment_points << "\n"
                         << "- Recommended combined point budget: " << candidate.recommended.combined_point_budget << "\n"
                         << "- Protected fallback: " << candidate.recommended.protected_fallback_points << "\n"
                         << "- Submitted soft cap: " << candidate.recommended.submitted_soft_cap << "\n"
                         << "- Target: " << candidate.resolution_width << 'x'
                         << candidate.resolution_height << " @ " << candidate.target_fps << " FPS\n"
                         << "- Validation gates: completed "
                         << (candidate.validation.completed ? "PASS" : "FAIL")
                         << " | route " << (candidate.validation.route_pass ? "PASS" : "FAIL")
                         << " | frame pacing "
                         << (candidate.validation.frame_pacing_pass ? "PASS" : "FAIL")
                         << " | memory guard "
                         << (candidate.validation.memory_guard_pass ? "PASS" : "FAIL")
                         << " | content hash "
                         << (candidate.validation.content_hash_pass ? "PASS" : "FAIL")
                         << " | stages " << candidate.validation.passed_stages << " passed / "
                         << candidate.validation.failed_stages << " failed\n"
                         << "- Validation: " << validation_reason << "\n"
                         << "- Privacy: capability identity is hashed; no username, hostname, home path, or serial is stored.\n";
            if (options.profile_promotion && valid_candidate) {
                if (signalcloud::benchmark::promote_candidate_atomic(options.root, profile_context, &profile_error)) {
                    profile_note << "- Promotion: ACTIVE profile replaced atomically; previous active profile preserved.\n";
                    std::cout << "Machine profile promoted atomically: " << paths.active << '\n';
                } else {
                    profile_note << "- Promotion: REJECTED — " << profile_error << "\n";
                    std::cerr << "Machine-profile promotion rejected: " << profile_error << '\n';
                }
            } else if (options.profile_promotion) {
                profile_note << "- Promotion: REJECTED — candidate did not pass all gates.\n";
            } else {
                profile_note << "- Promotion: not requested; active profile unchanged.\n";
            }
        }
    }
    std::cout << "Engine-native stress results: " << dir.string() << '\n';
}

}  // namespace

int main(int argc, char** argv) {
    Options options = parse_args(argc, argv);
    try {
        options.session_dir = safe_session_directory(options);
    } catch (const std::exception& session_error) {
        std::cerr << "Native stress session error: " << session_error.what() << '\n';
        return 9;
    }
    if (options.stop_file.empty()) options.stop_file = options.session_dir / "STOP.request";
    if (options.heartbeat_file.empty()) options.heartbeat_file = options.session_dir / "WATCHDOG_HEARTBEAT.json";
    fs::remove(options.stop_file);
    reset_stage_journal(options);
    write_run_state(options, "starting", "INITIALIZING", 0U, 0U);
    SDL_SetAppMetadata("ALMOND SIGNAL: LIVE TAPE — Engine-Native Stress", "0.13.0-a9a3r1", "io.digimancer3d.almondsignal.stress");
    if (const auto hint = signalcloud::platform::sdl_driver_hint(options.backend)) {
        SDL_SetHint(SDL_HINT_VIDEO_DRIVER, std::string(*hint).c_str());
    }
    if (!SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS)) {
        std::cerr << "SDL initialization failed: " << SDL_GetError() << '\n';
        return 2;
    }
    SDL_Window* window = SDL_CreateWindow("ALMOND SIGNAL — ENGINE-NATIVE STRESS",
                                           options.width, options.height,
                                           SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY);
    if (window == nullptr) {
        std::cerr << SDL_GetError() << '\n';
        SDL_Quit();
        return 3;
    }
    SDL_GLContext context = nullptr;
    if (!create_context(window, context, 4, 3) && !create_context(window, context, 3, 3)) {
        std::cerr << SDL_GetError() << '\n';
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 4;
    }
    SDL_GL_MakeCurrent(window, context);
    SDL_GL_SetSwapInterval(0);
    signalcloud::render::GLApi gl;
    std::string error;
    if (!gl.load(&error)) {
        std::cerr << error << '\n';
        SDL_GL_DestroyContext(context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 5;
    }
    const char* driver = SDL_GetCurrentVideoDriver();
    const auto capability = signalcloud::platform::collect_capability_report(gl, driver ? driver : "unknown");

    const auto seed = signalcloud::world::mix_seed(0xA12D0A1ULL, {0, 0, 0}, 4);
    auto level = signalcloud::world::LiminalLevel::make_pivot11_scavenging(seed);
    const auto route = signalcloud::benchmark::NativeStressRoute::build(level);
    if (!route.valid()) {
        std::cerr << "Could not build engine-native stress route.\n";
        return 6;
    }

    signalcloud::benchmark::NativeStressRouteGuard route_guard;

    const std::uint32_t ceiling = std::max<std::uint32_t>(100'000U, options.max_points);
    auto stages = build_stages(options, ceiling);
    if (stages.empty()) {
        std::cerr << "No stages for mode " << options.mode << '\n';
        return 7;
    }

    signalcloud::platform::FirstPersonCamera camera;
    CameraAngleSmoother camera_angles;
    signalcloud::world::PlayerController player(level.spawn_position());
    signalcloud::combat::CombatSystem combat = signalcloud::combat::CombatSystem::make_pivot10();
    signalcloud::economy::EconomySystem economy = signalcloud::economy::EconomySystem::make_pivot12();
    std::vector<std::string> pcp3_warnings;
    const auto pcp3_assets = signalcloud::pcp3::discover_assets(options.root, &pcp3_warnings);
    for (const auto& warning : pcp3_warnings) {
        std::cerr << "PCP3 asset warning: " << warning << '\n';
    }
    signalcloud::pcp3::RuntimeInteractionState pcp3_interactions;
    signalcloud::pcp3::RuntimeEncounterState pcp3_encounters;
    signalcloud::ui::ArInterface ar;
    signalcloud::font::FontService stress_font_service;
    const auto stress_font_path = options.root / "content/core/fonts/terminal_00/Terminal_00.scfont";
    if (stress_font_service.load("core.fonts.terminal_00", stress_font_path) &&
        stress_font_service.set_default("core.fonts.terminal_00")) {
        ar.set_font(stress_font_service.default_font());
        const auto loaded_font = stress_font_service.default_font();
        std::cout << "Stress SCFONT runtime: "
                  << (loaded_font ? loaded_font->name : std::string("unknown"))
                  << " | glyphs " << (loaded_font ? loaded_font->glyphs.size() : 0U)
                  << " | generation "
                  << stress_font_service.generation(stress_font_service.default_font_id()) << '\n';
    } else {
        std::cerr << "Stress SCFONT warning: Terminal_00 could not be loaded; "
                     "legacy point alphabet remains active.\n";
        for (const auto& issue : stress_font_service.issues()) {
            std::cerr << "Stress SCFONT " << issue.font_id << ": " << issue.message << '\n';
        }
    }
    std::optional<signalcloud::ai::PlaybookRuntime> playbook_runtime;
    try {
        playbook_runtime = signalcloud::ai::PlaybookRuntime::load(
            options.root / "user_data/studio/playbook_runtime.scplayruntime");
        std::cout << "Stress universal-playbook budget: " << playbook_runtime->stats().point_budget_cost
                  << " | graphs " << playbook_runtime->stats().graph_count
                  << " | nodes " << playbook_runtime->stats().node_count
                  << " | edges " << playbook_runtime->stats().edge_count
                  << " | signature " << playbook_runtime->stats().signature << '\n';
    } catch (const std::exception& playbook_error) {
        std::cerr << "Stress playbook warning: " << playbook_error.what() << '\n';
    }
    std::vector<signalcloud::items::TupdRecipe> stress_tupd_recipes;
    for (const auto& path : signalcloud::items::discover_tupd_recipes(options.root)) {
        signalcloud::items::TupdRecipe recipe;
        std::string recipe_error;
        if (signalcloud::items::load_tupd_recipe(path, recipe, &recipe_error)) {
            stress_tupd_recipes.push_back(std::move(recipe));
            if (stress_tupd_recipes.size() >= 16U) break;
        }
    }
    std::vector<signalcloud::ui::ScuiPanel> stress_scui_panels;
    std::error_code scui_scan_error;
    const fs::path scui_root = options.root / "content";
    if (fs::is_directory(scui_root, scui_scan_error)) {
        for (const auto& entry : fs::recursive_directory_iterator(scui_root, scui_scan_error)) {
            if (scui_scan_error) break;
            if (!entry.is_regular_file(scui_scan_error) || entry.path().extension() != ".scui") continue;
            try {
                auto panel = signalcloud::ui::ScuiPanel::load(entry.path());
                if (panel.valid()) stress_scui_panels.push_back(std::move(panel));
                if (stress_scui_panels.size() >= 16U) break;
            } catch (...) {
            }
        }
    }
    signalcloud::render::SignalInterference interference;
    signalcloud::render::LocalSirenSource siren;
    signalcloud::render::WaterDisturbance water;
    signalcloud::render::SoundRipple ripple;
    signalcloud::render::PointRenderer renderer;
    signalcloud::lighting::IlluminosityRuntime illuminosity_runtime(
        options.root, options.root / "user_data/studio/illuminosity_runtime.udata");
    std::string illuminosity_error;
    if (!illuminosity_runtime.reload(&illuminosity_error)) {
        std::cerr << "Stress illuminosity warning: " << illuminosity_error
                  << " (neutral lighting telemetry will be used)\n";
    } else {
        illuminosity_runtime.set_budget_scale(static_cast<float>(options.light_budget_scale));
        std::cout << "Stress illuminosity budget: "
                  << illuminosity_runtime.stats().selected_point_budget_cost << "/"
                  << illuminosity_runtime.stats().effective_max_point_budget
                  << " | selected " << illuminosity_runtime.stats().budget_active_lights
                  << " | limited " << illuminosity_runtime.stats().budget_limited_lights
                  << " | scale " << options.light_budget_scale << " | source "
                  << illuminosity_runtime.stats().source_document << '\n';
    }
    signalcloud::materials::MaterialRuntime material_runtime(
        options.root, options.root / "user_data/studio/material_runtime.udata");
    std::string material_error;
    if (!material_runtime.reload(&material_error)) {
        std::cerr << "Stress material warning: " << material_error
                  << " (neutral material telemetry will be used)\n";
    } else {
        std::cout << "Stress material budget: "
                  << material_runtime.stats().selected_point_budget << "/"
                  << material_runtime.stats().max_point_budget
                  << " | selected " << material_runtime.stats().selected_materials
                  << " | graph " << material_runtime.stats().source_graph << '\n';
    }
    signalcloud::audio::AudioInterferenceRuntime audio_interference_runtime(
        options.root, options.root / "user_data/studio/audio_interference_runtime.udata");
    std::string audio_interference_error;
    if (!audio_interference_runtime.reload(&audio_interference_error)) {
        std::cerr << "Stress audio-interference warning: " << audio_interference_error
                  << " (safe built-in profile will be used)\n";
    } else {
        const auto& profile = audio_interference_runtime.hash_dog_bark();
        std::cout << "Stress audio-interference budget: "
                  << audio_interference_runtime.stats().point_budget_cost
                  << " | band " << signalcloud::render::frequency_band_name(profile.frequency_band)
                  << " | waves " << profile.wave_count
                  << " | source " << audio_interference_runtime.stats().source_profile << '\n';
    }
    const DeathFinaleSelection death_selection = select_death_finale(options.root);

    auto cloud = signalcloud::render::PointCloud::make_liminal_level(level, {stages.front().points, seed});
    if (!renderer.initialize(gl, cloud, &error)) {
        std::cerr << error << '\n';
        return 8;
    }

    double route_distance = 0.0;
    double runtime = 0.0;
    bool running = true;
    bool death_finale_completed = false;
    bool hard_abort = false;
    std::string completion_reason{"COMPLETED"};
    std::string previous_zone;
    std::vector<StageSummary> results;
    const double run_started = static_cast<double>(SDL_GetTicksNS()) / 1'000'000'000.0;
    reset_visibility_trace(options);
    reset_route_containment_trace(options);

    for (const auto& stage : stages) {
        if (!running) break;
        write_run_state(options, "running", "BENCHMARK_ACTIVE", results.size(), stages.size(), stage.label);
        write_watchdog_heartbeat(options, runtime, stage, 0.0, results.size(), stages.size(), "generating");
        route_guard.reset();
        StageSummary summary;
        summary.spec = stage;
        summary.route_distance_start = route_distance;
        summary.route_distance_end = route_distance;
        if (stage.kind == StageKind::death_finale) summary.death_cause = death_selection.label;

        const auto memory_decision = stage_memory_guard(options, stage.points);
        summary.memory_available_mib = memory_decision.available_mib;
        summary.memory_allowed_mib = memory_decision.allowed_allocation_mib;
        summary.memory_estimated_mib = memory_decision.estimated_allocation_mib;
        summary.memory_safe_point_limit = memory_decision.safe_point_limit;
        if (!memory_decision.allowed) {
            summary.guard_refused = true;
            summary.guard_reason = memory_decision.reason;
            summary.failure = memory_decision.reason;
            results.push_back(summary);
            append_stage_journal(options, results.back());
            write_watchdog_heartbeat(options, runtime, stage, 0.0, results.size(),
                                     stages.size(), "memory-guard-refused");
            continue;
        }

        const auto thermal_start = current_thermal_guard(options);
        apply_thermal_decision(summary, thermal_start, true, false);
        // A9a3r1 never refuses a stage from a single starting temperature sample.
        // The user-selected fail threshold can mark profile evidence while the campaign
        // continues, and the force-stop threshold must remain sustained for the chosen
        // hold period before the watchdog stops the child.
        double thermal_force_elapsed = 0.0;
        CpuTimes previous_cpu_times = read_linux_cpu_times();

        const auto generation_started = std::chrono::steady_clock::now();
        auto next_cloud = signalcloud::render::PointCloud::make_liminal_level(level, {stage.points, seed});
        if (!renderer.upload_cloud(next_cloud, &error)) {
            summary.failure = "POINT_UPLOAD_FAILED: " + error;
            results.push_back(summary);
            append_stage_journal(options, results.back());
            completion_reason = "POINT_UPLOAD_FAILED";
            running = false;
            break;
        }
        cloud = std::move(next_cloud);
        summary.generation_ms = std::chrono::duration<double, std::milli>(
            std::chrono::steady_clock::now() - generation_started).count();
        summary.resident_points = renderer.resident_count();

        if (stage.kind == StageKind::scare_finale) {
            interference.set_mode(signalcloud::render::SignalMode::night_flux);
            siren.set_active(true);
            const auto& profile = audio_interference_runtime.hash_dog_bark();
            ripple.trigger_event(
                level.spawn_position(), profile.strength, profile.frequency_band,
                profile.obstruction_path, profile.seed_salt ^ static_cast<std::uint32_t>(stage.points),
                profile.duration_seconds, profile.radius_scale, profile.wave_count,
                profile.wave_sharpness, profile.displacement_scale,
                profile.color_mix, profile.visibility_floor);
        } else {
            interference.set_mode(signalcloud::render::SignalMode::stable);
            siren.set_active(false);
        }

        std::vector<double> fps_samples;
        std::set<std::string> zones_seen;
        double stage_elapsed = 0.0;
        double previous = static_cast<double>(SDL_GetTicksNS()) / 1'000'000'000.0;
        double fps_accum = 0.0;
        int fps_frames = 0;
        float displayed_fps = 0.0F;
        signalcloud::render::RoomVisibilitySelection visibility;
        int full_map_recoveries = 0;
        std::size_t route_containment_corrections = 0U;
        std::size_t signal_void_entries = 0U;
        bool full_map_restore_active = false;
        int full_siren_pulses = 0;
        double last_workload_pulse = -1.0;
        bool night_active = stage.kind == StageKind::scare_finale;
        bool local_siren_active = stage.kind == StageKind::scare_finale;
        const double first_full_siren = stage.kind == StageKind::scare_finale
            ? std::max(options.scare_seconds * 0.55, options.scare_seconds - 15.0) : 0.0;
        const std::array<double, 3> full_siren_starts{{
            first_full_siren, first_full_siren + 5.0, first_full_siren + 10.0
        }};

        while (running && stage_elapsed < stage.seconds) {
            const double now = static_cast<double>(SDL_GetTicksNS()) / 1'000'000'000.0;
            const float dt = static_cast<float>(std::clamp(now - previous, 0.0, 0.1));
            previous = now;
            stage_elapsed += dt;
            runtime = now - run_started;
            SDL_Event event;
            while (SDL_PollEvent(&event)) {
                if (event.type == SDL_EVENT_QUIT) {
                    completion_reason = "WINDOW_CLOSE_CLEAN_STOP";
                    running = false;
                } else if (event.type == SDL_EVENT_KEY_DOWN && event.key.scancode == SDL_SCANCODE_ESCAPE) {
                    const bool shifted = (event.key.mod & SDL_KMOD_SHIFT) != 0;
                    hard_abort = shifted;
                    completion_reason = shifted ? "USER_HARD_ABORT" : "USER_CLEAN_STOP";
                    running = false;
                }
            }
            if (stop_file_requested(options)) {
                completion_reason = "USER_CLEAN_STOP_FILE";
                running = false;
            }
            if (!running) break;

            if (stage.kind != StageKind::death_finale) {
                float speed = options.presentation ? 2.65F : 5.0F;
                if (stage.kind == StageKind::scare_finale && signalcloud::world::zone_is_protected(previous_zone)) {
                    speed = std::max(speed, 4.5F);
                }
                route_distance += static_cast<double>(speed * dt);
            }
            const auto pose = route.pose_at(static_cast<float>(route_distance));
            player.teleport(pose.position);
            signalcloud::world::PlayerMoveInput idle;
            player.update(idle, signalcloud::math::normalize_or(pose.look_at - pose.position), dt, level);
            const Vec3 attempted_route_position = player.position();
            const auto containment = route_guard.stabilize(level, pose, attempted_route_position);
            if (containment.corrected) {
                player.teleport(containment.position);
                // Refresh ground/water state at the bounded position without
                // advancing movement or creating another threshold crossing.
                player.update(idle, signalcloud::math::normalize_or(
                    pose.look_at - containment.position), 0.0F, level);
                ++route_containment_corrections;
            }
            if (containment.entered_void) {
                ++signal_void_entries;
                append_route_containment_trace(options, runtime, stage, pose,
                                               attempted_route_position, containment,
                                               "ENTER_VOID_RECOVERED");
                std::cerr << "STRESS_ROUTE_CONTAINMENT_RECOVERY raw=\""
                          << containment.raw_zone << "\" expected=\"" << pose.zone
                          << "\" effective=\"" << containment.effective_zone
                          << "\" from=" << attempted_route_position.x << ','
                          << attempted_route_position.y << ',' << attempted_route_position.z
                          << " to=" << containment.position.x << ','
                          << containment.position.y << ',' << containment.position.z << '\n';
            } else if (containment.exited_void) {
                append_route_containment_trace(options, runtime, stage, pose,
                                               attempted_route_position, containment,
                                               "EXIT_VOID");
            } else if (pose.portal_jump) {
                append_route_containment_trace(options, runtime, stage, pose,
                                               attempted_route_position, containment,
                                               "PORTAL_HANDOFF");
            }
            camera.set_position(player.position());

            const Vec3 requested_forward = signalcloud::math::normalize_or(
                pose.look_at - player.position(), {0.0F, 0.0F, -1.0F});
            constexpr float pi = 3.14159265358979323846F;
            const float target_yaw = std::atan2(requested_forward.z, requested_forward.x) * 180.0F / pi;
            const float target_pitch = std::asin(std::clamp(requested_forward.y, -1.0F, 1.0F)) * 180.0F / pi;
            camera_angles.update(target_yaw, target_pitch, dt, options.presentation);
            camera.set_yaw_degrees(camera_angles.yaw);
            camera.set_pitch_degrees(camera_angles.pitch);

            std::string zone = containment.effective_zone;
            if (zone.empty() || zone == "Signal Void") zone = pose.zone;
            if (zone.empty() || zone == "Signal Void") zone = "Reception Tape";
            zones_seen.insert(zone);
            illuminosity_runtime.update(dt);
            const auto authored_light_frame = illuminosity_runtime.evaluate(player.position(), zone);
            renderer.set_illuminosity_frame(authored_light_frame);
            const auto authored_material_frame = material_runtime.evaluate(zone);
            renderer.set_material_frame(authored_material_frame);

            const int desired_entities = stage.kind == StageKind::scare_finale ? std::max(4, stage.entities) : stage.entities;
            const std::uint32_t workload_level = std::min<std::uint32_t>(stage.workload_level, 64U);
            if (stage.workload_axis == signalcloud::benchmark::WorkloadAxis::lights) {
                for (std::uint32_t i = 0; i < workload_level; ++i) {
                    const auto probe = illuminosity_runtime.evaluate(player.position(), zone);
                    summary.workload_operations += 1U + probe.active_lights;
                }
            } else if (stage.workload_axis == signalcloud::benchmark::WorkloadAxis::material_layers) {
                for (std::uint32_t i = 0; i < workload_level; ++i) {
                    const auto probe = material_runtime.evaluate(zone);
                    summary.workload_operations += 1U + probe.active_materials;
                }
            } else if (stage.workload_axis == signalcloud::benchmark::WorkloadAxis::playbook_evaluations &&
                       playbook_runtime && !playbook_runtime->graphs().empty()) {
                signalcloud::ai::PlaybookContext playbook_context;
                playbook_context.event = "stress_tick";
                playbook_context.true_conditions.insert("target_visible");
                const auto& graph = playbook_runtime->graphs().front();
                for (std::uint32_t i = 0; i < workload_level; ++i) {
                    summary.workload_operations += playbook_runtime->evaluate(graph.id, playbook_context).size();
                }
            } else if (stage.workload_axis == signalcloud::benchmark::WorkloadAxis::tupd_test_objects &&
                       !stress_tupd_recipes.empty()) {
                const auto inventory = signalcloud::items::make_tupd_test_inventory();
                for (std::uint32_t i = 0; i < workload_level; ++i) {
                    const auto& recipe = stress_tupd_recipes[static_cast<std::size_t>(i) % stress_tupd_recipes.size()];
                    const auto preview = signalcloud::items::preview_tupd(recipe, inventory);
                    summary.workload_operations += 1U + preview.added_interfaces.size() + preview.added_sockets.size();
                }
            } else if (stage.workload_axis == signalcloud::benchmark::WorkloadAxis::scui_panels &&
                       !stress_scui_panels.empty()) {
                for (std::uint32_t i = 0; i < workload_level; ++i) {
                    const auto& panel = stress_scui_panels[static_cast<std::size_t>(i) % stress_scui_panels.size()];
                    const auto layout = signalcloud::ui::ScuiNativeLayout::build(panel);
                    summary.workload_operations += 1U + layout.rows.size();
                }
            } else if (stage.workload_axis == signalcloud::benchmark::WorkloadAxis::sound_ripples &&
                       stage_elapsed - last_workload_pulse >= 0.5) {
                const auto& profile = audio_interference_runtime.hash_dog_bark();
                ripple.trigger_event(
                    player.position(), profile.strength, profile.frequency_band,
                    profile.obstruction_path, profile.seed_salt ^ static_cast<std::uint32_t>(summary.workload_operations),
                    profile.duration_seconds, profile.radius_scale,
                    std::clamp<std::uint32_t>(workload_level, 1U, 8U),
                    profile.wave_sharpness, profile.displacement_scale,
                    profile.color_mix, profile.visibility_floor);
                summary.workload_operations += workload_level;
                last_workload_pulse = stage_elapsed;
            } else if (stage.workload_axis == signalcloud::benchmark::WorkloadAxis::animated_actors) {
                summary.workload_operations += static_cast<std::uint64_t>(std::max(0, desired_entities));
            }

            const auto audio_event = ripple.event();
            renderer.set_audio_interference(audio_event);

            if (stage.kind == StageKind::scare_finale) {
                while (full_siren_pulses < 3 && stage_elapsed >= full_siren_starts[static_cast<std::size_t>(full_siren_pulses)]) {
                    interference.trigger_siren();
                    ++full_siren_pulses;
                    if (full_siren_pulses == 1) {
                        interference.set_mode(signalcloud::render::SignalMode::stable);
                        night_active = false;
                    }
                }
                if (full_siren_pulses >= 2 && stage_elapsed >= full_siren_starts[1] + 4.0) {
                    siren.set_active(false);
                    local_siren_active = false;
                }
            }

            if (zone != previous_zone) {
                if (!previous_zone.empty()) combat.despawn_world_entities(previous_zone);
                spawn_real_entities(combat, level, zone, player.position(), desired_entities);
                previous_zone = zone;
            }

            interference.update(dt, stage.points);
            economy.update(dt, stage.scanner);
            ar.update(dt);
            if (const auto* area = find_area(level, zone)) siren.update(dt, *area);
            water.update(dt);
            ripple.update(dt);
            const auto combat_update = combat.update(dt, player.position(), zone, &level);
            (void)combat_update;

            auto dynamic_points = combat.build_visual_points(static_cast<float>(now), zone);
            auto economy_points = economy.build_visual_points(static_cast<float>(now), zone, player.position());
            dynamic_points.insert(dynamic_points.end(), economy_points.begin(), economy_points.end());
            signalcloud::pcp3::RuntimeContext pcp3_context;
            pcp3_context.time_seconds = now;
            pcp3_context.scanner_active = stage.scanner;
            pcp3_context.debug_evidence = true;
            pcp3_context.interaction_pressed = stage.scanner && std::fmod(now, 4.0) < dt;
            pcp3_context.viewer_position = player.position();
            pcp3_context.interaction_state = &pcp3_interactions;
            pcp3_context.encounter_state = &pcp3_encounters;
            auto pcp3_points = signalcloud::pcp3::points_for_zone(
                pcp3_assets, zone, signalcloud::pcp3::PreviewPurpose::stress,
                pcp3_context, 500'000U);
            dynamic_points.insert(dynamic_points.end(), pcp3_points.begin(), pcp3_points.end());
            for (const auto& interaction_event : pcp3_interactions.take_events()) {
                if (!interaction_event.console_log) continue;
                std::cout << "PCP3 stress interaction: " << interaction_event.asset_id << " trigger "
                          << (interaction_event.trigger_index + 1U) << " -> " << interaction_event.action;
                if (!interaction_event.target.empty()) std::cout << " (" << interaction_event.target << ")";
                std::cout << '\n';
            }
            for (const auto& encounter_event : pcp3_encounters.take_events()) {
                if (!encounter_event.console_log) continue;
                std::cout << "PCP3 stress encounter: " << encounter_event.encounter_id << " -> " << encounter_event.kind;
                if (!encounter_event.referenced_asset_id.empty()) std::cout << " (" << encounter_event.referenced_asset_id << ")";
                if (encounter_event.kind == "reward_hook") {
                    std::cout << " [telemetry only: proofs " << encounter_event.reward_proofs
                              << ", XAR " << encounter_event.reward_xar << ", scrap " << encounter_event.reward_scrap << "]";
                }
                std::cout << '\n';
            }
            if (!renderer.upload_dynamic_points(dynamic_points, &error)) {
                running = false;
                summary.failure = error;
                break;
            }

            const auto camera_forward = camera.forward();
            Vec3 flat_forward{camera_forward.x, 0.0F, camera_forward.z};
            flat_forward = signalcloud::math::normalize_or(flat_forward, {0.0F, 0.0F, -1.0F});
            const Vec3 camera_right = signalcloud::math::normalize_or(
                signalcloud::math::cross(flat_forward, {0.0F, 1.0F, 0.0F}), {1.0F, 0.0F, 0.0F});
            signalcloud::combat::ViewmodelPose viewmodel_pose;
            viewmodel_pose.camera_position = camera.position();
            viewmodel_pose.forward = camera_forward;
            viewmodel_pose.right = camera_right;
            viewmodel_pose.movement_amount = stage.kind == StageKind::death_finale ? 0.0F : 0.55F;
            viewmodel_pose.sprinting = false;
            viewmodel_pose.crouched = pose.crouched;
            viewmodel_pose.swimming = player.water_state() == signalcloud::world::WaterState::swimming;
            viewmodel_pose.weapon_slot = 1;
            auto viewmodel_points = stage.kind == StageKind::death_finale
                ? std::vector<signalcloud::render::PointGpu>{}
                : combat.build_viewmodel_points(static_cast<float>(now), viewmodel_pose);

            signalcloud::ui::ArPose ar_pose{camera.position(), camera_forward, camera_right};
            signalcloud::ui::ArInterfaceData ar_data;
            ar_data.health_ratio = 1.0F;
            ar_data.oxygen_ratio = std::clamp(player.oxygen_ratio(), 0.0F, 1.0F);
            ar_data.sabs_ratio = economy.sabs_wetness_ratio();
            ar_data.carry_ratio = economy.encumbrance_ratio();
            ar_data.xar = economy.xar_balance();
            ar_data.magazine = combat.magazine();
            ar_data.reserve = combat.reserve_ammo();
            ar_data.weapon_slot = 1;
            ar_data.belt_slot = 1;
            ar_data.interaction_near = economy.interaction_target(player.position(), zone, 1.4F) !=
                                       signalcloud::economy::InteractionTarget::none;
            ar_data.safe_room = signalcloud::world::zone_is_protected(zone);
            ar_data.vending_menu = stage.kind != StageKind::death_finale &&
                                   zone == "Scavenger Exchange" && std::fmod(stage_elapsed, 12.0) > 7.0;
            ar_data.menu_product = 1 + static_cast<int>(stage_elapsed / 4.0) % 3;
            ar_data.menu_quantity = 1;
            ar_data.menu_unit_price = economy.menu_unit_price();
            ar_data.scanner_active = stage.scanner;
            ar_data.scanner_strength = economy.scanner_strength();
            if (stage.kind == StageKind::death_finale) {
                const float death_progress = std::clamp(static_cast<float>(stage_elapsed / stage.seconds), 0.0F, 1.0F);
                const float eased = death_progress * death_progress * (3.0F - 2.0F * death_progress);
                ar_data.health_ratio = std::max(0.0F, 1.0F - death_progress * 2.8F);
                ar_data.danger_kind = death_selection.danger;
                ar_data.recovery_active = true;
                ar_data.recovery_progress = eased;
                ar_data.blackout_strength = eased;
            }
            auto ar_points = ar.build_points(static_cast<float>(now), ar_pose, ar_data);
            viewmodel_points.insert(viewmodel_points.end(), ar_points.begin(), ar_points.end());
            if (!renderer.upload_viewmodel_points(viewmodel_points, &error)) {
                running = false;
                summary.failure = error;
                break;
            }

            float distance_limit = 46.0F;
            if (zone == "Long Signal Hall") distance_limit = 38.0F;
            if (zone == "Submerged Service Tunnel") distance_limit = 30.0F;
            if (zone == "Open Pressure Cavity") distance_limit = 34.0F;
            if (zone == "Submerged Boundary Lab") distance_limit = 32.0F;
            const auto local_light = level.strongest_light(player.position(), zone);
            distance_limit += local_light.influence * 18.0F;
            if (stage.scanner) distance_limit += 16.0F * economy.scanner_strength();
            if (options.progressive) {
                const double multiplier = progressive_multiplier(options.progressive_range);
                if (std::isfinite(multiplier)) distance_limit *= static_cast<float>(multiplier);
            }
            std::vector<signalcloud::render::PreviewRequest> previews;
            for (const auto& preview : level.connection_previews(zone, player.position())) {
                previews.push_back({std::string(preview.destination_zone), preview.center, preview.strength,
                                    preview.viewer_position, preview.normal, preview.half_width,
                                    preview.bottom_y, preview.top_y});
            }
            const bool full_map = !options.progressive || options.progressive_range == "full-map";
            if (full_map) {
                visibility = signalcloud::render::select_room_ranges(cloud, zone, stage.points, stage.points, true);
            } else {
                visibility = signalcloud::render::select_room_ranges(cloud, zone, stage.points, stage.points, false,
                                                                     player.position(), distance_limit, previews);
            }
            const auto& pool = signalcloud::render::system_point_budget_for_total(
                std::max<std::uint32_t>(4'000'000U, stage.points));
            if (full_map) {
                signalcloud::render::enforce_submitted_point_cap_balanced(
                    visibility, pool.submitted_soft_cap);
            } else {
                signalcloud::render::enforce_submitted_point_cap(
                    visibility, pool.submitted_soft_cap);
            }
            bool visibility_recovered = false;
            if (full_map) {
                visibility_recovered = signalcloud::render::restore_balanced_full_map_selection(
                    visibility, cloud, stage.points, stage.points,
                    pool.submitted_soft_cap);
            }
            renderer.set_draw_ranges(visibility.ranges);
            if (full_map && renderer.point_count() == 0U && !cloud.points().empty()) {
                // Rebuild only the balanced global selection. Never replace a
                // full-map run with a one-room fallback, even during a
                // transient threshold/Signal Void sample.
                visibility = signalcloud::render::select_room_ranges(
                    cloud, {}, stage.points, stage.points, true);
                signalcloud::render::enforce_submitted_point_cap_balanced(
                    visibility, pool.submitted_soft_cap);
                renderer.set_draw_ranges(visibility.ranges);
                visibility_recovered = true;
            }
            if (visibility_recovered) {
                if (!full_map_restore_active) {
                    ++full_map_recoveries;
                    std::cerr << "FULL_MAP_SUBMISSION_RESTORE zone=\"" << zone
                              << "\" selected=" << visibility.submitted_points
                              << " renderer=" << renderer.point_count() << '\n';
                }
                full_map_restore_active = true;
            } else {
                full_map_restore_active = false;
            }
            renderer.set_tactical_marker(player.position());

            int width = options.width;
            int height = options.height;
            SDL_GetWindowSizeInPixels(window, &width, &height);
            const float aspect = height > 0 ? static_cast<float>(width) / static_cast<float>(height) : 16.0F / 9.0F;
            renderer.render(camera.view_projection(aspect), static_cast<float>(now),
                            stage.kind == StageKind::scare_finale ? siren.intensity() : 0.0F,
                            stage.scanner, false, 1.0F, 1.0F, interference.level(),
                            siren.position(), siren.radius(), siren.intensity(),
                            water.position(), water.radius(), water.intensity(), water.bomb(),
                            local_light.position, local_light.radius, local_light.influence,
                            ripple.position(), ripple.radius(), ripple.intensity(),
                            combat.void_position(zone), combat.void_radius(zone), combat.void_strength(zone), width, height);
            SDL_GL_SwapWindow(window);

            fps_accum += dt;
            ++fps_frames;
            if (fps_accum >= 0.25) {
                displayed_fps = static_cast<float>(static_cast<double>(fps_frames) / fps_accum);
                fps_samples.push_back(displayed_fps);
                const double telemetry_window = fps_accum;
                const CpuTimes current_cpu_times = read_linux_cpu_times();
                summary.cpu_peak_percent = std::max(
                    summary.cpu_peak_percent, cpu_usage_percent(previous_cpu_times, current_cpu_times));
                previous_cpu_times = current_cpu_times;
                const double target_frame_ms = 1000.0 / static_cast<double>(std::max(1, options.target_fps));
                if (renderer.last_gpu_ms() > 0.0 && target_frame_ms > 0.0) {
                    const double gpu_budget_percent = std::clamp(
                        renderer.last_gpu_ms() / target_frame_ms * 100.0, 0.0, 999.0);
                    summary.gpu_frame_budget_peak_percent = std::max(
                        summary.gpu_frame_budget_peak_percent, gpu_budget_percent);
                }

                const auto thermal_now = current_thermal_guard(options);
                apply_thermal_decision(summary, thermal_now);
                if (thermal_now.abort_required) {
                    thermal_force_elapsed += telemetry_window;
                } else {
                    thermal_force_elapsed = 0.0;
                }
                summary.thermal_force_elapsed_seconds = std::max(
                    summary.thermal_force_elapsed_seconds, thermal_force_elapsed);
                const bool force_hold_reached = thermal_now.abort_required &&
                    (options.thermal_force_hold_seconds <= 0.0 ||
                     thermal_force_elapsed + 0.001 >= options.thermal_force_hold_seconds);
                if (force_hold_reached) {
                    summary.thermal_guard_triggered = true;
                    summary.guard_reason = "THERMAL_FORCE_STOP";
                    summary.failure = "THERMAL_FORCE_STOP";
                    completion_reason = "THERMAL_FORCE_STOP";
                    running = false;
                }
                fps_accum = 0.0;
                fps_frames = 0;
                std::string finale_phase;
                if (stage.kind == StageKind::scare_finale) {
                    finale_phase = night_active ? "NIGHT + LOCAL SIREN"
                        : (local_siren_active ? "FULL SIREN / LOCAL SIREN" : "FULL SIREN FINALE");
                } else if (stage.kind == StageKind::death_finale) {
                    finale_phase = "LIVE TAPE COLLAPSE — " + death_selection.label;
                }
                std::ostringstream title;
                title << std::fixed << std::setprecision(1)
                      << "ALMOND NATIVE STRESS | " << stage.mode << " | " << zone
                      << " | " << stage.points << " RES | " << renderer.point_count() << " DRAW"
                      << " | " << displayed_fps << " FPS | " << stage.label
                      << (stage.workload_axis != signalcloud::benchmark::WorkloadAxis::none
                          ? " | WORKLOAD " + std::string(signalcloud::benchmark::workload_axis_name(stage.workload_axis)) + " L" + std::to_string(stage.workload_level)
                          : std::string{})
                      << (summary.thermal_data_available
                          ? " | " + std::to_string(static_cast<int>(std::lround(summary.thermal_peak_celsius))) + "C"
                          : std::string{})
                      << (stage.scanner ? " | SCAN" : "")
                      << (night_active ? " | NIGHT" : "")
                      << (local_siren_active ? " | LOCAL SIREN" : "")
                      << (interference.siren_active() ? " | FULL SIREN" : "")
                      << (stage.kind == StageKind::death_finale ? " | " + death_selection.label : "")
                      << (route_containment_corrections > 0U ? " | ROUTE GUARD" : "")
                      << " | " << (options.progressive ? options.progressive_range : "FULL-MAP")
                      << " | ESC";
                SDL_SetWindowTitle(window, title.str().c_str());
                std::string live_alert;
                if (summary.thermal_state == "force-stop") {
                    live_alert = options.thermal_force_stop
                        ? "THERMAL FORCE-STOP COUNTDOWN"
                        : "THERMAL FORCE THRESHOLD OBSERVED";
                } else if (summary.thermal_state == "failed") {
                    live_alert = options.thermal_profile_fail
                        ? "THERMAL FAIL THRESHOLD — CAMPAIGN CONTINUES"
                        : "THERMAL FAIL THRESHOLD OBSERVED";
                } else if (summary.thermal_state == "warning") {
                    live_alert = "THERMAL ABOVE USER SAFE LIMIT";
                } else if (stage.workload_axis != signalcloud::benchmark::WorkloadAxis::none) {
                    live_alert = "WORKLOAD RAMP — " +
                        std::string(signalcloud::benchmark::workload_axis_name(stage.workload_axis)) +
                        " LEVEL " + std::to_string(stage.workload_level);
                } else if (stage.kind == StageKind::death_finale) {
                    live_alert = "LIVE TAPE COLLAPSE — " + death_selection.label;
                } else if (interference.siren_active()) {
                    live_alert = "FULL SIREN ACTIVE";
                } else if (local_siren_active && night_active) {
                    live_alert = "NIGHT FLUX + LOCAL SIREN";
                } else if (local_siren_active) {
                    live_alert = "LOCAL SIREN ACTIVE";
                } else if (stage.scanner) {
                    live_alert = "SCANNER RECONSTRUCTION ACTIVE";
                } else if (zone == "Scavenger Exchange") {
                    live_alert = "AR: XAR/EX · ALMOND · AMMO TABLET SIGNALS";
                } else if (level.water_at(player.position().x, player.position().z) != nullptr) {
                    live_alert = "WATER / PRESSURE FIELD ACTIVE";
                } else if (desired_entities > 0) {
                    live_alert = "THREAT SIGNALS ACTIVE: " + std::to_string(desired_entities);
                } else if (local_light.influence > 0.25F) {
                    live_alert = "LOCAL LIGHT FIELD ACTIVE";
                } else {
                    live_alert = "SIGNALCLOUD ROUTE ACTIVE";
                }
                const int floor_level = std::max(1, static_cast<int>(
                    std::floor((static_cast<double>(player.position().y) + 0.35) / 3.0)) + 1);
                write_live_status(options, runtime, stage, stage_elapsed, displayed_fps, route_distance,
                                  player.position(), floor_level, live_alert, zone, summary, visibility,
                                  renderer.point_count(), full_map_recoveries,
                                  containment.raw_zone, route_containment_corrections,
                                  signal_void_entries,
                                  desired_entities, stage.scanner, night_active, local_siren_active,
                                  full_siren_pulses,
                                  authored_light_frame.point_budget_cost,
                                  authored_light_frame.local_strength,
                                  authored_light_frame.global_strength,
                                  authored_material_frame.selected_point_budget,
                                  authored_material_frame.active_materials,
                                  ripple.serial(),
                                  audio_interference_runtime.stats().point_budget_cost,
                                  audio_interference_runtime.hash_dog_bark().wave_count,
                                  stage.kind == StageKind::death_finale ? death_selection.label : "",
                                  finale_phase);
                write_watchdog_heartbeat(options, runtime, stage, stage_elapsed, results.size(),
                                         stages.size(), "rendering");
                append_visibility_trace(options, runtime, stage, zone, full_map, visibility,
                                        renderer.point_count(), visibility_recovered);
            }
            summary.peak_submitted_points = std::max(summary.peak_submitted_points, visibility.submitted_points);
            summary.peak_renderer_submitted_points = std::max(
                summary.peak_renderer_submitted_points, renderer.point_count());
            summary.peak_submitted_rooms = std::max(summary.peak_submitted_rooms, visibility.submitted_rooms);
            summary.peak_preview_rooms = std::max(summary.peak_preview_rooms, visibility.preview_rooms);
            summary.peak_trimmed_points = std::max(summary.peak_trimmed_points, visibility.points_trimmed);
            summary.peak_gpu_ms = std::max(summary.peak_gpu_ms, renderer.last_gpu_ms());
            SDL_Delay(1);
        }

        const auto thermal_end = current_thermal_guard(options);
        apply_thermal_decision(summary, thermal_end, false, true);
        summary.elapsed = stage_elapsed;
        summary.fps = summarize_fps(fps_samples, options.target_fps, stage_elapsed);
        summary.zones_seen = zones_seen.size();
        summary.route_distance_end = route_distance;
        summary.full_siren_pulses = full_siren_pulses;
        summary.full_map_recoveries = full_map_recoveries;
        summary.route_containment_corrections = route_containment_corrections;
        summary.signal_void_entries = signal_void_entries;
        const double route_delta = summary.route_distance_end - summary.route_distance_start;
        if (summary.failure.empty() && summary.thermal_profile_failure) {
            summary.failure = "THERMAL_FAIL_THRESHOLD";
        }
        if (stage.kind == StageKind::scare_finale) {
            summary.passed = summary.failure.empty() && full_siren_pulses == 3 && stage_elapsed + 0.15 >= stage.seconds;
            if (!summary.passed && summary.failure.empty()) summary.failure = "SCARE_SEQUENCE_INCOMPLETE";
        } else if (stage.kind == StageKind::death_finale) {
            summary.passed = summary.failure.empty() && stage_elapsed + 0.15 >= stage.seconds;
            if (!summary.passed && summary.failure.empty()) summary.failure = "DEATH_OVERLAY_INCOMPLETE";
            death_finale_completed = summary.passed;
        } else {
            const double target_floor = static_cast<double>(options.target_fps) * 0.80;
            const bool movement_confirmed = summary.zones_seen >= 2U || route_delta >= 6.0;
            summary.passed = summary.failure.empty() && summary.fps.average >= target_floor && movement_confirmed;
            if (!summary.passed && summary.failure.empty()) {
                summary.failure = !movement_confirmed ? "ROUTE_DID_NOT_PROGRESS" : "FPS_BELOW_80_PERCENT_TARGET";
            }
        }
        results.push_back(summary);
        append_stage_journal(options, results.back());
        write_watchdog_heartbeat(options, runtime, stage, stage_elapsed, results.size(),
                                 stages.size(), "stage-complete");
    }

    const bool run_completed = running && results.size() == stages.size();
    if (!run_completed && completion_reason == "COMPLETED") completion_reason = "INCOMPLETE_STAGE_SEQUENCE";
    if (death_finale_completed) advance_death_finale(options.root, death_selection.next_index);
    write_results(options, results, route, capability,
                  driver ? std::string_view(driver) : std::string_view("unknown"),
                  illuminosity_runtime.stats(), material_runtime.stats(),
                  audio_interference_runtime.stats(), run_completed, completion_reason);
    write_run_state(options, run_completed ? "completed" : "interrupted", completion_reason,
                    results.size(), stages.size(), results.empty() ? std::string_view{} : results.back().spec.label);
    renderer.shutdown();
    SDL_GL_DestroyContext(context);
    SDL_DestroyWindow(window);
    SDL_Quit();
    if (run_completed) return 0;
    return hard_abort ? 11 : 10;
}
