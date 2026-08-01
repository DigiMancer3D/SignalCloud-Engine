#include "engine/render/memory_budget.hpp"

#include <iomanip>
#include <sstream>

namespace signalcloud::render {

PointMemoryEstimate estimate_point_memory(std::uint64_t point_count, std::size_t bytes_per_point) {
    const auto single = point_count * static_cast<std::uint64_t>(bytes_per_point);
    return {point_count, single, single * 3U};
}

std::vector<PointMemoryEstimate> standard_point_presets() {
    return {estimate_point_memory(100'000), estimate_point_memory(500'000),
            estimate_point_memory(1'000'000), estimate_point_memory(2'000'000),
            estimate_point_memory(3'000'000), estimate_point_memory(4'000'000),
            estimate_point_memory(8'000'000)};
}

std::string format_mebibytes(std::uint64_t bytes) {
    std::ostringstream output;
    output << std::fixed << std::setprecision(2)
           << static_cast<double>(bytes) / (1024.0 * 1024.0) << " MiB";
    return output.str();
}

}  // namespace signalcloud::render
