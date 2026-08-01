#include "engine/scfont/font_service.hpp"

#include <exception>
#include <utility>

namespace signalcloud::font {

bool FontService::replace(std::string font_id, const std::filesystem::path& path,
                          bool require_existing) {
    if (font_id.empty()) {
        issues_.push_back({{}, path, "font id cannot be empty"});
        return false;
    }
    const auto existing = fonts_.find(font_id);
    if (require_existing && existing == fonts_.end()) {
        issues_.push_back({font_id, path, "cannot reload an unregistered font"});
        return false;
    }
    try {
        Font candidate = load_scfont(path);
        validate(candidate);
        Entry replacement;
        replacement.font = std::make_shared<const Font>(std::move(candidate));
        replacement.path = path;
        replacement.generation = existing == fonts_.end() ? 1U : existing->second.generation + 1U;
        fonts_.insert_or_assign(font_id, std::move(replacement));
        if (default_font_id_.empty()) default_font_id_ = font_id;
        return true;
    } catch (const std::exception& error) {
        // Transactional behavior: do not disturb an already-valid entry.
        issues_.push_back({std::move(font_id), path, error.what()});
        return false;
    }
}

bool FontService::load(std::string font_id, const std::filesystem::path& path) {
    return replace(std::move(font_id), path, false);
}

bool FontService::reload(std::string_view font_id, const std::filesystem::path& path) {
    return replace(std::string(font_id), path, true);
}

std::shared_ptr<const Font> FontService::snapshot(std::string_view font_id) const noexcept {
    const auto found = fonts_.find(font_id);
    return found == fonts_.end() ? std::shared_ptr<const Font>{} : found->second.font;
}

std::shared_ptr<const Font> FontService::default_font() const noexcept {
    return snapshot(default_font_id_);
}

std::uint64_t FontService::generation(std::string_view font_id) const noexcept {
    const auto found = fonts_.find(font_id);
    return found == fonts_.end() ? 0U : found->second.generation;
}

bool FontService::set_default(std::string font_id) {
    if (fonts_.find(font_id) == fonts_.end()) return false;
    default_font_id_ = std::move(font_id);
    return true;
}

}  // namespace signalcloud::font
