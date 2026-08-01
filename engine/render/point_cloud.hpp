#pragma once

#include "engine/math/vec.hpp"
#include "engine/render/point_types.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace signalcloud::world { class LiminalLevel; }

namespace signalcloud::render {

struct LiminalRoomSpec {
    float width{18.0F};
    float height{5.8F};
    float depth{24.0F};
    std::uint32_t point_count{100'000};
    std::uint64_t seed{0xA11D0A1ULL};
};

struct LiminalLevelPointSpec {
    std::uint32_t point_count{1'000'000U};
    std::uint64_t seed{0xA11D0A1ULL};
};

struct PointRange {
    std::string zone;
    std::size_t first{0};
    std::size_t count{0};
    math::Vec3 center{};
    float radius{0.0F};
};

class PointCloud {
public:
    static PointCloud make_liminal_room(const LiminalRoomSpec& spec);
    static PointCloud make_liminal_level(const world::LiminalLevel& level,
                                         const LiminalLevelPointSpec& spec);

    [[nodiscard]] const std::vector<PointGpu>& points() const noexcept { return points_; }
    [[nodiscard]] const std::vector<PointRange>& ranges() const noexcept { return ranges_; }
    [[nodiscard]] const PointRange* range_for(std::string_view zone) const noexcept;
    [[nodiscard]] std::vector<const PointRange*> ranges_for(std::string_view zone) const;
    [[nodiscard]] const PointCloudStats& stats() const noexcept { return stats_; }
    [[nodiscard]] bool finite() const noexcept;

private:
    std::vector<PointGpu> points_;
    std::vector<PointRange> ranges_;
    PointCloudStats stats_{};
};

}  // namespace signalcloud::render
