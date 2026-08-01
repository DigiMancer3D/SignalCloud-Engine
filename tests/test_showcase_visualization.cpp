#include "engine/physics/showcase_visualization.hpp"

#include <cassert>
#include <cmath>
#include <iostream>
#include <vector>

int main() {
    using signalcloud::render::PointGpu;
    std::vector<PointGpu> source;
    for (int y = 0; y < 10; ++y) {
        for (int x = 0; x < 20; ++x) {
            source.push_back({{static_cast<float>(x) * 0.1F - 0.95F,
                               static_cast<float>(y) * 0.1F,
                               0.15F * std::sin(static_cast<float>(x))},
                              1.4F, {0.4F, 0.6F, 0.8F, 1.0F},
                              {0.0F, 1.0F, 0.0F},
                              static_cast<float>((x + y) % 5)});
        }
    }
    const auto bounds = signalcloud::physics::showcase_bounds(source);
    assert(bounds.valid);
    assert(bounds.maximum.x > bounds.minimum.x);
    assert(bounds.maximum.y > bounds.minimum.y);
    assert(signalcloud::physics::showcase_lod_count(200U, 0.25F) == 50U);
    assert(signalcloud::physics::showcase_lod_count(0U, 0.25F) == 0U);

    signalcloud::physics::PhysicsProfile profile;
    profile.shape = "box";
    profile.collision_half_extents = bounds.half_extents;
    signalcloud::physics::ShowcaseState state;
    state.position = {0.0F, bounds.half_extents.y, 0.0F};
    signalcloud::physics::ShowcaseVisualizationOptions options;
    options.lod_fraction = 0.25F;
    options.collision_outline = true;
    options.view_mode = signalcloud::physics::ShowcaseViewMode::density;
    const auto frame = signalcloud::physics::build_showcase_frame_points(
        source, bounds, profile, state, options, 1.25F);
    assert(frame.size() > 50U); // stage + LOD + collision
    for (const auto& point : frame) {
        (void)point;
        assert(std::isfinite(point.position[0]));
        assert(std::isfinite(point.position[1]));
        assert(std::isfinite(point.position[2]));
        assert(std::isfinite(point.radius));
    }

    options.actor_preview = true;
    options.view_mode = signalcloud::physics::ShowcaseViewMode::light;
    const auto actor_frame = signalcloud::physics::build_showcase_frame_points(
        source, bounds, profile, state, options, 2.50F);
    assert(actor_frame.size() >= frame.size());
    assert(signalcloud::physics::parse_showcase_view_mode("material") ==
           signalcloud::physics::ShowcaseViewMode::material);
    assert(signalcloud::physics::showcase_view_mode_name(
               signalcloud::physics::ShowcaseViewMode::light) == "light");


    // A7a2r1: object and collision share the same moving/rotating transform.
    signalcloud::physics::ShowcaseVisualizationOptions transform_options;
    transform_options.collision_outline = false;
    std::vector<PointGpu> one_source{{{1.0F, 0.0F, 0.0F}, 1.7F, {0.7F, 0.8F, 0.9F, 1.0F},
                                      {0.0F, 1.0F, 0.0F}, 1.0F}};
    const auto one_bounds = signalcloud::physics::showcase_bounds(one_source);
    signalcloud::physics::ShowcaseState moved_state;
    moved_state.position = {3.0F, 2.0F, -1.0F};
    moved_state.yaw_radians = 1.57079632679F;
    const auto moved_frame = signalcloud::physics::build_showcase_frame_points(
        one_source, one_bounds, profile, moved_state, transform_options, 0.0F);
    assert(!moved_frame.empty());
    const PointGpu* moved_object = nullptr;
    for (const auto& candidate : moved_frame) {
        if (std::abs(candidate.color[0] - 0.7F) < 0.001F &&
            std::abs(candidate.color[1] - 0.8F) < 0.001F) {
            moved_object = &candidate;
            break;
        }
    }
    (void)moved_object;
    assert(moved_object != nullptr);
    assert(std::abs(moved_object->position[0] - 3.0F) < 0.001F);
    assert(std::abs(moved_object->position[1] - 2.0F) < 0.001F);
    assert(std::abs(moved_object->position[2] + 1.0F) < 0.001F);
    assert(moved_object->radius < 0.05F);

    signalcloud::physics::ShowcaseBounds invalid_bounds;
    transform_options.collision_outline = true;
    signalcloud::physics::ShowcaseState collision_a;
    collision_a.position = {0.0F, 1.0F, 0.0F};
    signalcloud::physics::ShowcaseState collision_b = collision_a;
    collision_b.position.x = 2.5F;
    collision_b.yaw_radians = 0.8F;
    const auto collision_frame_a = signalcloud::physics::build_showcase_frame_points(
        {}, invalid_bounds, profile, collision_a, transform_options, 0.0F);
    const auto collision_frame_b = signalcloud::physics::build_showcase_frame_points(
        {}, invalid_bounds, profile, collision_b, transform_options, 0.0F);
    assert(collision_frame_a.size() == collision_frame_b.size());
    assert(std::abs(collision_frame_b.back().position[0] - collision_frame_a.back().position[0]) > 1.0F);

    std::cout << "A7a2r2 Showcase visualization: shared motion, collision, LOD, actor PASS\n";
    return 0;
}
