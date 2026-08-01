#include "engine/world/recovery_system.hpp"

#include "engine/combat/combat_system.hpp"
#include "engine/economy/economy_system.hpp"
#include "engine/world/liminal_level.hpp"

#include <algorithm>

namespace signalcloud::world {

std::string_view recovery_phase_name(RecoveryPhase phase) noexcept {
    switch (phase) {
        case RecoveryPhase::alive: return "ALIVE";
        case RecoveryPhase::blackout: return "BLACKOUT";
        case RecoveryPhase::stabilizing: return "STABILIZING";
    }
    return "UNKNOWN";
}

void RecoverySystem::reset() noexcept {
    phase_ = RecoveryPhase::alive;
    cause_ = DamageCause::none;
    death_zone_.clear();
    timer_ = 0.0F;
    phase_duration_ = 0.0F;
}

float RecoverySystem::progress() const noexcept {
    if (phase_duration_ <= 0.0F || phase_ == RecoveryPhase::alive) return 0.0F;
    return std::clamp(1.0F - timer_ / phase_duration_, 0.0F, 1.0F);
}

float RecoverySystem::blackout_strength() const noexcept {
    if (phase_ == RecoveryPhase::alive) return 0.0F;
    if (phase_ == RecoveryPhase::stabilizing) {
        return std::clamp(timer_ / std::max(0.001F, phase_duration_), 0.0F, 1.0F) * 0.84F;
    }
    return std::clamp(progress() / 0.14F, 0.0F, 1.0F);
}

RecoveryEvent RecoverySystem::update(float dt_seconds, PlayerController& player,
                                     const LiminalLevel& level,
                                     economy::EconomySystem& economy,
                                     combat::CombatSystem& combat,
                                     std::string_view active_zone) {
    RecoveryEvent event;
    const float dt = std::clamp(dt_seconds, 0.0F, 0.10F);

    if (phase_ == RecoveryPhase::alive && player.health() <= 0.0F) {
        phase_ = RecoveryPhase::blackout;
        cause_ = player.last_damage_cause();
        if (cause_ == DamageCause::none) cause_ = DamageCause::combat;
        death_zone_ = std::string(active_zone);
        phase_duration_ = 1.65F;
        timer_ = phase_duration_;
        const auto penalty = economy.apply_death_penalty();
        event.death_started = true;
        event.xar_lost = penalty.xar_lost;
        event.scrap_lost = penalty.scrap_lost;
        event.message = "Live tape collapsed; recovery handshake started";
        combat.on_player_recovery_started();
        return event;
    }

    if (phase_ == RecoveryPhase::alive) return event;
    timer_ = std::max(0.0F, timer_ - dt);
    if (phase_ == RecoveryPhase::blackout && timer_ <= 0.0F) {
        player.combat_respawn(level.spawn_position());
        combat.on_player_recovered();
        phase_ = RecoveryPhase::stabilizing;
        phase_duration_ = 0.85F;
        timer_ = phase_duration_;
        ++recovery_count_;
        event.respawned = true;
        event.message = "Live tape recovered at Reception Tape";
    } else if (phase_ == RecoveryPhase::stabilizing && timer_ <= 0.0F) {
        phase_ = RecoveryPhase::alive;
        cause_ = DamageCause::none;
        death_zone_.clear();
        phase_duration_ = 0.0F;
    }
    return event;
}

}  // namespace signalcloud::world
