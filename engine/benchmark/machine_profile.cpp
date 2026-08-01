#include "engine/benchmark/machine_profile.hpp"

#include "engine/render/system_point_budget.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <cctype>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <system_error>
#include <vector>

namespace signalcloud::benchmark {
namespace {

std::string trim(std::string_view value) {
    std::size_t first = 0U;
    while (first < value.size() && std::isspace(static_cast<unsigned char>(value[first]))) ++first;
    std::size_t last = value.size();
    while (last > first && std::isspace(static_cast<unsigned char>(value[last - 1U]))) --last;
    return std::string(value.substr(first, last - first));
}

std::string lower(std::string_view value) {
    std::string result(value);
    std::transform(result.begin(), result.end(), result.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return result;
}

bool contains(std::string_view value, std::string_view token) {
    return value.find(token) != std::string_view::npos;
}

std::string unwrap_value(std::string_view raw) {
    std::string compact = trim(raw);
    if (compact.starts_with("{\"value\":")) {
        compact = trim(std::string_view(compact).substr(9U));
        if (!compact.empty() && compact.back() == '}') compact.pop_back();
        compact = trim(compact);
    }
    return compact;
}

std::optional<std::string> parse_string(std::string_view raw) {
    const std::string compact = unwrap_value(raw);
    if (compact.size() < 2U || compact.front() != '"' || compact.back() != '"') return std::nullopt;
    std::string result;
    result.reserve(compact.size() - 2U);
    bool escaped = false;
    for (std::size_t i = 1U; i + 1U < compact.size(); ++i) {
        const char c = compact[i];
        if (escaped) {
            switch (c) {
                case 'n': result.push_back('\n'); break;
                case 'r': result.push_back('\r'); break;
                case 't': result.push_back('\t'); break;
                case '\\': result.push_back('\\'); break;
                case '"': result.push_back('"'); break;
                default: result.push_back(c); break;
            }
            escaped = false;
        } else if (c == '\\') {
            escaped = true;
        } else {
            result.push_back(c);
        }
    }
    return result;
}

std::optional<std::uint64_t> parse_u64(std::string_view raw) {
    const std::string compact = unwrap_value(raw);
    std::uint64_t value = 0U;
    const auto result = std::from_chars(compact.data(), compact.data() + compact.size(), value);
    if (result.ec != std::errc{} || result.ptr != compact.data() + compact.size()) return std::nullopt;
    return value;
}

std::optional<std::int64_t> parse_i64(std::string_view raw) {
    const std::string compact = unwrap_value(raw);
    std::int64_t value = 0;
    const auto result = std::from_chars(compact.data(), compact.data() + compact.size(), value);
    if (result.ec != std::errc{} || result.ptr != compact.data() + compact.size()) return std::nullopt;
    return value;
}

std::optional<bool> parse_bool(std::string_view raw) {
    const std::string compact = unwrap_value(raw);
    if (compact == "true") return true;
    if (compact == "false") return false;
    return std::nullopt;
}

std::string json_string(std::string_view value) {
    std::ostringstream output;
    output << '"';
    for (const char c : value) {
        switch (c) {
            case '\\': output << "\\\\"; break;
            case '"': output << "\\\""; break;
            case '\n': output << "\\n"; break;
            case '\r': output << "\\r"; break;
            case '\t': output << "\\t"; break;
            default: output << c; break;
        }
    }
    output << '"';
    return output.str();
}

std::string read_string(const data::UDataDocument& document, std::string_view section,
                        std::string_view key, std::string fallback = {}) {
    if (const auto raw = document.value(section, key)) {
        if (const auto value = parse_string(*raw)) return *value;
    }
    return fallback;
}

std::uint32_t read_u32(const data::UDataDocument& document, std::string_view section,
                       std::string_view key, std::uint32_t fallback = 0U) {
    if (const auto raw = document.value(section, key)) {
        if (const auto value = parse_u64(*raw)) {
            return static_cast<std::uint32_t>(std::min<std::uint64_t>(*value, std::numeric_limits<std::uint32_t>::max()));
        }
    }
    return fallback;
}

int read_int(const data::UDataDocument& document, std::string_view section,
             std::string_view key, int fallback = 0) {
    if (const auto raw = document.value(section, key)) {
        if (const auto value = parse_i64(*raw)) {
            return static_cast<int>(std::clamp<std::int64_t>(*value, std::numeric_limits<int>::min(),
                                                            std::numeric_limits<int>::max()));
        }
    }
    return fallback;
}

bool read_bool(const data::UDataDocument& document, std::string_view section,
               std::string_view key, bool fallback = false) {
    if (const auto raw = document.value(section, key)) {
        if (const auto value = parse_bool(*raw)) return *value;
    }
    return fallback;
}

void write_known_fields(data::UDataDocument& document, const MachineProfile& profile) {
    document.set("header", "schema_name", json_string(kMachineProfileSchema));
    document.set("header", "schema_major", std::to_string(kMachineProfileSchemaMajor));
    document.set("header", "ruleset_id", json_string(profile.ruleset_id));
    document.set("header", "status", json_string(profile.status));
    document.set("header", "source_kind", json_string(profile.source_kind));
    document.set("header", "run_class", json_string(profile.run_class));

    document.set("fingerprint", "privacy_hash", json_string(profile.fingerprint));
    document.set("fingerprint", "content_hash", json_string(profile.content_hash));
    document.set("fingerprint", "gpu_class", json_string(profile.gpu_class));
    document.set("fingerprint", "resolution_width", std::to_string(profile.resolution_width));
    document.set("fingerprint", "resolution_height", std::to_string(profile.resolution_height));
    document.set("fingerprint", "target_fps", std::to_string(profile.target_fps));

    document.set("measured", "burst_environment_points", std::to_string(profile.burst_environment_points));
    document.set("measured", "sustainable_environment_points", std::to_string(profile.sustainable_environment_points));
    document.set("measured", "burst_entities", std::to_string(profile.burst_entities));
    document.set("measured", "sustainable_entities", std::to_string(profile.sustainable_entities));

    const auto& recommended = profile.recommended;
    document.set("recommended", "environment_points", std::to_string(recommended.environment_points));
    document.set("recommended", "combined_point_budget", std::to_string(recommended.combined_point_budget));
    document.set("recommended", "protected_fallback_points", std::to_string(recommended.protected_fallback_points));
    document.set("recommended", "submitted_soft_cap", std::to_string(recommended.submitted_soft_cap));
    document.set("recommended", "full_rate_entities", std::to_string(recommended.full_rate_entities));
    document.set("recommended", "reduced_rate_entities", std::to_string(recommended.reduced_rate_entities));
    document.set("recommended", "active_lights", std::to_string(recommended.active_lights));
    document.set("recommended", "material_layers", std::to_string(recommended.material_layers));
    document.set("recommended", "sound_ripples", std::to_string(recommended.sound_ripples));
    document.set("recommended", "animated_actors", std::to_string(recommended.animated_actors));
    document.set("recommended", "playbook_evaluations", std::to_string(recommended.playbook_evaluations));
    document.set("recommended", "tupd_test_objects", std::to_string(recommended.tupd_test_objects));
    document.set("recommended", "scui_panels", std::to_string(recommended.scui_panels));

    const auto& validation = profile.validation;
    document.set("validation", "completed", validation.completed ? "true" : "false");
    document.set("validation", "route_pass", validation.route_pass ? "true" : "false");
    document.set("validation", "frame_pacing_pass", validation.frame_pacing_pass ? "true" : "false");
    document.set("validation", "memory_guard_pass", validation.memory_guard_pass ? "true" : "false");
    document.set("validation", "content_hash_pass", validation.content_hash_pass ? "true" : "false");
    document.set("validation", "passed_stages", std::to_string(validation.passed_stages));
    document.set("validation", "failed_stages", std::to_string(validation.failed_stages));

    document.set("privacy", "contains_private_paths", "false");
    document.set("privacy", "contains_hostname", "false");
    document.set("privacy", "contains_serial", "false");
    document.set("privacy", "identity_policy", json_string("hashed-capability-only"));
}

MachineProfile read_profile(const data::UDataDocument& document) {
    MachineProfile profile;
    profile.document = document;
    profile.status = read_string(document, "header", "status", "invalid");
    profile.source_kind = read_string(document, "header", "source_kind", "unknown");
    profile.run_class = read_string(document, "header", "run_class", "unknown");
    profile.ruleset_id = read_string(document, "header", "ruleset_id", "");
    profile.fingerprint = read_string(document, "fingerprint", "privacy_hash", "");
    profile.content_hash = read_string(document, "fingerprint", "content_hash", "");
    profile.gpu_class = read_string(document, "fingerprint", "gpu_class", "unknown");
    profile.resolution_width = read_int(document, "fingerprint", "resolution_width", 0);
    profile.resolution_height = read_int(document, "fingerprint", "resolution_height", 0);
    profile.target_fps = read_int(document, "fingerprint", "target_fps", 60);
    profile.burst_environment_points = read_u32(document, "measured", "burst_environment_points");
    profile.sustainable_environment_points = read_u32(document, "measured", "sustainable_environment_points");
    profile.burst_entities = read_int(document, "measured", "burst_entities");
    profile.sustainable_entities = read_int(document, "measured", "sustainable_entities");

    auto& recommended = profile.recommended;
    recommended.environment_points = read_u32(document, "recommended", "environment_points", 500'000U);
    recommended.combined_point_budget = read_u32(document, "recommended", "combined_point_budget", 4'000'000U);
    recommended.protected_fallback_points = read_u32(document, "recommended", "protected_fallback_points", 100'000U);
    recommended.submitted_soft_cap = read_u32(document, "recommended", "submitted_soft_cap", 1'300'000U);
    recommended.full_rate_entities = read_int(document, "recommended", "full_rate_entities", 1);
    recommended.reduced_rate_entities = read_int(document, "recommended", "reduced_rate_entities", 2);
    recommended.active_lights = read_u32(document, "recommended", "active_lights", 4U);
    recommended.material_layers = read_u32(document, "recommended", "material_layers", 3U);
    recommended.sound_ripples = read_u32(document, "recommended", "sound_ripples", 3U);
    recommended.animated_actors = read_u32(document, "recommended", "animated_actors", 2U);
    recommended.playbook_evaluations = read_u32(document, "recommended", "playbook_evaluations", 8U);
    recommended.tupd_test_objects = read_u32(document, "recommended", "tupd_test_objects", 1U);
    recommended.scui_panels = read_u32(document, "recommended", "scui_panels", 1U);

    auto& validation = profile.validation;
    validation.completed = read_bool(document, "validation", "completed");
    validation.route_pass = read_bool(document, "validation", "route_pass");
    validation.frame_pacing_pass = read_bool(document, "validation", "frame_pacing_pass");
    validation.memory_guard_pass = read_bool(document, "validation", "memory_guard_pass");
    validation.content_hash_pass = read_bool(document, "validation", "content_hash_pass");
    validation.passed_stages = read_u32(document, "validation", "passed_stages");
    validation.failed_stages = read_u32(document, "validation", "failed_stages");
    return profile;
}

bool supported_environment_points(std::uint32_t points) {
    static constexpr std::array<std::uint32_t, 7U> tiers{{
        100'000U, 500'000U, 1'000'000U, 2'000'000U, 3'000'000U,
        4'000'000U, 8'000'000U,
    }};
    return std::find(tiers.begin(), tiers.end(), points) != tiers.end();
}

std::uint32_t combined_budget_for(std::uint32_t environment_points) {
    if (environment_points >= 8'000'000U) return 20'000'000U;
    if (environment_points >= 6'000'000U) return 16'000'000U;
    if (environment_points >= 4'000'000U) return 12'000'000U;
    if (environment_points >= 2'000'000U) return 8'000'000U;
    return 4'000'000U;
}

std::uint32_t fallback_for(std::uint32_t environment_points) {
    if (environment_points >= 8'000'000U) return 4'000'000U;
    if (environment_points >= 4'000'000U) return 2'000'000U;
    if (environment_points >= 2'000'000U) return 1'000'000U;
    if (environment_points >= 500'000U) return 100'000U;
    return 100'000U;
}

bool copy_atomic(const std::filesystem::path& source, const std::filesystem::path& destination,
                 std::string* error) {
    try {
        std::filesystem::create_directories(destination.parent_path());
        const std::filesystem::path temporary = destination.string() + ".tmp";
        std::error_code ec;
        std::filesystem::copy_file(source, temporary, std::filesystem::copy_options::overwrite_existing, ec);
        if (ec) throw std::runtime_error("Unable to copy profile: " + ec.message());
        std::filesystem::rename(temporary, destination, ec);
        if (ec) {
            std::filesystem::remove(destination, ec);
            ec.clear();
            std::filesystem::rename(temporary, destination, ec);
        }
        if (ec) throw std::runtime_error("Unable to promote profile copy: " + ec.message());
        return true;
    } catch (const std::exception& exception) {
        if (error != nullptr) *error = exception.what();
        return false;
    }
}

}  // namespace

MachineProfilePaths machine_profile_paths(const std::filesystem::path& project_root) {
    const auto directory = project_root / "user_data/machine_profiles";
    return {directory, directory / "active.udata", directory / "candidate.udata",
            directory / "previous_known_good.udata", directory / "promotion_receipt.udata"};
}

MachineProfileTargetHint read_active_profile_target_hint(
    const std::filesystem::path& project_root, int fallback_width,
    int fallback_height, int fallback_target_fps) {
    MachineProfileTargetHint hint;
    hint.width = std::clamp(fallback_width, 640, 7680);
    hint.height = std::clamp(fallback_height, 360, 4320);
    hint.target_fps = std::clamp(fallback_target_fps, 30, 240);

    const auto active = machine_profile_paths(project_root).active;
    if (!std::filesystem::is_regular_file(active)) return hint;
    try {
        const data::UDataDocument document = data::UDataDocument::load(active);
        if (document.has_errors()) return hint;
        const std::string schema = read_string(document, "header", "schema_name", "");
        const std::uint32_t major = read_u32(document, "header", "schema_major", 0U);
        const std::string ruleset = read_string(document, "header", "ruleset_id", "");
        const std::string status = read_string(document, "header", "status", "");
        if (schema != kMachineProfileSchema || major != kMachineProfileSchemaMajor ||
            ruleset != kMachineProfileRuleset || status != "active") {
            return hint;
        }
        const int width = static_cast<int>(read_u32(document, "fingerprint", "resolution_width", 0U));
        const int height = static_cast<int>(read_u32(document, "fingerprint", "resolution_height", 0U));
        const int target_fps = static_cast<int>(read_u32(document, "fingerprint", "target_fps", 0U));
        if (width < 640 || width > 7680 || height < 360 || height > 4320 ||
            target_fps < 30 || target_fps > 240) {
            return hint;
        }
        hint.width = width;
        hint.height = height;
        hint.target_fps = target_fps;
        hint.from_active_profile = true;
    } catch (...) {
        return hint;
    }
    return hint;
}

std::string privacy_safe_hash(std::string_view value) {
    std::uint64_t hash = 1469598103934665603ULL;
    for (const unsigned char c : value) {
        hash ^= static_cast<std::uint64_t>(c);
        hash *= 1099511628211ULL;
    }
    std::ostringstream output;
    output << std::hex << std::setw(16) << std::setfill('0') << hash;
    return output.str();
}

std::string hash_file_privacy_safe(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) return privacy_safe_hash("missing");
    std::uint64_t hash = 1469598103934665603ULL;
    std::array<char, 8192U> buffer{};
    while (input) {
        input.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
        const auto count = input.gcount();
        for (std::streamsize i = 0; i < count; ++i) {
            hash ^= static_cast<std::uint64_t>(static_cast<unsigned char>(buffer[static_cast<std::size_t>(i)]));
            hash *= 1099511628211ULL;
        }
    }
    std::ostringstream output;
    output << std::hex << std::setw(16) << std::setfill('0') << hash;
    return output.str();
}

std::string hash_machine_profile_content_manifest(const std::filesystem::path& path) {
    // Machine profiles should become stale when a performance-relevant asset changes,
    // not when a file timestamp or phase/documentation rule marker changes. The content
    // manifest keeps modified_ns for incremental tooling, so hash a canonical subset.
    std::ifstream input(path);
    if (!input) return privacy_safe_hash("missing-profile-content-manifest");

    auto split_csv = [](std::string_view line) {
        std::vector<std::string> fields;
        std::string field;
        bool quoted = false;
        for (std::size_t index = 0U; index < line.size(); ++index) {
            const char c = line[index];
            if (c == '"') {
                if (quoted && index + 1U < line.size() && line[index + 1U] == '"') {
                    field.push_back('"');
                    ++index;
                } else {
                    quoted = !quoted;
                }
            } else if (c == ',' && !quoted) {
                fields.push_back(field);
                field.clear();
            } else {
                field.push_back(c);
            }
        }
        fields.push_back(field);
        return fields;
    };

    auto strip_record_ending = [](std::string& record) {
        if (!record.empty() && record.back() == '\r') record.pop_back();
    };

    std::string header_line;
    if (!std::getline(input, header_line)) return privacy_safe_hash("empty-profile-content-manifest");
    strip_record_ending(header_line);
    const auto header = split_csv(header_line);
    auto index_of = [&](std::string_view name) -> std::optional<std::size_t> {
        for (std::size_t index = 0U; index < header.size(); ++index) {
            if (header[index] == name) return index;
        }
        return std::nullopt;
    };
    const auto asset_id = index_of("asset_id");
    const auto asset_type = index_of("asset_type");
    const auto family = index_of("family");
    const auto pack = index_of("pack");
    const auto relative_path = index_of("relative_path");
    const auto size_bytes = index_of("size_bytes");
    const auto sha256 = index_of("sha256");
    const auto enabled = index_of("enabled");
    if (!asset_id || !asset_type || !family || !pack || !relative_path || !size_bytes || !sha256 || !enabled) {
        return hash_file_privacy_safe(path);
    }
    const std::size_t max_index = std::max({*asset_id, *asset_type, *family, *pack,
                                             *relative_path, *size_bytes, *sha256, *enabled});

    std::ostringstream canonical;
    std::string line;
    while (std::getline(input, line)) {
        strip_record_ending(line);
        if (line.empty()) continue;
        const auto fields = split_csv(line);
        if (fields.size() <= max_index) continue;
        if (lower(fields[*asset_type]) == "rules") continue;
        canonical << fields[*asset_id] << '|'
                  << fields[*asset_type] << '|'
                  << fields[*family] << '|'
                  << fields[*pack] << '|'
                  << fields[*relative_path] << '|'
                  << fields[*size_bytes] << '|'
                  << fields[*sha256] << '|'
                  << lower(fields[*enabled]) << '\n';
    }
    return privacy_safe_hash(canonical.str());
}

std::string classify_gpu(std::string_view vendor, std::string_view renderer) {
    const std::string combined = lower(std::string(vendor) + " " + std::string(renderer));
    if (contains(combined, "llvmpipe") || contains(combined, "softpipe") || contains(combined, "software")) {
        return "software";
    }
    if (contains(combined, "intel") || contains(combined, "uhd") || contains(combined, "iris")) {
        return "integrated";
    }
    if (contains(combined, "nvidia") || contains(combined, "geforce") ||
        contains(combined, "radeon") || contains(combined, "amd")) {
        return "discrete";
    }
    return "unknown";
}

std::string make_machine_fingerprint(const MachineProfileContext& context, std::string_view ruleset_id) {
    std::ostringstream canonical;
    canonical << lower(context.vendor) << '|'
              << lower(context.renderer) << '|'
              << lower(context.version) << '|'
              << context.gl_major << '.' << context.gl_minor << '|'
              << lower(context.video_driver) << '|'
              << context.width << 'x' << context.height << '|'
              << ruleset_id << '|'
              << context.content_hash;
    return privacy_safe_hash(canonical.str());
}

MachineProfile make_conservative_profile(const MachineProfileContext& context,
                                         const render::AdaptivePointBudget& capability_budget,
                                         int target_fps) {
    MachineProfile profile;
    profile.status = "conservative";
    profile.source_kind = "capability-fallback";
    profile.run_class = "first-run";
    profile.ruleset_id = std::string(kMachineProfileRuleset);
    profile.fingerprint = make_machine_fingerprint(context);
    profile.content_hash = context.content_hash;
    profile.gpu_class = classify_gpu(context.vendor, context.renderer);
    profile.resolution_width = context.width;
    profile.resolution_height = context.height;
    profile.target_fps = target_fps;
    profile.recommended.environment_points = capability_budget.gameplay_points;
    profile.recommended.combined_point_budget = combined_budget_for(capability_budget.gameplay_points);
    profile.recommended.protected_fallback_points = fallback_for(capability_budget.gameplay_points);
    const auto& total_budget = render::system_point_budget_for_total(profile.recommended.combined_point_budget);
    profile.recommended.submitted_soft_cap = total_budget.submitted_soft_cap;
    profile.recommended.full_rate_entities = profile.gpu_class == "software" ? 1 : 2;
    profile.recommended.reduced_rate_entities = profile.gpu_class == "integrated" ? 6 : 4;
    profile.recommended.active_lights = 4U;
    profile.recommended.material_layers = 3U;
    profile.recommended.sound_ripples = 3U;
    profile.recommended.animated_actors = 3U;
    profile.recommended.playbook_evaluations = 8U;
    profile.recommended.tupd_test_objects = 1U;
    profile.recommended.scui_panels = 2U;
    profile.validation.content_hash_pass = true;
    return profile;
}

MachineProfileLoadResult load_machine_profile(const std::filesystem::path& path,
                                              const MachineProfileContext& context,
                                              bool require_active_status) {
    MachineProfileLoadResult result;
    if (!std::filesystem::is_regular_file(path)) {
        result.reason = "profile file is missing";
        return result;
    }
    result.present = true;
    try {
        const data::UDataDocument document = data::UDataDocument::load(path);
        if (document.has_errors()) {
            result.reason = "profile document contains parse errors";
            return result;
        }
        const std::string schema = read_string(document, "header", "schema_name", "");
        const std::uint32_t major = read_u32(document, "header", "schema_major", 0U);
        if (schema != kMachineProfileSchema || major != kMachineProfileSchemaMajor) {
            result.reason = "profile schema is unsupported";
            return result;
        }
        result.profile = read_profile(document);
        if (require_active_status && result.profile.status != "active") {
            result.reason = "profile is not active";
            return result;
        }
        if (result.profile.ruleset_id != kMachineProfileRuleset) {
            result.stale = true;
            result.reason = "benchmark ruleset changed";
            return result;
        }
        if (result.profile.content_hash != context.content_hash) {
            result.stale = true;
            result.reason = "performance content signature changed or profile uses the legacy raw-manifest signature";
            return result;
        }
        if (result.profile.fingerprint != make_machine_fingerprint(context, result.profile.ruleset_id)) {
            result.stale = true;
            result.reason = "GPU, driver, renderer, or resolution fingerprint changed";
            return result;
        }
        if (!supported_environment_points(result.profile.recommended.environment_points)) {
            result.reason = "recommended point tier is unsupported";
            return result;
        }
        if (result.profile.recommended.protected_fallback_points > result.profile.recommended.environment_points) {
            result.reason = "protected fallback exceeds recommended environment points";
            return result;
        }
        result.valid = true;
        result.reason = "profile is current";
        return result;
    } catch (const std::exception& exception) {
        result.reason = exception.what();
        return result;
    }
}

MachineProfileLoadResult load_active_or_conservative(const std::filesystem::path& project_root,
                                                     const MachineProfileContext& context,
                                                     const render::AdaptivePointBudget& capability_budget,
                                                     int target_fps) {
    const auto paths = machine_profile_paths(project_root);
    auto active = load_machine_profile(paths.active, context, true);
    if (active.valid) return active;
    auto previous = load_machine_profile(paths.previous_known_good, context, false);
    if (previous.valid) {
        previous.used_previous_known_good = true;
        previous.profile.status = "previous-known-good";
        previous.reason = "active profile unavailable or stale; previous known-good profile selected";
        return previous;
    }
    MachineProfileLoadResult fallback;
    fallback.profile = make_conservative_profile(context, capability_budget, target_fps);
    fallback.valid = true;
    fallback.stale = active.stale || previous.stale;
    if (active.present) {
        fallback.reason = "active profile rejected (" + active.reason +
                          "); conservative capability profile selected";
    } else {
        fallback.reason = "first-run conservative capability profile selected";
    }
    return fallback;
}

bool validate_profile_candidate(const MachineProfile& profile, const MachineProfileContext& context,
                                std::string* reason) {
    const auto reject = [&](std::string message) {
        if (reason != nullptr) *reason = std::move(message);
        return false;
    };
    if (profile.status != "candidate") return reject("profile status is not candidate");
    if (profile.ruleset_id != kMachineProfileRuleset) return reject("candidate ruleset is stale");
    if (profile.content_hash != context.content_hash) return reject("candidate content hash is stale");
    if (profile.fingerprint != make_machine_fingerprint(context, profile.ruleset_id)) {
        return reject("candidate machine fingerprint is stale");
    }
    if (!profile.validation.completed || !profile.validation.route_pass ||
        !profile.validation.frame_pacing_pass || !profile.validation.memory_guard_pass ||
        !profile.validation.content_hash_pass) {
        std::string failed;
        const auto append_failed = [&](std::string_view name, bool passed) {
            if (passed) return;
            if (!failed.empty()) failed += ", ";
            failed += name;
        };
        append_failed("completed", profile.validation.completed);
        append_failed("route", profile.validation.route_pass);
        append_failed("frame-pacing", profile.validation.frame_pacing_pass);
        append_failed("memory-guard", profile.validation.memory_guard_pass);
        append_failed("content-hash", profile.validation.content_hash_pass);
        return reject("candidate validation gates failed: " + failed);
    }
    if (profile.validation.passed_stages == 0U) return reject("candidate has no passing benchmark stage");
    if (profile.sustainable_environment_points == 0U ||
        profile.burst_environment_points < profile.sustainable_environment_points) {
        return reject("candidate environment measurements are inconsistent");
    }
    if (!supported_environment_points(profile.recommended.environment_points) ||
        profile.recommended.environment_points > profile.sustainable_environment_points) {
        return reject("candidate recommendation is not a supported sustainable tier");
    }
    if (profile.recommended.protected_fallback_points > profile.recommended.environment_points) {
        return reject("candidate fallback exceeds recommendation");
    }
    if (profile.recommended.submitted_soft_cap == 0U ||
        profile.recommended.submitted_soft_cap > profile.recommended.combined_point_budget) {
        return reject("candidate submitted-point cap is invalid");
    }
    if (reason != nullptr) *reason = "candidate passed all protected promotion gates";
    return true;
}

bool save_machine_profile_atomic(const MachineProfile& profile, const std::filesystem::path& path,
                                 std::string* error) {
    data::UDataDocument document = profile.document;
    write_known_fields(document, profile);
    std::filesystem::create_directories(path.parent_path());
    return document.save_atomic(path, error);
}

bool promote_candidate_atomic(const std::filesystem::path& project_root,
                              const MachineProfileContext& context,
                              std::string* error) {
    const auto paths = machine_profile_paths(project_root);
    const auto candidate_result = load_machine_profile(paths.candidate, context, false);
    if (!candidate_result.present || !candidate_result.valid) {
        if (error != nullptr) *error = candidate_result.reason.empty() ? "candidate is unavailable" : candidate_result.reason;
        return false;
    }
    std::string validation_reason;
    if (!validate_profile_candidate(candidate_result.profile, context, &validation_reason)) {
        if (error != nullptr) *error = validation_reason;
        return false;
    }

    std::filesystem::create_directories(paths.directory);
    if (std::filesystem::is_regular_file(paths.active)) {
        if (!copy_atomic(paths.active, paths.previous_known_good, error)) return false;
    }

    MachineProfile promoted = candidate_result.profile;
    promoted.status = "active";
    promoted.source_kind = promoted.source_kind.empty() ? "native-stress" : promoted.source_kind;
    if (!save_machine_profile_atomic(promoted, paths.active, error)) return false;

    data::UDataDocument receipt;
    receipt.set("promotion", "status", json_string("active"));
    receipt.set("promotion", "ruleset_id", json_string(promoted.ruleset_id));
    receipt.set("promotion", "fingerprint", json_string(promoted.fingerprint));
    receipt.set("promotion", "content_hash", json_string(promoted.content_hash));
    receipt.set("promotion", "environment_points", std::to_string(promoted.recommended.environment_points));
    receipt.set("promotion", "previous_known_good_preserved",
                std::filesystem::is_regular_file(paths.previous_known_good) ? "true" : "false");
    receipt.set("privacy", "contains_private_paths", "false");
    std::string receipt_error;
    if (!receipt.save_atomic(paths.promotion_receipt, &receipt_error) && error != nullptr) {
        *error = "profile was promoted but promotion receipt failed: " + receipt_error;
    }
    return true;
}

}  // namespace signalcloud::benchmark
