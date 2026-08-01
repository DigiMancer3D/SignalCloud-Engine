#include "engine/benchmark/native_stress_route.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/player_controller.hpp"
#include "engine/world/world_seed.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>

namespace {
void check(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

float angle_degrees(signalcloud::math::Vec3 a, signalcloud::math::Vec3 b) {
    a = signalcloud::math::normalize_or(a);
    b = signalcloud::math::normalize_or(b);
    constexpr float pi = 3.14159265358979323846F;
    return std::acos(std::clamp(signalcloud::math::dot(a, b), -1.0F, 1.0F)) * 180.0F / pi;
}
}

int main() {
    try {
        const auto seed = signalcloud::world::mix_seed(0xA12D0A1ULL, {0, 0, 0}, 4);
        const auto level = signalcloud::world::LiminalLevel::make_pivot11_scavenging(seed);
        const auto route = signalcloud::benchmark::NativeStressRoute::build(level);
        check(route.valid(), "route is valid");
        check(route.length() > 100.0F, "route is long enough");
        check(route.zone_count() >= 12U, "route reaches enough zones");
        check(route.waypoints().size() >= 40U, "route has enough waypoints");

        bool found_standing_center = false;
        bool found_crouched_window = false;
        for (const auto& waypoint : route.waypoints()) {
            const float ground = level.ground_height_at(waypoint.position.x, waypoint.position.z);
            const float eye_height = waypoint.position.y - ground;
            if (waypoint.label == "Reception Tape center") {
                found_standing_center = true;
                check(eye_height >= 1.55F && eye_height <= 1.68F, "standing camera uses lowered eye height");
            }
            if (waypoint.crouched) {
                found_crouched_window = true;
                check(eye_height <= 1.22F, "window route uses crouched eye height");
            }
        }
        check(found_standing_center, "standing center waypoint found");
        check(found_crouched_window, "crouched window waypoint found");

        std::set<std::string> seen;
        signalcloud::math::Vec3 previous_look{};
        bool have_previous = false;
        std::size_t previous_segment = 0U;
        float maximum_look_step = 0.0F;
        for (float distance = 0.0F; distance < route.length(); distance += 0.25F) {
            const auto pose = route.pose_at(distance);
            check(std::isfinite(pose.position.x) && std::isfinite(pose.position.y) &&
                  std::isfinite(pose.position.z) && std::isfinite(pose.look_at.x),
                  "route pose remains finite");
            const auto look = pose.look_at - pose.position;
            if (have_previous && !pose.portal_jump && pose.segment_index == previous_segment) {
                maximum_look_step = std::max(maximum_look_step, angle_degrees(previous_look, look));
            }
            previous_look = look;
            previous_segment = pose.segment_index;
            have_previous = true;
            seen.insert(pose.zone);
        }
        check(maximum_look_step < 90.0F, "look targets blend within each turn segment; max=" + std::to_string(maximum_look_step));
        check(seen.size() >= 10U, "sampled route sees enough zones");

        signalcloud::benchmark::NativeStressRouteGuard guard;
        signalcloud::benchmark::RoutePose forced_void;
        forced_void.position = {5000.0F, 1.62F, 5000.0F};
        forced_void.look_at = forced_void.position + signalcloud::math::Vec3{1.0F, 0.0F, 0.0F};
        forced_void.zone = "Reception Tape";
        const auto recovered = guard.stabilize(level, forced_void, forced_void.position);
        check(recovered.corrected, "route guard corrects an out-of-bounds stress pose");
        check(recovered.entered_void, "route guard records only the beginning of a Signal Void excursion");
        check(recovered.effective_zone == "Reception Tape", "route guard uses the expected authored room");
        check(level.zone_name(recovered.position) != "Signal Void", "route guard returns a position inside authored space");

        const auto repeated = guard.stabilize(level, forced_void, forced_void.position);
        check(repeated.corrected && !repeated.entered_void,
              "repeated invalid frames are contained without repeated void-entry events");
        const auto valid_again = guard.stabilize(level, route.pose_at(0.0F), level.spawn_position());
        check(valid_again.exited_void, "returning to a valid room closes the Signal Void excursion");

        guard.reset();
        signalcloud::world::PlayerController route_player(level.spawn_position());
        std::size_t contained_samples = 0U;
        for (float distance = 0.0F; distance < route.length(); distance += 0.85F) {
            const auto pose = route.pose_at(distance);
            route_player.teleport(pose.position);
            signalcloud::world::PlayerMoveInput idle;
            route_player.update(idle, signalcloud::math::normalize_or(pose.look_at - pose.position),
                                0.10F, level);
            const auto stable = guard.stabilize(level, pose, route_player.position());
            if (stable.corrected) ++contained_samples;
            check(stable.effective_zone != "Signal Void",
                  "coarse/lagged route samples never publish Signal Void as the active zone");
            check(level.zone_name(stable.position) != "Signal Void",
                  "coarse/lagged route samples remain inside an authored room");
        }
        check(guard.void_entry_count() <= guard.correction_count(),
              "route guard coalesces repeated correction frames into bounded excursion entries");

        std::cout << "PASS: native stress route " << route.length() << "m, "
                  << route.zone_count() << " zones, " << route.waypoints().size()
                  << " waypoints, max look step " << maximum_look_step << " degrees\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
