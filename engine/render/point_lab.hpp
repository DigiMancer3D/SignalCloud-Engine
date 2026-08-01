#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <string_view>

namespace signalcloud::render {

struct PointPreset {
    std::string_view name;
    std::uint32_t points;
};

inline constexpr std::array<PointPreset, 7> kPointLabPresets{{
    {"100K", 100'000U},
    {"500K", 500'000U},
    {"1M", 1'000'000U},
    {"2M", 2'000'000U},
    {"3M", 3'000'000U},
    {"4M", 4'000'000U},
    {"8M", 8'000'000U},
}};

class PointLabState {
public:
    [[nodiscard]] std::size_t preset_index() const noexcept { return preset_index_; }
    [[nodiscard]] PointPreset preset() const noexcept { return kPointLabPresets[preset_index_]; }
    [[nodiscard]] float point_scale() const noexcept { return point_scale_; }
    [[nodiscard]] float density_scale() const noexcept { return density_scale_; }

    bool select_preset(std::size_t index) noexcept;
    bool select_point_count(std::uint32_t points) noexcept;
    void adjust_point_scale(float delta) noexcept;
    void adjust_density_scale(float delta) noexcept;

private:
    std::size_t preset_index_{0};
    float point_scale_{1.0F};
    float density_scale_{1.0F};
};

}  // namespace signalcloud::render
