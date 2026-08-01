#pragma once

#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace signalcloud::data {

struct UDataEntry {
    std::string section;
    std::string key;
    std::string raw_json;
    std::size_t line_number{0};
};

struct UDataIssue {
    enum class Severity { warning, error };
    Severity severity{Severity::warning};
    std::size_t line_number{0};
    std::string message;
};

class UDataDocument {
public:
    static UDataDocument parse(std::string_view text);
    static UDataDocument load(const std::filesystem::path& path);

    [[nodiscard]] std::optional<std::string> value(std::string_view section,
                                                   std::string_view key) const;
    [[nodiscard]] const std::vector<UDataEntry>& entries() const noexcept { return entries_; }
    [[nodiscard]] const std::vector<UDataIssue>& issues() const noexcept { return issues_; }
    [[nodiscard]] bool has_errors() const noexcept;
    [[nodiscard]] std::string serialize() const;

    void set(std::string section, std::string key, std::string raw_json);
    bool save_atomic(const std::filesystem::path& path, std::string* error = nullptr) const;

private:
    std::vector<UDataEntry> entries_;
    std::vector<UDataIssue> issues_;
    std::vector<std::string> section_order_;
};

}  // namespace signalcloud::data
