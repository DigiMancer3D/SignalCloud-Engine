#include "engine/data/udata.hpp"
#include "engine/render/point_cloud.hpp"
#include "engine/render/room_visibility.hpp"
#include "engine/render/signal_interference.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/world_seed.hpp"

#include <filesystem>
#include <iostream>
#include <set>
#include <string>

namespace {
int failures = 0;
void check(bool condition, const std::string& message) {
    if (condition) std::cout << "PASS: " << message << '\n';
    else { std::cerr << "FAIL: " << message << '\n'; ++failures; }
}
}

int main(int argc, char** argv) {
    const std::filesystem::path root = argc > 1 ? argv[1] : std::filesystem::current_path();
    using namespace signalcloud;

    const auto seed = world::mix_seed(0xA11D0A1ULL, {0, 0, 0}, 4);
    const auto level = world::LiminalLevel::make_pivot3_procedural(seed, 12U);
    const auto cloud = render::PointCloud::make_liminal_level(level, {240'000U, seed});
    check(cloud.ranges().size() == level.areas().size(), "point cloud exposes one contiguous range per procedural room");
    std::size_t range_total = 0U;
    std::set<std::string> names;
    for (const auto& range : cloud.ranges()) {
        range_total += range.count;
        names.insert(range.zone);
        check(range.first + range.count <= cloud.points().size(), "room range remains inside the resident VBO");
    }
    check(range_total == cloud.points().size(), "room ranges cover every resident point exactly once");
    check(names.size() == level.areas().size(), "room range names are unique");

    const std::string active = level.areas().front().name;
    const auto normal = render::select_room_ranges(cloud, active, 240'000U, 240'000U, false);
    check(normal.submitted_rooms == 1U, "normal gameplay submits only the active room");
    check(normal.submitted_points > 0U && normal.submitted_points < normal.resident_points,
          "active-room submission is smaller than the full resident tape");
    const auto tactical = render::select_room_ranges(cloud, active, 240'000U, 240'000U, true);
    check(tactical.submitted_rooms == level.areas().size(), "tactical view can submit the complete graph");
    check(tactical.submitted_points == tactical.resident_points, "stable tactical view submits the full resident cloud");

    auto sequential_cap = tactical;
    render::enforce_submitted_point_cap(sequential_cap, 1'200U);
    check(sequential_cap.ranges.size() < tactical.ranges.size(),
          "legacy sequential cap demonstrates why later full-map rooms could disappear");

    auto balanced_cap = tactical;
    render::enforce_submitted_point_cap_balanced(balanced_cap, 1'200U);
    check(balanced_cap.submitted_points == 1'200U, "balanced full-map cap respects the exact point budget");
    check(balanced_cap.ranges.size() == tactical.ranges.size(),
          "balanced full-map cap preserves a representative range for every room");
    check(balanced_cap.balanced_cap_applied, "balanced full-map cap reports its distribution policy");
    bool every_range_visible = true;
    for (const auto& range : balanced_cap.ranges) every_range_visible = every_range_visible && range.count > 0U;
    check(every_range_visible, "balanced full-map cap never leaves a represented room with a zero draw count");

    const auto stress_level = world::LiminalLevel::make_pivot11_scavenging(seed);
    const auto stress_cloud = render::PointCloud::make_liminal_level(stress_level, {320'000U, seed});
    auto stress_full_map = render::select_room_ranges(
        stress_cloud, "Reception Tape", 320'000U, 320'000U, true);
    render::enforce_submitted_point_cap_balanced(stress_full_map, 130'000U);
    check(stress_full_map.ranges.size() == stress_cloud.ranges().size(),
          "balanced cap preserves every banded range in the real 26-room stress level");
    check(stress_full_map.submitted_rooms == stress_level.areas().size(),
          "balanced full-map telemetry retains all 26 stress rooms");
    check(render::full_map_selection_is_stable(stress_full_map, stress_cloud),
          "balanced 26-room selection is recognized as a stable global submission");

    auto invalid_void_fallback = render::select_room_ranges(
        stress_cloud, "Signal Void", 320'000U, 320'000U, false);
    render::enforce_submitted_point_cap(invalid_void_fallback, 130'000U);
    check(!render::full_map_selection_is_stable(invalid_void_fallback, stress_cloud),
          "one-room Signal Void fallback is rejected as an unstable full-map submission");
    const bool restored = render::restore_balanced_full_map_selection(
        invalid_void_fallback, stress_cloud, 320'000U, 320'000U, 130'000U);
    check(restored, "unstable Signal Void fallback is replaced by a balanced global submission");
    check(render::full_map_selection_is_stable(invalid_void_fallback, stress_cloud),
          "restored full-map selection represents every stress room");
    check(invalid_void_fallback.ranges.size() == stress_cloud.ranges().size(),
          "full-map restore never degrades into a one-room fallback");
    check(!render::restore_balanced_full_map_selection(
              invalid_void_fallback, stress_cloud, 320'000U, 320'000U, 130'000U),
          "stable full-map selection is not rebuilt every frame");

    const auto disrupted = render::select_room_ranges(cloud, active, 100'000U, 240'000U, false);
    check(disrupted.submitted_points < normal.submitted_points, "signal fill reduces active-room point submission");

    render::SignalInterference signal;
    signal.update(0.0, 2'000'000U);
    check(signal.equivalent_points() == 2'000'000U, "stable signal preserves the selected fill tier");
    signal.set_mode(render::SignalMode::night_flux);
    for (int i = 0; i < 600; ++i) signal.update(1.0 / 60.0, 2'000'000U);
    check(signal.equivalent_points() >= 100'000U && signal.equivalent_points() <= 750'000U,
          "night flux stays inside the requested 100K-750K equivalent range");
    signal.set_mode(render::SignalMode::chase_sway);
    for (int i = 0; i < 180; ++i) signal.update(1.0 / 60.0, 2'000'000U);
    check(signal.equivalent_points() >= 1'000'000U && signal.equivalent_points() <= 2'000'000U,
          "chase sway moves between the selected tier and the next lower tier");
    signal.set_mode(render::SignalMode::stable);
    signal.trigger_siren();
    signal.update(0.01, 2'000'000U);
    check(signal.equivalent_points() < 500'000U, "siren scatter immediately disrupts point fill");

    const auto renderer_config = data::UDataDocument::load(root / "config/renderer.udata");
    const auto stream_config = data::UDataDocument::load(root / "config/streaming.udata");
    check(!renderer_config.has_errors(), "Pivot 4 renderer config loads");
    check(!stream_config.has_errors(), "Pivot 4 streaming config loads");
    check(stream_config.value("body", "active_room_only").has_value(), "stream config declares active-room submission");
    check(stream_config.value("body", "night_fill_range").has_value(), "stream config declares night signal fill range");

    if (failures == 0) {
        std::cout << "All SignalCloud Pivot 4 Active Tape Stream tests passed.\n";
        return 0;
    }
    return 1;
}
