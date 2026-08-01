#include "engine/ui/scui_native_runtime.hpp"
#include "engine/ui/scui_registry.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
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
}

int main(int argc, char** argv) {
    const std::filesystem::path root = argc > 1 ? argv[1] : std::filesystem::current_path();
    const auto registry = signalcloud::ui::ScuiPanelRegistry::load(
        root, root / "content/core/ui/scui_panel_registry.udata");
    expect(registry.valid(), "canonical SCUI panel registry validates");
    expect(registry.entries().size() == 3U, "canonical registry exposes three trusted panels");
    expect(registry.default_panel_key() == "project-selector", "registry default is project selector");
    expect(registry.selector_panel_id() == "authoring_lab.panel_selector", "selector panel id is stable");

    const auto* project = registry.find("project-selector");
    expect(project != nullptr, "project selector is registered");
    if (project != nullptr) {
        expect(project->safe_room_only, "project selector remains safe-room only");
        expect(project->relative_path == "content/core/ui/authoring_lab_project_selector.scui",
               "project selector path is project-relative");
    }
    const auto* light = registry.find("light-lab");
    expect(light != nullptr, "Light Lab is registered");
    if (light != nullptr) {
        expect(light->safe_room_only, "Light Lab remains safe-room only");
        expect(light->preview_kind == "illuminosity-light", "Light Lab declares native preview handoff");
        expect(light->native_state_path == "user_data/studio/light_lab_native_state.udata",
               "Light Lab native state path is managed");
        expect(light->commands.size() == 13U, "Light Lab command allowlist covers all shipped actions");
        const auto panel = signalcloud::ui::ScuiPanel::load(root / light->relative_path);
        for (const auto& control : panel.controls) {
            if (!control.enabled || !control.visible || control.command_id.empty()) continue;
            const bool trusted = std::find(light->commands.begin(), light->commands.end(), control.command_id)
                != light->commands.end();
            expect(trusted, "Light Lab registry trusts command: " + control.command_id);
        }
        signalcloud::ui::ScuiNativeRuntime light_runtime(panel, 4U);
        for (const auto& command : light->commands) (void)light_runtime.register_command(command);
        light_runtime.set_open(true);
        for (const std::string control_id : {
                 "timeline_play", "timeline_pause", "timeline_stop", "probe", "bake"}) {
            for (std::size_t step = 0U;
                 step <= light_runtime.stats().focusable_controls &&
                 light_runtime.focused_control_id() != control_id;
                 ++step) {
                (void)light_runtime.handle_key(signalcloud::ui::ScuiNativeKey::focus_next);
            }
            expect(light_runtime.focused_control_id() == control_id,
                   "Light Lab can focus native action: " + control_id);
            expect(light_runtime.handle_key(signalcloud::ui::ScuiNativeKey::confirm),
                   "Light Lab confirms native action: " + control_id);
            const auto events = light_runtime.take_events();
            expect(events.size() == 1U, "Light Lab dispatches one event for: " + control_id);
            if (!events.empty()) {
                expect(events.front().control_id == control_id,
                       "Light Lab event preserves control id: " + control_id);
            }
            expect(light_runtime.stats().blocked_commands == 0U,
                   "Light Lab action is not blocked: " + control_id);
        }
    }

    const auto* tupd = registry.find("tupd-workbench");
    expect(tupd != nullptr, "Tupd Workbench is registered");
    if (tupd != nullptr) {
        expect(tupd->safe_room_only, "Tupd Workbench remains safe-room only");
        expect(tupd->preview_kind == "tupd-ghost-result", "Tupd Workbench declares ghost preview");
        expect(tupd->commands.size() == 6U, "Tupd command allowlist covers shipped actions");
    }

    auto selector_panel = signalcloud::ui::ScuiPanel::load(
        root / "content/core/ui/authoring_lab_panel_selector.scui");
    signalcloud::ui::ScuiNativeRuntime selector(std::move(selector_panel), 4U);
    expect(selector.valid(), "registry selector panel validates");
    expect(selector.set_choices("panel", registry.keys(), std::string(registry.default_panel_key())),
           "selector dropdown accepts validated registry keys");
    expect(selector.string("panel_key").value_or("") == "project-selector",
           "selector initializes to registry default");
    expect(selector.register_command("authoring.panel.open"), "selector open command is explicit");
    selector.set_open(true);
    expect(selector.handle_key(signalcloud::ui::ScuiNativeKey::adjust_next),
           "selector cycles between registered panels");
    expect(selector.string("panel_key").value_or("") == "project-selector" ||
           selector.string("panel_key").value_or("") == "light-lab" ||
           selector.string("panel_key").value_or("") == "tupd-workbench",
           "selector remains inside registry choices");

    const auto temp_dir = root / "user_data/test_scui_a2a4";
    std::filesystem::create_directories(temp_dir);
    const auto bad_registry_path = temp_dir / "escape_registry.udata";
    std::ofstream out(bad_registry_path);
    out << "@udata 1\n\n[registry]\n"
           "schema_name: \"signalcloud.scui.registry\";\n"
           "schema_major: 1;\n"
           "default_panel: \"escape\";\n"
           "selector_panel: \"authoring_lab.panel_selector\";\n\n"
           "[panel.escape]\n"
           "panel_id: \"escape.panel\";\n"
           "label: \"Escape\";\n"
           "path: \"../outside.scui\";\n"
           "safe_room_only: true;\n";
    out.close();
    const auto bad = signalcloud::ui::ScuiPanelRegistry::load(root, bad_registry_path);
    expect(bad.find("escape") == nullptr, "registry rejects panel paths outside project root");
    expect(!bad.valid(), "registry with no validated entries is invalid");
    std::filesystem::remove_all(temp_dir);

    if (failures == 0) {
        std::cout << "SCUI registry, protected selector, and project-root containment PASS\n";
    }
    return failures == 0 ? 0 : 1;
}
