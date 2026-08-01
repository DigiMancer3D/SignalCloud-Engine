#pragma once

#include "engine/math/vec.hpp"
#include "engine/world/liminal_level.hpp"

namespace signalcloud::render {

class LocalSirenSource {
public:
    void toggle() noexcept { active_ = !active_; phase_seconds_ = 0.0; pulse_seconds_ = 0.0; }
    void set_active(bool value) noexcept { active_ = value; }
    void update(double dt_seconds, const world::WalkArea& area) noexcept;

    [[nodiscard]] bool active() const noexcept { return active_; }
    [[nodiscard]] math::Vec3 position() const noexcept { return position_; }
    [[nodiscard]] float radius() const noexcept { return radius_; }
    [[nodiscard]] float intensity() const noexcept { return intensity_; }
    [[nodiscard]] float effect_at(math::Vec3 point) const noexcept;

private:
    bool active_{false};
    double phase_seconds_{0.0};
    double pulse_seconds_{0.0};
    math::Vec3 position_{};
    float radius_{8.5F};
    float intensity_{0.0F};
};

}  // namespace signalcloud::render
