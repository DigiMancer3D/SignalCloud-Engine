#include "engine/combat/combat_system.hpp"
#include "engine/render/system_point_budget.hpp"

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
        if (!std::isfinite(point.radius)) return false;
    }
    return true;
}

}  // namespace

int main() {
    using namespace signalcloud;

    auto combat = combat::CombatSystem::make_pivot10();
    check(combat.entities().size() == 2U, "Pivot 10 preserves two combat families");
    check(std::abs(combat.entities().front().forward.x) > 0.9F,
          "formed creature begins with an explicit front direction");

    const auto initial = combat.build_visual_points(0.0F, "Live-Fire Signal Range");
    const auto animated = combat.build_visual_points(0.65F, "Live-Fire Signal Range");
    check(finite_points(initial) && finite_points(animated),
          "skeletal and formless animation points stay finite");
    check(initial.size() >= 4'500U,
          "Pivot 10 increases visible creature articulation without using millions of points");

    combat.emit_noise({1000.0F, 0.0F, -160.0F}, 1.0F, "Live-Fire Signal Range");
    const auto dog_before = combat.entities().front();
    combat.update(0.15F, {984.0F, 1.72F, -176.0F}, "Live-Fire Signal Range");
    const auto dog_after = combat.entities().front();
    const math::Vec3 displacement = dog_after.position - dog_before.position;
    check(math::length(displacement) < 0.8F,
          "formed creature turns before making an impossible sideways leap");
    check(math::dot(dog_after.forward, dog_before.forward) < 1.001F,
          "formed creature orientation remains normalized while turning");

    const math::Vec3 pistol_origin{999.0F, 1.05F, -160.0F};
    auto first = combat.fire_primary(pistol_origin, {1.0F, 0.0F, 0.0F}, 1, true);
    combat.update_timers(0.20F);
    auto second = combat.fire_primary(pistol_origin, {1.0F, 0.0F, 0.0F}, 1, true);
    check(first.hit && second.hit, "formed creature remains hittable during the reaction test");
    check(second.reaction_dodge, "formed creature uses a sideways/back reaction dodge");

    combat.reset_wave();
    const math::Vec3 shadow_origin{1002.0F, 1.05F, -140.0F};
    (void)combat.fire_primary(shadow_origin, {0.0F, 0.0F, -1.0F}, 1, true);
    combat.update_timers(0.20F);
    const auto shadow_hit = combat.fire_primary(shadow_origin, {0.0F, 0.0F, -1.0F}, 1, true);
    check(shadow_hit.reaction_dodge, "formless creature uses a collapse-and-flow reaction dodge");
    bool shadow_deformed = false;
    for (const auto& entity : combat.entities()) {
        if (entity.kind == combat::CreatureKind::formless_shadow) {
            shadow_deformed = entity.deformation > 0.5F && entity.state == combat::CreatureState::dodge;
        }
    }
    check(shadow_deformed, "formless dodge exposes a deformation state for rendering");

    combat::ViewmodelPose pistol_pose;
    pistol_pose.camera_position = {987.0F, 1.72F, -160.0F};
    pistol_pose.forward = {1.0F, 0.0F, 0.0F};
    pistol_pose.right = {0.0F, 0.0F, 1.0F};
    pistol_pose.pitch_degrees = -42.0F;
    pistol_pose.movement_amount = 1.0F;
    pistol_pose.sprinting = true;
    pistol_pose.weapon_slot = 1;
    const auto pistol_view = combat.build_viewmodel_points(0.5F, pistol_pose);
    check(finite_points(pistol_view) && pistol_view.size() >= 3'000U,
          "first-person point arms, hands, weapon, and lower body render together");

    combat::ViewmodelPose prybar_pose = pistol_pose;
    prybar_pose.weapon_slot = 2;
    const auto prybar_view = combat.build_viewmodel_points(0.75F, prybar_pose);
    check(finite_points(prybar_view) && prybar_view.size() >= 3'000U,
          "prybar viewmodel includes a visible directional swing tool");

    const auto& budgets = render::system_point_budgets();
    check(budgets.size() == 12U, "all requested 4M through 32M total tiers exist");
    bool balanced = true;
    for (const auto& budget : budgets) balanced = balanced && render::point_budget_is_balanced(budget);
    check(balanced, "each system point tier is split into balanced resource pools");
    const auto& full = render::system_point_budget_for_total(20'000'000U);
    check(full.total_points == 20'000'000U && full.environment_points <= 10'000'000U,
          "20M Full tier preserves an environment ceiling and separate animation pools");
    check(full.submitted_soft_cap < full.total_points,
          "resident total is distinct from the per-frame submitted soft cap");

    if (failures != 0) {
        std::cerr << failures << " Pivot 10 checks failed.\n";
        return EXIT_FAILURE;
    }
    std::cout << "All SignalCloud Pivot 10 motion, viewmodel, and point-pool checks passed.\n";
    return EXIT_SUCCESS;
}
