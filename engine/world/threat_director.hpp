#pragma once

#include "engine/math/vec.hpp"

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace signalcloud::combat { class CombatSystem; enum class CreatureKind : std::uint8_t; }
namespace signalcloud::world { class LiminalLevel; }

namespace signalcloud::world {

struct ThreatDirectorStats {
    std::uint32_t world_spawns{0};
    std::uint32_t migrations{0};
    std::uint32_t threshold_queues{0};
    std::uint32_t threshold_failures{0};
    std::uint32_t retired_entities{0};
    std::uint32_t active_world_entities{0};
    std::uint32_t threatened_zones{0};
    float current_zone_pressure{0.0F};
};

struct ThreatDirectorEvent {
    bool spawned{false};
    bool migrated{false};
    bool pursuit_queued{false};
    bool pursuit_expired{false};
    bool retired{false};
    std::string message;
};

[[nodiscard]] bool zone_is_protected(std::string_view zone) noexcept;

class ThreatDirector {
public:
    static ThreatDirector make_pivot13(const LiminalLevel& level);

    void reset(const LiminalLevel& level);
    ThreatDirectorEvent update(float dt_seconds, const LiminalLevel& level,
                               combat::CombatSystem& combat,
                               math::Vec3 player_position,
                               std::string_view active_zone,
                               bool scanner_active);
    void on_player_recovered(combat::CombatSystem& combat,
                             std::string_view death_zone);

    [[nodiscard]] const ThreatDirectorStats& stats() const noexcept { return stats_; }
    [[nodiscard]] std::string_view current_zone() const noexcept { return current_zone_; }
    [[nodiscard]] float grace_remaining() const noexcept { return grace_remaining_; }
    [[nodiscard]] bool current_zone_protected() const noexcept {
        return zone_is_protected(current_zone_);
    }

private:
    struct ZoneState {
        std::string name;
        math::Vec3 center{};
        float half_x{5.0F};
        float half_z{5.0F};
        float pressure{0.35F};
        float spawn_cooldown{0.0F};
        float inactive_seconds{0.0F};
        std::uint32_t visits{0};
        std::uint32_t defeats{0};
    };

    [[nodiscard]] ZoneState* find_zone(std::string_view name) noexcept;
    [[nodiscard]] const ZoneState* find_zone(std::string_view name) const noexcept;
    [[nodiscard]] std::optional<math::Vec3> choose_spawn(
        const LiminalLevel& level, const ZoneState& zone,
        math::Vec3 player_position, combat::CreatureKind kind) const noexcept;
    [[nodiscard]] int desired_population(const ZoneState& zone) const noexcept;
    [[nodiscard]] bool zones_are_connected(const LiminalLevel& level,
                                           std::string_view a,
                                           std::string_view b) const noexcept;

    std::vector<ZoneState> zones_;
    std::string current_zone_;
    std::string previous_zone_;
    float grace_remaining_{0.0F};
    float global_spawn_cooldown_{0.0F};
    std::uint64_t transition_serial_{0};
    ThreatDirectorStats stats_{};
};

}  // namespace signalcloud::world
