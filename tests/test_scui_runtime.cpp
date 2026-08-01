#include "engine/ui/scui_native_runtime.hpp"
#include "engine/ui/scui_binding_store.hpp"
#include "engine/ui/scui_light_preview.hpp"
#include "engine/scfont/font_service.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <string>

namespace {

int failures = 0;

void expect(bool condition, const std::string& message) {
    if (!condition) {
        ++failures;
        std::cerr << "FAIL: " << message << '\n';
    }
}

bool finite_point(const signalcloud::render::PointGpu& point) {
    for (float value : point.position) if (!std::isfinite(value)) return false;
    if (!std::isfinite(point.radius) || !std::isfinite(point.density)) return false;
    for (float value : point.color) if (!std::isfinite(value)) return false;
    return true;
}

}  // namespace

int main(int argc, char** argv) {
    const std::filesystem::path root = argc > 1 ? argv[1] : std::filesystem::current_path();
    signalcloud::font::FontService font_service;
    expect(font_service.load("core.fonts.terminal_00",
                             root / "content/core/fonts/terminal_00/Terminal_00.scfont"),
           "Terminal_00 SCFONT loads for native SCUI proof");
    expect(font_service.set_default("core.fonts.terminal_00"),
           "Terminal_00 becomes the default native SCUI font");
    const auto terminal_font = font_service.default_font();

    auto panel = signalcloud::ui::ScuiPanel::load(
        root / "content/core/ui/authoring_lab_project_selector.scui");
    signalcloud::ui::ScuiNativeRuntime runtime(std::move(panel), 4U);
    runtime.set_font(terminal_font);

    expect(runtime.valid(), "native runtime accepts proof panel");
    expect(runtime.external_font_active(), "native runtime uses Terminal_00 instead of the legacy text path");
    expect(runtime.layout().page_count == 2U, "proof panel creates two native pages");
    expect(runtime.layout().focus_order.size() == 4U, "proof panel exposes four focus controls");
    expect(runtime.register_command("authoring.project.select"), "project command registered");
    expect(runtime.register_command("authoring.preview.toggle"), "preview command registered");
    expect(runtime.register_command("authoring.point_budget.set"), "budget command registered");
    expect(runtime.register_command("authoring.profile.refresh"), "refresh command registered");

    runtime.set_open(true);
    expect(runtime.open(), "runtime opens");
    expect(runtime.focused_control_id() == "project", "first focus lands on project dropdown");
    expect(runtime.string("project_id").value_or("") == "current", "initial project value parsed");

    expect(runtime.handle_key(signalcloud::ui::ScuiNativeKey::confirm),
           "confirm dispatches current dropdown selection");
    expect(runtime.string("project_id").value_or("") == "current",
           "confirm does not unexpectedly cycle dropdown");
    auto confirm_events = runtime.take_events();
    expect(confirm_events.size() == 1U, "dropdown confirm emits one event");
    if (!confirm_events.empty()) {
        expect(confirm_events.front().payload_json.find("current") != std::string::npos,
               "dropdown confirm emits the current value");
    }

    expect(runtime.handle_key(signalcloud::ui::ScuiNativeKey::adjust_next),
           "right action cycles dropdown");
    expect(runtime.string("project_id").value_or("") == "last-opened",
           "dropdown value changed deterministically");
    auto events = runtime.take_events();
    expect(events.size() == 1U, "dropdown emits one event");
    if (!events.empty()) {
        expect(events.front().command_id == "authoring.project.select", "dropdown event allowlisted");
        expect(events.front().payload_json.find("last-opened") != std::string::npos,
               "dropdown event includes value");
    }

    expect(runtime.handle_key(signalcloud::ui::ScuiNativeKey::focus_next), "focus advances to toggle");
    expect(runtime.focused_control_id() == "safe_preview", "toggle focused");
    expect(runtime.handle_key(signalcloud::ui::ScuiNativeKey::confirm), "toggle confirms");
    expect(!runtime.boolean("safe_preview").value_or(true), "toggle state changed");

    expect(runtime.handle_key(signalcloud::ui::ScuiNativeKey::focus_next), "focus advances to slider");
    const double before = runtime.number("point_budget").value_or(0.0);
    expect(runtime.handle_key(signalcloud::ui::ScuiNativeKey::adjust_next), "slider increments");
    expect(runtime.number("point_budget").value_or(0.0) > before, "slider value increased");

    expect(runtime.handle_key(signalcloud::ui::ScuiNativeKey::focus_next), "focus advances to refresh");
    expect(runtime.focused_control_id() == "refresh", "refresh focused");
    expect(runtime.current_page() == 1U, "focus navigation changes page");
    expect(runtime.handle_key(signalcloud::ui::ScuiNativeKey::confirm), "refresh button confirms");

    expect(runtime.handle_key(signalcloud::ui::ScuiNativeKey::page_previous), "page previous handled");
    expect(runtime.current_page() == 0U, "page returns to first page");
    expect(runtime.handle_pointer_move(0.70F, 0.680F), "pointer move handled");
    expect(runtime.focused_control_id() == "point_budget", "pointer hover focuses slider row");
    expect(runtime.handle_pointer_activate(0.915F, 0.680F), "pointer slider activation handled");
    expect(runtime.number("point_budget").value_or(0.0) == 12'000'000.0,
           "pointer maps slider to bounded maximum");

    signalcloud::ui::ArPose pose;
    pose.camera_position = {2.0F, 1.72F, -4.0F};
    pose.forward = {0.0F, 0.0F, -1.0F};
    pose.right = {1.0F, 0.0F, 0.0F};
    const auto points = runtime.build_points(1.25F, pose);
    expect(points.size() > 500U, "native point panel generates visible point geometry");
    expect(points.size() < 40'000U, "native point panel remains bounded");
    const auto presentation = runtime.stats();
    expect(presentation.backplate_points > 5'000U,
           "native panel generates a dense readability backplate");
    expect(presentation.wrapped_text_lines >= 8U,
           "native panel records wrapped title, labels, values, and footer text");
    bool all_finite = true;
    std::size_t external_font_points = 0U;
    float maximum_font_radius = 0.0F;
    for (const auto& point : points) {
        all_finite = all_finite && finite_point(point);
        if (std::abs(point.density - 1.05F) < 0.001F) {
            ++external_font_points;
            maximum_font_radius = std::max(maximum_font_radius, point.radius);
        }
    }
    expect(external_font_points > 300U, "Terminal_00 supplies the panel text points");
    expect(maximum_font_radius <= 0.00216F, "Terminal_00 SCUI point radius remains separated and bounded");
    expect(all_finite, "native point panel is finite");
    expect(runtime.stats().generated_points == points.size(), "runtime reports generated point count");

    const auto blocked_panel = signalcloud::ui::ScuiPanel::parse(
        "@udata 1\n[panel]\nschema_name: \"signalcloud.scui\";\n"
        "schema_major: 1;\npanel_id: \"blocked.proof\";\ntitle: \"Blocked\";\n"
        "[control.execute]\norder: 1;\ntype: \"button\";\nlabel: \"Execute\";\n"
        "command_id: \"os.shell.execute\";\n");
    signalcloud::ui::ScuiNativeRuntime blocked(blocked_panel, 4U);
    blocked.set_open(true);
    expect(blocked.handle_key(signalcloud::ui::ScuiNativeKey::confirm),
           "blocked button still provides local visual activation");
    expect(blocked.take_events().empty(), "unknown command does not dispatch");
    expect(blocked.stats().blocked_commands == 1U, "blocked command is counted");

    auto light_panel = signalcloud::ui::ScuiPanel::load(
        root / "content/core/ui/light_lab_control_surface.scui");
    signalcloud::ui::ScuiNativeRuntime light_runtime(std::move(light_panel), 4U);
    light_runtime.set_font(terminal_font);
    expect(light_runtime.valid(), "native Light Lab SCUI panel validates");
    expect(light_runtime.layout().page_count == 4U, "Light Lab panel uses four bounded pages");
    std::size_t document_bindings = 0U;
    for (const auto& control : light_runtime.panel().controls) {
        if (!control.document_binding.empty()) ++document_bindings;
    }
    expect(document_bindings == 6U, "Light Lab panel exposes six managed document bindings");
    for (const std::string command : {
             "light.scope.set", "light.illuminosity.set", "light.radius.set",
             "light.day_illuminosity.set", "light.night_illuminosity.set",
             "light.time_of_day.set", "light.timeline.play", "light.timeline.pause",
             "light.timeline.stop", "light.probe.sample", "light.diagnostics.bake",
             "light.document.reload", "light.document.save"}) {
        expect(light_runtime.register_command(command), "Light Lab command registered: " + command);
    }
    light_runtime.set_open(true);
    expect(light_runtime.focused_control_id() == "scope", "Light Lab focus starts on scope");
    expect(light_runtime.handle_key(signalcloud::ui::ScuiNativeKey::adjust_next),
           "Light Lab scope changes");
    expect(light_runtime.string("light_scope").value_or("") == "area",
           "Light Lab scope changed to area");
    expect(light_runtime.set_number("light_i", 104.0), "Light Lab illuminosity state set");
    light_runtime.show_notice(signalcloud::ui::ScuiNativeNoticeKind::success,
                              "LIGHT SAVED", 1.0F, 2.0F);
    const auto light_notice_points = light_runtime.build_points(1.2F, pose);
    expect(light_runtime.stats().notice_points > 100U,
           "successful native save renders a visible green confirmation notice");
    expect(light_notice_points.size() < 40'000U,
           "save notice preserves the bounded native SCUI point budget");
    (void)light_runtime.build_points(3.2F, pose);
    expect(light_runtime.stats().notice_points == 0U,
           "native confirmation notice expires without closing the panel");

    signalcloud::ui::ScuiLightPreview light_preview;
    const auto preview_before = light_preview.build_points(light_runtime, 1.25F, pose);
    expect(preview_before.size() > 500U && preview_before.size() < 2'000U,
           "Light Lab produces a bounded native live preview handoff");
    bool preview_finite = true;
    for (const auto& point : preview_before) preview_finite = preview_finite && finite_point(point);
    expect(preview_finite, "Light Lab live preview points are finite");
    const float preview_i_before = light_preview.stats().effective_illuminosity;
    expect(light_runtime.set_number("light_i", 30.0), "Light Lab preview state can change");
    const auto preview_after = light_preview.build_points(light_runtime, 1.35F, pose);
    expect(!preview_after.empty(), "Light Lab preview remains visible after state change");
    expect(light_preview.stats().effective_illuminosity < preview_i_before,
           "Light Lab preview consumes the authored illuminosity state live");
    expect(light_runtime.set_number("light_i", 104.0),
           "Light Lab state restores before persistence proof");

    const auto state_path = root / "user_data/test_scui_a2a3/native_light_state.udata";
    signalcloud::ui::ScuiNativeBindingStore state_store(
        state_path, "content/core/lights/authoring_lab_default.slight");
    std::string state_error;
    expect(state_store.save(light_runtime, &state_error), "native Light Lab state saves atomically: " + state_error);
    auto reloaded_panel = signalcloud::ui::ScuiPanel::load(
        root / "content/core/ui/light_lab_control_surface.scui");
    signalcloud::ui::ScuiNativeRuntime reloaded_runtime(std::move(reloaded_panel), 4U);
    reloaded_runtime.set_font(terminal_font);
    expect(state_store.load(reloaded_runtime, &state_error), "native Light Lab state reloads: " + state_error);
    expect(reloaded_runtime.string("light_scope").value_or("") == "area",
           "native Light Lab scope survives reload");
    expect(reloaded_runtime.number("light_i").value_or(0.0) == 104.0,
           "native Light Lab illuminosity survives reload");
    std::filesystem::remove_all(state_path.parent_path());

    expect(runtime.handle_key(signalcloud::ui::ScuiNativeKey::cancel), "cancel closes panel");
    expect(!runtime.open(), "runtime closes without changing game state");

    if (failures == 0) {
        std::cout << "SCUI native point rendering, focus, paging, pointer, keyboard, and allowlist PASS\n";
    }
    return failures == 0 ? 0 : 1;
}
