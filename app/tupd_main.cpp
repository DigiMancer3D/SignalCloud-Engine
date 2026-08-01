#include "engine/items/tupd_runtime.hpp"
#include "engine/math/mat4.hpp"
#include "engine/math/vec.hpp"
#include "engine/platform/video_backend.hpp"
#include "engine/render/gl_api.hpp"
#include "engine/render/point_renderer.hpp"
#include "engine/scfont/scfont.hpp"
#include "engine/ui/ar_interface.hpp"
#include "engine/ui/showcase_info_overlay.hpp"
#include "engine/ui/tupd_ghost_preview.hpp"

#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <optional>
#include <sstream>
#include <string>
#include <vector>

namespace {
namespace fs = std::filesystem;
using signalcloud::math::Vec3;

struct Options {
    signalcloud::platform::VideoBackend backend{signalcloud::platform::VideoBackend::automatic};
    fs::path project_root;
    fs::path recipe;
    int width{1280};
    int height{820};
};

struct OrbitCamera {
    Vec3 center{0.0F, 1.15F, 0.0F};
    float yaw_degrees{-38.0F};
    float pitch_degrees{16.0F};
    float distance{6.4F};

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
        return signalcloud::math::perspective(58.0F * pi / 180.0F, aspect, 0.02F, 300.0F) *
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

fs::path find_project_root(fs::path start) {
    start = fs::absolute(start);
    if (fs::is_regular_file(start)) start = start.parent_path();
    for (fs::path current = start; !current.empty(); current = current.parent_path()) {
        if (fs::exists(current / "CMakeLists.txt") && fs::exists(current / "content")) return current;
        if (current == current.root_path()) break;
    }
    return {};
}

Options parse_args(int argc, char** argv) {
    Options options;
    options.project_root = find_project_root(fs::current_path());
    for (int index = 1; index < argc; ++index) {
        const std::string argument(argv[index]);
        if (argument.starts_with("--root=")) options.project_root = fs::path(argument.substr(7));
        else if (argument.starts_with("--recipe=")) options.recipe = fs::path(argument.substr(9));
        else if (argument.starts_with("--video=")) {
            if (const auto backend = signalcloud::platform::parse_video_backend(argument.substr(8))) {
                options.backend = *backend;
            }
        } else if (options.recipe.empty()) {
            options.recipe = fs::path(argument);
        }
    }
    if (options.project_root.empty() && !options.recipe.empty()) options.project_root = find_project_root(options.recipe);
    return options;
}

signalcloud::render::PointGpu point(Vec3 position, float radius,
                                    float r, float g, float b, float a,
                                    float density = 1.0F) noexcept {
    return {{position.x, position.y, position.z}, radius,
            {r, g, b, a}, {0.0F, 1.0F, 0.0F}, density};
}

std::vector<signalcloud::render::PointGpu> build_stage() {
    std::vector<signalcloud::render::PointGpu> points;
    points.reserve(6'000U);
    for (int x = -12; x <= 12; ++x) {
        for (int z = -12; z <= 12; ++z) {
            const bool axis = x == 0 || z == 0;
            points.push_back(point({static_cast<float>(x) * 0.45F, 0.0F, static_cast<float>(z) * 0.45F},
                                   axis ? 0.020F : 0.012F,
                                   axis ? 0.25F : 0.11F,
                                   axis ? 0.48F : 0.18F,
                                   axis ? 0.52F : 0.22F,
                                   axis ? 0.72F : 0.46F,
                                   axis ? 1.2F : 0.72F));
        }
    }
    for (int ring = 0; ring < 4; ++ring) {
        const float radius = 2.4F + static_cast<float>(ring) * 0.85F;
        for (int index = 0; index < 160; ++index) {
            const float angle = static_cast<float>(index) / 160.0F * 6.283185307F;
            points.push_back(point({std::cos(angle) * radius, 0.015F, std::sin(angle) * radius},
                                   0.010F, 0.16F, 0.42F, 0.48F, 0.55F, 0.8F));
        }
    }
    return points;
}

std::string status_text(const signalcloud::items::TupdRecipe& recipe,
                        const signalcloud::items::TupdPreview& preview,
                        const signalcloud::items::TupdSandboxSession& sandbox,
                        std::size_t recipe_index,
                        std::size_t recipe_count,
                        bool overlay_visible,
                        std::string_view test_action,
                        signalcloud::ui::TupdGhostInspectionMode inspection_mode,
                        bool exploded) {
    std::ostringstream output;
    output << "TUPD A8a3r1 " << recipe.label << '\n'
           << "RECIPE " << (recipe_index + 1U) << '/' << recipe_count
           << " MODE " << signalcloud::items::tupd_mode_name(recipe.mode) << '\n'
           << "PREVIEW " << (preview.valid ? "VALID" : "BLOCKED")
           << " STABILITY " << static_cast<int>(std::lround(preview.stability_percent))
           << "% CONDITION " << static_cast<int>(std::lround(preview.condition_before))
           << "->" << static_cast<int>(std::lround(preview.condition_after)) << '\n'
           << "RESULT " << (sandbox.result_instance() ? signalcloud::items::tupd_instance_state(*sandbox.result_instance()) : "NONE")
           << " TEST " << test_action << '\n'
           << "TAPE " << sandbox.inventory().items.at("consumable.tupd-tape")
           << " TEST XAR " << sandbox.inventory().xar
           << " NORMAL SAVE " << (sandbox.normal_save_unchanged() ? "UNCHANGED" : "ERROR") << '\n'
           << "LEFT/RIGHT RECIPE  P COMPARE  C COMMIT  E EQUIP/SPAWN\n"
           << "A ACTION  X TEST  D CLEAR  R RESET  I INFO " << (overlay_visible ? "ON" : "OFF") << '\n'
           << "G GHOST " << (exploded ? "EXPLODED" : "ASSEMBLED")
           << "  V VIEW " << signalcloud::ui::tupd_ghost_inspection_name(inspection_mode)
           << "  F/HOME CAMERA";
    if (!preview.errors.empty()) output << "\nBLOCK: " << preview.errors.front();
    else if (!preview.warnings.empty()) output << "\nWARN: " << preview.warnings.front();
    return output.str();
}

}  // namespace

int main(int argc, char** argv) {
    Options options = parse_args(argc, argv);
    if (options.project_root.empty()) {
        std::cerr << "Unable to locate SignalCloud project root\n";
        return 2;
    }

    auto recipe_paths = signalcloud::items::discover_tupd_recipes(options.project_root);
    if (!options.recipe.empty()) {
        const fs::path explicit_path = fs::absolute(options.recipe);
        recipe_paths.erase(std::remove(recipe_paths.begin(), recipe_paths.end(), explicit_path), recipe_paths.end());
        recipe_paths.insert(recipe_paths.begin(), explicit_path);
    }
    if (recipe_paths.empty()) {
        std::cerr << "No .tupd recipes were found\n";
        return 3;
    }

    std::vector<signalcloud::items::TupdRecipe> recipes;
    for (const auto& path : recipe_paths) {
        signalcloud::items::TupdRecipe recipe;
        std::string error;
        if (signalcloud::items::load_tupd_recipe(path, recipe, &error)) recipes.push_back(std::move(recipe));
        else std::cerr << "Tupd recipe skipped: " << path << " | " << error << '\n';
    }
    if (recipes.empty()) return 4;

    std::optional<signalcloud::font::Font> font;
    try {
        font = signalcloud::font::load_scfont(
            options.project_root / "content/core/fonts/terminal_00/Terminal_00.scfont");
    } catch (...) {
        font.reset();
    }

    SDL_SetAppMetadata("SignalCloud Tupd Native Stage", "0.8.3-a3r1", "io.digimancer3d.signalcloud.tupd");
    if (const auto hint = signalcloud::platform::sdl_driver_hint(options.backend)) {
        SDL_SetHint(SDL_HINT_VIDEO_DRIVER, std::string(*hint).c_str());
    }
    if (!SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS)) {
        std::cerr << SDL_GetError() << '\n';
        return 5;
    }
    SDL_Window* window = SDL_CreateWindow(
        "SignalCloud Tupd Native Stage A8a3r1", options.width, options.height,
        SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY);
    if (!window) {
        std::cerr << SDL_GetError() << '\n';
        SDL_Quit();
        return 6;
    }
    SDL_GLContext context = nullptr;
    if (!create_context(window, context, 4, 3) && !create_context(window, context, 3, 3)) {
        std::cerr << SDL_GetError() << '\n';
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 7;
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
        return 8;
    }

