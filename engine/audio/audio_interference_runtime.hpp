#pragma once

#include "engine/render/sound_ripple.hpp"

#include <cstdint>
#include <filesystem>
#include <string>

namespace signalcloud::audio {

struct AudioInterferenceProfile {
    std::string asset_id{"core.audio.hash_dog_bark"};
    std::string name{"Hash Dog Low-Band Bark"};
    render::FrequencyBand frequency_band{render::FrequencyBand::low};
    float strength{0.82F};
    float duration_seconds{1.08F};
    float obstruction_path{0.12F};
    std::uint32_t seed_salt{0xA5A30001U};
    float radius_scale{1.18F};
    std::uint32_t wave_count{3U};
    float wave_sharpness{0.72F};
    float displacement_scale{0.82F};
    float color_mix{0.34F};
    float visibility_floor{0.08F};
    float hearing_loudness{0.86F};
    float cooldown_seconds{7.5F};
    std::uint32_t point_budget_cost{224U};
};

struct AudioInterferenceStats {
    std::string source_profile;
    std::size_t profile_count{0U};
    std::size_t warning_count{0U};
    std::string signature;
    std::uint32_t point_budget_cost{0U};
};

class AudioInterferenceRuntime {
public:
    AudioInterferenceRuntime() = default;
    AudioInterferenceRuntime(std::filesystem::path project_root,
                             std::filesystem::path sidecar_path);

    bool reload(std::string* error = nullptr);
    [[nodiscard]] const AudioInterferenceProfile& hash_dog_bark() const noexcept { return profile_; }
    [[nodiscard]] const AudioInterferenceStats& stats() const noexcept { return stats_; }
    [[nodiscard]] bool valid() const noexcept { return valid_; }

private:
    std::filesystem::path project_root_;
    std::filesystem::path sidecar_path_;
    AudioInterferenceProfile profile_{};
    AudioInterferenceStats stats_{};
    bool valid_{false};
};

}  // namespace signalcloud::audio
