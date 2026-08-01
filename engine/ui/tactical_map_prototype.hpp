#pragma once

#include "engine/math/mat4.hpp"

namespace signalcloud::world { class LiminalLevel; }

namespace signalcloud::legacy {

class TacticalMapPrototype {
public:
    [[nodiscard]] math::Mat4 view_projection(float aspect) const noexcept;
    [[nodiscard]] math::Mat4 view_projection(float aspect, const world::LiminalLevel& level) const noexcept;
    [[nodiscard]] const char* mode_label() const noexcept { return "LEGACY TACTICAL MAP / FUTURE LIDAR"; }
};

}  // namespace signalcloud::legacy
