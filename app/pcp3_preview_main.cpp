#include "engine/math/mat4.hpp"
#include "engine/math/vec.hpp"
#include "engine/pcp3/pcp3_asset.hpp"
#include "engine/platform/video_backend.hpp"
#include "engine/render/gl_api.hpp"
#include "engine/render/point_renderer.hpp"

#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace {

namespace fs = std::filesystem;
using signalcloud::math::Vec3;

struct Options {
    signalcloud::platform::VideoBackend backend{signalcloud::platform::VideoBackend::automatic};
    fs::path root{fs::current_path()};
    fs::path asset;
    fs::path brush_commands;
    bool live{false};
    int width{1120};
    int height{760};
};

struct OrbitCamera {
    Vec3 center{};
    float yaw_degrees{-45.0F};
    float pitch_degrees{24.0F};
    float distance{12.0F};

    [[nodiscard]] Vec3 eye() const noexcept {
        constexpr float pi = 3.14159265358979323846F;
        const float yaw = yaw_degrees * pi / 180.0F;
        const float pitch = pitch_degrees * pi / 180.0F;
        const float horizontal = std::cos(pitch) * distance;
        return {center.x + std::cos(yaw) * horizontal,
                center.y + std::sin(pitch) * distance,
                center.z + std::sin(yaw) * horizontal};
    }

    [[nodiscard]] signalcloud::math::Mat4 view_projection(float aspect) const noexcept {
        constexpr float pi = 3.14159265358979323846F;
        const auto projection = signalcloud::math::perspective(58.0F * pi / 180.0F, aspect, 0.02F, 5000.0F);
        const auto view = signalcloud::math::look_at(eye(), center, {0.0F, 1.0F, 0.0F});
        return projection * view;
    }

    void frame(const signalcloud::pcp3::Asset& asset) noexcept {
        center = (asset.bounds_min + asset.bounds_max) * 0.5F;
        const Vec3 extent = asset.bounds_max - asset.bounds_min;
        const float radius = std::max({std::abs(extent.x), std::abs(extent.y), std::abs(extent.z), 1.0F}) * 0.5F;
        distance = std::clamp(radius * 3.2F, 2.0F, 2500.0F);
    }
};

bool create_context(SDL_Window* window, SDL_GLContext& context, int major, int minor) {
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, major);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, minor);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 24);
    context = SDL_GL_CreateContext(window);
    return context != nullptr;
}

Options parse_args(int argc, char** argv) {
    Options options;
    for (int index = 1; index < argc; ++index) {
        const std::string_view arg(argv[index]);
        const auto after = [&](std::string_view prefix) -> std::optional<std::string_view> {
            if (!arg.starts_with(prefix)) return std::nullopt;
            return arg.substr(prefix.size());
        };
        if (const auto root_value = after("--root=")) {
            options.root = fs::path(std::string(*root_value));
            continue;
        }
        if (const auto asset_value = after("--asset=")) {
            options.asset = fs::path(std::string(*asset_value));
            continue;
        }
        if (const auto brush_value = after("--brush-commands=")) {
            options.brush_commands = fs::path(std::string(*brush_value));
            continue;
        }
        if (const auto video_value = after("--video=")) {
            if (const auto parsed = signalcloud::platform::parse_video_backend(*video_value)) options.backend = *parsed;
            continue;
        }
        if (const auto resolution_value = after("--resolution=")) {
            const auto split = resolution_value->find('x');
            if (split != std::string_view::npos) {
                try {
                    options.width = std::max(320, std::stoi(std::string(resolution_value->substr(0, split))));
                    options.height = std::max(240, std::stoi(std::string(resolution_value->substr(split + 1))));
                } catch (...) {
                }
            }
            continue;
        }
        if (arg == "--live") options.live = true;
    }
    return options;
}


