#pragma once

#include <algorithm>
#include <cmath>

namespace signalcloud::math {

struct Vec2 {
    float x{0.0F};
    float y{0.0F};
};

struct Vec3 {
    float x{0.0F};
    float y{0.0F};
    float z{0.0F};
};

inline Vec3 operator+(Vec3 a, Vec3 b) noexcept { return {a.x + b.x, a.y + b.y, a.z + b.z}; }
inline Vec3 operator-(Vec3 a, Vec3 b) noexcept { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
inline Vec3 operator*(Vec3 v, float scalar) noexcept { return {v.x * scalar, v.y * scalar, v.z * scalar}; }
inline Vec3 operator/(Vec3 v, float scalar) noexcept { return {v.x / scalar, v.y / scalar, v.z / scalar}; }
inline Vec3& operator+=(Vec3& a, Vec3 b) noexcept { a = a + b; return a; }

inline float dot(Vec3 a, Vec3 b) noexcept { return a.x * b.x + a.y * b.y + a.z * b.z; }
inline Vec3 cross(Vec3 a, Vec3 b) noexcept {
    return {a.y * b.z - a.z * b.y,
            a.z * b.x - a.x * b.z,
            a.x * b.y - a.y * b.x};
}
inline float length(Vec3 value) noexcept { return std::sqrt(dot(value, value)); }
inline Vec3 normalize_or(Vec3 value, Vec3 fallback = {0.0F, 0.0F, -1.0F}) noexcept {
    const float len = length(value);
    return len > 0.00001F ? value / len : fallback;
}
inline float clamp(float value, float low, float high) noexcept { return std::clamp(value, low, high); }

}  // namespace signalcloud::math
