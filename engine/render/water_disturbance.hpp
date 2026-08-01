#pragma once

#include "engine/math/vec.hpp"

#include <cstdint>

namespace signalcloud::render {

class WaterDisturbance {
public:
    void trigger(math::Vec3 position, float strength, bool bomb) noexcept;
    void update(float dt_seconds) noexcept;

    [[nodiscard]] bool active() const noexcept { return remaining_seconds_ > 0.0F; }
    [[nodiscard]] math::Vec3 position() const noexcept { return position_; }
    [[nodiscard]] float radius() const noexcept;
    [[nodiscard]] float intensity() const noexcept;
    [[nodiscard]] bool bomb() const noexcept { return bomb_; }
    [[nodiscard]] std::uint32_t serial() const noexcept { return serial_; }

private:
    math::Vec3 position_{};
    float initial_strength_{0.0F};
    float duration_seconds_{0.0F};
    float remaining_seconds_{0.0F};
    bool bomb_{false};
    std::uint32_t serial_{0};
};

}  // namespace signalcloud::render
