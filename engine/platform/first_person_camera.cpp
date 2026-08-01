#include "engine/platform/first_person_camera.hpp"

#include <algorithm>
#include <cmath>

namespace signalcloud::platform {
namespace {
constexpr float pi = 3.14159265358979323846F;
float radians(float degrees) noexcept { return degrees * pi / 180.0F; }
}

void FirstPersonCamera::set_pitch_degrees(float pitch) noexcept {
    pitch_degrees_ = std::clamp(pitch, -84.0F, 84.0F);
}

void FirstPersonCamera::apply_mouse_delta(float dx, float dy) noexcept {
    yaw_degrees_ += dx * sensitivity_;
    pitch_degrees_ = std::clamp(pitch_degrees_ - dy * sensitivity_, -84.0F, 84.0F);
}

math::Vec3 FirstPersonCamera::forward() const noexcept {
    const float yaw = radians(yaw_degrees_);
    const float pitch = radians(pitch_degrees_);
    return math::normalize_or({std::cos(yaw) * std::cos(pitch),
                               std::sin(pitch),
                               std::sin(yaw) * std::cos(pitch)});
}

void FirstPersonCamera::move(float forward_axis, float right_axis, float vertical_axis,
                             float dt, bool sprint) noexcept {
    math::Vec3 flat_forward = forward();
    flat_forward.y = 0.0F;
    flat_forward = math::normalize_or(flat_forward);
    const math::Vec3 right = math::normalize_or(math::cross(flat_forward, {0.0F, 1.0F, 0.0F}), {1.0F, 0.0F, 0.0F});
    const float speed = sprint ? 7.5F : 3.6F;
    position_ += flat_forward * (forward_axis * speed * dt);
    position_ += right * (right_axis * speed * dt);
    position_.y += vertical_axis * speed * dt;
    position_.x = std::clamp(position_.x, -8.35F, 8.35F);
    position_.y = std::clamp(position_.y, 0.45F, 5.25F);
    position_.z = std::clamp(position_.z, -11.35F, 11.35F);
}

math::Mat4 FirstPersonCamera::view_projection(float aspect) const noexcept {
    const auto projection = math::perspective(radians(field_of_view_degrees_), aspect, 0.12F, 130.0F);
    const auto view = math::look_at(position_, position_ + forward(), {0.0F, 1.0F, 0.0F});
    return projection * view;
}

}  // namespace signalcloud::platform
