#include "engine/audio/audio_interference_runtime.hpp"
#include "engine/materials/material_runtime.hpp"
#include "engine/render/sound_ripple.hpp"

#include <filesystem>
#include <iostream>
#include <string>

namespace {
int failures = 0;
void check(bool condition, const char* message) {
    if (!condition) {
        ++failures;
        std::cerr << "FAIL: " << message << '\n';
    }
}
}

int main(int argc, char** argv) {
    const std::filesystem::path root = argc > 1 ? argv[1] : ".";
    signalcloud::audio::AudioInterferenceRuntime audio(
        root, root / "user_data/studio/audio_interference_runtime.udata");
    std::string error;
    check(audio.reload(&error), "authored audio-interference runtime loads");
    const auto& profile = audio.hash_dog_bark();
    check(audio.stats().profile_count == 1U && audio.stats().warning_count == 0U,
          "one clean authored audio profile loads");
    check(profile.frequency_band == signalcloud::render::FrequencyBand::low,
          "Hash Dog authored profile remains low-band");
    check(profile.wave_count >= 1U && profile.wave_count <= 8U,
          "authored wave count remains bounded");
    check(profile.point_budget_cost <= 4096U,
          "authored audio point budget remains bounded");
    check(profile.hearing_loudness > 0.0F && profile.cooldown_seconds >= 0.5F,
          "authored gameplay hearing and cooldown controls load");

    signalcloud::render::SoundRipple ripple;
    ripple.trigger_event({1.0F, 0.0F, 2.0F}, profile.strength, profile.frequency_band,
        profile.obstruction_path, profile.seed_salt, profile.duration_seconds,
        profile.radius_scale, profile.wave_count, profile.wave_sharpness,
        profile.displacement_scale, profile.color_mix, profile.visibility_floor);
    const auto event = ripple.event();
    check(event.wave_count == profile.wave_count && event.wave_sharpness == profile.wave_sharpness,
          "authored visual wave controls reach the runtime event");
    check(event.displacement_scale == profile.displacement_scale && event.color_mix == profile.color_mix,
          "authored displacement and color controls reach the renderer event");
    check(event.visibility_floor == profile.visibility_floor && event.propagation_radius > 0.0F,
          "authored visibility floor and radius are active");

    signalcloud::materials::MaterialRuntime materials(
        root, root / "user_data/studio/material_runtime.udata");
    check(materials.reload(&error), "material runtime still loads with multi-layer definitions");
    const auto frame = materials.evaluate("Reception Tape");
    check(frame.surfaces[0].definition_layer_count >= 3U,
          "carpet carries multiple definition layers");
    check(frame.surfaces[1].definition_opacity[4] > 0.0F,
          "wallpaper carries Inner Texture definition");
    check(frame.surfaces[2].definition_opacity[0] > 0.0F &&
          frame.surfaces[2].definition_opacity[2] > 0.0F,
          "ceiling carries HD Light and Outer Light definitions");

    if (failures == 0) {
        std::cout << "SignalCloud A5a3 definition-layer and authored audio runtime tests PASS\n";
    }
    return failures == 0 ? 0 : 1;
}
