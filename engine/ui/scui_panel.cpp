#include "engine/ui/scui_panel.hpp"

#include "engine/data/udata.hpp"

#include <algorithm>
#include <cctype>
#include <charconv>
#include <fstream>
#include <sstream>
#include <system_error>

namespace signalcloud::ui {
namespace {

std::string trim(std::string_view value) {
    std::size_t first = 0;
    while (first < value.size() && std::isspace(static_cast<unsigned char>(value[first])) != 0) {
        ++first;
    }
    std::size_t last = value.size();
    while (last > first && std::isspace(static_cast<unsigned char>(value[last - 1])) != 0) {
        --last;
    }
    return std::string(value.substr(first, last - first));
}

bool valid_token(std::string_view value, bool command_token = false) {
    if (value.empty()) {
        return false;
    }
    const auto first_ok = [](char c) {
        return std::isalpha(static_cast<unsigned char>(c)) != 0 || c == '_';
    };
    const auto rest_ok = [command_token](char c) {
        return std::isalnum(static_cast<unsigned char>(c)) != 0 || c == '_' || c == '-' || c == '.' ||
            (command_token && c == ':');
    };
    return first_ok(value.front()) && std::all_of(value.begin() + 1, value.end(), rest_ok);
}

std::optional<std::string> json_string(std::string_view raw) {
    const std::string value = trim(raw);
    if (value.size() < 2U || value.front() != '"' || value.back() != '"') {
        return std::nullopt;
    }
    std::string result;
    result.reserve(value.size() - 2U);
    bool escaped = false;
    for (std::size_t index = 1U; index + 1U < value.size(); ++index) {
        const char c = value[index];
        if (escaped) {
            switch (c) {
                case 'n': result.push_back('\n'); break;
                case 'r': result.push_back('\r'); break;
                case 't': result.push_back('\t'); break;
                case '\\': result.push_back('\\'); break;
                case '"': result.push_back('"'); break;
                default: result.push_back(c); break;
            }
            escaped = false;
        } else if (c == '\\') {
            escaped = true;
        } else {
            result.push_back(c);
        }
    }
    if (escaped) {
        return std::nullopt;
    }
    return result;
}

std::optional<bool> json_bool(std::string_view raw) {
    const std::string value = trim(raw);
    if (value == "true") {
        return true;
    }
    if (value == "false") {
        return false;
    }
    return std::nullopt;
}

std::optional<double> json_number(std::string_view raw) {
    const std::string value = trim(raw);
    if (value.empty()) {
        return std::nullopt;
    }
    double result = 0.0;
    const auto parsed = std::from_chars(value.data(), value.data() + value.size(), result);
    if (parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size()) {
        return std::nullopt;
    }
    return result;
}

std::optional<int> json_int(std::string_view raw) {
    const std::string value = trim(raw);
    if (value.empty()) {
        return std::nullopt;
    }
    int result = 0;
    const auto parsed = std::from_chars(value.data(), value.data() + value.size(), result);
    if (parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size()) {
        return std::nullopt;
    }
    return result;
}

std::vector<std::string> json_string_array(std::string_view raw) {
    const std::string value = trim(raw);
    std::vector<std::string> result;
    if (value.size() < 2U || value.front() != '[' || value.back() != ']') {
        return result;
    }
    std::size_t index = 1U;
    while (index + 1U < value.size()) {
        while (index + 1U < value.size() &&
               (std::isspace(static_cast<unsigned char>(value[index])) != 0 || value[index] == ',')) {
            ++index;
        }
        if (index + 1U >= value.size() || value[index] == ']') {
            break;
        }
        if (value[index] != '"') {
            result.clear();
            return result;
        }
        const std::size_t start = index;
        ++index;
        bool escaped = false;
        while (index < value.size()) {
            if (!escaped && value[index] == '"') {
                break;
            }
            if (!escaped && value[index] == '\\') {
                escaped = true;
            } else {
                escaped = false;
            }
            ++index;
        }
        if (index >= value.size()) {
            result.clear();
            return result;
        }
        const auto parsed = json_string(std::string_view(value).substr(start, index - start + 1U));
        if (!parsed.has_value()) {
            result.clear();
            return result;
        }
        result.push_back(*parsed);
        ++index;
    }
    return result;
}

ScuiControlType parse_control_type(std::string_view value) {
    if (value == "label") return ScuiControlType::label;
    if (value == "button") return ScuiControlType::button;
    if (value == "toggle") return ScuiControlType::toggle;
    if (value == "radio") return ScuiControlType::radio;
    if (value == "dropdown") return ScuiControlType::dropdown;
    if (value == "number") return ScuiControlType::number;
    if (value == "slider") return ScuiControlType::slider;
    if (value == "color") return ScuiControlType::color;
    if (value == "list") return ScuiControlType::list;
    if (value == "tree") return ScuiControlType::tree;
    if (value == "progress") return ScuiControlType::progress;
    if (value == "tabs") return ScuiControlType::tabs;
    if (value == "graph-inspector") return ScuiControlType::graph_inspector;
    if (value == "confirmation") return ScuiControlType::confirmation;
    return ScuiControlType::unsupported;
}

bool native_supported(ScuiControlType type) {
    switch (type) {
        case ScuiControlType::label:
        case ScuiControlType::button:
        case ScuiControlType::toggle:
        case ScuiControlType::radio:
        case ScuiControlType::dropdown:
        case ScuiControlType::number:
        case ScuiControlType::slider:
        case ScuiControlType::color:
        case ScuiControlType::list:
        case ScuiControlType::tree:
        case ScuiControlType::progress:
        case ScuiControlType::graph_inspector:
        case ScuiControlType::confirmation:
            return true;
        case ScuiControlType::tabs:
        case ScuiControlType::unsupported:
            return false;
    }
    return false;
}

bool focusable(ScuiControlType type) {
    return type != ScuiControlType::label && type != ScuiControlType::progress &&
        type != ScuiControlType::tabs && type != ScuiControlType::unsupported;
}

std::pair<std::string, std::string> actions_for(ScuiControlType type) {
    switch (type) {
        case ScuiControlType::button:
        case ScuiControlType::confirmation:
            return {"left-click", "Enter or Space"};
        case ScuiControlType::toggle:
            return {"left-click", "Space"};
        case ScuiControlType::radio:
        case ScuiControlType::dropdown:
        case ScuiControlType::list:
        case ScuiControlType::tree:
        case ScuiControlType::graph_inspector:
            return {"left-click", "Up/Down and Enter"};
        case ScuiControlType::number:
        case ScuiControlType::slider:
            return {"left-click or drag", "Left/Right"};
        case ScuiControlType::color:
            return {"left-click", "Enter"};
        case ScuiControlType::label:
        case ScuiControlType::progress:
        case ScuiControlType::tabs:
        case ScuiControlType::unsupported:
            return {"none", "none"};
    }
    return {"none", "none"};
}

std::map<std::string, std::string> fields_for_section(
    const data::UDataDocument& document, std::string_view section) {
    std::map<std::string, std::string> result;
    for (const auto& entry : document.entries()) {
        if (entry.section == section) {
            result[entry.key] = entry.raw_json;
        }
    }
    return result;
}

std::optional<std::string> string_field(
    const std::map<std::string, std::string>& fields, std::string_view key) {
    const auto match = fields.find(std::string(key));
    if (match == fields.end()) {
        return std::nullopt;
    }
    return json_string(match->second);
}

std::optional<bool> bool_field(
    const std::map<std::string, std::string>& fields, std::string_view key) {
    const auto match = fields.find(std::string(key));
    if (match == fields.end()) {
        return std::nullopt;
    }
    return json_bool(match->second);
}

std::optional<double> number_field(
    const std::map<std::string, std::string>& fields, std::string_view key) {
    const auto match = fields.find(std::string(key));
    if (match == fields.end()) {
        return std::nullopt;
    }
    return json_number(match->second);
}

std::optional<int> int_field(
    const std::map<std::string, std::string>& fields, std::string_view key) {
    const auto match = fields.find(std::string(key));
    if (match == fields.end()) {
        return std::nullopt;
    }
    return json_int(match->second);
}

}  // namespace

ScuiPanel ScuiPanel::parse(std::string_view text) {
    ScuiPanel panel;
    const data::UDataDocument document = data::UDataDocument::parse(text);
    for (const auto& issue : document.issues()) {
        panel.issues.push_back({
            issue.severity == data::UDataIssue::Severity::error ? ScuiIssueSeverity::error : ScuiIssueSeverity::warning,
            "line " + std::to_string(issue.line_number),
            issue.message,
        });
    }

    const auto panel_fields = fields_for_section(document, "panel");
    panel.schema_name = string_field(panel_fields, "schema_name").value_or("");
    panel.schema_major = int_field(panel_fields, "schema_major").value_or(0);
    panel.schema_minor = int_field(panel_fields, "schema_minor").value_or(0);
    panel.panel_id = string_field(panel_fields, "panel_id").value_or("");
    panel.title = string_field(panel_fields, "title").value_or("");
    panel.layout = string_field(panel_fields, "layout").value_or("stack");
    panel.help_topic = string_field(panel_fields, "help_topic").value_or("");

    static const std::set<std::string, std::less<>> known_panel{
        "schema_name", "schema_major", "schema_minor", "panel_id", "title", "layout", "help_topic"};
    for (const auto& [key, value] : panel_fields) {
        if (!known_panel.contains(key)) {
            panel.unknown_panel_fields[key] = value;
        }
    }

    if (panel.schema_name != "signalcloud.scui") {
        panel.issues.push_back({ScuiIssueSeverity::error, "panel.schema_name", "schema_name must be signalcloud.scui"});
    }
    if (panel.schema_major != 1) {
        panel.issues.push_back({ScuiIssueSeverity::error, "panel.schema_major", "unsupported SCUI major version"});
    }
    if (!valid_token(panel.panel_id)) {
        panel.issues.push_back({ScuiIssueSeverity::error, "panel.panel_id", "panel_id is missing or invalid"});
    }
    if (panel.title.empty()) {
        panel.issues.push_back({ScuiIssueSeverity::warning, "panel.title", "panel title is empty"});
    }

    const auto state_fields = fields_for_section(document, "state");
    panel.initial_values = state_fields;

    std::set<std::string, std::less<>> seen_controls;
    std::set<std::string, std::less<>> known_sections{"panel", "state"};
    for (const auto& entry : document.entries()) {
        constexpr std::string_view prefix = "control.";
        if (!std::string_view(entry.section).starts_with(prefix)) {
            continue;
        }
        known_sections.insert(entry.section);
        const std::string id = entry.section.substr(prefix.size());
        if (seen_controls.contains(id)) {
            continue;
        }
        seen_controls.insert(id);
        if (!valid_token(id)) {
            panel.issues.push_back({ScuiIssueSeverity::warning, entry.section, "invalid control id; control skipped"});
            continue;
        }
        const auto fields = fields_for_section(document, entry.section);
        ScuiControl control;
        control.id = id;
        control.type_name = string_field(fields, "type").value_or("unsupported");
        control.type = parse_control_type(control.type_name);
        control.label = string_field(fields, "label").value_or("");
        control.value_binding = string_field(fields, "value_binding").value_or("");
        control.document_binding = string_field(fields, "document_binding").value_or("");
        control.order = int_field(fields, "order").value_or(0);
        control.minimum = number_field(fields, "minimum");
        control.maximum = number_field(fields, "maximum");
        control.step = number_field(fields, "step");
        const auto choices_entry = fields.find("choices");
        if (choices_entry != fields.end()) {
            control.choices = json_string_array(choices_entry->second);
        }
        control.command_id = string_field(fields, "command_id").value_or("");
        control.enabled = bool_field(fields, "enabled").value_or(true);
        control.visible = bool_field(fields, "visible").value_or(true);
        control.style_role = string_field(fields, "style_role").value_or("");
        control.tooltip = string_field(fields, "tooltip").value_or("");
        control.help_topic = string_field(fields, "help_topic").value_or("");

        static const std::set<std::string, std::less<>> known_control{
            "order", "type", "label", "value_binding", "document_binding", "minimum", "maximum", "step", "choices",
            "command_id", "enabled", "visible", "style_role", "tooltip", "help_topic"};
        for (const auto& [key, value] : fields) {
            if (!known_control.contains(key)) {
                control.unknown_fields[key] = value;
            }
        }

        if (control.type == ScuiControlType::unsupported) {
            panel.issues.push_back({ScuiIssueSeverity::warning, entry.section + ".type",
                                    "unsupported control type: " + control.type_name});
        }
        if (!control.command_id.empty() && !valid_token(control.command_id, true)) {
            panel.issues.push_back({ScuiIssueSeverity::warning, entry.section + ".command_id",
                                    "invalid command id; command blocked"});
            control.command_id.clear();
        }
        if (control.minimum.has_value() && control.maximum.has_value() && *control.minimum > *control.maximum) {
            panel.issues.push_back({ScuiIssueSeverity::warning, entry.section,
                                    "minimum exceeds maximum; values were swapped"});
            std::swap(control.minimum, control.maximum);
        }
        if (control.step.has_value() && *control.step <= 0.0) {
            panel.issues.push_back({ScuiIssueSeverity::warning, entry.section + ".step",
                                    "non-positive step ignored"});
            control.step.reset();
        }
        panel.controls.push_back(std::move(control));
    }

    for (const auto& entry : document.entries()) {
        if (!known_sections.contains(entry.section) && entry.section != "panel" && entry.section != "state") {
            panel.unknown_sections[entry.section][entry.key] = entry.raw_json;
        }
    }

    std::sort(panel.controls.begin(), panel.controls.end(), [](const ScuiControl& left, const ScuiControl& right) {
        if (left.order != right.order) {
            return left.order < right.order;
        }
        return left.id < right.id;
    });
    return panel;
}

ScuiPanel ScuiPanel::load(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        ScuiPanel panel;
        panel.issues.push_back({ScuiIssueSeverity::error, path.string(), "unable to open SCUI file"});
        return panel;
    }
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return parse(buffer.str());
}

