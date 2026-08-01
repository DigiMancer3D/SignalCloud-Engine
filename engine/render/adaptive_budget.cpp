#include "engine/render/adaptive_budget.hpp"

#include <algorithm>
#include <cctype>

namespace signalcloud::render {
namespace {
std::string lower(std::string_view value) {
    std::string result(value);
    std::transform(result.begin(), result.end(), result.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return result;
}
bool contains(const std::string& value, std::string_view token) {
    return value.find(token) != std::string::npos;
}
}

AdaptivePointBudget recommend_point_budget(std::string_view vendor, std::string_view renderer,
                                            int gl_major, int gl_minor) {
    const std::string combined = lower(std::string(vendor) + " " + std::string(renderer));
    if (contains(combined, "llvmpipe") || contains(combined, "softpipe") || contains(combined, "software")) {
        return {100'000U, "software-safe", "Software rasterizer detected; use the smallest gameplay cloud."};
    }
    if (gl_major < 3 || (gl_major == 3 && gl_minor < 3)) {
        return {100'000U, "legacy-safe", "OpenGL capability is below the compatibility target."};
    }
    if (contains(combined, "intel") || contains(combined, "uhd") || contains(combined, "iris")) {
        return {8'000'000U, "integrated-adaptive-8m",
                "Verified Intel/Mesa profile: Pivot 12 a5 sustained the JAM atlas, traversal, and animated threats at the 8M resident tier. Pivot 13 starts at 8M and defers any fallback until a protected room."};
    }
    if (contains(combined, "nvidia") || contains(combined, "geforce") ||
        contains(combined, "radeon") || contains(combined, "amd")) {
        return {2'000'000U, "discrete-balanced", "Discrete graphics use the established 2M compatibility start until a device-specific residency profile is verified."};
    }
    return {500'000U, "compatibility", "Unknown GPU class; begin at the conservative 500K tier."};
}

}  // namespace signalcloud::render
