#include "engine/render/point_cloud.hpp"
#include "engine/render/room_visibility.hpp"
#include "engine/render/water_disturbance.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/player_controller.hpp"
#include "engine/world/world_seed.hpp"

#include <cmath>
#include <iostream>
#include <string>

namespace {
int failures = 0;
void check(bool condition, const std::string& message) {
    if (condition) std::cout << "PASS: " << message << '\n';
    else { std::cerr << "FAIL: " << message << '\n'; ++failures; }
}
}

int main() {
    using namespace signalcloud;
    const auto seed = world::mix_seed(0xA11D0A1ULL, {0, 0, 0}, 4);
    const auto level = world::LiminalLevel::make_pivot6_depth(seed);

    check(level.areas().size() == 20U, "Pivot 6 contains twenty procedural and laboratory room areas");
    check(level.water_regions().size() == 5U, "Pivot 6 contains five water regions");
    check(level.portals().size() >= 19U, "Pivot 6 retains the graph and adds complex access portals");
    check(level.has_almond_tech_station(), "underwater Almond technology station exists");

    const auto* shaft = level.water_at(800.0F, -164.0F);
    const auto* tunnel = level.water_at(840.0F, -164.0F);
    const auto* cavity = level.water_at(900.0F, -164.0F);
    check(shaft != nullptr && shaft->bottom_y <= -14.0F && shaft->corridor_safe,
          "vertical flood shaft is deep but corridor-safe");
    check(tunnel != nullptr && tunnel->viscosity > 1.4F && tunnel->corridor_safe,
          "submerged service tunnel uses thick green water");
    check(cavity != nullptr && cavity->pressure_exposed && !cavity->corridor_safe,
          "open cavity is pressure-exposed");

    const auto cloud = render::PointCloud::make_liminal_level(level, {360'000U, seed});
    const auto hall_ranges = cloud.ranges_for("Long Signal Hall");
    const auto tunnel_ranges = cloud.ranges_for("Submerged Service Tunnel");
    const auto cavity_ranges = cloud.ranges_for("Open Pressure Cavity");
    check(hall_ranges.size() >= 4U, "long hall is split into distance-submit bands");
    check(tunnel_ranges.size() >= 3U, "underwater tunnel is split into distance-submit bands");
    check(cavity_ranges.size() >= 4U, "open cavity is split into distance-submit bands");

    const auto near_hall = render::select_room_ranges(
        cloud, "Long Signal Hall", 360'000U, 360'000U, false,
        {712.0F, 1.72F, -164.0F}, 24.0F);
    const auto full_hall = render::select_room_ranges(
        cloud, "Long Signal Hall", 360'000U, 360'000U, false,
        {712.0F, 1.72F, -164.0F}, 120.0F);
    check(near_hall.submitted_ranges < full_hall.submitted_ranges,
          "distance submission omits far long-hall bands");
    check(near_hall.submitted_points < full_hall.submitted_points,
          "distance submission lowers long-hall point work");

    world::PlayerController save_player({791.70F, 2.72F, -164.0F});
    world::PlayerMoveInput move_off;
    move_off.forward = 1.0F;
    for (int i = 0; i < 4; ++i) {
        save_player.update(move_off, {1.0F, 0.0F, 0.0F}, 1.0F / 60.0F, level);
    }
    world::PlayerMoveInput save_jump = move_off;
    save_jump.jump_pressed = true;
    save_player.update(save_jump, {1.0F, 0.0F, 0.0F}, 1.0F / 60.0F, level);
    check(save_player.last_jump_kind() == world::JumpKind::save,
          "jump shortly after leaving a ledge becomes a save jump");
    check(save_player.save_jump_count() == 1U,
          "save jump counter increments exactly once");

    const auto entry_before = save_player.water_entry_serial();
    for (int i = 0; i < 240 && save_player.water_entry_serial() == entry_before; ++i) {
        save_player.update(move_off, {1.0F, 0.0F, 0.0F}, 1.0F / 60.0F, level);
    }
    check(save_player.water_entry_serial() > entry_before,
          "save jump reaches a water-entry event");
    check(save_player.last_water_entry_was_bomb(),
          "save-jump water entry is classified as a bomb");
    check(save_player.bomb_entry_count() == 1U,
          "bomb entry counter increments");

    world::PlayerController tunnel_player({840.0F, -4.0F, -164.0F});
    world::PlayerMoveInput idle;
    const float tunnel_health = tunnel_player.health();
    for (int i = 0; i < 12; ++i) {
        tunnel_player.update(idle, {1.0F, 0.0F, 0.0F}, 1.0F / 60.0F, level);
    }
    check(tunnel_player.water_depth() > 1.0F, "tunnel player reports underwater depth");
    check(tunnel_player.pressure_damage_per_second() == 0.0F,
          "deep constrained tunnel suppresses pressure damage");
    check(std::abs(tunnel_player.health() - tunnel_health) < 0.01F,
          "safe tunnel does not damage health while oxygen remains");

    world::PlayerController cavity_player({900.0F, -8.0F, -164.0F});
    const float cavity_health = cavity_player.health();
    for (int i = 0; i < 20; ++i) {
        cavity_player.update(idle, {1.0F, 0.0F, 0.0F}, 1.0F / 60.0F, level);
    }
    check(cavity_player.pressure_damage_per_second() > 0.0F,
          "open cavity applies depth pressure");
    check(cavity_player.health() < cavity_health,
          "open-cavity pressure reduces health");

    world::PlayerController tech_player({802.0F, 1.72F, -157.5F});
    world::PlayerMoveInput interact;
    interact.interact_pressed = true;
    tech_player.update(interact, {0.0F, 0.0F, -1.0F}, 1.0F / 60.0F, level);
    check(tech_player.has_almond_depth_tech(),
          "interacting near the station equips Almond depth technology");
    check(tech_player.tech_pickup_count() == 1U,
          "Almond depth technology pickup is recorded");

    render::WaterDisturbance splash;
    splash.trigger({800.0F, 0.1F, -164.0F}, 1.0F, true);
    check(splash.active() && splash.bomb() && splash.radius() > 2.0F,
          "bomb entry creates an active radial water disturbance");
    const float radius_before = splash.radius();
    splash.update(0.3F);
    check(splash.radius() > radius_before && splash.intensity() < 1.0F,
          "water disturbance expands while fading");

    if (failures == 0) {
        std::cout << "All SignalCloud Pivot 6 Room Complex & Depth Lab tests passed.\n";
        return 0;
    }
    return 1;
}