bool ScuiPanel::valid() const noexcept {
    return std::none_of(issues.begin(), issues.end(), [](const ScuiIssue& issue) {
        return issue.severity == ScuiIssueSeverity::error;
    });
}

const ScuiControl* ScuiPanel::control(std::string_view id) const noexcept {
    const auto match = std::find_if(controls.begin(), controls.end(), [id](const ScuiControl& item) {
        return item.id == id;
    });
    return match == controls.end() ? nullptr : &*match;
}

ScuiNativeLayout ScuiNativeLayout::build(const ScuiPanel& panel, std::size_t rows_per_page) {
    ScuiNativeLayout result;
    result.panel_id = panel.panel_id;
    result.title = panel.title;
    const std::size_t safe_rows = std::max<std::size_t>(1U, rows_per_page);
    std::size_t visible_index = 0U;
    for (const auto& control : panel.controls) {
        if (!control.visible) {
            continue;
        }
        const auto [mouse_action, keyboard_action] = actions_for(control.type);
        ScuiNativeRow row;
        row.control_id = control.id;
        row.type = control.type;
        row.page = visible_index / safe_rows;
        row.row = visible_index % safe_rows;
        row.focusable = focusable(control.type) && control.enabled;
        row.supported = native_supported(control.type);
        row.mouse_action = mouse_action;
        row.keyboard_action = keyboard_action;
        result.rows.push_back(row);
        if (row.focusable) {
            result.focus_order.push_back(control.id);
        }
        if (!row.supported) {
            result.unsupported_controls.push_back(control.id);
        }
        ++visible_index;
    }
    result.page_count = visible_index == 0U ? 0U : ((visible_index - 1U) / safe_rows) + 1U;
    return result;
}

