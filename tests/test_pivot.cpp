#include "engine/data/udata.hpp"
#include "engine/input/input_profile.hpp"
#include "engine/render/memory_budget.hpp"
#include "engine/render/point_cloud.hpp"
#include "engine/render/point_types.hpp"
#include "engine/world/world_seed.hpp"
#include "engine/ui/tactical_map_prototype.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

namespace {
int failures = 0;
void check(bool value, const std::string& label) {
    if (value) std::cout << "PASS: " << label << '\n';
    else { std::cerr << "FAIL: " << label << '\n'; ++failures; }
}
std::string read_text(const std::filesystem::path& path) {
    std::ifstream input(path);
    std::ostringstream output;
    output << input.rdbuf();
    return output.str();
}
}

int main(int argc, char** argv) {
    const std::filesystem::path root = argc > 1 ? argv[1] : std::filesystem::current_path();
    check(sizeof(signalcloud::render::PointGpu) == 48, "point format remains 48 bytes");

    const auto seed_a = signalcloud::world::mix_seed(42, {1, 2, 3}, 7);
    const auto seed_b = signalcloud::world::mix_seed(42, {1, 2, 3}, 7);
    const auto seed_c = signalcloud::world::mix_seed(42, {1, 2, 4}, 7);
    check(seed_a == seed_b, "world seed mixing is deterministic");
    check(seed_a != seed_c, "different chunk coordinates produce different seeds");

    const auto cloud = signalcloud::render::PointCloud::make_liminal_room(
        {18.0F, 5.8F, 24.0F, 100'000U, seed_a});
    check(cloud.points().size() == 100'000U, "pivot room generates exactly 100000 points");
    check(cloud.finite(), "all generated point values are finite");
    check(cloud.stats().wall_points + cloud.stats().floor_points + cloud.stats().ceiling_points + cloud.stats().dust_points == 100'000U,
          "point class counts sum to total");

    const auto estimate = signalcloud::render::estimate_point_memory(100'000U);
    check(estimate.bytes_single == 4'800'000U, "100000-point base memory is 4.8 MB decimal");
    check(estimate.bytes_triple == 14'400'000U, "triple-buffer estimate is three regions");

    const auto profile = signalcloud::input::InputProfile::solo_paw_defaults();
    check(profile.validate().empty(), "soloPAW input profile validates");
    check(profile.find("sabs") != nullptr && profile.find("squad_ping") != nullptr,
          "six-button extension includes SABS and squad actions");

    const auto config = signalcloud::data::UDataDocument::load(root / "config/renderer.udata");
    check(!config.has_errors(), "renderer .udata loads without fatal errors");
    check(config.value("body", "initial_point_count").has_value(), "renderer config declares point count");

    check(!std::filesystem::exists(root / "game/prototype"), "brawler prototype directory is absent");
    const std::string cmake = read_text(root / "CMakeLists.txt");
    check(cmake.find("HoodRatBrawler") == std::string::npos, "CMake no longer declares Hood Rat Brawler");
    check(cmake.find("arena_timeline") == std::string::npos, "CMake has no arena timeline dependency");

    signalcloud::legacy::TacticalMapPrototype tactical;
    const auto matrix = tactical.view_projection(16.0F / 9.0F);
    check(matrix.m[0] != 0.0F && matrix.m[9] != 0.0F && matrix.m[15] == 1.0F, "tactical map compatibility matrix is valid");

    if (failures == 0) {
        std::cout << "All SignalCloud Pivot 0 tests passed.\n";
        return 0;
    }
    return 1;
}
