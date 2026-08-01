#pragma once

#include "engine/math/vec.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace signalcloud::world { class LiminalLevel; }

namespace signalcloud::lighting {

inline constexpr std::size_t kMaxEvaluatedLocalLights = 4U;

enum class LightScope : std::uint8_t {
    local,
    area,
    room,
    global,
};

struct LightDefinition {
    std::string id;
    std::string name;
    math::Vec3 position{};
    math::Vec3 target{};
    math::Vec3 color{1.0F, 1.0F, 1.0F};
    float illuminosity_percent{0.0F};
    float aperture_distance{2.5F};
    float radius{1.0F};
    float cone_or_degree_burst{80.0F};
    LightScope scope{LightScope::local};
    std::string zone;
    bool enabled{false};
    bool dynamic{false};
    std::uint32_t bounce_count_limit{0U};
    float bounce_cost{0.34F};
    std::string shadow_policy{"none"};
    std::string day_night_binding{"none"};
    std::uint32_t point_budget_cost{0U};
    std::uint32_t budget_priority{100U};
    std::uint32_t seed{0U};
    bool budget_active{false};
};

struct DayNightDefinition {
    math::Vec3 day_color{1.0F, 0.95F, 0.85F};
    float day_illuminosity_percent{95.0F};
    math::Vec3 night_color{0.15F, 0.18F, 0.35F};
    float night_illuminosity_percent{18.0F};
    float day_to_night_seconds{45.0F};
    float night_to_day_seconds{60.0F};
    float time_of_day{0.35F};
    bool playing{false};
    bool paused{false};
    bool protected_global{true};
};

struct LightBudgetDefinition {
    std::uint32_t max_active_lights{8U};
    std::uint32_t max_point_budget{4096U};
    std::uint32_t rays_per_light{8U};
    std::uint32_t max_diagnostic_rays{32U};
    float stress_scale{1.0F};
};

struct EvaluatedLightContribution {
    math::Vec3 position{};
    math::Vec3 color{1.0F, 1.0F, 1.0F};
    float radius{1.0F};
    float strength{0.0F};
    std::size_t source_index{0U};
};

struct IlluminosityFrame {
    // Legacy strongest-local fields remain for downstream telemetry compatibility.
    bool local_enabled{false};
    math::Vec3 local_position{};
    math::Vec3 local_color{1.0F, 1.0F, 1.0F};
    float local_radius{1.0F};
    float local_strength{0.0F};

    std::array<EvaluatedLightContribution, kMaxEvaluatedLocalLights> local_lights{};
    std::size_t local_light_count{0U};
    std::size_t contributing_lights{0U};
    std::size_t active_lights{0U};
    std::size_t budget_limited_lights{0U};

    math::Vec3 global_color{1.0F, 1.0F, 1.0F};
    float global_strength{0.0F};
    float point_size_boost{0.0F};
    float visibility_floor{0.30F};
    std::uint32_t point_budget_cost{0U};
    std::uint32_t selected_point_budget_cost{0U};
};


struct SurfaceProbeDiagnostic {
    math::Vec3 sample_position{};
    math::Vec3 effective_color{1.0F, 1.0F, 1.0F};
    float effective_illuminosity_percent{0.0F};
    float visibility{0.0F};
    float point_size_boost{0.0F};
    std::size_t contributing_lights{0U};
    std::string quality_band{"DARKNESS"};
};

struct SignalRayDiagnostic {
    math::Vec3 origin{};
    math::Vec3 end{};
    float travelled_distance{0.0F};
    float remaining_illuminosity{0.0F};
    std::uint32_t bounce_count{0U};
    bool hit_surface{false};
    std::size_t light_index{0U};
    std::size_t ray_index{0U};
};

struct IlluminosityRuntimeStats {
    std::string source_document;
    std::size_t configured_lights{0U};
    std::size_t enabled_lights{0U};
    std::size_t budget_active_lights{0U};
    std::size_t budget_limited_lights{0U};
    std::size_t warning_count{0U};
    std::uint32_t point_budget_cost{0U};
    std::uint32_t selected_point_budget_cost{0U};
    std::uint32_t effective_max_point_budget{0U};
    bool used_fallback{false};
    std::uint64_t deterministic_signature{0U};
};

class IlluminosityRuntime {
public:
    IlluminosityRuntime() = default;
    IlluminosityRuntime(std::filesystem::path project_root,
                        std::filesystem::path runtime_sidecar);

    bool reload(std::string* error = nullptr);
    void update(float dt_seconds) noexcept;
    void set_time_of_day(float value) noexcept;
    void play_day_night() noexcept;
    void pause_day_night(bool paused = true) noexcept;
    void stop_day_night(float reset_time = 0.35F) noexcept;
    void set_budget_scale(float value) noexcept;
    void apply_authoring_override(std::string_view scope,
                                  float illuminosity_percent,
                                  float radius,
                                  float day_illuminosity_percent,
                                  float night_illuminosity_percent,
                                  float time_of_day) noexcept;

    [[nodiscard]] IlluminosityFrame evaluate(math::Vec3 viewer_position,
                                             std::string_view active_zone) const noexcept;
    [[nodiscard]] SurfaceProbeDiagnostic probe_surface(
        math::Vec3 sample_position, std::string_view active_zone) const noexcept;
    [[nodiscard]] std::vector<SignalRayDiagnostic> diagnostic_rays(
        const world::LiminalLevel& level, std::size_t light_index = 0U) const;
    [[nodiscard]] std::vector<SignalRayDiagnostic> diagnostic_rays_all(
        const world::LiminalLevel& level) const;

    [[nodiscard]] bool valid() const noexcept { return valid_; }
    [[nodiscard]] const std::vector<LightDefinition>& lights() const noexcept { return lights_; }
    [[nodiscard]] const DayNightDefinition& day_night() const noexcept { return day_night_; }
    [[nodiscard]] const LightBudgetDefinition& budget() const noexcept { return budget_; }
    [[nodiscard]] const IlluminosityRuntimeStats& stats() const noexcept { return stats_; }
    [[nodiscard]] const std::vector<std::string>& warnings() const noexcept { return warnings_; }
    [[nodiscard]] const std::filesystem::path& sidecar_path() const noexcept { return sidecar_path_; }

private:
    void rebuild_budget_selection() noexcept;
    [[nodiscard]] std::vector<SignalRayDiagnostic> diagnostic_rays_bounded(
        const world::LiminalLevel& level, std::size_t light_index,
        std::size_t ray_limit) const;

    std::filesystem::path project_root_;
    std::filesystem::path sidecar_path_;
    std::vector<LightDefinition> lights_;
    DayNightDefinition day_night_{};
    LightBudgetDefinition budget_{};
    IlluminosityRuntimeStats stats_{};
    std::vector<std::string> warnings_;
    float runtime_budget_scale_{1.0F};
    bool valid_{false};
};

[[nodiscard]] std::string_view light_scope_name(LightScope scope) noexcept;
[[nodiscard]] std::optional<LightScope> parse_light_scope(std::string_view value) noexcept;

}  // namespace signalcloud::lighting
