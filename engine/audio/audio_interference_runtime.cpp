#include "engine/audio/audio_interference_runtime.hpp"

#include "engine/data/udata.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdlib>
#include <optional>
#include <string>
#include <system_error>

namespace signalcloud::audio {
namespace {

std::string unquote(std::optional<std::string> raw) {
    if (!raw) return {};
    std::string value = *raw;
    if (value.size() >= 2U && value.front() == '"' && value.back() == '"') {
        value = value.substr(1U, value.size() - 2U);
    }
    return value;
}

std::optional<float> as_float(const std::optional<std::string>& raw) {
    if (!raw) return std::nullopt;
    char* end = nullptr;
    const float value = std::strtof(raw->c_str(), &end);
    if (end == raw->c_str() || *end != '\0' || !std::isfinite(value)) return std::nullopt;
    return value;
}

std::optional<std::uint32_t> as_u32(const std::optional<std::string>& raw) {
    if (!raw || raw->empty() || raw->front() == '-') return std::nullopt;
    std::uint32_t value = 0U;
    const auto result = std::from_chars(raw->data(), raw->data() + raw->size(), value);
    if (result.ec != std::errc{} || result.ptr != raw->data() + raw->size()) return std::nullopt;
    return value;
}

float bounded(const std::optional<std::string>& raw, float fallback, float lo, float hi) {
    return std::clamp(as_float(raw).value_or(fallback), lo, hi);
}

render::FrequencyBand band_from_name(const std::string& value) {
    if (value == "low") return render::FrequencyBand::low;
    if (value == "high") return render::FrequencyBand::high;
    if (value == "broadband") return render::FrequencyBand::broadband;
    return render::FrequencyBand::mid;
}

}  // namespace

AudioInterferenceRuntime::AudioInterferenceRuntime(std::filesystem::path project_root,
                                                   std::filesystem::path sidecar_path)
    : project_root_(std::move(project_root)), sidecar_path_(std::move(sidecar_path)) {}

bool AudioInterferenceRuntime::reload(std::string* error) {
    valid_ = false;
    profile_ = {};
    stats_ = {};
    try {
        const auto document = data::UDataDocument::load(sidecar_path_);
        if (document.has_errors()) {
            if (error) *error = "audio-interference runtime sidecar contains parse errors";
            return false;
        }
        if (unquote(document.value("meta", "schema")) != "signalcloud_audio_interference_runtime_v1") {
            if (error) *error = "unsupported audio-interference runtime schema";
            return false;
        }
        stats_.source_profile = unquote(document.value("meta", "source_profile"));
        stats_.profile_count = as_u32(document.value("meta", "profile_count")).value_or(0U);
        stats_.warning_count = as_u32(document.value("meta", "warning_count")).value_or(0U);
        stats_.signature = unquote(document.value("meta", "signature"));
        profile_.asset_id = unquote(document.value("profile.0", "asset_id"));
        profile_.name = unquote(document.value("profile.0", "name"));
        profile_.frequency_band = band_from_name(unquote(document.value("profile.0", "frequency_band")));
        profile_.strength = bounded(document.value("profile.0", "strength"), 0.82F, 0.08F, 1.0F);
        profile_.duration_seconds = bounded(document.value("profile.0", "duration_seconds"), 1.08F, 0.18F, 1.8F);
        profile_.obstruction_path = bounded(document.value("profile.0", "obstruction_path"), 0.12F, 0.0F, 1.0F);
        profile_.seed_salt = as_u32(document.value("profile.0", "seed_salt")).value_or(0xA5A30001U);
        profile_.radius_scale = bounded(document.value("profile.0", "radius_scale"), 1.18F, 0.35F, 2.0F);
        profile_.wave_count = std::clamp(as_u32(document.value("profile.0", "wave_count")).value_or(3U), 1U, 8U);
        profile_.wave_sharpness = bounded(document.value("profile.0", "wave_sharpness"), 0.72F, 0.08F, 1.0F);
        profile_.displacement_scale = bounded(document.value("profile.0", "displacement_scale"), 0.82F, 0.0F, 1.5F);
        profile_.color_mix = bounded(document.value("profile.0", "color_mix"), 0.34F, 0.0F, 1.0F);
        profile_.visibility_floor = bounded(document.value("profile.0", "visibility_floor"), 0.08F, 0.0F, 0.4F);
        profile_.hearing_loudness = bounded(document.value("profile.0", "hearing_loudness"), 0.86F, 0.08F, 1.25F);
        profile_.cooldown_seconds = bounded(document.value("profile.0", "cooldown_seconds"), 7.5F, 0.5F, 60.0F);
        profile_.point_budget_cost = std::min(as_u32(document.value("profile.0", "point_budget_cost")).value_or(224U), 4096U);
        stats_.point_budget_cost = profile_.point_budget_cost;
        valid_ = stats_.profile_count == 1U && !profile_.asset_id.empty();
        if (!valid_ && error) *error = "audio-interference runtime has no usable profile";
        return valid_;
    } catch (const std::exception& ex) {
        if (error) *error = ex.what();
        return false;
    }
}

}  // namespace signalcloud::audio
