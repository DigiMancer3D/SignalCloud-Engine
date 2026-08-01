#pragma once

#include "engine/math/vec.hpp"

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace signalcloud::world {

struct WalkArea {
    float min_x{0.0F};
    float max_x{0.0F};
    float min_z{0.0F};
    float max_z{0.0F};
    std::string name;
};

struct WallSegment {
    math::Vec3 start{};
    math::Vec3 end{};
    math::Vec3 inward_normal{};
    float height{5.8F};
    float base_y{0.0F};
};

struct SolidObstacle {
    float min_x{0.0F};
    float max_x{0.0F};
    float min_z{0.0F};
    float max_z{0.0F};
    float height{2.8F};
    std::string name;
};

struct WaterRegion {
    float min_x{0.0F};
    float max_x{0.0F};
    float min_z{0.0F};
    float max_z{0.0F};
    float surface_y{0.08F};
    float bottom_y{-1.0F};
    std::string name;
    float viscosity{1.0F};
    bool pressure_exposed{false};
    bool corridor_safe{true};
    float oxygen_drain_scale{1.0F};
};

enum class PortalKind : std::uint8_t {
    door,
    window,
    drop,
};

struct PortalGate {
    std::uint32_t id{0};
    PortalKind kind{PortalKind::door};
    math::Vec3 center{};
    math::Vec3 inward_normal{0.0F, 0.0F, 1.0F};
    float half_width{1.05F};
    float height{2.55F};
    float trigger_depth{0.90F};
    math::Vec3 destination{};
    float destination_yaw_degrees{-90.0F};
    std::string name;
    std::string source_zone;
    std::string destination_zone;
};

enum class ConnectionKind : std::uint8_t {
    open_doorway,
    framed_doorway,
    window,
    hole,
    passage,
    glass,
};

struct RoomConnection {
    std::string zone_a;
    std::string zone_b;
    math::Vec3 center{};
    float half_width{1.5F};
    float preview_distance{7.5F};
    ConnectionKind kind{ConnectionKind::open_doorway};
    bool bidirectional{true};
};

struct ConnectionAperture {
    math::Vec3 center{};
    math::Vec3 normal{1.0F, 0.0F, 0.0F};
    float half_width{1.5F};
    float bottom_y{0.0F};
    float top_y{3.2F};
};

struct ConnectionPreview {
    std::string_view destination_zone{};
    math::Vec3 center{};
    float strength{0.0F};
    ConnectionKind kind{ConnectionKind::open_doorway};
    math::Vec3 viewer_position{};
    math::Vec3 normal{1.0F, 0.0F, 0.0F};
    float half_width{1.5F};
    float bottom_y{0.0F};
    float top_y{3.2F};
};

struct ThresholdEnvelope {
    std::string zone_a;
    std::string zone_b;
    ConnectionAperture aperture{};
    float span_min{0.0F};
    float span_max{0.0F};
    float base_y{0.0F};
    float ceiling_y{5.8F};
    bool vertical_plane{true};
    std::vector<WallSegment> panels;
};

struct LightSource {
    math::Vec3 position{};
    float radius{9.0F};
    float intensity{1.0F};
    std::string zone;
};

struct LightInfluence {
    math::Vec3 position{};
    float radius{0.0F};
    float intensity{0.0F};
    float influence{0.0F};
};

struct LevelBounds {
    float min_x{0.0F};
    float max_x{0.0F};
    float min_z{0.0F};
    float max_z{0.0F};
};

struct DepenetrationResult {
    math::Vec3 position{};
    bool corrected{false};
    std::uint32_t iterations{0};
    std::string_view obstacle_name{};
};

class LiminalLevel {
public:
    static LiminalLevel make_pivot2_demo(std::uint64_t seed);
    static LiminalLevel make_pivot3_procedural(std::uint64_t seed, std::size_t room_count = 12U);
    static LiminalLevel make_pivot5_traversal(std::uint64_t seed);
    static LiminalLevel make_pivot6_depth(std::uint64_t seed);
    static LiminalLevel make_pivot7_thresholds(std::uint64_t seed);
    static LiminalLevel make_pivot8_submerged(std::uint64_t seed);
    static LiminalLevel make_pivot9_combat(std::uint64_t seed);
    static LiminalLevel make_pivot11_scavenging(std::uint64_t seed);

    [[nodiscard]] bool point_is_walkable(float x, float z) const noexcept;
    [[nodiscard]] bool can_occupy(float x, float z, float radius) const noexcept;
    [[nodiscard]] bool can_occupy_3d(float x, float z, float feet_y, float player_height,
                                     float radius, float step_height) const noexcept;
    [[nodiscard]] DepenetrationResult depenetrate_3d(math::Vec3 eye_position,
                                                     float player_height,
                                                     float radius,
                                                     float step_height) const noexcept;
    [[nodiscard]] float ground_height_at(float x, float z) const noexcept;
    [[nodiscard]] const WaterRegion* water_at(float x, float z) const noexcept;
    [[nodiscard]] const SolidObstacle* obstacle_at(float x, float z, float radius = 0.0F) const noexcept;
    [[nodiscard]] const SolidObstacle* climbable_obstacle_near(float x, float z, float radius,
                                                               float maximum_top) const noexcept;
    [[nodiscard]] std::string_view surface_name_at(float x, float z) const noexcept;
    [[nodiscard]] std::string_view zone_name(math::Vec3 position) const noexcept;
    [[nodiscard]] const PortalGate* portal_at(math::Vec3 position) const noexcept;
    [[nodiscard]] std::vector<ConnectionPreview> connection_previews(
        std::string_view active_zone, math::Vec3 position) const;
    [[nodiscard]] ConnectionAperture connection_aperture(
        const RoomConnection& connection, std::string_view source_zone) const noexcept;
    [[nodiscard]] LightInfluence strongest_light(math::Vec3 position,
                                                 std::string_view active_zone) const noexcept;
    [[nodiscard]] LevelBounds bounds() const noexcept;
    [[nodiscard]] std::uint64_t layout_signature() const noexcept;
    [[nodiscard]] math::Vec3 traversal_lab_spawn() const noexcept { return traversal_lab_spawn_; }
    [[nodiscard]] math::Vec3 depth_lab_spawn() const noexcept { return depth_lab_spawn_; }
    [[nodiscard]] math::Vec3 threshold_lab_spawn() const noexcept { return threshold_lab_spawn_; }
    [[nodiscard]] math::Vec3 submerged_lab_spawn() const noexcept { return submerged_lab_spawn_; }
    [[nodiscard]] math::Vec3 combat_lab_spawn() const noexcept { return combat_lab_spawn_; }
    [[nodiscard]] math::Vec3 economy_lab_spawn() const noexcept { return economy_lab_spawn_; }
    [[nodiscard]] math::Vec3 almond_tech_position() const noexcept { return almond_tech_position_; }
    [[nodiscard]] bool has_almond_tech_station() const noexcept { return has_almond_tech_station_; }
    [[nodiscard]] bool near_almond_tech(math::Vec3 position, float radius = 3.4F) const noexcept;

    [[nodiscard]] const std::vector<WalkArea>& areas() const noexcept { return areas_; }
    [[nodiscard]] const std::vector<WallSegment>& walls() const noexcept { return walls_; }
    [[nodiscard]] const std::vector<SolidObstacle>& obstacles() const noexcept { return obstacles_; }
    [[nodiscard]] const std::vector<WaterRegion>& water_regions() const noexcept { return water_regions_; }
    [[nodiscard]] const std::vector<PortalGate>& portals() const noexcept { return portals_; }
    [[nodiscard]] const std::vector<RoomConnection>& connections() const noexcept { return connections_; }
    [[nodiscard]] const std::vector<ThresholdEnvelope>& threshold_envelopes() const noexcept {
        return threshold_envelopes_;
    }
    [[nodiscard]] const std::vector<LightSource>& lights() const noexcept { return lights_; }
    [[nodiscard]] math::Vec3 spawn_position() const noexcept { return spawn_position_; }
    [[nodiscard]] float floor_height() const noexcept { return floor_height_; }
    [[nodiscard]] float ceiling_height() const noexcept { return ceiling_height_; }
    [[nodiscard]] std::uint64_t seed() const noexcept { return seed_; }

private:
    std::vector<WalkArea> areas_;
    std::vector<WallSegment> walls_;
    std::vector<SolidObstacle> obstacles_;
    std::vector<WaterRegion> water_regions_;
    std::vector<PortalGate> portals_;
    std::vector<RoomConnection> connections_;
    std::vector<ThresholdEnvelope> threshold_envelopes_;
    std::vector<LightSource> lights_;
    math::Vec3 spawn_position_{0.0F, 1.72F, 5.5F};
    math::Vec3 traversal_lab_spawn_{0.0F, 1.72F, 0.0F};
    math::Vec3 depth_lab_spawn_{0.0F, 1.72F, 0.0F};
    math::Vec3 threshold_lab_spawn_{0.0F, 1.72F, 0.0F};
    math::Vec3 submerged_lab_spawn_{0.0F, 1.72F, 0.0F};
    math::Vec3 combat_lab_spawn_{0.0F, 1.72F, 0.0F};
    math::Vec3 economy_lab_spawn_{0.0F, 1.72F, 0.0F};
    math::Vec3 almond_tech_position_{0.0F, 0.0F, 0.0F};
    bool has_almond_tech_station_{false};
    void rebuild_threshold_envelopes();
    float threshold_floor_near(math::Vec3 position) const noexcept;
    float floor_height_{0.0F};
    float ceiling_height_{5.8F};
    std::uint64_t seed_{0};
};

[[nodiscard]] std::string_view portal_kind_name(PortalKind kind) noexcept;
[[nodiscard]] std::string_view connection_kind_name(ConnectionKind kind) noexcept;

}  // namespace signalcloud::world