    signalcloud::render::PointRenderer renderer;
    const auto stage = build_stage();
    if (!renderer.initialize_points(gl, stage, &error)) {
        std::cerr << error << '\n';
        SDL_GL_DestroyContext(context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 9;
    }

    OrbitCamera camera;
    signalcloud::ui::TupdGhostPreview ghost;
    signalcloud::items::TupdSandboxSession sandbox;
    std::size_t recipe_index = 0U;
    auto preview = sandbox.preview(recipes[recipe_index]);
    std::size_t test_action_index = 0U;
    bool running = true;
    bool orbiting = false;
    bool overlay_visible = true;
    bool ghost_exploded = false;
    auto inspection_mode = signalcloud::ui::TupdGhostInspectionMode::result;
    std::string notice = "PREVIEW READY";
    std::uint64_t notice_until = SDL_GetTicks() + 1800U;

    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_QUIT) running = false;
            else if (event.type == SDL_EVENT_KEY_DOWN && !event.key.repeat) {
                bool changed_recipe = false;
                switch (event.key.scancode) {
                    case SDL_SCANCODE_ESCAPE: running = false; break;
                    case SDL_SCANCODE_LEFT:
                        recipe_index = recipe_index == 0U ? recipes.size() - 1U : recipe_index - 1U;
                        changed_recipe = true;
                        break;
                    case SDL_SCANCODE_RIGHT:
                        recipe_index = (recipe_index + 1U) % recipes.size();
                        changed_recipe = true;
                        break;
                    case SDL_SCANCODE_P:
                        preview = sandbox.preview(recipes[recipe_index]);
                        notice = preview.valid ? "PREVIEW VALID" : "PREVIEW BLOCKED";
                        notice_until = SDL_GetTicks() + 1800U;
                        break;
                    case SDL_SCANCODE_C: {
                        const auto receipt = sandbox.commit(recipes[recipe_index]);
                        preview = sandbox.last_preview();
                        notice = receipt.committed ? "RESULT CREATED / NOT EQUIPPED" : "COMMIT REJECTED";
                        notice_until = SDL_GetTicks() + 2600U;
                        std::string receipt_error;
                        (void)signalcloud::items::write_tupd_receipt_atomic(
                            options.project_root / "user_data/studio/tupd_sandbox_receipt_latest.json",
                            receipt, &receipt_error);
                        if (sandbox.result_instance()) {
                            (void)signalcloud::items::save_tupd_instance_atomic(
                                options.project_root / "user_data/studio/tupd_sandbox_instance_latest.tupdinstance",
                                *sandbox.result_instance(), &receipt_error);
                        }
                        break;
                    }
                    case SDL_SCANCODE_E: {
                        const bool applied = sandbox.equip_or_spawn_result();
                        notice = applied && sandbox.result_instance() ? signalcloud::items::tupd_instance_state(*sandbox.result_instance()) : "COMMIT A RESULT FIRST";
                        notice_until = SDL_GetTicks() + 2200U;
                        if (sandbox.result_instance()) {
                            std::string save_error;
                            (void)signalcloud::items::save_tupd_instance_atomic(
                                options.project_root / "user_data/studio/tupd_sandbox_instance_latest.tupdinstance",
                                *sandbox.result_instance(), &save_error);
                        }
                        break;
                    }
                    case SDL_SCANCODE_A: {
                        const auto& actions = recipes[recipe_index].test_actions;
                        if (!actions.empty()) test_action_index = (test_action_index + 1U) % actions.size();
                        notice = actions.empty() ? "NO DECLARED TEST" : "TEST " + actions[test_action_index];
                        notice_until = SDL_GetTicks() + 1600U;
                        break;
                    }
                    case SDL_SCANCODE_X: {
                        const auto& actions = recipes[recipe_index].test_actions;
                        const auto action = actions.empty() ? signalcloud::items::TupdTestAction::unknown : signalcloud::items::parse_tupd_test_action(actions[test_action_index % actions.size()]);
                        const auto result = sandbox.test_result(action);
                        notice = result.accepted ? result.outcome : "TEST BLOCKED: " + result.outcome;
                        notice_until = SDL_GetTicks() + 2600U;
                        if (sandbox.result_instance()) {
                            std::string save_error;
                            (void)signalcloud::items::save_tupd_instance_atomic(
                                options.project_root / "user_data/studio/tupd_sandbox_instance_latest.tupdinstance",
                                *sandbox.result_instance(), &save_error);
                        }
                        break;
                    }
                    case SDL_SCANCODE_D:
                        sandbox.clear_result();
                        notice = "RESULT CLEARED";
                        notice_until = SDL_GetTicks() + 1800U;
                        break;
                    case SDL_SCANCODE_R:
                        sandbox.reset();
                        test_action_index = 0U;
                        preview = sandbox.preview(recipes[recipe_index]);
                        notice = "SANDBOX RESET";
                        notice_until = SDL_GetTicks() + 1800U;
                        break;
                    case SDL_SCANCODE_G:
                        ghost_exploded = !ghost_exploded;
                        notice = ghost_exploded ? "GHOST EXPLODED" : "GHOST ASSEMBLED";
                        notice_until = SDL_GetTicks() + 1800U;
                        break;
                    case SDL_SCANCODE_V:
                        inspection_mode = signalcloud::ui::next_tupd_ghost_inspection_mode(inspection_mode);
                        notice = "VIEW " + std::string(signalcloud::ui::tupd_ghost_inspection_name(inspection_mode));
                        notice_until = SDL_GetTicks() + 1800U;
                        break;
                    case SDL_SCANCODE_I:
                        overlay_visible = !overlay_visible;
                        notice = overlay_visible ? "INFO ON" : "INFO OFF";
                        notice_until = SDL_GetTicks() + 1600U;
                        break;
                    case SDL_SCANCODE_F:
                    case SDL_SCANCODE_HOME:
                        camera = OrbitCamera{};
                        notice = "CAMERA RESET";
                        notice_until = SDL_GetTicks() + 1600U;
                        break;
                    default: break;
                }
                if (changed_recipe) {
                    sandbox.reset();
                    test_action_index = 0U;
                    preview = sandbox.preview(recipes[recipe_index]);
                    notice = "RECIPE " + std::to_string(recipe_index + 1U);
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
                camera.distance = std::clamp(camera.distance * std::pow(0.88F, event.wheel.y), 3.0F, 40.0F);
            }
        }

