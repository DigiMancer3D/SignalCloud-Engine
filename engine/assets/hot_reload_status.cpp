#include "engine/assets/hot_reload_status.hpp"

#include "engine/data/udata.hpp"

#include <algorithm>
#include <charconv>
#include <optional>
#include <set>
#include <stdexcept>

namespace signalcloud::assets {
namespace {

std::string unquote(std::optional<std::string> raw) {
    if (!raw.has_value()) return {};
    std::string value = *raw;
    if (value.size() >= 2U && value.front() == '"' && value.back() == '"') {
        value = value.substr(1U, value.size() - 2U);
    }
    return value;
}

std::uint64_t unsigned_value(std::optional<std::string> raw) {
    if (!raw.has_value()) return 0U;
    std::uint64_t value = 0U;
    const std::string text = unquote(raw);
    const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
    return result.ec == std::errc{} ? value : 0U;
}

bool safe_relative(const std::filesystem::path& path) {
    if (path.empty() || path.is_absolute()) return false;
    return std::none_of(path.begin(), path.end(), [](const auto& part) { return part == ".."; });
}

bool inside_root(const std::filesystem::path& root, const std::filesystem::path& path) {
    const auto resolved = std::filesystem::weakly_canonical(root / path);
    const auto relative = resolved.lexically_relative(root);
    const std::string text = relative.generic_string();
    return !text.empty() && text != ".." && !text.starts_with("../");
}

bool valid_hash(std::string_view value) {
    return value.size() == 64U && std::all_of(value.begin(), value.end(), [](char c) {
        return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
    });
}

std::size_t count_type(const std::vector<HotReloadStatusEntry>& entries, std::string_view type) {
    return static_cast<std::size_t>(std::count_if(entries.begin(), entries.end(), [&](const auto& entry) {
        return entry.status == "changed" && entry.asset_type == type;
    }));
}

}  // namespace

HotReloadStatus HotReloadStatus::load(const std::filesystem::path& project_root,
                                      const std::filesystem::path& status_path) {
    HotReloadStatus status;
    try {
        const auto root = std::filesystem::weakly_canonical(project_root);
        const auto document = signalcloud::data::UDataDocument::load(status_path);
        if (document.has_errors()) {
            status.errors_.push_back("hot-reload status contains UDATA errors");
            return status;
        }
        if (unquote(document.value("status", "schema_name")) != "signalcloud.hot-reload-status") {
            status.errors_.push_back("unexpected hot-reload status schema");
        }
        if (unquote(document.value("status", "mode")) != "protected-authoring-preview") {
            status.errors_.push_back("hot-reload status is not protected-authoring-preview");
        }
        status.generated_unix_ = unsigned_value(document.value("status", "generated_unix"));
        status.transaction_id_ = unquote(document.value("status", "transaction_id"));
        if (!status.transaction_id_.empty() && status.transaction_id_.size() > 64U) {
            status.errors_.push_back("hot-reload transaction_id is too long");
        }
        std::set<std::string> ids;
        for (const auto& entry : document.entries()) {
            if (!entry.section.starts_with("asset.") || entry.key != "asset_id") continue;
            HotReloadStatusEntry asset;
            asset.asset_id = unquote(document.value(entry.section, "asset_id"));
            asset.relative_path = unquote(document.value(entry.section, "relative_path"));
            asset.asset_type = unquote(document.value(entry.section, "asset_type"));
            asset.indexed_sha256 = unquote(document.value(entry.section, "indexed_sha256"));
            asset.observed_sha256 = unquote(document.value(entry.section, "observed_sha256"));
            asset.status = unquote(document.value(entry.section, "status"));
            asset.staged_state_path = unquote(document.value(entry.section, "staged_state_path"));
            asset.compiled_runtime_path = unquote(document.value(entry.section, "compiled_runtime_path"));
            asset.companion_sha256 = unquote(document.value(entry.section, "companion_sha256"));
            asset.point_count = unsigned_value(document.value(entry.section, "point_count"));
            if (asset.asset_id.empty() || !ids.insert(asset.asset_id).second) {
                status.errors_.push_back("duplicate or empty hot-reload status asset_id");
                continue;
            }
            if (!safe_relative(asset.relative_path) || !inside_root(root, asset.relative_path)) {
                status.errors_.push_back("unsafe hot-reload status path for " + asset.asset_id);
                continue;
            }
            if (!asset.staged_state_path.empty() &&
                (!safe_relative(asset.staged_state_path) || !inside_root(root, asset.staged_state_path))) {
                status.errors_.push_back("unsafe staged state path for " + asset.asset_id);
                continue;
            }
            if (!asset.compiled_runtime_path.empty() &&
                (!safe_relative(asset.compiled_runtime_path) || !inside_root(root, asset.compiled_runtime_path))) {
                status.errors_.push_back("unsafe compiled runtime path for " + asset.asset_id);
                continue;
            }
            if (asset.status == "changed" && !valid_hash(asset.observed_sha256)) {
                status.errors_.push_back("changed hot-reload entry has invalid observed hash");
                continue;
            }
            if (asset.asset_type == "pcp3_project" && asset.status == "changed") {
                if (asset.staged_state_path.empty() || !valid_hash(asset.companion_sha256)) {
                    status.errors_.push_back("changed PCP3 entry is missing validated companion telemetry");
                    continue;
                }
            }
            if ((asset.asset_type == "jitter_map" || asset.asset_type == "texture_graph") &&
                asset.status == "changed" && asset.compiled_runtime_path.empty()) {
                status.errors_.push_back("changed material entry is missing compiled runtime telemetry");
                continue;
            }
            if (asset.asset_type == "audio_interference_profile" &&
                asset.status == "changed" && asset.compiled_runtime_path.empty()) {
                status.errors_.push_back("changed audio entry is missing compiled runtime telemetry");
                continue;
            }
            if (asset.asset_type == "signalcloud_font" &&
                asset.status == "changed" && asset.staged_state_path.empty()) {
                status.errors_.push_back("changed font entry is missing validated staged source telemetry");
                continue;
            }
            status.entries_.push_back(std::move(asset));
        }
    } catch (const std::exception& ex) {
        status.errors_.push_back(ex.what());
    }
    return status;
}

std::size_t HotReloadStatus::changed_count() const noexcept {
    return static_cast<std::size_t>(std::count_if(entries_.begin(), entries_.end(), [](const auto& entry) {
        return entry.status == "changed";
    }));
}

std::size_t HotReloadStatus::changed_light_count() const noexcept {
    return count_type(entries_, "light_set");
}

std::size_t HotReloadStatus::changed_scui_count() const noexcept {
    return count_type(entries_, "scui");
}

std::size_t HotReloadStatus::changed_pcp3_count() const noexcept {
    return count_type(entries_, "pcp3_project");
}

std::size_t HotReloadStatus::changed_material_count() const noexcept {
    return static_cast<std::size_t>(std::count_if(entries_.begin(), entries_.end(), [](const auto& entry) {
        return entry.status == "changed" &&
               (entry.asset_type == "jitter_map" || entry.asset_type == "texture_graph");
    }));
}

std::size_t HotReloadStatus::changed_audio_count() const noexcept {
    return count_type(entries_, "audio_interference_profile");
}

std::size_t HotReloadStatus::changed_font_count() const noexcept {
    return count_type(entries_, "signalcloud_font");
}

const HotReloadStatusEntry* HotReloadStatus::changed_for_path(std::string_view relative_path) const noexcept {
    const auto found = std::find_if(entries_.begin(), entries_.end(), [&](const auto& entry) {
        return entry.status == "changed" && entry.relative_path.generic_string() == relative_path;
    });
    return found == entries_.end() ? nullptr : &*found;
}

const HotReloadStatusEntry* HotReloadStatus::changed_light_set() const noexcept {
    const auto found = std::find_if(entries_.begin(), entries_.end(), [](const auto& entry) {
        return entry.status == "changed" && entry.asset_type == "light_set" &&
               !entry.staged_state_path.empty() && !entry.compiled_runtime_path.empty();
    });
    return found == entries_.end() ? nullptr : &*found;
}

std::vector<const HotReloadStatusEntry*> HotReloadStatus::changed_pcp3_projects() const {
    std::vector<const HotReloadStatusEntry*> changed;
    for (const auto& entry : entries_) {
        if (entry.status == "changed" && entry.asset_type == "pcp3_project" && !entry.staged_state_path.empty()) {
            changed.push_back(&entry);
        }
    }
    return changed;
}

const HotReloadStatusEntry* HotReloadStatus::changed_material_set() const noexcept {
    const auto found = std::find_if(entries_.begin(), entries_.end(), [](const auto& entry) {
        return entry.status == "changed" &&
               (entry.asset_type == "jitter_map" || entry.asset_type == "texture_graph") &&
               !entry.compiled_runtime_path.empty();
    });
    return found == entries_.end() ? nullptr : &*found;
}

const HotReloadStatusEntry* HotReloadStatus::changed_audio_profile() const noexcept {
    const auto found = std::find_if(entries_.begin(), entries_.end(), [](const auto& entry) {
        return entry.status == "changed" && entry.asset_type == "audio_interference_profile" &&
               !entry.compiled_runtime_path.empty();
    });
    return found == entries_.end() ? nullptr : &*found;
}

const HotReloadStatusEntry* HotReloadStatus::changed_font() const noexcept {
    const auto found = std::find_if(entries_.begin(), entries_.end(), [](const auto& entry) {
        return entry.status == "changed" && entry.asset_type == "signalcloud_font" &&
               !entry.staged_state_path.empty();
    });
    return found == entries_.end() ? nullptr : &*found;
}

}  // namespace signalcloud::assets
