#pragma once

#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace signalcloud::ui {

struct ScuiRegistryIssue {
    enum class Severity { warning, error };
    Severity severity{Severity::warning};
    std::string location;
    std::string message;
};

struct ScuiRegistryEntry {
    std::string key;
    std::string panel_id;
    std::string label;
    std::filesystem::path relative_path;
    bool safe_room_only{true};
    std::string shortcut;
    std::vector<std::string> commands;
    std::filesystem::path native_state_path;
    std::filesystem::path default_document;
    std::string preview_kind;
    std::map<std::string, std::string, std::less<>> unknown_fields;
};

class ScuiPanelRegistry {
public:
    static ScuiPanelRegistry load(const std::filesystem::path& project_root,
                                  const std::filesystem::path& registry_path);

    [[nodiscard]] bool valid() const noexcept;
    [[nodiscard]] const ScuiRegistryEntry* find(std::string_view key) const noexcept;
    [[nodiscard]] std::vector<std::string> keys() const;
    [[nodiscard]] std::vector<std::string> labels() const;
    [[nodiscard]] const std::vector<ScuiRegistryEntry>& entries() const noexcept { return entries_; }
    [[nodiscard]] const std::vector<ScuiRegistryIssue>& issues() const noexcept { return issues_; }
    [[nodiscard]] std::string_view default_panel_key() const noexcept { return default_panel_key_; }
    [[nodiscard]] std::string_view selector_panel_id() const noexcept { return selector_panel_id_; }
    [[nodiscard]] const std::filesystem::path& project_root() const noexcept { return project_root_; }
    [[nodiscard]] const std::filesystem::path& registry_path() const noexcept { return registry_path_; }

private:
    std::filesystem::path project_root_;
    std::filesystem::path registry_path_;
    std::string default_panel_key_;
    std::string selector_panel_id_;
    std::vector<ScuiRegistryEntry> entries_;
    std::vector<ScuiRegistryIssue> issues_;
};

}  // namespace signalcloud::ui
