#include "engine/render/water_disturbance.hpp"

#include <algorithm>

namespace signalcloud::render {

void WaterDisturbance::trigger(math::Vec3 position, float strength, bool bomb) noexcept {
    position_ = position;
    initial_strength_ = std::clamp(strength, 0.10F, 1.0F);
    bomb_ = bomb;
    duration_seconds_ = bomb ? 1.15F : 0.62F;
    remaining_seconds_ = duration_seconds_;
    ++serial_;
}

void WaterDisturbance::update(float dt_seconds) noexcept {
    remaining_seconds_ = std::max(0.0F, remaining_seconds_ - std::max(0.0F, dt_seconds));
}

float WaterDisturbance::radius() const noexcept {
    if (!active() || duration_seconds_ <= 0.0F) return 0.0F;
    const float progress = 1.0F - remaining_seconds_ / duration_seconds_;
    return (bomb_ ? 2.4F : 1.2F) + progress * (bomb_ ? 10.5F : 5.0F);
}

float WaterDisturbance::intensity() const noexcept {
    if (!active() || duration_seconds_ <= 0.0F) return 0.0F;
    const float remaining_ratio = remaining_seconds_ / duration_seconds_;
    return initial_strength_ * remaining_ratio;
}

}  // namespace signalcloud::render
