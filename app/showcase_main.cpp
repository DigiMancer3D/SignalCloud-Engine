#include "engine/math/mat4.hpp"
#include "engine/math/vec.hpp"
#include "engine/pcp3/pcp3_asset.hpp"
#include "engine/physics/showcase_runtime.hpp"
#include "engine/physics/showcase_visualization.hpp"
#include "engine/platform/video_backend.hpp"
#include "engine/render/gl_api.hpp"
#include "engine/render/point_renderer.hpp"
#include "engine/scfont/scfont.hpp"
#include "engine/scfont/text_point_adapter.hpp"
#include "engine/ui/showcase_info_overlay.hpp"

#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>

#include <algorithm>
#include <stdexcept>
#include <cstdint>
#include <cctype>
#include <array>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

namespace {
namespace fs = std::filesystem;
using signalcloud::math::Vec3;

struct Options {
    signalcloud::platform::VideoBackend backend{signalcloud::platform::VideoBackend::automatic};
    fs::path asset;
    fs::path physics;
    fs::path visualization;
    fs::path snapshot_dir;
    signalcloud::physics::ShowcaseTest test{signalcloud::physics::ShowcaseTest::drop};
    signalcloud::physics::ShowcaseVisualizationOptions visual{};
    std::string playbook_id;
    int width{1280};
    int height{820};
};

struct OrbitCamera {
    Vec3 center{0.0F, 1.3F, 0.0F};
    float yaw_degrees{-42.0F};
    float pitch_degrees{22.0F};
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
        return signalcloud::math::perspective(58.0F * pi / 180.0F, aspect, 0.02F, 4000.0F) *
               signalcloud::math::look_at(eye(), center, {0.0F, 1.0F, 0.0F});
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

bool truthy(std::string_view value) noexcept {
    return value == "1" || value == "true" || value == "yes" || value == "on";
}

std::string read_text(const fs::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) return {};
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return buffer.str();
}

std::optional<std::size_t> json_value_start(std::string_view text, std::string_view key) {
    const std::string quoted = "\"" + std::string(key) + "\"";
    std::size_t position = text.find(quoted);
    if (position == std::string_view::npos) return std::nullopt;
    position = text.find(':', position + quoted.size());
    if (position == std::string_view::npos) return std::nullopt;
    ++position;
    while (position < text.size() && std::isspace(static_cast<unsigned char>(text[position]))) ++position;
    return position;
}

std::optional<std::string> json_string(std::string_view text, std::string_view key) {
    const auto start = json_value_start(text, key);
    if (!start || *start >= text.size() || text[*start] != '"') return std::nullopt;
    const std::size_t end = text.find('"', *start + 1U);
    if (end == std::string_view::npos) return std::nullopt;
    return std::string(text.substr(*start + 1U, end - *start - 1U));
}

std::optional<float> json_float(std::string_view text, std::string_view key) {
    const auto start = json_value_start(text, key);
    if (!start) return std::nullopt;
    std::size_t end = *start;
    while (end < text.size()) {
        const char c = text[end];
        if (!(std::isdigit(static_cast<unsigned char>(c)) || c == '-' || c == '+' ||
              c == '.' || c == 'e' || c == 'E')) break;
        ++end;
    }
    if (end == *start) return std::nullopt;
    try {
        const float value = std::stof(std::string(text.substr(*start, end - *start)));
        return std::isfinite(value) ? std::optional(value) : std::nullopt;
    } catch (...) {
        return std::nullopt;
    }
}

std::optional<bool> json_bool(std::string_view text, std::string_view key) {
    const auto start = json_value_start(text, key);
    if (!start) return std::nullopt;
    if (text.substr(*start, 4U) == "true") return true;
    if (text.substr(*start, 5U) == "false") return false;
    return std::nullopt;
}

void apply_visualization_file(Options& options) {
    if (options.visualization.empty()) return;
    const std::string text = read_text(options.visualization);
    if (text.empty()) return;
    if (const auto value = json_string(text, "view_mode")) {
        options.visual.view_mode = signalcloud::physics::parse_showcase_view_mode(*value);
    }
    if (const auto value = json_float(text, "lod_fraction")) options.visual.lod_fraction = *value;
    if (const auto value = json_float(text, "point_scale")) options.visual.point_scale = *value;
    if (const auto value = json_bool(text, "collision_outline")) options.visual.collision_outline = *value;
    if (const auto value = json_bool(text, "actor_preview")) options.visual.actor_preview = *value;
    if (const auto value = json_string(text, "playbook_id")) options.playbook_id = *value;
}

Options parse_args(int argc, char** argv) {
    Options options;
    std::vector<std::string> arguments;
    arguments.reserve(static_cast<std::size_t>(std::max(0, argc - 1)));
    for (int index = 1; index < argc; ++index) arguments.emplace_back(argv[index]);
    for (const std::string& storage : arguments) {
        const std::string_view argument(storage);
        const auto after = [&](std::string_view prefix) -> std::optional<std::string_view> {
            return argument.starts_with(prefix) ? std::optional(argument.substr(prefix.size())) : std::nullopt;
        };
        if (const auto asset_value = after("--asset=")) options.asset = fs::path(std::string(*asset_value));
        else if (const auto physics_value = after("--physics=")) options.physics = fs::path(std::string(*physics_value));
        else if (const auto visualization_value = after("--visualization=")) options.visualization = fs::path(std::string(*visualization_value));
        else if (const auto snapshot_value = after("--snapshot-dir=")) options.snapshot_dir = fs::path(std::string(*snapshot_value));
        else if (const auto test_value = after("--test=")) options.test = signalcloud::physics::parse_showcase_test(*test_value);
        else if (const auto view_value = after("--view=")) options.visual.view_mode = signalcloud::physics::parse_showcase_view_mode(*view_value);
        else if (const auto lod_value = after("--lod=")) {
            try { options.visual.lod_fraction = std::stof(std::string(*lod_value)); } catch (...) {}
        } else if (const auto scale_value = after("--point-scale=")) {
            try { options.visual.point_scale = std::stof(std::string(*scale_value)); } catch (...) {}
        } else if (const auto collision_value = after("--collision=")) options.visual.collision_outline = truthy(*collision_value);
        else if (const auto actor_value = after("--actor=")) options.visual.actor_preview = truthy(*actor_value);
        else if (const auto playbook_value = after("--playbook=")) options.playbook_id = std::string(*playbook_value);
        else if (const auto video_value = after("--video=")) {
            if (const auto parsed = signalcloud::platform::parse_video_backend(*video_value)) options.backend = *parsed;
        }
    }
    apply_visualization_file(options);
    // Explicit CLI values are applied a second time so they override the sidecar.
    for (const std::string& storage : arguments) {
        const std::string_view argument(storage);
        const auto after = [&](std::string_view prefix) -> std::optional<std::string_view> {
            return argument.starts_with(prefix) ? std::optional(argument.substr(prefix.size())) : std::nullopt;
        };
        if (const auto view_override = after("--view=")) options.visual.view_mode = signalcloud::physics::parse_showcase_view_mode(*view_override);
        else if (const auto lod_override = after("--lod=")) { try { options.visual.lod_fraction = std::stof(std::string(*lod_override)); } catch (...) {} }
        else if (const auto scale_override = after("--point-scale=")) { try { options.visual.point_scale = std::stof(std::string(*scale_override)); } catch (...) {} }
        else if (const auto collision_override = after("--collision=")) options.visual.collision_outline = truthy(*collision_override);
        else if (const auto actor_override = after("--actor=")) options.visual.actor_preview = truthy(*actor_override);
        else if (const auto playbook_override = after("--playbook=")) options.playbook_id = std::string(*playbook_override);
    }
    options.visual.lod_fraction = std::clamp(options.visual.lod_fraction, 0.01F, 1.0F);
    options.visual.point_scale = std::clamp(options.visual.point_scale, 0.25F, 4.0F);
    return options;
}

fs::path find_project_root(fs::path start) {
    start = fs::absolute(start);
    if (fs::is_regular_file(start)) start = start.parent_path();
    for (fs::path current = start; !current.empty(); current = current.parent_path()) {
        if (fs::exists(current / "CMakeLists.txt") && fs::exists(current / "content")) return current;
        if (current == current.root_path()) break;
    }
    return {};
}

void fit_profile_to_bounds(signalcloud::physics::PhysicsProfile& profile,
                           const signalcloud::physics::ShowcaseBounds& bounds) {
    if (!bounds.valid) return;
    profile.collision_half_extents = bounds.half_extents;
    profile.collision_radius = std::max({bounds.half_extents.x, bounds.half_extents.y, bounds.half_extents.z});
    if (profile.shape == "capsule") {
        profile.collision_radius = std::max(bounds.half_extents.x, bounds.half_extents.z);
        profile.collision_half_extents.y = std::max(0.02F, bounds.half_extents.y - profile.collision_radius);
    }
    profile = signalcloud::physics::normalize_profile(profile);
}

float support_height(const signalcloud::physics::PhysicsProfile& profile) noexcept {
    return signalcloud::physics::showcase_support_height(profile);
}

void reset_test(signalcloud::physics::ShowcaseTest test,
                const signalcloud::physics::PhysicsProfile& profile,
                signalcloud::physics::ShowcaseState& state) {
    signalcloud::physics::reset_showcase_state(test, profile, state);
}

float loop_seconds(signalcloud::physics::ShowcaseTest test) noexcept {
    switch (test) {
        case signalcloud::physics::ShowcaseTest::drop: return 4.0F;
        case signalcloud::physics::ShowcaseTest::bounce: return 5.0F;
        case signalcloud::physics::ShowcaseTest::slide: return 5.5F;
        case signalcloud::physics::ShowcaseTest::throw_arc: return 5.5F;
        case signalcloud::physics::ShowcaseTest::break_test: return 4.0F;
    }
    return 5.0F;
}

std::string status_text(signalcloud::physics::ShowcaseTest test,
                        const signalcloud::physics::ShowcaseVisualizationOptions& visual,
                        bool paused, bool follow_camera, bool auto_loop, bool show_help,
                        std::size_t source_points, std::size_t visible_points,
                        std::string_view playbook) {
    std::ostringstream text;
    text << "SHOWCASE A7a2r2  " << signalcloud::physics::showcase_test_name(test)
         << (paused ? "  PAUSED" : "  RUNNING") << '\n';
    text << "VIEW " << signalcloud::physics::showcase_view_mode_name(visual.view_mode)
         << "  LOD " << static_cast<int>(std::lround(visual.lod_fraction * 100.0F)) << "%"
         << "  POINTS " << visible_points << '/' << source_points << '\n';
    text << "COLLISION " << (visual.collision_outline ? "ON" : "OFF")
         << "  ACTOR " << (visual.actor_preview ? "ON" : "OFF")
         << "  FOLLOW " << (follow_camera ? "ON" : "OFF")
         << "  LOOP " << (auto_loop ? "ON" : "OFF");
    if (!playbook.empty()) text << "  PB " << playbook.substr(0U, 28U);
    if (show_help) {
        text << "\n1-5 TEST  C COLLISION  L LOD  V VIEW  P ACTOR"
             << "\nT FOLLOW  O LOOP  F/HOME RESET  S SNAPSHOT  I INFO";
    }
    return text.str();
}

void append_status_billboard(std::vector<signalcloud::render::PointGpu>& points,
                             const signalcloud::font::Font* font,
                             std::string_view text, Vec3 camera_position,
                             Vec3 anchor) {
    if (font == nullptr) return;
    signalcloud::font::TextPointStyle style;
    style.point_radius = 0.002F;
    style.opacity = 1.0F;
    style.tint = {0.62F, 1.0F, 0.94F};
    style.replace_rgb = false;
    signalcloud::font::append_constant_apparent_billboard(
        points, *font, text, anchor, camera_position, 0.38F, style, false, 8'000U);
}

bool write_snapshot_ppm(signalcloud::render::GLApi& gl, const fs::path& directory,
                        int width, int height, std::uint64_t ticks,
                        fs::path& written, std::string& error) {
    if (!gl.read_pixels || !gl.pixel_store_i || width <= 0 || height <= 0) {
        error = "OpenGL screenshot entry points are unavailable";
        return false;
    }
    try {
        fs::create_directories(directory);
        written = directory / ("showcase_" + std::to_string(ticks) + ".ppm");
        std::vector<unsigned char> pixels(static_cast<std::size_t>(width) * static_cast<std::size_t>(height) * 3U);
        gl.pixel_store_i(GL_PACK_ALIGNMENT, 1);
        gl.read_pixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE, pixels.data());
        std::ofstream output(written, std::ios::binary);
        if (!output) throw std::runtime_error("unable to open snapshot output");
        output << "P6\n" << width << ' ' << height << "\n255\n";
        const std::size_t row_bytes = static_cast<std::size_t>(width) * 3U;
        for (int row = height - 1; row >= 0; --row) {
            output.write(reinterpret_cast<const char*>(pixels.data() + static_cast<std::size_t>(row) * row_bytes),
                         static_cast<std::streamsize>(row_bytes));
        }
        return static_cast<bool>(output);
    } catch (const std::exception& exception) {
        error = exception.what();
        return false;
    }
}

void set_title(SDL_Window* window, const signalcloud::physics::PhysicsProfile& profile,
               signalcloud::physics::ShowcaseTest test,
               const signalcloud::physics::ShowcaseVisualizationOptions& visual,
               const signalcloud::physics::ShowcaseState& state,
               bool paused, bool follow_camera, bool auto_loop, bool status_overlay,
               std::string_view notice) {
    std::ostringstream title;
    title << "SignalCloud Showcase A7a2r2 — " << signalcloud::physics::showcase_test_name(test)
          << (paused ? " · PAUSED" : " · RUNNING")
          << " · " << signalcloud::physics::showcase_view_mode_name(visual.view_mode)
          << " · LOD " << static_cast<int>(std::lround(visual.lod_fraction * 100.0F)) << '%'
          << " · collision " << (visual.collision_outline ? "ON" : "OFF")
          << " · actor " << (visual.actor_preview ? "ON" : "OFF")
          << " · follow " << (follow_camera ? "ON" : "OFF")
          << " · loop " << (auto_loop ? "ON" : "OFF")
          << " · info " << (status_overlay ? "UI" : "WORLD")
          << " · shape " << profile.shape
          << " · bounces " << state.bounce_count;
    if (state.broken) title << " · BREAK THRESHOLD";
    if (!notice.empty()) title << " · " << notice;
    SDL_SetWindowTitle(window, title.str().c_str());
}

signalcloud::physics::ShowcaseViewMode next_view(signalcloud::physics::ShowcaseViewMode current) noexcept {
    using Mode = signalcloud::physics::ShowcaseViewMode;
    switch (current) {
        case Mode::source: return Mode::density;
        case Mode::density: return Mode::material;
        case Mode::material: return Mode::light;
        case Mode::light: return Mode::source;
    }
    return Mode::source;
}

float next_lod(float current) noexcept {
    if (current > 0.75F) return 0.50F;
    if (current > 0.375F) return 0.25F;
    if (current > 0.1875F) return 0.125F;
    return 1.0F;
}

}  // namespace

