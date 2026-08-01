#include "engine/physics/showcase_runtime.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <limits>
#include <optional>
#include <sstream>
#include <stdexcept>

namespace signalcloud::physics {
namespace {

std::string read_text(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("Unable to open SC physics profile: " + path.string());
    std::ostringstream buffer;
    buffer << input.rdbuf();
    if (buffer.str().size() > 2U * 1024U * 1024U) {
        throw std::runtime_error("SC physics profile exceeds the 2 MiB runtime limit");
    }
    return buffer.str();
}

std::optional<std::size_t> value_start(std::string_view text, std::string_view key) {
    const std::string quoted = "\"" + std::string(key) + "\"";
    std::size_t position = text.find(quoted);
    if (position == std::string_view::npos) return std::nullopt;
    position = text.find(':', position + quoted.size());
    if (position == std::string_view::npos) return std::nullopt;
    ++position;
    while (position < text.size() && std::isspace(static_cast<unsigned char>(text[position]))) ++position;
    return position;
}

std::optional<std::string> json_string(std::string_view text, std::string_view key) {
    const auto start_value = value_start(text, key);
    if (!start_value || *start_value >= text.size() || text[*start_value] != '"') return std::nullopt;
    std::string value;
    bool escaped = false;
    for (std::size_t index = *start_value + 1U; index < text.size(); ++index) {
        const char c = text[index];
        if (escaped) {
            switch (c) {
                case 'n': value.push_back('\n'); break;
                case 'r': value.push_back('\r'); break;
                case 't': value.push_back('\t'); break;
                default: value.push_back(c); break;
            }
            escaped = false;
        } else if (c == '\\') {
            escaped = true;
        } else if (c == '"') {
            return value;
        } else {
            value.push_back(c);
        }
    }
    return std::nullopt;
}

std::optional<float> json_float(std::string_view text, std::string_view key) {
    const auto start_value = value_start(text, key);
    if (!start_value) return std::nullopt;
    std::size_t end = *start_value;
    while (end < text.size()) {
        const char c = text[end];
        if (!(std::isdigit(static_cast<unsigned char>(c)) || c == '-' || c == '+' || c == '.' || c == 'e' || c == 'E')) break;
        ++end;
    }
    if (end == *start_value) return std::nullopt;
    try {
        const float value = std::stof(std::string(text.substr(*start_value, end - *start_value)));
        if (!std::isfinite(value)) return std::nullopt;
        return value;
    } catch (...) {
        return std::nullopt;
    }
}

std::uint64_t fnv1a(std::string_view value) noexcept {
    std::uint64_t hash = 1469598103934665603ULL;
    for (const unsigned char c : value) {
        hash ^= c;
        hash *= 1099511628211ULL;
    }
    return hash;
}

float speed_of(const math::Vec3& velocity) noexcept {
    return std::sqrt(velocity.x * velocity.x + velocity.y * velocity.y + velocity.z * velocity.z);
}

}  // namespace

PhysicsProfile normalize_profile(PhysicsProfile profile) noexcept {
    const auto finite = [](float value, float fallback) noexcept { return std::isfinite(value) ? value : fallback; };
    if (profile.shape != "box" && profile.shape != "sphere" && profile.shape != "capsule" &&
        profile.shape != "hull" && profile.shape != "compound") {
        profile.shape = "box";
    }
    if (profile.sleep_policy != "allow" && profile.sleep_policy != "never" && profile.sleep_policy != "after_settle") {
        profile.sleep_policy = "after_settle";
    }
    profile.mass = std::clamp(finite(profile.mass, 4.0F), 0.001F, 100000.0F);
    profile.friction = std::clamp(finite(profile.friction, 0.55F), 0.0F, 4.0F);
    profile.restitution = std::clamp(finite(profile.restitution, 0.28F), 0.0F, 1.0F);
    profile.gravity_scale = std::clamp(finite(profile.gravity_scale, 1.0F), -2.0F, 8.0F);
    profile.drag = std::clamp(finite(profile.drag, 0.04F), 0.0F, 10.0F);
    profile.break_threshold = std::clamp(finite(profile.break_threshold, 18.0F), 0.0F, 1000000.0F);
    profile.impact_multiplier = std::clamp(finite(profile.impact_multiplier, 1.0F), 0.0F, 100.0F);
    profile.collision_half_extents.x = std::clamp(finite(profile.collision_half_extents.x, 0.50F), 0.02F, 2000.0F);
    profile.collision_half_extents.y = std::clamp(finite(profile.collision_half_extents.y, 0.50F), 0.02F, 2000.0F);
    profile.collision_half_extents.z = std::clamp(finite(profile.collision_half_extents.z, 0.50F), 0.02F, 2000.0F);
    profile.collision_radius = std::clamp(finite(profile.collision_radius, 0.50F), 0.02F, 2000.0F);
    return profile;
}

bool load_physics_profile(const std::filesystem::path& path, PhysicsProfile& profile, std::string* error) {
    try {
        const std::string text = read_text(path);
        if (const auto schema = json_string(text, "schema"); schema && *schema != "signalcloud.physics-profile") {
            throw std::runtime_error("Unsupported SC physics profile schema: " + *schema);
        }
        PhysicsProfile candidate = profile;
        if (const auto value = json_string(text, "profile_id")) candidate.profile_id = *value;
        if (const auto value = json_string(text, "shape")) candidate.shape = *value;
        if (const auto value = json_float(text, "mass")) candidate.mass = *value;
        if (const auto value = json_float(text, "friction")) candidate.friction = *value;
        if (const auto value = json_float(text, "restitution")) candidate.restitution = *value;
        if (const auto value = json_float(text, "gravity_scale")) candidate.gravity_scale = *value;
        if (const auto value = json_float(text, "drag")) candidate.drag = *value;
        if (const auto value = json_float(text, "break_threshold")) candidate.break_threshold = *value;
        if (const auto value = json_float(text, "impact_multiplier")) candidate.impact_multiplier = *value;
        if (const auto value = json_float(text, "collision_half_x")) candidate.collision_half_extents.x = *value;
        if (const auto value = json_float(text, "collision_half_y")) candidate.collision_half_extents.y = *value;
        if (const auto value = json_float(text, "collision_half_z")) candidate.collision_half_extents.z = *value;
        if (const auto value = json_float(text, "collision_radius")) candidate.collision_radius = *value;
        if (const auto value = json_string(text, "sleep_policy")) candidate.sleep_policy = *value;
        profile = normalize_profile(std::move(candidate));
        return true;
    } catch (const std::exception& exception) {
        if (error) *error = exception.what();
        return false;
    }
}

ShowcaseState initial_state(ShowcaseTest test) noexcept {
    ShowcaseState state;
    switch (test) {
        case ShowcaseTest::drop:
            state.position = {0.0F, 5.0F, 0.0F};
            state.angular_velocity = 0.45F;
            break;
        case ShowcaseTest::bounce:
            state.position = {0.0F, 4.0F, 0.0F};
            state.velocity = {1.2F, -1.0F, 0.4F};
            state.angular_velocity = 1.35F;
            break;
        case ShowcaseTest::slide:
            state.position = {-4.0F, 0.35F, 0.0F};
            state.velocity = {5.5F, 0.0F, 0.6F};
            state.angular_velocity = 2.10F;
            break;
        case ShowcaseTest::throw_arc:
            state.position = {-3.0F, 1.35F, -1.0F};
            state.velocity = {6.2F, 5.4F, 1.7F};
            state.angular_velocity = 3.10F;
            break;
        case ShowcaseTest::break_test:
            state.position = {0.0F, 7.5F, 0.0F};
            state.velocity = {0.0F, -8.0F, 0.0F};
            state.angular_velocity = 1.75F;
            break;
    }
    return state;
}

float showcase_support_height(const PhysicsProfile& raw_profile) noexcept {
    const PhysicsProfile profile = normalize_profile(raw_profile);
    if (profile.shape == "sphere") return profile.collision_radius;
    if (profile.shape == "capsule") {
        return profile.collision_half_extents.y + profile.collision_radius;
    }
    return profile.collision_half_extents.y;
}

void reset_showcase_state(ShowcaseTest test, const PhysicsProfile& raw_profile,
                          ShowcaseState& state) noexcept {
    const PhysicsProfile profile = normalize_profile(raw_profile);
    state = initial_state(test);
    const float floor = showcase_support_height(profile);
    if (test == ShowcaseTest::slide) state.position.y = floor;
    else if (test == ShowcaseTest::throw_arc) state.position.y = std::max(floor + 0.70F, state.position.y);
    else state.position.y = std::max(state.position.y, floor + 0.20F);
}

void step_showcase(const PhysicsProfile& raw_profile, ShowcaseState& state,
                   float dt, std::size_t settle_frame_limit) noexcept {
    const PhysicsProfile profile = normalize_profile(raw_profile);
    if (!std::isfinite(dt) || dt <= 0.0F || dt > 0.1F || state.settled) return;
    constexpr float gravity = -9.80665F;
    const float radius = std::clamp(showcase_support_height(profile), 0.02F, 2000.0F);
    const float speed = speed_of(state.velocity);
    state.max_speed = std::max(state.max_speed, speed);
    const float drag_factor = std::max(0.0F, 1.0F - profile.drag * dt);
    state.velocity.x *= drag_factor;
    state.velocity.z *= drag_factor;
    state.velocity.y = state.velocity.y * drag_factor + gravity * profile.gravity_scale * dt;
    state.position += state.velocity * dt;
    state.elapsed_seconds += dt;
    state.yaw_radians = std::remainder(state.yaw_radians + state.angular_velocity * dt,
                                       6.28318530717958647692F);
    state.angular_velocity *= std::max(0.0F, 1.0F - profile.drag * dt * 0.42F);

    if (state.position.y < radius) {
        const float incoming = std::abs(state.velocity.y);
        state.impact_speed = std::max(state.impact_speed, incoming);
        const float impulse = incoming * profile.mass * profile.impact_multiplier;
        state.broken = state.broken || (profile.break_threshold > 0.0F && impulse >= profile.break_threshold);
        state.position.y = radius;
        if (incoming > 0.12F && profile.restitution > 0.015F) {
            state.velocity.y = incoming * profile.restitution;
            ++state.bounce_count;
        } else {
            state.velocity.y = 0.0F;
        }
        const float planar_friction = std::max(0.0F, 1.0F - std::min(0.98F, profile.friction * dt * 7.0F));
        state.velocity.x *= planar_friction;
        state.velocity.z *= planar_friction;
        state.angular_velocity *= std::max(0.10F, 1.0F - std::min(0.92F, profile.friction * dt * 4.0F));
    }

    // The Showcase is a bounded proving ground, not an unbounded world.
    // Side-wall response keeps every test visible while preserving the
    // authored mass/friction/restitution relationships.
    constexpr float stage_half = 7.5F;
    const float support_x = profile.shape == "sphere" ? profile.collision_radius :
                            (profile.shape == "capsule" ? profile.collision_radius : profile.collision_half_extents.x);
    const float support_z = profile.shape == "sphere" ? profile.collision_radius :
                            (profile.shape == "capsule" ? profile.collision_radius : profile.collision_half_extents.z);
    const float min_x = -stage_half + std::min(stage_half - 0.02F, support_x);
    const float max_x = stage_half - std::min(stage_half - 0.02F, support_x);
    const float min_z = -stage_half + std::min(stage_half - 0.02F, support_z);
    const float max_z = stage_half - std::min(stage_half - 0.02F, support_z);
    const float wall_bounce = std::clamp(0.18F + profile.restitution * 0.72F, 0.18F, 0.90F);
    if (state.position.x < min_x || state.position.x > max_x) {
        state.position.x = std::clamp(state.position.x, min_x, max_x);
        state.velocity.x = -state.velocity.x * wall_bounce;
        state.angular_velocity = -state.angular_velocity * 0.82F;
    }
    if (state.position.z < min_z || state.position.z > max_z) {
        state.position.z = std::clamp(state.position.z, min_z, max_z);
        state.velocity.z = -state.velocity.z * wall_bounce;
        state.angular_velocity = -state.angular_velocity * 0.82F;
    }

    const float planar = std::sqrt(state.velocity.x * state.velocity.x + state.velocity.z * state.velocity.z);
    if (state.position.y <= radius + 0.00001F && planar < 0.025F && std::abs(state.velocity.y) < 0.025F) {
        ++state.settle_frames;
        if (profile.sleep_policy == "after_settle" && state.settle_frames > settle_frame_limit) {
            state.velocity = {};
            state.angular_velocity = 0.0F;
            state.settled = true;
        }
    } else {
        state.settle_frames = 0U;
    }
}

ShowcaseResult simulate_showcase(const PhysicsProfile& raw_profile, ShowcaseTest test,
                                 float duration_seconds, std::size_t hz) {
    const PhysicsProfile profile = normalize_profile(raw_profile);
    duration_seconds = std::clamp(duration_seconds, 0.1F, 30.0F);
    hz = std::clamp<std::size_t>(hz, 20U, 1000U);
    const float dt = 1.0F / static_cast<float>(hz);
    const std::size_t steps = std::max<std::size_t>(1U, static_cast<std::size_t>(std::lround(duration_seconds * static_cast<float>(hz))));
    ShowcaseState state;
    reset_showcase_state(test, profile, state);
    for (std::size_t index = 0; index < steps; ++index) {
        step_showcase(profile, state, dt, std::max<std::size_t>(1U, hz / 3U));
    }
    std::ostringstream evidence;
    evidence << showcase_test_name(test) << '|' << profile.profile_id << '|' << profile.shape << '|'
             << std::fixed << std::setprecision(6)
             << state.position.x << '|' << state.position.y << '|' << state.position.z << '|'
             << state.max_speed << '|' << state.impact_speed << '|' << state.bounce_count << '|'
             << state.yaw_radians << '|' << state.broken << '|' << steps;
    std::ostringstream signature;
    signature << std::hex << std::setw(16) << std::setfill('0') << fnv1a(evidence.str());
    return {test, state, duration_seconds, steps, signature.str()};
}

std::string_view showcase_test_name(ShowcaseTest test) noexcept {
    switch (test) {
        case ShowcaseTest::drop: return "drop";
        case ShowcaseTest::bounce: return "bounce";
        case ShowcaseTest::slide: return "slide";
        case ShowcaseTest::throw_arc: return "throw";
        case ShowcaseTest::break_test: return "break";
    }
    return "drop";
}

ShowcaseTest parse_showcase_test(std::string_view value) noexcept {
    if (value == "bounce") return ShowcaseTest::bounce;
    if (value == "slide") return ShowcaseTest::slide;
    if (value == "throw") return ShowcaseTest::throw_arc;
    if (value == "break") return ShowcaseTest::break_test;
    return ShowcaseTest::drop;
}

}  // namespace signalcloud::physics
