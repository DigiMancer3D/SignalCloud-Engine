cmake_minimum_required(VERSION 3.20)
project(SignalCloudEngine VERSION 0.13.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(SC_ENABLE_WARNINGS "Enable strict compiler warnings" ON)
option(SC_BUILD_GUI "Build the SDL3/OpenGL Pivot window" ON)
option(SC_FETCH_SDL3 "Fetch pinned SDL3 if no shared installation is found" ON)

set(SC_SDL3_VERSION "3.4.10" CACHE STRING "Pinned fallback SDL3 version")
set(SC_SDL3_SHA256 "12b34280415ec8418c864408b93d008a20a6530687ee613d60bfbd20411f2785" CACHE STRING "Pinned SDL3 source SHA-256")

function(sc_warnings target)
    if(NOT SC_ENABLE_WARNINGS)
        return()
    endif()
    if(MSVC)
        target_compile_options(${target} PRIVATE /W4 /permissive-)
    else()
        target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wshadow)
    endif()
endfunction()

add_library(signalcloud_core
    engine/ai/playbook.cpp
    engine/data/udata.cpp
    engine/pcp3/pcp3_asset.cpp
    engine/physics/showcase_runtime.cpp
    engine/physics/showcase_visualization.cpp
    engine/items/tupd_runtime.cpp
    engine/ui/showcase_info_overlay.cpp
    engine/ui/tupd_ghost_preview.cpp
    engine/assets/manifest_index.cpp
    engine/assets/hot_reload_index.cpp
    engine/assets/hot_reload_status.cpp
    engine/scfont/scfont.cpp
    engine/scfont/font_service.cpp
    engine/scfont/text_point_adapter.cpp
    engine/platform/video_backend.cpp
    engine/platform/first_person_camera.cpp
    engine/input/input_profile.cpp
    engine/lighting/illuminosity_runtime.cpp
    engine/lighting/illuminosity_bake.cpp
    engine/audio/audio_interference_runtime.cpp
    engine/materials/material_runtime.cpp
    engine/render/memory_budget.cpp
    engine/render/adaptive_budget.cpp
    engine/render/adaptive_residency.cpp
    engine/render/point_cloud.cpp
    engine/render/point_lab.cpp
    engine/render/system_point_budget.cpp
    engine/render/room_visibility.cpp
    engine/render/signal_interference.cpp
    engine/render/local_siren.cpp
    engine/render/water_disturbance.cpp
    engine/render/sound_ripple.cpp
    engine/world/world_seed.cpp
    engine/world/liminal_level.cpp
    engine/world/player_controller.cpp
    engine/world/threat_director.cpp
    engine/world/threat_navigation.cpp
    engine/world/recovery_system.cpp
    engine/combat/combat_system.cpp
    engine/economy/economy_system.cpp
    engine/ui/ar_interface.cpp
    engine/ui/scui_panel.cpp
    engine/ui/scui_native_runtime.cpp
    engine/ui/scui_binding_store.cpp
    engine/ui/scui_registry.cpp
    engine/ui/scui_light_preview.cpp
    engine/ui/tactical_memory_map.cpp
    engine/benchmark/native_stress_route.cpp
    engine/benchmark/machine_profile.cpp
    engine/benchmark/stress_safety.cpp
    engine/benchmark/workload_ramp.cpp
    engine/ui/tactical_map_prototype.cpp
)
target_include_directories(signalcloud_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
sc_warnings(signalcloud_core)

add_executable(signalcloud_diagnostics app/main.cpp)
target_link_libraries(signalcloud_diagnostics PRIVATE signalcloud_core)
sc_warnings(signalcloud_diagnostics)

add_executable(signalcloud_illuminosity_bake app/illuminosity_bake_main.cpp)
target_link_libraries(signalcloud_illuminosity_bake PRIVATE signalcloud_core)
sc_warnings(signalcloud_illuminosity_bake)

if(SC_BUILD_GUI)
    find_package(SDL3 CONFIG QUIET)
    if(NOT TARGET SDL3::SDL3)
        if(NOT SC_FETCH_SDL3)
            message(FATAL_ERROR "SDL3 was not found. Set CMAKE_PREFIX_PATH to the shared SDL3 cache or enable SC_FETCH_SDL3.")
        endif()
        include(FetchContent)
        set(SDL_SHARED ON CACHE BOOL "" FORCE)
        set(SDL_STATIC OFF CACHE BOOL "" FORCE)
        set(SDL_TEST_LIBRARY OFF CACHE BOOL "" FORCE)
        set(SDL_TESTS OFF CACHE BOOL "" FORCE)
        set(SDL_EXAMPLES OFF CACHE BOOL "" FORCE)
        FetchContent_Declare(
            SDL3
            URL "https://github.com/libsdl-org/SDL/releases/download/release-${SC_SDL3_VERSION}/SDL3-${SC_SDL3_VERSION}.tar.gz"
            URL_HASH "SHA256=${SC_SDL3_SHA256}"
            DOWNLOAD_EXTRACT_TIMESTAMP FALSE
        )
        FetchContent_MakeAvailable(SDL3)
    endif()

    add_executable(almond_signal_live_tape
        app/game_main.cpp
        engine/platform/capability_report.cpp
        engine/render/gl_api.cpp
        engine/render/point_renderer.cpp
        engine/audio/splash_audio.cpp
    )
    target_link_libraries(almond_signal_live_tape PRIVATE signalcloud_core SDL3::SDL3)
    sc_warnings(almond_signal_live_tape)

    add_executable(almond_signal_native_stress
        app/native_stress_main.cpp
        engine/platform/capability_report.cpp
        engine/render/gl_api.cpp
        engine/render/point_renderer.cpp
    )
    target_link_libraries(almond_signal_native_stress PRIVATE signalcloud_core SDL3::SDL3)
    sc_warnings(almond_signal_native_stress)

    add_executable(almond_signal_showcase
        app/showcase_main.cpp
        engine/render/gl_api.cpp
        engine/render/point_renderer.cpp
    )
    target_link_libraries(almond_signal_showcase PRIVATE signalcloud_core SDL3::SDL3)
    sc_warnings(almond_signal_showcase)

    add_executable(almond_signal_pcp_preview
        app/pcp3_preview_main.cpp
        engine/render/gl_api.cpp
        engine/render/point_renderer.cpp
    )
    target_link_libraries(almond_signal_pcp_preview PRIVATE signalcloud_core SDL3::SDL3)
    sc_warnings(almond_signal_pcp_preview)

    add_executable(almond_signal_tupd_preview
        app/tupd_main.cpp
        engine/render/gl_api.cpp
        engine/render/point_renderer.cpp
    )
    target_link_libraries(almond_signal_tupd_preview PRIVATE signalcloud_core SDL3::SDL3)
    sc_warnings(almond_signal_tupd_preview)
endif()

add_executable(signalcloud_pivot0_tests tests/test_pivot.cpp)
target_link_libraries(signalcloud_pivot0_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot0_tests)

add_executable(signalcloud_pivot1_tests tests/test_pivot1.cpp)
target_link_libraries(signalcloud_pivot1_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot1_tests)

add_executable(signalcloud_pivot2_tests tests/test_pivot2.cpp)
target_link_libraries(signalcloud_pivot2_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot2_tests)

add_executable(signalcloud_pivot3_tests tests/test_pivot3.cpp)
target_link_libraries(signalcloud_pivot3_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot3_tests)

add_executable(signalcloud_pivot4_tests tests/test_pivot4.cpp)
target_link_libraries(signalcloud_pivot4_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot4_tests)


add_executable(signalcloud_pivot5_tests tests/test_pivot5.cpp)
target_link_libraries(signalcloud_pivot5_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot5_tests)

add_executable(signalcloud_pivot5_a2_tests tests/test_pivot5_a2.cpp)
target_link_libraries(signalcloud_pivot5_a2_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot5_a2_tests)

add_executable(signalcloud_pivot6_tests tests/test_pivot6.cpp)
target_link_libraries(signalcloud_pivot6_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot6_tests)

add_executable(signalcloud_pivot6_a2_tests tests/test_pivot6_a2.cpp)
target_link_libraries(signalcloud_pivot6_a2_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot6_a2_tests)

add_executable(signalcloud_pivot7_tests tests/test_pivot7.cpp)
target_link_libraries(signalcloud_pivot7_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot7_tests)

add_executable(signalcloud_pivot8_tests tests/test_pivot8.cpp)
target_link_libraries(signalcloud_pivot8_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot8_tests)

add_executable(signalcloud_pivot8_a2_tests tests/test_pivot8_a2.cpp)
target_link_libraries(signalcloud_pivot8_a2_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot8_a2_tests)

add_executable(signalcloud_pivot9_tests tests/test_pivot9.cpp)
target_link_libraries(signalcloud_pivot9_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot9_tests)


add_executable(signalcloud_pivot10_tests tests/test_pivot10.cpp)
target_link_libraries(signalcloud_pivot10_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot10_tests)

add_executable(signalcloud_pivot11_tests tests/test_pivot11.cpp)
target_link_libraries(signalcloud_pivot11_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot11_tests)

add_executable(signalcloud_pivot12_tests tests/test_pivot12.cpp)
target_link_libraries(signalcloud_pivot12_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot12_tests)

add_executable(signalcloud_pivot12_a3_tests tests/test_pivot12_a3.cpp)
target_link_libraries(signalcloud_pivot12_a3_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot12_a3_tests)

add_executable(signalcloud_pivot12_a4_tests tests/test_pivot12_a4.cpp)
target_link_libraries(signalcloud_pivot12_a4_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot12_a4_tests)

add_executable(signalcloud_pivot12_a5_tests tests/test_pivot12_a5.cpp)
target_link_libraries(signalcloud_pivot12_a5_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot12_a5_tests)

add_executable(signalcloud_pivot13_tests tests/test_pivot13.cpp)
target_link_libraries(signalcloud_pivot13_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot13_tests)

add_executable(signalcloud_pivot13_a2_tests tests/test_pivot13_a2.cpp)
target_link_libraries(signalcloud_pivot13_a2_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot13_a2_tests)

add_executable(signalcloud_pivot13_a3_tests tests/test_pivot13_a3.cpp)
target_link_libraries(signalcloud_pivot13_a3_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pivot13_a3_tests)


add_executable(signalcloud_native_stress_route_tests tests/test_native_stress_route.cpp)
target_link_libraries(signalcloud_native_stress_route_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_native_stress_route_tests)

add_executable(signalcloud_machine_profile_tests tests/test_machine_profile.cpp)
target_link_libraries(signalcloud_machine_profile_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_machine_profile_tests)

add_executable(signalcloud_stress_safety_tests tests/test_stress_safety.cpp)
target_link_libraries(signalcloud_stress_safety_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_stress_safety_tests)

add_executable(signalcloud_workload_ramp_tests tests/test_workload_ramp.cpp)
target_link_libraries(signalcloud_workload_ramp_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_workload_ramp_tests)

add_executable(signalcloud_pcp3_asset_tests tests/test_pcp3_asset.cpp)
target_link_libraries(signalcloud_pcp3_asset_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pcp3_asset_tests)

add_executable(signalcloud_pcp3_interaction_tests tests/test_pcp3_interaction.cpp)
target_link_libraries(signalcloud_pcp3_interaction_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pcp3_interaction_tests)

add_executable(signalcloud_pcp3_entity_tests tests/test_pcp3_entity.cpp)
target_link_libraries(signalcloud_pcp3_entity_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pcp3_entity_tests)

add_executable(signalcloud_pcp3_world_tests tests/test_pcp3_world.cpp)
target_link_libraries(signalcloud_pcp3_world_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pcp3_world_tests)

add_executable(signalcloud_pcp3_encounter_tests tests/test_pcp3_encounter.cpp)
target_link_libraries(signalcloud_pcp3_encounter_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pcp3_encounter_tests)

add_executable(signalcloud_pcp3_streaming_tests tests/test_pcp3_streaming.cpp)
target_link_libraries(signalcloud_pcp3_streaming_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_pcp3_streaming_tests)

add_executable(signalcloud_scui_tests tests/test_scui.cpp)
target_link_libraries(signalcloud_scui_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_scui_tests)

add_executable(signalcloud_scui_runtime_tests tests/test_scui_runtime.cpp)
target_link_libraries(signalcloud_scui_runtime_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_scui_runtime_tests)

add_executable(signalcloud_scui_registry_tests tests/test_scui_registry.cpp)
target_link_libraries(signalcloud_scui_registry_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_scui_registry_tests)

add_executable(signalcloud_hot_reload_index_tests tests/test_hot_reload_index.cpp)
target_link_libraries(signalcloud_hot_reload_index_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_hot_reload_index_tests)

add_executable(signalcloud_hot_reload_status_tests tests/test_hot_reload_status.cpp)
target_link_libraries(signalcloud_hot_reload_status_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_hot_reload_status_tests)

add_executable(signalcloud_illuminosity_runtime_tests tests/test_illuminosity_runtime.cpp)
target_link_libraries(signalcloud_illuminosity_runtime_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_illuminosity_runtime_tests)

add_executable(signalcloud_illuminosity_multilight_tests tests/test_illuminosity_multilight.cpp)
target_link_libraries(signalcloud_illuminosity_multilight_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_illuminosity_multilight_tests)

add_executable(signalcloud_illuminosity_authoring_tests tests/test_illuminosity_authoring.cpp)
target_link_libraries(signalcloud_illuminosity_authoring_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_illuminosity_authoring_tests)

add_executable(signalcloud_material_runtime_tests tests/test_material_runtime.cpp)
target_link_libraries(signalcloud_material_runtime_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_material_runtime_tests)

add_executable(signalcloud_material_pattern_tests tests/test_material_patterns.cpp)
target_link_libraries(signalcloud_material_pattern_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_material_pattern_tests)

add_executable(signalcloud_audio_interference_runtime_tests tests/test_audio_interference_runtime.cpp)
target_link_libraries(signalcloud_audio_interference_runtime_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_audio_interference_runtime_tests)

add_executable(signalcloud_a5a3r1_preview_audio_tests tests/test_a5a3r1_preview_audio.cpp)
target_link_libraries(signalcloud_a5a3r1_preview_audio_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_a5a3r1_preview_audio_tests)

add_executable(signalcloud_scfont_tests tests/test_scfont.cpp)
target_link_libraries(signalcloud_scfont_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_scfont_tests)

add_executable(signalcloud_a5a3r2_text_preview_tests tests/test_a5a3r2_text_preview.cpp)
target_link_libraries(signalcloud_a5a3r2_text_preview_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_a5a3r2_text_preview_tests)

add_executable(signalcloud_playbook_runtime_tests tests/test_playbook_runtime.cpp)
target_link_libraries(signalcloud_playbook_runtime_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_playbook_runtime_tests)

add_executable(signalcloud_showcase_runtime_tests tests/test_showcase_runtime.cpp)
target_link_libraries(signalcloud_showcase_runtime_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_showcase_runtime_tests)

add_executable(signalcloud_showcase_visualization_tests tests/test_showcase_visualization.cpp)
target_link_libraries(signalcloud_showcase_visualization_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_showcase_visualization_tests)

add_executable(signalcloud_showcase_info_overlay_tests tests/test_showcase_info_overlay.cpp)
target_link_libraries(signalcloud_showcase_info_overlay_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_showcase_info_overlay_tests)

add_executable(signalcloud_tupd_runtime_tests tests/test_tupd_runtime.cpp)
target_link_libraries(signalcloud_tupd_runtime_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_tupd_runtime_tests)

add_executable(signalcloud_tupd_ghost_preview_tests tests/test_tupd_ghost_preview.cpp)
target_link_libraries(signalcloud_tupd_ghost_preview_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_tupd_ghost_preview_tests)

add_executable(signalcloud_tupd_instance_tests tests/test_tupd_instance.cpp)
target_link_libraries(signalcloud_tupd_instance_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_tupd_instance_tests)

add_executable(signalcloud_tupd_graph_inspection_tests tests/test_tupd_graph_inspection.cpp)
target_link_libraries(signalcloud_tupd_graph_inspection_tests PRIVATE signalcloud_core)
sc_warnings(signalcloud_tupd_graph_inspection_tests)

include(CTest)
if(BUILD_TESTING)
    add_test(NAME signalcloud_pivot0_tests COMMAND signalcloud_pivot0_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot1_tests COMMAND signalcloud_pivot1_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot2_tests COMMAND signalcloud_pivot2_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot3_tests COMMAND signalcloud_pivot3_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot4_tests COMMAND signalcloud_pivot4_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot5_tests COMMAND signalcloud_pivot5_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot5_a2_tests COMMAND signalcloud_pivot5_a2_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot6_tests COMMAND signalcloud_pivot6_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot6_a2_tests COMMAND signalcloud_pivot6_a2_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot7_tests COMMAND signalcloud_pivot7_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot8_tests COMMAND signalcloud_pivot8_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot8_a2_tests COMMAND signalcloud_pivot8_a2_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot9_tests COMMAND signalcloud_pivot9_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot10_tests COMMAND signalcloud_pivot10_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot11_tests COMMAND signalcloud_pivot11_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot12_tests COMMAND signalcloud_pivot12_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot12_a3_tests COMMAND signalcloud_pivot12_a3_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot12_a4_tests COMMAND signalcloud_pivot12_a4_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot12_a5_tests COMMAND signalcloud_pivot12_a5_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot13_tests COMMAND signalcloud_pivot13_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot13_a2_tests COMMAND signalcloud_pivot13_a2_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pivot13_a3_tests COMMAND signalcloud_pivot13_a3_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_native_stress_route_tests COMMAND signalcloud_native_stress_route_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_machine_profile_tests COMMAND signalcloud_machine_profile_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_stress_safety_tests COMMAND signalcloud_stress_safety_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_workload_ramp_tests COMMAND signalcloud_workload_ramp_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pcp3_asset_tests COMMAND signalcloud_pcp3_asset_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pcp3_interaction_tests COMMAND signalcloud_pcp3_interaction_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pcp3_entity_tests COMMAND signalcloud_pcp3_entity_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pcp3_world_tests COMMAND signalcloud_pcp3_world_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pcp3_encounter_tests COMMAND signalcloud_pcp3_encounter_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_pcp3_streaming_tests COMMAND signalcloud_pcp3_streaming_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_scui_tests COMMAND signalcloud_scui_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_scui_runtime_tests COMMAND signalcloud_scui_runtime_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_scui_registry_tests COMMAND signalcloud_scui_registry_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_hot_reload_index_tests COMMAND signalcloud_hot_reload_index_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_hot_reload_status_tests COMMAND signalcloud_hot_reload_status_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_illuminosity_runtime_tests COMMAND signalcloud_illuminosity_runtime_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_illuminosity_multilight_tests COMMAND signalcloud_illuminosity_multilight_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_illuminosity_authoring_tests COMMAND signalcloud_illuminosity_authoring_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_material_runtime_tests COMMAND signalcloud_material_runtime_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_material_pattern_tests COMMAND signalcloud_material_pattern_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_audio_interference_runtime_tests COMMAND signalcloud_audio_interference_runtime_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_a5a3r1_preview_audio_tests COMMAND signalcloud_a5a3r1_preview_audio_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_scfont_tests COMMAND signalcloud_scfont_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_a5a3r2_text_preview_tests COMMAND signalcloud_a5a3r2_text_preview_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_playbook_runtime_tests COMMAND signalcloud_playbook_runtime_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_showcase_runtime_tests COMMAND signalcloud_showcase_runtime_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_showcase_visualization_tests COMMAND signalcloud_showcase_visualization_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_showcase_info_overlay_tests COMMAND signalcloud_showcase_info_overlay_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_tupd_runtime_tests COMMAND signalcloud_tupd_runtime_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_tupd_ghost_preview_tests COMMAND signalcloud_tupd_ghost_preview_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_tupd_instance_tests COMMAND signalcloud_tupd_instance_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_tupd_graph_inspection_tests COMMAND signalcloud_tupd_graph_inspection_tests ${CMAKE_CURRENT_SOURCE_DIR})
    add_test(NAME signalcloud_clock_skew_recovery COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_clock_skew_recovery.sh ${CMAKE_CURRENT_SOURCE_DIR})
endif()
