#pragma once

#include "engine/math/vec.hpp"

#include <cstddef>
#include <filesystem>
#include <string>
#include <string_view>

namespace signalcloud::physics {

enum class ShowcaseTest { drop, bounce, slide, throw_arc, break_test };

struct PhysicsProfile {
    std::string profile_id{"showcase.default"};
    std::string shape{"box"};
    float mass{4.0F};
    float friction{0.55F};
    float restitution{0.28F};
    float gravity_scale{1.0F};
    float drag{0.04F};
    float break_threshold{18.0F};
    float impact_multiplier{1.0F};
    math::Vec3 collision_half_extents{0.50F, 0.50F, 0.50F};
    float collision_radius{0.50F};
    std::string sleep_policy{"after_settle"};
};

struct ShowcaseState {
    math::Vec3 position{};
    math::Vec3 velocity{};
    float yaw_radians{0.0F};
    float angular_velocity{0.0F};
    float elapsed_seconds{0.0F};
    float max_speed{0.0F};
    float impact_speed{0.0F};
    std::size_t bounce_count{0U};
    std::size_t settle_frames{0U};
    bool broken{false};
    bool settled{false};
};

struct ShowcaseResult {
    ShowcaseTest test{ShowcaseTest::drop};
    ShowcaseState state{};
    float duration_seconds{0.0F};
    std::size_t steps{0U};
    std::string signature;
};

[[nodiscard]] bool load_physics_profile(const std::filesystem::path& path,
                                        PhysicsProfile& profile,
                                        std::string* error = nullptr);
[[nodiscard]] PhysicsProfile normalize_profile(PhysicsProfile profile) noexcept;
[[nodiscard]] ShowcaseState initial_state(ShowcaseTest test) noexcept;
[[nodiscard]] float showcase_support_height(const PhysicsProfile& profile) noexcept;
void reset_showcase_state(ShowcaseTest test, const PhysicsProfile& profile,
                          ShowcaseState& state) noexcept;
void step_showcase(const PhysicsProfile& profile, ShowcaseState& state,
                   float dt, std::size_t settle_frame_limit = 40U) noexcept;
[[nodiscard]] ShowcaseResult simulate_showcase(const PhysicsProfile& profile,
                                               ShowcaseTest test,
                                               float duration_seconds = 6.0F,
                                               std::size_t hz = 120U);
[[nodiscard]] std::string_view showcase_test_name(ShowcaseTest test) noexcept;
[[nodiscard]] ShowcaseTest parse_showcase_test(std::string_view value) noexcept;

}  // namespace signalcloud::physics
