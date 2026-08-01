#include "engine/render/point_cloud.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/world_seed.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <string_view>

namespace {

bool near(float a, float b, float epsilon = 0.08F) {
    return std::abs(a - b) <= epsilon;
}

const signalcloud::world::ThresholdEnvelope* find_envelope(
    const signalcloud::world::LiminalLevel& level,
    std::string_view zone_a,
    std::string_view zone_b) {
    for (const auto& envelope : level.threshold_envelopes()) {
        if ((envelope.zone_a == zone_a && envelope.zone_b == zone_b) ||
            (envelope.zone_a == zone_b && envelope.zone_b == zone_a)) {
            return &envelope;
        }
    }
    return nullptr;
}

bool has_panel(const signalcloud::world::ThresholdEnvelope& envelope,
               float base_y, float top_y) {
    for (const auto& panel : envelope.panels) {
        if (near(panel.base_y, base_y) && near(panel.height, top_y)) return true;
    }
    return false;
}

}  // namespace

int main() {
    using namespace signalcloud;
    int failures = 0;
    auto check = [&](bool condition, const char* message) {
        if (!condition) {
            std::cerr << "FAIL: " << message << '\n';
            ++failures;
        }
    };

    const auto seed = world::mix_seed(0xA11D0A1ULL, {8, 0, 2}, 4);
    const auto level = world::LiminalLevel::make_pivot8_submerged(seed);

    check(level.threshold_envelopes().size() == level.connections().size(),
          "every physical connection owns one normalized structural envelope");

    const auto* framed = find_envelope(level, "Corridor Junction", "Threshold Gallery");
    check(framed != nullptr, "framed gallery threshold has an envelope");
    if (framed != nullptr) {
        check(near(framed->base_y, 0.0F) && near(framed->aperture.bottom_y, 0.0F),
              "dry framed doorway begins at the shared floor");
        check(has_panel(*framed, 3.2F, 5.8F),
              "dry framed doorway owns a full lintel panel");
    }

    const auto* window = find_envelope(level, "Threshold Gallery", "Raised Window Annex");
    check(window != nullptr, "raised window has an envelope");
    if (window != nullptr) {
        check(has_panel(*window, 0.0F, 0.90F),
              "raised window owns a sill panel");
        check(has_panel(*window, 2.82F, 5.8F),
              "raised window owns a lintel panel");
    }

    const auto* hall_shaft = find_envelope(level, "Long Signal Hall", "Vertical Flood Shaft");
    check(hall_shaft != nullptr, "hall-to-shaft threshold has an envelope");
    if (hall_shaft != nullptr) {
        check(near(hall_shaft->base_y, -14.0F) &&
              near(hall_shaft->aperture.bottom_y, 0.0F),
              "dry-to-deep threshold derives its lower wall and higher opening floor");
        check(has_panel(*hall_shaft, -14.0F, 0.0F),
              "hall-to-shaft threshold owns the missing lower wall panel");
    }

    const auto* shaft_tunnel = find_envelope(level, "Vertical Flood Shaft", "Submerged Service Tunnel");
    check(shaft_tunnel != nullptr, "shaft-to-tunnel threshold has an envelope");
    if (shaft_tunnel != nullptr) {
        check(near(shaft_tunnel->base_y, -14.0F) &&
              near(shaft_tunnel->aperture.bottom_y, -6.5F),
              "unequal underwater floors derive a lower sill wall");
        check(has_panel(*shaft_tunnel, -14.0F, -6.5F),
              "shaft-to-tunnel threshold owns its lower wall panel");
    }

    const auto* tunnel_cavity = find_envelope(level, "Submerged Service Tunnel", "Open Pressure Cavity");
    check(tunnel_cavity != nullptr, "tunnel-to-cavity threshold has an envelope");
    if (tunnel_cavity != nullptr) {
        check(near(tunnel_cavity->base_y, -22.0F) &&
              near(tunnel_cavity->aperture.bottom_y, -6.5F),
              "tunnel-to-cavity threshold uses the higher traversal floor");
        check(has_panel(*tunnel_cavity, -22.0F, -6.5F),
              "tunnel-to-cavity threshold owns its deep lower wall panel");
    }

    const auto* cavity_lab = find_envelope(level, "Open Pressure Cavity", "Submerged Boundary Lab");
    check(cavity_lab != nullptr, "cavity-to-water-lab threshold has an envelope");
    if (cavity_lab != nullptr) {
        check(near(cavity_lab->base_y, -22.0F) &&
              near(cavity_lab->aperture.bottom_y, -4.2F),
              "cavity-to-water-lab threshold uses the lab floor as opening floor");
        check(has_panel(*cavity_lab, -22.0F, -4.2F),
              "cavity-to-water-lab threshold owns its lower wall panel");
    }

    // No source zone may have two portal gates in exactly the same place. This
    // guards against the confusing doubled portal-frame presentation.
    bool duplicate_portal = false;
    for (std::size_t i = 0; i < level.portals().size(); ++i) {
        for (std::size_t j = i + 1U; j < level.portals().size(); ++j) {
            const auto& a = level.portals()[i];
            const auto& b = level.portals()[j];
            if (a.source_zone != b.source_zone) continue;
            if (near(a.center.x, b.center.x, 0.02F) &&
                near(a.center.y, b.center.y, 0.02F) &&
                near(a.center.z, b.center.z, 0.02F)) {
                duplicate_portal = true;
            }
        }
    }
    check(!duplicate_portal, "portal frames are not duplicated at one source threshold");

    const auto cloud = render::PointCloud::make_liminal_level(level, {500'000U, seed});
    check(cloud.finite(), "normalized envelope cloud remains finite");
    check(cloud.stats().threshold_structure_points == 15'000U,
          "three percent of the budget is reserved for threshold wall envelopes");
    check(!cloud.ranges_for("Long Signal Hall").empty() &&
          !cloud.ranges_for("Vertical Flood Shaft").empty(),
          "both sides of a depth threshold retain streamed ranges");

    if (failures == 0) {
        std::cout << "All SignalCloud Pivot 8 a2 Structural Envelope tests passed.\n";
        return 0;
    }
    return 1;
}
