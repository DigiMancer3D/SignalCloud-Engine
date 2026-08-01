#include "engine/render/signal_interference.hpp"

#include <algorithm>
#include <array>
#include <cmath>

namespace signalcloud::render {
namespace {
constexpr std::array<std::uint32_t, 7> tiers{{
    100'000U, 500'000U, 1'000'000U, 2'000'000U, 3'000'000U, 4'000'000U, 8'000'000U
}};

std::uint32_t lower_tier(std::uint32_t base) noexcept {
    std::uint32_t lower = tiers.front();
    for (const auto tier : tiers) {
        if (tier >= base) break;
        lower = tier;
    }
    return lower;
}
}

std::string_view signal_mode_name(SignalMode mode) noexcept {
    switch (mode) {
        case SignalMode::stable: return "STABLE";
        case SignalMode::night_flux: return "NIGHT FLUX";
        case SignalMode::chase_sway: return "CHASE SWAY";
    }
    return "UNKNOWN";
}

void SignalInterference::cycle_mode() noexcept {
    if (mode_ == SignalMode::stable) mode_ = SignalMode::night_flux;
    else if (mode_ == SignalMode::night_flux) mode_ = SignalMode::chase_sway;
    else mode_ = SignalMode::stable;
    phase_seconds_ = 0.0;
}

void SignalInterference::update(double dt_seconds, std::uint32_t base_points) noexcept {
    const double dt = std::clamp(dt_seconds, 0.0, 0.25);
    phase_seconds_ += dt;
    siren_seconds_ = std::max(0.0, siren_seconds_ - dt);
    const std::uint32_t safe_base = std::max<std::uint32_t>(100'000U, base_points);
    double target = static_cast<double>(safe_base);

    if (mode_ == SignalMode::night_flux) {
        const double high = static_cast<double>(std::min<std::uint32_t>(750'000U, safe_base));
        const double low = static_cast<double>(std::min<std::uint32_t>(100'000U, safe_base));
        const double wave = std::sin(phase_seconds_ * 0.72) * 0.5 + 0.5;
        target = low + (high - low) * wave;
    } else if (mode_ == SignalMode::chase_sway) {
        const double low = static_cast<double>(lower_tier(safe_base));
        const double wave = std::sin(phase_seconds_ * 1.35) * 0.5 + 0.5;
        target = low + (static_cast<double>(safe_base) - low) * wave;
    }

    if (siren_seconds_ > 0.0) {
        const double progress = 1.0 - siren_seconds_ / 4.0;
        const double recovery = 0.14 + 0.86 * std::clamp(progress, 0.0, 1.0);
        target *= recovery;
    }

    target = std::clamp(target, 10'000.0, static_cast<double>(safe_base));
    equivalent_points_ = static_cast<std::uint32_t>(std::llround(target));
    level_ = std::clamp(static_cast<float>(target / static_cast<double>(safe_base)), 0.01F, 1.0F);
}

}  // namespace signalcloud::render
