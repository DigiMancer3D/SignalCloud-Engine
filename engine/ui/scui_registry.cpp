#include "engine/ui/scui_registry.hpp"

#include "engine/data/udata.hpp"
#include "engine/ui/scui_panel.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <set>
#include <sstream>
#include <system_error>

namespace signalcloud::ui {
namespace {

std::string trim(std::string_view value) {
    std::size_t first = 0U;
    while (first < value.size() && std::isspace(static_cast<unsigned char>(value[first])) != 0) ++first;
    std::size_t last = value.size();
    while (last > first && std::isspace(static_cast<unsigned char>(value[last - 1U])) != 0) --last;
    return std::string(value.substr(first, last - first));
}

std::optional<std::string> json_string(std::string_view raw) {
    const std::string value = trim(raw);
    if (value.size() < 2U || value.front() != '"' || value.back() != '"') return std::nullopt;
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
    if (escaped) return std::nullopt;
    return result;
}

std::optional<bool> json_bool(std::string_view raw) {
    const std::string value = trim(raw);
    if (value == "true") return true;
    if (value == "false") return false;
    return std::nullopt;
}

std::vector<std::string> json_string_array(std::string_view raw) {
    const std::string value = trim(raw);
    std::vector<std::string> result;
    if (value.size() < 2U || value.front() != '[' || value.back() != ']') return result;
    std::size_t index = 1U;
    while (index + 1U < value.size()) {
        while (index + 1U < value.size() &&
               (std::isspace(static_cast<unsigned char>(value[index])) != 0 || value[index] == ',')) ++index;
        if (index + 1U >= value.size() || value[index] == ']') break;
        if (value[index] != '"') return {};
        const std::size_t start = index++;
        bool escaped = false;
        while (index < value.size()) {
            if (!escaped && value[index] == '"') break;
            if (!escaped && value[index] == '\\') escaped = true;
            else escaped = false;
            ++index;
        }
        if (index >= value.size()) return {};
        const auto parsed = json_string(std::string_view(value).substr(start, index - start + 1U));
        if (!parsed.has_value()) return {};
        result.push_back(*parsed);
        ++index;
    }
    return result;
}

std::map<std::string, std::string, std::less<>> fields_for(
    const data::UDataDocument& document, std::string_view section) {
    std::map<std::string, std::string, std::less<>> result;
    for (const auto& entry : document.entries()) {
        if (entry.section == section) result[entry.key] = entry.raw_json;
    }
    return result;
}

bool path_inside(const std::filesystem::path& root, const std::filesystem::path& relative,
                 std::filesystem::path* resolved = nullptr) {
    if (relative.empty() || relative.is_absolute()) return false;
    std::error_code ec;
    const auto root_absolute = std::filesystem::weakly_canonical(root, ec);
    if (ec) return false;
    ec.clear();
    const auto candidate = std::filesystem::weakly_canonical(root / relative, ec);
    if (ec) return false;
    auto root_it = root_absolute.begin();
    auto candidate_it = candidate.begin();
    for (; root_it != root_absolute.end(); ++root_it, ++candidate_it) {
        if (candidate_it == candidate.end() || *root_it != *candidate_it) return false;
    }
    if (resolved != nullptr) *resolved = candidate;
    return true;
}

std::optional<std::string> string_field(
    const std::map<std::string, std::string, std::less<>>& fields, std::string_view key) {
    const auto match = fields.find(key);
    return match == fields.end() ? std::nullopt : json_string(match->second);
}

}  // namespace

ScuiPanelRegistry ScuiPanelRegistry::load(const std::filesystem::path& project_root,
                                          const std::filesystem::path& registry_path) {
    ScuiPanelRegistry registry;
    registry.project_root_ = project_root;
    registry.registry_path_ = registry_path;
    data::UDataDocument document;
    try {
        document = data::UDataDocument::load(registry_path);
    } catch (const std::exception& ex) {
        registry.issues_.push_back({ScuiRegistryIssue::Severity::error, registry_path.string(), ex.what()});
        return registry;
    }
    for (const auto& issue : document.issues()) {
        registry.issues_.push_back({
            issue.severity == data::UDataIssue::Severity::error
                ? ScuiRegistryIssue::Severity::error : ScuiRegistryIssue::Severity::warning,
            "line " + std::to_string(issue.line_number), issue.message});
    }
    const auto registry_fields = fields_for(document, "registry");
    const std::string schema = string_field(registry_fields, "schema_name").value_or("");
    if (schema != "signalcloud.scui.registry") {
        registry.issues_.push_back({ScuiRegistryIssue::Severity::error, "registry.schema_name",
                                    "schema_name must be signalcloud.scui.registry"});
    }
    const auto major_raw = registry_fields.find("schema_major");
    if (major_raw == registry_fields.end() || trim(major_raw->second) != "1") {
        registry.issues_.push_back({ScuiRegistryIssue::Severity::error, "registry.schema_major",
                                    "unsupported SCUI registry major version"});
    }
    registry.default_panel_key_ = string_field(registry_fields, "default_panel").value_or("");
    registry.selector_panel_id_ = string_field(registry_fields, "selector_panel").value_or("");

    std::set<std::string, std::less<>> seen_keys;
    std::set<std::string, std::less<>> seen_ids;
    for (const auto& entry : document.entries()) {
        constexpr std::string_view prefix = "panel.";
        if (!std::string_view(entry.section).starts_with(prefix)) continue;
        const std::string key = entry.section.substr(prefix.size());
        if (seen_keys.contains(key)) continue;
        seen_keys.insert(key);
        const auto fields = fields_for(document, entry.section);
        ScuiRegistryEntry item;
        item.key = key;
        item.panel_id = string_field(fields, "panel_id").value_or("");
        item.label = string_field(fields, "label").value_or(key);
        item.relative_path = string_field(fields, "path").value_or("");
        const auto safe = fields.find("safe_room_only");
        item.safe_room_only = safe == fields.end() ? true : json_bool(safe->second).value_or(true);
        item.shortcut = string_field(fields, "shortcut").value_or("");
        const auto commands = fields.find("commands");
        if (commands != fields.end()) item.commands = json_string_array(commands->second);
        item.native_state_path = string_field(fields, "native_state_path").value_or("");
        item.default_document = string_field(fields, "default_document").value_or("");
        item.preview_kind = string_field(fields, "preview_kind").value_or("");

        static const std::set<std::string, std::less<>> known{
            "panel_id", "label", "path", "safe_room_only", "shortcut", "commands",
            "native_state_path", "default_document", "preview_kind"};
        for (const auto& [field_key, raw] : fields) {
            if (!known.contains(field_key)) item.unknown_fields[field_key] = raw;
        }

        if (item.key.empty() || item.panel_id.empty() || item.relative_path.empty()) {
            registry.issues_.push_back({ScuiRegistryIssue::Severity::warning, entry.section,
                                        "registry entry missing key, panel_id, or path and was skipped"});
            continue;
        }
        if (seen_ids.contains(item.panel_id)) {
            registry.issues_.push_back({ScuiRegistryIssue::Severity::warning, entry.section,
                                        "duplicate panel_id and entry was skipped"});
            continue;
        }
        seen_ids.insert(item.panel_id);
        std::filesystem::path resolved;
        if (!path_inside(project_root, item.relative_path, &resolved)) {
            registry.issues_.push_back({ScuiRegistryIssue::Severity::warning, entry.section + ".path",
                                        "panel path escapes project root and was skipped"});
            continue;
        }
        const ScuiPanel panel = ScuiPanel::load(resolved);
        if (!panel.valid() || panel.panel_id != item.panel_id) {
            registry.issues_.push_back({ScuiRegistryIssue::Severity::warning, entry.section,
                                        "registered panel failed validation or panel_id did not match"});
            continue;
        }
        registry.entries_.push_back(std::move(item));
    }
    std::sort(registry.entries_.begin(), registry.entries_.end(), [](const auto& left, const auto& right) {
        return left.key < right.key;
    });
    if (!registry.default_panel_key_.empty() && registry.find(registry.default_panel_key_) == nullptr) {
        registry.issues_.push_back({ScuiRegistryIssue::Severity::warning, "registry.default_panel",
                                    "default panel is not present in the validated registry"});
    }
    return registry;
}

bool ScuiPanelRegistry::valid() const noexcept {
    return !entries_.empty() && std::none_of(issues_.begin(), issues_.end(), [](const auto& issue) {
        return issue.severity == ScuiRegistryIssue::Severity::error;
    });
}

const ScuiRegistryEntry* ScuiPanelRegistry::find(std::string_view key) const noexcept {
    const auto match = std::find_if(entries_.begin(), entries_.end(), [key](const auto& entry) {
        return entry.key == key;
    });
    return match == entries_.end() ? nullptr : &*match;
}

std::vector<std::string> ScuiPanelRegistry::keys() const {
    std::vector<std::string> result;
    result.reserve(entries_.size());
    for (const auto& entry : entries_) result.push_back(entry.key);
    return result;
}

std::vector<std::string> ScuiPanelRegistry::labels() const {
    std::vector<std::string> result;
    result.reserve(entries_.size());
    for (const auto& entry : entries_) result.push_back(entry.label);
    return result;
}

}  // namespace signalcloud::ui
