#pragma once

#include <cstdint>
#include <string_view>
#include <vector>

namespace signalcloud::render {

struct SystemPointBudget {
    std::string_view name;
    std::uint32_t total_points;
    std::uint32_t environment_points;
    std::uint32_t hostile_points;
    std::uint32_t player_viewmodel_points;
    std::uint32_t friendly_npc_points;
    std::uint32_t object_effect_points;
    std::uint32_t submitted_soft_cap;
};

[[nodiscard]] const std::vector<SystemPointBudget>& system_point_budgets();
[[nodiscard]] const SystemPointBudget& system_point_budget_for_total(std::uint32_t total_points);
[[nodiscard]] double point_buffer_mebibytes(std::uint32_t points, std::uint32_t bytes_per_point = 48U) noexcept;
[[nodiscard]] bool point_budget_is_balanced(const SystemPointBudget& budget) noexcept;

}  // namespace signalcloud::render
