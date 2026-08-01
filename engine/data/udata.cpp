#include "engine/data/udata.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <system_error>

namespace signalcloud::data {
namespace {

std::string trim(std::string_view value) {
    std::size_t first = 0;
    while (first < value.size() && std::isspace(static_cast<unsigned char>(value[first]))) {
        ++first;
    }
    std::size_t last = value.size();
    while (last > first && std::isspace(static_cast<unsigned char>(value[last - 1]))) {
        --last;
    }
    return std::string(value.substr(first, last - first));
}

bool valid_identifier(std::string_view value) {
    if (value.empty()) {
        return false;
    }
    const auto valid_first = [](char c) {
        return std::isalpha(static_cast<unsigned char>(c)) || c == '_';
    };
    const auto valid_rest = [](char c) {
        return std::isalnum(static_cast<unsigned char>(c)) || c == '_' || c == '-' || c == '.';
    };
    if (!valid_first(value.front())) {
        return false;
    }
    return std::all_of(value.begin() + 1, value.end(), valid_rest);
}

bool looks_like_json_value(std::string_view value) {
    const std::string compact = trim(value);
    if (compact.empty()) {
        return false;
    }
    const char first = compact.front();
    const char last = compact.back();
    if ((first == '{' && last == '}') || (first == '[' && last == ']') ||
        (first == '"' && last == '"')) {
        return true;
    }
    if (compact == "true" || compact == "false" || compact == "null") {
        return true;
    }
    if (first == '-' || std::isdigit(static_cast<unsigned char>(first))) {
        return true;
    }
    return false;
}

}  // namespace

UDataDocument UDataDocument::parse(std::string_view text) {
    UDataDocument document;
    std::istringstream stream{std::string(text)};
    std::string line;
    std::string current_section;
    std::size_t line_number = 0;

    while (std::getline(stream, line)) {
        ++line_number;
        const std::string cleaned = trim(line);
        if (cleaned.empty() || cleaned.starts_with('#') || cleaned.starts_with("//")) {
            continue;
        }
        if (cleaned.starts_with("@udata")) {
            continue;
        }
        if (cleaned.front() == '[' && cleaned.back() == ']') {
            current_section = trim(std::string_view(cleaned).substr(1, cleaned.size() - 2));
            if (!valid_identifier(current_section)) {
                document.issues_.push_back({UDataIssue::Severity::error, line_number,
                                            "Invalid section name: " + current_section});
                current_section.clear();
                continue;
            }
            if (std::find(document.section_order_.begin(), document.section_order_.end(),
                          current_section) == document.section_order_.end()) {
                document.section_order_.push_back(current_section);
            }
            continue;
        }
        if (current_section.empty()) {
            document.issues_.push_back({UDataIssue::Severity::warning, line_number,
                                        "Entry appears before any valid section and was skipped."});
            continue;
        }
        if (!cleaned.ends_with(';')) {
            document.issues_.push_back({UDataIssue::Severity::warning, line_number,
                                        "Entry is missing the required semicolon and was skipped."});
            continue;
        }

        const std::string without_semicolon = trim(std::string_view(cleaned).substr(0, cleaned.size() - 1));
        const std::size_t colon = without_semicolon.find(':');
        if (colon == std::string::npos) {
            document.issues_.push_back({UDataIssue::Severity::warning, line_number,
                                        "Entry is missing ':' and was skipped."});
            continue;
        }

        const std::string key = trim(std::string_view(without_semicolon).substr(0, colon));
        const std::string raw_json = trim(std::string_view(without_semicolon).substr(colon + 1));
        if (!valid_identifier(key)) {
            document.issues_.push_back({UDataIssue::Severity::warning, line_number,
                                        "Invalid variable name and entry was skipped: " + key});
            continue;
        }
        if (!looks_like_json_value(raw_json)) {
            document.issues_.push_back({UDataIssue::Severity::warning, line_number,
                                        "Value does not resemble JSON and entry was skipped: " + key});
            continue;
        }

        const auto duplicate = std::find_if(document.entries_.begin(), document.entries_.end(),
            [&](const UDataEntry& entry) {
                return entry.section == current_section && entry.key == key;
            });
        if (duplicate != document.entries_.end()) {
            document.issues_.push_back({UDataIssue::Severity::warning, line_number,
                                        "Duplicate variable; the last valid value wins: " + key});
            document.entries_.erase(duplicate);
        }
        document.entries_.push_back({current_section, key, raw_json, line_number});
    }

    return document;
}

UDataDocument UDataDocument::load(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        throw std::runtime_error("Unable to open .udata file: " + path.string());
    }
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return parse(buffer.str());
}

std::optional<std::string> UDataDocument::value(std::string_view section,
                                               std::string_view key) const {
    const auto match = std::find_if(entries_.rbegin(), entries_.rend(),
        [&](const UDataEntry& entry) {
            return entry.section == section && entry.key == key;
        });
    if (match == entries_.rend()) {
        return std::nullopt;
    }
    return match->raw_json;
}

bool UDataDocument::has_errors() const noexcept {
    return std::any_of(issues_.begin(), issues_.end(), [](const UDataIssue& issue) {
        return issue.severity == UDataIssue::Severity::error;
    });
}

std::string UDataDocument::serialize() const {
    std::ostringstream output;
    output << "@udata 1\n\n";

    for (const std::string& section : section_order_) {
        output << '[' << section << "]\n";
        for (const UDataEntry& entry : entries_) {
            if (entry.section == section) {
                output << entry.key << ": " << entry.raw_json << ";\n";
            }
        }
        output << '\n';
    }
    return output.str();
}

void UDataDocument::set(std::string section, std::string key, std::string raw_json) {
    if (!valid_identifier(section) || !valid_identifier(key) || !looks_like_json_value(raw_json)) {
        throw std::invalid_argument("Invalid .udata section, key, or JSON-like value.");
    }
    if (std::find(section_order_.begin(), section_order_.end(), section) == section_order_.end()) {
        section_order_.push_back(section);
    }
    entries_.erase(std::remove_if(entries_.begin(), entries_.end(),
        [&](const UDataEntry& entry) {
            return entry.section == section && entry.key == key;
        }), entries_.end());
    entries_.push_back({std::move(section), std::move(key), std::move(raw_json), 0});
}

bool UDataDocument::save_atomic(const std::filesystem::path& path, std::string* error) const {
    try {
        const std::filesystem::path tmp = path.string() + ".tmp";
        const std::filesystem::path bak = path.string() + ".bak";
        {
            std::ofstream output(tmp, std::ios::binary | std::ios::trunc);
            if (!output) {
                throw std::runtime_error("Unable to open temporary save file.");
            }
            output << serialize();
            output.flush();
            if (!output) {
                throw std::runtime_error("Unable to flush temporary save file.");
            }
        }

        const UDataDocument validation = load(tmp);
        if (validation.has_errors()) {
            throw std::runtime_error("Temporary save failed validation.");
        }

        std::error_code ec;
        if (std::filesystem::exists(path)) {
            std::filesystem::remove(bak, ec);
            ec.clear();
            std::filesystem::rename(path, bak, ec);
            if (ec) {
                throw std::runtime_error("Unable to rotate existing save: " + ec.message());
            }
        }
        std::filesystem::rename(tmp, path, ec);
        if (ec) {
            if (std::filesystem::exists(bak)) {
                std::filesystem::rename(bak, path, ec);
            }
            throw std::runtime_error("Unable to promote temporary save: " + ec.message());
        }
        return true;
    } catch (const std::exception& ex) {
        if (error != nullptr) {
            *error = ex.what();
        }
        return false;
    }
}

}  // namespace signalcloud::data
