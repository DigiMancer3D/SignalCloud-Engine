#include "engine/render/local_siren.hpp"

#include <algorithm>
#include <cmath>

namespace signalcloud::render {

void LocalSirenSource::update(double dt_seconds, const world::WalkArea& area) noexcept {
    const double dt = std::clamp(dt_seconds, 0.0, 0.25);
    phase_seconds_ += dt;
    const float cx = (area.min_x + area.max_x) * 0.5F;
    const float cz = (area.min_z + area.max_z) * 0.5F;
    const float orbit_x = std::max(1.2F, (area.max_x - area.min_x) * 0.28F);
    const float orbit_z = std::max(1.2F, (area.max_z - area.min_z) * 0.28F);
    position_ = {cx + std::cos(static_cast<float>(phase_seconds_) * 0.43F) * orbit_x,
                 1.45F,
                 cz + std::sin(static_cast<float>(phase_seconds_) * 0.37F) * orbit_z};

    if (!active_) {
        intensity_ = 0.0F;
        pulse_seconds_ = 0.0;
        return;
    }
    pulse_seconds_ += dt;
    if (pulse_seconds_ >= 3.2) pulse_seconds_ = 0.0;
    const double attack = std::clamp(pulse_seconds_ / 0.18, 0.0, 1.0);
    const double release = std::clamp((1.15 - pulse_seconds_) / 0.72, 0.0, 1.0);
    intensity_ = static_cast<float>(std::clamp(attack * release, 0.0, 1.0));
}

float LocalSirenSource::effect_at(math::Vec3 point) const noexcept {
    if (!active_ || intensity_ <= 0.0F) return 0.0F;
    const float dx = point.x - position_.x;
    const float dz = point.z - position_.z;
    const float distance = std::sqrt(dx * dx + dz * dz);
    const float radial = std::clamp(1.0F - distance / std::max(0.1F, radius_), 0.0F, 1.0F);
    return radial * radial * intensity_;
}

}  // namespace signalcloud::render
