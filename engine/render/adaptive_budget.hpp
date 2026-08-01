#pragma once

#include <cstdint>
#include <string>
#include <string_view>

namespace signalcloud::render {

struct AdaptivePointBudget {
    std::uint32_t gameplay_points{500'000U};
    std::string profile{"compatibility"};
    std::string rationale;
};

[[nodiscard]] AdaptivePointBudget recommend_point_budget(std::string_view vendor,
                                                          std::string_view renderer,
                                                          int gl_major,
                                                          int gl_minor);

}  // namespace signalcloud::render
