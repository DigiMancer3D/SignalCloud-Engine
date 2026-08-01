#include "engine/benchmark/workload_ramp.hpp"

#include "engine/data/udata.hpp"

#include <algorithm>
#include <charconv>
#include <set>
#include <string_view>

namespace signalcloud::benchmark {
namespace {

std::uint64_t parse_u64_or(std::string_view text, std::uint64_t fallback) {
    std::uint64_t value = 0;
    const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
    return result.ec == std::errc{} ? value : fallback;
}

std::string unquote(std::string value) {
    if (value.size() >= 2U && value.front() == '"' && value.back() == '"') {
        return value.substr(1U, value.size() - 2U);
    }
    return value;
}

std::vector<std::uint32_t> three_step_levels(std::uint64_t maximum) {
    const std::uint32_t capped = static_cast<std::uint32_t>(
        std::clamp<std::uint64_t>(maximum, 1ULL, 128ULL));
    std::set<std::uint32_t> levels{1U, std::max(1U, (capped + 1U) / 2U), capped};
    return {levels.begin(), levels.end()};
}

void append_axis(std::vector<WorkloadRampPoint>& out, WorkloadAxis axis,
                 std::uint64_t maximum, std::string_view title) {
    const auto levels = three_step_levels(maximum);
    for (std::size_t index = 0; index < levels.size(); ++index) {
        WorkloadRampPoint point;
        point.axis = axis;
        point.level = levels[index];
        point.step = static_cast<std::uint32_t>(index + 1U);
        point.step_count = static_cast<std::uint32_t>(levels.size());
        point.label = std::string(title) + " " + std::to_string(point.level);
        out.push_back(std::move(point));
    }
}

std::uint64_t channel_or(const WorkloadRegistrySnapshot& registry,
                         std::string_view name, std::uint64_t fallback) {
    const auto match = registry.feature_channels.find(std::string(name));
    return match == registry.feature_channels.end() ? fallback : match->second;
}

}  // namespace

WorkloadRegistrySnapshot load_workload_registry(const std::filesystem::path& path) {
    WorkloadRegistrySnapshot result;
    try {
        const auto document = data::UDataDocument::load(path);
        if (document.has_errors()) return result;
        if (const auto value = document.value("header", "enabled_asset_count")) {
            result.enabled_asset_count = parse_u64_or(*value, 0U);
        }
        if (const auto value = document.value("header", "registry_sha256")) {
            result.registry_sha256 = unquote(*value);
        }
        for (const auto& entry : document.entries()) {
            if (entry.section == "feature_channels") {
                result.feature_channels[entry.key] = parse_u64_or(entry.raw_json, 0U);
            }
        }
        result.valid = !result.feature_channels.empty() && !result.registry_sha256.empty();
    } catch (...) {
        result.valid = false;
    }
    return result;
}

std::vector<WorkloadRampPoint> build_workload_ramps(const WorkloadRegistrySnapshot& registry) {
    std::vector<WorkloadRampPoint> result;
    append_axis(result, WorkloadAxis::lights,
                std::max<std::uint64_t>(4U, channel_or(registry, "lights", 4U)), "Authored lights");
    append_axis(result, WorkloadAxis::material_layers,
                std::max<std::uint64_t>(3U, channel_or(registry, "materials", 3U)), "Material layers");
    append_axis(result, WorkloadAxis::sound_ripples,
                std::max<std::uint64_t>(3U, channel_or(registry, "sound_ripples", 3U)), "Sound ripples");
    append_axis(result, WorkloadAxis::animated_actors,
                std::max<std::uint64_t>(8U, channel_or(registry, "content_enemy", 2U) * 4U), "Animated actors");
    append_axis(result, WorkloadAxis::playbook_evaluations,
                std::max<std::uint64_t>(12U, channel_or(registry, "playbook_evaluations", 4U) * 4U), "Playbook evaluations");
    append_axis(result, WorkloadAxis::tupd_test_objects,
                std::clamp<std::uint64_t>(channel_or(registry, "tupd_test_objects", 8U), 8U, 64U), "Tupd test objects");
    append_axis(result, WorkloadAxis::scui_panels,
                std::max<std::uint64_t>(3U, channel_or(registry, "scui_panels", 3U)), "SCUI panels");
    return result;
}

const char* workload_axis_name(WorkloadAxis axis) noexcept {
    switch (axis) {
        case WorkloadAxis::lights: return "lights";
        case WorkloadAxis::material_layers: return "material_layers";
        case WorkloadAxis::sound_ripples: return "sound_ripples";
        case WorkloadAxis::animated_actors: return "animated_actors";
        case WorkloadAxis::playbook_evaluations: return "playbook_evaluations";
        case WorkloadAxis::tupd_test_objects: return "tupd_test_objects";
        case WorkloadAxis::scui_panels: return "scui_panels";
        case WorkloadAxis::none: return "none";
    }
    return "none";
}

}  // namespace signalcloud::benchmark