        const std::uint64_t ticks = SDL_GetTicks();
        if (ticks > notice_until) notice.clear();
        const float time = static_cast<float>(ticks) / 1000.0F;
        const Vec3 eye = camera.eye();
        const Vec3 forward = signalcloud::math::normalize_or(camera.center - eye, {0.0F, 0.0F, -1.0F});
        const Vec3 right = signalcloud::math::normalize_or(
            signalcloud::math::cross(forward, {0.0F, 1.0F, 0.0F}), {1.0F, 0.0F, 0.0F});
        signalcloud::ui::ArPose camera_pose;
        camera_pose.camera_position = eye;
        camera_pose.forward = forward;
        camera_pose.right = right;
        const auto* instance = sandbox.result_instance() ? &*sandbox.result_instance() : nullptr;
        const auto* test = sandbox.last_test() ? &*sandbox.last_test() : nullptr;

        signalcloud::ui::TupdGhostPlacement world_placement;
        world_placement.mode = signalcloud::ui::TupdGhostPlacementMode::world_stage;
        world_placement.world_center = {0.0F, 1.15F, 0.0F};
        world_placement.world_forward = {0.0F, 0.0F, -1.0F};
        world_placement.world_right = {1.0F, 0.0F, 0.0F};
        auto world_points = ghost.build_points(
            recipes[recipe_index], preview, time, camera_pose, instance, test,
            inspection_mode, ghost_exploded, world_placement);
        std::vector<signalcloud::render::PointGpu> ui_points;

