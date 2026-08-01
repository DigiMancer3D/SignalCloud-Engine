#include "engine/physics/showcase_runtime.hpp"

#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

namespace {

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

}  // namespace

int main() {
    using namespace signalcloud::physics;
    PhysicsProfile profile;
    profile.profile_id = "showcase.test";
    profile.shape = "sphere";
    profile.mass = 5.0F;
    profile.friction = 0.65F;
    profile.restitution = 0.45F;
    profile.break_threshold = 80.0F;

    const auto first = simulate_showcase(profile, ShowcaseTest::bounce, 6.0F, 120U);
    const auto second = simulate_showcase(profile, ShowcaseTest::bounce, 6.0F, 120U);
    require(first.signature == second.signature, "Showcase simulation must be deterministic");
    require(first.state.bounce_count > 0U, "Bounce test should bounce");
    require(first.state.position.y >= 0.29F, "Showcase object must remain above floor");

    PhysicsProfile break_profile = profile;
    break_profile.mass = 20.0F;
    break_profile.break_threshold = 20.0F;
    const auto broken = simulate_showcase(break_profile, ShowcaseTest::break_test, 3.0F, 120U);
    require(broken.state.broken, "Break test should exceed low threshold");

    const auto temp = std::filesystem::temp_directory_path() / "signalcloud_showcase_test.scphysics";
    {
        std::ofstream output(temp);
        output << R"({
  "schema": "signalcloud.physics-profile",
  "profile_id": "showcase.loaded",
  "shape": "capsule",
  "mass": 12.5,
  "friction": 0.8,
  "restitution": 0.2,
  "gravity_scale": 1.1,
  "drag": 0.03,
  "break_threshold": 120.0,
  "impact_multiplier": 1.4,
  "sleep_policy": "after_settle",
  "future_field": {"preserved_by_authoring": true}
})";
    }
    PhysicsProfile loaded;
    std::string error;
    require(load_physics_profile(temp, loaded, &error), "Physics profile should load: " + error);
    require(loaded.profile_id == "showcase.loaded", "Profile ID should load");
    require(loaded.shape == "capsule", "Shape should load");
    require(std::abs(loaded.mass - 12.5F) < 0.001F, "Mass should load");
    std::filesystem::remove(temp);

    PhysicsProfile unsafe;
    unsafe.mass = -500.0F;
    unsafe.restitution = 4.0F;
    unsafe.shape = "unsafe-script";
    unsafe.gravity_scale = 100.0F;
    unsafe = normalize_profile(unsafe);
    require(unsafe.mass >= 0.001F, "Mass should clamp safely");
    require(unsafe.restitution <= 1.0F, "Restitution should clamp safely");
    require(unsafe.shape == "box", "Unknown shape should fall back");
    require(unsafe.gravity_scale <= 8.0F, "Gravity should be bounded");

    std::cout << "SignalCloud A7 Showcase runtime tests PASS | signature " << first.signature << '\n';
    return 0;
}
