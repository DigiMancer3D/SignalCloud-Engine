#include "engine/render/point_cloud.hpp"
#include "engine/render/room_visibility.hpp"
#include "engine/render/sound_ripple.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/world_seed.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <string>
#include <vector>

namespace {
int failures = 0;
void check(bool condition, const char* message) {
    if (condition) std::cout << "PASS: " << message << '\n';
    else { std::cerr << "FAIL: " << message << '\n'; ++failures; }
}

bool has_destination(const std::vector<signalcloud::world::ConnectionPreview>& previews,
                     std::string_view destination) {
    return std::any_of(previews.begin(), previews.end(), [&](const auto& preview) {
        return preview.destination_zone == destination;
    });
}
}

int main() {
    using namespace signalcloud;
    const auto seed = world::mix_seed(0xA5A3A1ULL, {5, 3, 1}, 4);
    const auto level = world::LiminalLevel::make_pivot11_scavenging(seed);

    std::size_t tested_sides = 0U;
    bool every_side_visible = true;
    bool every_normal_reversed = true;
    std::vector<world::ConnectionPreview> proof_previews;
    math::Vec3 proof_position{};
    for (const auto& connection : level.connections()) {
        const auto from_a = level.connection_aperture(connection, connection.zone_a);
        const auto from_b = level.connection_aperture(connection, connection.zone_b);
        every_normal_reversed = every_normal_reversed &&
            std::abs(math::dot(from_a.normal, from_b.normal) + 1.0F) < 0.01F;

        const auto verify_side = [&](std::string_view source, std::string_view destination,
                                     const world::ConnectionAperture& aperture) {
            const float approach = std::max(0.25F, std::min(connection.preview_distance * 0.70F, 4.0F));
            const math::Vec3 position = aperture.center - aperture.normal * approach;
            const auto previews = level.connection_previews(source, position);
            every_side_visible = every_side_visible && has_destination(previews, destination);
            ++tested_sides;
            if (source == "Traversal & Water Lab" && destination == "Fallen Office") {
                proof_previews = previews;
                proof_position = position;
            }
        };
        verify_side(connection.zone_a, connection.zone_b, from_a);
        if (connection.bidirectional) verify_side(connection.zone_b, connection.zone_a, from_b);
    }
    check(tested_sides >= 20U && every_normal_reversed,
          "canonical threshold aperture reverses exactly across every connected room side");
    check(every_side_visible,
          "destination preview activates from every authored bidirectional threshold approach");

    const auto cloud = render::PointCloud::make_liminal_level(level, {460'000U, seed});
    std::vector<render::PreviewRequest> requests;
    for (const auto& preview : proof_previews) {
        requests.push_back({std::string(preview.destination_zone), preview.center, preview.strength,
                            preview.viewer_position, preview.normal, preview.half_width,
                            preview.bottom_y, preview.top_y});
    }
    const auto selection = render::select_room_ranges(
        cloud, "Traversal & Water Lab", 460'000U, 460'000U, false,
        proof_position, 38.0F, requests);
    const bool strength_carried = std::any_of(selection.ranges.begin(), selection.ranges.end(),
        [](const auto& range) { return range.aperture.enabled && range.aperture.strength > 0.0F; });
    check(selection.preview_rooms >= 1U && strength_carried,
          "preview submission carries clipping geometry and visibility strength");

    render::SoundRipple ripple;
    ripple.trigger_event({0.0F, 1.0F, 0.0F}, 0.95F, render::FrequencyBand::low,
                         0.15F, 0xA5A3A1U, 1.4F, 1.0F, 5U, 0.72F);
    ripple.update(0.75F);
    const auto radii = ripple.wave_radii();
    check(ripple.visible_wave_count() == 5U,
          "five authored sound waves become five distinct visible ring radii");
    check(radii[0] > radii[1] && radii[1] > radii[2] && radii[2] > radii[3] && radii[3] > radii[4],
          "audio rings trail the leading wave in strict radius order");

    if (failures == 0) {
        std::cout << "All A5a3r1 preview continuity and multi-ring audio checks passed.\n";
        return 0;
    }
    return 1;
}