        int width = 1;
        int height = 1;
        SDL_GetWindowSizeInPixels(window, &width, &height);
        const std::string status = status_text(recipes[recipe_index], preview, sandbox,
                                               recipe_index, recipes.size(), overlay_visible,
                                               recipes[recipe_index].test_actions.empty() ? "none" : recipes[recipe_index].test_actions[test_action_index % recipes[recipe_index].test_actions.size()],
                                               inspection_mode, ghost_exploded);
        if (overlay_visible && font) {
            signalcloud::ui::ShowcaseInfoOverlayCamera overlay_camera;
            overlay_camera.eye = eye;
            overlay_camera.center = camera.center;
            overlay_camera.aspect = static_cast<float>(width) / static_cast<float>(std::max(1, height));
            (void)signalcloud::ui::append_showcase_info_overlay(
                ui_points, *font, status + (notice.empty() ? "" : "\n" + notice), overlay_camera);
        }
        if (!renderer.upload_dynamic_points(world_points, &error)) {
            std::cerr << "Tupd world-result upload failed: " << error << '\n';
            running = false;
        }
        if (!renderer.upload_viewmodel_points(ui_points, &error)) {
            std::cerr << "Tupd information-overlay upload failed: " << error << '\n';
            running = false;
        }

        std::ostringstream title;
        title << "SignalCloud Tupd Native Stage A8a3r1 — " << recipes[recipe_index].label
              << " · " << (preview.valid ? "VALID" : "BLOCKED")
              << " · test inventory " << sandbox.inventory().items.at("consumable.tupd-tape")
              << " tape / " << sandbox.inventory().xar << " XAR"
              << " · result " << (sandbox.result_instance() ? signalcloud::items::tupd_instance_state(*sandbox.result_instance()) : "NONE")
              << " · " << signalcloud::ui::tupd_ghost_inspection_name(inspection_mode)
              << "/" << (ghost_exploded ? "EXPLODED" : "ASSEMBLED")
              << " · normal save " << (sandbox.normal_save_unchanged() ? "UNCHANGED" : "ERROR");
        SDL_SetWindowTitle(window, title.str().c_str());

