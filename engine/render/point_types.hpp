#pragma once

#include <cstdint>

namespace signalcloud::render {

struct alignas(16) PointGpu {
    float position[3];
    float radius;
    float color[4];
    float normal[3];
    float density;
};

static_assert(sizeof(PointGpu) == 48, "PointGpu must remain std430-friendly at 48 bytes.");

struct PointCloudStats {
    std::uint64_t seed{0};
    std::uint32_t total_points{0};
    std::uint32_t wall_points{0};
    std::uint32_t floor_points{0};
    std::uint32_t ceiling_points{0};
    std::uint32_t dust_points{0};
    std::uint32_t portal_points{0};
    std::uint32_t threshold_structure_points{0};
    std::uint32_t water_surface_points{0};
    std::uint32_t water_volume_points{0};
    std::uint32_t submerged_floor_points{0};
    std::uint32_t submerged_wall_points{0};
};

}  // namespace signalcloud::render
