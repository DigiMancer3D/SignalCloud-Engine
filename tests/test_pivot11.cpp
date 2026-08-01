#include "engine/economy/economy_system.hpp"
#include "engine/render/room_visibility.hpp"
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
        if (!std::isfinite(point.radius)) return false;
    }
    return true;
}
}  // namespace

int main() {
    using namespace signalcloud;
    const auto seed = world::mix_seed(0xA11D0A1ULL, {0, 0, 0}, 4);
    const auto level = world::LiminalLevel::make_pivot11_scavenging(seed);
    check(level.areas().size() == 26U, "Pivot 11 adds one scavenger room");
    check(level.portals().size() == 23U, "Pivot 11 adds a two-way scavenger portal pair");
    check(level.zone_name(level.economy_lab_spawn()) == "Scavenger Exchange",
          "economy quick-access spawn is inside the exchange");

    auto economy = economy::EconomySystem::make_pivot11();
    check(economy.pickups().size() == 5U, "five low-rank pickups seed the economy lab");
    const auto visuals = economy.build_visual_points(0.5F, "Scavenger Exchange");
    check(finite_points(visuals), "pickup and terminal visuals remain finite");
    check(economy.build_visual_points(0.5F, "Reception Tape").empty(),
          "economy overlay sleeps outside its active room");

    auto pickup_a = economy.interact({1052.5F, 1.72F, -169.0F}, "Scavenger Exchange", 1);
    auto pickup_b = economy.interact({1057.0F, 1.72F, -146.5F}, "Scavenger Exchange", 1);
    check(pickup_a.success && pickup_b.success, "scrap pickups enter inventory");
    check(economy.quantity(economy::ItemKind::signal_scrap) == 5U,
          "scrap stacks deterministically");
    check(economy.carried_weight() > 6.0F, "inventory reports physical carry weight");

    economy.add_claimed_proof(2U);
    const auto balance_before = economy.xar_balance();
    auto sold = economy.interact({1062.0F, 1.72F, -160.0F}, "Scavenger Exchange", 1);
    check(sold.success && sold.xar_delta == 34,
          "scavenger sells five scrap and two proofs for deterministic XAR");
    check(economy.xar_balance() == balance_before + 34,
          "local XAR ledger applies the exchange atomically");
    check(economy.sold_proofs() == 2U, "sold proof count is tracked separately");

    auto bought = economy.interact({1073.0F, 1.72F, -150.0F}, "Scavenger Exchange", 2);
    check(bought.success && economy.quantity(economy::ItemKind::almond_water) == 1U,
          "vending belt slot two buys Almond Water");
    const float wet_before = economy.sabs_wetness_seconds();
    auto used = economy.use_belt_item(2);
    check(used.success && used.health_restored > 0.0F && used.oxygen_restored > 0.0F,
          "Almond Water returns health, oxygen, and SABS wetness effects");
    check(economy.sabs_wetness_seconds() > wet_before,
          "Almond Water dampens SABS contacts");

    render::RoomVisibilitySelection selection;
    selection.ranges = {{0U, 900U, {}}, {900U, 700U, {}}, {1600U, 500U, {}}};
    selection.submitted_points = 2100U;
    selection.submitted_ranges = selection.ranges.size();
    render::enforce_submitted_point_cap(selection, 1200U);
    check(selection.cap_applied && selection.submitted_points == 1200U,
          "submitted-point governor enforces its hard cap");
    check(selection.ranges.size() == 2U && selection.ranges.back().count == 300U,
          "governor preserves priority order and trims only the last admitted range");
    check(selection.points_trimmed == 900U,
          "governor reports the prevented submission count");

    if (failures != 0) {
        std::cerr << failures << " Pivot 11 checks failed.\n";
        return EXIT_FAILURE;
    }
    std::cout << "All SignalCloud Pivot 11 scavenging, exchange, and submission-governor checks passed.\n";
    return EXIT_SUCCESS;
}
