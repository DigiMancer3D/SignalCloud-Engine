#pragma once

#include "engine/math/vec.hpp"

#include <cstddef>
#include <string_view>
#include <vector>

namespace signalcloud::world {

class LiminalLevel;

struct ThreatNavigationRequest {
    math::Vec3 start{};
    math::Vec3 goal{};
    std::string_view zone{};
    float radius{1.0F};
    float body_height{1.30F};
    float step_height{0.60F};
    bool can_swim{true};
    float grid_spacing{0.90F};
    std::size_t maximum_expansions{8192U};
};

struct ThreatNavigationResult {
    std::vector<math::Vec3> waypoints;
    bool start_recovered{false};
    bool goal_recovered{false};
    bool reached_goal_cell{false};
    std::size_t expanded_nodes{0U};
};

[[nodiscard]] bool threat_position_is_valid(const LiminalLevel& level,
                                            math::Vec3 position,
                                            std::string_view zone,
                                            float radius,
                                            float body_height,
                                            float step_height,
                                            bool can_swim = true) noexcept;

[[nodiscard]] math::Vec3 nearest_valid_threat_position(const LiminalLevel& level,
                                                        math::Vec3 position,
                                                        std::string_view zone,
                                                        float radius,
                                                        float body_height,
                                                        float step_height,
                                                        bool can_swim = true) noexcept;

[[nodiscard]] bool threat_motion_line_clear(const LiminalLevel& level,
                                             math::Vec3 start,
                                             math::Vec3 end,
                                             std::string_view zone,
                                             float radius,
                                             float body_height,
                                             float step_height,
                                             bool can_swim = true) noexcept;

[[nodiscard]] bool threat_sensor_line_clear(const LiminalLevel& level,
                                             math::Vec3 start,
                                             math::Vec3 end,
                                             bool glass_is_transparent = true) noexcept;

[[nodiscard]] ThreatNavigationResult plan_threat_route(
    const LiminalLevel& level, const ThreatNavigationRequest& request);

}  // namespace signalcloud::world
