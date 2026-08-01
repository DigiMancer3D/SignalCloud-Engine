#pragma once

#include <filesystem>
#include <string>
#include <vector>

namespace signalcloud::assets {

struct HotReloadAsset {
    std::string asset_id;
    std::filesystem::path relative_path;
    std::string sha256;
    std::string asset_type;
};

class HotReloadIndex {
public:
    static HotReloadIndex load(const std::filesystem::path& project_root,
                               const std::filesystem::path& index_path);

    [[nodiscard]] bool valid() const noexcept { return errors_.empty(); }
    [[nodiscard]] const std::vector<HotReloadAsset>& entries() const noexcept { return entries_; }
    [[nodiscard]] const std::vector<std::string>& errors() const noexcept { return errors_; }
    [[nodiscard]] std::string mode() const noexcept { return mode_; }

private:
    std::vector<HotReloadAsset> entries_;
    std::vector<std::string> errors_;
    std::string mode_;
};

}  // namespace signalcloud::assets
