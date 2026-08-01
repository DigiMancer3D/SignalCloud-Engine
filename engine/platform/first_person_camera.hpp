#pragma once

#include "engine/math/mat4.hpp"
#include "engine/math/vec.hpp"

namespace signalcloud::platform {

class FirstPersonCamera {
public:
    void apply_mouse_delta(float dx, float dy) noexcept;
    void move(float forward_axis, float right_axis, float vertical_axis, float dt, bool sprint) noexcept;
    void set_position(math::Vec3 position) noexcept { position_ = position; }
    void set_yaw_degrees(float yaw) noexcept { yaw_degrees_ = yaw; }
    void set_pitch_degrees(float pitch) noexcept;

    [[nodiscard]] math::Vec3 position() const noexcept { return position_; }
    [[nodiscard]] math::Vec3 forward() const noexcept;
    [[nodiscard]] math::Mat4 view_projection(float aspect) const noexcept;
    [[nodiscard]] float yaw_degrees() const noexcept { return yaw_degrees_; }
    [[nodiscard]] float pitch_degrees() const noexcept { return pitch_degrees_; }

private:
    math::Vec3 position_{0.0F, 1.72F, 5.5F};
    float yaw_degrees_{-90.0F};
    float pitch_degrees_{0.0F};
    float field_of_view_degrees_{72.0F};
    float sensitivity_{0.095F};
};

}  // namespace signalcloud::platform
