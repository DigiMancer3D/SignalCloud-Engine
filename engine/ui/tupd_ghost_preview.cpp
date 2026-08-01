#include "engine/ui/tupd_ghost_preview.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>

namespace signalcloud::ui {
namespace {

constexpr float kPi = 3.14159265358979323846F;

render::PointGpu make_point(math::Vec3 position, float radius,
                            float r, float g, float b, float a,
                            float density = 1.0F) noexcept {
    return {{position.x, position.y, position.z}, radius,
            {r, g, b, a}, {0.0F, 1.0F, 0.0F}, density};
}

void append_line(std::vector<render::PointGpu>& points,
                 math::Vec3 a, math::Vec3 b, std::size_t count,
                 float radius, float r, float g, float blue, float alpha,
                 float density = 1.0F) {
    if (count < 2U) count = 2U;
    for (std::size_t index = 0U; index < count; ++index) {
        const float t = static_cast<float>(index) / static_cast<float>(count - 1U);
        points.push_back(make_point(a + (b - a) * t, radius, r, g, blue, alpha, density));
    }
}

void append_box(std::vector<render::PointGpu>& points,
                math::Vec3 center, math::Vec3 half,
                const math::Vec3& right, const math::Vec3& up, const math::Vec3& forward,
                float r, float g, float b, float alpha,
                std::size_t& body_points) {
    const std::array<math::Vec3, 8U> corners{
        center - right * half.x - up * half.y - forward * half.z,
        center + right * half.x - up * half.y - forward * half.z,
        center - right * half.x + up * half.y - forward * half.z,
        center + right * half.x + up * half.y - forward * half.z,
        center - right * half.x - up * half.y + forward * half.z,
        center + right * half.x - up * half.y + forward * half.z,
        center - right * half.x + up * half.y + forward * half.z,
        center + right * half.x + up * half.y + forward * half.z,
    };
    const std::array<std::array<std::size_t, 2U>, 12U> edges{{
        {{0U, 1U}}, {{0U, 2U}}, {{1U, 3U}}, {{2U, 3U}},
        {{4U, 5U}}, {{4U, 6U}}, {{5U, 7U}}, {{6U, 7U}},
        {{0U, 4U}}, {{1U, 5U}}, {{2U, 6U}}, {{3U, 7U}},
    }};
    const std::size_t before = points.size();
    for (const auto& edge : edges) {
        append_line(points, corners[edge[0]], corners[edge[1]], 18U,
                    0.0044F, r, g, b, alpha, 1.15F);
    }
    body_points += points.size() - before;
}

void append_weapon(std::vector<render::PointGpu>& points,
                   math::Vec3 center,
                   const math::Vec3& right, const math::Vec3& up, const math::Vec3& forward,
                   float r, float g, float b, float alpha,
                   std::size_t& body_points) {
    const std::size_t before = points.size();
    append_box(points, center + right * 0.02F, {0.23F, 0.07F, 0.06F},
               right, up, forward, r, g, b, alpha, body_points);
    append_box(points, center - up * 0.15F - right * 0.05F, {0.06F, 0.13F, 0.055F},
               right, up, forward, r, g, b, alpha, body_points);
    append_line(points, center + right * 0.23F, center + right * 0.44F,
                20U, 0.0048F, r, g, b, alpha, 1.2F);
    body_points += points.size() - before;
}

void append_barrier(std::vector<render::PointGpu>& points,
                    math::Vec3 center,
                    const math::Vec3& right, const math::Vec3& up, const math::Vec3& forward,
                    float r, float g, float b, float alpha,
                    std::size_t& body_points) {
    append_box(points, center, {0.38F, 0.27F, 0.045F}, right, up, forward,
               r, g, b, alpha, body_points);
    for (int stripe = -2; stripe <= 2; ++stripe) {
        const float x = static_cast<float>(stripe) * 0.14F;
        append_line(points, center + right * x - up * 0.25F,
                    center + right * (x + 0.18F) + up * 0.25F,
                    22U, 0.0038F, r, g, b, alpha * 0.75F, 1.0F);
    }
}

}  // namespace

std::string_view tupd_ghost_inspection_name(TupdGhostInspectionMode mode) noexcept {
    switch (mode) {
        case TupdGhostInspectionMode::result: return "RESULT";
        case TupdGhostInspectionMode::interfaces: return "INTERFACES";
        case TupdGhostInspectionMode::sockets: return "SOCKETS";
        case TupdGhostInspectionMode::penalties: return "PENALTIES";
    }
    return "RESULT";
}

TupdGhostInspectionMode parse_tupd_ghost_inspection_mode(std::string_view value) noexcept {
    if (value == "interfaces" || value == "INTERFACES") return TupdGhostInspectionMode::interfaces;
    if (value == "sockets" || value == "SOCKETS") return TupdGhostInspectionMode::sockets;
    if (value == "penalties" || value == "PENALTIES") return TupdGhostInspectionMode::penalties;
    return TupdGhostInspectionMode::result;
}

TupdGhostInspectionMode next_tupd_ghost_inspection_mode(TupdGhostInspectionMode mode) noexcept {
    switch (mode) {
        case TupdGhostInspectionMode::result: return TupdGhostInspectionMode::interfaces;
        case TupdGhostInspectionMode::interfaces: return TupdGhostInspectionMode::sockets;
        case TupdGhostInspectionMode::sockets: return TupdGhostInspectionMode::penalties;
        case TupdGhostInspectionMode::penalties: return TupdGhostInspectionMode::result;
    }
    return TupdGhostInspectionMode::result;
}

std::vector<render::PointGpu> TupdGhostPreview::build_points(
    const items::TupdRecipe& recipe,
    const items::TupdPreview& preview,
    float time_seconds,
    const ArPose& pose,
    const items::TupdResultInstance* instance,
    const items::TupdInstanceTest* test,
    TupdGhostInspectionMode inspection_mode,
    bool exploded,
    TupdGhostPlacement placement) const {
    std::vector<render::PointGpu> points;
    if (recipe.recipe_id.empty() || preview.result_id.empty()) {
        last_stats_ = {};
        return points;
    }

    const bool world_stage = placement.mode == TupdGhostPlacementMode::world_stage;
    const auto forward = math::normalize_or(
        world_stage ? placement.world_forward : pose.forward, {0.0F, 0.0F, -1.0F});
    const auto right = math::normalize_or(
        world_stage ? placement.world_right : pose.right, {1.0F, 0.0F, 0.0F});
    const auto up = math::normalize_or(math::cross(right, forward), {0.0F, 1.0F, 0.0F});
    const bool committed = instance != nullptr && !instance->instance_id.empty();
    const bool active = committed && (instance->equipped || instance->spawned);
    const bool broken = committed && instance->broken;
    const float pulse_rate = active ? 2.0F : 4.0F;
    const float pulse = 0.88F + 0.12F * std::sin(time_seconds * pulse_rate);
    const float alpha = broken ? 0.94F : (active ? 0.92F * pulse : (committed ? 0.84F * pulse : (preview.valid ? 0.78F * pulse : 0.48F)));
    float r = preview.valid ? 0.24F : 1.0F;
    float g = preview.valid ? 0.90F : 0.18F;
    float b = preview.valid ? 0.96F : 0.12F;
    if (preview.forced) {
        r = 1.0F;
        g = 0.58F;
        b = 0.12F;
    }
    if (active) {
        r = 0.38F;
        g = 1.0F;
        b = 0.52F;
    }
    if (broken) {
        r = 1.0F;
        g = 0.16F;
        b = 0.10F;
    }
    if (!broken && inspection_mode == TupdGhostInspectionMode::interfaces) {
        r = 0.24F; g = 1.0F; b = 0.58F;
    } else if (!broken && inspection_mode == TupdGhostInspectionMode::sockets) {
        r = 0.72F; g = 0.42F; b = 1.0F;
    } else if (!broken && inspection_mode == TupdGhostInspectionMode::penalties) {
        const float penalty = std::clamp((100.0F - preview.stability_percent) / 100.0F, 0.0F, 1.0F);
        r = 0.80F + 0.20F * penalty;
        g = 0.74F - 0.58F * penalty;
        b = 0.14F;
    }

    // Camera-overlay placement remains the in-game SCUI default. The native
    // inspection stage can instead anchor the result to a fixed world point so
    // orbiting and zooming reveal real depth rather than a screen-space sticker.
    math::Vec3 center = world_stage
        ? placement.world_center
        : pose.camera_position + forward * 1.55F + right * 0.58F - up * 0.12F;
    if (broken) center = center - up * 0.16F;
    if (exploded) center = center - right * 0.16F;
    if (test != nullptr && test->accepted && test->action == items::TupdTestAction::primary) {
        center = center + forward * (0.05F * std::sin(time_seconds * 12.0F));
    }
    std::size_t body_points = 0U;
    if (recipe.preview_shape == "weapon" || recipe.preview_shape == "tool") {
        append_weapon(points, center, right, up, forward, r, g, b, alpha, body_points);
    } else if (recipe.preview_shape == "barrier") {
        append_barrier(points, center, right, up, forward, r, g, b, alpha, body_points);
    } else {
        append_box(points, center, {0.28F, 0.20F, 0.14F}, right, up, forward,
                   r, g, b, alpha, body_points);
    }

    const auto graph = items::build_assembly_graph(recipe);
    std::size_t connector_points = 0U;
    const std::size_t node_count = std::max<std::size_t>(1U, graph.nodes.size());
    for (std::size_t index = 0U; index < graph.nodes.size(); ++index) {
        const float angle = static_cast<float>(index) / static_cast<float>(node_count) * 2.0F * kPi;
        const float horizontal_radius = exploded ? 0.72F : 0.43F;
        const float vertical_radius = exploded ? 0.50F : 0.31F;
        const math::Vec3 node = center + right * (std::cos(angle) * horizontal_radius) +
                                up * (std::sin(angle) * vertical_radius) +
                                forward * (exploded ? (static_cast<float>(index % 3U) - 1.0F) * 0.08F : 0.0F);
        const std::size_t before = points.size();
        float node_r = r;
        float node_g = g;
        float node_b = b;
        if (inspection_mode == TupdGhostInspectionMode::interfaces) {
            node_r = 0.18F; node_g = 1.0F; node_b = 0.52F;
        } else if (inspection_mode == TupdGhostInspectionMode::sockets) {
            node_r = 0.72F; node_g = 0.44F; node_b = 1.0F;
        } else if (inspection_mode == TupdGhostInspectionMode::penalties && index < recipe.forced_connections.size()) {
            node_r = 1.0F; node_g = 0.20F; node_b = 0.08F;
        }
        append_line(points, center, node, exploded ? 24U : 16U, 0.0035F,
                    node_r, node_g, node_b, alpha * (exploded ? 0.72F : 0.52F), 0.8F);
        for (std::size_t ring = 0U; ring < 28U; ++ring) {
            const float theta = static_cast<float>(ring) / 28.0F * 2.0F * kPi;
            points.push_back(make_point(node + right * (std::cos(theta) * 0.025F) +
                                              up * (std::sin(theta) * 0.025F),
                                        0.0040F, node_r, node_g, node_b, alpha, 1.0F));
        }
        connector_points += points.size() - before;
    }

    if (exploded) {
        append_line(points, center - right * 0.64F, center + right * 0.64F, 52U,
                    0.0028F, 0.22F, 0.74F, 0.82F, 0.42F, 0.65F);
        append_line(points, center - up * 0.45F, center + up * 0.45F, 40U,
                    0.0028F, 0.22F, 0.74F, 0.82F, 0.42F, 0.65F);
    }

    const float stability = std::clamp(preview.stability_percent / 100.0F, 0.0F, 1.0F);
    const math::Vec3 meter_start = center - right * 0.34F - up * 0.38F;
    append_line(points, meter_start, meter_start + right * 0.68F,
                50U, 0.0036F, 0.14F, 0.18F, 0.22F, 0.75F, 1.0F);
    append_line(points, meter_start, meter_start + right * (0.68F * stability),
                std::max<std::size_t>(2U, static_cast<std::size_t>(50.0F * stability)),
                0.0048F, r, g, b, 0.95F, 1.25F);

    last_stats_ = {points.size(), body_points, connector_points,
                   preview.valid, preview.forced, committed,
                   committed && instance->equipped, committed && instance->spawned,
                   test != nullptr && test->accepted, broken, exploded, inspection_mode};
    return points;
}

}  // namespace signalcloud::ui