Vec3 brush_world_position(const OrbitCamera& camera, float mouse_x, float mouse_y, int width, int height) {
    constexpr float pi = 3.14159265358979323846F;
    const Vec3 eye = camera.eye();
    const Vec3 forward = signalcloud::math::normalize_or(camera.center - eye, {0.0F, 0.0F, -1.0F});
    const Vec3 right = signalcloud::math::normalize_or(signalcloud::math::cross(forward, {0.0F, 1.0F, 0.0F}), {1.0F, 0.0F, 0.0F});
    const Vec3 up = signalcloud::math::normalize_or(signalcloud::math::cross(right, forward), {0.0F, 1.0F, 0.0F});
    const float aspect = static_cast<float>(std::max(1, width)) / static_cast<float>(std::max(1, height));
    const float nx = (mouse_x / static_cast<float>(std::max(1, width)) - 0.5F) * 2.0F;
    const float ny = (0.5F - mouse_y / static_cast<float>(std::max(1, height))) * 2.0F;
    const float tan_half = std::tan(58.0F * pi / 360.0F);
    const Vec3 ray = signalcloud::math::normalize_or(
        forward + right * (nx * tan_half * aspect) + up * (ny * tan_half), forward);
    const float denominator = signalcloud::math::dot(ray, forward);
    if (std::abs(denominator) < 0.00001F) return camera.center;
    const float distance = signalcloud::math::dot(camera.center - eye, forward) / denominator;
    return eye + ray * std::max(0.0F, distance);
}

void append_brush_command(const fs::path& path, std::string_view action, const Vec3& point) {
    if (path.empty()) return;
    std::error_code error;
    fs::create_directories(path.parent_path(), error);
    std::ofstream output(path, std::ios::app);
    if (!output) return;
    output << std::fixed << std::setprecision(6)
           << "{\"action\":\"" << action << "\",\"x\":" << point.x
           << ",\"y\":" << point.y << ",\"z\":" << point.z << "}\n";
}

std::vector<signalcloud::render::PointGpu> fallback_axes() {
    std::vector<signalcloud::render::PointGpu> points;
    auto line = [&](Vec3 start, Vec3 end, float r, float g, float b) {
        constexpr int count = 61;
        for (int index = 0; index < count; ++index) {
            const float t = static_cast<float>(index) / static_cast<float>(count - 1);
            const Vec3 position = start + (end - start) * t;
            points.push_back({{position.x, position.y, position.z}, 2.8F,
                              {r, g, b, 1.0F}, {0.0F, 1.0F, 0.0F}, 1.0F});
        }
    };
    line({-3,0,0}, {3,0,0}, 0.95F, 0.18F, 0.18F);
    line({0,-3,0}, {0,3,0}, 0.18F, 0.95F, 0.30F);
    line({0,0,-3}, {0,0,3}, 0.18F, 0.45F, 0.98F);
    return points;
}

bool load_asset_points(const fs::path& path, signalcloud::pcp3::Asset& asset,
                       std::vector<signalcloud::render::PointGpu>& points,
                       std::string& error) {
    signalcloud::pcp3::Asset loaded;
    if (!signalcloud::pcp3::load_cloud(path, loaded, &error)) return false;
    asset = std::move(loaded);
    points = asset.render_points();
    if (points.empty()) points = fallback_axes();
    return true;
}

}  // namespace

