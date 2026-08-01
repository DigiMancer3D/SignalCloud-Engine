#pragma once

#include <optional>
#include <string>
#include <string_view>

namespace signalcloud::platform {

enum class VideoBackend { automatic, x11, wayland };

[[nodiscard]] std::optional<VideoBackend> parse_video_backend(std::string_view value);
[[nodiscard]] std::string_view video_backend_name(VideoBackend backend) noexcept;
[[nodiscard]] std::optional<std::string_view> sdl_driver_hint(VideoBackend backend) noexcept;

}  // namespace signalcloud::platform
