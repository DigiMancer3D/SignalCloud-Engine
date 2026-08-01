#include "engine/materials/material_runtime.hpp"
#include "engine/render/sound_ripple.hpp"

#include <cmath>
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
    signalcloud::materials::MaterialRuntime runtime(
        root, root / "user_data/studio/material_runtime.udata");
    std::string error;
    check(runtime.reload(&error), "material runtime loads compiled sidecar");
    check(runtime.stats().material_count == 3U, "three authored material definitions load");
    check(runtime.stats().assignment_count == 3U, "three texture graph assignments load");
    check(runtime.stats().warning_count == 0U, "material runtime has no compile warnings");
    check(runtime.stats().selected_point_budget <= runtime.stats().max_point_budget,
          "material point budget remains bounded");

    const auto frame = runtime.evaluate("Reception Tape");
    check(frame.active_materials == 3U, "floor wall and ceiling materials are active in Reception Tape");
    check(frame.surfaces[0].enabled && frame.surfaces[0].locked,
          "user-locked floor material overrides guided assignment");
    check(frame.surfaces[1].enabled && frame.surfaces[2].enabled,
          "guided wall and ceiling assignments resolve");
    check(frame.surfaces[0].jitter_amplitude > frame.surfaces[2].jitter_amplitude,
          "bumpy carpet has stronger jitter than ceiling tile");
    check(frame.surfaces[2].jitter_amplitude <= 0.002F,
          "ceiling tile remains geometrically flat while fixture depth is shader-bounded");
    check(frame.surfaces[2].source_color.z > frame.surfaces[0].source_color.z,
          "ceiling palette remains visibly cooler than the carpet palette");
    check(frame.combined_opacity > 0.0F && frame.combined_opacity <= 1.0F,
          "opacity hierarchy is deterministically clamped");
    check(runtime.evaluate("Long Signal Hall").active_materials == 0U,
          "room-specific texture graph does not leak into other zones");

    signalcloud::render::SoundRipple ripple;
    ripple.trigger_event({1.0F, 2.0F, 3.0F}, 0.82F,
        signalcloud::render::FrequencyBand::low, 0.25F, 0xA5A10001U, 1.0F);
    const auto event = ripple.event();
    check(event.serial == 1U && event.seed == 0xA5A10001U,
          "audio interference event preserves serial and deterministic seed");
    check(event.frequency_band == signalcloud::render::FrequencyBand::low,
          "Hash Dog bark uses low frequency band");
    check(event.strength > 0.0F && event.propagation_radius > 0.0F,
          "audio event creates bounded visible ripple");
    check(event.obstruction_path > 0.0F && event.obstruction_path <= 1.0F,
          "audio obstruction path is normalized");
    ripple.update(2.0F);
    check(!ripple.active(), "audio interference is temporary and does not rewrite resident cloud");

    if (failures == 0) {
        std::cout << "SignalCloud A5a1 material and audio interference runtime tests PASS\n";
    }
    return failures == 0 ? 0 : 1;
}
