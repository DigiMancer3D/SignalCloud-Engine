#pragma once

#include <cstdint>
#include <optional>
#include <string_view>

namespace signalcloud::render {

struct ResidencyDecision {
    std::optional<std::uint32_t> requested_points;
    std::string_view reason{};
};

class AdaptiveResidencyController {
public:
    explicit AdaptiveResidencyController(std::uint32_t current_points = 8'000'000U) noexcept
        : current_points_(current_points) {}

    ResidencyDecision update(float dt_seconds, float fps, double gpu_ms,
                             bool protected_room, bool tactical_open) noexcept;
    void record_loaded(std::uint32_t points) noexcept;
    void reset(std::uint32_t points) noexcept;

    [[nodiscard]] std::uint32_t current_points() const noexcept { return current_points_; }
    [[nodiscard]] float low_fps_seconds() const noexcept { return low_fps_seconds_; }
    [[nodiscard]] bool fallback_pending() const noexcept { return fallback_pending_; }
    [[nodiscard]] std::uint32_t fallback_count() const noexcept { return fallback_count_; }

private:
    std::uint32_t current_points_{8'000'000U};
    float low_fps_seconds_{0.0F};
    float cooldown_seconds_{0.0F};
    bool fallback_pending_{false};
    std::uint32_t fallback_count_{0};
};

}  // namespace signalcloud::render
