#pragma once

#include <cstddef>
#include <filesystem>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace signalcloud::ui {

enum class ScuiIssueSeverity { warning, error };

enum class ScuiControlType {
    label,
    button,
    toggle,
    radio,
    dropdown,
    number,
    slider,
    color,
    list,
    tree,
    progress,
    tabs,
    graph_inspector,
    confirmation,
    unsupported,
};

struct ScuiIssue {
    ScuiIssueSeverity severity{ScuiIssueSeverity::warning};
    std::string location;
    std::string message;
};

struct ScuiControl {
    std::string id;
    ScuiControlType type{ScuiControlType::unsupported};
    std::string type_name{"unsupported"};
    std::string label;
    std::string value_binding;
    std::string document_binding;
    int order{0};
    std::optional<double> minimum;
    std::optional<double> maximum;
    std::optional<double> step;
    std::vector<std::string> choices;
    std::string command_id;
    bool enabled{true};
    bool visible{true};
    std::string style_role;
    std::string tooltip;
    std::string help_topic;
    std::map<std::string, std::string> unknown_fields;
};

class ScuiPanel {
public:
    static ScuiPanel parse(std::string_view text);
    static ScuiPanel load(const std::filesystem::path& path);

    [[nodiscard]] bool valid() const noexcept;
    [[nodiscard]] const ScuiControl* control(std::string_view id) const noexcept;

    std::string schema_name;
    int schema_major{0};
    int schema_minor{0};
    std::string panel_id;
    std::string title;
    std::string layout{"stack"};
    std::string help_topic;
    std::map<std::string, std::string> initial_values;
    std::vector<ScuiControl> controls;
    std::map<std::string, std::string> unknown_panel_fields;
    std::map<std::string, std::map<std::string, std::string>> unknown_sections;
    std::vector<ScuiIssue> issues;
};

struct ScuiNativeRow {
    std::string control_id;
    ScuiControlType type{ScuiControlType::unsupported};
    std::size_t page{0};
    std::size_t row{0};
    bool focusable{false};
    bool supported{false};
    std::string mouse_action;
    std::string keyboard_action;
};

struct ScuiNativeLayout {
    std::string panel_id;
    std::string title;
    std::size_t page_count{0};
    std::vector<ScuiNativeRow> rows;
    std::vector<std::string> focus_order;
    std::vector<std::string> unsupported_controls;

    static ScuiNativeLayout build(const ScuiPanel& panel, std::size_t rows_per_page = 7U);
};

struct ScuiPanelEvent {
    std::string panel_id;
    std::string control_id;
    std::string command_id;
    std::string payload_json;
    std::string transaction_id;
};

class ScuiNativeCommandRegistry {
public:
    bool register_command(std::string command_id);
    [[nodiscard]] bool contains(std::string_view command_id) const noexcept;
    [[nodiscard]] bool may_dispatch(const ScuiPanelEvent& event) const noexcept;
    [[nodiscard]] std::size_t size() const noexcept { return command_ids_.size(); }

private:
    std::set<std::string, std::less<>> command_ids_;
};

[[nodiscard]] std::string_view scui_control_type_name(ScuiControlType type) noexcept;

}  // namespace signalcloud::ui
