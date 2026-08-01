#pragma once

#include "engine/lighting/illuminosity_runtime.hpp"
#include "engine/materials/material_runtime.hpp"
#include "engine/render/sound_ripple.hpp"
#include "engine/math/mat4.hpp"
#include "engine/math/vec.hpp"
#include "engine/render/gl_api.hpp"
#include "engine/render/point_cloud.hpp"
#include "engine/render/room_visibility.hpp"

#include <array>
#include <cstddef>
#include <string>
#include <vector>

namespace signalcloud::render {

class PointRenderer {
public:
    PointRenderer() = default;
    ~PointRenderer();
    PointRenderer(const PointRenderer&) = delete;
    PointRenderer& operator=(const PointRenderer&) = delete;

    bool initialize(GLApi& gl, const PointCloud& cloud, std::string* error = nullptr);
    bool initialize_points(GLApi& gl, const std::vector<PointGpu>& points, std::string* error = nullptr);
    bool upload_cloud(const PointCloud& cloud, std::string* error = nullptr);
    bool upload_points(const std::vector<PointGpu>& points, std::string* error = nullptr);
    bool upload_dynamic_points(const std::vector<PointGpu>& points, std::string* error = nullptr);
    bool upload_viewmodel_points(const std::vector<PointGpu>& points, std::string* error = nullptr);
    void set_draw_count(std::size_t count) noexcept;
    void set_draw_ranges(const std::vector<DrawRange>& ranges) noexcept;
    void set_tactical_marker(math::Vec3 position) noexcept;
    void set_illuminosity_frame(const lighting::IlluminosityFrame& frame) noexcept { illuminosity_frame_ = frame; }
    void set_material_frame(const materials::MaterialFrame& frame) noexcept { material_frame_ = frame; }
    void set_audio_interference(const SoundInterferenceEvent& event) noexcept {
        audio_band_ = event.frequency_band;
        audio_seed_ = event.seed;
        audio_obstruction_path_ = event.obstruction_path;
        audio_wave_count_ = event.wave_count;
        audio_wave_sharpness_ = event.wave_sharpness;
        audio_displacement_scale_ = event.displacement_scale;
        audio_color_mix_ = event.color_mix;
        audio_visibility_floor_ = event.visibility_floor;
    }
    void set_audio_interference(FrequencyBand band, std::uint32_t seed, float obstruction_path) noexcept {
        SoundInterferenceEvent event{};
        event.frequency_band = band;
        event.seed = seed;
        event.obstruction_path = obstruction_path;
        set_audio_interference(event);
    }
    void render(const math::Mat4& view_projection, float time_seconds, float action_pulse,
                bool scanner_mode, bool tactical_mode, float point_scale,
                float density_scale, float signal_level,
                math::Vec3 local_siren_position, float local_siren_radius,
                float local_siren_strength,
                math::Vec3 splash_position, float splash_radius,
                float splash_strength, bool splash_bomb,
                math::Vec3 light_position, float light_radius, float light_strength,
                math::Vec3 sound_position, float sound_radius, float sound_strength,
                math::Vec3 void_position, float void_radius, float void_strength,
                int viewport_width, int viewport_height);
    void shutdown();

    [[nodiscard]] std::size_t point_count() const noexcept { return submitted_count_; }
    [[nodiscard]] std::size_t resident_count() const noexcept { return allocated_count_; }
    [[nodiscard]] std::size_t allocated_count() const noexcept { return allocated_count_; }
    [[nodiscard]] std::size_t allocated_bytes() const noexcept { return allocated_count_ * sizeof(PointGpu); }
    [[nodiscard]] double last_gpu_ms() const noexcept { return last_gpu_ms_; }
    [[nodiscard]] bool timer_query_available() const noexcept { return timer_query_available_; }

private:
    GLuint compile(GLenum type, const char* source, std::string* error);
    void poll_timer_query();
    void configure_point_vao(GLuint vao, GLuint vbo);

