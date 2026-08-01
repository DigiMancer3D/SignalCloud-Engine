#include "engine/pcp3/pcp3_asset.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>
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

int main(int argc, char** argv) {
    if (argc < 2) return 2;

    signalcloud::pcp3::RuntimeStreaming settings;
    settings.present = true;
    settings.enabled = true;
    settings.game_enabled = true;
    settings.stress_enabled = true;
    settings.near_distance = 10.0F;
    settings.mid_distance = 20.0F;
    settings.far_distance = 30.0F;
    settings.near_ratio = 1.0F;
    settings.mid_ratio = 0.5F;
    settings.far_ratio = 0.25F;
    settings.very_far_ratio = 0.1F;
    settings.minimum_points = 5U;
    settings.maximum_points = 80U;
    settings.semantic_reserve_ratio = 0.25F;

    const auto b0 = signalcloud::pcp3::streaming_point_budget(settings, 100U, 5.0F);
    const auto b1 = signalcloud::pcp3::streaming_point_budget(settings, 100U, 15.0F);
    const auto b2 = signalcloud::pcp3::streaming_point_budget(settings, 100U, 25.0F);
    const auto b3 = signalcloud::pcp3::streaming_point_budget(settings, 100U, 50.0F);
    if (b0 != 80U) return 3;
    if (b1 != 50U) return 4;
    if (b2 != 25U) return 5;
    if (b3 != 10U) return 6;

    std::vector<signalcloud::pcp3::LayeredPoint> layered(100U);
    for (std::size_t i = 0U; i < layered.size(); ++i) {
        layered[i].point.position[0] = static_cast<float>(i);
        layered[i].flags = (i % 10U == 0U) ? 1U : 0U;
    }
    const auto sampled = signalcloud::pcp3::streaming_sample_indices(layered, settings, 20U);
    if (sampled.size() != 20U || !std::is_sorted(sampled.begin(), sampled.end())) return 7;
    const std::size_t priority_count = static_cast<std::size_t>(std::count_if(
        sampled.begin(), sampled.end(), [&](std::size_t index) { return layered[index].flags != 0U; }));
    if (priority_count < 5U) return 8;

    const fs::path root = fs::path(argv[1]) / "reports" / "pcp3_streaming_cpp_test";
    fs::remove_all(root);
    const fs::path dir = root / "content" / "pcp3_assets" / "environment_object" / "streamed_asset";
    fs::create_directories(dir);
    Header header{{'P','C','P','3','C','L','D','1'}, 1U, 64U, 100U};
    {
        std::ofstream output(dir / "streamed_asset.pcp3cloud", std::ios::binary);
        output.write(reinterpret_cast<const char*>(&header), sizeof(header));
        for (std::uint32_t i = 0; i < 100U; ++i) {
            Record record{static_cast<float>(i),0,0,2, 0.8F,0.8F,0.8F,1, 0,1,0,1, 1U, i % 10U == 0U ? 1U : 0U, 0,0};
            output.write(reinterpret_cast<const char*>(&record), sizeof(record));
        }
    }
    {
        std::ofstream output(dir / "streamed_asset.udata");
        output << "@udata 1\n\n[header]\nasset_id: {\"value\":\"streamed_asset\"};\n"
               << "display_name: {\"value\":\"Streamed Asset\"};\nasset_kind: {\"value\":\"environment_object\"};\n\n"
               << "[body]\ncloud_file: {\"value\":\"streamed_asset.pcp3cloud\"};\n\n"
               << "[runtime]\nenabled: {\"value\":true};\nauto_preview_in_game: {\"value\":true};\n"
               << "preview_zone: {\"value\":\"Reception Tape\"};\npreview_position: {\"value\":[0,0,0]};\npreview_scale: {\"value\":1};\n\n"
               << "[runtime_streaming]\nudata_sidecar_file: {\"value\":\"streamed_asset.pcp3stream.udata\"};\n";
    }
    {
        std::ofstream output(dir / "streamed_asset.pcp3stream.udata");
        output << "@udata 1\n\n[streaming]\n"
               << "enabled: {\"value\":true};\ngame_enabled: {\"value\":true};\nstress_enabled: {\"value\":true};\n"
               << "profile: {\"value\":\"balanced\"};\nlod_policy: {\"value\":\"distance_semantic\"};\n"
               << "near_distance: {\"value\":10};\nmid_distance: {\"value\":20};\nfar_distance: {\"value\":30};\n"
               << "near_ratio: {\"value\":1};\nmid_ratio: {\"value\":0.5};\nfar_ratio: {\"value\":0.25};\nvery_far_ratio: {\"value\":0.1};\n"
               << "minimum_points: {\"value\":5};\nmaximum_points: {\"value\":80};\n"
               << "preserve_semantic_points: {\"value\":true};\nsemantic_reserve_ratio: {\"value\":0.25};\n";
    }

    std::vector<std::string> warnings;
    const auto assets = signalcloud::pcp3::discover_assets(root, &warnings);
    if (!warnings.empty() || assets.size() != 1U) return 9;
    if (!assets.front().runtime_streaming.present || !assets.front().runtime_streaming.enabled) return 10;

    signalcloud::pcp3::RuntimeContext near_context;
    near_context.viewer_position = {0,0,0};
    const auto near_points = signalcloud::pcp3::points_for_zone(
        assets, "Reception Tape", signalcloud::pcp3::PreviewPurpose::game, near_context, 500U);
    if (near_points.size() != 80U) return 11;

    signalcloud::pcp3::RuntimeContext far_context;
    far_context.viewer_position = {100,0,0};
    const auto far_points = signalcloud::pcp3::points_for_zone(
        assets, "Reception Tape", signalcloud::pcp3::PreviewPurpose::game, far_context, 500U);
    if (far_points.size() != 10U) return 12;

    std::cout << "PCP3 bounded streaming, LOD, and semantic reserve runtime PASS\n";
    fs::remove_all(root);
    return 0;
}
