#include "engine/ui/scui_panel.hpp"

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

}  // namespace

int main(int argc, char** argv) {
    const std::filesystem::path root = argc > 1 ? argv[1] : std::filesystem::current_path();
    const auto panel = signalcloud::ui::ScuiPanel::load(
        root / "content/core/ui/authoring_lab_project_selector.scui");

    expect(panel.valid(), "proof SCUI panel validates");
    expect(panel.schema_name == "signalcloud.scui", "schema name parsed");
    expect(panel.schema_major == 1, "schema major parsed");
    expect(panel.panel_id == "authoring_lab.project_selector", "panel id parsed");
    expect(panel.controls.size() == 6U, "all proof controls parsed");
    expect(panel.initial_values.contains("point_budget"), "initial state preserved");
    expect(panel.unknown_panel_fields.contains("future_alpha_hint"), "unknown panel field preserved");

    const auto* project = panel.control("project");
    expect(project != nullptr, "project control available");
    if (project != nullptr) {
        expect(project->type == signalcloud::ui::ScuiControlType::dropdown, "project is dropdown");
        expect(project->choices.size() == 3U, "project choices parsed");
        expect(project->command_id == "authoring.project.select", "project command parsed");
        expect(project->unknown_fields.contains("future_native_role"), "unknown control field preserved");
    }

    const auto layout = signalcloud::ui::ScuiNativeLayout::build(panel, 4U);
    expect(layout.page_count == 2U, "native layout pages bounded");
    expect(layout.rows.size() == 6U, "native layout includes visible controls");
    expect(layout.focus_order.size() == 4U, "native focus order skips label and progress");
    expect(layout.unsupported_controls.empty(), "proof controls supported by native foundation");
    expect(layout.rows[2].keyboard_action == "Space", "toggle keyboard equivalent defined");

    signalcloud::ui::ScuiNativeCommandRegistry commands;
    expect(commands.register_command("authoring.project.select"), "allowlisted command registered");
    expect(!commands.register_command("authoring.project.select"), "duplicate command rejected");
    expect(!commands.register_command("bad command"), "invalid command rejected");
    const signalcloud::ui::ScuiPanelEvent allowed{
        panel.panel_id, "project", "authoring.project.select", "{\"value\":\"current\"}", "tx-1"};
    const signalcloud::ui::ScuiPanelEvent blocked{
        panel.panel_id, "project", "os.shell.execute", "{}", "tx-2"};
    expect(commands.may_dispatch(allowed), "allowlisted native event may dispatch");
    expect(!commands.may_dispatch(blocked), "unknown native command remains blocked");

    const auto malformed = signalcloud::ui::ScuiPanel::parse(
        "@udata 1\n[panel]\nschema_name: \"signalcloud.scui\";\n"
        "schema_major: 99;\npanel_id: \"bad panel\";\n");
    expect(!malformed.valid(), "unsupported schema and invalid id fail safely");

    if (failures == 0) {
        std::cout << "SCUI shared parser, native layout, focus, and command allowlist PASS\n";
    }
    return failures == 0 ? 0 : 1;
}
