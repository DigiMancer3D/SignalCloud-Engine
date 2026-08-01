#pragma once

#include "engine/math/vec.hpp"
#include "engine/world/liminal_level.hpp"

#include <cstdint>
#include <string_view>

namespace signalcloud::world {

struct PlayerMoveInput {
    float forward{0.0F};
    float right{0.0F};
    bool sprint{false};
    bool jump_pressed{false};
    bool descend{false};
    bool interact_pressed{false};
    bool quick_action_pressed{false};
    float speed_scale{1.0F};
};

enum class WaterState : unsigned char {
    dry,
    wading,
    swimming,
};

enum class JumpKind : unsigned char {
    none,
    normal,
    save,
};

enum class DamageCause : unsigned char {
    none,
    combat,
    drowning,
    pressure,
    fall,
    poison,
    treason,
};

[[nodiscard]] std::string_view water_state_name(WaterState state) noexcept;
[[nodiscard]] std::string_view jump_kind_name(JumpKind kind) noexcept;
[[nodiscard]] std::string_view damage_cause_name(DamageCause cause) noexcept;

class PlayerController {
public:
    explicit PlayerController(math::Vec3 spawn = {0.0F, 1.72F, 5.5F}) : position_(spawn) {}

    void reset(math::Vec3 spawn) noexcept;
    void teleport(math::Vec3 destination) noexcept;
    void update(const PlayerMoveInput& input, math::Vec3 camera_forward,
                float dt_seconds, const LiminalLevel& level) noexcept;
    void apply_damage(float amount, DamageCause cause = DamageCause::combat) noexcept;
    void restore_health(float amount) noexcept;
    void restore_oxygen(float seconds) noexcept;
    void combat_respawn(math::Vec3 destination) noexcept;

    [[nodiscard]] math::Vec3 position() const noexcept { return position_; }
    [[nodiscard]] float vertical_velocity() const noexcept { return vertical_velocity_; }
    [[nodiscard]] bool grounded() const noexcept { return grounded_; }
    [[nodiscard]] bool crouched() const noexcept { return crouched_; }
    [[nodiscard]] float collision_radius() const noexcept { return collision_radius_; }
    [[nodiscard]] float eye_height() const noexcept { return eye_height_; }
    [[nodiscard]] WaterState water_state() const noexcept { return water_state_; }
    [[nodiscard]] float immersion() const noexcept { return immersion_; }
    [[nodiscard]] float ground_height() const noexcept { return ground_height_; }
    [[nodiscard]] std::string_view surface_name() const noexcept { return surface_name_; }
    [[nodiscard]] std::uint32_t depenetration_count() const noexcept { return depenetration_count_; }
    [[nodiscard]] std::string_view last_recovery_surface() const noexcept { return last_recovery_surface_; }

    [[nodiscard]] JumpKind last_jump_kind() const noexcept { return last_jump_kind_; }
    [[nodiscard]] std::uint32_t save_jump_count() const noexcept { return save_jump_count_; }
    [[nodiscard]] float coyote_time_remaining() const noexcept { return coyote_time_remaining_; }
    [[nodiscard]] float health() const noexcept { return health_; }
    [[nodiscard]] float oxygen_seconds() const noexcept { return oxygen_seconds_; }
    [[nodiscard]] float oxygen_ratio() const noexcept { return oxygen_seconds_ / maximum_oxygen_seconds_; }
    [[nodiscard]] float water_depth() const noexcept { return water_depth_; }
    [[nodiscard]] float pressure_damage_per_second() const noexcept { return pressure_damage_per_second_; }
    [[nodiscard]] float water_viscosity() const noexcept { return water_viscosity_; }
    [[nodiscard]] bool has_almond_depth_tech() const noexcept { return has_almond_depth_tech_; }
    [[nodiscard]] std::uint32_t tech_pickup_count() const noexcept { return tech_pickup_count_; }
    [[nodiscard]] std::uint32_t rescue_count() const noexcept { return rescue_count_; }

