#include "engine/pcp3/pcp3_asset.hpp"

#include <array>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

#pragma pack(push, 1)
struct Header {
    char magic[8]; std::uint32_t version; std::uint32_t record_size; std::uint64_t point_count;
    std::array<std::uint8_t, 32> checksum{}; std::uint64_t flags{0};
};
struct Record {
    float x,y,z,radius; float r,g,b,a; float nx,ny,nz,density;
    std::uint32_t layer_id; std::uint32_t flags; float attribute0; float attribute1;
};
#pragma pack(pop)

void write_cloud(const fs::path& path, std::initializer_list<Record> records) {
    Header header{{'P','C','P','3','C','L','D','1'}, 1U, 64U, static_cast<std::uint64_t>(records.size())};
    std::ofstream output(path, std::ios::binary);
    output.write(reinterpret_cast<const char*>(&header), sizeof(header));
    for (const auto& record : records) output.write(reinterpret_cast<const char*>(&record), sizeof(record));
}

void write_asset(const fs::path& root, const std::string& kind, const std::string& id,
                 const std::string& zone, bool preview, const std::string& encounter_sidecar = {}) {
    const fs::path dir = root / "content" / "pcp3_assets" / kind / id;
    fs::create_directories(dir);
    write_cloud(dir / (id + ".pcp3cloud"), {
        {0,0,0,2, 0.8F,0.8F,0.8F,1, 0,1,0,1, 1,0,0,0},
        {0,1,0,2, 0.5F,0.7F,1.0F,1, 0,1,0,1, 1,0,0,0},
    });
    std::ofstream output(dir / (id + ".udata"));
    output << "@udata 1\n\n[header]\nasset_id: {\"value\":\"" << id << "\"};\n"
           << "display_name: {\"value\":\"" << id << "\"};\nasset_kind: {\"value\":\"" << kind << "\"};\n\n"
           << "[body]\ncloud_file: {\"value\":\"" << id << ".pcp3cloud\"};\n\n"
           << "[runtime]\nenabled: {\"value\":true};\nauto_preview_in_game: {\"value\":" << (preview ? "true" : "false") << "};\n"
           << "preview_zone: {\"value\":\"" << zone << "\"};\npreview_position: {\"value\":[0,0,0]};\npreview_scale: {\"value\":1};\n";
    if (!encounter_sidecar.empty()) {
        output << "\n[runtime_encounter]\nudata_sidecar_file: {\"value\":\"" << encounter_sidecar << "\"};\n";
    }
}

void write_encounter(const fs::path& path) {
    std::ofstream output(path);
    output << "@udata 1\n\n[encounter]\n"
           << "enabled: {\"value\":true};\ngame_enabled: {\"value\":true};\nstress_enabled: {\"value\":true};\n"
           << "encounter_id: {\"value\":\"cpp_encounter\"};\nhost_zone: {\"value\":\"Reception Tape\"};\n"
           << "start_condition: {\"value\":\"world_enter\"};\nstart_position: {\"value\":[0,0,0]};\n"
           << "start_radius: {\"value\":8};\nstart_delay: {\"value\":0};\ncompletion_policy: {\"value\":\"all_waves_cleared\"};\n"
           << "completion_seconds: {\"value\":30};\ncompletion_delay: {\"value\":0.2};\ninter_wave_delay: {\"value\":0.5};\n"
           << "entity_lifetime: {\"value\":1};\nreset_policy: {\"value\":\"zone_exit\"};\nshow_debug: {\"value\":true};\n"
           << "console_events: {\"value\":true};\nmax_waves: {\"value\":16};\nmax_active_entities: {\"value\":8};\n"
           << "max_total_spawns: {\"value\":16};\nmax_friendlies: {\"value\":4};\nmax_boss_phases: {\"value\":4};\n\n"
           << "[reward]\npolicy: {\"value\":\"combined_hook\"};\nproofs: {\"value\":2};\nxar: {\"value\":12};\nscrap: {\"value\":3};\n\n"
           << "[wave.0]\nid: {\"value\":\"wave_1\"};\nindex: {\"value\":1};\nasset_ids: {\"value\":[\"enemy_a\"]};\n"
           << "count: {\"value\":2};\ndelay: {\"value\":0};\nactive_seconds: {\"value\":1};\nspawn_role: {\"value\":\"encounter\"};\n"
           << "spread_radius: {\"value\":2};\ncompletion_policy: {\"value\":\"lifetime\"};\n\n"
           << "[wave.1]\nid: {\"value\":\"wave_2\"};\nindex: {\"value\":2};\nasset_ids: {\"value\":[\"enemy_a\"]};\n"
           << "count: {\"value\":1};\ndelay: {\"value\":0};\nactive_seconds: {\"value\":1};\nspawn_role: {\"value\":\"encounter\"};\n"
           << "spread_radius: {\"value\":1};\ncompletion_policy: {\"value\":\"lifetime\"};\n\n"
           << "[boss_phase.0]\nid: {\"value\":\"phase_1\"};\nname: {\"value\":\"Pressure\"};\nprogress_threshold: {\"value\":0};\n"
           << "clip: {\"value\":\"Alert\"};\nmovement_profile: {\"value\":\"hover\"};\ntheme_target: {\"value\":\"#FF00FF\"};\n"
           << "effect_anchor: {\"value\":\"burst\"};\n\n"
           << "[friendly.0]\nid: {\"value\":\"helper\"};\nasset_id: {\"value\":\"friendly_a\"};\nposition: {\"value\":[2,0,0]};\n"
           << "rotation_degrees: {\"value\":[0,0,0]};\nscale: {\"value\":1};\ngroup: {\"value\":\"friendlies\"};\nenabled: {\"value\":true};\n";
}