        gl.viewport(0, 0, width, height);
        gl.clear_color(0.008F, 0.013F, 0.018F, 1.0F);
        gl.clear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        renderer.render(camera.view_projection(static_cast<float>(width) / static_cast<float>(std::max(1, height))),
                        time, preview.forced ? 0.25F : 0.0F, false, false,
                        1.0F, 1.0F, 1.0F,
                        {}, 0.0F, 0.0F, {}, 0.0F, 0.0F, false,
                        {2.5F, 5.0F, 2.0F}, 18.0F, 0.72F,
                        {}, 0.0F, 0.0F, {}, 0.0F, 0.0F, width, height);
        SDL_GL_SwapWindow(window);
    }

    std::cout << "Tupd native stage | recipe " << recipes[recipe_index].recipe_id
              << " | preview " << (preview.valid ? "valid" : "blocked")
              << " | result " << (sandbox.result_instance() ? signalcloud::items::tupd_instance_state(*sandbox.result_instance()) : "none")
              << " | tests " << sandbox.test_history().size()
              << " | view " << signalcloud::ui::tupd_ghost_inspection_name(inspection_mode)
              << "/" << (ghost_exploded ? "exploded" : "assembled")
              << " | normal save " << (sandbox.normal_save_unchanged() ? "unchanged" : "ERROR")
              << " | signature " << preview.signature << '\n';

    renderer.shutdown();
    SDL_GL_DestroyContext(context);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