    [[nodiscard]] std::uint32_t water_entry_serial() const noexcept { return water_entry_serial_; }
    [[nodiscard]] std::uint32_t bomb_entry_count() const noexcept { return bomb_entry_count_; }
    [[nodiscard]] bool last_water_entry_was_bomb() const noexcept { return last_water_entry_was_bomb_; }
    [[nodiscard]] float last_water_entry_strength() const noexcept { return last_water_entry_strength_; }
    [[nodiscard]] math::Vec3 last_water_entry_position() const noexcept { return last_water_entry_position_; }
    [[nodiscard]] bool combat_invulnerable() const noexcept { return combat_invulnerability_ > 0.0F; }
    [[nodiscard]] float evade_cooldown() const noexcept { return evade_cooldown_; }
    [[nodiscard]] std::uint32_t evade_count() const noexcept { return evade_count_; }
    [[nodiscard]] std::uint32_t combat_death_count() const noexcept { return combat_death_count_; }
    [[nodiscard]] DamageCause last_damage_cause() const noexcept { return last_damage_cause_; }
    [[nodiscard]] float last_damage_amount() const noexcept { return last_damage_amount_; }
    [[nodiscard]] std::uint32_t fall_damage_count() const noexcept { return fall_damage_count_; }

private:
    void apply_depenetration(const LiminalLevel& level, float step_allowance) noexcept;
    void set_eye_height(float target_height) noexcept;
    void refresh_water_state(const LiminalLevel& level) noexcept;
    void rescue_to(math::Vec3 destination) noexcept;

    math::Vec3 position_{};
    float vertical_velocity_{0.0F};
    float eye_height_{1.72F};
    float standing_eye_height_{1.72F};
    float crouched_eye_height_{1.18F};
    float collision_radius_{0.48F};
    float step_height_{0.60F};
    bool grounded_{true};
    bool crouched_{false};
    WaterState water_state_{WaterState::dry};
    float immersion_{0.0F};
    float ground_height_{0.0F};
    std::string_view surface_name_{"Liminal Floor"};
    std::uint32_t depenetration_count_{0};
    std::string_view last_recovery_surface_{};

    float coyote_time_remaining_{0.0F};
    float coyote_window_seconds_{0.085F};
    float save_boost_remaining_{0.0F};
    float save_boost_duration_{0.22F};
    float save_boost_speed_{2.45F};
    math::Vec3 save_boost_direction_{0.0F, 0.0F, -1.0F};
    JumpKind last_jump_kind_{JumpKind::none};
    bool save_jump_airborne_{false};
    std::uint32_t save_jump_count_{0};

    float maximum_oxygen_seconds_{42.0F};
    float oxygen_seconds_{42.0F};
    float health_{100.0F};
    float water_depth_{0.0F};
    float pressure_damage_per_second_{0.0F};
    float water_viscosity_{1.0F};
    bool has_almond_depth_tech_{false};
    std::uint32_t tech_pickup_count_{0};
    std::uint32_t rescue_count_{0};

    std::uint32_t water_entry_serial_{0};
    std::uint32_t bomb_entry_count_{0};
    bool last_water_entry_was_bomb_{false};
    float last_water_entry_strength_{0.0F};
    math::Vec3 last_water_entry_position_{};

    float evade_remaining_{0.0F};
    float evade_duration_{0.18F};
    float evade_speed_{7.8F};
    float evade_cooldown_{0.0F};
    float combat_invulnerability_{0.0F};
    math::Vec3 evade_direction_{0.0F, 0.0F, 1.0F};
    std::uint32_t evade_count_{0};
    std::uint32_t combat_death_count_{0};
    DamageCause last_damage_cause_{DamageCause::none};
    float last_damage_amount_{0.0F};
    std::uint32_t fall_damage_count_{0};
};

}  // namespace signalcloud::world
