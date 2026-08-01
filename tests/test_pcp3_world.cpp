#include "engine/pcp3/pcp3_asset.hpp"

#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

namespace fs = std::filesystem;

#pragma pack(push, 1)
struct Header {
    char magic[8];
    std::uint32_t version;
    std::uint32_t record_size;
    std::uint64_t point_count;
    std::array<std::uint8_t, 32> checksum{};
    std::uint64_t flags{0};
};
struct Record {
    float x, y, z, radius;
    float r, g, b, a;
    float nx, ny, nz, density;
    std::uint32_t layer_id;
    std::uint32_t flags;
    float attribute0;
    float attribute1;
};
#pragma pack(pop)

void write_cloud(const fs::path& path, std::initializer_list<Record> records) {
    Header header{{'P','C','P','3','C','L','D','1'}, 1U, 64U, static_cast<std::uint64_t>(records.size())};
    std::ofstream output(path, std::ios::binary);
    output.write(reinterpret_cast<const char*>(&header), sizeof(header));
    for (const auto& record : records) output.write(reinterpret_cast<const char*>(&record), sizeof(record));
}

void write_main(const fs::path& path, const std::string& asset_id, const std::string& zone,
                float x, const std::string& world_sidecar) {
    std::ofstream output(path);
    output << "@udata 1\n\n[header]\n"
           << "asset_id: {\"value\":\"" << asset_id << "\"};\n"
           << "display_name: {\"value\":\"" << asset_id << "\"};\n"
           << "asset_kind: {\"value\":\"room\"};\n\n"
           << "[body]\ncloud_file: {\"value\":\"" << asset_id << ".pcp3cloud\"};\n\n"
           << "[runtime]\nenabled: {\"value\":true};\n"
           << "auto_preview_in_game: {\"value\":false};\n"
           << "preview_zone: {\"value\":\"" << zone << "\"};\n"
           << "preview_position: {\"value\":[" << x << ",0,0]};\n"
           << "preview_scale: {\"value\":1.0};\n\n"
           << "[runtime_world]\nudata_sidecar_file: {\"value\":\"" << world_sidecar << "\"};\n";
}

void write_world(const fs::path& path, const std::string& room_id, const std::string& zone,
                 const std::string& portal_id, const std::string& destination_asset,
                 const std::string& destination_portal, bool interaction_required) {
    std::ofstream output(path);
    output << "@udata 1\n\n[world]\n"
           << "enabled: {\"value\":true};\n"
           << "game_enabled: {\"value\":true};\n"
           << "stress_enabled: {\"value\":true};\n"
           << "world_id: {\"value\":\"world_test\"};\n"
           << "room_id: {\"value\":\"" << room_id << "\"};\n"
           << "room_name: {\"value\":\"" << room_id << "\"};\n"
           << "host_zone: {\"value\":\"" << zone << "\"};\n"
           << "execute_portals: {\"value\":true};\n"
           << "portal_interaction_required: {\"value\":true};\n"
           << "portal_cooldown: {\"value\":0.8};\n"
           << "show_portal_debug: {\"value\":true};\n"
           << "show_bounds_debug: {\"value\":true};\n"
           << "max_portals: {\"value\":32};\n"
           << "max_placements: {\"value\":64};\n"
           << "max_liquid_points: {\"value\":150000};\n\n"
           << "[liquid]\nenabled: {\"value\":true};\n"
           << "type: {\"value\":\"water\"};\n"
           << "color: {\"value\":\"#2F6F8F\"};\n"
           << "opacity: {\"value\":0.72};\n"
           << "wave_amplitude: {\"value\":0.2};\n"
           << "wave_frequency: {\"value\":1.0};\n"
           << "flow_scale: {\"value\":1.0};\n\n"
           << "[theme]\napply: {\"value\":true};\n\n"
           << "[world_theme.0]\nsemantic: {\"value\":\"wall\"};\ncolor: {\"value\":\"#123456\"};\n\n"
           << "[portal.0]\nid: {\"value\":\"" << portal_id << "\"};\n"
           << "kind: {\"value\":\"door\"};\n"
           << "position: {\"value\":[0,1,0]};\n"
           << "size: {\"value\":[2,3,1]};\n"
           << "destination_asset_id: {\"value\":\"" << destination_asset << "\"};\n"
           << "destination_portal_id: {\"value\":\"" << destination_portal << "\"};\n"
           << "arrival_offset: {\"value\":[0,0,1]};\n"
           << "arrival_yaw_degrees: {\"value\":90};\n"
           << "interaction_required: {\"value\":" << (interaction_required ? "true" : "false") << "};\n"
           << "one_way: {\"value\":false};\n"
           << "enabled: {\"value\":true};\n\n"
           << "[spawn.0]\nid: {\"value\":\"default_spawn\"};\n"
           << "role: {\"value\":\"default\"};\n"
           << "position: {\"value\":[0,0,2]};\n"
           << "yaw_degrees: {\"value\":180};\n"
           << "enabled: {\"value\":true};\n\n"
           << "[world_flow.0]\nposition: {\"value\":[0,0,0]};\n"
           << "direction: {\"value\":[1,0,0]};\n"
           << "strength: {\"value\":2};\n"
           << "viscosity: {\"value\":0.5};\n";
}

