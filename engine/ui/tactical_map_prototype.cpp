#include "engine/ui/tactical_map_prototype.hpp"

#include "engine/world/liminal_level.hpp"

#include <algorithm>

namespace signalcloud::legacy {

math::Mat4 TacticalMapPrototype::view_projection(float aspect) const noexcept {
    const float half_height = 24.0F;
    const float half_width = half_height * (aspect > 0.1F ? aspect : 1.0F);
    const auto projection = math::orthographic(-half_width, half_width,
                                                -half_height, half_height,
                                                -120.0F, 120.0F);
    const auto view = math::look_at({10.0F, 52.0F, -10.0F},
                                    {10.0F, 0.0F, -10.0F},
                                    {0.0F, 0.0F, -1.0F});
    return projection * view;
}

math::Mat4 TacticalMapPrototype::view_projection(float aspect, const world::LiminalLevel& level) const noexcept {
    const auto bounds = level.bounds();
    const float center_x = (bounds.min_x + bounds.max_x) * 0.5F;
    const float center_z = (bounds.min_z + bounds.max_z) * 0.5F;
    const float span_x = std::max(20.0F, bounds.max_x - bounds.min_x);
    const float span_z = std::max(20.0F, bounds.max_z - bounds.min_z);
    const float safe_aspect = aspect > 0.1F ? aspect : 1.0F;
    const float half_height = std::max(span_z * 0.56F, span_x * 0.56F / safe_aspect);
    const float half_width = half_height * safe_aspect;
    const auto projection = math::orthographic(-half_width, half_width,
                                                -half_height, half_height,
                                                -1000.0F, 1000.0F);
    const auto view = math::look_at({center_x, 620.0F, center_z},
                                    {center_x, 0.0F, center_z},
                                    {0.0F, 0.0F, -1.0F});
    return projection * view;
}

}  // namespace signalcloud::legacy
