#include "engine/ui/tactical_memory_map.hpp"

#include "engine/combat/combat_system.hpp"
#include "engine/economy/economy_system.hpp"
#include "engine/world/liminal_level.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <system_error>
#include <tuple>

namespace signalcloud::ui {
namespace {

constexpr float kMapY = 1.15F;
constexpr float kNodeRadius = 4.15F;
constexpr float kNodeSpacing = 8.4F;
constexpr float kInsetRadius = 2.72F;
constexpr std::size_t kStaticPointBudget = 16'000U;
constexpr float kPi = 3.14159265358979323846F;

struct SideVector {
    int x;
    int z;
};

// JAM-derived topology order: N, NE, E, SE, S, SW, W, NW.
constexpr std::array<SideVector, 8> kSideVectors{{
    {0, -1}, {1, -1}, {1, 0}, {1, 1},
    {0, 1}, {-1, 1}, {-1, 0}, {-1, -1},
}};

int normalize_side(int side) noexcept {
    side %= 8;
    return side < 0 ? side + 8 : side;
}

int opposite_side(int side) noexcept {
    return normalize_side(side + 4);
}

int diagonal_for_level(int side, int delta) noexcept {
    const int normalized = normalize_side(side);
    const bool east = normalized == 0 || normalized == 1 || normalized == 2 || normalized == 3;
    if (delta > 0) return east ? 1 : 7;
    if (delta < 0) return east ? 3 : 5;
    return normalized;
}

render::PointGpu point(math::Vec3 p, float radius,
                       float r, float g, float b, float a = 1.0F) {
    return {{p.x, p.y, p.z}, radius, {r, g, b, a}, {0.0F, 1.0F, 0.0F}, 1.0F};
}

void add_line(std::vector<render::PointGpu>& out,
              math::Vec3 a, math::Vec3 b, float spacing, float radius,
              float r, float g, float blue, float alpha = 1.0F) {
    if (out.size() >= kStaticPointBudget) return;
    const math::Vec3 delta = b - a;
    const float length = math::length(delta);
    const int steps = std::max(1, static_cast<int>(std::ceil(length / std::max(0.12F, spacing))));
    for (int i = 0; i <= steps && out.size() < kStaticPointBudget; ++i) {
        const float t = static_cast<float>(i) / static_cast<float>(steps);
        out.push_back(point(a + delta * t, radius, r, g, blue, alpha));
    }
}

void add_dashed_line(std::vector<render::PointGpu>& out,
                     math::Vec3 a, math::Vec3 b, float spacing, float radius,
                     float r, float g, float blue, float alpha = 1.0F) {
    if (out.size() >= kStaticPointBudget) return;
    const math::Vec3 delta = b - a;
    const float length = math::length(delta);
    const int steps = std::max(1, static_cast<int>(std::ceil(length / std::max(0.16F, spacing))));
    for (int i = 0; i <= steps && out.size() < kStaticPointBudget; ++i) {
        if ((i / 3) % 2 != 0) continue;
        const float t = static_cast<float>(i) / static_cast<float>(steps);
        out.push_back(point(a + delta * t, radius, r, g, blue, alpha));
    }
}

std::array<math::Vec3, 8> octagon(math::Vec3 center, float radius = kNodeRadius) {
    std::array<math::Vec3, 8> vertices{};
    for (int i = 0; i < 8; ++i) {
        const float angle = (-112.5F + static_cast<float>(i) * 45.0F) * kPi / 180.0F;
        vertices[static_cast<std::size_t>(i)] = center + math::Vec3{
            std::cos(angle) * radius, 0.0F, std::sin(angle) * radius};
    }
    return vertices;
}

math::Vec3 side_outward(int side) noexcept {
    const auto d = kSideVectors[static_cast<std::size_t>(normalize_side(side))];
    return math::normalize_or(math::Vec3{static_cast<float>(d.x), 0.0F,
                                        static_cast<float>(d.z)},
                              {0.0F, 0.0F, -1.0F});
}

math::Vec3 rotate_flat(math::Vec3 v, int steps) noexcept {
    const float angle = static_cast<float>(normalize_side(steps)) * 45.0F * kPi / 180.0F;
    const float c = std::cos(angle);
    const float s = std::sin(angle);
    return {v.x * c - v.z * s, 0.0F, v.x * s + v.z * c};
}

const world::WalkArea* find_area(const world::LiminalLevel& level,
                                 std::string_view zone) noexcept {
    for (const auto& area : level.areas()) {
        if (area.name == zone) return &area;
    }
    return nullptr;
}

bool overlaps(const world::WalkArea& area, const world::WaterRegion& water) noexcept {
    return area.min_x <= water.max_x && area.max_x >= water.min_x &&
           area.min_z <= water.max_z && area.max_z >= water.min_z;
}

void add_cross(std::vector<render::PointGpu>& out, math::Vec3 center,
               float size, float r, float g, float b) {
    add_line(out, center + math::Vec3{-size, 0.0F, 0.0F},
             center + math::Vec3{size, 0.0F, 0.0F}, 0.22F, 0.20F, r, g, b);
    add_line(out, center + math::Vec3{0.0F, 0.0F, -size},
             center + math::Vec3{0.0F, 0.0F, size}, 0.22F, 0.20F, r, g, b);
}

void add_diamond(std::vector<render::PointGpu>& out, math::Vec3 center,
                 float size, float r, float g, float b) {
    add_line(out, center + math::Vec3{0.0F, 0.0F, -size},
             center + math::Vec3{size, 0.0F, 0.0F}, 0.20F, 0.20F, r, g, b);
    add_line(out, center + math::Vec3{size, 0.0F, 0.0F},
             center + math::Vec3{0.0F, 0.0F, size}, 0.20F, 0.20F, r, g, b);
    add_line(out, center + math::Vec3{0.0F, 0.0F, size},
             center + math::Vec3{-size, 0.0F, 0.0F}, 0.20F, 0.20F, r, g, b);
    add_line(out, center + math::Vec3{-size, 0.0F, 0.0F},
             center + math::Vec3{0.0F, 0.0F, -size}, 0.20F, 0.20F, r, g, b);
}

void add_ring(std::vector<render::PointGpu>& out, math::Vec3 center,
              float radius, float r, float g, float b) {
    constexpr int steps = 20;
    for (int i = 0; i < steps && out.size() < kStaticPointBudget; ++i) {
        const float angle = static_cast<float>(i) * 2.0F * kPi / static_cast<float>(steps);
        out.push_back(point(center + math::Vec3{std::cos(angle) * radius, 0.0F,
                                                std::sin(angle) * radius},
                            0.20F, r, g, b));
    }
}

std::string hex64(std::uint64_t value) {
    std::ostringstream out;
    out << std::uppercase << std::hex << std::setw(16) << std::setfill('0') << value;
    return out.str();
}

}  // namespace

TacticalMemoryMap::ConnectionKey TacticalMemoryMap::connection_key(
    std::string_view a, std::string_view b) {
    if (a <= b) return {std::string(a), std::string(b)};
    return {std::string(b), std::string(a)};
}

void TacticalMemoryMap::set_storage_root(std::filesystem::path root) {
    storage_root_ = std::move(root);
}

void TacticalMemoryMap::configure_memory_path(const world::LiminalLevel& level) {
    if (storage_root_.empty()) {
        memory_path_.clear();
        return;
    }
    memory_path_ = storage_root_ /
        (hex64(level.seed()) + "_" + hex64(level.layout_signature()) + ".tmap");
}

void TacticalMemoryMap::reset(const world::LiminalLevel& level,
                              std::string_view starting_zone) {
    visited_zones_.clear();
    scanned_zones_.clear();
    remembered_connections_.clear();
    nodes_.clear();
    thresholds_.clear();
    static_points_.clear();
    stats_ = {};
    starting_zone_ = std::string(starting_zone);
    dirty_ = true;
    topology_dirty_ = true;
    memory_dirty_ = false;
    configure_memory_path(level);
    load_memory(level);
    observe_zone(level, starting_zone);
}

bool TacticalMemoryMap::knows_zone(std::string_view zone) const {
    return visited_zones_.contains(std::string(zone)) ||
           scanned_zones_.contains(std::string(zone));
}

bool TacticalMemoryMap::visited_zone(std::string_view zone) const {
    return visited_zones_.contains(std::string(zone));
}

std::optional<AtlasNodeSnapshot> TacticalMemoryMap::node_snapshot(
    std::string_view zone) const {
    const auto found = nodes_.find(std::string(zone));
    if (found == nodes_.end()) return std::nullopt;
    return AtlasNodeSnapshot{
        found->second.coord.x,
        found->second.coord.z,
        found->second.coord.level,
        found->second.rotation_steps,
        found->second.thresholds.size(),
        visited_zone(zone),
        scanned_zones_.contains(std::string(zone)),
    };
}

std::size_t TacticalMemoryMap::threshold_count(std::string_view zone) const {
    const auto found = nodes_.find(std::string(zone));
    return found == nodes_.end() ? 0U : found->second.thresholds.size();
}

void TacticalMemoryMap::remember_connections_for(const world::LiminalLevel& level,
                                                 std::string_view zone) {
    for (const auto& connection : level.connections()) {
        if (connection.zone_a == zone || connection.zone_b == zone) {
            const std::string_view other = connection.zone_a == zone
                ? std::string_view(connection.zone_b) : std::string_view(connection.zone_a);
            if (knows_zone(other)) remembered_connections_.insert(connection_key(zone, other));
        }
    }
    for (const auto& portal : level.portals()) {
        if ((portal.source_zone == zone && knows_zone(portal.destination_zone)) ||
            (portal.destination_zone == zone && knows_zone(portal.source_zone))) {
            remembered_connections_.insert(
                connection_key(portal.source_zone, portal.destination_zone));
        }
    }
}

bool TacticalMemoryMap::observe_zone(const world::LiminalLevel& level,
                                     std::string_view zone) {
    if (zone.empty()) return false;
    const std::string owned(zone);
    bool changed = visited_zones_.insert(owned).second;
    changed = scanned_zones_.erase(owned) > 0U || changed;
    remember_connections_for(level, zone);
    for (const auto& known : visited_zones_) remember_connections_for(level, known);
    if (changed) {
        dirty_ = true;
        topology_dirty_ = true;
        memory_dirty_ = true;
    }
    return changed;
}

bool TacticalMemoryMap::observe_scan(const world::LiminalLevel& level,
                                     std::string_view active_zone) {
    bool changed = false;
    auto remember_preview = [&](std::string_view destination) {
        if (destination.empty() || visited_zone(destination)) return;
        changed = scanned_zones_.insert(std::string(destination)).second || changed;
        remembered_connections_.insert(connection_key(active_zone, destination));
    };
    for (const auto& connection : level.connections()) {
        if (connection.zone_a == active_zone) remember_preview(connection.zone_b);
        else if (connection.zone_b == active_zone && connection.bidirectional) {
            remember_preview(connection.zone_a);
        }
    }
    for (const auto& portal : level.portals()) {
        if (portal.source_zone == active_zone) remember_preview(portal.destination_zone);
    }
    if (changed) {
        dirty_ = true;
        topology_dirty_ = true;
        memory_dirty_ = true;
    }
    return changed;
}

std::vector<TacticalMemoryMap::RawThreshold> TacticalMemoryMap::collect_raw_thresholds(
    const world::LiminalLevel& level) const {
    std::vector<RawThreshold> raw;
    raw.reserve(level.connections().size() + level.portals().size());

    for (const auto& connection : level.connections()) {
        ThresholdKind kind = ThresholdKind::door;
        switch (connection.kind) {
            case world::ConnectionKind::window: kind = ThresholdKind::window; break;
            case world::ConnectionKind::hole: kind = ThresholdKind::hole; break;
            case world::ConnectionKind::passage: kind = ThresholdKind::passage; break;
            case world::ConnectionKind::glass: kind = ThresholdKind::glass; break;
            case world::ConnectionKind::open_doorway:
            case world::ConnectionKind::framed_doorway: kind = ThresholdKind::door; break;
        }
        raw.push_back({connection.zone_a, connection.zone_b, kind,
                       connection.center, connection.center, true, true,
                       connection.bidirectional, 0});
    }

    for (const auto& portal : level.portals()) {
        ThresholdKind kind = ThresholdKind::door;
        if (portal.kind == world::PortalKind::window) kind = ThresholdKind::window;
        if (portal.kind == world::PortalKind::drop) kind = ThresholdKind::drop;

        bool merged = false;
        for (auto& existing : raw) {
            if (existing.kind != kind) continue;
            if (existing.zone_a == portal.destination_zone &&
                existing.zone_b == portal.source_zone && !existing.has_center_b) {
                existing.center_b = portal.center;
                existing.has_center_b = true;
                existing.bidirectional = true;
                merged = true;
                break;
            }
            if (existing.zone_a == portal.source_zone &&
                existing.zone_b == portal.destination_zone && !existing.has_center_a) {
                existing.center_a = portal.center;
                existing.has_center_a = true;
                merged = true;
                break;
            }
        }
        if (merged) continue;

        RawThreshold threshold{};
        threshold.zone_a = portal.source_zone;
        threshold.zone_b = portal.destination_zone;
        threshold.kind = kind;
        threshold.center_a = portal.center;
        threshold.has_center_a = true;
        threshold.bidirectional = false;
        threshold.level_delta_a_to_b = portal.kind == world::PortalKind::drop ? -1 : 0;
        raw.push_back(std::move(threshold));
    }

    std::sort(raw.begin(), raw.end(), [](const RawThreshold& lhs, const RawThreshold& rhs) {
        return std::tie(lhs.zone_a, lhs.zone_b, lhs.kind) <
               std::tie(rhs.zone_a, rhs.zone_b, rhs.kind);
    });
    return raw;
}

int TacticalMemoryMap::physical_side(const world::LiminalLevel& level,
                                     std::string_view zone,
                                     math::Vec3 threshold_center,
                                     bool has_center,
                                     int fallback_side) const noexcept {
    const auto* area = find_area(level, zone);
    if (area == nullptr || !has_center) return normalize_side(fallback_side);

    const std::array<float, 4> distances{{
        std::abs(threshold_center.z - area->min_z),
        std::abs(threshold_center.x - area->max_x),
        std::abs(threshold_center.z - area->max_z),
        std::abs(threshold_center.x - area->min_x),
    }};
    const auto best = static_cast<int>(std::distance(
        distances.begin(), std::min_element(distances.begin(), distances.end())));
    return best * 2;
}

bool TacticalMemoryMap::coord_occupied(const LogicalCoord& coord,
                                       std::string_view except_zone) const {
    for (const auto& [zone, node] : nodes_) {
        if (!except_zone.empty() && zone == except_zone) continue;
        if (node.coord == coord) return true;
    }
    return false;
}

TacticalMemoryMap::LogicalCoord TacticalMemoryMap::find_open_coord(
    const AtlasNode& source, int map_side, int target_level,
    std::size_t branch_ordinal) const {
    const auto direction = kSideVectors[static_cast<std::size_t>(normalize_side(map_side))];
    const SideVector perpendicular{-direction.z, direction.x};
    constexpr std::array<int, 9> offsets{{0, -1, 1, -2, 2, -3, 3, -4, 4}};

    for (int distance = 1; distance <= 6; ++distance) {
        for (std::size_t pass = 0; pass < offsets.size(); ++pass) {
            const std::size_t index = (pass + branch_ordinal) % offsets.size();
            const int lateral = offsets[index];
            LogicalCoord candidate{
                source.coord.x + direction.x * distance + perpendicular.x * lateral,
                source.coord.z + direction.z * distance + perpendicular.z * lateral,
                target_level,
            };
            const bool diagonal = direction.x != 0 && direction.z != 0;
            if (diagonal && (candidate.x == source.coord.x ||
                             candidate.z == source.coord.z)) {
                continue;
            }
            if (!coord_occupied(candidate)) return candidate;
        }
    }
    return {source.coord.x + direction.x * 7,
            source.coord.z + direction.z * 7,
            target_level};
}

void TacticalMemoryMap::rebuild_topology(const world::LiminalLevel& level) {
    const auto raw = collect_raw_thresholds(level);

    for (auto& [zone, node] : nodes_) node.thresholds.clear();
    thresholds_.clear();

    if (!knows_zone(starting_zone_)) visited_zones_.insert(starting_zone_);
    if (!nodes_.contains(starting_zone_)) {
        nodes_.emplace(starting_zone_, AtlasNode{{0, 0, 0}, 0, {}});
    }

    auto place_target = [&](const RawThreshold& edge, bool from_a) {
        const std::string& source_zone = from_a ? edge.zone_a : edge.zone_b;
        const std::string& target_zone = from_a ? edge.zone_b : edge.zone_a;
        auto source_it = nodes_.find(source_zone);
        if (source_it == nodes_.end() || nodes_.contains(target_zone)) return false;

        const int signed_delta = from_a ? edge.level_delta_a_to_b : -edge.level_delta_a_to_b;
        const math::Vec3 source_center = from_a ? edge.center_a : edge.center_b;
        const math::Vec3 target_center = from_a ? edge.center_b : edge.center_a;
        const bool has_source_center = from_a ? edge.has_center_a : edge.has_center_b;
        const bool has_target_center = from_a ? edge.has_center_b : edge.has_center_a;

        int source_physical = physical_side(level, source_zone, source_center,
                                            has_source_center, 0);
        int map_side = normalize_side(source_physical + source_it->second.rotation_steps);
        if (signed_delta != 0) map_side = diagonal_for_level(map_side, signed_delta);

        const int target_physical = physical_side(
            level, target_zone, target_center, has_target_center,
            opposite_side(source_physical));
        const int target_rotation = normalize_side(opposite_side(map_side) - target_physical);
        const int target_level = source_it->second.coord.level + signed_delta;

        const LogicalCoord coord = find_open_coord(
            source_it->second, map_side, target_level, 0U);
        nodes_.emplace(target_zone, AtlasNode{coord, target_rotation, {}});
        return true;
    };

    bool progress = true;
    while (progress) {
        progress = false;
        for (const auto& edge : raw) {
            if (!knows_zone(edge.zone_a) || !knows_zone(edge.zone_b)) continue;
            if (place_target(edge, true)) progress = true;
            if (place_target(edge, false)) progress = true;
        }
    }

    int orphan_row = 0;
    for (const auto& zone : visited_zones_) {
        if (nodes_.contains(zone)) continue;
        while (coord_occupied({orphan_row, 4, 0})) ++orphan_row;
        nodes_.emplace(zone, AtlasNode{{orphan_row++, 4, 0}, 0, {}});
    }
    for (const auto& zone : scanned_zones_) {
        if (nodes_.contains(zone)) continue;
        while (coord_occupied({orphan_row, 4, 0})) ++orphan_row;
        nodes_.emplace(zone, AtlasNode{{orphan_row++, 4, 0}, 0, {}});
    }

    for (const auto& edge : raw) {
        if (!knows_zone(edge.zone_a) || !knows_zone(edge.zone_b)) continue;
        const auto a_it = nodes_.find(edge.zone_a);
        const auto b_it = nodes_.find(edge.zone_b);
        if (a_it == nodes_.end() || b_it == nodes_.end()) continue;

        int side_a = normalize_side(physical_side(level, edge.zone_a, edge.center_a,
                                                  edge.has_center_a, 0) +
                                    a_it->second.rotation_steps);
        int side_b = normalize_side(physical_side(level, edge.zone_b, edge.center_b,
                                                  edge.has_center_b,
                                                  opposite_side(side_a)) +
                                    b_it->second.rotation_steps);
        if (edge.level_delta_a_to_b != 0) {
            side_a = diagonal_for_level(side_a, edge.level_delta_a_to_b);
            side_b = opposite_side(side_a);
        }

        thresholds_.push_back({edge.zone_a, edge.zone_b, edge.kind,
                               edge.center_a, edge.center_b,
                               edge.has_center_a, edge.has_center_b,
                               edge.bidirectional, side_a, side_b,
                               0U, 0U, 1U, 1U});
    }

    std::map<std::pair<std::string, int>, std::vector<std::size_t>> side_groups;
    for (std::size_t index = 0; index < thresholds_.size(); ++index) {
        const auto& threshold = thresholds_[index];
        side_groups[{threshold.zone_a, threshold.side_a}].push_back(index);
        side_groups[{threshold.zone_b, threshold.side_b}].push_back(index);
    }
    for (auto& [key, indices] : side_groups) {
        std::sort(indices.begin(), indices.end(), [&](std::size_t lhs, std::size_t rhs) {
            const auto other = [&](std::size_t index) -> const std::string& {
                const auto& threshold = thresholds_[index];
                return threshold.zone_a == key.first ? threshold.zone_b : threshold.zone_a;
            };
            return other(lhs) < other(rhs);
        });
        for (std::size_t slot = 0; slot < indices.size(); ++slot) {
            auto& threshold = thresholds_[indices[slot]];
            if (threshold.zone_a == key.first && threshold.side_a == key.second) {
                threshold.slot_a = slot;
                threshold.slots_on_side_a = indices.size();
            }
            if (threshold.zone_b == key.first && threshold.side_b == key.second) {
                threshold.slot_b = slot;
                threshold.slots_on_side_b = indices.size();
            }
        }
    }

    for (std::size_t index = 0; index < thresholds_.size(); ++index) {
        nodes_[thresholds_[index].zone_a].thresholds.push_back(index);
        nodes_[thresholds_[index].zone_b].thresholds.push_back(index);
    }

    remembered_connections_.clear();
    for (const auto& threshold : thresholds_) {
        remembered_connections_.insert(connection_key(threshold.zone_a, threshold.zone_b));
    }

    topology_dirty_ = false;
}

math::Vec3 TacticalMemoryMap::node_center(std::string_view zone) const noexcept {
    const auto found = nodes_.find(std::string(zone));
    if (found == nodes_.end()) return {0.0F, kMapY, 0.0F};
    return {static_cast<float>(found->second.coord.x) * kNodeSpacing,
            kMapY,
            static_cast<float>(found->second.coord.z) * kNodeSpacing};
}

math::Vec3 TacticalMemoryMap::transform_into_node(
    const world::LiminalLevel& level, std::string_view zone,
    math::Vec3 world_position, float inset_scale) const noexcept {
    const auto node_it = nodes_.find(std::string(zone));
    const auto* area = find_area(level, zone);
    if (node_it == nodes_.end() || area == nullptr) return node_center(zone);

    const float width = std::max(0.1F, area->max_x - area->min_x);
    const float depth = std::max(0.1F, area->max_z - area->min_z);
    math::Vec3 local{
        ((world_position.x - area->min_x) / width - 0.5F) * inset_scale * 2.0F,
        0.0F,
        ((world_position.z - area->min_z) / depth - 0.5F) * inset_scale * 2.0F,
    };
    local = rotate_flat(local, node_it->second.rotation_steps);
    return node_center(zone) + local;
}

void TacticalMemoryMap::rebuild_static_points(const world::LiminalLevel& level) {
    static_points_.clear();

    for (const auto& [zone, node] : nodes_) {
        const bool visited = visited_zone(zone);
        const bool scanned = scanned_zones_.contains(zone);
        if (!visited && !scanned) continue;

        const math::Vec3 center = node_center(zone);
        const auto vertices = octagon(center);
        const float level_light = std::clamp(0.58F + static_cast<float>(node.coord.level) * 0.10F,
                                             0.22F, 0.95F);
        const float base_r = visited ? 0.08F + level_light * 0.08F : 0.16F;
        const float base_g = visited ? 0.48F + level_light * 0.34F : 0.28F;
        const float base_b = visited ? 0.62F + level_light * 0.34F : 0.38F;
        const float base_a = visited ? 0.96F : 0.62F;

        // Sparse nested octagons give each logical level a stable shade without filling the screen.
        for (float scale : {0.86F, 0.68F}) {
            const auto inner = octagon(center, kNodeRadius * scale);
            for (int side = 0; side < 8; ++side) {
                if (scanned && !visited) {
                    add_dashed_line(static_points_, inner[static_cast<std::size_t>(side)],
                                    inner[static_cast<std::size_t>((side + 1) % 8)],
                                    0.34F, 0.10F, base_r, base_g, base_b, base_a * 0.34F);
                } else {
                    add_line(static_points_, inner[static_cast<std::size_t>(side)],
                             inner[static_cast<std::size_t>((side + 1) % 8)],
                             0.42F, 0.09F, base_r, base_g, base_b, base_a * 0.24F);
                }
            }
        }

        for (int side = 0; side < 8; ++side) {
            const math::Vec3 a = vertices[static_cast<std::size_t>(side)];
            const math::Vec3 b = vertices[static_cast<std::size_t>((side + 1) % 8)];
            std::vector<std::pair<float, std::size_t>> slots;
            for (const std::size_t threshold_index : node.thresholds) {
                const auto& threshold = thresholds_[threshold_index];
                const bool endpoint_a = threshold.zone_a == zone;
                const int endpoint_side = endpoint_a ? threshold.side_a : threshold.side_b;
                if (endpoint_side != side) continue;
                const std::size_t slot = endpoint_a ? threshold.slot_a : threshold.slot_b;
                const std::size_t count = endpoint_a ? threshold.slots_on_side_a
                                                     : threshold.slots_on_side_b;
                const float t = static_cast<float>(slot + 1U) /
                                static_cast<float>(count + 1U);
                slots.emplace_back(t, threshold_index);
            }
            std::sort(slots.begin(), slots.end());

            float cursor = 0.0F;
            const float gap = slots.size() > 3U ? 0.055F : 0.075F;
            auto draw_border = [&](float from, float to) {
                if (to <= from) return;
                const math::Vec3 p0 = a + (b - a) * from;
                const math::Vec3 p1 = a + (b - a) * to;
                if (scanned && !visited) {
                    add_dashed_line(static_points_, p0, p1, 0.28F, 0.16F,
                                    base_r, base_g, base_b, base_a);
                } else {
                    add_line(static_points_, p0, p1, 0.23F, 0.18F,
                             base_r, base_g, base_b, base_a);
                }
            };

            for (const auto& [t, threshold_index] : slots) {
                draw_border(cursor, std::max(cursor, t - gap));
                cursor = std::min(1.0F, t + gap);

                const auto& threshold = thresholds_[threshold_index];
                const bool endpoint_a = threshold.zone_a == zone;
                const std::string& other = endpoint_a ? threshold.zone_b : threshold.zone_a;
                const bool traversed = visited && visited_zone(other);
                const float mr = traversed ? 0.24F : 0.30F;
                const float mg = traversed ? 0.96F : 0.48F;
                const float mb = traversed ? 1.00F : 0.62F;
                const math::Vec3 slot_center = a + (b - a) * t;
                const math::Vec3 inward = side_outward(side) * -0.52F;
                const math::Vec3 tangent = math::normalize_or(b - a, {1.0F, 0.0F, 0.0F});

                if (threshold.kind == ThresholdKind::window) {
                    add_line(static_points_, slot_center - tangent * 0.30F + inward * 0.20F,
                             slot_center + tangent * 0.30F + inward * 0.20F,
                             0.14F, 0.16F, 0.18F, 0.66F, 1.0F);
                    add_line(static_points_, slot_center - tangent * 0.30F + inward * 0.48F,
                             slot_center + tangent * 0.30F + inward * 0.48F,
                             0.14F, 0.13F, 0.18F, 0.66F, 1.0F);
                } else if (threshold.kind == ThresholdKind::drop) {
                    const math::Vec3 tip = slot_center + inward * 0.78F;
                    add_line(static_points_, slot_center - tangent * 0.34F,
                             tip, 0.15F, 0.16F, 1.0F, 0.66F, 0.20F);
                    add_line(static_points_, slot_center + tangent * 0.34F,
                             tip, 0.15F, 0.16F, 1.0F, 0.66F, 0.20F);
                } else {
                    add_line(static_points_, slot_center - tangent * 0.34F,
                             slot_center - tangent * 0.34F + inward,
                             0.15F, 0.15F, mr, mg, mb, traversed ? 1.0F : 0.72F);
                    add_line(static_points_, slot_center + tangent * 0.34F,
                             slot_center + tangent * 0.34F + inward,
                             0.15F, 0.15F, mr, mg, mb, traversed ? 1.0F : 0.72F);
                    if (threshold.kind == ThresholdKind::glass) {
                        add_line(static_points_, slot_center - tangent * 0.26F + inward * 0.52F,
                                 slot_center + tangent * 0.26F + inward * 0.52F,
                                 0.13F, 0.11F, 0.20F, 0.72F, 1.0F, 0.70F);
                    }
                }
            }
            draw_border(cursor, 1.0F);
        }

        if (visited) {
            const auto* area = find_area(level, zone);
            if (area != nullptr) {
                const float width = std::max(0.1F, area->max_x - area->min_x);
                const float depth = std::max(0.1F, area->max_z - area->min_z);
                const float fit = (2.0F * kInsetRadius) / std::max(width, depth);
                const float half_x = width * fit * 0.5F;
                const float half_z = depth * fit * 0.5F;
                std::array<math::Vec3, 4> footprint{{
                    {-half_x, 0.0F, -half_z}, {half_x, 0.0F, -half_z},
                    {half_x, 0.0F, half_z}, {-half_x, 0.0F, half_z},
                }};
                for (auto& p : footprint) p = center + rotate_flat(p, node.rotation_steps);
                for (int i = 0; i < 4; ++i) {
                    add_line(static_points_, footprint[static_cast<std::size_t>(i)],
                             footprint[static_cast<std::size_t>((i + 1) % 4)],
                             0.30F, 0.10F, 0.34F, 0.58F, 0.68F, 0.72F);
                }

                int wall_count = 0;
                for (const auto& wall : level.walls()) {
                    const math::Vec3 middle = (wall.start + wall.end) * 0.5F;
                    if (middle.x < area->min_x || middle.x > area->max_x ||
                        middle.z < area->min_z || middle.z > area->max_z) continue;
                    const auto p0 = transform_into_node(level, zone, wall.start, kInsetRadius);
                    const auto p1 = transform_into_node(level, zone, wall.end, kInsetRadius);
                    add_line(static_points_, p0, p1, 0.38F, 0.09F,
                             0.26F, 0.38F, 0.44F, 0.62F);
                    if (++wall_count >= 12) break;
                }

                for (const auto& obstacle : level.obstacles()) {
                    const float cx = (obstacle.min_x + obstacle.max_x) * 0.5F;
                    const float cz = (obstacle.min_z + obstacle.max_z) * 0.5F;
                    if (cx < area->min_x || cx > area->max_x ||
                        cz < area->min_z || cz > area->max_z) continue;
                    const auto marker = transform_into_node(level, zone, {cx, 0.0F, cz}, kInsetRadius);
                    add_diamond(static_points_, marker, 0.20F, 0.30F, 0.46F, 0.52F);
                }
            }
        }

        if (zone == "Reception Tape" || zone.find("Safe") != std::string::npos ||
            zone.find("Save") != std::string::npos) {
            add_cross(static_points_, center + math::Vec3{-1.65F, 0.0F, 1.55F},
                      0.46F, 0.28F, 1.0F, 0.54F);
        }
        if (zone == "Scavenger Exchange") {
            add_diamond(static_points_, center + math::Vec3{1.60F, 0.0F, 1.52F},
                        0.50F, 1.0F, 0.74F, 0.18F);
        }
        if (const auto* area = find_area(level, zone); area != nullptr) {
            bool wet = false;
            for (const auto& water : level.water_regions()) wet = wet || overlaps(*area, water);
            if (wet) {
                for (int band = -1; band <= 1; ++band) {
                    const float z = center.z + 1.35F + static_cast<float>(band) * 0.24F;
                    add_line(static_points_, {center.x - 0.72F, kMapY, z},
                             {center.x + 0.72F, kMapY, z},
                             0.20F, 0.11F, 0.12F, 0.58F, 1.0F, 0.86F);
                }
            }
        }

        const int level_marks = std::min(4, std::abs(node.coord.level));
        for (int mark = 0; mark < level_marks; ++mark) {
            const float x = center.x - 0.52F + static_cast<float>(mark) * 0.35F;
            const float z = node.coord.level > 0 ? center.z - 1.78F : center.z + 1.82F;
            add_line(static_points_, {x, kMapY, z}, {x + 0.20F, kMapY, z},
                     0.12F, 0.10F,
                     node.coord.level > 0 ? 0.80F : 0.28F,
                     node.coord.level > 0 ? 0.92F : 0.38F,
                     node.coord.level > 0 ? 1.0F : 0.52F, 0.92F);
        }
    }

    if (static_points_.size() > kStaticPointBudget) static_points_.resize(kStaticPointBudget);
    ++stats_.static_rebuilds;
    stats_.visited_rooms = visited_zones_.size();
    stats_.scanned_rooms = scanned_zones_.size();
    stats_.remembered_connections = remembered_connections_.size();
    stats_.topology_nodes = nodes_.size();
    stats_.threshold_slots = thresholds_.size() * 2U;
    std::set<int> levels;
    for (const auto& [zone, node] : nodes_) {
        (void)zone;
        levels.insert(node.coord.level);
    }
    stats_.logical_levels = levels.size();
    stats_.static_points = static_points_.size();
    dirty_ = false;
}

void TacticalMemoryMap::rebuild_if_dirty(const world::LiminalLevel& level) {
    if (topology_dirty_) rebuild_topology(level);
    if (dirty_) rebuild_static_points(level);
    if (memory_dirty_) save_memory(level);
}

int TacticalMemoryMap::facing_side(std::string_view zone,
                                   math::Vec3 world_forward) const noexcept {
    const auto found = nodes_.find(std::string(zone));
    const int rotation = found == nodes_.end() ? 0 : found->second.rotation_steps;
    math::Vec3 forward{world_forward.x, 0.0F, world_forward.z};
    forward = rotate_flat(math::normalize_or(forward, {0.0F, 0.0F, -1.0F}), rotation);
    int best_side = 0;
    float best_dot = -std::numeric_limits<float>::infinity();
    for (int side = 0; side < 8; ++side) {
        const float score = math::dot(forward, side_outward(side));
        if (score > best_dot) {
            best_dot = score;
            best_side = side;
        }
    }
    return best_side;
}

std::vector<render::PointGpu> TacticalMemoryMap::build_points(
    const world::LiminalLevel& level,
    math::Vec3 player_position,
    math::Vec3 player_forward,
    std::string_view current_zone,
    const combat::CombatSystem& combat,
    const economy::EconomySystem& economy,
    float time_seconds) {
    observe_zone(level, current_zone);
    rebuild_if_dirty(level);

    std::vector<render::PointGpu> result = static_points_;
    result.reserve(static_points_.size() + 384U);

    const auto node_it = nodes_.find(std::string(current_zone));
    if (node_it == nodes_.end()) {
        stats_.submitted_points = result.size();
        return result;
    }

    const math::Vec3 center = node_center(current_zone) + math::Vec3{0.0F, 0.13F, 0.0F};
    math::Vec3 map_forward = rotate_flat(
        math::normalize_or(math::Vec3{player_forward.x, 0.0F, player_forward.z},
                           {0.0F, 0.0F, -1.0F}),
        node_it->second.rotation_steps);
    const math::Vec3 right{-map_forward.z, 0.0F, map_forward.x};
    const float pulse = 0.20F + std::sin(time_seconds * 5.0F) * 0.035F;
    const math::Vec3 tip = center + map_forward * 1.48F;
    add_line(result, center - map_forward * 0.54F, tip,
             0.17F, pulse, 1.0F, 1.0F, 1.0F);
    add_line(result, tip, center + map_forward * 0.60F + right * 0.58F,
             0.17F, pulse, 1.0F, 1.0F, 1.0F);
    add_line(result, tip, center + map_forward * 0.60F - right * 0.58F,
             0.17F, pulse, 1.0F, 1.0F, 1.0F);

    std::optional<std::size_t> facing_threshold;
    float best_score = 0.52F;
    math::Vec3 flat_forward = math::normalize_or(
        math::Vec3{player_forward.x, 0.0F, player_forward.z},
        {0.0F, 0.0F, -1.0F});
    for (const std::size_t threshold_index : node_it->second.thresholds) {
        const auto& threshold = thresholds_[threshold_index];
        const bool endpoint_a = threshold.zone_a == current_zone;
        const bool has_center = endpoint_a ? threshold.has_center_a : threshold.has_center_b;
        if (!has_center) continue;
        const math::Vec3 target = endpoint_a ? threshold.center_a : threshold.center_b;
        const math::Vec3 to_target = math::normalize_or(
            math::Vec3{target.x - player_position.x, 0.0F, target.z - player_position.z},
            flat_forward);
        const float score = math::dot(flat_forward, to_target);
        if (score > best_score) {
            best_score = score;
            facing_threshold = threshold_index;
        }
    }
    if (!facing_threshold.has_value()) {
        const int side = facing_side(current_zone, player_forward);
        for (const std::size_t threshold_index : node_it->second.thresholds) {
            const auto& threshold = thresholds_[threshold_index];
            const int endpoint_side = threshold.zone_a == current_zone
                ? threshold.side_a : threshold.side_b;
            if (endpoint_side == side) {
                facing_threshold = threshold_index;
                break;
            }
        }
    }
    if (facing_threshold.has_value()) {
        const auto& threshold = thresholds_[*facing_threshold];
        const bool endpoint_a = threshold.zone_a == current_zone;
        const int side = endpoint_a ? threshold.side_a : threshold.side_b;
        const std::size_t slot = endpoint_a ? threshold.slot_a : threshold.slot_b;
        const std::size_t count = endpoint_a ? threshold.slots_on_side_a
                                             : threshold.slots_on_side_b;
        const auto vertices = octagon(node_center(current_zone));
        const float t = static_cast<float>(slot + 1U) / static_cast<float>(count + 1U);
        const math::Vec3 slot_point = vertices[static_cast<std::size_t>(side)] +
            (vertices[static_cast<std::size_t>((side + 1) % 8)] -
             vertices[static_cast<std::size_t>(side)]) * t;
        add_ring(result, slot_point + side_outward(side) * -0.52F,
                 0.42F + std::sin(time_seconds * 6.0F) * 0.05F,
                 1.0F, 0.92F, 0.28F);
    }

    if (current_zone == "Live-Fire Signal Range") {
        for (const auto& entity : combat.entities()) {
            if (!entity.alive) continue;
            const math::Vec3 marker = transform_into_node(level, current_zone,
                                                           entity.position, 2.62F) +
                                      math::Vec3{0.0F, 0.11F, 0.0F};
            if (entity.kind == signalcloud::combat::CreatureKind::hash_dog) {
                add_line(result, marker + math::Vec3{0.0F, 0.0F, -0.52F},
                         marker + math::Vec3{0.45F, 0.0F, 0.38F},
                         0.16F, 0.18F, 1.0F, 0.16F, 0.10F);
                add_line(result, marker + math::Vec3{0.45F, 0.0F, 0.38F},
                         marker + math::Vec3{-0.45F, 0.0F, 0.38F},
                         0.16F, 0.18F, 1.0F, 0.16F, 0.10F);
                add_line(result, marker + math::Vec3{-0.45F, 0.0F, 0.38F},
                         marker + math::Vec3{0.0F, 0.0F, -0.52F},
                         0.16F, 0.18F, 1.0F, 0.16F, 0.10F);
            } else {
                add_ring(result, marker, 0.48F, 0.92F, 0.18F, 1.0F);
            }
        }
    }

    if (current_zone == "Scavenger Exchange") {
        for (const auto& pickup : economy.pickups()) {
            if (pickup.collected) continue;
            const auto marker = transform_into_node(level, current_zone,
                                                     pickup.position, 2.62F);
            add_diamond(result, marker, 0.26F, 1.0F, 0.90F, 0.28F);
        }
    }

    if (result.size() > kStaticPointBudget) result.resize(kStaticPointBudget);
    stats_.submitted_points = result.size();
    return result;
}

math::Mat4 TacticalMemoryMap::view_projection(float aspect,
                                              const world::LiminalLevel& level) const noexcept {
    (void)level;
    float min_x = -kNodeRadius;
    float max_x = kNodeRadius;
    float min_z = -kNodeRadius;
    float max_z = kNodeRadius;
    bool first = true;
    for (const auto& [zone, node] : nodes_) {
        if (!knows_zone(zone)) continue;
        const float x = static_cast<float>(node.coord.x) * kNodeSpacing;
        const float z = static_cast<float>(node.coord.z) * kNodeSpacing;
        if (first) {
            min_x = x - kNodeRadius; max_x = x + kNodeRadius;
            min_z = z - kNodeRadius; max_z = z + kNodeRadius;
            first = false;
        } else {
            min_x = std::min(min_x, x - kNodeRadius); max_x = std::max(max_x, x + kNodeRadius);
            min_z = std::min(min_z, z - kNodeRadius); max_z = std::max(max_z, z + kNodeRadius);
        }
    }
    const float center_x = (min_x + max_x) * 0.5F;
    const float center_z = (min_z + max_z) * 0.5F;
    const float span_x = std::max(18.0F, max_x - min_x + 5.0F);
    const float span_z = std::max(18.0F, max_z - min_z + 5.0F);
    const float safe_aspect = aspect > 0.1F ? aspect : 1.0F;
    const float half_height = std::max(span_z * 0.54F, span_x * 0.54F / safe_aspect);
    const float half_width = half_height * safe_aspect;
    const auto projection = math::orthographic(-half_width, half_width,
                                                -half_height, half_height,
                                                -1000.0F, 1000.0F);
    const auto view = math::look_at({center_x, 620.0F, center_z},
                                    {center_x, 0.0F, center_z},
                                    {0.0F, 0.0F, -1.0F});
    return projection * view;
}

bool TacticalMemoryMap::load_memory(const world::LiminalLevel& level) {
    if (memory_path_.empty()) return false;
    std::ifstream input(memory_path_);
    if (!input) return false;

    std::string magic;
    int version = 0;
    input >> magic >> version;
    if (magic != "@tmap" || version != 1) return false;

    std::uint64_t seed = 0;
    std::uint64_t layout = 0;
    std::string token;
    input >> token >> std::hex >> seed;
    input >> token >> std::hex >> layout;
    input >> std::dec;
    if (seed != level.seed() || layout != level.layout_signature()) return false;

    while (input >> token) {
        if (token != "room") {
            std::string ignored;
            std::getline(input, ignored);
            continue;
        }
        std::string zone;
        int visited = 0;
        int scanned = 0;
        AtlasNode node{};
        input >> std::quoted(zone) >> visited >> scanned
              >> node.coord.x >> node.coord.z >> node.coord.level >> node.rotation_steps;
        if (!input) break;
        node.rotation_steps = normalize_side(node.rotation_steps);
        nodes_[zone] = node;
        if (visited != 0) visited_zones_.insert(zone);
        else if (scanned != 0) scanned_zones_.insert(zone);
    }
    ++stats_.memory_loads;
    topology_dirty_ = true;
    dirty_ = true;
    memory_dirty_ = false;
    return true;
}

bool TacticalMemoryMap::save_memory(const world::LiminalLevel& level) {
    if (memory_path_.empty() || storage_root_.empty()) {
        memory_dirty_ = false;
        return false;
    }
    std::error_code ec;
    std::filesystem::create_directories(storage_root_, ec);
    if (ec) return false;

    const std::filesystem::path temporary = memory_path_.string() + ".tmp";
    {
        std::ofstream output(temporary, std::ios::trunc);
        if (!output) return false;
        output << "@tmap 1\n";
        output << "seed " << std::uppercase << std::hex << level.seed() << '\n';
        output << "layout " << std::uppercase << std::hex << level.layout_signature() << '\n';
        output << std::dec;
        for (const auto& [zone, node] : nodes_) {
            if (!knows_zone(zone)) continue;
            output << "room " << std::quoted(zone) << ' '
                   << (visited_zone(zone) ? 1 : 0) << ' '
                   << (scanned_zones_.contains(zone) ? 1 : 0) << ' '
                   << node.coord.x << ' ' << node.coord.z << ' '
                   << node.coord.level << ' ' << node.rotation_steps << '\n';
        }
        output.flush();
        if (!output) return false;
    }

    std::filesystem::rename(temporary, memory_path_, ec);
    if (ec) {
        std::error_code remove_ec;
        std::filesystem::remove(memory_path_, remove_ec);
        ec.clear();
        std::filesystem::rename(temporary, memory_path_, ec);
    }
    if (ec) {
        std::error_code cleanup_ec;
        std::filesystem::remove(temporary, cleanup_ec);
        return false;
    }
    memory_dirty_ = false;
    ++stats_.memory_saves;
    return true;
}

}  // namespace signalcloud::ui