int main(int argc, char** argv) {
    const Options options = parse_args(argc, argv);
    if (options.asset.empty()) {
        std::cerr << "Usage: almond_signal_pcp_preview --asset=/path/file.pcp3cloud [--live]\n";
        return 2;
    }
    SDL_SetAppMetadata("Point Cloud Paint++ Native Preview", "0.2.0-branch2", "io.digimancer3d.almondsignal.pcp3");
    if (const auto hint = signalcloud::platform::sdl_driver_hint(options.backend)) {
        SDL_SetHint(SDL_HINT_VIDEO_DRIVER, std::string(*hint).c_str());
    }
    if (!SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS)) {
        std::cerr << "SDL initialization failed: " << SDL_GetError() << '\n';
        return 3;
    }
    SDL_Window* window = SDL_CreateWindow(
        "Point Cloud Paint++ — SignalCloud Native Preview",
        options.width, options.height,
        SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY);
    if (!window) {
        std::cerr << SDL_GetError() << '\n';
        SDL_Quit();
        return 4;
    }
    SDL_GLContext context = nullptr;
    if (!create_context(window, context, 4, 3) && !create_context(window, context, 3, 3)) {
        std::cerr << SDL_GetError() << '\n';
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 5;
    }
    SDL_GL_MakeCurrent(window, context);
    SDL_GL_SetSwapInterval(1);

    signalcloud::render::GLApi gl;
    std::string error;
    if (!gl.load(&error)) {
        std::cerr << error << '\n';
        SDL_GL_DestroyContext(context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 6;
    }

    signalcloud::pcp3::Asset asset;
    std::vector<signalcloud::render::PointGpu> points;
    if (!load_asset_points(options.asset, asset, points, error)) {
        std::cerr << error << '\n';
        points = fallback_axes();
        asset.bounds_min = {-3,-3,-3};
        asset.bounds_max = {3,3,3};
    }

    signalcloud::render::PointRenderer renderer;
    if (!renderer.initialize_points(gl, points, &error)) {
        std::cerr << error << '\n';
        return 7;
    }

    OrbitCamera camera;
    camera.frame(asset);
    bool running = true;
    bool orbiting = false;
    bool panning = false;
    bool brush_mode = false;
    bool painting = false;
    bool erasing = false;
    std::uint64_t last_brush_emit = 0;
    float point_scale = 1.0F;
    float density_scale = 1.0F;
    fs::file_time_type last_write{};
    std::error_code time_error;
    if (fs::exists(options.asset)) last_write = fs::last_write_time(options.asset, time_error);
    std::uint64_t last_reload_check = SDL_GetTicks();
    const std::uint64_t start_ticks = SDL_GetTicks();

    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_QUIT) running = false;
            else if (event.type == SDL_EVENT_KEY_DOWN) {
                switch (event.key.scancode) {
                    case SDL_SCANCODE_ESCAPE: running = false; break;
                    case SDL_SCANCODE_F: camera.frame(asset); break;
                    case SDL_SCANCODE_B: {
                        brush_mode = !brush_mode;
                        painting = false;
                        erasing = false;
                        const std::string title = brush_mode
                            ? "Point Cloud Paint++ — NATIVE BRUSH MODE · left paint · right erase · middle orbit"
                            : "Point Cloud Paint++ — SignalCloud Native Preview";
                        SDL_SetWindowTitle(window, title.c_str());
                        break;
                    }
                    case SDL_SCANCODE_R: {
                        if (load_asset_points(options.asset, asset, points, error)) {
                            renderer.upload_points(points, &error);
                            camera.frame(asset);
                        }
                        break;
                    }
                    case SDL_SCANCODE_LEFTBRACKET: point_scale = std::max(0.1F, point_scale / 1.12F); break;
                    case SDL_SCANCODE_RIGHTBRACKET: point_scale = std::min(8.0F, point_scale * 1.12F); break;
                    case SDL_SCANCODE_MINUS: density_scale = std::max(0.1F, density_scale / 1.12F); break;
                    case SDL_SCANCODE_EQUALS: density_scale = std::min(8.0F, density_scale * 1.12F); break;
                    default: break;
                }
            } else if (event.type == SDL_EVENT_MOUSE_BUTTON_DOWN) {
                if (brush_mode) {
                    if (event.button.button == SDL_BUTTON_LEFT) painting = true;
                    if (event.button.button == SDL_BUTTON_RIGHT) erasing = true;
                    if (event.button.button == SDL_BUTTON_MIDDLE) orbiting = true;
                    if (painting || erasing) {
                        int pixel_width = 1;
                        int pixel_height = 1;
                        SDL_GetWindowSizeInPixels(window, &pixel_width, &pixel_height);
                        const Vec3 point = brush_world_position(camera, event.button.x, event.button.y, pixel_width, pixel_height);
                        append_brush_command(options.brush_commands, erasing ? "erase" : "paint", point);
                    }
                } else {
                    if (event.button.button == SDL_BUTTON_LEFT) orbiting = true;
                    if (event.button.button == SDL_BUTTON_MIDDLE || event.button.button == SDL_BUTTON_RIGHT) panning = true;
                }
            } else if (event.type == SDL_EVENT_MOUSE_BUTTON_UP) {
                if (brush_mode) {
                    if (event.button.button == SDL_BUTTON_LEFT) painting = false;
                    if (event.button.button == SDL_BUTTON_RIGHT) erasing = false;
                    if (event.button.button == SDL_BUTTON_MIDDLE) orbiting = false;
                } else {
                    if (event.button.button == SDL_BUTTON_LEFT) orbiting = false;
                    if (event.button.button == SDL_BUTTON_MIDDLE || event.button.button == SDL_BUTTON_RIGHT) panning = false;
                }
            } else if (event.type == SDL_EVENT_MOUSE_MOTION) {
                if (orbiting) {
                    camera.yaw_degrees += event.motion.xrel * 0.32F;
                    camera.pitch_degrees = std::clamp(camera.pitch_degrees - event.motion.yrel * 0.28F, -88.0F, 88.0F);
                }
                if (panning) {
                    const Vec3 eye = camera.eye();
                    const Vec3 forward = signalcloud::math::normalize_or(camera.center - eye, {0,0,-1});
                    const Vec3 right = signalcloud::math::normalize_or(signalcloud::math::cross(forward, {0,1,0}), {1,0,0});
                    const Vec3 up = signalcloud::math::normalize_or(signalcloud::math::cross(right, forward), {0,1,0});
                    const float scale = camera.distance * 0.0016F;
                    camera.center += right * (-event.motion.xrel * scale);
                    camera.center += up * (event.motion.yrel * scale);
                }
                if (brush_mode && (painting || erasing) && SDL_GetTicks() - last_brush_emit >= 50U) {
                    last_brush_emit = SDL_GetTicks();
                    int pixel_width = 1;
                    int pixel_height = 1;
                    SDL_GetWindowSizeInPixels(window, &pixel_width, &pixel_height);
                    const Vec3 point = brush_world_position(camera, event.motion.x, event.motion.y, pixel_width, pixel_height);
                    append_brush_command(options.brush_commands, erasing ? "erase" : "paint", point);
                }
            } else if (event.type == SDL_EVENT_MOUSE_WHEEL) {
                camera.distance = std::clamp(camera.distance * std::pow(0.88F, event.wheel.y), 0.15F, 5000.0F);
            }
        }

        const bool* keys = SDL_GetKeyboardState(nullptr);
        const float pan_step = camera.distance * 0.012F;
        const Vec3 eye = camera.eye();
        const Vec3 forward = signalcloud::math::normalize_or(camera.center - eye, {0,0,-1});
        const Vec3 right = signalcloud::math::normalize_or(signalcloud::math::cross(forward, {0,1,0}), {1,0,0});
        if (keys[SDL_SCANCODE_W]) camera.center += forward * pan_step;
        if (keys[SDL_SCANCODE_S]) camera.center += forward * (-pan_step);
        if (keys[SDL_SCANCODE_A]) camera.center += right * (-pan_step);
        if (keys[SDL_SCANCODE_D]) camera.center += right * pan_step;
        if (keys[SDL_SCANCODE_Q]) camera.center.y -= pan_step;
        if (keys[SDL_SCANCODE_E]) camera.center.y += pan_step;

        if (options.live && SDL_GetTicks() - last_reload_check > 350U) {
            last_reload_check = SDL_GetTicks();
            std::error_code current_error;
            const auto current = fs::last_write_time(options.asset, current_error);
            if (!current_error && current != last_write) {
                last_write = current;
                if (load_asset_points(options.asset, asset, points, error)) {
                    renderer.upload_points(points, &error);
                    std::string title = "Point Cloud Paint++ — " + std::to_string(points.size()) + " points — LIVE";
                    SDL_SetWindowTitle(window, title.c_str());
                }
            }
        }

        int width = 1;
        int height = 1;
        SDL_GetWindowSizeInPixels(window, &width, &height);
        gl.viewport(0, 0, width, height);
        gl.clear_color(0.018F, 0.022F, 0.028F, 1.0F);
        gl.clear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        const float time = static_cast<float>(SDL_GetTicks() - start_ticks) / 1000.0F;
        renderer.render(camera.view_projection(static_cast<float>(width) / static_cast<float>(std::max(1, height))),
                        time, 0.0F, false, false, point_scale, density_scale, 1.0F,
                        {}, 0.0F, 0.0F,
                        {}, 0.0F, 0.0F, false,
                        camera.center + Vec3{0.0F, camera.distance * 0.5F, 0.0F}, camera.distance * 1.2F, 0.75F,
                        {}, 0.0F, 0.0F,
                        {}, 0.0F, 0.0F,
                        width, height);
        SDL_GL_SwapWindow(window);
    }

    renderer.shutdown();
    SDL_GL_DestroyContext(context);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
