#pragma once

#include "engine/math/vec.hpp"
#include "engine/world/liminal_level.hpp"

#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

namespace signalcloud::benchmark {

enum class RouteTransition : unsigned char {
    continuous,
    portal_jump,
};

struct RouteWaypoint {
    math::Vec3 position{};
    std::string zone;
    std::string label;
    RouteTransition transition{RouteTransition::continuous};
    bool crouched{false};
};

struct RoutePose {
    math::Vec3 position{};
    math::Vec3 look_at{};
    std::string zone;
    std::string label;
    std::size_t segment_index{0};
    float segment_progress{0.0F};
    bool portal_jump{false};
    bool crouched{false};
};

struct RouteContainmentResult {
    math::Vec3 position{};
    std::string raw_zone;
    std::string effective_zone;
    bool corrected{false};
    bool entered_void{false};
    bool exited_void{false};
    bool portal_handoff{false};
    bool used_expected_zone{false};
    bool used_last_valid{false};
};

// Native stress is a deterministic presentation route, not a free-running
// gameplay controller.  A long frame or a threshold/depenetration edge must
// never leave its camera in the un-authored space between rooms.  This guard
// converts a transient "Signal Void" sample into one bounded handoff at the
// expected route room and remembers the last valid position as a final safety
// net.  It deliberately does not alter the level, portal graph, or point cloud.
class NativeStressRouteGuard {
public:
    [[nodiscard]] RouteContainmentResult stabilize(
        const world::LiminalLevel& level,
        const RoutePose& pose,
        math::Vec3 attempted_position);

    void reset() noexcept;

    [[nodiscard]] std::size_t correction_count() const noexcept { return correction_count_; }
    [[nodiscard]] std::size_t void_entry_count() const noexcept { return void_entry_count_; }
    [[nodiscard]] std::string_view last_valid_zone() const noexcept { return last_valid_zone_; }
    [[nodiscard]] math::Vec3 last_valid_position() const noexcept { return last_valid_position_; }

private:
    math::Vec3 last_valid_position_{};
    std::string last_valid_zone_;
    bool have_last_valid_{false};
    bool void_active_{false};
    std::size_t correction_count_{0};
    std::size_t void_entry_count_{0};
};

class NativeStressRoute {
public:
    static NativeStressRoute build(const world::LiminalLevel& level);

    [[nodiscard]] const std::vector<RouteWaypoint>& waypoints() const noexcept { return waypoints_; }
    [[nodiscard]] float length() const noexcept { return total_length_; }
    [[nodiscard]] std::size_t zone_count() const noexcept;
    [[nodiscard]] RoutePose pose_at(float distance) const noexcept;
    [[nodiscard]] bool valid() const noexcept { return waypoints_.size() >= 2U && total_length_ > 1.0F; }

private:
    std::vector<RouteWaypoint> waypoints_;
    std::vector<float> cumulative_;
    float total_length_{0.0F};
};

}  // namespace signalcloud::benchmark
