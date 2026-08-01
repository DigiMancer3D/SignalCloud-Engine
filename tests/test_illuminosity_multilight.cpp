#include "engine/lighting/illuminosity_runtime.hpp"
#include "engine/world/liminal_level.hpp"

#include <algorithm>
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

void write_light(std::ofstream& out, int index, std::string_view id,
                 std::string_view scope, float x, float y, float z,
                 float radius, float intensity, std::uint32_t cost,
                 std::uint32_t priority, std::uint32_t bounces) {
    out << "\n[light." << index << "]\n"
        << "id: \"" << id << "\";\n"
        << "name: \"" << id << "\";\n"
        << "position: [" << x << ',' << y << ',' << z << "];\n"
        << "target: [0.0,1.2,0.0];\n"
        << "color: [0.8,0.7,0.6];\n"
        << "illuminosity_percent: " << intensity << ";\n"
        << "aperture_distance: 2.5;\n"
        << "radius: " << radius << ";\n"
        << "cone_or_degree_burst: 90.0;\n"
        << "scope: \"" << scope << "\";\n"
        << "zone: \"Reception Tape\";\n"
        << "enabled: true;\n"
        << "dynamic: false;\n"
        << "bounce_count_limit: " << bounces << ";\n"
        << "bounce_cost: 0.35;\n"
        << "shadow_policy: \"analytic\";\n"
        << "day_night_binding: \"multiply\";\n"
        << "point_budget_cost: " << cost << ";\n"
        << "budget_priority: " << priority << ";\n"
        << "seed: " << (700 + index) << ";\n";
}
}  // namespace

int main() {
    namespace fs = std::filesystem;
    using namespace signalcloud;
    const fs::path root = fs::temp_directory_path() / "signalcloud_a4a2_multilight";
    fs::remove_all(root);
    fs::create_directories(root / "user_data/studio");
    const fs::path sidecar = root / "user_data/studio/illuminosity_runtime.udata";
    std::ofstream out(sidecar);
    out << "@udata 1\n\n[document]\n"
        << "schema_name: \"signalcloud.illuminosity-runtime\";\n"
        << "schema_major: 1;\n"
        << "source_document: \"content/core/lights/a4a2_test.slight\";\n"
        << "light_count: 5;\n"
        << "enabled_count: 5;\n"
        << "warning_count: 0;\n"
        << "point_budget_cost: 1250;\n"
        << "used_fallback: false;\n\n"
        << "[runtime-budget]\n"
        << "max_active_lights: 4;\n"
        << "max_point_budget: 950;\n"
        << "rays_per_light: 4;\n"
        << "max_diagnostic_rays: 12;\n"
        << "stress_scale: 1.0;\n\n"
        << "[day-night]\n"
        << "day_color: [1.0,0.95,0.85];\n"
        << "day_illuminosity_percent: 95.0;\n"
        << "night_color: [0.15,0.18,0.35];\n"
        << "night_illuminosity_percent: 18.0;\n"
        << "day_to_night_seconds: 45.0;\n"
        << "night_to_day_seconds: 60.0;\n"
        << "time_of_day: 0.35;\n"
        << "playing: false;\n"
        << "protected_global: true;\n";
    write_light(out, 0, "room-key", "room", 0.0F, 4.2F, 3.0F, 12.0F, 95.0F, 400U, 900U, 1U);
    write_light(out, 1, "local-console", "local", -1.5F, 2.2F, 0.5F, 8.0F, 65.0F, 250U, 800U, 1U);
    write_light(out, 2, "area-fill", "area", 2.0F, 3.0F, 0.0F, 8.0F, 48.0F, 200U, 700U, 2U);
    write_light(out, 3, "global-haze", "global", 0.0F, 8.0F, 0.0F, 80.0F, 22.0F, 100U, 600U, 0U);
    write_light(out, 4, "budget-overflow", "local", 0.0F, 2.0F, -1.0F, 6.0F, 80.0F, 300U, 100U, 1U);
    out.close();

    lighting::IlluminosityRuntime runtime(root, sidecar);
    std::string error;
    check(runtime.reload(&error), "A4a2 multi-light sidecar loads");
    check(runtime.stats().configured_lights == 5U && runtime.stats().enabled_lights == 5U,
          "all authored lights remain configured and enabled");
    check(runtime.stats().budget_active_lights == 4U && runtime.stats().budget_limited_lights == 1U,
          "priority budget deterministically selects four lights and limits one");
    check(runtime.stats().selected_point_budget_cost == 950U &&
          runtime.stats().effective_max_point_budget == 950U,
          "selected point cost exactly respects the authored runtime budget");

    const auto level = world::LiminalLevel::make_pivot11_scavenging(0xA4A20001ULL);
    const auto frame = runtime.evaluate(level.spawn_position(), "Reception Tape");
    check(frame.local_light_count == 3U && frame.contributing_lights == 4U,
          "room, local, area, and global scopes contribute in one bounded frame");
    check(frame.local_strength > frame.local_lights[0].strength,
          "multiple local contributions blend instead of replacing one another");
    check(frame.selected_point_budget_cost == 950U && frame.budget_limited_lights == 1U,
          "frame telemetry carries selected and limited light budgets");

    const auto rays = runtime.diagnostic_rays_all(level);
    check(rays.size() == 12U, "all-light diagnostics respect the global 12-ray cap");
    const bool bounded_bounces = std::all_of(rays.begin(), rays.end(), [](const auto& ray) {
        return ray.bounce_count <= 2U && ray.ray_index < 4U;
    });
    check(bounded_bounces, "expanded ray diagnostics preserve per-light ray and bounce bounds");

    runtime.set_budget_scale(0.50F);
    check(runtime.stats().effective_max_point_budget == 475U &&
          runtime.stats().budget_active_lights == 1U &&
          runtime.stats().budget_limited_lights == 4U,
          "stress budget scale can deterministically reduce active authored lights");
    const auto reduced = runtime.evaluate(level.spawn_position(), "Reception Tape");
    check(reduced.local_light_count == 1U && reduced.selected_point_budget_cost == 400U,
          "reduced stress budget immediately reaches the evaluated renderer frame");

    fs::remove_all(root);
    return failures == 0 ? 0 : 1;
}
