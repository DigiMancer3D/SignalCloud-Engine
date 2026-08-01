#include "engine/lighting/illuminosity_runtime.hpp"
#include "engine/world/liminal_level.hpp"

#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string_view>

namespace {
int failures = 0;
void check(bool condition, std::string_view label) {
    std::cout << (condition ? "PASS: " : "FAIL: ") << label << '\n';
    if (!condition) ++failures;
}
}

int main() {
    namespace fs = std::filesystem;
    using namespace signalcloud;
    const fs::path root = fs::temp_directory_path() / "signalcloud_a4a1_illuminosity";
    fs::remove_all(root);
    fs::create_directories(root / "user_data/studio");
    const fs::path sidecar = root / "user_data/studio/illuminosity_runtime.udata";
    std::ofstream out(sidecar);
    out << "@udata 1\n\n[document]\n"
        << "schema_name: \"signalcloud.illuminosity-runtime\";\n"
        << "schema_major: 1;\n"
        << "source_document: \"content/core/lights/authoring_lab_default.slight\";\n"
        << "light_count: 1;\n"
        << "enabled_count: 1;\n"
        << "warning_count: 0;\n"
        << "point_budget_cost: 640;\n"
        << "used_fallback: false;\n\n"
        << "[day-night]\n"
        << "day_color: [1.0,0.95,0.85];\n"
        << "day_illuminosity_percent: 95.0;\n"
        << "night_color: [0.15,0.18,0.35];\n"
        << "night_illuminosity_percent: 18.0;\n"
        << "day_to_night_seconds: 45.0;\n"
        << "night_to_day_seconds: 60.0;\n"
        << "time_of_day: 0.35;\n"
        << "playing: false;\n"
        << "protected_global: true;\n\n"
        << "[light.0]\n"
        << "id: \"reception-authoring-key\";\n"
        << "name: \"Authoring Key Light\";\n"
        << "position: [0.0,4.6,3.8];\n"
        << "target: [0.0,1.2,0.8];\n"
        << "color: [1.0,0.62,0.24];\n"
        << "illuminosity_percent: 96.0;\n"
        << "aperture_distance: 2.5;\n"
        << "radius: 12.0;\n"
        << "cone_or_degree_burst: 96.0;\n"
        << "scope: \"room\";\n"
        << "zone: \"Reception Tape\";\n"
        << "enabled: true;\n"
        << "dynamic: false;\n"
        << "bounce_count_limit: 1;\n"
        << "bounce_cost: 0.34;\n"
        << "shadow_policy: \"analytic\";\n"
        << "day_night_binding: \"multiply\";\n"
        << "point_budget_cost: 640;\n"
        << "seed: 401;\n";
    out.close();

    lighting::IlluminosityRuntime runtime(root, sidecar);
    std::string error;
    check(runtime.reload(&error), "compiled Illuminosity sidecar loads without a JSON parser");
    check(runtime.stats().configured_lights == 1U && runtime.stats().enabled_lights == 1U,
          "shared runtime reports one enabled authored light");
    check(runtime.stats().point_budget_cost == 640U,
          "authored light point budget survives compilation");

    const auto level = world::LiminalLevel::make_pivot11_scavenging(0xA4A10001ULL);
    const auto reception = runtime.evaluate(level.spawn_position(), "Reception Tape");
    check(reception.local_enabled && reception.local_strength > 0.35F,
          "room-scoped authored light affects the real Reception Tape spawn");
    check(reception.local_color.x > reception.local_color.z * 2.5F,
          "authored amber color reaches the native renderer frame");
    const auto elsewhere = runtime.evaluate({0.0F, 1.72F, -10.0F}, "North Hall");
    check(!elsewhere.local_enabled,
          "room scope does not leak its local light into another zone");

    const float day_strength = reception.global_strength;
    runtime.set_time_of_day(0.0F);
    const auto night = runtime.evaluate(level.spawn_position(), "Reception Tape");
    check(night.global_strength < day_strength && night.global_color.z > night.global_color.x,
          "day/night blend changes native global intensity and hue deterministically");

    const auto rays_a = runtime.diagnostic_rays(level);
    const auto rays_b = runtime.diagnostic_rays(level);
    check(rays_a.size() == 8U && rays_b.size() == 8U,
          "bounded Signal Ray diagnostics emit exactly eight sub-rays");
    bool deterministic = true;
    for (std::size_t index = 0U; index < rays_a.size(); ++index) {
        deterministic = deterministic &&
            std::abs(rays_a[index].end.x - rays_b[index].end.x) < 0.0001F &&
            std::abs(rays_a[index].end.z - rays_b[index].end.z) < 0.0001F &&
            rays_a[index].bounce_count <= 1U;
    }
    check(deterministic, "Signal Ray results and bounce bounds are deterministic");

    runtime.apply_authoring_override("global", 110.0F, 15.0F, 110.0F, 8.0F, 0.0F);
    const auto overridden = runtime.evaluate(level.spawn_position(), "Reception Tape");
    check(!overridden.local_enabled && overridden.global_strength > night.global_strength,
          "native Light Lab override can promote the first authored light to global scope");

    fs::remove_all(root);
    return failures == 0 ? 0 : 1;
}
