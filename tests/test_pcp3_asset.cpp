#include "engine/pcp3/pcp3_asset.hpp"

#include <array>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>

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

int main(int argc, char** argv) {
    if (argc < 2) return 2;
    if (argc >= 3) {
        signalcloud::pcp3::Asset verified;
        std::string verify_error;
        if (!signalcloud::pcp3::load_cloud(fs::path(argv[2]), verified, &verify_error)) {
            std::cerr << verify_error << '\n';
            return 20;
        }
        if (!verified.finite() || verified.layered_points.empty()) return 21;
        std::cout << "PCP3 sealed cloud validation PASS: " << verified.layered_points.size() << " points\n";
        return 0;
    }
    const fs::path root = fs::path(argv[1]) / "reports" / "pcp3_cpp_test";
    fs::remove_all(root);
    const fs::path asset_dir = root / "content" / "pcp3_assets" / "environment_object" / "cpp_orb";
    fs::create_directories(asset_dir);
    const fs::path cloud = asset_dir / "cpp_orb.pcp3cloud";
    Header header{{'P','C','P','3','C','L','D','1'}, 1U, 64U, 2U};
    Record records[2] = {
        {0,1,0,2, 1,0,0,1, 0,1,0,1, 1, 8, 0,0},
        {1,2,3,3, 0,1,0,1, 0,1,0,0.8F, 2, 1, 4,5},
    };
    {
        std::ofstream output(cloud, std::ios::binary);
        output.write(reinterpret_cast<const char*>(&header), sizeof(header));
        output.write(reinterpret_cast<const char*>(records), sizeof(records));
    }
    const fs::path sidecar = asset_dir / "cpp_orb.udata";
    {
        std::ofstream output(sidecar);
        output << "@udata 1\n\n[header]\n"
               << "data_type: {\"value\":\"pcp3_asset\"};\n"
               << "asset_id: {\"value\":\"cpp_orb\"};\n"
               << "display_name: {\"value\":\"C++ Orb\"};\n"
               << "asset_kind: {\"value\":\"environment_object\"};\n\n"
               << "[body]\ncloud_file: {\"value\":\"cpp_orb.pcp3cloud\"};\n\n"
               << "[runtime]\nenabled: {\"value\":true};\n"
               << "auto_preview_in_game: {\"value\":true};\n"
               << "preview_zone: {\"value\":\"Reception Tape\"};\n"
               << "preview_position: {\"value\":[2.0,1.0,-3.0]};\n"
               << "preview_scale: {\"value\":2.0};\n\n"
               << "[runtime_factory]\n"
               << "udata_sidecar_file: {\"value\":\"cpp_orb.pcp3factory.udata\"};\n\n"
               << "[runtime_interaction]\n"
               << "udata_sidecar_file: {\"value\":\"cpp_orb.pcp3interaction.udata\"};\n";
    }
    const fs::path factory_sidecar = asset_dir / "cpp_orb.pcp3factory.udata";
    {
        std::ofstream output(factory_sidecar);
        output << "@udata 1\n\n[factory]\n"
               << "enabled: {\"value\":true};\n"
               << "game_enabled: {\"value\":true};\n"
               << "stress_enabled: {\"value\":true};\n"
               << "scanner_required: {\"value\":true};\n"
               << "proximity_required: {\"value\":false};\n"
               << "proximity_radius: {\"value\":20.0};\n"
               << "duration: {\"value\":2.0};\n"
               << "loop: {\"value\":true};\n"
               << "max_nested_points: {\"value\":10};\n\n"
               << "[keyframe.0]\ntime: {\"value\":0.0};\nposition: {\"value\":[0,0,0]};\nrotation: {\"value\":[0,0,0]};\nscale: {\"value\":[1,1,1]};\n\n"
               << "[keyframe.1]\ntime: {\"value\":2.0};\nposition: {\"value\":[2,0,0]};\nrotation: {\"value\":[0,0,0]};\nscale: {\"value\":[1,1,1]};\n\n"
               << "[placement.0]\nasset_id: {\"value\":\"nested_dot\"};\nkind: {\"value\":\"object\"};\nposition: {\"value\":[1,0,0]};\nrotation: {\"value\":[0,0,0]};\nscale: {\"value\":1.0};\nenabled: {\"value\":true};\n";
    }
    const fs::path interaction_sidecar = asset_dir / "cpp_orb.pcp3interaction.udata";
    {
        std::ofstream output(interaction_sidecar);
        output << "@udata 1\n\n[interaction]\n"
               << "enabled: {\"value\":true};\n"
               << "game_enabled: {\"value\":true};\n"
               << "stress_enabled: {\"value\":true};\n"
               << "default_cooldown: {\"value\":1.3};\n"
               << "alert_duration: {\"value\":3.0};\n"
               << "pulse_duration: {\"value\":1.25};\n"
               << "proxy_lifetime: {\"value\":5.0};\n"
               << "max_state_entries: {\"value\":256};\n"
               << "max_event_ledger: {\"value\":256};\n"
               << "max_active_proxies: {\"value\":16};\n"
               << "reset_policy: {\"value\":\"zone_exit\"};\n";
    }
    const fs::path nested_dir = root / "content" / "pcp3_assets" / "environment_object" / "nested_dot";
    fs::create_directories(nested_dir);
    const fs::path nested_cloud = nested_dir / "nested_dot.pcp3cloud";
    Header nested_header{{'P','C','P','3','C','L','D','1'}, 1U, 64U, 1U};
    Record nested_record{0,0,0,2, 0,0,1,1, 0,1,0,1, 1,0,0,0};
    {
        std::ofstream output(nested_cloud, std::ios::binary);
        output.write(reinterpret_cast<const char*>(&nested_header), sizeof(nested_header));
        output.write(reinterpret_cast<const char*>(&nested_record), sizeof(nested_record));
    }
    {
        std::ofstream output(nested_dir / "nested_dot.udata");
        output << "@udata 1\n\n[header]\nasset_id: {\"value\":\"nested_dot\"};\nasset_kind: {\"value\":\"environment_object\"};\n\n"
               << "[body]\ncloud_file: {\"value\":\"nested_dot.pcp3cloud\"};\n\n"
               << "[runtime]\nenabled: {\"value\":true};\nauto_preview_in_game: {\"value\":false};\npreview_zone: {\"value\":\"Nested Storage\"};\npreview_position: {\"value\":[0,0,0]};\npreview_scale: {\"value\":1.0};\n";
    }

    signalcloud::pcp3::Asset asset;
    std::string error;
    if (!signalcloud::pcp3::load_asset(sidecar, asset, &error)) {
        std::cerr << error << '\n';
        return 3;
    }
    if (asset.layered_points.size() != 2U || !asset.finite()) return 4;
    const auto rendered = asset.render_points(asset.metadata.preview_position, asset.metadata.preview_scale);
    if (rendered.size() != 2U) return 5;
    if (rendered[1].position[0] != 4.0F || rendered[1].position[1] != 5.0F || rendered[1].position[2] != 3.0F) return 6;

    std::vector<std::string> warnings;
    const auto assets = signalcloud::pcp3::discover_assets(root, &warnings);
    if (assets.size() != 2U || !warnings.empty()) return 7;
    const auto hidden_points = signalcloud::pcp3::points_for_zone(
        assets, "Reception Tape", signalcloud::pcp3::PreviewPurpose::game, 10U);
    if (!hidden_points.empty()) return 8;
    signalcloud::pcp3::RuntimeContext context;
    context.time_seconds = 1.0;
    context.scanner_active = true;
    context.viewer_position = {2.0F, 1.0F, -3.0F};
    const auto game_points = signalcloud::pcp3::points_for_zone(
        assets, "Reception Tape", signalcloud::pcp3::PreviewPurpose::game, context, 10U);
    const auto stress_points = signalcloud::pcp3::points_for_zone(
        assets, "Reception Tape", signalcloud::pcp3::PreviewPurpose::stress, context, 10U);
    if (game_points.size() != 3U || stress_points.size() != 3U) return 9;
    if (std::abs(game_points.front().position[0] - 3.0F) > 0.001F) return 10;
    if (!asset.runtime_factory.present || !asset.runtime_factory.enabled) return 11;
    if (!asset.runtime_interaction.present || !asset.runtime_interaction.enabled) return 12;
    if (std::abs(asset.runtime_interaction.default_cooldown - 1.3F) > 0.001F) return 13;

    std::cout << "PCP3 C++ asset loader PASS\n";
    fs::remove_all(root);
    return 0;
}