    GLApi* gl_{nullptr};
    GLuint vao_{0};
    GLuint vbo_{0};
    GLuint marker_vao_{0};
    GLuint marker_vbo_{0};
    GLuint dynamic_vao_{0};
    GLuint dynamic_vbo_{0};
    GLuint viewmodel_vao_{0};
    GLuint viewmodel_vbo_{0};
    GLsizei marker_count_{0};
    GLsizei dynamic_count_{0};
    GLsizei viewmodel_count_{0};
    math::Vec3 marker_position_{};
    GLuint program_{0};
    GLint matrix_location_{-1};
    GLint time_location_{-1};
    GLint pulse_location_{-1};
    GLint scanner_location_{-1};
    GLint tactical_location_{-1};
    GLint point_scale_location_{-1};
    GLint density_scale_location_{-1};
    GLint signal_level_location_{-1};
    GLint local_siren_position_location_{-1};
    GLint local_siren_radius_location_{-1};
    GLint local_siren_strength_location_{-1};
    GLint splash_position_location_{-1};
    GLint splash_radius_location_{-1};
    GLint splash_strength_location_{-1};
    GLint splash_bomb_location_{-1};
    GLint light_position_location_{-1};
    GLint light_radius_location_{-1};
    GLint light_strength_location_{-1};
    GLint sound_position_location_{-1};
    GLint sound_radius_location_{-1};
    GLint sound_strength_location_{-1};
    GLint void_position_location_{-1};
    GLint void_radius_location_{-1};
    GLint void_strength_location_{-1};
    GLint preview_clip_location_{-1};
    GLint preview_viewer_location_{-1};
    GLint preview_center_location_{-1};
    GLint preview_normal_location_{-1};
    GLint preview_half_width_location_{-1};
    GLint preview_bottom_location_{-1};
    GLint preview_top_location_{-1};
    GLint preview_strength_location_{-1};
    GLint authored_light_count_location_{-1};
    std::array<GLint, lighting::kMaxEvaluatedLocalLights> authored_light_position_locations_{};
    std::array<GLint, lighting::kMaxEvaluatedLocalLights> authored_light_color_locations_{};
    std::array<GLint, lighting::kMaxEvaluatedLocalLights> authored_light_radius_locations_{};
    std::array<GLint, lighting::kMaxEvaluatedLocalLights> authored_light_strength_locations_{};
    GLint authored_global_color_location_{-1};
    GLint authored_global_strength_location_{-1};
    GLint authored_point_size_boost_location_{-1};
    GLint authored_visibility_floor_location_{-1};
    GLint render_class_location_{-1};
    std::array<GLint, 3U> material_enabled_locations_{};
    std::array<GLint, 3U> material_source_color_locations_{};
    std::array<GLint, 3U> material_accent_color_locations_{};
    std::array<GLint, 3U> material_detail_color_locations_{};
    std::array<GLint, 3U> material_jg_locations_{};
    std::array<GLint, 3U> material_jl_locations_{};
    std::array<GLint, 3U> material_jc_locations_{};
    std::array<GLint, 3U> material_js_locations_{};
    std::array<GLint, 3U> material_jitter_locations_{};
    std::array<GLint, 3U> material_variation_locations_{};
    std::array<GLint, 3U> material_opacity_locations_{};
    std::array<GLint, 3U> material_seed_locations_{};
    std::array<GLint, 3U> material_pattern_mode_locations_{};
    std::array<GLint, 3U> material_primary_spacing_locations_{};
    std::array<GLint, 3U> material_secondary_spacing_locations_{};
    std::array<GLint, 3U> material_breakup_scale_locations_{};
    std::array<GLint, 3U> material_breakup_strength_locations_{};
    std::array<GLint, 3U> material_displacement_weight_locations_{};
    std::array<GLint, 3U> material_color_weight_locations_{};
    std::array<GLint, 3U> material_line_width_locations_{};
    std::array<GLint, 15U> material_definition_layer_locations_{};
    GLint sound_band_location_{-1};
    GLint sound_seed_location_{-1};
    GLint sound_obstruction_location_{-1};
    GLint sound_wave_count_location_{-1};
    GLint sound_wave_sharpness_location_{-1};
    GLint sound_displacement_scale_location_{-1};
    GLint sound_color_mix_location_{-1};
    GLint sound_visibility_floor_location_{-1};
    lighting::IlluminosityFrame illuminosity_frame_{};
    materials::MaterialFrame material_frame_{};
    FrequencyBand audio_band_{FrequencyBand::mid};
    std::uint32_t audio_seed_{1U};
    float audio_obstruction_path_{0.0F};
    std::uint32_t audio_wave_count_{2U};
    float audio_wave_sharpness_{0.58F};
    float audio_displacement_scale_{1.0F};
    float audio_color_mix_{0.22F};
    float audio_visibility_floor_{0.04F};
    std::size_t allocated_count_{0};
    std::size_t submitted_count_{0};
    std::vector<DrawRange> draw_ranges_;

    std::array<GLuint, 3> timer_queries_{};
    std::array<bool, 3> timer_pending_{};
    std::size_t timer_write_index_{0};
    double last_gpu_ms_{0.0};
    bool timer_query_available_{false};
};

}  // namespace signalcloud::render
