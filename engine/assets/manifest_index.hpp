#pragma once

#include <filesystem>
#include <string>
#include <vector>

namespace signalcloud::assets {

struct ManifestRecord {
    std::string asset_id;
    std::string asset_type;
    std::string family;
    std::string pack;
    std::filesystem::path relative_path;
    std::uintmax_t size_bytes{0};
    std::string sha256;
    bool enabled{true};
};

class ManifestIndex {
public:
    static ManifestIndex load_csv(const std::filesystem::path& path);
    [[nodiscard]] const std::vector<ManifestRecord>& records() const noexcept { return records_; }
    [[nodiscard]] std::vector<std::string> validate() const;

private:
    std::vector<ManifestRecord> records_;
};

}  // namespace signalcloud::assets
