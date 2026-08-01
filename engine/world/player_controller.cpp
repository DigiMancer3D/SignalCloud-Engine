#include "engine/world/player_controller.hpp"

#include <algorithm>
#include <cmath>

namespace signalcloud::world {

std::string_view water_state_name(WaterState state) noexcept {
    switch (state) {
        case WaterState::dry: return "DRY";
        case WaterState::wading: return "WADING";
        case WaterState::swimming: return "SWIMMING";
    }
    return "UNKNOWN";
}

std::string_view jump_kind_name(JumpKind kind) noexcept {
    switch (kind) {
        case JumpKind::none: return "NONE";
        case JumpKind::normal: return "NORMAL";
        case JumpKind::save: return "SAVE";
    }
    return "UNKNOWN";
}


std::string_view damage_cause_name(DamageCause cause) noexcept {
    switch (cause) {
        case DamageCause::none: return "NONE";
        case DamageCause::combat: return "COMBAT";
        case DamageCause::drowning: return "DROWNING";
        case DamageCause::pressure: return "PRESSURE";
        case DamageCause::fall: return "FALL";
        case DamageCause::poison: return "POISON";
        case DamageCause::treason: return "TREASON";
    }
    return "UNKNOWN";
}

void PlayerController::reset(math::Vec3 spawn) noexcept {
    position_ = spawn;
    vertical_velocity_ = 0.0F;
    eye_height_ = standing_eye_height_;
    grounded_ = true;
    crouched_ = false;
    water_state_ = WaterState::dry;
    immersion_ = 0.0F;
    ground_height_ = 0.0F;
    surface_name_ = "Liminal Floor";
    depenetration_count_ = 0;
    last_recovery_surface_ = {};
    coyote_time_remaining_ = 0.0F;
    save_boost_remaining_ = 0.0F;
    last_jump_kind_ = JumpKind::none;
    save_jump_airborne_ = false;
    save_jump_count_ = 0;
    oxygen_seconds_ = maximum_oxygen_seconds_;
    health_ = 100.0F;
    water_depth_ = 0.0F;
    pressure_damage_per_second_ = 0.0F;
    water_viscosity_ = 1.0F;
    has_almond_depth_tech_ = false;
    tech_pickup_count_ = 0;
    rescue_count_ = 0;
    water_entry_serial_ = 0;
    bomb_entry_count_ = 0;
    last_water_entry_was_bomb_ = false;
    last_water_entry_strength_ = 0.0F;
    last_water_entry_position_ = {};
    evade_remaining_ = 0.0F;
    evade_cooldown_ = 0.0F;
    combat_invulnerability_ = 0.0F;
    evade_count_ = 0;
    combat_death_count_ = 0;
    last_damage_cause_ = DamageCause::none;
    last_damage_amount_ = 0.0F;
    fall_damage_count_ = 0;
}

void PlayerController::apply_damage(float amount, DamageCause cause) noexcept {
    if (amount <= 0.0F || combat_invulnerability_ > 0.0F || health_ <= 0.0F) return;
    const float before = health_;
    health_ = std::max(0.0F, health_ - amount);
    last_damage_amount_ = before - health_;
    if (last_damage_amount_ > 0.0F) last_damage_cause_ = cause;
}

void PlayerController::restore_health(float amount) noexcept {
    if (amount <= 0.0F) return;
    health_ = std::min(100.0F, health_ + amount);
}

void PlayerController::restore_oxygen(float seconds) noexcept {
    if (seconds <= 0.0F) return;
    oxygen_seconds_ = std::min(maximum_oxygen_seconds_, oxygen_seconds_ + seconds);
}

void PlayerController::combat_respawn(math::Vec3 destination) noexcept {
    teleport(destination);
    health_ = 100.0F;
    oxygen_seconds_ = maximum_oxygen_seconds_;
    pressure_damage_per_second_ = 0.0F;
    combat_invulnerability_ = 1.0F;
    ++combat_death_count_;
    last_damage_amount_ = 0.0F;
}

void PlayerController::teleport(math::Vec3 destination) noexcept {
    position_ = destination;
    vertical_velocity_ = 0.0F;
    eye_height_ = standing_eye_height_;
    grounded_ = true;
    crouched_ = false;
    water_state_ = WaterState::dry;
    immersion_ = 0.0F;
    water_depth_ = 0.0F;
    pressure_damage_per_second_ = 0.0F;
    water_viscosity_ = 1.0F;
    coyote_time_remaining_ = 0.0F;
    save_boost_remaining_ = 0.0F;
    last_jump_kind_ = JumpKind::none;
    save_jump_airborne_ = false;
    evade_remaining_ = 0.0F;
    evade_cooldown_ = 0.0F;
    combat_invulnerability_ = 0.0F;
}

void PlayerController::rescue_to(math::Vec3 destination) noexcept {
    position_ = destination;
    vertical_velocity_ = 0.0F;
    eye_height_ = standing_eye_height_;
    grounded_ = true;
    crouched_ = false;
    water_state_ = WaterState::dry;
    immersion_ = 0.0F;
    water_depth_ = 0.0F;
    pressure_damage_per_second_ = 0.0F;
    water_viscosity_ = 1.0F;
    coyote_time_remaining_ = 0.0F;
    save_boost_remaining_ = 0.0F;
    save_jump_airborne_ = false;
    oxygen_seconds_ = maximum_oxygen_seconds_;
    health_ = 100.0F;
    ++rescue_count_;
}

void PlayerController::set_eye_height(float target_height) noexcept {
    if (std::abs(target_height - eye_height_) < 0.0001F) return;
    const float feet_y = position_.y - eye_height_;
    eye_height_ = target_height;
    position_.y = feet_y + eye_height_;
}

void PlayerController::apply_depenetration(const LiminalLevel& level, float step_allowance) noexcept {
    const auto result = level.depenetrate_3d(position_, eye_height_, collision_radius_, step_allowance);
    if (!result.corrected) return;
    position_.x = result.position.x;
    position_.z = result.position.z;
    depenetration_count_ += result.iterations;
    last_recovery_surface_ = result.obstacle_name;
}

void PlayerController::refresh_water_state(const LiminalLevel& level) noexcept {
    const WaterRegion* water = level.water_at(position_.x, position_.z);
    const float feet = position_.y - eye_height_;
    immersion_ = water == nullptr ? 0.0F :
        std::clamp((water->surface_y - feet) / eye_height_, 0.0F, 1.0F);
    const bool deep_water = water != nullptr && (water->surface_y - water->bottom_y) > 1.35F;
    water_state_ = deep_water && immersion_ > 0.72F ? WaterState::swimming :
        (immersion_ > 0.06F ? WaterState::wading : WaterState::dry);
    water_depth_ = water == nullptr ? 0.0F : std::max(0.0F, water->surface_y - position_.y);
    water_viscosity_ = water == nullptr ? 1.0F : std::max(0.35F, water->viscosity);
}

void PlayerController::update(const PlayerMoveInput& input, math::Vec3 camera_forward,
                              float dt_seconds, const LiminalLevel& level) noexcept {
    const float dt = std::clamp(dt_seconds, 0.0F, 0.05F);
    evade_cooldown_ = std::max(0.0F, evade_cooldown_ - dt);
    combat_invulnerability_ = std::max(0.0F, combat_invulnerability_ - dt);
    const bool was_wet = water_state_ != WaterState::dry;

    refresh_water_state(level);
    const bool wants_crouch = input.descend && grounded_ && water_state_ != WaterState::swimming;
    crouched_ = wants_crouch;
    set_eye_height(crouched_ ? crouched_eye_height_ : standing_eye_height_);
    apply_depenetration(level, grounded_ ? step_height_ : 0.0F);

    const math::Vec3 view_forward = math::normalize_or(camera_forward, {0.0F, 0.0F, -1.0F});
    camera_forward.y = 0.0F;
    const math::Vec3 forward = math::normalize_or(camera_forward, {0.0F, 0.0F, -1.0F});
    const math::Vec3 right = math::normalize_or(
        math::cross(forward, {0.0F, 1.0F, 0.0F}), {1.0F, 0.0F, 0.0F});
    math::Vec3 wish = forward * input.forward + right * input.right;
    const float wish_length = math::length(wish);
    if (wish_length > 1.0F) wish = wish / wish_length;

    float speed = (input.sprint ? 6.3F : 3.7F) * std::clamp(input.speed_scale, 0.35F, 1.25F);
    if (crouched_) speed *= 0.52F;
    if (water_state_ == WaterState::wading) speed *= 0.68F / std::sqrt(water_viscosity_);
    if (water_state_ == WaterState::swimming) speed *= 0.48F / water_viscosity_;

    if (input.quick_action_pressed && evade_cooldown_ <= 0.0F && water_state_ != WaterState::swimming) {
        evade_direction_ = math::normalize_or(wish_length > 0.05F ? wish : forward * -1.0F,
                                               forward * -1.0F);
        evade_remaining_ = evade_duration_;
        evade_cooldown_ = 0.72F;
        combat_invulnerability_ = 0.30F;
        ++evade_count_;
    }

    math::Vec3 horizontal_velocity = wish * speed;
    if (evade_remaining_ > 0.0F) {
        const float envelope = std::clamp(evade_remaining_ / evade_duration_, 0.0F, 1.0F);
        horizontal_velocity += evade_direction_ * (evade_speed_ * envelope);
        evade_remaining_ = std::max(0.0F, evade_remaining_ - dt);
    }
    // Ctrl while swimming is a view-directed dive. Even without W held, it
    // carries the swimmer toward the look vector while adding a guaranteed
    // downward component, avoiding the old circle-to-descend behavior.
    if (water_state_ == WaterState::swimming && input.descend) {
        math::Vec3 dive_horizontal{view_forward.x, 0.0F, view_forward.z};
        dive_horizontal = math::normalize_or(dive_horizontal, forward);
        horizontal_velocity += dive_horizontal * (1.35F / std::sqrt(water_viscosity_));
    }
    if (save_boost_remaining_ > 0.0F) {
        const float envelope = std::clamp(save_boost_remaining_ / save_boost_duration_, 0.0F, 1.0F);
        horizontal_velocity += save_boost_direction_ * (save_boost_speed_ * envelope);
        save_boost_remaining_ = std::max(0.0F, save_boost_remaining_ - dt);
    }
    const math::Vec3 delta = horizontal_velocity * dt;

    auto try_axis = [&](float desired_x, float desired_z) {
        const float current_feet = position_.y - eye_height_;
        if (!level.can_occupy_3d(desired_x, desired_z, current_feet, eye_height_,
                                 collision_radius_, grounded_ ? step_height_ : 0.0F)) {
            return false;
        }
        const float target_ground = level.ground_height_at(desired_x, desired_z);
        if (grounded_ && water_state_ == WaterState::dry &&
            target_ground > current_feet + step_height_ + 0.02F) {
            return false;
        }
        position_.x = desired_x;
        position_.z = desired_z;
        if (grounded_ && water_state_ == WaterState::dry && target_ground > current_feet) {
            position_.y = target_ground + eye_height_;
        }
        return true;
    };

    constexpr float kMaximumHorizontalSubstep = 0.11F;
    const float horizontal_distance = std::sqrt(delta.x * delta.x + delta.z * delta.z);
    const int substeps = std::max(1, static_cast<int>(
        std::ceil(horizontal_distance / kMaximumHorizontalSubstep)));
    const float step_x = delta.x / static_cast<float>(substeps);
    const float step_z = delta.z / static_cast<float>(substeps);
    for (int step = 0; step < substeps; ++step) {
        const float desired_x = position_.x + step_x;
        const float desired_z = position_.z + step_z;
        if (!try_axis(desired_x, desired_z)) {
            const bool moved_x = try_axis(desired_x, position_.z);
            const bool moved_z = try_axis(position_.x, desired_z);
            if (!moved_x && !moved_z) apply_depenetration(level, grounded_ ? step_height_ : 0.0F);
        }
    }

    refresh_water_state(level);
    ground_height_ = level.ground_height_at(position_.x, position_.z);
    surface_name_ = level.surface_name_at(position_.x, position_.z);

    // Detect leaving a ledge before resolving the jump key. This formalizes the
    // accidental 1-3 frame edge jump from Pivot 5 a2 as a short save-jump window.
    const float feet_after_move = position_.y - eye_height_;
    if (grounded_ && water_state_ == WaterState::dry &&
        feet_after_move > ground_height_ + 0.055F) {
        grounded_ = false;
        coyote_time_remaining_ = coyote_window_seconds_;
    }
    if (!grounded_) coyote_time_remaining_ = std::max(0.0F, coyote_time_remaining_ - dt);

    if (input.jump_pressed && water_state_ != WaterState::swimming) {
        if (grounded_) {
            if (crouched_) {
                crouched_ = false;
                set_eye_height(standing_eye_height_);
            }
            vertical_velocity_ = 6.70F;
            grounded_ = false;
            coyote_time_remaining_ = 0.0F;
            last_jump_kind_ = JumpKind::normal;
            save_jump_airborne_ = false;
        } else if (coyote_time_remaining_ > 0.0F) {
            vertical_velocity_ = std::max(vertical_velocity_, 6.45F);
            coyote_time_remaining_ = 0.0F;
            save_boost_remaining_ = save_boost_duration_;
            save_boost_direction_ = math::normalize_or(
                wish_length > 0.05F ? wish : forward, forward);
            last_jump_kind_ = JumpKind::save;
            save_jump_airborne_ = true;
            ++save_jump_count_;
        }
    }

    const WaterRegion* water = level.water_at(position_.x, position_.z);
    if (water_state_ == WaterState::swimming && water != nullptr) {
        crouched_ = false;
        set_eye_height(standing_eye_height_);
        grounded_ = false;
        const float float_eye = water->surface_y + 0.34F;
        const float buoyancy = std::clamp((float_eye - position_.y) * (5.4F / water_viscosity_),
                                          -3.2F, 4.2F);
        vertical_velocity_ += buoyancy * dt;
        vertical_velocity_ *= std::pow(std::clamp(0.18F + 0.10F / water_viscosity_, 0.12F, 0.34F), dt);
        if (input.jump_pressed) vertical_velocity_ = std::max(vertical_velocity_, 3.3F / water_viscosity_);
        if (input.descend) {
            const float look_dive = std::clamp(view_forward.y, -1.0F, 0.35F);
            const float desired_down = -2.2F + look_dive * 3.2F;
            vertical_velocity_ = std::min(vertical_velocity_, desired_down / std::sqrt(water_viscosity_));
        }
        position_.y += vertical_velocity_ * dt;
        const float minimum_eye = water->bottom_y + eye_height_;
        position_.y = std::max(position_.y, minimum_eye);

        // Water-exit mantle prototype: Space near a low platform pulls the
        // capsule onto its top rather than depenetrating sideways from below.
        if (input.jump_pressed) {
            if (const auto* platform = level.climbable_obstacle_near(
                    position_.x, position_.z, collision_radius_ + 0.95F,
                    water->surface_y + 1.15F)) {
                if (platform->height > water->surface_y + 0.10F) {
                    position_.x = std::clamp(position_.x,
                        platform->min_x + collision_radius_ * 0.55F,
                        platform->max_x - collision_radius_ * 0.55F);
                    position_.z = std::clamp(position_.z,
                        platform->min_z + collision_radius_ * 0.55F,
                        platform->max_z - collision_radius_ * 0.55F);
                    position_.y = platform->height + eye_height_;
                    vertical_velocity_ = 0.0F;
                    grounded_ = true;
                    surface_name_ = platform->name;
                }
            }
        }

        const float maximum_eye = water->surface_y + 1.25F;
        if (!grounded_ && position_.y > maximum_eye) {
            position_.y = maximum_eye;
            vertical_velocity_ = std::min(0.0F, vertical_velocity_);
        }
    } else {
        const float gravity = water_state_ == WaterState::wading ? 8.0F : 16.8F;
        vertical_velocity_ -= gravity * dt;
        if (input.descend && !grounded_) vertical_velocity_ -= 11.0F * dt;
        const float landing_velocity = vertical_velocity_;
        const bool was_airborne = !grounded_;
        position_.y += vertical_velocity_ * dt;

        ground_height_ = level.ground_height_at(position_.x, position_.z);
        const float floor_eye_y = ground_height_ + eye_height_;
        if (position_.y <= floor_eye_y) {
            position_.y = floor_eye_y;
            vertical_velocity_ = 0.0F;
            grounded_ = true;
            if (was_airborne && landing_velocity < -11.8F) {
                const float fall_damage = std::min(100.0F, (std::abs(landing_velocity) - 11.8F) * 5.4F);
                apply_damage(fall_damage, DamageCause::fall);
                if (fall_damage > 0.0F) ++fall_damage_count_;
            }
            coyote_time_remaining_ = 0.0F;
            save_boost_remaining_ = 0.0F;
            save_jump_airborne_ = false;
        }
    }

    apply_depenetration(level, grounded_ ? step_height_ : 0.0F);
    refresh_water_state(level);
    ground_height_ = level.ground_height_at(position_.x, position_.z);
    surface_name_ = level.surface_name_at(position_.x, position_.z);

    const bool is_wet = water_state_ != WaterState::dry;
    if (!was_wet && is_wet) {
        ++water_entry_serial_;
        last_water_entry_position_ = position_;
        last_water_entry_was_bomb_ = save_jump_airborne_;
        const float speed_strength = std::clamp(std::abs(vertical_velocity_) / 8.0F, 0.15F, 1.0F);
        last_water_entry_strength_ = std::clamp(
            speed_strength + (last_water_entry_was_bomb_ ? 0.45F : 0.0F), 0.20F, 1.0F);
        if (last_water_entry_was_bomb_) ++bomb_entry_count_;
        save_jump_airborne_ = false;
        save_boost_remaining_ = 0.0F;
    }

    water = level.water_at(position_.x, position_.z);
    water_depth_ = water == nullptr ? 0.0F : std::max(0.0F, water->surface_y - position_.y);
    pressure_damage_per_second_ = 0.0F;
    const bool head_submerged = water != nullptr && water_depth_ > 0.08F;
    if (head_submerged) {
        const float drain = water->oxygen_drain_scale * (has_almond_depth_tech_ ? 0.58F : 1.0F);
        oxygen_seconds_ = std::max(0.0F, oxygen_seconds_ - drain * dt);
    } else {
        oxygen_seconds_ = std::min(maximum_oxygen_seconds_, oxygen_seconds_ + 2.6F * dt);
    }
    if (oxygen_seconds_ <= 0.0F) apply_damage(14.0F * dt, DamageCause::drowning);

    if (water != nullptr && water->pressure_exposed) {
        const float safe_depth = has_almond_depth_tech_ ? 10.0F : 4.5F;
        const float excess = std::max(0.0F, water_depth_ - safe_depth);
        pressure_damage_per_second_ = excess * (has_almond_depth_tech_ ? 0.85F : 2.55F);
        apply_damage(pressure_damage_per_second_ * dt, DamageCause::pressure);
    }

    if (input.interact_pressed && level.near_almond_tech(position_)) {
        if (!has_almond_depth_tech_) ++tech_pickup_count_;
        has_almond_depth_tech_ = true;
        oxygen_seconds_ = maximum_oxygen_seconds_;
    }

    if (grounded_) {
        const float floor_eye_y = ground_height_ + eye_height_;
        if (position_.y < floor_eye_y) position_.y = floor_eye_y;
    }

    const float max_eye_y = level.ceiling_height() - 0.22F;
    if (position_.y > max_eye_y) {
        position_.y = max_eye_y;
        vertical_velocity_ = std::min(0.0F, vertical_velocity_);
    }

    health_ = std::clamp(health_, 0.0F, 100.0F);
}

}  // namespace signalcloud::world
