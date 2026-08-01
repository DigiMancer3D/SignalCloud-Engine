#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace signalcloud::render {

struct PointMemoryEstimate {
    std::uint64_t points{0};
    std::uint64_t bytes_single{0};
    std::uint64_t bytes_triple{0};
};

[[nodiscard]] PointMemoryEstimate estimate_point_memory(std::uint64_t point_count,
                                                        std::size_t bytes_per_point = 48);
[[nodiscard]] std::vector<PointMemoryEstimate> standard_point_presets();
[[nodiscard]] std::string format_mebibytes(std::uint64_t bytes);

}  // namespace signalcloud::render
