#pragma once

#include "engine/ui/ar_interface.hpp"
#include "engine/ui/scui_native_runtime.hpp"

#include <cstddef>
#include <vector>

namespace signalcloud::ui {

struct ScuiLightPreviewStats {
    std::size_t generated_points{0};
    float effective_illuminosity{0.0F};
    float normalized_radius{0.0F};
};

class ScuiLightPreview {
public:
    [[nodiscard]] std::vector<render::PointGpu> build_points(
        const ScuiNativeRuntime& runtime, float time_seconds, const ArPose& pose) const;
    [[nodiscard]] ScuiLightPreviewStats stats() const noexcept { return last_stats_; }

private:
    mutable ScuiLightPreviewStats last_stats_{};
};

}  // namespace signalcloud::ui
