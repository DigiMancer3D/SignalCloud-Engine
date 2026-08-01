#pragma once

#include "engine/math/vec.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <string_view>

namespace signalcloud::render {

enum class FrequencyBand : std::uint8_t { low = 0, mid = 1, high = 2, broadband = 3 };

struct SoundInterferenceEvent {
    math::Vec3 source{};
    float strength{0.0F};
    FrequencyBand frequency_band{FrequencyBand::mid};
    float propagation_radius{0.0F};
    float obstruction_path{0.0F};
    std::uint32_t seed{0U};
    std::uint32_t serial{0U};
    float radius_scale{1.0F};
    std::uint32_t wave_count{2U};
    float wave_sharpness{0.58F};
    float displacement_scale{1.0F};
    float color_mix{0.22F};
    float visibility_floor{0.04F};
};

class SoundRipple {
public:
    void trigger(math::Vec3 position, float loudness, float duration = 0.72F) noexcept;
    void trigger_event(math::Vec3 position, float loudness, FrequencyBand band,
                       float obstruction_path, std::uint32_t seed,
                       float duration = 0.72F, float radius_scale = 1.0F,
                       std::uint32_t wave_count = 2U, float wave_sharpness = 0.58F,
                       float displacement_scale = 1.0F, float color_mix = 0.22F,
                       float visibility_floor = 0.04F) noexcept;
    void update(float dt_seconds) noexcept;

    [[nodiscard]] bool active() const noexcept { return remaining_seconds_ > 0.0F; }
    [[nodiscard]] math::Vec3 position() const noexcept { return position_; }
    [[nodiscard]] float radius() const noexcept;
    [[nodiscard]] float intensity() const noexcept;
    [[nodiscard]] std::uint32_t serial() const noexcept { return serial_; }
    [[nodiscard]] std::uint32_t seed() const noexcept { return seed_; }
    [[nodiscard]] FrequencyBand frequency_band() const noexcept { return frequency_band_; }
    [[nodiscard]] float obstruction_path() const noexcept { return obstruction_path_; }
    [[nodiscard]] SoundInterferenceEvent event() const noexcept;
    [[nodiscard]] std::array<float, 8> wave_radii() const noexcept;
    [[nodiscard]] std::size_t visible_wave_count() const noexcept;

private:
    math::Vec3 position_{};
    float loudness_{0.0F};
    float duration_seconds_{0.0F};
    float remaining_seconds_{0.0F};
    float obstruction_path_{0.0F};
    FrequencyBand frequency_band_{FrequencyBand::mid};
    std::uint32_t seed_{0U};
    std::uint32_t serial_{0};
    float radius_scale_{1.0F};
    std::uint32_t wave_count_{2U};
    float wave_sharpness_{0.58F};
    float displacement_scale_{1.0F};
    float color_mix_{0.22F};
    float visibility_floor_{0.04F};
};

[[nodiscard]] std::string_view frequency_band_name(FrequencyBand band) noexcept;

}  // namespace signalcloud::render
