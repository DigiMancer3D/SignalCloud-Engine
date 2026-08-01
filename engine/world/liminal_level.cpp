#include "engine/world/liminal_level.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>

namespace signalcloud::world {
namespace {

bool within(float value, float low, float high) noexcept {
    return value >= low && value <= high;
}

WallSegment vertical_wall(float x, float z0, float z1, float nx, float nz, float height,
                          float base_y = 0.0F) {
    return {{x, base_y, z0}, {x, base_y, z1}, {nx, 0.0F, nz}, height, base_y};
}

WallSegment horizontal_wall(float z, float x0, float x1, float nx, float nz, float height,
                            float base_y = 0.0F) {
    return {{x0, base_y, z}, {x1, base_y, z}, {nx, 0.0F, nz}, height, base_y};
}

class XorShift64 {
public:
    explicit XorShift64(std::uint64_t seed) : state_(seed == 0 ? 0x9E3779B97F4A7C15ULL : seed) {}
    std::uint64_t next() noexcept {
        state_ ^= state_ << 13U;
        state_ ^= state_ >> 7U;
        state_ ^= state_ << 17U;
        return state_;
    }
    float unit() noexcept {
        return static_cast<float>((next() >> 40U) & 0xFFFFFFU) / static_cast<float>(0xFFFFFFU);
    }
    float range(float low, float high) noexcept { return low + (high - low) * unit(); }
private:
    std::uint64_t state_;
};

std::string procedural_name(std::size_t index) {
    static constexpr std::array<std::string_view, 16> names{{
        "Reception Tape", "Hum Hall", "Carpet Annex", "Window Array",
        "Open Office", "Matrix Door Hall", "Almond Concourse", "Service Loop",
        "Null Breakroom", "Echo Archive", "Inverted Lobby", "Signal Threshold",
        "Fluorescent Court", "Copy Room Delta", "Wetwall Approach", "Deep Registry",
    }};
    return std::string(names[index % names.size()]);
}

math::Vec3 room_center(const WalkArea& area, float eye_height) noexcept {
    return {(area.min_x + area.max_x) * 0.5F, eye_height, (area.min_z + area.max_z) * 0.5F};
}

struct SidePlacement {
    math::Vec3 center;
    math::Vec3 inward;
    float yaw;
};

SidePlacement side_placement(const WalkArea& area, int side, float eye_height) {
    const float cx = (area.min_x + area.max_x) * 0.5F;
    const float cz = (area.min_z + area.max_z) * 0.5F;
    switch (side & 3) {
        case 0: return {{cx, eye_height, area.min_z}, {0.0F, 0.0F, 1.0F}, 90.0F};
        case 1: return {{area.max_x, eye_height, cz}, {-1.0F, 0.0F, 0.0F}, 180.0F};
        case 2: return {{cx, eye_height, area.max_z}, {0.0F, 0.0F, -1.0F}, -90.0F};
        default: return {{area.min_x, eye_height, cz}, {1.0F, 0.0F, 0.0F}, 0.0F};
    }
}

std::uint64_t mix_signature(std::uint64_t value, std::uint64_t input) noexcept {
    value ^= input + 0x9E3779B97F4A7C15ULL + (value << 6U) + (value >> 2U);
    return value;
}

std::uint64_t quantized(float value) noexcept {
    return static_cast<std::uint64_t>(static_cast<std::int64_t>(std::llround(value * 1000.0F)));
}

math::Vec3 closest_point_on_wall_xz(const WallSegment& wall, math::Vec3 position) noexcept {
    const float dx = wall.end.x - wall.start.x;
    const float dz = wall.end.z - wall.start.z;
    const float length_sq = dx * dx + dz * dz;
    if (length_sq <= 0.000001F) return wall.start;
    const float t = std::clamp(((position.x - wall.start.x) * dx +
                                (position.z - wall.start.z) * dz) / length_sq,
                               0.0F, 1.0F);
    return {wall.start.x + dx * t, position.y, wall.start.z + dz * t};
}

float distance_xz(math::Vec3 a, math::Vec3 b) noexcept {
    const float dx = a.x - b.x;
    const float dz = a.z - b.z;
    return std::sqrt(dx * dx + dz * dz);
}

bool approximately(float a, float b, float epsilon = 0.001F) noexcept {
    return std::abs(a - b) <= epsilon;
}

const WalkArea* find_area(const std::vector<WalkArea>& areas, std::string_view name) noexcept {
    for (const auto& area : areas) if (area.name == name) return &area;
    return nullptr;
}

math::Vec3 horizontal_direction(math::Vec3 from, math::Vec3 to) noexcept {
    math::Vec3 direction{to.x - from.x, 0.0F, to.z - from.z};
    const float length = std::sqrt(direction.x * direction.x + direction.z * direction.z);
    if (length <= 0.0001F) return {1.0F, 0.0F, 0.0F};
    return {direction.x / length, 0.0F, direction.z / length};
}

}  // namespace

std::string_view portal_kind_name(PortalKind kind) noexcept {
    switch (kind) {
        case PortalKind::door: return "door";
        case PortalKind::window: return "window";
        case PortalKind::drop: return "drop";
    }
    return "unknown";
}

std::string_view connection_kind_name(ConnectionKind kind) noexcept {
    switch (kind) {
        case ConnectionKind::open_doorway: return "open doorway";
        case ConnectionKind::framed_doorway: return "framed doorway";
        case ConnectionKind::window: return "window";
        case ConnectionKind::hole: return "hole";
        case ConnectionKind::passage: return "passage";
        case ConnectionKind::glass: return "glass";
    }
    return "unknown";
}

LiminalLevel LiminalLevel::make_pivot2_demo(std::uint64_t seed) {
    LiminalLevel level;
    level.seed_ = seed;
    constexpr float h = 5.8F;

    level.areas_ = {
        {-8.0F, 8.0F, -3.0F, 11.0F, "Reception Tape"},
        {-2.5F, 2.5F, -15.0F, -3.0F, "North Hall"},
        {-10.0F, 10.0F, -31.0F, -15.0F, "Open Office"},
        {10.0F, 18.0F, -25.0F, -20.0F, "Window Hall"},
        {18.0F, 30.0F, -31.0F, -15.0F, "Deep Room"},
    };

    level.walls_.push_back(vertical_wall(-8.0F, -3.0F, 11.0F, 1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(8.0F, -3.0F, 11.0F, -1.0F, 0.0F, h));
    level.walls_.push_back(horizontal_wall(11.0F, -8.0F, 8.0F, 0.0F, -1.0F, h));
    level.walls_.push_back(horizontal_wall(-3.0F, -8.0F, -2.5F, 0.0F, 1.0F, h));
    level.walls_.push_back(horizontal_wall(-3.0F, 2.5F, 8.0F, 0.0F, 1.0F, h));
    level.walls_.push_back(vertical_wall(-2.5F, -15.0F, -3.0F, 1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(2.5F, -15.0F, -3.0F, -1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(-10.0F, -31.0F, -15.0F, 1.0F, 0.0F, h));
    level.walls_.push_back(horizontal_wall(-31.0F, -10.0F, 10.0F, 0.0F, 1.0F, h));
    level.walls_.push_back(horizontal_wall(-15.0F, -10.0F, -2.5F, 0.0F, -1.0F, h));
    level.walls_.push_back(horizontal_wall(-15.0F, 2.5F, 10.0F, 0.0F, -1.0F, h));
    level.walls_.push_back(vertical_wall(10.0F, -31.0F, -25.0F, -1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(10.0F, -20.0F, -15.0F, -1.0F, 0.0F, h));
    level.walls_.push_back(horizontal_wall(-25.0F, 10.0F, 18.0F, 0.0F, 1.0F, h));
    level.walls_.push_back(horizontal_wall(-20.0F, 10.0F, 18.0F, 0.0F, -1.0F, h));
    level.walls_.push_back(vertical_wall(18.0F, -31.0F, -25.0F, 1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(18.0F, -20.0F, -15.0F, 1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(30.0F, -31.0F, -15.0F, -1.0F, 0.0F, h));
    level.walls_.push_back(horizontal_wall(-31.0F, 18.0F, 30.0F, 0.0F, 1.0F, h));
    level.walls_.push_back(horizontal_wall(-15.0F, 18.0F, 30.0F, 0.0F, -1.0F, h));

    level.obstacles_ = {
        {-4.6F, -2.6F, -26.0F, -23.8F, 3.2F, "Left Support"},
        {3.0F, 5.1F, -20.2F, -18.0F, 3.8F, "Right Support"},
        {-3.8F, 3.8F, 0.4F, 1.45F, 1.18F, "Reception Counter"},
    };

    return level;
}

LiminalLevel LiminalLevel::make_pivot3_procedural(std::uint64_t seed, std::size_t room_count) {
    LiminalLevel level;
    level.seed_ = seed;
    level.floor_height_ = 0.0F;
    level.ceiling_height_ = 5.8F;
    room_count = std::clamp<std::size_t>(room_count, 4U, 24U);
    XorShift64 rng(seed ^ 0x50305254414C334FULL);

    constexpr float spacing_x = 160.0F;
    constexpr float spacing_z = 150.0F;
    constexpr std::size_t columns = 4U;
    level.areas_.reserve(room_count);
    level.walls_.reserve(room_count * 4U);

    for (std::size_t i = 0; i < room_count; ++i) {
        const std::size_t col = i % columns;
        const std::size_t row = i / columns;
        const float center_x = static_cast<float>(col) * spacing_x;
        const float center_z = -static_cast<float>(row) * spacing_z;
        const float width = rng.range(12.0F, 20.0F);
        const float depth = rng.range(12.0F, 22.0F);
        WalkArea area{center_x - width * 0.5F, center_x + width * 0.5F,
                      center_z - depth * 0.5F, center_z + depth * 0.5F,
                      procedural_name(i)};
        level.areas_.push_back(area);
        const WalkArea& shell = level.areas_.back();
        level.walls_.push_back(vertical_wall(shell.min_x, shell.min_z, shell.max_z, 1.0F, 0.0F, level.ceiling_height_));
        level.walls_.push_back(vertical_wall(shell.max_x, shell.min_z, shell.max_z, -1.0F, 0.0F, level.ceiling_height_));
        level.walls_.push_back(horizontal_wall(shell.min_z, shell.min_x, shell.max_x, 0.0F, 1.0F, level.ceiling_height_));
        level.walls_.push_back(horizontal_wall(shell.max_z, shell.min_x, shell.max_x, 0.0F, -1.0F, level.ceiling_height_));

        const int obstacle_count = 1 + static_cast<int>(rng.next() % 3U);
        for (int obstacle_index = 0; obstacle_index < obstacle_count; ++obstacle_index) {
            const float half_w = rng.range(0.55F, 1.25F);
            const float half_d = rng.range(0.55F, 1.35F);
            float ox = rng.range(area.min_x + 2.4F, area.max_x - 2.4F);
            float oz = rng.range(area.min_z + 2.4F, area.max_z - 2.4F);
            const float room_cx = (area.min_x + area.max_x) * 0.5F;
            const float room_cz = (area.min_z + area.max_z) * 0.5F;
            if (std::abs(ox - room_cx) < 2.4F && std::abs(oz - room_cz) < 2.4F) {
                ox = area.min_x + 2.8F + static_cast<float>(obstacle_index) * 1.8F;
                oz = area.max_z - 2.8F;
            }
            const float oh = rng.range(1.1F, 4.2F);
            level.obstacles_.push_back({ox - half_w, ox + half_w, oz - half_d, oz + half_d, oh,
                                        "Procedural Fixture " + std::to_string(i) + "." + std::to_string(obstacle_index)});
        }
    }

    constexpr float eye_height = 1.72F;
    level.spawn_position_ = room_center(level.areas_.front(), eye_height);
    const std::size_t rotation = static_cast<std::size_t>(rng.next() % room_count);
    const std::size_t step = room_count % 2U == 0U ? 5U : 4U;
    level.portals_.reserve(room_count + 3U);

    for (std::size_t i = 0; i < room_count; ++i) {
        const std::size_t destination_index = (i * step + rotation + 1U) % room_count;
        const int side = static_cast<int>((rng.next() + i) % 4U);
        const auto placement = side_placement(level.areas_[i], side, eye_height);
        const auto destination = room_center(level.areas_[destination_index], eye_height);
        PortalGate gate;
        gate.id = static_cast<std::uint32_t>(i + 1U);
        gate.kind = i % 7U == 3U ? PortalKind::window : (i % 11U == 7U ? PortalKind::drop : PortalKind::door);
        gate.center = placement.center;
        gate.inward_normal = placement.inward;
        gate.destination = destination;
        gate.destination_yaw_degrees = placement.yaw + 180.0F;
        gate.name = "Gate " + std::to_string(i + 1U) + " / " + std::string(portal_kind_name(gate.kind));
        gate.source_zone = level.areas_[i].name;
        gate.destination_zone = level.areas_[destination_index].name;
        gate.half_width = gate.kind == PortalKind::window ? 1.35F : 1.05F;
        gate.height = gate.kind == PortalKind::window ? 2.15F : 2.65F;
        level.portals_.push_back(std::move(gate));
    }

    // Matrix Door Hall receives three extra choices so a single corridor can branch
    // into locations that are not spatially adjacent.
    const std::size_t matrix_index = std::min<std::size_t>(5U, room_count - 1U);
    for (std::size_t extra = 0; extra < 3U; ++extra) {
        const int side = static_cast<int>((extra + 1U) % 4U);
        const auto placement = side_placement(level.areas_[matrix_index], side, eye_height);
        const std::size_t destination_index = (matrix_index + 3U + extra * 2U + rotation) % room_count;
        PortalGate gate;
        gate.id = static_cast<std::uint32_t>(room_count + extra + 1U);
        gate.kind = extra == 1U ? PortalKind::window : PortalKind::door;
        gate.center = placement.center;
        gate.inward_normal = placement.inward;
        gate.destination = room_center(level.areas_[destination_index], eye_height);
        gate.destination_yaw_degrees = placement.yaw + 90.0F;
        gate.name = "Matrix Choice " + std::to_string(extra + 1U);
        gate.source_zone = level.areas_[matrix_index].name;
        gate.destination_zone = level.areas_[destination_index].name;
        level.portals_.push_back(std::move(gate));
    }

    return level;
}


LiminalLevel LiminalLevel::make_pivot5_traversal(std::uint64_t seed) {
    LiminalLevel level = make_pivot3_procedural(seed, 12U);
    constexpr float eye_height = 1.72F;
    constexpr float h = 5.8F;

    const WalkArea lab{628.0F, 656.0F, -173.0F, -127.0F, "Traversal & Water Lab"};
    level.areas_.push_back(lab);
    level.walls_.push_back(vertical_wall(lab.min_x, lab.min_z, lab.max_z, 1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(lab.max_x, lab.min_z, lab.max_z, -1.0F, 0.0F, h));
    level.walls_.push_back(horizontal_wall(lab.min_z, lab.min_x, lab.max_x, 0.0F, 1.0F, h));
    level.walls_.push_back(horizontal_wall(lab.max_z, lab.min_x, lab.max_x, 0.0F, -1.0F, h));

    level.obstacles_.push_back({630.5F, 633.0F, -164.0F, -161.5F, 0.25F, "GREEN STEP 0.25"});
    level.obstacles_.push_back({635.0F, 638.0F, -164.0F, -161.0F, 0.55F, "CYAN JUMP 0.55"});
    level.obstacles_.push_back({640.0F, 643.5F, -164.5F, -161.0F, 0.90F, "AMBER RUN JUMP 0.90"});
    level.obstacles_.push_back({646.0F, 650.0F, -165.0F, -161.0F, 1.35F, "RED MANTLE LIMIT 1.35"});
    level.obstacles_.push_back({632.0F, 638.0F, -153.0F, -149.0F, 0.42F, "LANDING PLATFORM"});
    level.obstacles_.push_back({647.0F, 652.0F, -153.0F, -149.0F, 0.70F, "WATER EXIT PLATFORM"});

    level.water_regions_.push_back({630.0F, 639.0F, -144.0F, -132.0F, 0.08F, -0.78F, "Shallow Almond Water"});
    level.water_regions_.push_back({643.0F, 653.5F, -144.0F, -132.0F, 0.08F, -2.85F, "Deep Almond Water"});

    level.traversal_lab_spawn_ = {642.0F, eye_height, -168.5F};

    PortalGate enter;
    enter.id = static_cast<std::uint32_t>(level.portals_.size() + 1U);
    enter.kind = PortalKind::door;
    // Keep laboratory access distinct from the procedural Reception portal.
    // Earlier builds placed both frames at the east-wall midpoint.
    enter.center = {(level.areas_.front().min_x + level.areas_.front().max_x) * 0.5F,
                    eye_height, level.areas_.front().max_z};
    enter.inward_normal = {0.0F, 0.0F, -1.0F};
    enter.destination = level.traversal_lab_spawn_;
    enter.destination_yaw_degrees = 90.0F;
    enter.name = "Traversal Lab Access";
    enter.source_zone = level.areas_.front().name;
    enter.destination_zone = lab.name;
    level.portals_.push_back(enter);

    PortalGate exit;
    exit.id = static_cast<std::uint32_t>(level.portals_.size() + 1U);
    exit.kind = PortalKind::door;
    exit.center = {lab.min_x, eye_height, -168.5F};
    exit.inward_normal = {1.0F, 0.0F, 0.0F};
    exit.destination = room_center(level.areas_.front(), eye_height);
    exit.destination_yaw_degrees = -90.0F;
    exit.name = "Return to Reception";
    exit.source_zone = lab.name;
    exit.destination_zone = level.areas_.front().name;
    level.portals_.push_back(exit);


    return level;
}

LiminalLevel LiminalLevel::make_pivot6_depth(std::uint64_t seed) {
    LiminalLevel level = make_pivot5_traversal(seed);
    constexpr float eye_height = 1.72F;
    constexpr float h = 5.8F;

    const WalkArea junction{680.0F, 708.0F, -180.0F, -148.0F, "Corridor Junction"};
    const WalkArea long_hall{708.0F, 792.0F, -168.0F, -160.0F, "Long Signal Hall"};
    const WalkArea nested{680.0F, 708.0F, -220.0F, -180.0F, "Nested Room Matrix"};
    // a2 removes the accidental overlap with the Traversal & Water Lab. The
    // shared boundary at x=656 now contains one deliberate two-way passage.
    const WalkArea fallen{656.0F, 680.0F, -180.0F, -148.0F, "Fallen Office"};
    const WalkArea shaft{792.0F, 810.0F, -178.0F, -150.0F, "Vertical Flood Shaft"};
    const WalkArea tunnel{810.0F, 870.0F, -168.0F, -160.0F, "Submerged Service Tunnel"};
    const WalkArea cavity{870.0F, 926.0F, -200.0F, -128.0F, "Open Pressure Cavity"};

    level.areas_.insert(level.areas_.end(), {junction, long_hall, nested, fallen, shaft, tunnel, cavity});

    // Replace Pivot 5's full east laboratory wall with a wall containing a
    // visible, physical passage into the Fallen Office.
    level.walls_.erase(std::remove_if(level.walls_.begin(), level.walls_.end(),
        [](const WallSegment& wall) {
            return approximately(wall.start.x, 656.0F) && approximately(wall.end.x, 656.0F) &&
                   approximately(wall.start.z, -173.0F) && approximately(wall.end.z, -127.0F);
        }), level.walls_.end());
    level.walls_.push_back(vertical_wall(656.0F, -173.0F, -166.0F, -1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(656.0F, -160.0F, -127.0F, -1.0F, 0.0F, h));

    // Corridor Junction: west/east openings, plus the south doorway into the
    // nested room. The north edge is intentionally solid.
    level.walls_.push_back(horizontal_wall(junction.min_z, junction.min_x, 692.0F, 0.0F, 1.0F, h));
    level.walls_.push_back(horizontal_wall(junction.min_z, 696.0F, junction.max_x, 0.0F, 1.0F, h));
    level.walls_.push_back(horizontal_wall(junction.max_z, junction.min_x, junction.max_x, 0.0F, -1.0F, h));
    level.walls_.push_back(vertical_wall(junction.min_x, junction.min_z, -166.0F, 1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(junction.min_x, -162.0F, junction.max_z, 1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(junction.max_x, junction.min_z, -166.0F, -1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(junction.max_x, -162.0F, junction.max_z, -1.0F, 0.0F, h));

    // Long hall and connected flood shaft. Open east/west ends are explicit
    // physical passages; only the narrow sides are walls.
    level.walls_.push_back(horizontal_wall(long_hall.min_z, long_hall.min_x, long_hall.max_x, 0.0F, 1.0F, h));
    level.walls_.push_back(horizontal_wall(long_hall.max_z, long_hall.min_x, long_hall.max_x, 0.0F, -1.0F, h));
    level.walls_.push_back(horizontal_wall(shaft.min_z, shaft.min_x, shaft.max_x, 0.0F, 1.0F, h, -14.0F));
    level.walls_.push_back(horizontal_wall(shaft.max_z, shaft.min_x, shaft.max_x, 0.0F, -1.0F, h, -14.0F));

    // Nested room with a clear north doorway and one blue glass wall. The glass
    // remains physically solid from both directions.
    level.walls_.push_back(vertical_wall(nested.min_x, nested.min_z, nested.max_z, 1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(nested.max_x, nested.min_z, nested.max_z, -1.0F, 0.0F, h));
    level.walls_.push_back(horizontal_wall(nested.min_z, nested.min_x, nested.max_x, 0.0F, 1.0F, h));
    level.walls_.push_back(horizontal_wall(nested.max_z, nested.min_x, 692.0F, 0.0F, -1.0F, h));
    level.walls_.push_back(horizontal_wall(nested.max_z, 696.0F, nested.max_x, 0.0F, -1.0F, h));
    level.obstacles_.push_back({686.0F, 687.0F, -211.0F, -190.0F, 3.4F, "NESTED WEST WALL"});
    level.obstacles_.push_back({701.0F, 702.0F, -211.0F, -190.0F, 3.4F, "GLASS NESTED EAST WALL"});
    level.obstacles_.push_back({686.0F, 702.0F, -211.0F, -210.0F, 3.4F, "NESTED SOUTH WALL"});
    level.obstacles_.push_back({686.0F, 692.0F, -191.0F, -190.0F, 3.4F, "NESTED NORTH LEFT"});
    level.obstacles_.push_back({696.0F, 702.0F, -191.0F, -190.0F, 3.4F, "NESTED NORTH RIGHT"});

    // Fallen office: the west passage connects to the Traversal Lab and the east
    // doorway connects to the Corridor Junction. Diagonal ribs remain climbable.
    level.walls_.push_back(vertical_wall(fallen.min_x, fallen.min_z, -166.0F, 1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(fallen.min_x, -160.0F, fallen.max_z, 1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(fallen.max_x, fallen.min_z, -166.0F, -1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(fallen.max_x, -162.0F, fallen.max_z, -1.0F, 0.0F, h));
    level.walls_.push_back(horizontal_wall(fallen.min_z, fallen.min_x, fallen.max_x, 0.0F, 1.0F, h));
    level.walls_.push_back(horizontal_wall(fallen.max_z, fallen.min_x, fallen.max_x, 0.0F, -1.0F, h));
    level.obstacles_.push_back({661.0F, 662.0F, -176.0F, -152.0F, 2.7F, "FALLEN OFFICE RIB A"});
    level.obstacles_.push_back({668.0F, 669.0F, -176.0F, -152.0F, 3.6F, "FALLEN OFFICE RIB B"});
    level.obstacles_.push_back({675.0F, 676.0F, -176.0F, -152.0F, 4.5F, "FALLEN OFFICE RIB C"});
    level.obstacles_.push_back({661.5F, 666.5F, -155.0F, -151.5F, 0.42F, "FALLEN WATER EXIT PLATFORM"});

    // Deep underwater tunnel and exposed cavity use walls that extend below the
    // zero plane. Their open ends are represented by explicit connections.
    level.walls_.push_back(horizontal_wall(tunnel.min_z, tunnel.min_x, tunnel.max_x, 0.0F, 1.0F, h, -6.5F));
    level.walls_.push_back(horizontal_wall(tunnel.max_z, tunnel.min_x, tunnel.max_x, 0.0F, -1.0F, h, -6.5F));
    level.walls_.push_back(horizontal_wall(cavity.min_z, cavity.min_x, cavity.max_x, 0.0F, 1.0F, h, -22.0F));
    level.walls_.push_back(horizontal_wall(cavity.max_z, cavity.min_x, cavity.max_x, 0.0F, -1.0F, h, -22.0F));
    level.walls_.push_back(vertical_wall(cavity.max_x, cavity.min_z, cavity.max_z, -1.0F, 0.0F, h, -22.0F));

    level.water_regions_.push_back({792.0F, 810.0F, -178.0F, -150.0F, 0.10F, -14.0F,
                                    "Thin Blue Flood Shaft", 0.82F, false, true, 0.92F});
    level.water_regions_.push_back({810.0F, 870.0F, -168.0F, -160.0F, 0.10F, -6.5F,
                                    "Thick Green Service Water", 1.48F, false, true, 1.18F});
    level.water_regions_.push_back({870.0F, 926.0F, -200.0F, -128.0F, 0.10F, -22.0F,
                                    "Open Pressure Cavity Water", 1.00F, true, false, 1.08F});

    level.obstacles_.push_back({686.5F, 689.5F, -174.0F, -170.5F, 1.05F, "SAVE JUMP LAUNCH"});
    level.obstacles_.push_back({699.0F, 702.0F, -174.0F, -170.5F, 1.05F, "SAVE JUMP LANDING"});
    level.obstacles_.push_back({788.0F, 792.0F, -166.0F, -162.0F, 1.00F, "SAVE JUMP WATER LEDGE"});
    level.obstacles_.push_back({800.2F, 804.2F, -162.4F, -158.6F, 0.65F, "ALMOND TECH STATION"});

    level.depth_lab_spawn_ = {694.0F, eye_height, -164.0F};
    level.almond_tech_position_ = {802.2F, 0.65F, -160.5F};
    level.has_almond_tech_station_ = true;

    // Explicit physical connection metadata powers destination-room previews,
    // door taxonomy, and future sound/light propagation.
    level.connections_.push_back({"Traversal & Water Lab", fallen.name,
                                  {656.0F, eye_height, -163.0F}, 3.0F, 8.0F,
                                  ConnectionKind::passage, true});
    level.connections_.push_back({fallen.name, junction.name,
                                  {680.0F, eye_height, -164.0F}, 2.0F, 8.0F,
                                  ConnectionKind::open_doorway, true});
    level.connections_.push_back({junction.name, nested.name,
                                  {694.0F, eye_height, -180.0F}, 2.0F, 8.0F,
                                  ConnectionKind::framed_doorway, true});
    level.connections_.push_back({junction.name, long_hall.name,
                                  {708.0F, eye_height, -164.0F}, 2.0F, 9.0F,
                                  ConnectionKind::open_doorway, true});
    level.connections_.push_back({long_hall.name, shaft.name,
                                  {792.0F, eye_height, -164.0F}, 2.0F, 10.0F,
                                  ConnectionKind::hole, true});
    level.connections_.push_back({shaft.name, tunnel.name,
                                  {810.0F, 0.10F, -164.0F}, 2.0F, 10.0F,
                                  ConnectionKind::passage, true});
    level.connections_.push_back({tunnel.name, cavity.name,
                                  {870.0F, 0.10F, -164.0F}, 2.0F, 11.0F,
                                  ConnectionKind::open_doorway, true});

    // A few real light anchors let fill range react to local illumination. The
    // actual point cloud remains the visible representation.
    level.lights_.push_back({{666.0F, 4.9F, -164.0F}, 9.0F, 0.75F, fallen.name});
    level.lights_.push_back({{694.0F, 4.9F, -164.0F}, 10.0F, 0.85F, junction.name});
    level.lights_.push_back({{694.0F, 4.6F, -200.0F}, 10.0F, 0.75F, nested.name});
    level.lights_.push_back({{724.0F, 4.9F, -164.0F}, 12.0F, 0.90F, long_hall.name});
    level.lights_.push_back({{752.0F, 4.9F, -164.0F}, 12.0F, 0.95F, long_hall.name});
    level.lights_.push_back({{780.0F, 4.9F, -164.0F}, 12.0F, 0.90F, long_hall.name});
    level.lights_.push_back({{802.0F, 1.2F, -160.5F}, 10.0F, 0.95F, shaft.name});
    level.lights_.push_back({{830.0F, -1.0F, -164.0F}, 11.0F, 0.62F, tunnel.name});
    level.lights_.push_back({{858.0F, -1.2F, -164.0F}, 11.0F, 0.58F, tunnel.name});
    level.lights_.push_back({{888.0F, -2.0F, -164.0F}, 13.0F, 0.48F, cavity.name});

    PortalGate enter;
    enter.id = static_cast<std::uint32_t>(level.portals_.size() + 1U);
    enter.kind = PortalKind::door;
    enter.center = {level.areas_.front().min_x, eye_height,
                    (level.areas_.front().min_z + level.areas_.front().max_z) * 0.5F};
    enter.inward_normal = {1.0F, 0.0F, 0.0F};
    enter.destination = level.depth_lab_spawn_;
    enter.destination_yaw_degrees = 0.0F;
    enter.name = "Room Complex Access";
    enter.source_zone = level.areas_.front().name;
    enter.destination_zone = junction.name;
    level.portals_.push_back(enter);

    PortalGate exit;
    exit.id = static_cast<std::uint32_t>(level.portals_.size() + 1U);
    exit.kind = PortalKind::door;
    exit.center = {junction.min_x, eye_height, -176.0F};
    exit.inward_normal = {1.0F, 0.0F, 0.0F};
    exit.destination = room_center(level.areas_.front(), eye_height);
    exit.destination_yaw_degrees = -90.0F;
    exit.name = "Complex Return";
    exit.source_zone = junction.name;
    exit.destination_zone = level.areas_.front().name;
    level.portals_.push_back(exit);

    return level;
}


LiminalLevel LiminalLevel::make_pivot7_thresholds(std::uint64_t seed) {
    LiminalLevel level = make_pivot6_depth(seed);
    constexpr float eye_height = 1.72F;
    constexpr float h = 5.8F;

    const WalkArea gallery{680.0F, 708.0F, -148.0F, -116.0F, "Threshold Gallery"};
    const WalkArea window_annex{708.0F, 724.0F, -140.0F, -124.0F, "Raised Window Annex"};
    const WalkArea passage_annex{664.0F, 680.0F, -140.0F, -124.0F, "Broken Passage Annex"};
    level.areas_.insert(level.areas_.end(), {gallery, window_annex, passage_annex});

    // Corridor Junction's north wall becomes a framed two-way opening into the
    // threshold gallery. The remaining wall pieces stay solid from both sides.
    level.walls_.erase(std::remove_if(level.walls_.begin(), level.walls_.end(),
        [](const WallSegment& wall) {
            return approximately(wall.start.z, -148.0F) && approximately(wall.end.z, -148.0F) &&
                   approximately(wall.start.x, 680.0F) && approximately(wall.end.x, 708.0F);
        }), level.walls_.end());
    level.walls_.push_back(horizontal_wall(-148.0F, 680.0F, 691.8F, 0.0F, 1.0F, h));
    level.walls_.push_back(horizontal_wall(-148.0F, 696.2F, 708.0F, 0.0F, 1.0F, h));

    // Gallery shell: south framed doorway, west broken passage, east raised
    // window, and a solid north wall.
    level.walls_.push_back(horizontal_wall(gallery.max_z, gallery.min_x, gallery.max_x, 0.0F, -1.0F, h));
    level.walls_.push_back(vertical_wall(gallery.min_x, gallery.min_z, -134.2F, 1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(gallery.min_x, -129.8F, gallery.max_z, 1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(gallery.max_x, gallery.min_z, -134.2F, -1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(gallery.max_x, -129.8F, gallery.max_z, -1.0F, 0.0F, h));
    // Raised-window sill and lintel leave a vertical opening from 0.90m to 2.82m.
    level.walls_.push_back(vertical_wall(gallery.max_x, -134.2F, -129.8F, -1.0F, 0.0F, 0.90F));
    level.walls_.push_back(vertical_wall(gallery.max_x, -134.2F, -129.8F, -1.0F, 0.0F, h, 2.82F));

    // Annex shells leave their shared threshold sides open.
    level.walls_.push_back(horizontal_wall(window_annex.min_z, window_annex.min_x, window_annex.max_x, 0.0F, 1.0F, h));
    level.walls_.push_back(horizontal_wall(window_annex.max_z, window_annex.min_x, window_annex.max_x, 0.0F, -1.0F, h));
    level.walls_.push_back(vertical_wall(window_annex.max_x, window_annex.min_z, window_annex.max_z, -1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(window_annex.min_x, window_annex.min_z, -134.2F, 1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(window_annex.min_x, -129.8F, window_annex.max_z, 1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(window_annex.min_x, -134.2F, -129.8F, 1.0F, 0.0F, 0.90F));
    level.walls_.push_back(vertical_wall(window_annex.min_x, -134.2F, -129.8F, 1.0F, 0.0F, h, 2.82F));

    level.walls_.push_back(horizontal_wall(passage_annex.min_z, passage_annex.min_x, passage_annex.max_x, 0.0F, 1.0F, h));
    level.walls_.push_back(horizontal_wall(passage_annex.max_z, passage_annex.min_x, passage_annex.max_x, 0.0F, -1.0F, h));
    level.walls_.push_back(vertical_wall(passage_annex.min_x, passage_annex.min_z, passage_annex.max_z, 1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(passage_annex.max_x, passage_annex.min_z, -134.2F, -1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(passage_annex.max_x, -129.8F, passage_annex.max_z, -1.0F, 0.0F, h));

    // Solid blue glass cubicle. Its doorway faces south and remains ordinary
    // geometry; the glass is intentionally visible but not passable.
    level.obstacles_.push_back({686.0F, 687.0F, -128.0F, -118.5F, 3.2F, "GLASS CUBICLE WEST"});
    level.obstacles_.push_back({701.0F, 702.0F, -128.0F, -118.5F, 3.2F, "GLASS CUBICLE EAST"});
    level.obstacles_.push_back({686.0F, 702.0F, -119.5F, -118.5F, 3.2F, "GLASS CUBICLE NORTH"});
    level.obstacles_.push_back({686.0F, 692.0F, -129.0F, -128.0F, 3.2F, "GLASS CUBICLE SOUTH LEFT"});
    level.obstacles_.push_back({696.0F, 702.0F, -129.0F, -128.0F, 3.2F, "GLASS CUBICLE SOUTH RIGHT"});

    level.connections_.push_back({"Corridor Junction", gallery.name,
                                  {694.0F, eye_height, -148.0F}, 2.2F, 9.0F,
                                  ConnectionKind::framed_doorway, true});
    level.connections_.push_back({gallery.name, window_annex.name,
                                  {708.0F, 1.86F, -132.0F}, 2.2F, 8.0F,
                                  ConnectionKind::window, true});
    level.connections_.push_back({gallery.name, passage_annex.name,
                                  {680.0F, eye_height, -132.0F}, 2.2F, 8.0F,
                                  ConnectionKind::passage, true});

    level.lights_.push_back({{694.0F, 4.8F, -142.0F}, 11.0F, 0.92F, gallery.name});
    level.lights_.push_back({{716.0F, 4.6F, -132.0F}, 8.5F, 0.78F, window_annex.name});
    level.lights_.push_back({{672.0F, 4.4F, -132.0F}, 8.0F, 0.58F, passage_annex.name});
    level.threshold_lab_spawn_ = {694.0F, eye_height, -142.0F};
    return level;
}

LiminalLevel LiminalLevel::make_pivot8_submerged(std::uint64_t seed) {
    LiminalLevel level = make_pivot7_thresholds(seed);
    constexpr float eye_height = 1.72F;
    constexpr float h = 5.8F;

    // Pivot 8 completes the structural walls around all three water-connected
    // apertures. Earlier phases intentionally left the whole shared boundary
    // open and drew only a narrow connection frame, which made the rest of the
    // wall disappear wherever water touched the threshold.
    auto add_wet_aperture_wall = [&](float x, float min_z, float max_z,
                                     float center_z, float half_width,
                                     float base_y, float top_y) {
        const float opening_min = center_z - half_width;
        const float opening_max = center_z + half_width;
        if (min_z < opening_min) {
            level.walls_.push_back(vertical_wall(x, min_z, opening_min,
                                                 1.0F, 0.0F, h, base_y));
        }
        if (opening_max < max_z) {
            level.walls_.push_back(vertical_wall(x, opening_max, max_z,
                                                 1.0F, 0.0F, h, base_y));
        }
        if (top_y < h - 0.01F) {
            level.walls_.push_back(vertical_wall(x, opening_min, opening_max,
                                                 1.0F, 0.0F, h, top_y));
        }
    };

    add_wet_aperture_wall(792.0F, -178.0F, -150.0F,
                          -164.0F, 2.0F, -14.0F, h);
    add_wet_aperture_wall(810.0F, -178.0F, -150.0F,
                          -164.0F, 2.0F, -14.0F, 4.20F);
    add_wet_aperture_wall(870.0F, -200.0F, -128.0F,
                          -164.0F, 2.0F, -22.0F, 4.20F);

    // Dedicated wet-threshold laboratory attached to the east side of the open
    // pressure cavity. It gives one repeatable wall/water/aperture case without
    // changing the accepted traversal route.
    const WalkArea wet_lab{926.0F, 958.0F, -184.0F, -144.0F,
                           "Submerged Boundary Lab"};
    level.areas_.push_back(wet_lab);

    // Replace the cavity's previous full east wall with a properly bounded
    // submerged passage into the new lab.
    level.walls_.erase(std::remove_if(level.walls_.begin(), level.walls_.end(),
        [](const WallSegment& wall) {
            return approximately(wall.start.x, 926.0F) &&
                   approximately(wall.end.x, 926.0F) &&
                   approximately(wall.start.z, -200.0F) &&
                   approximately(wall.end.z, -128.0F);
        }), level.walls_.end());
    add_wet_aperture_wall(926.0F, -200.0F, -128.0F,
                          -164.0F, 2.5F, -22.0F, 4.20F);

    level.walls_.push_back(vertical_wall(wet_lab.max_x, wet_lab.min_z,
                                         wet_lab.max_z, -1.0F, 0.0F, h, -4.2F));
    level.walls_.push_back(horizontal_wall(wet_lab.min_z, wet_lab.min_x,
                                           wet_lab.max_x, 0.0F, 1.0F, h, -4.2F));
    level.walls_.push_back(horizontal_wall(wet_lab.max_z, wet_lab.min_x,
                                           wet_lab.max_x, 0.0F, -1.0F, h, -4.2F));

    level.water_regions_.push_back({wet_lab.min_x, wet_lab.max_x,
                                    wet_lab.min_z, wet_lab.max_z,
                                    0.10F, -4.20F,
                                    "Blue-Green Boundary Water",
                                    1.15F, false, true, 1.02F});
    level.obstacles_.push_back({934.0F, 940.0F, -167.0F, -161.0F,
                                0.65F, "WATER BOUNDARY OBSERVATION PLATFORM"});

    level.connections_.push_back({"Open Pressure Cavity", wet_lab.name,
                                  {926.0F, 0.10F, -164.0F}, 2.5F, 11.0F,
                                  ConnectionKind::passage, true});
    level.lights_.push_back({{940.0F, -0.8F, -164.0F}, 12.0F, 0.72F,
                             wet_lab.name});
    level.lights_.push_back({{952.0F, -2.2F, -152.0F}, 8.5F, 0.48F,
                             wet_lab.name});

    level.submerged_lab_spawn_ = {937.0F, eye_height + 0.65F, -164.0F};

    // Procedural and laboratory portals may independently select the same wall
    // coordinate. Move later duplicates along that wall so one source room never
    // renders two overlapping frames or triggers at the same threshold.
    for (std::size_t i = 0; i < level.portals_.size(); ++i) {
        PortalGate& portal = level.portals_[i];
        const WalkArea* area = find_area(level.areas_, portal.source_zone);
        if (area == nullptr) continue;
        for (std::size_t j = 0; j < i; ++j) {
            const PortalGate& earlier = level.portals_[j];
            if (earlier.source_zone != portal.source_zone) continue;
            if (distance_xz(earlier.center, portal.center) > 0.10F) continue;

            const bool on_vertical_wall =
                approximately(portal.center.x, area->min_x, 0.10F) ||
                approximately(portal.center.x, area->max_x, 0.10F);
            const float margin = portal.half_width + 0.45F;
            const float offset = portal.half_width * 2.8F + 0.80F;
            if (on_vertical_wall) {
                const float plus = std::clamp(portal.center.z + offset,
                                              area->min_z + margin,
                                              area->max_z - margin);
                const float minus = std::clamp(portal.center.z - offset,
                                               area->min_z + margin,
                                               area->max_z - margin);
                portal.center.z = std::abs(plus - earlier.center.z) >=
                                  std::abs(minus - earlier.center.z) ? plus : minus;
            } else {
                const float plus = std::clamp(portal.center.x + offset,
                                              area->min_x + margin,
                                              area->max_x - margin);
                const float minus = std::clamp(portal.center.x - offset,
                                               area->min_x + margin,
                                               area->max_x - margin);
                portal.center.x = std::abs(plus - earlier.center.x) >=
                                  std::abs(minus - earlier.center.x) ? plus : minus;
            }
        }
    }

    // Pivot 8 a2 derives every physical threshold surround from the same
    // connection aperture used by collision, preview clipping, frames, and
    // submerged wall coating. This replaces inconsistent hand-authored edges.
    level.rebuild_threshold_envelopes();
    return level;
}


LiminalLevel LiminalLevel::make_pivot9_combat(std::uint64_t seed) {
    LiminalLevel level = make_pivot8_submerged(seed);
    constexpr float eye_height = 1.72F;
    constexpr float h = 5.8F;

    const WalkArea range{980.0F, 1028.0F, -180.0F, -140.0F,
                         "Live-Fire Signal Range"};
    level.areas_.push_back(range);
    level.walls_.push_back(vertical_wall(range.min_x, range.min_z, range.max_z,
                                         1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(range.max_x, range.min_z, range.max_z,
                                         -1.0F, 0.0F, h));
    level.walls_.push_back(horizontal_wall(range.min_z, range.min_x, range.max_x,
                                           0.0F, 1.0F, h));
    level.walls_.push_back(horizontal_wall(range.max_z, range.min_x, range.max_x,
                                           0.0F, -1.0F, h));

    level.obstacles_.push_back({992.0F, 996.0F, -168.0F, -164.0F,
                                1.15F, "SIGNAL RANGE COVER A"});
    level.obstacles_.push_back({1012.0F, 1016.0F, -158.0F, -154.0F,
                                1.55F, "SIGNAL RANGE COVER B"});
    level.obstacles_.push_back({1000.0F, 1008.0F, -145.5F, -143.5F,
                                0.75F, "DEATH PROOF CLAIM TABLE"});

    level.combat_lab_spawn_ = {987.0F, eye_height, -160.0F};
    level.lights_.push_back({{990.0F, 4.7F, -160.0F}, 13.0F, 0.82F, range.name});
    level.lights_.push_back({{1018.0F, 4.5F, -160.0F}, 12.0F, 0.54F, range.name});

    const WalkArea& reception = level.areas_.front();
    PortalGate enter;
    enter.id = static_cast<std::uint32_t>(level.portals_.size() + 1U);
    enter.kind = PortalKind::door;
    enter.center = {reception.max_x, eye_height,
                    std::clamp(reception.min_z + 2.25F, reception.min_z + 1.4F,
                               reception.max_z - 1.4F)};
    enter.inward_normal = {-1.0F, 0.0F, 0.0F};
    enter.destination = level.combat_lab_spawn_;
    enter.destination_yaw_degrees = 0.0F;
    enter.name = "Live-Fire Range Access";
    enter.source_zone = reception.name;
    enter.destination_zone = range.name;
    level.portals_.push_back(enter);

    PortalGate exit;
    exit.id = static_cast<std::uint32_t>(level.portals_.size() + 1U);
    exit.kind = PortalKind::door;
    exit.center = {range.min_x, eye_height, -160.0F};
    exit.inward_normal = {1.0F, 0.0F, 0.0F};
    exit.destination = room_center(reception, eye_height);
    exit.destination_yaw_degrees = -90.0F;
    exit.name = "Range Return";
    exit.source_zone = range.name;
    exit.destination_zone = reception.name;
    level.portals_.push_back(exit);

    return level;
}


LiminalLevel LiminalLevel::make_pivot11_scavenging(std::uint64_t seed) {
    LiminalLevel level = make_pivot9_combat(seed);
    constexpr float eye_height = 1.72F;
    constexpr float h = 5.8F;

    const WalkArea exchange{1040.0F, 1088.0F, -180.0F, -140.0F,
                            "Scavenger Exchange"};
    level.areas_.push_back(exchange);
    level.walls_.push_back(vertical_wall(exchange.min_x, exchange.min_z, exchange.max_z,
                                         1.0F, 0.0F, h));
    level.walls_.push_back(vertical_wall(exchange.max_x, exchange.min_z, exchange.max_z,
                                         -1.0F, 0.0F, h));
    level.walls_.push_back(horizontal_wall(exchange.min_z, exchange.min_x, exchange.max_x,
                                           0.0F, 1.0F, h));
    level.walls_.push_back(horizontal_wall(exchange.max_z, exchange.min_x, exchange.max_x,
                                           0.0F, -1.0F, h));

    level.obstacles_.push_back({1061.82F, 1062.18F, -161.45F, -158.55F,
                                2.18F, "THIN SCAVENGER AR TERMINAL"});
    level.obstacles_.push_back({1071.55F, 1074.45F, -150.18F, -149.82F,
                                2.38F, "THIN ALMOND AR VENDING TERMINAL"});
    level.obstacles_.push_back({1071.55F, 1074.45F, -170.18F, -169.82F,
                                2.38F, "THIN AMMO TABLET"});
    level.obstacles_.push_back({1050.0F, 1058.0F, -176.0F, -173.5F,
                                0.58F, "PARKOUR SORTING BENCH"});
    level.obstacles_.push_back({1077.0F, 1083.0F, -145.5F, -143.0F,
                                0.58F, "AUTO STEP DROP PALLET"});

    level.economy_lab_spawn_ = {1047.0F, eye_height, -160.0F};
    level.lights_.push_back({{1052.0F, 4.8F, -160.0F}, 15.0F, 0.74F, exchange.name});
    level.lights_.push_back({{1074.0F, 4.4F, -150.0F}, 10.0F, 0.58F, exchange.name});
    level.lights_.push_back({{1074.0F, 4.4F, -170.0F}, 10.0F, 0.52F, exchange.name});

    const WalkArea& reception = level.areas_.front();
    PortalGate enter;
    enter.id = static_cast<std::uint32_t>(level.portals_.size() + 1U);
    enter.kind = PortalKind::door;
    enter.center = {reception.max_x, eye_height,
                    std::clamp(reception.max_z - 2.15F, reception.min_z + 1.4F,
                               reception.max_z - 1.4F)};
    enter.inward_normal = {-1.0F, 0.0F, 0.0F};
    enter.destination = level.economy_lab_spawn_;
    enter.destination_yaw_degrees = 0.0F;
    enter.name = "Scavenger Exchange Access";
    enter.source_zone = reception.name;
    enter.destination_zone = exchange.name;
    level.portals_.push_back(enter);

    PortalGate exit;
    exit.id = static_cast<std::uint32_t>(level.portals_.size() + 1U);
    exit.kind = PortalKind::door;
    exit.center = {exchange.min_x, eye_height, -160.0F};
    exit.inward_normal = {1.0F, 0.0F, 0.0F};
    exit.destination = room_center(reception, eye_height);
    exit.destination_yaw_degrees = -90.0F;
    exit.name = "Exchange Return";
    exit.source_zone = exchange.name;
    exit.destination_zone = reception.name;
    level.portals_.push_back(exit);

    return level;
}

float LiminalLevel::threshold_floor_near(math::Vec3 position) const noexcept {
    if (const auto* water = water_at(position.x, position.z)) return water->bottom_y;
    return floor_height_;
}

void LiminalLevel::rebuild_threshold_envelopes() {
    threshold_envelopes_.clear();
    constexpr float plane_epsilon = 0.06F;
    constexpr float span_epsilon = 0.015F;

    for (const RoomConnection& connection : connections_) {
        const WalkArea* area_a = find_area(areas_, connection.zone_a);
        const WalkArea* area_b = find_area(areas_, connection.zone_b);
        if (area_a == nullptr || area_b == nullptr) continue;

        bool vertical_plane = false;
        float plane = 0.0F;
        float span_min = 0.0F;
        float span_max = 0.0F;
        bool shared_boundary = true;

        if (approximately(area_a->max_x, area_b->min_x, plane_epsilon)) {
            vertical_plane = true;
            plane = (area_a->max_x + area_b->min_x) * 0.5F;
            span_min = std::max(area_a->min_z, area_b->min_z);
            span_max = std::min(area_a->max_z, area_b->max_z);
        } else if (approximately(area_a->min_x, area_b->max_x, plane_epsilon)) {
            vertical_plane = true;
            plane = (area_a->min_x + area_b->max_x) * 0.5F;
            span_min = std::max(area_a->min_z, area_b->min_z);
            span_max = std::min(area_a->max_z, area_b->max_z);
        } else if (approximately(area_a->max_z, area_b->min_z, plane_epsilon)) {
            vertical_plane = false;
            plane = (area_a->max_z + area_b->min_z) * 0.5F;
            span_min = std::max(area_a->min_x, area_b->min_x);
            span_max = std::min(area_a->max_x, area_b->max_x);
        } else if (approximately(area_a->min_z, area_b->max_z, plane_epsilon)) {
            vertical_plane = false;
            plane = (area_a->min_z + area_b->max_z) * 0.5F;
            span_min = std::max(area_a->min_x, area_b->min_x);
            span_max = std::min(area_a->max_x, area_b->max_x);
        } else {
            shared_boundary = false;
        }

        if (!shared_boundary || span_max <= span_min + span_epsilon) continue;

        ConnectionAperture aperture = connection_aperture(connection, connection.zone_a);
        const float tangent_center = vertical_plane ? aperture.center.z : aperture.center.x;
        const float requested_min = tangent_center - aperture.half_width;
        const float requested_max = tangent_center + aperture.half_width;
        const float opening_min = std::clamp(requested_min, span_min, span_max);
        const float opening_max = std::clamp(requested_max, span_min, span_max);
        if (opening_max <= opening_min + span_epsilon) continue;

        if (vertical_plane) {
            aperture.center.x = plane;
            aperture.center.z = (opening_min + opening_max) * 0.5F;
            const float direction = room_center(*area_b, aperture.center.y).x >=
                                    room_center(*area_a, aperture.center.y).x ? 1.0F : -1.0F;
            aperture.normal = {direction, 0.0F, 0.0F};
        } else {
            aperture.center.z = plane;
            aperture.center.x = (opening_min + opening_max) * 0.5F;
            const float direction = room_center(*area_b, aperture.center.y).z >=
                                    room_center(*area_a, aperture.center.y).z ? 1.0F : -1.0F;
            aperture.normal = {0.0F, 0.0F, direction};
        }
        aperture.half_width = (opening_max - opening_min) * 0.5F;

        const math::Vec3 sample_a{
            aperture.center.x - aperture.normal.x * 0.35F,
            aperture.center.y,
            aperture.center.z - aperture.normal.z * 0.35F};
        const math::Vec3 sample_b{
            aperture.center.x + aperture.normal.x * 0.35F,
            aperture.center.y,
            aperture.center.z + aperture.normal.z * 0.35F};
        const float floor_a = threshold_floor_near(sample_a);
        const float floor_b = threshold_floor_near(sample_b);
        const float base_y = std::min(floor_a, floor_b);
        aperture.bottom_y = std::clamp(aperture.bottom_y, base_y, ceiling_height_);
        aperture.top_y = std::clamp(aperture.top_y, aperture.bottom_y + 0.05F,
                                    ceiling_height_);

        // Remove every old wall fragment inside the shared boundary span while
        // preserving portions beyond the overlap. This eliminates duplicate,
        // offset, and one-sided hand-authored surrounds.
        std::vector<WallSegment> retained;
        retained.reserve(walls_.size() + 6U);
        for (const WallSegment& wall : walls_) {
            const bool wall_vertical = approximately(wall.start.x, wall.end.x, plane_epsilon);
            const bool wall_horizontal = approximately(wall.start.z, wall.end.z, plane_epsilon);
            const bool same_plane = vertical_plane
                ? (wall_vertical && approximately(wall.start.x, plane, plane_epsilon))
                : (wall_horizontal && approximately(wall.start.z, plane, plane_epsilon));
            if (!same_plane) {
                retained.push_back(wall);
                continue;
            }

            const float wall_min = vertical_plane
                ? std::min(wall.start.z, wall.end.z)
                : std::min(wall.start.x, wall.end.x);
            const float wall_max = vertical_plane
                ? std::max(wall.start.z, wall.end.z)
                : std::max(wall.start.x, wall.end.x);
            if (wall_max <= span_min + span_epsilon ||
                wall_min >= span_max - span_epsilon) {
                retained.push_back(wall);
                continue;
            }

            if (wall_min < span_min - span_epsilon) {
                retained.push_back(vertical_plane
                    ? vertical_wall(plane, wall_min, span_min,
                                    wall.inward_normal.x, wall.inward_normal.z,
                                    wall.height, wall.base_y)
                    : horizontal_wall(plane, wall_min, span_min,
                                      wall.inward_normal.x, wall.inward_normal.z,
                                      wall.height, wall.base_y));
            }
            if (wall_max > span_max + span_epsilon) {
                retained.push_back(vertical_plane
                    ? vertical_wall(plane, span_max, wall_max,
                                    wall.inward_normal.x, wall.inward_normal.z,
                                    wall.height, wall.base_y)
                    : horizontal_wall(plane, span_max, wall_max,
                                      wall.inward_normal.x, wall.inward_normal.z,
                                      wall.height, wall.base_y));
            }
        }
        walls_ = std::move(retained);

        ThresholdEnvelope envelope;
        envelope.zone_a = connection.zone_a;
        envelope.zone_b = connection.zone_b;
        envelope.aperture = aperture;
        envelope.span_min = span_min;
        envelope.span_max = span_max;
        envelope.base_y = base_y;
        envelope.ceiling_y = ceiling_height_;
        envelope.vertical_plane = vertical_plane;

        const float nx = vertical_plane
            ? (aperture.normal.x >= 0.0F ? -1.0F : 1.0F)
            : 0.0F;
        const float nz = vertical_plane
            ? 0.0F
            : (aperture.normal.z >= 0.0F ? -1.0F : 1.0F);

        auto append_panel = [&](float first, float second, float panel_base,
                                float panel_top) {
            if (second <= first + span_epsilon ||
                panel_top <= panel_base + span_epsilon) return;
            WallSegment panel = vertical_plane
                ? vertical_wall(plane, first, second, nx, nz, panel_top, panel_base)
                : horizontal_wall(plane, first, second, nx, nz, panel_top, panel_base);
            walls_.push_back(panel);
            envelope.panels.push_back(panel);
        };

        append_panel(span_min, opening_min, base_y, ceiling_height_);
        append_panel(opening_max, span_max, base_y, ceiling_height_);
        append_panel(opening_min, opening_max, base_y, aperture.bottom_y);
        append_panel(opening_min, opening_max, aperture.top_y, ceiling_height_);
        threshold_envelopes_.push_back(std::move(envelope));
    }
}

bool LiminalLevel::point_is_walkable(float x, float z) const noexcept {
    for (const WalkArea& area : areas_) {
        if (within(x, area.min_x, area.max_x) && within(z, area.min_z, area.max_z)) return true;
    }
    return false;
}

const SolidObstacle* LiminalLevel::obstacle_at(float x, float z, float radius) const noexcept {
    for (const SolidObstacle& obstacle : obstacles_) {
        const bool overlap_x = x + radius > obstacle.min_x && x - radius < obstacle.max_x;
        const bool overlap_z = z + radius > obstacle.min_z && z - radius < obstacle.max_z;
        if (overlap_x && overlap_z) return &obstacle;
    }
    return nullptr;
}

const SolidObstacle* LiminalLevel::climbable_obstacle_near(float x, float z, float radius,
                                                               float maximum_top) const noexcept {
    const SolidObstacle* nearest = nullptr;
    float nearest_distance = 0.0F;
    for (const SolidObstacle& obstacle : obstacles_) {
        if (obstacle.height > maximum_top) continue;
        const float closest_x = std::clamp(x, obstacle.min_x, obstacle.max_x);
        const float closest_z = std::clamp(z, obstacle.min_z, obstacle.max_z);
        const float dx = x - closest_x;
        const float dz = z - closest_z;
        const float distance = std::sqrt(dx * dx + dz * dz);
        if (distance > radius) continue;
        if (nearest == nullptr || distance < nearest_distance) {
            nearest = &obstacle;
            nearest_distance = distance;
        }
    }
    return nearest;
}

const WaterRegion* LiminalLevel::water_at(float x, float z) const noexcept {
    for (const WaterRegion& water : water_regions_) {
        if (within(x, water.min_x, water.max_x) && within(z, water.min_z, water.max_z)) return &water;
    }
    return nullptr;
}

float LiminalLevel::ground_height_at(float x, float z) const noexcept {
    float ground = floor_height_;
    if (const auto* water = water_at(x, z)) ground = water->bottom_y;
    for (const SolidObstacle& obstacle : obstacles_) {
        if (within(x, obstacle.min_x, obstacle.max_x) && within(z, obstacle.min_z, obstacle.max_z)) {
            ground = std::max(ground, obstacle.height);
        }
    }
    return ground;
}

std::string_view LiminalLevel::surface_name_at(float x, float z) const noexcept {
    if (const auto* obstacle = obstacle_at(x, z)) return obstacle->name;
    if (const auto* water = water_at(x, z)) return water->name;
    return "Liminal Floor";
}

bool LiminalLevel::can_occupy(float x, float z, float radius) const noexcept {
    return can_occupy_3d(x, z, floor_height_, 1.72F, radius, 0.0F);
}

bool LiminalLevel::can_occupy_3d(float x, float z, float feet_y, float player_height,
                                 float radius, float step_height) const noexcept {
    constexpr std::array<std::array<float, 2>, 9> samples{{
        {{0.0F, 0.0F}}, {{1.0F, 0.0F}}, {{-1.0F, 0.0F}}, {{0.0F, 1.0F}}, {{0.0F, -1.0F}},
        {{0.70710678F, 0.70710678F}}, {{-0.70710678F, 0.70710678F}},
        {{0.70710678F, -0.70710678F}}, {{-0.70710678F, -0.70710678F}},
    }};
    for (const auto& sample : samples) {
        if (!point_is_walkable(x + sample[0] * radius, z + sample[1] * radius)) return false;
    }
    const float head_y = feet_y + player_height;
    for (const SolidObstacle& obstacle : obstacles_) {
        const bool overlap_x = x + radius > obstacle.min_x && x - radius < obstacle.max_x;
        const bool overlap_z = z + radius > obstacle.min_z && z - radius < obstacle.max_z;
        if (!overlap_x || !overlap_z) continue;
        const bool above_top = feet_y >= obstacle.height - 0.08F;
        const bool can_step = obstacle.height <= feet_y + step_height + 0.02F;
        const bool below_bottom = head_y <= 0.0F;
        if (!above_top && !can_step && !below_bottom) return false;
    }

    // Pivot 6 a2 promotes visible wall segments into two-sided analytical
    // blockers. Openings are represented by actual gaps between segments, so a
    // doorway behaves the same from both directions.
    const math::Vec3 position{x, feet_y + player_height * 0.5F, z};
    for (const WallSegment& wall : walls_) {
        if (head_y <= wall.base_y + 0.01F || feet_y >= wall.height - 0.01F) continue;
        const math::Vec3 closest = closest_point_on_wall_xz(wall, position);
        if (distance_xz(position, closest) < radius) return false;
    }
    return true;
}

DepenetrationResult LiminalLevel::depenetrate_3d(math::Vec3 eye_position,
                                                  float player_height,
                                                  float radius,
                                                  float step_height) const noexcept {
    DepenetrationResult result;
    result.position = eye_position;

    constexpr float kCollisionSkin = 0.018F;
    constexpr std::uint32_t kMaximumIterations = 10U;

    for (std::uint32_t iteration = 0; iteration < kMaximumIterations; ++iteration) {
        bool moved_this_iteration = false;
        const float feet_y = result.position.y - player_height;
        const float head_y = feet_y + player_height;

        for (const SolidObstacle& obstacle : obstacles_) {
            const bool above_top = feet_y >= obstacle.height - 0.08F;
            const bool can_step = obstacle.height <= feet_y + step_height + 0.02F;
            const bool below_bottom = head_y <= 0.0F;
            if (above_top || can_step || below_bottom) continue;

            const float expanded_min_x = obstacle.min_x - radius - kCollisionSkin;
            const float expanded_max_x = obstacle.max_x + radius + kCollisionSkin;
            const float expanded_min_z = obstacle.min_z - radius - kCollisionSkin;
            const float expanded_max_z = obstacle.max_z + radius + kCollisionSkin;

            if (result.position.x <= expanded_min_x || result.position.x >= expanded_max_x ||
                result.position.z <= expanded_min_z || result.position.z >= expanded_max_z) {
                continue;
            }

            const float to_left = result.position.x - expanded_min_x;
            const float to_right = expanded_max_x - result.position.x;
            const float to_near = result.position.z - expanded_min_z;
            const float to_far = expanded_max_z - result.position.z;

            float smallest = to_left;
            int side = 0;
            if (to_right < smallest) { smallest = to_right; side = 1; }
            if (to_near < smallest) { smallest = to_near; side = 2; }
            if (to_far < smallest) { side = 3; }

            switch (side) {
                case 0: result.position.x = expanded_min_x; break;
                case 1: result.position.x = expanded_max_x; break;
                case 2: result.position.z = expanded_min_z; break;
                default: result.position.z = expanded_max_z; break;
            }

            result.corrected = true;
            result.obstacle_name = obstacle.name;
            moved_this_iteration = true;
        }

        for (const WallSegment& wall : walls_) {
            if (head_y <= wall.base_y + 0.01F || feet_y >= wall.height - 0.01F) continue;
            const math::Vec3 closest = closest_point_on_wall_xz(wall, result.position);
            float dx = result.position.x - closest.x;
            float dz = result.position.z - closest.z;
            float distance = std::sqrt(dx * dx + dz * dz);
            const float required = radius + kCollisionSkin;
            if (distance >= required) continue;
            if (distance <= 0.00001F) {
                const float signed_side = (result.position.x - wall.start.x) * wall.inward_normal.x +
                                          (result.position.z - wall.start.z) * wall.inward_normal.z;
                const float direction = signed_side >= 0.0F ? 1.0F : -1.0F;
                dx = wall.inward_normal.x * direction;
                dz = wall.inward_normal.z * direction;
                distance = 1.0F;
            }
            const float push = required - distance;
            result.position.x += (dx / distance) * push;
            result.position.z += (dz / distance) * push;
            result.corrected = true;
            result.obstacle_name = "WALL SEGMENT";
            moved_this_iteration = true;
        }

        if (!moved_this_iteration) break;
        ++result.iterations;
    }

    return result;
}


bool LiminalLevel::near_almond_tech(math::Vec3 position, float radius) const noexcept {
    if (!has_almond_tech_station_) return false;
    const float dx = position.x - almond_tech_position_.x;
    const float dz = position.z - almond_tech_position_.z;
    return dx * dx + dz * dz <= radius * radius;
}

std::string_view LiminalLevel::zone_name(math::Vec3 position) const noexcept {
    // Overlapping/nested areas resolve to the most specific (smallest) authored
    // room instead of whichever area happened to be inserted first.
    const WalkArea* best = nullptr;
    float best_area = std::numeric_limits<float>::max();
    for (const WalkArea& area : areas_) {
        if (!within(position.x, area.min_x, area.max_x) ||
            !within(position.z, area.min_z, area.max_z)) continue;
        const float area_size = std::max(0.001F, (area.max_x - area.min_x) *
                                                 (area.max_z - area.min_z));
        if (best == nullptr || area_size < best_area) {
            best = &area;
            best_area = area_size;
        }
    }
    return best == nullptr ? std::string_view("Signal Void") : std::string_view(best->name);
}

const PortalGate* LiminalLevel::portal_at(math::Vec3 position) const noexcept {
    for (const PortalGate& portal : portals_) {
        const math::Vec3 relative = position - portal.center;
        const float inward_distance = math::dot(relative, portal.inward_normal);
        if (inward_distance < 0.0F || inward_distance > portal.trigger_depth) continue;
        const math::Vec3 tangent{-portal.inward_normal.z, 0.0F, portal.inward_normal.x};
        const float lateral = std::abs(math::dot(relative, tangent));
        if (lateral <= portal.half_width && position.y >= floor_height_ + 0.5F &&
            position.y <= floor_height_ + portal.height + 0.5F) {
            return &portal;
        }
    }
    return nullptr;
}

ConnectionAperture LiminalLevel::connection_aperture(
    const RoomConnection& connection, std::string_view source_zone) const noexcept {
    // Once threshold envelopes exist, they are the canonical geometry shared by
    // collision, point generation, and destination preview clipping. Room-center
    // inference is unreliable for nested and L-shaped rooms and caused previews
    // to activate only from one approach direction.
    for (const ThresholdEnvelope& envelope : threshold_envelopes_) {
        const bool same_order = envelope.zone_a == connection.zone_a &&
                                envelope.zone_b == connection.zone_b;
        const bool reverse_order = envelope.zone_a == connection.zone_b &&
                                   envelope.zone_b == connection.zone_a;
        if (!same_order && !reverse_order) continue;
        ConnectionAperture canonical = envelope.aperture;
        const bool source_is_b = source_zone == envelope.zone_b;
        if (source_is_b) canonical.normal = canonical.normal * -1.0F;
        return canonical;
    }

    const WalkArea* source = find_area(areas_, source_zone);
    const std::string_view destination_name = source_zone == connection.zone_a
        ? std::string_view(connection.zone_b) : std::string_view(connection.zone_a);
    const WalkArea* destination = find_area(areas_, destination_name);
    math::Vec3 normal{1.0F, 0.0F, 0.0F};
    if (source != nullptr && destination != nullptr) {
        normal = horizontal_direction(room_center(*source, connection.center.y),
                                      room_center(*destination, connection.center.y));
    }

    const math::Vec3 source_sample{
        connection.center.x - normal.x * 0.35F,
        connection.center.y,
        connection.center.z - normal.z * 0.35F};
    const math::Vec3 destination_sample{
        connection.center.x + normal.x * 0.35F,
        connection.center.y,
        connection.center.z + normal.z * 0.35F};
    const float source_floor = threshold_floor_near(source_sample);
    const float destination_floor = threshold_floor_near(destination_sample);
    const float threshold_floor = std::max(source_floor, destination_floor);

    float bottom = threshold_floor;
    float top = std::min(ceiling_height_, threshold_floor + 3.2F);
    switch (connection.kind) {
        case ConnectionKind::window:
            bottom = threshold_floor + 0.90F;
            top = std::min(ceiling_height_, threshold_floor + 2.82F);
            break;
        case ConnectionKind::hole:
            bottom = threshold_floor;
            top = ceiling_height_;
            break;
        case ConnectionKind::passage:
            bottom = threshold_floor;
            top = std::min(ceiling_height_,
                           std::max(threshold_floor + 3.2F,
                                    connection.center.y + 4.1F));
            break;
        case ConnectionKind::glass:
            bottom = threshold_floor;
            top = std::min(ceiling_height_, threshold_floor + 3.4F);
            break;
        case ConnectionKind::open_doorway:
        case ConnectionKind::framed_doorway:
            top = std::min(ceiling_height_,
                           std::max(threshold_floor + 3.2F, 3.2F));
            break;
    }
    if (top <= bottom + 0.05F) top = std::min(ceiling_height_, bottom + 0.05F);
    return {connection.center, normal, connection.half_width, bottom, top};
}

std::vector<ConnectionPreview> LiminalLevel::connection_previews(
    std::string_view active_zone, math::Vec3 position) const {
    std::vector<ConnectionPreview> result;
    for (const RoomConnection& connection : connections_) {
        std::string_view destination;
        if (connection.zone_a == active_zone) destination = connection.zone_b;
        else if (connection.bidirectional && connection.zone_b == active_zone) destination = connection.zone_a;
        else continue;

        const ConnectionAperture aperture = connection_aperture(connection, active_zone);
        const math::Vec3 relative = position - aperture.center;
        const float signed_distance = -math::dot(relative, aperture.normal);
        // Use a true capsule around the authored opening. Room ownership can
        // lag the physical threshold in overlapping/nested rooms, so rejecting
        // every point behind one inferred plane recreated the one-step-back bug.
        // Absolute normal distance keeps both sides continuous while the active
        // zone still decides which destination is eligible.
        const math::Vec3 tangent{-aperture.normal.z, 0.0F, aperture.normal.x};
        const float lateral = std::abs(math::dot(relative, tangent));
        const float lateral_excess = std::max(0.0F, lateral - (aperture.half_width + 0.90F));
        const float normal_distance = std::abs(signed_distance);
        const float aperture_distance = std::sqrt(
            normal_distance * normal_distance + lateral_excess * lateral_excess);
        const float activation_range = connection.preview_distance + 0.65F;
        if (aperture_distance > activation_range) continue;

        const float proximity = 1.0F - aperture_distance / std::max(0.1F, activation_range);
        const float strength = std::clamp(0.08F + proximity * proximity * 0.62F, 0.08F, 0.70F);
        result.push_back({destination, connection.center, strength, connection.kind,
                          position, aperture.normal, aperture.half_width,
                          aperture.bottom_y, aperture.top_y});
    }
    return result;
}

LightInfluence LiminalLevel::strongest_light(math::Vec3 position,
                                             std::string_view active_zone) const noexcept {
    LightInfluence result;
    for (const LightSource& light : lights_) {
        if (!light.zone.empty() && light.zone != active_zone) continue;
        const float distance = distance_xz(position, light.position);
        if (distance >= light.radius) continue;
        const float normalized = 1.0F - distance / std::max(0.1F, light.radius);
        const float influence = normalized * normalized * light.intensity;
        if (influence <= result.influence) continue;
        result.position = light.position;
        result.radius = light.radius;
        result.intensity = light.intensity;
        result.influence = influence;
    }
    return result;
}

LevelBounds LiminalLevel::bounds() const noexcept {
    LevelBounds result;
    result.min_x = std::numeric_limits<float>::max();
    result.max_x = std::numeric_limits<float>::lowest();
    result.min_z = std::numeric_limits<float>::max();
    result.max_z = std::numeric_limits<float>::lowest();
    for (const WalkArea& area : areas_) {
        result.min_x = std::min(result.min_x, area.min_x);
        result.max_x = std::max(result.max_x, area.max_x);
        result.min_z = std::min(result.min_z, area.min_z);
        result.max_z = std::max(result.max_z, area.max_z);
    }
    if (areas_.empty()) result = {};
    return result;
}

std::uint64_t LiminalLevel::layout_signature() const noexcept {
    std::uint64_t value = seed_ ^ 0x5349474E414C334FULL;
    value = mix_signature(value, static_cast<std::uint64_t>(areas_.size()));
    value = mix_signature(value, static_cast<std::uint64_t>(portals_.size()));
    for (const WalkArea& area : areas_) {
        value = mix_signature(value, quantized(area.min_x));
        value = mix_signature(value, quantized(area.max_x));
        value = mix_signature(value, quantized(area.min_z));
        value = mix_signature(value, quantized(area.max_z));
    }
    for (const PortalGate& portal : portals_) {
        value = mix_signature(value, portal.id);
        value = mix_signature(value, quantized(portal.destination.x));
        value = mix_signature(value, quantized(portal.destination.z));
    }
    return value;
}

}  // namespace signalcloud::world
