#include "engine/lighting/illuminosity_bake.hpp"
#include "engine/lighting/illuminosity_runtime.hpp"

#include <cmath>
#include <filesystem>
#include <fstream>
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

void write_sidecar(const std::filesystem::path& path) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::trunc);
    out << "@udata 1\n\n"
        << "[document]\n"
        << "schema_name: \"signalcloud.illuminosity-runtime\";\n"
        << "schema_major: 1;\n"
        << "source_document: \"content/core/lights/a4a3_test.slight\";\n"
        << "light_count: 2;\n"
        << "enabled_count: 2;\n"
        << "warning_count: 0;\n"
        << "point_budget_cost: 384;\n"
        << "used_fallback: false;\n\n"
        << "[runtime-budget]\n"
        << "max_active_lights: 4;\n"
        << "max_point_budget: 1024;\n"
        << "rays_per_light: 4;\n"
        << "max_diagnostic_rays: 8;\n"
        << "stress_scale: 1.0;\n\n"
        << "[day-night]\n"
        << "day_color: [1.0,0.95,0.85];\n"
        << "day_illuminosity_percent: 95.0;\n"
        << "night_color: [0.15,0.18,0.35];\n"
        << "night_illuminosity_percent: 18.0;\n"
        << "day_to_night_seconds: 10.0;\n"
        << "night_to_day_seconds: 12.0;\n"
        << "time_of_day: 0.35;\n"
        << "playing: false;\n"
        << "paused: false;\n"
        << "protected_global: true;\n\n"
        << "[light.0]\n"
        << "id: \"room-key\";\n"
        << "name: \"Room Key\";\n"
        << "position: [0.0,3.0,0.0];\n"
        << "target: [0.0,1.0,0.0];\n"
        << "color: [1.0,0.5,0.2];\n"
        << "illuminosity_percent: 90.0;\n"
        << "aperture_distance: 2.5;\n"
        << "radius: 10.0;\n"
        << "cone_or_degree_burst: 90.0;\n"
        << "scope: \"room\";\n"
        << "zone: \"Reception Tape\";\n"
        << "enabled: true;\n"
        << "dynamic: true;\n"
        << "bounce_count_limit: 1;\n"
        << "bounce_cost: 0.34;\n"
        << "shadow_policy: \"analytic\";\n"
        << "day_night_binding: \"multiply\";\n"
        << "point_budget_cost: 256;\n"
        << "budget_priority: 900;\n"
        << "seed: 43;\n\n"
        << "[light.1]\n"
        << "id: \"global-fill\";\n"
        << "name: \"Global Fill\";\n"
        << "position: [0.0,8.0,0.0];\n"
        << "target: [0.0,0.0,0.0];\n"
        << "color: [0.3,0.4,1.0];\n"
        << "illuminosity_percent: 20.0;\n"
        << "aperture_distance: 0.0;\n"
        << "radius: 80.0;\n"
        << "cone_or_degree_burst: 360.0;\n"
        << "scope: \"global\";\n"
        << "zone: \"Reception Tape\";\n"
        << "enabled: true;\n"
        << "dynamic: false;\n"
        << "bounce_count_limit: 0;\n"
        << "bounce_cost: 0.0;\n"
        << "shadow_policy: \"none\";\n"
        << "day_night_binding: \"global\";\n"
        << "point_budget_cost: 128;\n"
        << "budget_priority: 500;\n"
        << "seed: 44;\n";
}

}  // namespace

int main() {
    const auto root = std::filesystem::temp_directory_path() / "signalcloud_a4a3_authoring_test";
    std::error_code ec;
    std::filesystem::remove_all(root, ec);
    std::filesystem::create_directories(root);
    const auto sidecar = root / "user_data/studio/illuminosity_runtime.udata";
    write_sidecar(sidecar);

    signalcloud::lighting::IlluminosityRuntime runtime(root, sidecar);
    std::string error;
    check(runtime.reload(&error), "runtime sidecar should load");
    const float initial = runtime.day_night().time_of_day;
    runtime.update(1.0F);
    check(std::abs(runtime.day_night().time_of_day - initial) < 0.00001F,
          "stopped timeline should not advance");
    runtime.play_day_night();
    runtime.update(1.0F);
    const float advanced = runtime.day_night().time_of_day;
    check(advanced > initial, "playing timeline should advance");
    runtime.pause_day_night();
    runtime.update(2.0F);
    check(std::abs(runtime.day_night().time_of_day - advanced) < 0.00001F,
          "paused timeline should not advance");
    runtime.stop_day_night(0.35F);
    check(!runtime.day_night().playing && !runtime.day_night().paused,
          "stopped timeline should clear play and pause state");
    check(std::abs(runtime.day_night().time_of_day - 0.35F) < 0.00001F,
          "stopped timeline should reset deterministically");

    const auto probe = runtime.probe_surface({0.0F, 1.5F, 0.0F}, "Reception Tape");
    check(probe.contributing_lights >= 2U, "surface probe should include room and global lights");
    check(probe.effective_illuminosity_percent > 45.0F,
          "surface probe should report readable light in the proof room");
    check(!probe.quality_band.empty(), "surface probe should classify quality");

    signalcloud::lighting::IlluminosityBakeRequest request;
    request.center = {0.0F, 1.5F, 0.0F};
    request.zone = "Reception Tape";
    request.grid_size = 5U;
    request.spacing = 1.0F;
    const auto first = signalcloud::lighting::bake_illuminosity_grid(runtime, request);
    const auto second = signalcloud::lighting::bake_illuminosity_grid(runtime, request);
    check(first.samples.size() == 25U, "five by five bake should contain 25 samples");
    check(first.deterministic_signature == second.deterministic_signature,
          "identical bake requests should have stable signatures");
    check(first.readable_samples > 0U, "proof-room bake should contain readable samples");

    const auto report = root / "reports/a4a3_bake.json";
    check(signalcloud::lighting::write_illuminosity_bake_report(root, report, runtime, first, &error),
          "bake report should write atomically inside project root");
    check(std::filesystem::is_regular_file(report), "bake report should exist");
    check(!signalcloud::lighting::write_illuminosity_bake_report(
              root, root.parent_path() / "outside-a4a3.json", runtime, first, &error),
          "bake report should reject project escape");

    std::filesystem::remove_all(root, ec);
    if (failures != 0) return 1;
    std::cout << "SignalCloud A4a3 Illuminosity authoring tests PASS\n";
    return 0;
}