int main(int argc, char** argv) {
    if (argc < 2) return 2;
    const fs::path root = fs::path(argv[1]) / "reports" / "pcp3_encounter_cpp_test";
    fs::remove_all(root);
    write_asset(root, "enemy", "enemy_a", "Unused", false);
    write_asset(root, "friendly", "friendly_a", "Unused", false);
    write_asset(root, "room", "host_room", "Reception Tape", true, "host_room.pcp3encounter.udata");
    write_encounter(root / "content" / "pcp3_assets" / "room" / "host_room" / "host_room.pcp3encounter.udata");

    std::vector<std::string> warnings;
    const auto assets = signalcloud::pcp3::discover_assets(root, &warnings);
    if (!warnings.empty() || assets.size() != 3U) return 3;
    const auto host = std::find_if(assets.begin(), assets.end(), [](const auto& asset) { return asset.metadata.asset_id == "host_room"; });
    if (host == assets.end() || !host->runtime_encounter.present || !host->runtime_encounter.enabled) return 4;
    if (host->runtime_encounter.waves.size() != 2U || host->runtime_encounter.friendlies.size() != 1U) return 5;

    signalcloud::pcp3::RuntimeEncounterState encounter_state;
    signalcloud::pcp3::RuntimeContext context;
    context.viewer_position = {0,0,0}; context.debug_evidence = true; context.encounter_state = &encounter_state;
    context.time_seconds = 0.0;
    auto points = signalcloud::pcp3::points_for_zone(assets, "Reception Tape", signalcloud::pcp3::PreviewPurpose::game, context, 10000U);
    if (points.size() <= host->layered_points.size()) return 6;
    auto events = encounter_state.take_events();
    if (std::none_of(events.begin(), events.end(), [](const auto& e) { return e.kind == "encounter_started"; })) return 7;
    if (std::count_if(events.begin(), events.end(), [](const auto& e) { return e.kind == "entity_spawned"; }) != 2) return 8;

    context.time_seconds = 2.0;
    (void)signalcloud::pcp3::points_for_zone(assets, "Reception Tape", signalcloud::pcp3::PreviewPurpose::game, context, 10000U);
    events = encounter_state.take_events();
    if (std::count_if(events.begin(), events.end(), [](const auto& e) { return e.kind == "entity_spawned"; }) != 1) return 9;

    context.time_seconds = 4.0;
    (void)signalcloud::pcp3::points_for_zone(assets, "Reception Tape", signalcloud::pcp3::PreviewPurpose::game, context, 10000U);
    events = encounter_state.take_events();
    const auto reward = std::find_if(events.begin(), events.end(), [](const auto& e) { return e.kind == "reward_hook"; });
    if (reward == events.end() || reward->reward_proofs != 2 || reward->reward_xar != 12 || reward->reward_scrap != 3) return 10;

    encounter_state.begin_zone("Corridor Junction", "zone_exit");
    context.time_seconds = 5.0;
    context.encounter_state = &encounter_state;
    (void)signalcloud::pcp3::points_for_zone(assets, "Reception Tape", signalcloud::pcp3::PreviewPurpose::game, context, 10000U);
    events = encounter_state.take_events();
    if (std::none_of(events.begin(), events.end(), [](const auto& e) { return e.kind == "encounter_started"; })) return 11;

    std::cout << "PCP3 bounded encounter, wave, friendly, boss phase, and reward telemetry runtime PASS\n";
    fs::remove_all(root);
    return 0;
}