int main(int argc, char** argv) {
    Options options = parse_args(argc, argv);
    if (options.asset.empty() || options.physics.empty()) {
        std::cerr << "Usage: almond_signal_showcase --asset=file.pcp3cloud --physics=file.scphysics [--visualization=file.scshowcase]\n";
        return 2;
    }

    signalcloud::pcp3::Asset asset;
    std::string error;
    if (!signalcloud::pcp3::load_cloud(options.asset, asset, &error)) {
        std::cerr << error << '\n';
        return 3;
    }
    const std::vector<signalcloud::render::PointGpu> base_points = asset.render_points();
    if (base_points.empty()) {
        std::cerr << "Showcase asset has no renderable points\n";
        return 4;
    }
    const auto bounds = signalcloud::physics::showcase_bounds(base_points);
    signalcloud::physics::PhysicsProfile profile;
    if (!signalcloud::physics::load_physics_profile(options.physics, profile, &error)) {
        std::cerr << error << '\n';
        return 5;
    }
    fit_profile_to_bounds(profile, bounds);

    const fs::path project_root = find_project_root(options.asset);
    if (options.snapshot_dir.empty()) {
        options.snapshot_dir = project_root.empty() ? fs::path("showcase_snapshots") :
                               project_root / "user_data" / "showcase_snapshots";
    }
    std::optional<signalcloud::font::Font> status_font;
    if (!project_root.empty()) {
        try {
            status_font = signalcloud::font::load_scfont(
                project_root / "content/core/fonts/terminal_00/Terminal_00.scfont");
        } catch (...) {
            status_font.reset();
        }
    }

    SDL_SetAppMetadata("SignalCloud 3D Environment & Physics Showcase", "0.7.2-a2r2", "io.digimancer3d.signalcloud.showcase");
    if (const auto hint = signalcloud::platform::sdl_driver_hint(options.backend)) {
        SDL_SetHint(SDL_HINT_VIDEO_DRIVER, std::string(*hint).c_str());
    }
    if (!SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS)) {
        std::cerr << SDL_GetError() << '\n';
        return 6;
    }
    SDL_Window* window = SDL_CreateWindow(
        "SignalCloud Showcase A7a2r2", options.width, options.height,
        SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY);
    if (!window) {
        std::cerr << SDL_GetError() << '\n';
        SDL_Quit();
        return 7;
    }
    SDL_GLContext context = nullptr;
    if (!create_context(window, context, 4, 3) && !create_context(window, context, 3, 3)) {
        std::cerr << SDL_GetError() << '\n';
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 8;
    }
    SDL_GL_MakeCurrent(window, context);
    SDL_GL_SetSwapInterval(1);

    signalcloud::render::GLApi gl;
    if (!gl.load(&error)) {
        std::cerr << error << '\n';
        SDL_GL_DestroyContext(context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 9;
    }

    signalcloud::physics::ShowcaseTest active_test = options.test;
    signalcloud::physics::ShowcaseState state;
    reset_test(active_test, profile, state);
    signalcloud::render::PointRenderer renderer;
    OrbitCamera camera;
    camera.distance = std::clamp(std::max(15.0F, bounds.radius * 4.4F + 4.0F), 15.0F, 80.0F);
    camera.center = {0.0F, 2.2F, 0.0F};

    std::vector<signalcloud::render::PointGpu> points =
        signalcloud::physics::build_showcase_frame_points(base_points, bounds, profile, state, options.visual, 0.0F);
    append_status_billboard(points, status_font ? &*status_font : nullptr,
        status_text(active_test, options.visual, false, false, true, true, base_points.size(),
                    signalcloud::physics::showcase_lod_count(base_points.size(), options.visual.lod_fraction),
                    options.playbook_id), camera.eye(), {0.0F, std::max(4.2F, support_height(profile) + 3.0F), 2.6F});
    if (!renderer.initialize_points(gl, points, &error)) {
        std::cerr << error << '\n';
        SDL_GL_DestroyContext(context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 10;
    }

    bool running = true;
    bool paused = false;
    bool orbiting = false;
    bool follow_camera = false;
    bool auto_loop = true;
    bool show_help = true;
    bool status_overlay = false;
    bool snapshot_requested = false;
    std::string notice;
    std::uint64_t notice_until = 0U;
    std::uint64_t previous_ticks = SDL_GetTicks();
    std::uint64_t title_ticks = 0U;
    std::uint64_t panel_ticks = 0U;
    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_QUIT) running = false;
            else if (event.type == SDL_EVENT_KEY_DOWN) {
                bool reset = false;
                switch (event.key.scancode) {
                    case SDL_SCANCODE_ESCAPE: running = false; break;
                    case SDL_SCANCODE_SPACE: paused = !paused; break;
                    case SDL_SCANCODE_1: active_test = signalcloud::physics::ShowcaseTest::drop; reset = true; break;
                    case SDL_SCANCODE_2: active_test = signalcloud::physics::ShowcaseTest::bounce; reset = true; break;
                    case SDL_SCANCODE_3: active_test = signalcloud::physics::ShowcaseTest::slide; reset = true; break;
                    case SDL_SCANCODE_4: active_test = signalcloud::physics::ShowcaseTest::throw_arc; reset = true; break;
                    case SDL_SCANCODE_5: active_test = signalcloud::physics::ShowcaseTest::break_test; reset = true; break;
                    case SDL_SCANCODE_R: reset = true; break;
                    case SDL_SCANCODE_F:
                    case SDL_SCANCODE_HOME:
                        camera = OrbitCamera{};
                        camera.distance = std::clamp(std::max(15.0F, bounds.radius * 4.4F + 4.0F), 15.0F, 80.0F);
                        camera.center = {0.0F, 2.2F, 0.0F};
                        notice = "CAMERA RESET";
                        notice_until = SDL_GetTicks() + 1800U;
                        break;
                    case SDL_SCANCODE_C: options.visual.collision_outline = !options.visual.collision_outline; break;
                    case SDL_SCANCODE_L: options.visual.lod_fraction = next_lod(options.visual.lod_fraction); break;
                    case SDL_SCANCODE_V: options.visual.view_mode = next_view(options.visual.view_mode); break;
                    case SDL_SCANCODE_P: options.visual.actor_preview = !options.visual.actor_preview; break;
                    case SDL_SCANCODE_T:
                        follow_camera = !follow_camera;
                        notice = follow_camera ? "CAMERA FOLLOW ON" : "CAMERA FOLLOW OFF";
                        notice_until = SDL_GetTicks() + 1800U;
                        break;
                    case SDL_SCANCODE_O:
                        auto_loop = !auto_loop;
                        notice = auto_loop ? "TEST LOOP ON" : "TEST LOOP OFF";
                        notice_until = SDL_GetTicks() + 1800U;
                        break;
                    case SDL_SCANCODE_H: show_help = !show_help; break;
                    case SDL_SCANCODE_I:
                        status_overlay = !status_overlay;
                        notice = status_overlay ? "INFO UI OVERLAY" : "INFO WORLD PLATE";
                        notice_until = SDL_GetTicks() + 1800U;
                        break;
                    case SDL_SCANCODE_S: snapshot_requested = true; break;
                    default: break;
                }
                if (reset) {
                    reset_test(active_test, profile, state);
                    notice = std::string(signalcloud::physics::showcase_test_name(active_test)) + " START";
                    notice_until = SDL_GetTicks() + 1600U;
                }
            } else if (event.type == SDL_EVENT_MOUSE_BUTTON_DOWN && event.button.button == SDL_BUTTON_LEFT) {
                orbiting = true;
            } else if (event.type == SDL_EVENT_MOUSE_BUTTON_UP && event.button.button == SDL_BUTTON_LEFT) {
                orbiting = false;
            } else if (event.type == SDL_EVENT_MOUSE_MOTION && orbiting) {
                camera.yaw_degrees += event.motion.xrel * 0.32F;
                camera.pitch_degrees = std::clamp(camera.pitch_degrees - event.motion.yrel * 0.28F, -88.0F, 88.0F);
            } else if (event.type == SDL_EVENT_MOUSE_WHEEL) {
                camera.distance = std::clamp(camera.distance * std::pow(0.88F, event.wheel.y), 2.0F, 160.0F);
            }
        }

        const std::uint64_t current_ticks = SDL_GetTicks();
        const float elapsed = std::min(0.05F, static_cast<float>(current_ticks - previous_ticks) / 1000.0F);
        previous_ticks = current_ticks;
        if (!paused) {
            float remaining = elapsed;
            while (remaining > 0.0F) {
                const float dt = std::min(remaining, 1.0F / 120.0F);
                signalcloud::physics::step_showcase(profile, state, dt, 40U);
                remaining -= dt;
            }
            const bool completed = state.elapsed_seconds >= loop_seconds(active_test) ||
                (state.settled && state.elapsed_seconds >= 3.0F) ||
                (state.broken && state.elapsed_seconds >= 3.0F);
            if (auto_loop && completed) reset_test(active_test, profile, state);
        }
        if (follow_camera) {
            const Vec3 target = state.position + Vec3{0.0F, std::min(1.2F, support_height(profile) * 0.24F), 0.0F};
            camera.center = camera.center + (target - camera.center) * std::clamp(elapsed * 6.0F, 0.0F, 1.0F);
        }

        const float time = static_cast<float>(current_ticks) / 1000.0F;
        points = signalcloud::physics::build_showcase_frame_points(
            base_points, bounds, profile, state, options.visual, time);
        if (show_help && current_ticks - panel_ticks > 80U) panel_ticks = current_ticks;
        const std::string status = status_text(
            active_test, options.visual, paused, follow_camera, auto_loop, show_help,
            base_points.size(), signalcloud::physics::showcase_lod_count(
                base_points.size(), options.visual.lod_fraction), options.playbook_id);
        if (!status_overlay) {
            append_status_billboard(points, status_font ? &*status_font : nullptr, status,
                camera.eye(), camera.center + Vec3{
                    0.0F, std::max(3.8F, support_height(profile) + 2.5F), 2.4F});
        }
        if (!renderer.upload_points(points, &error)) {
            notice = "UPLOAD ERROR";
            notice_until = current_ticks + 3000U;
        }

        if (current_ticks > notice_until) notice.clear();
        if (current_ticks - title_ticks > 150U) {
            set_title(window, profile, active_test, options.visual, state, paused,
                      follow_camera, auto_loop, status_overlay, notice);
            title_ticks = current_ticks;
        }

        int width = 1;
        int height = 1;
        SDL_GetWindowSizeInPixels(window, &width, &height);
        std::vector<signalcloud::render::PointGpu> overlay_points;
        if (status_overlay && status_font) {
            signalcloud::ui::ShowcaseInfoOverlayCamera overlay_camera;
            overlay_camera.eye = camera.eye();
            overlay_camera.center = camera.center;
            overlay_camera.aspect = static_cast<float>(width) /
                                    static_cast<float>(std::max(1, height));
            (void)signalcloud::ui::append_showcase_info_overlay(
                overlay_points, *status_font, status, overlay_camera);
        }
        if (!renderer.upload_viewmodel_points(overlay_points, &error)) {
            notice = "OVERLAY UPLOAD ERROR";
            notice_until = current_ticks + 3000U;
        }
        gl.viewport(0, 0, width, height);
        gl.clear_color(0.014F, 0.019F, 0.025F, 1.0F);
        gl.clear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        const Vec3 moving_light{std::cos(time * 0.63F) * 4.0F, 5.6F, std::sin(time * 0.63F) * 4.0F};
        renderer.render(camera.view_projection(static_cast<float>(width) / static_cast<float>(std::max(1, height))),
                        time, state.broken ? 1.0F : 0.0F, false, false,
                        options.visual.point_scale, 1.0F, 1.0F,
                        {}, 0.0F, 0.0F, {}, 0.0F, 0.0F, false,
                        moving_light, 18.0F,
                        options.visual.view_mode == signalcloud::physics::ShowcaseViewMode::light ? 1.15F : 0.68F,
                        {}, 0.0F, 0.0F, {}, 0.0F, 0.0F, width, height);

        if (snapshot_requested) {
            fs::path written;
            std::string snapshot_error;
            if (write_snapshot_ppm(gl, options.snapshot_dir, width, height, current_ticks, written, snapshot_error)) {
                notice = "SNAPSHOT " + written.filename().string();
                std::cout << "Showcase snapshot: " << written << '\n';
            } else {
                notice = "SNAPSHOT FAILED: " + snapshot_error;
                std::cerr << notice << '\n';
            }
            notice_until = current_ticks + 5000U;
            snapshot_requested = false;
        }
        SDL_GL_SwapWindow(window);
    }

    const auto result = signalcloud::physics::simulate_showcase(profile, active_test);
    std::cout << "Showcase " << signalcloud::physics::showcase_test_name(active_test)
              << " | profile " << profile.profile_id
              << " | source points " << base_points.size()
              << " | LOD points " << signalcloud::physics::showcase_lod_count(base_points.size(), options.visual.lod_fraction)
              << " | view " << signalcloud::physics::showcase_view_mode_name(options.visual.view_mode)
              << " | collision " << (options.visual.collision_outline ? "yes" : "no")
              << " | actor " << (options.visual.actor_preview ? "yes" : "no")
              << " | signature " << result.signature
              << " | broken " << (result.state.broken ? "yes" : "no") << '\n';
    renderer.shutdown();
    SDL_GL_DestroyContext(context);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
