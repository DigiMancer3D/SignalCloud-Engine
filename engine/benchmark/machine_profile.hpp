#pragma once

#include "engine/data/udata.hpp"
#include "engine/render/adaptive_budget.hpp"

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <string_view>

namespace signalcloud::benchmark {

inline constexpr std::string_view kMachineProfileSchema{"signalcloud_machine_profile"};
inline constexpr std::uint32_t kMachineProfileSchemaMajor{1U};
inline constexpr std::string_view kMachineProfileRuleset{"signalcloud-alpha-a9-ruleset-1"};

struct MachineProfileContext {
    std::string vendor;
    std::string renderer;
    std::string version;
    std::string video_driver;
    int gl_major{0};
    int gl_minor{0};
    int width{1280};
    int height{720};
    std::string content_hash;
};

struct MachineProfileRecommendations {
    std::uint32_t environment_points{500'000U};
    std::uint32_t combined_point_budget{4'000'000U};
    std::uint32_t protected_fallback_points{100'000U};
    std::uint32_t submitted_soft_cap{1'300'000U};
    int full_rate_entities{1};
    int reduced_rate_entities{2};
    std::uint32_t active_lights{4U};
    std::uint32_t material_layers{3U};
    std::uint32_t sound_ripples{3U};
    std::uint32_t animated_actors{2U};
    std::uint32_t playbook_evaluations{8U};
    std::uint32_t tupd_test_objects{1U};
    std::uint32_t scui_panels{1U};
};

struct MachineProfileValidation {
    bool completed{false};
    bool route_pass{false};
    bool frame_pacing_pass{false};
    bool memory_guard_pass{false};
    bool content_hash_pass{false};
    std::uint32_t passed_stages{0U};
    std::uint32_t failed_stages{0U};
};

struct MachineProfile {
    data::UDataDocument document;
    std::string status{"conservative"};
    std::string source_kind{"capability-fallback"};
    std::string run_class{"first-run"};
    std::string ruleset_id{std::string(kMachineProfileRuleset)};
    std::string fingerprint;
    std::string content_hash;
    std::string gpu_class{"unknown"};
    int resolution_width{1280};
    int resolution_height{720};
    int target_fps{60};
    std::uint32_t burst_environment_points{0U};
    std::uint32_t sustainable_environment_points{0U};
    int burst_entities{0};
    int sustainable_entities{0};
    MachineProfileRecommendations recommended{};
    MachineProfileValidation validation{};
};

struct MachineProfileLoadResult {
    MachineProfile profile{};
    bool present{false};
    bool valid{false};
    bool stale{false};
    bool used_previous_known_good{false};
    std::string reason;
};

struct MachineProfilePaths {
    std::filesystem::path directory;
    std::filesystem::path active;
    std::filesystem::path candidate;
    std::filesystem::path previous_known_good;
    std::filesystem::path promotion_receipt;
};

struct MachineProfileTargetHint {
    int width{1280};
    int height{720};
    int target_fps{60};
    bool from_active_profile{false};
};

[[nodiscard]] MachineProfilePaths machine_profile_paths(const std::filesystem::path& project_root);
[[nodiscard]] MachineProfileTargetHint read_active_profile_target_hint(
    const std::filesystem::path& project_root, int fallback_width = 1280,
    int fallback_height = 720, int fallback_target_fps = 60);
[[nodiscard]] std::string privacy_safe_hash(std::string_view value);
[[nodiscard]] std::string hash_file_privacy_safe(const std::filesystem::path& path);
[[nodiscard]] std::string hash_machine_profile_content_manifest(const std::filesystem::path& path);
[[nodiscard]] std::string classify_gpu(std::string_view vendor, std::string_view renderer);
[[nodiscard]] std::string make_machine_fingerprint(const MachineProfileContext& context,
                                                   std::string_view ruleset_id = kMachineProfileRuleset);
[[nodiscard]] MachineProfile make_conservative_profile(
    const MachineProfileContext& context,
    const render::AdaptivePointBudget& capability_budget,
    int target_fps = 60);
[[nodiscard]] MachineProfileLoadResult load_machine_profile(
    const std::filesystem::path& path,
    const MachineProfileContext& context,
    bool require_active_status = false);
[[nodiscard]] MachineProfileLoadResult load_active_or_conservative(
    const std::filesystem::path& project_root,
    const MachineProfileContext& context,
    const render::AdaptivePointBudget& capability_budget,
    int target_fps = 60);
[[nodiscard]] bool validate_profile_candidate(const MachineProfile& profile,
                                              const MachineProfileContext& context,
                                              std::string* reason = nullptr);
bool save_machine_profile_atomic(const MachineProfile& profile,
                                 const std::filesystem::path& path,
                                 std::string* error = nullptr);
bool promote_candidate_atomic(const std::filesystem::path& project_root,
                              const MachineProfileContext& context,
                              std::string* error = nullptr);

}  // namespace signalcloud::benchmark
