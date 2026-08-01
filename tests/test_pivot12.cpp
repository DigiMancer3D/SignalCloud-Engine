#include "engine/combat/combat_system.hpp"
#include "engine/economy/economy_system.hpp"
#include "engine/ui/ar_interface.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/world_seed.hpp"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string_view>

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
    const auto seed = world::mix_seed(0xA12D0A1ULL, {0, 0, 0}, 4);
    const auto level = world::LiminalLevel::make_pivot11_scavenging(seed);

    bool thin_scavenger = false;
    bool thin_vending = false;
    bool step_bench = false;
    bool step_pallet = false;
    for (const auto& obstacle : level.obstacles()) {
        const float width = obstacle.max_x - obstacle.min_x;
        const float depth = obstacle.max_z - obstacle.min_z;
        if (obstacle.name == "THIN SCAVENGER AR TERMINAL") {
            thin_scavenger = std::min(width, depth) <= 0.40F;
        }
        if (obstacle.name == "THIN ALMOND AR VENDING TERMINAL") {
            thin_vending = std::min(width, depth) <= 0.40F;
        }
        if (obstacle.name == "PARKOUR SORTING BENCH") step_bench = obstacle.height <= 0.60F;
        if (obstacle.name == "AUTO STEP DROP PALLET") step_pallet = obstacle.height <= 0.60F;
    }
    check(thin_scavenger && thin_vending,
          "exchange terminals are thin, front-readable structural slabs");
    check(step_bench && step_pallet,
          "bench and pallet fit the Pivot 12 automatic-step envelope");

    auto economy = economy::EconomySystem::make_pivot12();
    const math::Vec3 vending_position{1073.0F, 1.72F, -152.0F};
    check(economy.interaction_target(vending_position, "Scavenger Exchange", 0.0F) ==
              economy::InteractionTarget::vending,
          "vending terminal advertises a proximity interaction target");
    const auto opened = economy.interact(vending_position, "Scavenger Exchange", 2);
    check(opened.success && opened.menu_opened && economy.vending_menu_active(),
          "first vending interaction opens the AR menu without purchasing");
    economy.set_menu_product(2);
    economy.adjust_menu_quantity(1);
    const auto bought = economy.confirm_vending_purchase(vending_position);
    check(bought.success && bought.quantity == 2U && bought.xar_delta == -8,
          "AR vending menu purchases a selected quantity at deterministic price");
    economy.close_vending_menu();
    check(!economy.vending_menu_active(), "right-click/K style close leaves gameplay state clean");

    const auto world_ui = economy.build_visual_points(0.4F, "Scavenger Exchange", vending_position);
    check(finite_points(world_ui) && world_ui.size() > 2'000U,
          "thin terminals, proximity signage, and pickups produce finite point visuals");

    ui::ArInterface ar;
    ui::ArPose pose;
    pose.camera_position = {1047.0F, 1.72F, -160.0F};
    pose.forward = {1.0F, 0.0F, 0.0F};
    pose.right = {0.0F, 0.0F, 1.0F};
    ui::ArInterfaceData normal;
    normal.health_ratio = 1.0F;
    normal.oxygen_ratio = 0.8F;
    normal.sabs_ratio = 0.7F;
    normal.carry_ratio = 0.3F;
    normal.xar = 42;
    normal.magazine = 7;
    normal.reserve = 36;
    normal.interaction_near = true;
    const auto normal_points = ar.build_points(0.5F, pose, normal);
    ui::ArInterfaceData danger = normal;
    danger.health_ratio = 0.03F;
    danger.vending_menu = true;
    danger.menu_product = 3;
    danger.menu_quantity = 4;
    danger.menu_unit_price = 6;
    const auto danger_points = ar.build_points(0.5F, pose, danger);
    check(finite_points(normal_points) && finite_points(danger_points),
          "camera-anchored AR HUD and quantity menu stay finite");
    check(danger_points.size() > normal_points.size(),
          "low-health edge warning and open menu add visible information without title text");
    ar.notify(ui::ArFeedbackKind::sale, 48);
    check(ar.feedback_kind() == ui::ArFeedbackKind::sale && ar.feedback_value() == 48,
          "transaction result is represented by a short-lived in-world AR event");

    auto combat = combat::CombatSystem::make_pivot10();
    combat::ViewmodelPose prybar_pose;
    prybar_pose.camera_position = {987.0F, 1.72F, -160.0F};
    prybar_pose.forward = {1.0F, 0.0F, 0.0F};
    prybar_pose.right = {0.0F, 0.0F, 1.0F};
    prybar_pose.weapon_slot = 2;
    const auto prybar = combat.build_viewmodel_points(0.7F, prybar_pose);
    check(finite_points(prybar) && prybar.size() > 3'500U,
          "reworked arms, fingers, and safety-edged prybar remain visible and finite");

    if (failures != 0) {
        std::cerr << failures << " Pivot 12 checks failed.\n";
        return EXIT_FAILURE;
    }
    std::cout << "All SignalCloud Pivot 12 AR interaction, world-combat policy, and readability checks passed.\n";
    return EXIT_SUCCESS;
}
