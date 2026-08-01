#include "engine/materials/material_runtime.hpp"

#include "engine/data/udata.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <cstdlib>
#include <optional>
#include <string>
#include <system_error>

namespace signalcloud::materials {
namespace {

std::string unquote(std::string value) {
    if (value.size() >= 2U && value.front() == '"' && value.back() == '"') {
        value = value.substr(1U, value.size() - 2U);
    }
    return value;
}

std::optional<float> as_float(const std::optional<std::string>& raw) {
    if (!raw) return std::nullopt;
    char* end = nullptr;
    const float value = std::strtof(raw->c_str(), &end);
    if (end == raw->c_str() || *end != '\0' || !std::isfinite(value)) return std::nullopt;
    return value;
}

std::optional<std::uint32_t> as_u32(const std::optional<std::string>& raw) {
    if (!raw || raw->empty() || raw->front() == '-') return std::nullopt;
    std::uint32_t value = 0U;
    const auto result = std::from_chars(raw->data(), raw->data() + raw->size(), value);
    if (result.ec != std::errc{} || result.ptr != raw->data() + raw->size()) return std::nullopt;
    return value;
}

bool as_bool(const std::optional<std::string>& raw, bool fallback = false) {
    if (!raw) return fallback;
    if (*raw == "true") return true;
    if (*raw == "false") return false;
    return fallback;
}

math::Vec3 as_vec3(const std::optional<std::string>& raw, math::Vec3 fallback) {
    if (!raw || raw->size() < 5U || raw->front() != '[' || raw->back() != ']') return fallback;
    std::array<float, 3U> values{};
    std::size_t cursor = 1U;
    for (std::size_t index = 0U; index < values.size(); ++index) {
        const std::size_t end = index + 1U == values.size() ? raw->size() - 1U : raw->find(',', cursor);
        if (end == std::string::npos) return fallback;
        const std::string token = raw->substr(cursor, end - cursor);
        char* parsed_end = nullptr;
        const float value = std::strtof(token.c_str(), &parsed_end);
        if (parsed_end == token.c_str() || *parsed_end != '\0' || !std::isfinite(value)) return fallback;
        values[index] = value;
        cursor = end + 1U;
    }
    return {values[0], values[1], values[2]};
}

SurfaceKind parse_surface(const std::string& value) {
    if (value == "wall") return SurfaceKind::wall;
    if (value == "ceiling") return SurfaceKind::ceiling;
    return SurfaceKind::floor;
}

PatternMode parse_pattern_mode(const std::string& value) {
    if (value == "fiber_rows") return PatternMode::fiber_rows;
    if (value == "wallpaper_breakup") return PatternMode::wallpaper_breakup;
    if (value == "flat_tiles") return PatternMode::flat_tiles;
    return PatternMode::legacy;
}

float clamped(float value, float lo, float hi) { return std::clamp(value, lo, hi); }

}  // namespace

MaterialRuntime::MaterialRuntime(std::filesystem::path project_root,
                                 std::filesystem::path sidecar_path)
    : project_root_(std::move(project_root)), sidecar_path_(std::move(sidecar_path)) {}

bool MaterialRuntime::reload(std::string* error) {
    valid_ = false;
    materials_.clear();
    assignments_.clear();
    stats_ = {};
    try {
        const auto document = data::UDataDocument::load(sidecar_path_);
        if (document.has_errors()) {
            if (error) *error = "material runtime sidecar contains parse errors";
            return false;
        }
        const std::string schema = unquote(document.value("meta", "schema").value_or("\"\""));
        if (schema != "signalcloud_material_runtime_v1") {
            if (error) *error = "unsupported material runtime schema";
            return false;
        }
        stats_.source_graph = unquote(document.value("meta", "source_graph").value_or("\"\""));
        stats_.mode = unquote(document.value("meta", "mode").value_or("\"auto\""));
        stats_.material_count = as_u32(document.value("meta", "material_count")).value_or(0U);
        stats_.assignment_count = as_u32(document.value("meta", "assignment_count")).value_or(0U);
        stats_.warning_count = as_u32(document.value("meta", "warning_count")).value_or(0U);
        stats_.signature = unquote(document.value("meta", "signature").value_or("\"\""));
        stats_.selected_materials = as_u32(document.value("budget", "selected_materials")).value_or(0U);
        stats_.selected_point_budget = as_u32(document.value("budget", "selected_point_budget")).value_or(0U);
        stats_.max_point_budget = as_u32(document.value("budget", "max_point_budget")).value_or(0U);
        const std::size_t material_count = std::min<std::size_t>(stats_.material_count, 32U);
        for (std::size_t index = 0U; index < material_count; ++index) {
            const std::string section = "material." + std::to_string(index);
            MaterialDefinition material;
            material.id = unquote(document.value(section, "id").value_or("\"\""));
            material.name = unquote(document.value(section, "name").value_or("\"\""));
            material.character = unquote(document.value(section, "character").value_or("\"bumpy\""));
            material.definition_layer = unquote(document.value(section, "definition_layer").value_or("\"HD Texture\""));
            material.jG = clamped(as_float(document.value(section, "jG")).value_or(0.05F), 0.001F, 4.0F);
            material.jL = clamped(as_float(document.value(section, "jL")).value_or(0.02F), 0.0F, 2.0F);
            material.jC = clamped(as_float(document.value(section, "jC")).value_or(0.3F), 0.01F, 8.0F);
            material.jS = clamped(as_float(document.value(section, "jS")).value_or(0.8F), 0.02F, 16.0F);
            material.runtime_amplitude = clamped(as_float(document.value(section, "runtime_amplitude")).value_or(0.04F), 0.0F, 0.35F);
            material.seed = as_u32(document.value(section, "seed")).value_or(1U);
            material.source_color = as_vec3(document.value(section, "source_color"), material.source_color);
            material.accent_color = as_vec3(document.value(section, "accent_color"), material.accent_color);
            material.detail_color = as_vec3(document.value(section, "detail_color"), material.detail_color);
            material.variation = clamped(as_float(document.value(section, "variation")).value_or(0.06F), 0.0F, 0.35F);
            material.effective_opacity = clamped(as_float(document.value(section, "effective_opacity")).value_or(1.0F), 0.02F, 1.0F);
            material.definition_layer_count = std::min<std::uint32_t>(
                as_u32(document.value(section, "definition_layer_count")).value_or(1U),
                static_cast<std::uint32_t>(kDefinitionLayerCount));
            material.definition_opacity[static_cast<std::size_t>(DefinitionLayer::hd_light)] =
                clamped(as_float(document.value(section, "definition_hd_light")).value_or(0.0F), 0.0F, 1.0F);
            material.definition_opacity[static_cast<std::size_t>(DefinitionLayer::hd_texture)] =
                clamped(as_float(document.value(section, "definition_hd_texture")).value_or(0.28F), 0.0F, 1.0F);
            material.definition_opacity[static_cast<std::size_t>(DefinitionLayer::outer_light)] =
                clamped(as_float(document.value(section, "definition_outer_light")).value_or(0.0F), 0.0F, 1.0F);
            material.definition_opacity[static_cast<std::size_t>(DefinitionLayer::outer_texture)] =
                clamped(as_float(document.value(section, "definition_outer_texture")).value_or(0.0F), 0.0F, 1.0F);
            material.definition_opacity[static_cast<std::size_t>(DefinitionLayer::inner_texture)] =
                clamped(as_float(document.value(section, "definition_inner_texture")).value_or(0.0F), 0.0F, 1.0F);
            material.point_budget_cost = as_u32(document.value(section, "point_budget_cost")).value_or(0U);
            material.pattern_mode = parse_pattern_mode(unquote(document.value(section, "pattern_mode").value_or("\"legacy\"")));
            material.primary_spacing = clamped(as_float(document.value(section, "primary_spacing")).value_or(0.8F), 0.08F, 12.0F);
            material.secondary_spacing = clamped(as_float(document.value(section, "secondary_spacing")).value_or(1.2F), 0.08F, 12.0F);
            material.breakup_scale = clamped(as_float(document.value(section, "breakup_scale")).value_or(3.0F), 0.2F, 24.0F);
            material.breakup_strength = clamped(as_float(document.value(section, "breakup_strength")).value_or(0.0F), 0.0F, 1.0F);
            material.displacement_weight = clamped(as_float(document.value(section, "displacement_weight")).value_or(1.0F), 0.0F, 1.0F);
            material.color_weight = clamped(as_float(document.value(section, "color_weight")).value_or(0.68F), 0.0F, 1.0F);
            material.line_width = clamped(as_float(document.value(section, "line_width")).value_or(0.18F), 0.02F, 0.48F);
            material.exact_match = as_bool(document.value(section, "exact_match"));
            material.budget_active = as_bool(document.value(section, "budget_active"));
            if (material.id.empty()) continue;
            materials_.push_back(material);
        }
        const std::size_t assignment_count = std::min<std::size_t>(stats_.assignment_count, 64U);
        for (std::size_t index = 0U; index < assignment_count; ++index) {
            const std::string section = "assignment." + std::to_string(index);
            TextureAssignment assignment;
            assignment.id = unquote(document.value(section, "id").value_or("\"\""));
            assignment.zone = unquote(document.value(section, "zone").value_or("\"*\""));
            assignment.surface = parse_surface(unquote(document.value(section, "surface").value_or("\"floor\"")));
            assignment.material_index = as_u32(document.value(section, "material_index")).value_or(0U);
            assignment.priority = as_u32(document.value(section, "priority")).value_or(0U);
            assignment.seed = as_u32(document.value(section, "seed")).value_or(1U);
            assignment.locked = as_bool(document.value(section, "locked"));
            assignment.opacity = clamped(as_float(document.value(section, "opacity")).value_or(1.0F), 0.0F, 1.0F);
            if (assignment.material_index >= materials_.size()) continue;
            assignments_.push_back(assignment);
        }
        valid_ = !materials_.empty() && !assignments_.empty();
        if (!valid_ && error) *error = "material runtime contains no usable materials or assignments";
        return valid_;
    } catch (const std::exception& ex) {
        if (error) *error = ex.what();
        return false;
    }
}

MaterialFrame MaterialRuntime::evaluate(std::string_view active_zone) const noexcept {
    MaterialFrame frame;
    frame.max_point_budget = stats_.max_point_budget;
    frame.selected_point_budget = stats_.selected_point_budget;
    for (std::size_t surface_index = 0U; surface_index < frame.surfaces.size(); ++surface_index) {
        const auto surface = static_cast<SurfaceKind>(surface_index);
        const TextureAssignment* best = nullptr;
        for (const auto& assignment : assignments_) {
            if (assignment.surface != surface) continue;
            if (assignment.zone != "*" && assignment.zone != active_zone) continue;
            if (best == nullptr || (assignment.locked && !best->locked) ||
                (assignment.locked == best->locked && assignment.priority > best->priority) ||
                (assignment.locked == best->locked && assignment.priority == best->priority && assignment.id < best->id)) {
                best = &assignment;
            }
        }
        if (best == nullptr) continue;
        const auto& material = materials_[best->material_index];
        if (!material.budget_active) continue;
        auto& out = frame.surfaces[surface_index];
        out.enabled = true;
        out.source_color = material.source_color;
        out.accent_color = material.accent_color;
        out.detail_color = material.detail_color;
        out.jG = material.jG;
        out.jL = material.jL;
        out.jC = material.jC;
        out.jS = material.jS;
        out.jitter_amplitude = material.runtime_amplitude;
        out.variation = material.variation;
        out.opacity = clamped(material.effective_opacity * best->opacity, 0.02F, 1.0F);
        out.definition_opacity = material.definition_opacity;
        out.definition_layer_count = material.definition_layer_count;
        out.seed = material.seed ^ best->seed;
        out.point_budget_cost = material.point_budget_cost;
        out.pattern_mode = material.pattern_mode;
        out.primary_spacing = material.primary_spacing;
        out.secondary_spacing = material.secondary_spacing;
        out.breakup_scale = material.breakup_scale;
        out.breakup_strength = material.breakup_strength;
        out.displacement_weight = material.displacement_weight;
        out.color_weight = material.color_weight;
        out.line_width = material.line_width;
        out.exact_match = material.exact_match;
        out.locked = best->locked;
        ++frame.active_materials;
        frame.combined_opacity *= out.opacity;
    }
    frame.combined_opacity = clamped(frame.combined_opacity, 0.02F, 1.0F);
    return frame;
}

std::string_view surface_kind_name(SurfaceKind kind) noexcept {
    if (kind == SurfaceKind::wall) return "wall";
    if (kind == SurfaceKind::ceiling) return "ceiling";
    return "floor";
}

std::string_view pattern_mode_name(PatternMode mode) noexcept {
    if (mode == PatternMode::fiber_rows) return "fiber_rows";
    if (mode == PatternMode::wallpaper_breakup) return "wallpaper_breakup";
    if (mode == PatternMode::flat_tiles) return "flat_tiles";
    return "legacy";
}

std::string_view definition_layer_name(DefinitionLayer layer) noexcept {
    if (layer == DefinitionLayer::hd_light) return "HD Light";
    if (layer == DefinitionLayer::hd_texture) return "HD Texture";
    if (layer == DefinitionLayer::outer_light) return "Outer Light";
    if (layer == DefinitionLayer::outer_texture) return "Outer Texture";
    return "Inner Texture";
}

}  // namespace signalcloud::materials
