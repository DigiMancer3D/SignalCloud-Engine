#include "engine/render/point_lab.hpp"

#include <algorithm>

namespace signalcloud::render {

bool PointLabState::select_preset(std::size_t index) noexcept {
    if (index >= kPointLabPresets.size() || index == preset_index_) return false;
    preset_index_ = index;
    return true;
}

bool PointLabState::select_point_count(std::uint32_t points) noexcept {
    for (std::size_t i = 0; i < kPointLabPresets.size(); ++i) {
        if (kPointLabPresets[i].points == points) return select_preset(i);
    }
    return false;
}

void PointLabState::adjust_point_scale(float delta) noexcept {
    point_scale_ = std::clamp(point_scale_ + delta, 0.35F, 3.0F);
}

void PointLabState::adjust_density_scale(float delta) noexcept {
    density_scale_ = std::clamp(density_scale_ + delta, 0.20F, 2.0F);
}

}  // namespace signalcloud::render
