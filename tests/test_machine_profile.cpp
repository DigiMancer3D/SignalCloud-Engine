#include "engine/benchmark/machine_profile.hpp"
#include "engine/data/udata.hpp"
#include "engine/render/adaptive_budget.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

namespace fs = std::filesystem;

#define CHECK(expression) \
    do { \
        if (!(expression)) { \
            std::cerr << "CHECK failed at " << __FILE__ << ':' << __LINE__ \
                      << ": " #expression << '\n'; \
            return 1; \
        } \
    } while (false)
using signalcloud::benchmark::MachineProfile;
using signalcloud::benchmark::MachineProfileContext;

namespace {

MachineProfileContext context(std::string content_hash = "content-a", int width = 1280) {
    return {
        "Intel",
        "Mesa Intel(R) UHD Graphics",
        "4.6 Mesa test",
        "x11",
        4,
        6,
        width,
        720,
        std::move(content_hash),
    };
}

MachineProfile valid_candidate(const MachineProfileContext& profile_context,
                               std::uint32_t recommended = 8'000'000U) {
    MachineProfile profile;
    profile.status = "candidate";
    profile.source_kind = "native-stress";
    profile.run_class = "quick";
    profile.ruleset_id = std::string(signalcloud::benchmark::kMachineProfileRuleset);
    profile.fingerprint = signalcloud::benchmark::make_machine_fingerprint(profile_context);
    profile.content_hash = profile_context.content_hash;
    profile.gpu_class = "integrated";
    profile.resolution_width = profile_context.width;
    profile.resolution_height = profile_context.height;
    profile.target_fps = 60;
    profile.burst_environment_points = 10'000'000U;
    profile.sustainable_environment_points = 8'000'000U;
    profile.burst_entities = 8;
    profile.sustainable_entities = 6;
    profile.recommended.environment_points = recommended;
    profile.recommended.combined_point_budget = 20'000'000U;
    profile.recommended.protected_fallback_points = 4'000'000U;
    profile.recommended.submitted_soft_cap = 3'800'000U;
    profile.recommended.full_rate_entities = 4;
    profile.recommended.reduced_rate_entities = 6;
    profile.validation.completed = true;
    profile.validation.route_pass = true;
    profile.validation.frame_pacing_pass = true;
    profile.validation.memory_guard_pass = true;
    profile.validation.content_hash_pass = true;
    profile.validation.passed_stages = 6U;
    return profile;
}

}  // namespace

