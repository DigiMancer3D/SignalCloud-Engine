#pragma once

#include "engine/scfont/scfont.hpp"

#include <cstdint>
#include <filesystem>
#include <map>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

namespace signalcloud::font {

struct FontLoadIssue {
    std::string font_id;
    std::filesystem::path path;
    std::string message;
};

class FontService {
public:
    bool load(std::string font_id, const std::filesystem::path& path);
    bool reload(std::string_view font_id, const std::filesystem::path& path);

    [[nodiscard]] std::shared_ptr<const Font> snapshot(std::string_view font_id) const noexcept;
    [[nodiscard]] std::shared_ptr<const Font> default_font() const noexcept;
    [[nodiscard]] std::string_view default_font_id() const noexcept { return default_font_id_; }
    [[nodiscard]] std::uint64_t generation(std::string_view font_id) const noexcept;
    [[nodiscard]] const std::vector<FontLoadIssue>& issues() const noexcept { return issues_; }

    bool set_default(std::string font_id);
    void clear_issues() noexcept { issues_.clear(); }

private:
    struct Entry {
        std::shared_ptr<const Font> font;
        std::filesystem::path path;
        std::uint64_t generation{0U};
    };

    bool replace(std::string font_id, const std::filesystem::path& path, bool require_existing);

    std::map<std::string, Entry, std::less<>> fonts_;
    std::vector<FontLoadIssue> issues_;
    std::string default_font_id_;
};

}  // namespace signalcloud::font
