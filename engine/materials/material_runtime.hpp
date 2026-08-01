#pragma once

#include "engine/math/vec.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <string_view>
#include <vector>

namespace signalcloud::materials {

enum class SurfaceKind : std::uint8_t { floor = 0, wall = 1, ceiling = 2 };
enum class PatternMode : std::uint8_t { legacy = 0, fiber_rows = 1, wallpaper_breakup = 2, flat_tiles = 3 };
inline constexpr std::size_t kDefinitionLayerCount = 5U;
enum class DefinitionLayer : std::uint8_t {
    hd_light = 0, hd_texture = 1, outer_light = 2, outer_texture = 3, inner_texture = 4
};

struct MaterialDefinition {
    std::string id;
    std::string name;
    std::string character{"bumpy"};
    std::string definition_layer{"HD Texture"};
    std::array<float, kDefinitionLayerCount> definition_opacity{{0.0F, 0.28F, 0.0F, 0.0F, 0.0F}};
    std::uint32_t definition_layer_count{1U};
    float jG{0.05F};
    float jL{0.02F};
    float jC{0.3F};
    float jS{0.8F};
    float runtime_amplitude{0.04F};
    std::uint32_t seed{1U};
    math::Vec3 source_color{0.48F, 0.42F, 0.31F};
    math::Vec3 accent_color{0.68F, 0.58F, 0.40F};
    math::Vec3 detail_color{0.24F, 0.20F, 0.15F};
    float variation{0.06F};
    float effective_opacity{1.0F};
    std::uint32_t point_budget_cost{0U};
    PatternMode pattern_mode{PatternMode::legacy};
    float primary_spacing{0.8F};
    float secondary_spacing{1.2F};
    float breakup_scale{3.0F};
    float breakup_strength{0.0F};
    float displacement_weight{1.0F};
    float color_weight{0.68F};
    float line_width{0.18F};
    bool exact_match{false};
    bool budget_active{false};
};

struct TextureAssignment {
    std::string id;
    std::string zone{"*"};
    SurfaceKind surface{SurfaceKind::floor};
    std::size_t material_index{0U};
    std::uint32_t priority{0U};
    std::uint32_t seed{1U};
    float opacity{1.0F};
    bool locked{false};
};

struct SurfaceMaterialFrame {
    bool enabled{false};
    math::Vec3 source_color{1.0F, 1.0F, 1.0F};
    math::Vec3 accent_color{1.0F, 1.0F, 1.0F};
    math::Vec3 detail_color{1.0F, 1.0F, 1.0F};
    float jG{0.05F};
    float jL{0.02F};
    float jC{0.3F};
    float jS{0.8F};
    float jitter_amplitude{0.0F};
    float variation{0.0F};
    float opacity{1.0F};
    std::array<float, kDefinitionLayerCount> definition_opacity{{0.0F, 0.28F, 0.0F, 0.0F, 0.0F}};
    std::uint32_t definition_layer_count{1U};
    std::uint32_t seed{1U};
    std::uint32_t point_budget_cost{0U};
    PatternMode pattern_mode{PatternMode::legacy};
    float primary_spacing{0.8F};
    float secondary_spacing{1.2F};
    float breakup_scale{3.0F};
    float breakup_strength{0.0F};
    float displacement_weight{1.0F};
    float color_weight{0.68F};
    float line_width{0.18F};
    bool exact_match{false};
    bool locked{false};
};

struct MaterialFrame {
    std::array<SurfaceMaterialFrame, 3U> surfaces{};
    std::size_t active_materials{0U};
    std::uint32_t selected_point_budget{0U};
    std::uint32_t max_point_budget{0U};
    float combined_opacity{1.0F};
};

struct MaterialRuntimeStats {
    std::string source_graph;
    std::string mode{"auto"};
    std::size_t material_count{0U};
    std::size_t assignment_count{0U};
    std::size_t selected_materials{0U};
    std::uint32_t selected_point_budget{0U};
    std::uint32_t max_point_budget{0U};
    std::size_t warning_count{0U};
    std::string signature;
};

class MaterialRuntime {
public:
    MaterialRuntime() = default;
    MaterialRuntime(std::filesystem::path project_root, std::filesystem::path sidecar_path);

    bool reload(std::string* error = nullptr);
    [[nodiscard]] MaterialFrame evaluate(std::string_view active_zone) const noexcept;
    [[nodiscard]] const std::vector<MaterialDefinition>& materials() const noexcept { return materials_; }
    [[nodiscard]] const std::vector<TextureAssignment>& assignments() const noexcept { return assignments_; }
    [[nodiscard]] const MaterialRuntimeStats& stats() const noexcept { return stats_; }
    [[nodiscard]] bool valid() const noexcept { return valid_; }

private:
    std::filesystem::path project_root_;
    std::filesystem::path sidecar_path_;
    std::vector<MaterialDefinition> materials_;
    std::vector<TextureAssignment> assignments_;
    MaterialRuntimeStats stats_{};
    bool valid_{false};
};

[[nodiscard]] std::string_view surface_kind_name(SurfaceKind kind) noexcept;
[[nodiscard]] std::string_view pattern_mode_name(PatternMode mode) noexcept;
[[nodiscard]] std::string_view definition_layer_name(DefinitionLayer layer) noexcept;

}  // namespace signalcloud::materials
