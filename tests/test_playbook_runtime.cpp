#include "engine/ai/playbook.hpp"
#include "engine/scfont/text_scale_profile.hpp"

#include <cmath>
#include <filesystem>
#include <iostream>
#include <string>

namespace {

bool close(float a, float b) {
    return std::fabs(a - b) < 0.0001F;
}

int fail(const std::string& message) {
    std::cerr << "FAIL: " << message << '\n';
    return 1;
}

}  // namespace

int main(int argc, char** argv) {
    const std::filesystem::path root = argc > 1 ? argv[1] : std::filesystem::current_path();
    const auto runtime = signalcloud::ai::PlaybookRuntime::load(
        root / "user_data/studio/playbook_runtime.scplayruntime");
    if (!runtime.valid()) return fail("runtime validation");
    if (runtime.stats().graph_count != 2U || runtime.stats().node_count != 8U ||
        runtime.stats().edge_count != 7U || runtime.stats().point_budget_cost != 168U) {
        return fail("runtime aggregate statistics");
    }

    const auto* dog = runtime.find("core.hash_dog.signal_investigate");
    const auto* water = runtime.find("core.environment.water_pressure_pulse");
    if (dog == nullptr || water == nullptr) return fail("shipped graph lookup");
    if (dog->subject_kind != "enemy" || water->subject_kind != "environmental_effect") {
        return fail("universal subject classes");
    }

    signalcloud::ai::PlaybookContext dog_context;
    dog_context.event = "event.sound_heard";
    dog_context.true_conditions.insert("path.available");
    const auto dog_trace = runtime.evaluate(dog->id, dog_context);
    if (dog_trace.size() != 4U || dog_trace[1].operation != "move.investigate" ||
        dog_trace[2].operation != "move.guard" || dog_trace.back().operation != "flow.reset") {
        return fail("deterministic Hash Dog compatibility trace");
    }

    signalcloud::ai::PlaybookContext water_context;
    water_context.event = "event.splash";
    const auto water_trace = runtime.evaluate(water->id, water_context);
    if (water_trace.size() != 4U || water_trace[1].operation != "signal.pressure_wave" ||
        water_trace[2].operation != "water.splash") {
        return fail("non-enemy environmental-effect trace");
    }
    if (runtime.evaluate(water->id, water_context, 2U).size() != 2U) {
        return fail("bounded maximum step override");
    }

    using signalcloud::font::SimpleTextRole;
    if (!close(signalcloud::font::simple_text_multiplier(SimpleTextRole::scui_menu), 1.78F) ||
        !close(signalcloud::font::simple_text_multiplier(SimpleTextRole::hud_compact), 2.65F) ||
        !close(signalcloud::font::simple_text_multiplier(SimpleTextRole::hud_menu), 2.20F) ||
        !close(signalcloud::font::simple_text_multiplier(SimpleTextRole::feedback), 2.25F)) {
        return fail("screenshot-derived simple text profiles");
    }

    std::cout << "Universal Playbook runtime and split simple-text profiles PASS\n";
    return 0;
}
