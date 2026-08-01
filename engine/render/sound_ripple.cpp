#include "engine/render/sound_ripple.hpp"

#include <algorithm>

namespace signalcloud::render {

void SoundRipple::trigger(math::Vec3 position, float loudness, float duration) noexcept {
    trigger_event(position, loudness, FrequencyBand::mid, 0.0F,
                  0x51A00000U ^ (serial_ + 1U) * 2654435761U, duration);
}

void SoundRipple::trigger_event(math::Vec3 position, float loudness, FrequencyBand band,
                                float obstruction_path, std::uint32_t seed,
                                float duration, float radius_scale,
                                std::uint32_t wave_count, float wave_sharpness,
                                float displacement_scale, float color_mix,
                                float visibility_floor) noexcept {
    position_ = position;
    loudness_ = std::clamp(loudness, 0.08F, 1.0F);
    duration_seconds_ = std::clamp(duration, 0.18F, 1.8F);
    remaining_seconds_ = duration_seconds_;
    frequency_band_ = band;
    obstruction_path_ = std::clamp(obstruction_path, 0.0F, 1.0F);
    seed_ = seed == 0U ? 1U : seed;
    radius_scale_ = std::clamp(radius_scale, 0.35F, 2.0F);
    wave_count_ = std::clamp(wave_count, 1U, 8U);
    wave_sharpness_ = std::clamp(wave_sharpness, 0.08F, 1.0F);
    displacement_scale_ = std::clamp(displacement_scale, 0.0F, 1.5F);
    color_mix_ = std::clamp(color_mix, 0.0F, 1.0F);
    visibility_floor_ = std::clamp(visibility_floor, 0.0F, 0.4F);
    ++serial_;
}

void SoundRipple::update(float dt_seconds) noexcept {
    remaining_seconds_ = std::max(0.0F, remaining_seconds_ - std::max(0.0F, dt_seconds));
}

float SoundRipple::radius() const noexcept {
    if (!active() || duration_seconds_ <= 0.0F) return 0.0F;
    const float progress = 1.0F - remaining_seconds_ / duration_seconds_;
    const float band_scale = frequency_band_ == FrequencyBand::low ? 1.18F :
                             frequency_band_ == FrequencyBand::high ? 0.82F : 1.0F;
    return (0.55F + progress * (5.0F + loudness_ * 10.0F)) * band_scale * radius_scale_;
}

float SoundRipple::intensity() const noexcept {
    if (!active() || duration_seconds_ <= 0.0F) return 0.0F;
    const float ratio = remaining_seconds_ / duration_seconds_;
    return loudness_ * ratio * (1.0F - obstruction_path_ * 0.42F);
}

SoundInterferenceEvent SoundRipple::event() const noexcept {
    return {position_, intensity(), frequency_band_, radius(), obstruction_path_, seed_, serial_,
            radius_scale_, wave_count_, wave_sharpness_, displacement_scale_, color_mix_, visibility_floor_};
}

std::array<float, 8> SoundRipple::wave_radii() const noexcept {
    std::array<float, 8> radii{};
    const float lead = radius();
    if (lead <= 0.0F) return radii;
    const float count = static_cast<float>(std::max<std::uint32_t>(1U, wave_count_));
    const float spacing = std::clamp(lead / (count + 0.5F), 0.42F, 1.60F);
    for (std::uint32_t index = 0U; index < wave_count_ && index < radii.size(); ++index) {
        radii[index] = std::max(0.0F, lead - static_cast<float>(index) * spacing);
    }
    return radii;
}

std::size_t SoundRipple::visible_wave_count() const noexcept {
    const auto radii = wave_radii();
    return static_cast<std::size_t>(std::count_if(radii.begin(), radii.end(),
        [](float value) { return value > 0.18F; }));
}

std::string_view frequency_band_name(FrequencyBand band) noexcept {
    if (band == FrequencyBand::low) return "low";
    if (band == FrequencyBand::high) return "high";
    if (band == FrequencyBand::broadband) return "broadband";
    return "mid";
}

}  // namespace signalcloud::render
