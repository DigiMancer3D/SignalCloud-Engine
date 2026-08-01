#include "engine/lighting/illuminosity_runtime.hpp"

#include "engine/data/udata.hpp"
#include "engine/world/liminal_level.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <cctype>
#include <cstdlib>
#include <limits>
#include <numbers>
#include <string>
#include <system_error>
#include <utility>

namespace signalcloud::lighting {
namespace {

std::string trim(std::string_view value) {
    std::size_t first = 0U;
    while (first < value.size() && std::isspace(static_cast<unsigned char>(value[first])) != 0) ++first;
    std::size_t last = value.size();
    while (last > first && std::isspace(static_cast<unsigned char>(value[last - 1U])) != 0) --last;
    return std::string(value.substr(first, last - first));
}

std::optional<std::string> json_string(std::string_view raw) {
    const std::string value = trim(raw);
    if (value.size() < 2U || value.front() != '"' || value.back() != '"') return std::nullopt;
    std::string result;
    result.reserve(value.size() - 2U);
    bool escape = false;
    for (std::size_t index = 1U; index + 1U < value.size(); ++index) {
        const char c = value[index];
        if (escape) {
            if (c == 'n') result.push_back('\n');
            else if (c == 't') result.push_back('\t');
            else result.push_back(c);
            escape = false;
        } else if (c == '\\') {
            escape = true;
        } else {
            result.push_back(c);
        }
    }
    return result;
}

std::optional<float> json_float(std::string_view raw) {
    const std::string value = trim(raw);
    if (value.empty()) return std::nullopt;
    char* end = nullptr;
    const float parsed = std::strtof(value.c_str(), &end);
    if (end == value.c_str() || *end != '\0' || !std::isfinite(parsed)) return std::nullopt;
    return parsed;
}

std::optional<std::uint32_t> json_u32(std::string_view raw) {
    const std::string value = trim(raw);
    if (value.empty() || value.front() == '-') return std::nullopt;
    std::uint32_t parsed = 0U;
    const auto result = std::from_chars(value.data(), value.data() + value.size(), parsed);
    if (result.ec != std::errc{} || result.ptr != value.data() + value.size()) return std::nullopt;
    return parsed;
}

std::optional<bool> json_bool(std::string_view raw) {
    const std::string value = trim(raw);
    if (value == "true") return true;
    if (value == "false") return false;
    return std::nullopt;
}

std::optional<math::Vec3> json_vec3(std::string_view raw) {
    const std::string value = trim(raw);
    if (value.size() < 5U || value.front() != '[' || value.back() != ']') return std::nullopt;
    std::array<float, 3> numbers{};
    std::size_t cursor = 1U;
    for (std::size_t item = 0U; item < numbers.size(); ++item) {
        const std::size_t end = item + 1U == numbers.size() ? value.size() - 1U : value.find(',', cursor);
        if (end == std::string::npos) return std::nullopt;
        const auto parsed = json_float(std::string_view(value).substr(cursor, end - cursor));
        if (!parsed) return std::nullopt;
        numbers[item] = *parsed;
        cursor = end + 1U;
    }
    return math::Vec3{numbers[0], numbers[1], numbers[2]};
}

template <typename T, typename Parser>
T value_or(const data::UDataDocument& document, std::string_view section, std::string_view key,
           T fallback, Parser parser, std::vector<std::string>& warnings) {
    const auto raw = document.value(section, key);
    if (!raw) {
        warnings.push_back(std::string(section) + "." + std::string(key) + ": missing; safe default used");
        return fallback;
    }
    const auto parsed = parser(*raw);
    if (!parsed) {
        warnings.push_back(std::string(section) + "." + std::string(key) + ": invalid; safe default used");
        return fallback;
    }
    return *parsed;
}

float distance(math::Vec3 a, math::Vec3 b) noexcept {
    const float dx = a.x - b.x;
    const float dy = a.y - b.y;
    const float dz = a.z - b.z;
    return std::sqrt(dx * dx + dy * dy + dz * dz);
}

float cross2(float ax, float az, float bx, float bz) noexcept {
    return ax * bz - az * bx;
}

struct WallHit {
    bool hit{false};
    float distance{0.0F};
    math::Vec3 point{};
    math::Vec3 normal{};
};

WallHit nearest_wall_hit(const world::LiminalLevel& level, math::Vec3 origin,
                         math::Vec3 direction, float maximum_distance) noexcept {
    WallHit best;
    best.distance = maximum_distance;
    for (const auto& wall : level.walls()) {
        const float sx = wall.end.x - wall.start.x;
        const float sz = wall.end.z - wall.start.z;
        const float denominator = cross2(direction.x, direction.z, sx, sz);
        if (std::abs(denominator) < 0.00001F) continue;
        const float qx = wall.start.x - origin.x;
        const float qz = wall.start.z - origin.z;
        const float t = cross2(qx, qz, sx, sz) / denominator;
        const float u = cross2(qx, qz, direction.x, direction.z) / denominator;
        if (t <= 0.001F || t > best.distance || u < 0.0F || u > 1.0F) continue;
        const float hit_y = origin.y + direction.y * t;
        if (hit_y < wall.base_y || hit_y > wall.base_y + wall.height) continue;
        best.hit = true;
        best.distance = t;
        best.point = origin + direction * t;
        best.normal = math::normalize_or(wall.inward_normal, {0.0F, 0.0F, 1.0F});
    }
    return best;
}

math::Vec3 rotate_y(math::Vec3 value, float radians) noexcept {
    const float c = std::cos(radians);
    const float s = std::sin(radians);
    return {value.x * c - value.z * s, value.y, value.x * s + value.z * c};
}

std::uint64_t fnv1a(std::uint64_t hash, std::uint64_t value) noexcept {
    hash ^= value;
    return hash * 1099511628211ULL;
}

std::uint64_t quantized(float value) noexcept {
    const double scaled = std::round(static_cast<double>(value) * 1000.0);
    const auto signed_value = static_cast<std::int64_t>(scaled);
    return static_cast<std::uint64_t>(signed_value);
}

float night_weight(float time_of_day) noexcept {
    const float t = std::clamp(time_of_day, 0.0F, 1.0F);
    if (t < 0.25F) return 1.0F - t * 4.0F;
    if (t < 0.75F) return 0.0F;
    return (t - 0.75F) * 4.0F;
}

float scope_radius_multiplier(LightScope scope) noexcept {
    if (scope == LightScope::room) return 2.6F;
    if (scope == LightScope::area) return 1.55F;
    return 1.0F;
}

float scope_strength_multiplier(LightScope scope) noexcept {
    if (scope == LightScope::room) return 0.88F;
    if (scope == LightScope::area) return 0.78F;
    return 1.0F;
}

}  // namespace

std::string_view light_scope_name(LightScope scope) noexcept {
    switch (scope) {
        case LightScope::local: return "local";
        case LightScope::area: return "area";
        case LightScope::room: return "room";
        case LightScope::global: return "global";
    }
    return "local";
}

std::optional<LightScope> parse_light_scope(std::string_view value) noexcept {
    if (value == "local") return LightScope::local;
    if (value == "area") return LightScope::area;
    if (value == "room") return LightScope::room;
    if (value == "global") return LightScope::global;
    return std::nullopt;
}

IlluminosityRuntime::IlluminosityRuntime(std::filesystem::path project_root,
                                         std::filesystem::path runtime_sidecar)
    : project_root_(std::move(project_root)), sidecar_path_(std::move(runtime_sidecar)) {}

bool IlluminosityRuntime::reload(std::string* error) {
    try {
        const auto document = data::UDataDocument::load(sidecar_path_);
        if (document.has_errors()) {
            if (error != nullptr) *error = "Illuminosity runtime sidecar contains structural errors.";
            valid_ = false;
            return false;
        }
        std::vector<std::string> warnings;
        IlluminosityRuntimeStats next_stats;
        next_stats.source_document = value_or<std::string>(
            document, "document", "source_document", "", json_string, warnings);
        const std::uint32_t light_count = value_or<std::uint32_t>(
            document, "document", "light_count", 0U, json_u32, warnings);
        next_stats.warning_count = value_or<std::uint32_t>(
            document, "document", "warning_count", 0U, json_u32, warnings);
        next_stats.point_budget_cost = value_or<std::uint32_t>(
            document, "document", "point_budget_cost", 0U, json_u32, warnings);
        next_stats.used_fallback = value_or<bool>(
            document, "document", "used_fallback", false, json_bool, warnings);

        LightBudgetDefinition next_budget;
        next_budget.max_active_lights = std::clamp(value_or<std::uint32_t>(document,
            "runtime-budget", "max_active_lights", next_budget.max_active_lights, json_u32, warnings), 1U, 64U);
        next_budget.max_point_budget = std::clamp(value_or<std::uint32_t>(document,
            "runtime-budget", "max_point_budget", next_budget.max_point_budget, json_u32, warnings), 64U, 2'000'000U);
        next_budget.rays_per_light = std::clamp(value_or<std::uint32_t>(document,
            "runtime-budget", "rays_per_light", next_budget.rays_per_light, json_u32, warnings), 1U, 16U);
        next_budget.max_diagnostic_rays = std::clamp(value_or<std::uint32_t>(document,
            "runtime-budget", "max_diagnostic_rays", next_budget.max_diagnostic_rays, json_u32, warnings), 1U, 128U);
        next_budget.stress_scale = std::clamp(value_or<float>(document,
            "runtime-budget", "stress_scale", next_budget.stress_scale, json_float, warnings), 0.10F, 2.0F);

        DayNightDefinition next_day;
        next_day.day_color = value_or<math::Vec3>(document, "day-night", "day_color",
            next_day.day_color, json_vec3, warnings);
        next_day.day_illuminosity_percent = std::clamp(value_or<float>(document, "day-night",
            "day_illuminosity_percent", next_day.day_illuminosity_percent, json_float, warnings), 0.0F, 160.0F);
        next_day.night_color = value_or<math::Vec3>(document, "day-night", "night_color",
            next_day.night_color, json_vec3, warnings);
        next_day.night_illuminosity_percent = std::clamp(value_or<float>(document, "day-night",
            "night_illuminosity_percent", next_day.night_illuminosity_percent, json_float, warnings), 0.0F, 160.0F);
        next_day.day_to_night_seconds = std::clamp(value_or<float>(document, "day-night",
            "day_to_night_seconds", next_day.day_to_night_seconds, json_float, warnings), 1.0F, 86400.0F);
        next_day.night_to_day_seconds = std::clamp(value_or<float>(document, "day-night",
            "night_to_day_seconds", next_day.night_to_day_seconds, json_float, warnings), 1.0F, 86400.0F);
        next_day.time_of_day = std::clamp(value_or<float>(document, "day-night", "time_of_day",
            next_day.time_of_day, json_float, warnings), 0.0F, 1.0F);
        next_day.playing = value_or<bool>(document, "day-night", "playing", false, json_bool, warnings);
        next_day.paused = value_or<bool>(document, "day-night", "paused", false, json_bool, warnings);
        next_day.protected_global = value_or<bool>(document, "day-night", "protected_global", true, json_bool, warnings);

        std::vector<LightDefinition> next_lights;
        next_lights.reserve(std::min<std::uint32_t>(light_count, 64U));
        const std::uint32_t bounded_count = std::min<std::uint32_t>(light_count, 64U);
        if (light_count > bounded_count) warnings.push_back("document.light_count exceeded 64 and was bounded");
        for (std::uint32_t index = 0U; index < bounded_count; ++index) {
            const std::string section = "light." + std::to_string(index);
            LightDefinition light;
            light.id = value_or<std::string>(document, section, "id", "light-" + std::to_string(index), json_string, warnings);
            light.name = value_or<std::string>(document, section, "name", light.id, json_string, warnings);
            light.position = value_or<math::Vec3>(document, section, "position", {0.0F, 3.4F, 3.0F}, json_vec3, warnings);
            light.target = value_or<math::Vec3>(document, section, "target", {0.0F, 1.2F, 0.0F}, json_vec3, warnings);
            light.color = value_or<math::Vec3>(document, section, "color", {1.0F, 1.0F, 1.0F}, json_vec3, warnings);
            light.illuminosity_percent = std::clamp(value_or<float>(document, section,
                "illuminosity_percent", 0.0F, json_float, warnings), 0.0F, 160.0F);
            light.aperture_distance = std::clamp(value_or<float>(document, section,
                "aperture_distance", 2.5F, json_float, warnings), 0.0F, 100.0F);
            light.radius = std::clamp(value_or<float>(document, section, "radius", 1.0F,
                json_float, warnings), 0.05F, 250.0F);
            light.cone_or_degree_burst = std::clamp(value_or<float>(document, section,
                "cone_or_degree_burst", 80.0F, json_float, warnings), 0.0F, 360.0F);
            const std::string scope_text = value_or<std::string>(document, section, "scope",
                "local", json_string, warnings);
            light.scope = parse_light_scope(scope_text).value_or(LightScope::local);
            light.zone = value_or<std::string>(document, section, "zone", "Reception Tape", json_string, warnings);
            light.enabled = value_or<bool>(document, section, "enabled", false, json_bool, warnings);
            light.dynamic = value_or<bool>(document, section, "dynamic", false, json_bool, warnings);
            light.bounce_count_limit = std::min<std::uint32_t>(value_or<std::uint32_t>(document,
                section, "bounce_count_limit", 0U, json_u32, warnings), 4U);
            light.bounce_cost = std::clamp(value_or<float>(document, section, "bounce_cost",
                0.34F, json_float, warnings), 0.0F, 1.0F);
            light.shadow_policy = value_or<std::string>(document, section, "shadow_policy",
                "none", json_string, warnings);
            light.day_night_binding = value_or<std::string>(document, section,
                "day_night_binding", "none", json_string, warnings);
            light.point_budget_cost = std::min<std::uint32_t>(value_or<std::uint32_t>(document,
                section, "point_budget_cost", 0U, json_u32, warnings), 200000U);
            light.budget_priority = std::min<std::uint32_t>(value_or<std::uint32_t>(document,
                section, "budget_priority", 100U, json_u32, warnings), 1000U);
            light.seed = value_or<std::uint32_t>(document, section, "seed", 0U, json_u32, warnings);
            if (light.enabled) ++next_stats.enabled_lights;
            next_lights.push_back(std::move(light));
        }
        next_stats.configured_lights = next_lights.size();
        next_stats.warning_count += warnings.size();
        std::uint64_t signature = 1469598103934665603ULL;
        for (const auto& light : next_lights) {
            for (const unsigned char c : light.id) signature = fnv1a(signature, c);
            signature = fnv1a(signature, quantized(light.position.x));
            signature = fnv1a(signature, quantized(light.position.y));
            signature = fnv1a(signature, quantized(light.position.z));
            signature = fnv1a(signature, quantized(light.illuminosity_percent));
            signature = fnv1a(signature, quantized(light.radius));
            signature = fnv1a(signature, light.point_budget_cost);
            signature = fnv1a(signature, light.budget_priority);
            signature = fnv1a(signature, light.seed);
        }
        signature = fnv1a(signature, quantized(next_day.time_of_day));
        signature = fnv1a(signature, next_day.playing ? 1U : 0U);
        signature = fnv1a(signature, next_day.paused ? 1U : 0U);
        signature = fnv1a(signature, next_budget.max_point_budget);
        signature = fnv1a(signature, next_budget.max_active_lights);
        next_stats.deterministic_signature = signature;

        lights_ = std::move(next_lights);
        day_night_ = next_day;
        budget_ = next_budget;
        runtime_budget_scale_ = budget_.stress_scale;
        stats_ = std::move(next_stats);
        warnings_ = std::move(warnings);
        rebuild_budget_selection();
        valid_ = true;
        return true;
    } catch (const std::exception& ex) {
        if (error != nullptr) *error = ex.what();
        valid_ = false;
        return false;
    }
}

void IlluminosityRuntime::rebuild_budget_selection() noexcept {
    for (auto& light : lights_) light.budget_active = false;
    std::vector<std::size_t> candidates;
    for (std::size_t index = 0U; index < lights_.size(); ++index) {
        if (lights_[index].enabled) candidates.push_back(index);
    }
    std::stable_sort(candidates.begin(), candidates.end(), [&](std::size_t left, std::size_t right) {
        if (lights_[left].budget_priority != lights_[right].budget_priority) {
            return lights_[left].budget_priority > lights_[right].budget_priority;
        }
        return lights_[left].id < lights_[right].id;
    });
    const double scaled = static_cast<double>(budget_.max_point_budget) *
                          static_cast<double>(std::clamp(runtime_budget_scale_, 0.10F, 2.0F));
    const auto effective_budget = static_cast<std::uint32_t>(std::clamp(
        scaled, 1.0, static_cast<double>(std::numeric_limits<std::uint32_t>::max())));
    std::uint32_t selected_cost = 0U;
    std::size_t selected_count = 0U;
    for (const std::size_t index : candidates) {
        auto& light = lights_[index];
        const bool count_available = selected_count < budget_.max_active_lights;
        const bool cost_available = light.point_budget_cost <= effective_budget - std::min(selected_cost, effective_budget);
        if (!count_available || !cost_available) continue;
        light.budget_active = true;
        selected_cost += light.point_budget_cost;
        ++selected_count;
    }
    stats_.budget_active_lights = selected_count;
    stats_.budget_limited_lights = candidates.size() - selected_count;
    stats_.selected_point_budget_cost = selected_cost;
    stats_.effective_max_point_budget = effective_budget;
}

void IlluminosityRuntime::update(float dt_seconds) noexcept {
    if (!day_night_.playing || day_night_.paused || dt_seconds <= 0.0F || !std::isfinite(dt_seconds)) return;
    const float period = day_night_.time_of_day < 0.5F
        ? day_night_.day_to_night_seconds : day_night_.night_to_day_seconds;
    day_night_.time_of_day = std::fmod(day_night_.time_of_day + dt_seconds / std::max(2.0F, period * 2.0F), 1.0F);
    if (day_night_.time_of_day < 0.0F) day_night_.time_of_day += 1.0F;
}

void IlluminosityRuntime::set_time_of_day(float value) noexcept {
    if (std::isfinite(value)) day_night_.time_of_day = std::clamp(value, 0.0F, 1.0F);
}

void IlluminosityRuntime::play_day_night() noexcept {
    day_night_.playing = true;
    day_night_.paused = false;
}

void IlluminosityRuntime::pause_day_night(bool paused) noexcept {
    if (!day_night_.playing && paused) day_night_.playing = true;
    day_night_.paused = paused;
}

void IlluminosityRuntime::stop_day_night(float reset_time) noexcept {
    day_night_.playing = false;
    day_night_.paused = false;
    set_time_of_day(reset_time);
}

void IlluminosityRuntime::set_budget_scale(float value) noexcept {
    if (!std::isfinite(value)) return;
    runtime_budget_scale_ = std::clamp(value, 0.10F, 2.0F);
    rebuild_budget_selection();
}

void IlluminosityRuntime::apply_authoring_override(std::string_view scope,
                                                    float illuminosity_percent,
                                                    float radius,
                                                    float day_illuminosity_percent,
                                                    float night_illuminosity_percent,
                                                    float time_of_day) noexcept {
    if (!lights_.empty()) {
        lights_.front().scope = parse_light_scope(scope).value_or(lights_.front().scope);
        if (std::isfinite(illuminosity_percent)) {
            lights_.front().illuminosity_percent = std::clamp(illuminosity_percent, 0.0F, 160.0F);
        }
        if (std::isfinite(radius)) lights_.front().radius = std::clamp(radius, 0.05F, 250.0F);
    }
    if (std::isfinite(day_illuminosity_percent)) {
        day_night_.day_illuminosity_percent = std::clamp(day_illuminosity_percent, 0.0F, 160.0F);
    }
    if (std::isfinite(night_illuminosity_percent)) {
        day_night_.night_illuminosity_percent = std::clamp(night_illuminosity_percent, 0.0F, 160.0F);
    }
    set_time_of_day(time_of_day);
}

IlluminosityFrame IlluminosityRuntime::evaluate(math::Vec3 viewer_position,
                                                std::string_view active_zone) const noexcept {
    IlluminosityFrame frame;
    const float night = night_weight(day_night_.time_of_day);
    frame.global_color = day_night_.day_color * (1.0F - night) + day_night_.night_color * night;
    const float global_i = day_night_.day_illuminosity_percent * (1.0F - night) +
                           day_night_.night_illuminosity_percent * night;
    frame.global_strength = std::clamp(global_i / 120.0F, 0.0F, 1.25F);
    frame.visibility_floor = std::clamp(0.22F + frame.global_strength * 0.50F, 0.20F, 0.84F);
    frame.point_budget_cost = stats_.point_budget_cost;
    frame.selected_point_budget_cost = stats_.selected_point_budget_cost;
    frame.active_lights = stats_.budget_active_lights;
    frame.budget_limited_lights = stats_.budget_limited_lights;

    struct Candidate {
        EvaluatedLightContribution contribution;
        float score{0.0F};
    };
    std::vector<Candidate> candidates;
    candidates.reserve(lights_.size());
    float global_color_weight = 1.0F;
    for (std::size_t light_index = 0U; light_index < lights_.size(); ++light_index) {
        const auto& light = lights_[light_index];
        if (!light.enabled || !light.budget_active) continue;
        if (light.scope == LightScope::global) {
            const float weight = std::clamp(light.illuminosity_percent / 160.0F, 0.0F, 1.0F);
            const float contribution = weight * 0.24F;
            frame.global_color = (frame.global_color * global_color_weight + light.color * contribution) /
                                 std::max(0.001F, global_color_weight + contribution);
            global_color_weight += contribution;
            frame.global_strength = std::clamp(frame.global_strength + contribution, 0.0F, 1.35F);
            ++frame.contributing_lights;
            continue;
        }
        if (!light.zone.empty() && light.zone != active_zone) continue;
        const float effective_radius = light.radius * scope_radius_multiplier(light.scope);
        const float d = distance(viewer_position, light.position);
        if (d >= effective_radius && light.scope != LightScope::room) continue;
        float falloff = 1.0F - std::clamp(d / std::max(0.05F, effective_radius), 0.0F, 1.0F);
        if (light.scope == LightScope::room) falloff = std::max(0.48F, falloff);
        const float day_binding = light.day_night_binding == "multiply"
            ? std::clamp(0.45F + frame.global_strength * 0.70F, 0.35F, 1.25F) : 1.0F;
        const float score = std::clamp(light.illuminosity_percent / 100.0F, 0.0F, 1.6F) *
                            falloff * scope_strength_multiplier(light.scope) * day_binding;
        if (score <= 0.0001F) continue;
        candidates.push_back({{light.position, light.color, effective_radius,
                               std::clamp(score, 0.0F, 1.45F), light_index}, score});
        ++frame.contributing_lights;
    }
    std::stable_sort(candidates.begin(), candidates.end(), [](const Candidate& left, const Candidate& right) {
        if (left.score != right.score) return left.score > right.score;
        return left.contribution.source_index < right.contribution.source_index;
    });
    frame.local_light_count = std::min<std::size_t>(candidates.size(), frame.local_lights.size());
    float combined = 0.0F;
    for (std::size_t index = 0U; index < frame.local_light_count; ++index) {
        frame.local_lights[index] = candidates[index].contribution;
        combined += candidates[index].contribution.strength * (index == 0U ? 1.0F : 0.62F);
    }
    if (frame.local_light_count > 0U) {
        const auto& strongest = frame.local_lights.front();
        frame.local_enabled = true;
        frame.local_position = strongest.position;
        frame.local_color = strongest.color;
        frame.local_radius = strongest.radius;
        frame.local_strength = std::clamp(combined, 0.0F, 1.60F);
    }
    frame.point_size_boost = std::clamp(frame.local_strength * 0.30F, 0.0F, 0.48F);
    frame.visibility_floor = std::clamp(frame.visibility_floor + frame.local_strength * 0.11F, 0.20F, 0.92F);
    return frame;
}

SurfaceProbeDiagnostic IlluminosityRuntime::probe_surface(
    math::Vec3 sample_position, std::string_view active_zone) const noexcept {
    SurfaceProbeDiagnostic probe;
    probe.sample_position = sample_position;
    const IlluminosityFrame frame = evaluate(sample_position, active_zone);
    math::Vec3 color = frame.global_color * std::max(0.05F, frame.global_strength);
    float weight = std::max(0.05F, frame.global_strength);
    float local_i = 0.0F;
    for (std::size_t index = 0U; index < frame.local_light_count; ++index) {
        const auto& light = frame.local_lights[index];
        const float contribution = light.strength * (index == 0U ? 1.0F : 0.62F);
        color += light.color * contribution;
        weight += contribution;
        local_i += contribution * 62.0F;
    }
    probe.effective_color = color / std::max(0.001F, weight);
    probe.effective_illuminosity_percent = std::clamp(
        frame.global_strength * 72.0F + local_i, 0.0F, 180.0F);
    probe.visibility = frame.visibility_floor;
    probe.point_size_boost = frame.point_size_boost;
    probe.contributing_lights = frame.contributing_lights;
    const float value = probe.effective_illuminosity_percent;
    if (value <= 3.0F) probe.quality_band = "DARKNESS";
    else if (value <= 29.0F) probe.quality_band = "OUTLINES";
    else if (value <= 45.0F) probe.quality_band = "LOW HALF";
    else if (value <= 65.0F) probe.quality_band = "LOW NORMAL";
    else if (value <= 77.0F) probe.quality_band = "GOOD";
    else if (value <= 89.0F) probe.quality_band = "GREAT";
    else if (value <= 110.0F) probe.quality_band = "BEST";
    else probe.quality_band = "BOOSTED";
    return probe;
}

std::vector<SignalRayDiagnostic> IlluminosityRuntime::diagnostic_rays_bounded(
    const world::LiminalLevel& level, std::size_t light_index, std::size_t ray_limit) const {
    std::vector<SignalRayDiagnostic> rays;
    if (light_index >= lights_.size() || !lights_[light_index].enabled ||
        !lights_[light_index].budget_active || ray_limit == 0U) return rays;
    const auto& light = lights_[light_index];
    const std::size_t ray_count = std::clamp<std::size_t>(ray_limit, 1U, 16U);
    rays.reserve(ray_count);
    math::Vec3 base = math::normalize_or(light.target - light.position, {0.0F, 0.0F, -1.0F});
    const float burst = std::clamp(light.cone_or_degree_burst, 0.0F, 180.0F) *
                        std::numbers::pi_v<float> / 180.0F;
    for (std::size_t index = 0U; index < ray_count; ++index) {
        const float centered = ray_count == 1U ? 0.0F
            : static_cast<float>(index) / static_cast<float>(ray_count - 1U) - 0.5F;
        math::Vec3 direction = math::normalize_or(rotate_y(base, centered * burst), base);
        math::Vec3 origin = light.position;
        math::Vec3 end = origin;
        float travelled = 0.0F;
        float remaining_distance = light.radius;
        float remaining_i = light.illuminosity_percent;
        std::uint32_t bounces = 0U;
        bool hit_any = false;
        for (;;) {
            const WallHit hit = nearest_wall_hit(level, origin, direction, remaining_distance);
            if (!hit.hit) {
                end = origin + direction * remaining_distance;
                travelled += remaining_distance;
                break;
            }
            hit_any = true;
            end = hit.point;
            travelled += hit.distance;
            remaining_distance = std::max(0.0F, remaining_distance - hit.distance);
            if (bounces >= light.bounce_count_limit || remaining_distance <= 0.01F) break;
            remaining_i *= 1.0F - light.bounce_cost;
            const float dot_value = math::dot(direction, hit.normal);
            direction = math::normalize_or(direction - hit.normal * (2.0F * dot_value), direction * -1.0F);
            origin = end + direction * 0.015F;
            ++bounces;
        }
        const float distance_factor = 1.0F - std::clamp(travelled / std::max(0.05F, light.radius), 0.0F, 1.0F);
        rays.push_back({light.position, end, travelled,
                        std::max(0.0F, remaining_i * distance_factor), bounces, hit_any,
                        light_index, index});
    }
    return rays;
}

std::vector<SignalRayDiagnostic> IlluminosityRuntime::diagnostic_rays(
    const world::LiminalLevel& level, std::size_t light_index) const {
    return diagnostic_rays_bounded(level, light_index, budget_.rays_per_light);
}

std::vector<SignalRayDiagnostic> IlluminosityRuntime::diagnostic_rays_all(
    const world::LiminalLevel& level) const {
    std::vector<SignalRayDiagnostic> all;
    const std::size_t total_limit = budget_.max_diagnostic_rays;
    all.reserve(total_limit);
    for (std::size_t light_index = 0U; light_index < lights_.size() && all.size() < total_limit; ++light_index) {
        const std::size_t remaining = total_limit - all.size();
        const std::size_t per_light = std::min<std::size_t>(budget_.rays_per_light, remaining);
        auto rays = diagnostic_rays_bounded(level, light_index, per_light);
        all.insert(all.end(), rays.begin(), rays.end());
    }
    return all;
}

}  // namespace signalcloud::lighting
