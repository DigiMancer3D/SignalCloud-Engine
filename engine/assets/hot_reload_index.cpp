#include "engine/assets/hot_reload_index.hpp"

#include "engine/data/udata.hpp"

#include <algorithm>
#include <cctype>
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

bool safe_relative(const std::filesystem::path& path) {
    if (path.empty() || path.is_absolute()) return false;
    return std::none_of(path.begin(), path.end(), [](const auto& part) { return part == ".."; });
}

}  // namespace

HotReloadIndex HotReloadIndex::load(const std::filesystem::path& project_root,
                                    const std::filesystem::path& index_path) {
    HotReloadIndex index;
    try {
        const auto root = std::filesystem::weakly_canonical(project_root);
        const auto document = signalcloud::data::UDataDocument::load(index_path);
        if (document.has_errors()) {
            index.errors_.push_back("hot-reload index contains UDATA errors");
            return index;
        }
        const std::string schema = unquote(document.value("index", "schema_name"));
        index.mode_ = unquote(document.value("index", "mode"));
        if (schema != "signalcloud.hot-reload-index") {
            index.errors_.push_back("unexpected hot-reload schema");
        }
        if (index.mode_ != "protected-authoring-only") {
            index.errors_.push_back("hot-reload index is not protected-authoring-only");
        }
        std::set<std::string> ids;
        for (const auto& entry : document.entries()) {
            if (!entry.section.starts_with("asset.") || entry.key != "asset_id") continue;
            HotReloadAsset asset;
            asset.asset_id = unquote(document.value(entry.section, "asset_id"));
            asset.relative_path = unquote(document.value(entry.section, "relative_path"));
            asset.sha256 = unquote(document.value(entry.section, "sha256"));
            asset.asset_type = unquote(document.value(entry.section, "asset_type"));
            if (asset.asset_id.empty() || !ids.insert(asset.asset_id).second) {
                index.errors_.push_back("duplicate or empty hot-reload asset_id");
                continue;
            }
            if (!safe_relative(asset.relative_path)) {
                index.errors_.push_back("unsafe hot-reload path for " + asset.asset_id);
                continue;
            }
            const auto resolved = std::filesystem::weakly_canonical(root / asset.relative_path);
            const auto relative = resolved.lexically_relative(root);
            const std::string relative_text = relative.generic_string();
            if (relative_text.empty() || relative_text == ".." || relative_text.starts_with("../")) {
                index.errors_.push_back("hot-reload path escapes project root for " + asset.asset_id);
                continue;
            }
            if (asset.sha256.size() != 64U) {
                index.errors_.push_back("invalid hot-reload hash for " + asset.asset_id);
                continue;
            }
            index.entries_.push_back(std::move(asset));
        }
    } catch (const std::exception& ex) {
        index.errors_.push_back(ex.what());
    }
    return index;
}

}  // namespace signalcloud::assets