int main() {
    const auto profile_context = context();
    const auto fingerprint = signalcloud::benchmark::make_machine_fingerprint(profile_context);
    CHECK(fingerprint.size() == 16U);
    CHECK(fingerprint.find("Intel") == std::string::npos);
    CHECK(fingerprint == signalcloud::benchmark::make_machine_fingerprint(profile_context));
    CHECK(fingerprint != signalcloud::benchmark::make_machine_fingerprint(context("content-a", 1920)));
    CHECK(fingerprint != signalcloud::benchmark::make_machine_fingerprint(context("content-b")));

    const auto budget = signalcloud::render::recommend_point_budget(
        profile_context.vendor, profile_context.renderer, profile_context.gl_major, profile_context.gl_minor);
    const auto conservative = signalcloud::benchmark::make_conservative_profile(profile_context, budget, 60);
    CHECK(conservative.status == "conservative");
    CHECK(conservative.recommended.environment_points == 8'000'000U);
    CHECK(conservative.recommended.protected_fallback_points == 4'000'000U);
    CHECK(conservative.recommended.combined_point_budget == 20'000'000U);
    CHECK(conservative.fingerprint == fingerprint);

    const fs::path root = fs::temp_directory_path() / "signalcloud_machine_profile_test";
    std::error_code ec;
    fs::remove_all(root, ec);
    fs::create_directories(root / "user_data/machine_profiles");
    fs::create_directories(root / "content");
    const fs::path manifest = root / "content/manifest.csv";
    {
        std::ofstream out(manifest, std::ios::trunc);
        out << "asset_id,asset_type,family,pack,relative_path,size_bytes,sha256,modified_ns,enabled\n"
            << "surface,materials,wall,core,core/materials/wall.jmap,10,aaa,100,true\n"
            << "phase,rules,phase,core,core/rules/phase.udata,20,bbb,100,true\n";
    }
    const auto stable_content_hash =
        signalcloud::benchmark::hash_machine_profile_content_manifest(manifest);
    CHECK(stable_content_hash == "4dd3bf2665d2d580");
    {
        std::ofstream out(manifest, std::ios::binary | std::ios::trunc);
        out << "asset_id,asset_type,family,pack,relative_path,size_bytes,sha256,modified_ns,enabled\r\n"
            << "surface,materials,wall,core,core/materials/wall.jmap,10,aaa,100,true\r\n"
            << "phase,rules,phase,core,core/rules/phase.udata,20,bbb,100,true\r\n";
    }
    CHECK(signalcloud::benchmark::hash_machine_profile_content_manifest(manifest) == stable_content_hash);
    {
        std::ofstream out(manifest, std::ios::trunc);
        out << "asset_id,asset_type,family,pack,relative_path,size_bytes,sha256,modified_ns,enabled\n"
            << "surface,materials,wall,core,core/materials/wall.jmap,10,aaa,999,true\n"
            << "phase,rules,phase,core,core/rules/phase.udata,20,changed,999,true\n"
            << "phase2,rules,phase,core,core/rules/phase2.udata,30,ccc,999,true\n";
    }
    CHECK(signalcloud::benchmark::hash_machine_profile_content_manifest(manifest) == stable_content_hash);
    {
        std::ofstream out(manifest, std::ios::trunc);
        out << "asset_id,asset_type,family,pack,relative_path,size_bytes,sha256,modified_ns,enabled\n"
            << "surface,materials,wall,core,core/materials/wall.jmap,10,changed,999,true\n";
    }
    CHECK(signalcloud::benchmark::hash_machine_profile_content_manifest(manifest) != stable_content_hash);
    const auto paths = signalcloud::benchmark::machine_profile_paths(root);
    const auto fallback_hint = signalcloud::benchmark::read_active_profile_target_hint(root);
    CHECK(!fallback_hint.from_active_profile);
    CHECK(fallback_hint.width == 1280 && fallback_hint.height == 720);

    MachineProfile candidate = valid_candidate(profile_context);
    candidate.document.set("future", "preserved_field", "{\"value\":42}");
    std::string error;
    CHECK(signalcloud::benchmark::save_machine_profile_atomic(candidate, paths.candidate, &error));
    auto loaded_candidate = signalcloud::benchmark::load_machine_profile(paths.candidate, profile_context, false);
    CHECK(loaded_candidate.valid);
    CHECK(loaded_candidate.profile.document.value("future", "preserved_field").has_value());
    std::string reason;
    CHECK(signalcloud::benchmark::validate_profile_candidate(loaded_candidate.profile, profile_context, &reason));
    CHECK(signalcloud::benchmark::promote_candidate_atomic(root, profile_context, &error));

    auto active = signalcloud::benchmark::load_machine_profile(paths.active, profile_context, true);
    CHECK(active.valid);
    CHECK(active.profile.status == "active");
    CHECK(active.profile.recommended.environment_points == 8'000'000U);
    CHECK(active.profile.document.value("future", "preserved_field").has_value());
    const auto active_hint = signalcloud::benchmark::read_active_profile_target_hint(root);
    CHECK(active_hint.from_active_profile);
    CHECK(active_hint.width == 1280 && active_hint.height == 720);
    CHECK(active_hint.target_fps == 60);

    MachineProfile second = valid_candidate(profile_context, 4'000'000U);
    second.sustainable_environment_points = 4'000'000U;
    second.burst_environment_points = 8'000'000U;
    second.recommended.combined_point_budget = 12'000'000U;
    second.recommended.protected_fallback_points = 2'000'000U;
    second.recommended.submitted_soft_cap = 2'600'000U;
    CHECK(signalcloud::benchmark::save_machine_profile_atomic(second, paths.candidate, &error));
    CHECK(signalcloud::benchmark::promote_candidate_atomic(root, profile_context, &error));
    auto previous = signalcloud::benchmark::load_machine_profile(paths.previous_known_good, profile_context, false);
    CHECK(previous.valid);
    CHECK(previous.profile.recommended.environment_points == 8'000'000U);
    active = signalcloud::benchmark::load_machine_profile(paths.active, profile_context, true);
    CHECK(active.valid);
    CHECK(active.profile.recommended.environment_points == 4'000'000U);

    MachineProfile rejected = valid_candidate(profile_context, 8'000'000U);
    rejected.validation.route_pass = false;
    CHECK(signalcloud::benchmark::save_machine_profile_atomic(rejected, paths.candidate, &error));
    reason.clear();
    CHECK(!signalcloud::benchmark::validate_profile_candidate(rejected, profile_context, &reason));
    CHECK(reason.find("route") != std::string::npos);
    CHECK(!signalcloud::benchmark::promote_candidate_atomic(root, profile_context, &error));
    active = signalcloud::benchmark::load_machine_profile(paths.active, profile_context, true);
    CHECK(active.valid);
    CHECK(active.profile.recommended.environment_points == 4'000'000U);

    auto stale_content = signalcloud::benchmark::load_machine_profile(paths.active, context("content-changed"), true);
    CHECK(stale_content.present);
    CHECK(stale_content.stale);
    CHECK(!stale_content.valid);

    auto resolved = signalcloud::benchmark::load_active_or_conservative(root, context("content-changed"), budget, 60);
    CHECK(resolved.valid);
    CHECK(resolved.profile.status == "conservative");
    CHECK(resolved.profile.recommended.environment_points == 8'000'000U);

    fs::remove_all(root, ec);
    return 0;
}
