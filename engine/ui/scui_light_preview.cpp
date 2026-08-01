#include "engine/ui/scui_light_preview.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace signalcloud::ui {
namespace {

constexpr float kPi = 3.14159265358979323846F;

render::PointGpu preview_point(math::Vec3 position, float radius,
                               float r, float g, float b, float a,
                               float density = 1.0F) noexcept {
    return {{position.x, position.y, position.z}, radius,
            {r, g, b, a}, {0.0F, 1.0F, 0.0F}, density};
}

float scope_multiplier(std::string_view scope) noexcept {
    if (scope == "global") return 1.0F;
    if (scope == "room") return 0.84F;
    if (scope == "area") return 0.68F;
    return 0.52F;
}

std::size_t scope_rings(std::string_view scope) noexcept {
    if (scope == "global") return 4U;
    if (scope == "room") return 3U;
    if (scope == "area") return 2U;
    return 1U;
}

}  // namespace

std::vector<render::PointGpu> ScuiLightPreview::build_points(
    const ScuiNativeRuntime& runtime, float time_seconds, const ArPose& pose) const {
    std::vector<render::PointGpu> points;
    if (!runtime.open() || runtime.panel().panel_id != "light_lab.control_surface") {
        last_stats_ = {};
        return points;
    }

    const auto forward = math::normalize_or(pose.forward, {0.0F, 0.0F, -1.0F});
    const auto right = math::normalize_or(pose.right, {1.0F, 0.0F, 0.0F});
    const auto up = math::normalize_or(math::cross(right, forward), {0.0F, 1.0F, 0.0F});
    const float local_i = static_cast<float>(runtime.number("light_i").value_or(72.0));
    const float radius_value = static_cast<float>(runtime.number("light_radius").value_or(10.0));
    const float day_i = static_cast<float>(runtime.number("day_i").value_or(95.0));
    const float night_i = static_cast<float>(runtime.number("night_i").value_or(18.0));
    const float time_of_day = std::clamp(static_cast<float>(runtime.number("time_of_day").value_or(0.35)), 0.0F, 1.0F);
    const std::string scope = runtime.string("light_scope").value_or("local");

    const float daylight = 0.5F + 0.5F * std::cos((time_of_day - 0.25F) * 2.0F * kPi);
    const float global_i = night_i + (day_i - night_i) * daylight;
    const float effective = std::clamp(local_i * 0.72F + global_i * 0.28F, 0.0F, 160.0F);
    const float intensity = std::clamp(effective / 140.0F, 0.05F, 1.15F);
    const float radius_norm = std::clamp((radius_value - 1.0F) / 23.0F, 0.0F, 1.0F);
    const float scope_scale = scope_multiplier(scope);
    const math::Vec3 center = pose.camera_position + forward * 1.34F + right * 0.61F + up * 0.02F;

    const float day_r = 1.0F;
    const float day_g = 0.83F;
    const float day_b = 0.48F;
    const float night_r = 0.24F;
    const float night_g = 0.48F;
    const float night_b = 1.0F;
    const float r = night_r + (day_r - night_r) * daylight;
    const float g = night_g + (day_g - night_g) * daylight;
    const float b = night_b + (day_b - night_b) * daylight;
    const float pulse = 0.88F + 0.12F * std::sin(time_seconds * 5.0F);

    points.reserve(1'800U);
    const std::size_t shell_latitudes = 13U;
    const std::size_t shell_longitudes = 32U;
    const float orb_radius = 0.055F + radius_norm * 0.052F;
    for (std::size_t latitude = 0U; latitude < shell_latitudes; ++latitude) {
        const float v = shell_latitudes == 1U ? 0.5F :
            static_cast<float>(latitude) / static_cast<float>(shell_latitudes - 1U);
        const float phi = (v - 0.5F) * kPi;
        const float ring_radius = std::cos(phi) * orb_radius;
        const float elevation = std::sin(phi) * orb_radius;
        for (std::size_t longitude = 0U; longitude < shell_longitudes; ++longitude) {
            const float u = static_cast<float>(longitude) / static_cast<float>(shell_longitudes);
            const float theta = u * 2.0F * kPi;
            const math::Vec3 offset = right * (std::cos(theta) * ring_radius) +
                                      up * elevation + forward * (std::sin(theta) * ring_radius * 0.55F);
            points.push_back(preview_point(center + offset, 0.0065F + intensity * 0.0025F,
                                           r * intensity, g * intensity, b * intensity,
                                           std::clamp(0.55F + intensity * 0.42F, 0.0F, 1.0F), 1.2F));
        }
    }

    const std::size_t rings = scope_rings(scope);
    for (std::size_t ring = 0U; ring < rings; ++ring) {
        const float ring_radius = (0.105F + radius_norm * 0.145F) *
                                  (0.65F + 0.22F * static_cast<float>(ring)) * scope_scale;
        const std::size_t count = 96U;
        for (std::size_t index = 0U; index < count; ++index) {
            const float theta = static_cast<float>(index) / static_cast<float>(count) * 2.0F * kPi;
            const math::Vec3 offset = right * (std::cos(theta) * ring_radius) +
                                      up * (std::sin(theta) * ring_radius);
            const float alpha = std::clamp((0.34F + intensity * 0.36F) * pulse, 0.0F, 0.95F);
            points.push_back(preview_point(center + offset, 0.0048F,
                                           r * 0.92F, g * 0.92F, b * 0.92F, alpha, 0.92F));
        }
    }

    const std::size_t rays = 8U;
    const float ray_length = 0.10F + radius_norm * 0.12F;
    for (std::size_t ray = 0U; ray < rays; ++ray) {
        const float theta = static_cast<float>(ray) / static_cast<float>(rays) * 2.0F * kPi;
        const math::Vec3 direction = right * std::cos(theta) + up * std::sin(theta);
        for (std::size_t step = 0U; step < 18U; ++step) {
            const float t = static_cast<float>(step) / 17.0F;
            points.push_back(preview_point(center + direction * (orb_radius + t * ray_length),
                                           0.0042F, r, g, b,
                                           std::clamp((1.0F - t) * 0.62F * intensity, 0.05F, 0.82F), 0.82F));
        }
    }

    last_stats_ = {points.size(), effective, radius_norm};
    return points;
}

}  // namespace signalcloud::ui
