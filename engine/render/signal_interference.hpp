#pragma once

#include <cstdint>
#include <string_view>

namespace signalcloud::render {

enum class SignalMode : std::uint8_t {
    stable,
    night_flux,
    chase_sway,
};

[[nodiscard]] std::string_view signal_mode_name(SignalMode mode) noexcept;

class SignalInterference {
public:
    void cycle_mode() noexcept;
    void set_mode(SignalMode mode) noexcept { mode_ = mode; phase_seconds_ = 0.0; }
    void trigger_siren() noexcept { siren_seconds_ = 4.0; }
    void update(double dt_seconds, std::uint32_t base_points) noexcept;

    [[nodiscard]] SignalMode mode() const noexcept { return mode_; }
    [[nodiscard]] std::uint32_t equivalent_points() const noexcept { return equivalent_points_; }
    [[nodiscard]] float level() const noexcept { return level_; }
    [[nodiscard]] bool siren_active() const noexcept { return siren_seconds_ > 0.0; }

private:
    SignalMode mode_{SignalMode::stable};
    double phase_seconds_{0.0};
    double siren_seconds_{0.0};
    std::uint32_t equivalent_points_{100'000U};
    float level_{1.0F};
};

}  // namespace signalcloud::render
