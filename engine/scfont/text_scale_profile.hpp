#pragma once

#include <algorithm>

namespace signalcloud::font {

enum class SimpleTextRole {
    scui_menu,
    hud_compact,
    hud_menu,
    feedback,
};

// Screenshot-derived A6a2 readability profiles. Rich/world billboard text
// intentionally does not use this table and retains authored apparent size.
constexpr float simple_text_multiplier(SimpleTextRole role) noexcept {
    switch (role) {
        case SimpleTextRole::scui_menu: return 1.78F;   // +31.7% over A5's 0.82 conversion
        case SimpleTextRole::hud_compact: return 2.65F; // tower digits need the strongest lift
        case SimpleTextRole::hud_menu: return 2.20F;    // vending/menu numbers
        case SimpleTextRole::feedback: return 2.25F;    // transient confirmation values
    }
    return 1.0F;
}

constexpr float simple_text_scale(SimpleTextRole role, float authored_scale) noexcept {
    return authored_scale * simple_text_multiplier(role);
}

constexpr float simple_external_height(SimpleTextRole role, float authored_height) noexcept {
    return authored_height * simple_text_multiplier(role);
}

}  // namespace signalcloud::font