bool ScuiNativeCommandRegistry::register_command(std::string command_id) {
    if (!valid_token(command_id, true)) {
        return false;
    }
    return command_ids_.insert(std::move(command_id)).second;
}

bool ScuiNativeCommandRegistry::contains(std::string_view command_id) const noexcept {
    return command_ids_.contains(command_id);
}

bool ScuiNativeCommandRegistry::may_dispatch(const ScuiPanelEvent& event) const noexcept {
    return !event.panel_id.empty() && !event.control_id.empty() && contains(event.command_id);
}

std::string_view scui_control_type_name(ScuiControlType type) noexcept {
    switch (type) {
        case ScuiControlType::label: return "label";
        case ScuiControlType::button: return "button";
        case ScuiControlType::toggle: return "toggle";
        case ScuiControlType::radio: return "radio";
        case ScuiControlType::dropdown: return "dropdown";
        case ScuiControlType::number: return "number";
        case ScuiControlType::slider: return "slider";
        case ScuiControlType::color: return "color";
        case ScuiControlType::list: return "list";
        case ScuiControlType::tree: return "tree";
        case ScuiControlType::progress: return "progress";
        case ScuiControlType::tabs: return "tabs";
        case ScuiControlType::graph_inspector: return "graph-inspector";
        case ScuiControlType::confirmation: return "confirmation";
        case ScuiControlType::unsupported: return "unsupported";
    }
    return "unsupported";
}

}  // namespace signalcloud::ui
