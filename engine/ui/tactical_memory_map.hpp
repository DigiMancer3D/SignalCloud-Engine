#pragma once

#include "engine/math/mat4.hpp"
#include "engine/math/vec.hpp"
#include "engine/render/point_types.hpp"

#include <compare>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace signalcloud::combat { class CombatSystem; }
namespace signalcloud::economy { class EconomySystem; }
namespace signalcloud::world { class LiminalLevel; }

namespace signalcloud::ui {

struct TacticalMapStats {
    std::size_t visited_rooms{0};
    std::size_t scanned_rooms{0};
    std::size_t remembered_connections{0};
    std::size_t topology_nodes{0};
    std::size_t threshold_slots{0};
    std::size_t logical_levels{0};
    std::size_t static_points{0};
    std::size_t submitted_points{0};
    std::size_t static_rebuilds{0};
    std::size_t memory_loads{0};
    std::size_t memory_saves{0};
};

struct AtlasNodeSnapshot {
    int grid_x{0};
    int grid_z{0};
    int logical_level{0};
    int rotation_steps{0};
    std::size_t threshold_slots{0};
    bool visited{false};
    bool scanned{false};
};

class TacticalMemoryMap {
public:
    void set_storage_root(std::filesystem::path root);
    void reset(const world::LiminalLevel& level, std::string_view starting_zone);
    bool observe_zone(const world::LiminalLevel& level, std::string_view zone);
    bool observe_scan(const world::LiminalLevel& level, std::string_view active_zone);

    [[nodiscard]] std::vector<render::PointGpu> build_points(
        const world::LiminalLevel& level,
        math::Vec3 player_position,
        math::Vec3 player_forward,
        std::string_view current_zone,
        const combat::CombatSystem& combat,
        const economy::EconomySystem& economy,
        float time_seconds);

    [[nodiscard]] math::Mat4 view_projection(float aspect,
                                              const world::LiminalLevel& level) const noexcept;
    [[nodiscard]] bool knows_zone(std::string_view zone) const;
    [[nodiscard]] bool visited_zone(std::string_view zone) const;
    [[nodiscard]] std::optional<AtlasNodeSnapshot> node_snapshot(std::string_view zone) const;
    [[nodiscard]] std::size_t threshold_count(std::string_view zone) const;
    [[nodiscard]] int facing_side(std::string_view zone, math::Vec3 world_forward) const noexcept;
    [[nodiscard]] const std::filesystem::path& memory_path() const noexcept { return memory_path_; }
    [[nodiscard]] const TacticalMapStats& stats() const noexcept { return stats_; }
    [[nodiscard]] const char* mode_label() const noexcept {
        return "JAM TOPOLOGY ATLAS";
    }

private:
    enum class ThresholdKind : std::uint8_t {
        door,
        window,
        drop,
        passage,
        hole,
        glass,
    };

    struct LogicalCoord {
        int x{0};
        int z{0};
        int level{0};
        auto operator<=>(const LogicalCoord&) const = default;
    };

    struct AtlasNode {
        LogicalCoord coord{};
        int rotation_steps{0};
        std::vector<std::size_t> thresholds;
    };

    struct RawThreshold {
        std::string zone_a;
        std::string zone_b;
        ThresholdKind kind{ThresholdKind::door};
        math::Vec3 center_a{};
        math::Vec3 center_b{};
        bool has_center_a{false};
        bool has_center_b{false};
        bool bidirectional{true};
        int level_delta_a_to_b{0};
    };

    struct AtlasThreshold {
        std::string zone_a;
        std::string zone_b;
        ThresholdKind kind{ThresholdKind::door};
        math::Vec3 center_a{};
        math::Vec3 center_b{};
        bool has_center_a{false};
        bool has_center_b{false};
        bool bidirectional{true};
        int side_a{0};
        int side_b{4};
        std::size_t slot_a{0};
        std::size_t slot_b{0};
        std::size_t slots_on_side_a{1};
        std::size_t slots_on_side_b{1};
    };

    using ConnectionKey = std::pair<std::string, std::string>;

    [[nodiscard]] static ConnectionKey connection_key(std::string_view a,
                                                       std::string_view b);
    void remember_connections_for(const world::LiminalLevel& level,
                                  std::string_view zone);
    void rebuild_topology(const world::LiminalLevel& level);
    void rebuild_static_points(const world::LiminalLevel& level);
    void rebuild_if_dirty(const world::LiminalLevel& level);

    [[nodiscard]] std::vector<RawThreshold> collect_raw_thresholds(
        const world::LiminalLevel& level) const;
    [[nodiscard]] int physical_side(const world::LiminalLevel& level,
                                    std::string_view zone,
                                    math::Vec3 threshold_center,
                                    bool has_center,
                                    int fallback_side) const noexcept;
    [[nodiscard]] LogicalCoord find_open_coord(const AtlasNode& source,
                                               int map_side,
                                               int target_level,
                                               std::size_t branch_ordinal) const;
    [[nodiscard]] bool coord_occupied(const LogicalCoord& coord,
                                      std::string_view except_zone = {}) const;
    [[nodiscard]] math::Vec3 node_center(std::string_view zone) const noexcept;
    [[nodiscard]] math::Vec3 transform_into_node(const world::LiminalLevel& level,
                                                 std::string_view zone,
                                                 math::Vec3 world_position,
                                                 float inset_scale = 4.2F) const noexcept;

    void configure_memory_path(const world::LiminalLevel& level);
    bool load_memory(const world::LiminalLevel& level);
    bool save_memory(const world::LiminalLevel& level);

    std::set<std::string> visited_zones_;
    std::set<std::string> scanned_zones_;
    std::set<ConnectionKey> remembered_connections_;
    std::map<std::string, AtlasNode> nodes_;
    std::vector<AtlasThreshold> thresholds_;
    std::vector<render::PointGpu> static_points_;
    TacticalMapStats stats_{};
    std::filesystem::path storage_root_{};
    std::filesystem::path memory_path_{};
    std::string starting_zone_;
    bool dirty_{true};
    bool topology_dirty_{true};
    bool memory_dirty_{false};
};

}  // namespace signalcloud::ui
