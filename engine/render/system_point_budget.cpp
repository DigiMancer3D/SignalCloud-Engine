#include "engine/render/system_point_budget.hpp"

#include <algorithm>

namespace signalcloud::render {
namespace {
const std::vector<SystemPointBudget> kBudgets{
    {"LOWEST",       4'000'000U, 2'600'000U,   500'000U, 100'000U,  350'000U,  450'000U, 1'300'000U},
    {"LOW",          6'000'000U, 3'800'000U,   750'000U, 150'000U,  550'000U,  750'000U, 1'650'000U},
    {"MEDIUM",       8'000'000U, 5'000'000U, 1'000'000U, 250'000U,  750'000U,1'000'000U, 2'000'000U},
    {"UPPER-MEDIUM",10'000'000U, 6'000'000U, 1'350'000U, 350'000U,  950'000U,1'350'000U, 2'300'000U},
    {"REDUCED+",    12'000'000U, 7'000'000U, 1'700'000U, 500'000U,1'150'000U,1'650'000U, 2'600'000U},
    {"REDUCED",     14'000'000U, 7'800'000U, 2'100'000U, 650'000U,1'450'000U,2'000'000U, 2'900'000U},
    {"NORMAL",      16'000'000U, 8'500'000U, 2'600'000U, 800'000U,1'750'000U,2'350'000U, 3'200'000U},
    {"LARGE",       18'000'000U, 9'000'000U, 3'200'000U, 900'000U,2'100'000U,2'800'000U, 3'500'000U},
    {"FULL",        20'000'000U, 9'500'000U, 4'000'000U,1'000'000U,2'500'000U,3'000'000U, 3'800'000U},
    {"ULTRA FULL",  24'000'000U,10'000'000U, 5'000'000U,1'400'000U,3'200'000U,4'400'000U, 4'400'000U},
    {"FANCY FULL",  26'000'000U,10'000'000U, 6'000'000U,1'600'000U,4'000'000U,4'400'000U, 4'800'000U},
    {"UBER FANCY",  32'000'000U,10'000'000U, 8'000'000U,2'000'000U,5'000'000U,7'000'000U, 5'800'000U},
};
}

const std::vector<SystemPointBudget>& system_point_budgets() { return kBudgets; }

const SystemPointBudget& system_point_budget_for_total(std::uint32_t total_points) {
    auto it = std::lower_bound(kBudgets.begin(), kBudgets.end(), total_points,
        [](const SystemPointBudget& budget, std::uint32_t value) {
            return budget.total_points < value;
        });
    if (it == kBudgets.end()) return kBudgets.back();
    return *it;
}

double point_buffer_mebibytes(std::uint32_t points, std::uint32_t bytes_per_point) noexcept {
    return static_cast<double>(points) * static_cast<double>(bytes_per_point) / (1024.0 * 1024.0);
}

bool point_budget_is_balanced(const SystemPointBudget& budget) noexcept {
    const std::uint64_t sum = static_cast<std::uint64_t>(budget.environment_points) +
        budget.hostile_points + budget.player_viewmodel_points +
        budget.friendly_npc_points + budget.object_effect_points;
    return sum == budget.total_points && budget.submitted_soft_cap <= budget.total_points;
}

}  // namespace signalcloud::render
