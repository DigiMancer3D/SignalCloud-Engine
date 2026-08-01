#pragma once

#include "engine/math/vec.hpp"
#include "engine/render/point_types.hpp"
#include "engine/scfont/scfont.hpp"

#include <cstddef>
#include <string_view>
#include <vector>

namespace signalcloud::ui {

struct ShowcaseInfoOverlayCamera {
    math::Vec3 eye{};
    math::Vec3 center{};
    float vertical_fov_radians{1.01229097F}; // 58 degrees
    float aspect{16.0F / 9.0F};
};

struct ShowcaseInfoOverlayStats {
    float scale{0.0F};
    float width{0.0F};
    float height{0.0F};
    std::size_t text_points{0U};
    std::size_t backplate_points{0U};
};

// Builds a stable, top-left, camera-relative point UI surface. The returned
// points are intended for PointRenderer::upload_viewmodel_points().
ShowcaseInfoOverlayStats append_showcase_info_overlay(
    std::vector<render::PointGpu>& output,
    const font::Font& font,
    std::string_view text,
    const ShowcaseInfoOverlayCamera& camera,
    std::size_t maximum_points = 14'000U);

}  // namespace signalcloud::ui
