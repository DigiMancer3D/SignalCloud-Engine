#include "engine/world/liminal_level.hpp"
#include "engine/world/player_controller.hpp"
#include "engine/world/world_seed.hpp"

#include <cmath>
#include <filesystem>
#include <iostream>
#include <string>

namespace {
int failures = 0;

void check(bool condition, const std::string& message) {
    if (condition) {
        std::cout << "PASS: " << message << '\n';
    } else {
        std::cerr << "FAIL: " << message << '\n';
        ++failures;
    }
}
}

int main() {
    using namespace signalcloud;
    const auto seed = world::mix_seed(0xA11D0A1ULL, {0, 0, 0}, 4);
    const auto level = world::LiminalLevel::make_pivot5_traversal(seed);

    const auto* red = level.obstacle_at(648.0F, -162.5F);
    check(red != nullptr, "red mantle-limit block exists");
    if (red == nullptr) return 1;

    const math::Vec3 embedded_edge{red->min_x - 0.20F, 1.72F, -162.5F};
    const auto recovered = level.depenetrate_3d(embedded_edge, 1.72F, 0.48F, 0.0F);
    check(recovered.corrected, "analytical depenetration detects a capsule embedded in a platform edge");
    check(recovered.iterations > 0U, "depenetration records at least one recovery iteration");
    check(recovered.obstacle_name == red->name, "recovery identifies the obstacle that caused the overlap");
    check(level.can_occupy_3d(recovered.position.x, recovered.position.z, 0.0F, 1.72F, 0.48F, 0.0F),
          "recovered position is immediately occupiable");

    world::PlayerController edge_player(embedded_edge);
    world::PlayerMoveInput idle;
    edge_player.update(idle, {1.0F, 0.0F, 0.0F}, 1.0F / 60.0F, level);
    check(edge_player.depenetration_count() > 0U, "player controller performs automatic overlap recovery");
    check(level.can_occupy_3d(edge_player.position().x, edge_player.position().z,
                              edge_player.position().y - edge_player.eye_height(),
                              edge_player.eye_height(), edge_player.collision_radius(), 0.0F),
          "automatic recovery leaves the controller outside the red block");

    const float z_before_slide = edge_player.position().z;
    world::PlayerMoveInput slide;
    slide.right = 1.0F;
    for (int i = 0; i < 90; ++i) {
        edge_player.update(slide, {1.0F, 0.0F, 0.0F}, 1.0F / 60.0F, level);
    }
    check(std::abs(edge_player.position().z - z_before_slide) > 0.50F,
          "player can move along the platform edge after recovery");

    world::PlayerController falling_player(
        {red->min_x - 0.16F, red->height + 1.72F + 0.55F, -162.5F});
    for (int i = 0; i < 180; ++i) {
        falling_player.update(idle, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
    }
    check(falling_player.depenetration_count() > 0U,
          "barely missed falling landing triggers edge depenetration");
    check(level.can_occupy_3d(falling_player.position().x, falling_player.position().z,
                              falling_player.position().y - falling_player.eye_height(),
                              falling_player.eye_height(), falling_player.collision_radius(), 0.0F),
          "fall recovery does not leave the player embedded");

    world::PlayerController crouch_player(level.traversal_lab_spawn());
    crouch_player.update(idle, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
    world::PlayerMoveInput crouch;
    crouch.descend = true;
    crouch_player.update(crouch, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
    check(crouch_player.crouched(), "Left Ctrl becomes crouch while grounded");
    check(crouch_player.eye_height() < 1.30F, "crouch lowers the eye while preserving the feet position");
    crouch_player.update(idle, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
    check(!crouch_player.crouched() && crouch_player.eye_height() > 1.70F,
          "releasing Ctrl returns to standing height");


    world::PlayerController shallow_player({633.0F, 0.94F, -138.0F});
    for (int i = 0; i < 60; ++i) {
        shallow_player.update(idle, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
    }
    check(shallow_player.water_state() == world::WaterState::wading,
          "shallow pool remains a grounded wading state");
    shallow_player.update(crouch, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
    check(shallow_player.crouched() && shallow_player.water_state() == world::WaterState::wading,
          "Ctrl crouches in shallow water instead of misclassifying it as swimming");

    world::PlayerController normal_fall(level.traversal_lab_spawn());
    world::PlayerController dive_fall(level.traversal_lab_spawn());
    world::PlayerMoveInput jump;
    jump.jump_pressed = true;
    normal_fall.update(jump, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
    dive_fall.update(jump, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
    world::PlayerMoveInput air_dive;
    air_dive.descend = true;
    for (int i = 0; i < 20; ++i) {
        normal_fall.update(idle, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
        dive_fall.update(air_dive, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
    }
    check(dive_fall.vertical_velocity() < normal_fall.vertical_velocity(),
          "Left Ctrl accelerates downward while airborne");

    if (failures == 0) {
        std::cout << "All SignalCloud Pivot 5 a2 collision-recovery tests passed.\n";
        return 0;
    }
    return 1;
}