int main(int argc, char** argv) {
    if (argc < 2) return 2;
    const fs::path root = fs::path(argv[1]) / "reports" / "pcp3_world_cpp_test";
    fs::remove_all(root);
    const auto make_asset = [&](const std::string& id, const std::string& zone, float x,
                                const std::string& portal, const std::string& destination,
                                const std::string& destination_portal) {
        const fs::path dir = root / "content" / "pcp3_assets" / "room" / id;
        fs::create_directories(dir);
        write_cloud(dir / (id + ".pcp3cloud"), {
            {0,0,0,2, 1,1,1,1, 0,1,0,1, 1,1,0,0},
            {0,0.5F,0,2, 0.1F,0.2F,0.3F,1, 0,1,0,1, 2,6,0,0},
        });
        write_main(dir / (id + ".udata"), id, zone, x, id + ".pcp3world.udata");
        write_world(dir / (id + ".pcp3world.udata"), id, zone, portal, destination, destination_portal, true);
    };
    make_asset("room_a", "Reception Tape", 0.0F, "north_door", "room_b", "south_door");
    make_asset("room_b", "Corridor Junction", 10.0F, "south_door", "room_a", "north_door");

    std::vector<std::string> warnings;
    const auto assets = signalcloud::pcp3::discover_assets(root, &warnings);
    if (!warnings.empty() || assets.size() != 2U) return 3;
    const auto& room_a = assets.front().metadata.asset_id == "room_a" ? assets.front() : assets.back();
    if (!room_a.runtime_world.present || !room_a.runtime_world.enabled) return 4;
    if (room_a.runtime_world.portals.size() != 1U || room_a.runtime_world.flow_nodes.size() != 1U) return 5;

    signalcloud::pcp3::RuntimeContext context;
    context.time_seconds = 0.25;
    context.scanner_active = true;
    context.debug_evidence = true;
    const auto points = signalcloud::pcp3::points_for_zone(
        assets, "Reception Tape", signalcloud::pcp3::PreviewPurpose::game, context, 4000U);
    if (points.size() <= room_a.layered_points.size()) return 6;
    const auto water = std::find_if(points.begin(), points.end(), [](const auto& point) {
        return point.color[2] > point.color[0] && point.color[2] > point.color[1];
    });
    if (water == points.end()) return 7;

    const auto blocked = signalcloud::pcp3::world_portal_transfer(
        assets, "Reception Tape", signalcloud::pcp3::PreviewPurpose::game,
        {0.0F, 1.0F, 0.0F}, false);
    if (blocked.has_value()) return 8;
    const auto transfer = signalcloud::pcp3::world_portal_transfer(
        assets, "Reception Tape", signalcloud::pcp3::PreviewPurpose::game,
        {0.0F, 1.0F, 0.0F}, true);
    if (!transfer || !transfer->valid) return 9;
    if (transfer->destination_asset_id != "room_b" || transfer->destination_zone != "Corridor Junction") return 10;
    if (std::abs(transfer->destination.x - 10.0F) > 0.001F || std::abs(transfer->destination.y - 1.0F) > 0.001F || std::abs(transfer->destination.z - 1.0F) > 0.001F) return 11;

    std::cout << "PCP3 world assembly, portal, theme, and liquid runtime PASS\n";
    fs::remove_all(root);
    return 0;
}
