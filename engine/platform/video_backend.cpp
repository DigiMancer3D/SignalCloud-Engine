#include "engine/platform/video_backend.hpp"

#include <algorithm>
#include <cctype>

namespace signalcloud::platform {

std::optional<VideoBackend> parse_video_backend(std::string_view value) {
    std::string normalized(value);
    std::transform(normalized.begin(), normalized.end(), normalized.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    if (normalized == "auto" || normalized == "automatic") return VideoBackend::automatic;
    if (normalized == "x11" || normalized == "xwayland") return VideoBackend::x11;
    if (normalized == "wayland") return VideoBackend::wayland;
    return std::nullopt;
}

std::string_view video_backend_name(VideoBackend backend) noexcept {
    switch (backend) {
        case VideoBackend::automatic: return "automatic";
        case VideoBackend::x11: return "x11";
        case VideoBackend::wayland: return "wayland";
    }
    return "automatic";
}

std::optional<std::string_view> sdl_driver_hint(VideoBackend backend) noexcept {
    switch (backend) {
        case VideoBackend::automatic: return std::nullopt;
        case VideoBackend::x11: return "x11";
        case VideoBackend::wayland: return "wayland";
    }
    return std::nullopt;
}

}  // namespace signalcloud::platform
