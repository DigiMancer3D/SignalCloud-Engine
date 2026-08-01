#include "engine/render/adaptive_residency.hpp"

#include <algorithm>

namespace signalcloud::render {

void AdaptiveResidencyController::reset(std::uint32_t points) noexcept {
    current_points_ = points;
    low_fps_seconds_ = 0.0F;
    cooldown_seconds_ = 0.0F;
    fallback_pending_ = false;
    fallback_count_ = 0U;
}

void AdaptiveResidencyController::record_loaded(std::uint32_t points) noexcept {
    current_points_ = points;
    low_fps_seconds_ = 0.0F;
    cooldown_seconds_ = 45.0F;
    fallback_pending_ = false;
}

ResidencyDecision AdaptiveResidencyController::update(float dt_seconds, float fps,
                                                       double gpu_ms,
                                                       bool protected_room,
                                                       bool tactical_open) noexcept {
    const float dt = std::clamp(dt_seconds, 0.0F, 0.25F);
    cooldown_seconds_ = std::max(0.0F, cooldown_seconds_ - dt);
    if (tactical_open || current_points_ < 8'000'000U || fps <= 1.0F) {
        low_fps_seconds_ = std::max(0.0F, low_fps_seconds_ - dt * 0.5F);
        return {};
    }

    const bool overloaded = fps < 38.0F || (gpu_ms > 0.0 && gpu_ms > 24.5);
    if (overloaded) low_fps_seconds_ += dt;
    else low_fps_seconds_ = std::max(0.0F, low_fps_seconds_ - dt * 1.75F);

    if (low_fps_seconds_ >= 8.0F) fallback_pending_ = true;
    if (fallback_pending_ && protected_room && cooldown_seconds_ <= 0.0F) {
        fallback_pending_ = false;
        low_fps_seconds_ = 0.0F;
        ++fallback_count_;
        return {4'000'000U, "sustained frame pressure; deferred safe-room fallback"};
    }
    return {};
}

}  // namespace signalcloud::render
