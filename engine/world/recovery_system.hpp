#pragma once

#include "engine/world/player_controller.hpp"

#include <cstdint>
#include <string>
#include <string_view>

namespace signalcloud::combat { class CombatSystem; }
namespace signalcloud::economy { class EconomySystem; }
namespace signalcloud::world { class LiminalLevel; }

namespace signalcloud::world {

enum class RecoveryPhase : std::uint8_t {
    alive,
    blackout,
    stabilizing,
};

struct RecoveryEvent {
    bool death_started{false};
    bool respawned{false};
    std::int64_t xar_lost{0};
    std::uint32_t scrap_lost{0};
    std::string message;
};

class RecoverySystem {
public:
    RecoveryEvent update(float dt_seconds, PlayerController& player,
                         const LiminalLevel& level,
                         economy::EconomySystem& economy,
                         combat::CombatSystem& combat,
                         std::string_view active_zone);
    void reset() noexcept;

    [[nodiscard]] RecoveryPhase phase() const noexcept { return phase_; }
    [[nodiscard]] bool controls_locked() const noexcept { return phase_ != RecoveryPhase::alive; }
    [[nodiscard]] float blackout_strength() const noexcept;
    [[nodiscard]] float progress() const noexcept;
    [[nodiscard]] DamageCause cause() const noexcept { return cause_; }
    [[nodiscard]] std::string_view death_zone() const noexcept { return death_zone_; }
    [[nodiscard]] std::uint32_t recovery_count() const noexcept { return recovery_count_; }

private:
    RecoveryPhase phase_{RecoveryPhase::alive};
    DamageCause cause_{DamageCause::none};
    std::string death_zone_;
    float timer_{0.0F};
    float phase_duration_{0.0F};
    std::uint32_t recovery_count_{0};
};

[[nodiscard]] std::string_view recovery_phase_name(RecoveryPhase phase) noexcept;

}  // namespace signalcloud::world
