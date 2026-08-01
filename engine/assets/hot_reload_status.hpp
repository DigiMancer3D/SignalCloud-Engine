#pragma once

#include <cstdint>
#include <filesystem>
#include <string>
#include <string_view>
#include <vector>

namespace signalcloud::assets {

struct HotReloadStatusEntry {
    std::string asset_id;
    std::filesystem::path relative_path;
    std::string asset_type;
    std::string indexed_sha256;
    std::string observed_sha256;
    std::string status;
    std::filesystem::path staged_state_path;
    std::filesystem::path compiled_runtime_path;
    std::string companion_sha256;
    std::uint64_t point_count{0};
};

class HotReloadStatus {
public:
    static HotReloadStatus load(const std::filesystem::path& project_root,
                                const std::filesystem::path& status_path);

    [[nodiscard]] bool valid() const noexcept { return errors_.empty(); }
    [[nodiscard]] std::uint64_t generated_unix() const noexcept { return generated_unix_; }
    [[nodiscard]] std::string_view transaction_id() const noexcept { return transaction_id_; }
    [[nodiscard]] std::size_t changed_count() const noexcept;
    [[nodiscard]] std::size_t changed_light_count() const noexcept;
    [[nodiscard]] std::size_t changed_scui_count() const noexcept;
    [[nodiscard]] std::size_t changed_pcp3_count() const noexcept;
    [[nodiscard]] std::size_t changed_material_count() const noexcept;
    [[nodiscard]] std::size_t changed_audio_count() const noexcept;
    [[nodiscard]] std::size_t changed_font_count() const noexcept;
    [[nodiscard]] const std::vector<HotReloadStatusEntry>& entries() const noexcept { return entries_; }
    [[nodiscard]] const std::vector<std::string>& errors() const noexcept { return errors_; }
    [[nodiscard]] const HotReloadStatusEntry* changed_for_path(std::string_view relative_path) const noexcept;
    [[nodiscard]] const HotReloadStatusEntry* changed_light_set() const noexcept;
    [[nodiscard]] std::vector<const HotReloadStatusEntry*> changed_pcp3_projects() const;
    [[nodiscard]] const HotReloadStatusEntry* changed_material_set() const noexcept;
    [[nodiscard]] const HotReloadStatusEntry* changed_audio_profile() const noexcept;
    [[nodiscard]] const HotReloadStatusEntry* changed_font() const noexcept;

private:
    std::vector<HotReloadStatusEntry> entries_;
    std::vector<std::string> errors_;
    std::uint64_t generated_unix_{0};
    std::string transaction_id_;
};

}  // namespace signalcloud::assets
