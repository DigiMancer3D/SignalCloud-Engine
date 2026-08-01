#pragma once

#include "engine/items/tupd_runtime.hpp"
#include "engine/ui/ar_interface.hpp"

#include <cstddef>
#include <string_view>
#include <vector>

namespace signalcloud::ui {

enum class TupdGhostInspectionMode {
    result,
    interfaces,
    sockets,
    penalties,
};

enum class TupdGhostPlacementMode {
    camera_overlay,
    world_stage,
};

struct TupdGhostPlacement {
    TupdGhostPlacementMode mode{TupdGhostPlacementMode::camera_overlay};
    math::Vec3 world_center{0.0F, 1.15F, 0.0F};
    math::Vec3 world_forward{0.0F, 0.0F, -1.0F};
    math::Vec3 world_right{1.0F, 0.0F, 0.0F};
};

[[nodiscard]] std::string_view tupd_ghost_inspection_name(TupdGhostInspectionMode mode) noexcept;
[[nodiscard]] TupdGhostInspectionMode parse_tupd_ghost_inspection_mode(std::string_view value) noexcept;
[[nodiscard]] TupdGhostInspectionMode next_tupd_ghost_inspection_mode(TupdGhostInspectionMode mode) noexcept;

struct TupdGhostPreviewStats {
    std::size_t generated_points{0U};
    std::size_t body_points{0U};
    std::size_t connector_points{0U};
    bool valid_preview{false};
    bool forced_preview{false};
    bool committed_result{false};
    bool equipped_result{false};
    bool spawned_result{false};
    bool tested_result{false};
    bool broken_result{false};
    bool exploded{false};
    TupdGhostInspectionMode inspection_mode{TupdGhostInspectionMode::result};
};

class TupdGhostPreview {
public:
    [[nodiscard]] std::vector<render::PointGpu> build_points(
        const items::TupdRecipe& recipe,
        const items::TupdPreview& preview,
        float time_seconds,
        const ArPose& pose,
        const items::TupdResultInstance* instance = nullptr,
        const items::TupdInstanceTest* test = nullptr,
        TupdGhostInspectionMode inspection_mode = TupdGhostInspectionMode::result,
        bool exploded = false,
        TupdGhostPlacement placement = {}) const;

    [[nodiscard]] TupdGhostPreviewStats stats() const noexcept { return last_stats_; }

private:
    mutable TupdGhostPreviewStats last_stats_{};
};

}  // namespace signalcloud::ui
