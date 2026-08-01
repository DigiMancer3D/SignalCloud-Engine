#include "engine/ui/ar_interface.hpp"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string_view>
#include <vector>

namespace {
int failures = 0;

void check(bool condition, std::string_view message) {
    if (!condition) {
        ++failures;
        std::cerr << "FAIL: " << message << '\n';
    }
}

bool finite_points(const std::vector<signalcloud::render::PointGpu>& points) {
    if (points.empty()) return false;
    for (const auto& point : points) {
        for (float value : point.position) if (!std::isfinite(value)) return false;
        if (!std::isfinite(point.radius) || point.radius <= 0.0F) return false;
    }
    return true;
}
}  // namespace

int main() {
    using namespace signalcloud;

    ui::ArInterface ar;
    ui::ArPose pose;
    pose.camera_position = {0.0F, 0.0F, 0.0F};
    pose.forward = {0.0F, 0.0F, -1.0F};
    pose.right = {1.0F, 0.0F, 0.0F};

    ui::ArInterfaceData base;
    base.health_ratio = 0.80F;
    base.oxygen_ratio = 0.65F;
    base.sabs_ratio = 0.55F;
    base.carry_ratio = 0.25F;
    base.xar = 84;
    base.magazine = 6;
    base.weapon_slot = 1;

    const auto base_points = ar.build_points(0.25F, pose, base);
    check(finite_points(base_points), "a3 base HUD points stay finite");

    float min_x = 10.0F;
    float max_x = -10.0F;
    float min_y = 10.0F;
    for (const auto& p : base_points) {
        min_x = std::min(min_x, p.position[0]);
        max_x = std::max(max_x, p.position[0]);
        min_y = std::min(min_y, p.position[1]);
    }
    check(min_x < -0.545F && max_x > 0.545F,
          "XAR and weapon towers reach the requested top corners");
    check(min_y < -0.299F,
          "health and oxygen bars sit halfway closer to the bottom edge");

    ui::ArInterfaceData scanner = base;
    scanner.scanner_active = true;
    scanner.scanner_strength = 0.72F;
    scanner.scanner_contacts[0] = {ui::ScannerContactKind::formed, 0.90F};
    scanner.scanner_contacts[1] = {ui::ScannerContactKind::formless, 0.82F};
    scanner.scanner_contacts[2] = {ui::ScannerContactKind::exchange, 0.70F};
    scanner.scanner_contacts[3] = {ui::ScannerContactKind::loot, 0.64F};
    scanner.scanner_contact_count = 4;
    const auto scanner_points = ar.build_points(0.50F, pose, scanner);
    check(finite_points(scanner_points), "scanner signature points stay finite");
    check(scanner_points.size() > base_points.size() + 180U,
          "scanner adds a visible signature band instead of only changing color");

    ar.notify(ui::ArFeedbackKind::failure, 0);
    const auto feedback = ar.build_points(0.75F, pose, base);
    bool raised_center_feedback = false;
    for (const auto& p : feedback) {
        const float x = p.position[0];
        const float y = p.position[1];
        const auto& c = p.color;
        if (std::abs(x) < 0.12F && y > 0.065F && y < 0.18F &&
            c[0] > 0.90F && c[1] < 0.25F) {
            raised_center_feedback = true;
            break;
        }
    }
    check(raised_center_feedback,
          "accept/deny feedback is raised to the requested two-thirds screen height");

    if (failures != 0) {
        std::cerr << failures << " Pivot 12 a3 checks failed.\n";
        return EXIT_FAILURE;
    }
    std::cout << "All SignalCloud Pivot 12 a3 AR layout and scanner-intelligence checks passed.\n";
    return EXIT_SUCCESS;
}
