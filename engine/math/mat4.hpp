#pragma once

#include "engine/math/vec.hpp"

#include <array>
#include <cmath>

namespace signalcloud::math {

struct Mat4 {
    std::array<float, 16> m{};

    static Mat4 identity() noexcept {
        Mat4 out;
        out.m = {1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1};
        return out;
    }

    [[nodiscard]] const float* data() const noexcept { return m.data(); }
};

inline Mat4 operator*(const Mat4& a, const Mat4& b) noexcept {
    Mat4 out;
    for (int column = 0; column < 4; ++column) {
        for (int row = 0; row < 4; ++row) {
            float sum = 0.0F;
            for (int k = 0; k < 4; ++k) {
                sum += a.m[static_cast<std::size_t>(k * 4 + row)] *
                       b.m[static_cast<std::size_t>(column * 4 + k)];
            }
            out.m[static_cast<std::size_t>(column * 4 + row)] = sum;
        }
    }
    return out;
}

inline Mat4 perspective(float fov_y_radians, float aspect, float near_plane, float far_plane) noexcept {
    const float f = 1.0F / std::tan(fov_y_radians * 0.5F);
    Mat4 out{};
    out.m[0] = f / aspect;
    out.m[5] = f;
    out.m[10] = (far_plane + near_plane) / (near_plane - far_plane);
    out.m[11] = -1.0F;
    out.m[14] = (2.0F * far_plane * near_plane) / (near_plane - far_plane);
    return out;
}

inline Mat4 orthographic(float left, float right, float bottom, float top,
                         float near_plane, float far_plane) noexcept {
    Mat4 out = Mat4::identity();
    out.m[0] = 2.0F / (right - left);
    out.m[5] = 2.0F / (top - bottom);
    out.m[10] = -2.0F / (far_plane - near_plane);
    out.m[12] = -(right + left) / (right - left);
    out.m[13] = -(top + bottom) / (top - bottom);
    out.m[14] = -(far_plane + near_plane) / (far_plane - near_plane);
    return out;
}

inline Mat4 look_at(Vec3 eye, Vec3 target, Vec3 up) noexcept {
    const Vec3 forward = normalize_or(target - eye);
    const Vec3 side = normalize_or(cross(forward, up), {1.0F, 0.0F, 0.0F});
    const Vec3 corrected_up = cross(side, forward);

    Mat4 out = Mat4::identity();
    out.m[0] = side.x;
    out.m[4] = side.y;
    out.m[8] = side.z;
    out.m[1] = corrected_up.x;
    out.m[5] = corrected_up.y;
    out.m[9] = corrected_up.z;
    out.m[2] = -forward.x;
    out.m[6] = -forward.y;
    out.m[10] = -forward.z;
    out.m[12] = -dot(side, eye);
    out.m[13] = -dot(corrected_up, eye);
    out.m[14] = dot(forward, eye);
    return out;
}

}  // namespace signalcloud::math
