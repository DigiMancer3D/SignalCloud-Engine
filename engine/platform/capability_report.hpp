#pragma once

#include "engine/render/gl_api.hpp"

#include <filesystem>
#include <string>
#include <string_view>

namespace signalcloud::platform {

struct CapabilityReport {
    std::string text;
    std::string vendor;
    std::string renderer;
    std::string version;
    int gl_major{0};
    int gl_minor{0};
    bool compute_shader{false};
    bool shader_storage{false};
    bool persistent_mapping{false};
    bool int64_atomics{false};
    bool timer_query{false};
};

[[nodiscard]] CapabilityReport collect_capability_report(const render::GLApi& gl,
                                                          std::string_view video_driver);
bool write_capability_report(const CapabilityReport& report,
                             const std::filesystem::path& path,
                             std::string* error = nullptr);

}  // namespace signalcloud::platform
