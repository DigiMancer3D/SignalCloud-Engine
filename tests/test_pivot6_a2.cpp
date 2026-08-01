#include "engine/render/point_cloud.hpp"
#include "engine/render/room_visibility.hpp"
#include "engine/render/sound_ripple.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/player_controller.hpp"
#include "engine/world/world_seed.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

namespace {
int failures = 0;
void check(bool condition, const std::string& message) {
    if (condition) std::cout << "PASS: " << message << '\n';
    else { std::cerr << "FAIL: " << message << '\n'; ++failures; }
}
}

int main(int argc, char** argv) {
    using namespace signalcloud;
    const auto seed = world::mix_seed(0xA11D0A1ULL, {0, 0, 0}, 4);
    const auto level = world::LiminalLevel::make_pivot6_depth(seed);

    check(level.connections().size() == 7U,
          "Pivot 6 a2 declares seven physical room connections");
    check(level.lights().size() >= 8U,
          "connected complex exposes local light anchors");
    check(level.zone_name({655.5F, 1.72F, -164.0F}) == "Traversal & Water Lab" &&
          level.zone_name({657.0F, 1.72F, -164.0F}) == "Fallen Office",
          "Traversal Lab and Fallen Office no longer overlap ambiguously");

    // The nested doorway at x=694 is open, while the adjacent wall is solid
    // from either side.
    check(level.can_occupy_3d(694.0F, -179.82F, 0.0F, 1.72F, 0.30F, 0.0F),
          "nested doorway opening is physically traversable");
    check(!level.can_occupy_3d(688.0F, -179.82F, 0.0F, 1.72F, 0.30F, 0.0F),
          "solid nested boundary blocks from the junction side");
    check(!level.can_occupy_3d(688.0F, -180.18F, 0.0F, 1.72F, 0.30F, 0.0F),
          "solid nested boundary blocks from the room side");

    const auto previews = level.connection_previews(
        "Corridor Junction", {704.0F, 1.72F, -164.0F});
    const bool sees_hall = std::any_of(previews.begin(), previews.end(), [](const auto& preview) {
        return preview.destination_zone == "Long Signal Hall" && preview.strength > 0.08F;
    });
    check(sees_hall, "approaching an opening requests a Long Signal Hall preview");

    const auto cloud = render::PointCloud::make_liminal_level(level, {420'000U, seed});
    std::vector<render::PreviewRequest> requests;
    for (const auto& preview : previews) {
        requests.push_back({std::string(preview.destination_zone), preview.center, preview.strength});
    }
    const auto selection = render::select_room_ranges(
        cloud, "Corridor Junction", 420'000U, 420'000U, false,
        {704.0F, 1.72F, -164.0F}, 38.0F, requests);
    check(selection.preview_rooms >= 1U && selection.submitted_rooms >= 2U,
          "visibility submission includes a limited connected-room preview");
    check(selection.submitted_points < cloud.points().size(),
          "connected preview remains smaller than the resident tape");

    const auto light_near = level.strongest_light({724.0F, 1.72F, -164.0F}, "Long Signal Hall");
    const auto light_far = level.strongest_light({744.0F, 1.72F, -164.0F}, "Long Signal Hall");
    check(light_near.influence > light_far.influence && light_near.influence > 0.1F,
          "local lights increase fill influence by range");

    world::PlayerController diver({820.0F, -0.5F, -164.0F});
    world::PlayerMoveInput dive;
    dive.descend = true;
    const float start_y = diver.position().y;
    const float start_x = diver.position().x;
    for (int i = 0; i < 60; ++i) {
        diver.update(dive, {0.80F, -0.60F, 0.0F}, 1.0F / 60.0F, level);
    }
    check(diver.position().y < start_y - 0.65F,
          "Ctrl dive follows downward look direction");
    check(diver.position().x > start_x + 0.25F,
          "Ctrl dive carries the swimmer along the look vector");

    world::PlayerController climber({799.35F, 0.40F, -160.5F});
    world::PlayerMoveInput climb;
    climb.jump_pressed = true;
    climber.update(climb, {1.0F, 0.0F, 0.0F}, 1.0F / 60.0F, level);
    check(climber.grounded() && climber.surface_name().find("ALMOND TECH") != std::string_view::npos,
          "Space mounts the low Almond platform from deep water");

    render::SoundRipple ripple;
    ripple.trigger({700.0F, 1.0F, -164.0F}, 0.8F, 0.8F);
    const float first_radius = ripple.radius();
    ripple.update(0.25F);
    check(ripple.active() && ripple.radius() > first_radius && ripple.intensity() < 0.8F,
          "spatial sound ripple expands and fades");

    if (argc > 1) {
        const std::filesystem::path root(argv[1]);
        std::ifstream source(root / "app/game_main.cpp");
        const std::string text((std::istreambuf_iterator<char>(source)),
                               std::istreambuf_iterator<char>());
        const auto shutdown_pos = text.find("splash_audio.shutdown()");
        const auto quit_pos = text.find("SDL_Quit();", shutdown_pos);
        check(shutdown_pos != std::string::npos && quit_pos != std::string::npos && shutdown_pos < quit_pos,
              "SDL audio stream is destroyed before SDL_Quit");
    }

    if (failures == 0) {
        std::cout << "All SignalCloud Pivot 6 a2 Room Continuity tests passed.\n";
        return 0;
    }
    return 1;
}
