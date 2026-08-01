#include "engine/ui/ar_interface.hpp"
#include "engine/scfont/text_point_adapter.hpp"
#include "engine/scfont/text_scale_profile.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <exception>
#include <iomanip>
#include <sstream>
#include <string>

namespace signalcloud::ui {
namespace {
constexpr float kPi = 3.14159265358979323846F;

render::PointGpu point(math::Vec3 p, float radius, float r, float g, float b,
                       float alpha = 1.0F, float density = 1.0F) noexcept {
    return {{p.x, p.y, p.z}, radius, {r, g, b, alpha}, {0.0F, 1.0F, 0.0F}, density};
}

void add_line(std::vector<render::PointGpu>& out, math::Vec3 a, math::Vec3 b,
              std::uint32_t count, float r, float g, float blue,
              float radius = 0.010F, float alpha = 0.96F) {
    if (count == 0U) return;
    for (std::uint32_t i = 0; i < count; ++i) {
        const float t = count == 1U ? 0.0F : static_cast<float>(i) / static_cast<float>(count - 1U);
        out.push_back(point(a + (b - a) * t, radius, r, g, blue, alpha, 1.0F));
    }
}

struct ScreenBasis {
    math::Vec3 center{};
    math::Vec3 right{};
    math::Vec3 up{};
};

ScreenBasis basis_for(const ArPose& pose, float distance = 0.70F) noexcept {
    const auto forward = math::normalize_or(pose.forward, {0.0F, 0.0F, -1.0F});
    const auto right = math::normalize_or(pose.right, {1.0F, 0.0F, 0.0F});
    const auto up = math::normalize_or(math::cross(right, forward), {0.0F, 1.0F, 0.0F});
    return {pose.camera_position + forward * distance, right, up};
}

math::Vec3 screen_point(const ScreenBasis& basis, float x, float y) noexcept {
    return basis.center + basis.right * x + basis.up * y;
}

void add_screen_line(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
                     float x0, float y0, float x1, float y1, std::uint32_t count,
                     float r, float g, float b, float radius = 0.009F,
                     float alpha = 0.92F) {
    add_line(out, screen_point(basis, x0, y0), screen_point(basis, x1, y1),
             count, r, g, b, radius, alpha);
}

void add_rect(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
              float left, float bottom, float right, float top,
              float r, float g, float b, float radius = 0.009F,
              float alpha = 0.92F) {
    add_screen_line(out, basis, left, bottom, right, bottom, 26U, r, g, b, radius, alpha);
    add_screen_line(out, basis, right, bottom, right, top, 18U, r, g, b, radius, alpha);
    add_screen_line(out, basis, right, top, left, top, 26U, r, g, b, radius, alpha);
    add_screen_line(out, basis, left, top, left, bottom, 18U, r, g, b, radius, alpha);
}

std::size_t add_filled_rect(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
                            float left, float bottom, float right, float top,
                            float step_x, float step_y, float r, float g, float b,
                            float alpha = 1.0F, float radius = 0.010F,
                            float density = 5.0F) {
    if (!(right > left) || !(top > bottom) || step_x <= 0.0F || step_y <= 0.0F) return 0U;
    const std::size_t columns = std::clamp<std::size_t>(
        static_cast<std::size_t>(std::ceil((right - left) / step_x)) + 1U, 2U, 96U);
    const std::size_t rows = std::clamp<std::size_t>(
        static_cast<std::size_t>(std::ceil((top - bottom) / step_y)) + 1U, 2U, 72U);
    const std::size_t before = out.size();
    for (std::size_t row = 0U; row < rows; ++row) {
        const float y = rows == 1U ? bottom :
            bottom + (top - bottom) * static_cast<float>(row) / static_cast<float>(rows - 1U);
        const float stagger = row % 2U == 0U ? 0.0F : step_x * 0.5F;
        for (std::size_t column = 0U; column < columns; ++column) {
            float x = columns == 1U ? left :
                left + (right - left) * static_cast<float>(column) / static_cast<float>(columns - 1U);
            x = std::min(right, x + stagger);
            out.push_back(point(screen_point(basis, x, y), radius, r, g, b, alpha, density));
        }
    }
    return out.size() - before;
}

void add_bar(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
             float left, float bottom, float width, float height, float ratio,
             float r, float g, float b) {
    ratio = std::clamp(ratio, 0.0F, 1.0F);
    add_rect(out, basis, left, bottom, left + width, bottom + height,
             r * 0.55F, g * 0.55F, b * 0.55F, 0.006F, 0.72F);
    constexpr int cells = 10;
    for (int i = 0; i < cells; ++i) {
        const float threshold = static_cast<float>(i + 1) / static_cast<float>(cells);
        if (ratio + 0.0001F < threshold) continue;
        const float x0 = left + 0.004F + static_cast<float>(i) * (width - 0.008F) / static_cast<float>(cells);
        const float x1 = left + 0.002F + static_cast<float>(i + 1) * (width - 0.008F) / static_cast<float>(cells);
        const float y = bottom + height * 0.5F;
        add_screen_line(out, basis, x0, y, x1, y, 8U, r, g, b, 0.008F, 0.90F);
    }
}

void add_vertical_bar(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
                      float left, float bottom, float width, float height, float ratio,
                      float r, float g, float b) {
    ratio = std::clamp(ratio, 0.0F, 1.0F);
    add_rect(out, basis, left, bottom, left + width, bottom + height,
             r * 0.50F, g * 0.50F, b * 0.50F, 0.006F, 0.72F);
    constexpr int cells = 10;
    const int filled = static_cast<int>(std::ceil(ratio * static_cast<float>(cells)));
    for (int i = 0; i < filled; ++i) {
        const float cell_height = (height - 0.008F) / static_cast<float>(cells);
        const float y = bottom + height - 0.004F -
                        (static_cast<float>(i) + 0.5F) * cell_height;
        add_screen_line(out, basis, left + 0.003F, y, left + width - 0.003F, y,
                        7U, r, g, b, 0.007F, 0.92F);
    }
}

void add_scanner_contact(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
                         ScannerContactKind kind, float x, float y, float size,
                         float strength, float pulse) {
    const float alpha = std::clamp(0.45F + strength * 0.45F + pulse, 0.45F, 1.0F);
    switch (kind) {
        case ScannerContactKind::room:
            add_rect(out, basis, x - size * 0.55F, y - size * 0.55F,
                     x + size * 0.55F, y + size * 0.55F,
                     0.30F, 0.92F, 1.0F, 0.007F, alpha);
            add_screen_line(out, basis, x, y - size * 0.55F, x, y + size * 0.20F,
                            10U, 0.30F, 0.92F, 1.0F, 0.006F, alpha);
            break;
        case ScannerContactKind::formed:
            add_screen_line(out, basis, x - size * 0.42F, y, x + size * 0.24F, y,
                            14U, 1.0F, 0.58F, 0.12F, 0.008F, alpha);
            add_screen_line(out, basis, x + size * 0.24F, y, x + size * 0.48F, y + size * 0.22F,
                            8U, 1.0F, 0.58F, 0.12F, 0.007F, alpha);
            for (float leg_x : {-0.28F, 0.12F}) {
                add_screen_line(out, basis, x + size * leg_x, y,
                                x + size * (leg_x - 0.08F), y - size * 0.45F,
                                9U, 1.0F, 0.58F, 0.12F, 0.007F, alpha);
                add_screen_line(out, basis, x + size * leg_x, y,
                                x + size * (leg_x + 0.12F), y - size * 0.45F,
                                9U, 1.0F, 0.58F, 0.12F, 0.007F, alpha);
            }
            break;
        case ScannerContactKind::formless:
            for (int i = 0; i < 28; ++i) {
                const float t = static_cast<float>(i) / 27.0F;
                const float px = x - size * 0.55F + t * size * 1.10F;
                const float py = y + std::sin(t * 3.0F * kPi + pulse * 8.0F) *
                                        size * (0.22F + 0.10F * std::sin(t * kPi));
                out.push_back(point(screen_point(basis, px, py), 0.008F,
                                    0.72F, 0.28F, 1.0F, alpha, 1.0F));
            }
            break;
        case ScannerContactKind::exchange:
            add_rect(out, basis, x - size * 0.42F, y - size * 0.50F,
                     x + size * 0.42F, y + size * 0.50F,
                     1.0F, 0.74F, 0.14F, 0.008F, alpha);
            add_screen_line(out, basis, x - size * 0.24F, y + size * 0.16F,
                            x + size * 0.24F, y + size * 0.16F,
                            10U, 1.0F, 0.74F, 0.14F, 0.007F, alpha);
            add_screen_line(out, basis, x, y - size * 0.30F, x, y + size * 0.30F,
                            10U, 1.0F, 0.74F, 0.14F, 0.007F, alpha);
            break;
        case ScannerContactKind::loot:
            for (int i = 0; i < 7; ++i) {
                const float angle = static_cast<float>(i) / 7.0F * 2.0F * kPi;
                const float px = x + std::cos(angle) * size * 0.34F;
                const float py = y + std::sin(angle) * size * 0.34F;
                out.push_back(point(screen_point(basis, px, py), 0.009F,
                                    0.28F, 1.0F, 0.48F, alpha, 1.0F));
            }
            break;
        case ScannerContactKind::none:
            break;
    }
}

constexpr std::array<std::array<bool, 7>, 10> kDigitSegments{{
    {{true, true, true, true, true, true, false}},
    {{false, true, true, false, false, false, false}},
    {{true, true, false, true, true, false, true}},
    {{true, true, true, true, false, false, true}},
    {{false, true, true, false, false, true, true}},
    {{true, false, true, true, false, true, true}},
    {{true, false, true, true, true, true, true}},
    {{true, true, true, false, false, false, false}},
    {{true, true, true, true, true, true, true}},
    {{true, true, true, true, false, true, true}},
}};

void add_digit(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
               int digit, float x, float y, float scale,
               float r, float g, float b, float alpha = 0.94F) {
    digit = std::clamp(digit, 0, 9);
    const float w = scale * 0.55F;
    const float h = scale;
    const float mid = y + h * 0.5F;
    const auto& s = kDigitSegments[static_cast<std::size_t>(digit)];
    if (s[0]) add_screen_line(out, basis, x, y + h, x + w, y + h, 10U, r, g, b, 0.006F, alpha);
    if (s[1]) add_screen_line(out, basis, x + w, y + h, x + w, mid, 10U, r, g, b, 0.006F, alpha);
    if (s[2]) add_screen_line(out, basis, x + w, mid, x + w, y, 10U, r, g, b, 0.006F, alpha);
    if (s[3]) add_screen_line(out, basis, x, y, x + w, y, 10U, r, g, b, 0.006F, alpha);
    if (s[4]) add_screen_line(out, basis, x, y, x, mid, 10U, r, g, b, 0.006F, alpha);
    if (s[5]) add_screen_line(out, basis, x, mid, x, y + h, 10U, r, g, b, 0.006F, alpha);
    if (s[6]) add_screen_line(out, basis, x, mid, x + w, mid, 10U, r, g, b, 0.006F, alpha);
}

void add_legacy_number(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
                int value, float x, float y, float scale,
                float r, float g, float b, int minimum_digits = 1) {
    value = std::clamp(value, -9999, 9999);
    const bool negative = value < 0;
    int absolute = std::abs(value);
    std::array<int, 5> digits{};
    int count = 0;
    do {
        digits[static_cast<std::size_t>(count++)] = absolute % 10;
        absolute /= 10;
    } while (absolute > 0 && count < 5);
    count = std::max(count, minimum_digits);
    float cursor = x;
    if (negative) {
        add_screen_line(out, basis, cursor, y + scale * 0.5F,
                        cursor + scale * 0.32F, y + scale * 0.5F,
                        8U, r, g, b, 0.006F, 0.95F);
        cursor += scale * 0.45F;
    }
    for (int i = count - 1; i >= 0; --i) {
        add_digit(out, basis, digits[static_cast<std::size_t>(i)], cursor, y,
                  scale, r, g, b);
        cursor += scale * 0.72F;
    }
}

void add_number(std::vector<render::PointGpu>& out, const signalcloud::font::Font* font,
                const ScreenBasis& basis, int value, float x, float y, float external_height,
                float r, float g, float b, int minimum_digits = 1,
                signalcloud::font::SimpleTextRole role = signalcloud::font::SimpleTextRole::hud_compact) {
    const float effective_height = signalcloud::font::simple_external_height(role, external_height);
    if (font != nullptr) {
        try {
            value = std::clamp(value, -9999, 9999);
            std::ostringstream stream;
            if (value < 0) {
                stream << '-';
                value = std::abs(value);
            }
            stream << std::setfill('0') << std::setw(std::max(1, minimum_digits)) << value;
            const float line_height = std::max(1.0F, font->metrics.line_height);
            const float font_scale = effective_height / line_height;
            signalcloud::font::TextBasis text_basis;
            text_basis.origin = screen_point(basis, x, y + effective_height);
            text_basis.right = basis.right * 1.04F;
            text_basis.up = basis.up;
            text_basis.depth = math::normalize_or(math::cross(text_basis.right, text_basis.up),
                                                  {0.0F, 0.0F, 1.0F});
            signalcloud::font::TextPointStyle style;
            style.point_radius = std::clamp(font_scale * 0.20F, 0.00082F, 0.00235F);
            style.opacity = 0.95F;
            style.tint = {r, g, b};
            style.replace_rgb = true;
            style.density = 1.05F;
            (void)signalcloud::font::append_simple_text_points(
                out, *font, stream.str(), text_basis, font_scale, style, 2'048U);
            return;
        } catch (const std::exception&) {
            // Preserve the established seven-segment emergency fallback.
        }
    }
    add_legacy_number(out, basis, value, x, y, effective_height, r, g, b, minimum_digits);
}

bool add_centered_rich_text(std::vector<render::PointGpu>& out,
                            const signalcloud::font::Font* font,
                            const ScreenBasis& basis, math::Vec3 depth,
                            std::string_view text, float center_x, float center_y,
                            float target_height, float r, float g, float b,
                            std::size_t maximum_points = 1'024U) {
    if (font == nullptr || target_height <= 0.0F) return false;
    try {
        const auto unit = signalcloud::font::layout_utf8(*font, text, 1.0F, maximum_points);
        if (unit.width <= 0.0001F || unit.height <= 0.0001F) return false;
        const float scale = target_height / unit.height;
        signalcloud::font::TextBasis text_basis;
        text_basis.right = basis.right;
        text_basis.up = basis.up;
        text_basis.depth = math::normalize_or(depth, {0.0F, 0.0F, -1.0F});
        text_basis.origin = screen_point(basis, center_x, center_y) -
            basis.right * (unit.width * scale * 0.5F) +
            basis.up * (unit.height * scale * 0.5F);
        signalcloud::font::TextPointStyle style;
        style.point_radius = std::clamp(scale * 0.21F, 0.00105F, 0.00255F);
        style.opacity = 0.98F;
        style.tint = {r, g, b};
        style.replace_rgb = true;
        style.density = 1.08F;
        return signalcloud::font::append_rich_text_points(
            out, *font, text, text_basis, scale, style, maximum_points) > 0U;
    } catch (const std::exception&) {
        return false;
    }
}

void add_check(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
               float x, float y, float size, float r, float g, float b,
               float alpha = 0.96F) {
    add_screen_line(out, basis, x - size, y, x - size * 0.24F, y - size * 0.72F,
                    14U, r, g, b, 0.009F, alpha);
    add_screen_line(out, basis, x - size * 0.24F, y - size * 0.72F,
                    x + size, y + size * 0.75F,
                    22U, r, g, b, 0.009F, alpha);
}

void add_chevron(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
                 float x, float y, float size, float r, float g, float b,
                 float alpha = 0.94F) {
    add_screen_line(out, basis, x - size, y + size * 0.45F, x, y - size * 0.45F,
                    16U, r, g, b, 0.010F, alpha);
    add_screen_line(out, basis, x, y - size * 0.45F, x + size, y + size * 0.45F,
                    16U, r, g, b, 0.010F, alpha);
}

void add_cross(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
               float x, float y, float size, float r, float g, float b,
               float alpha = 0.94F) {
    add_screen_line(out, basis, x - size, y, x + size, y, 14U, r, g, b, 0.008F, alpha);
    add_screen_line(out, basis, x, y - size, x, y + size, 14U, r, g, b, 0.008F, alpha);
}

void add_lock(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
              float x, float y, float r, float g, float b) {
    add_rect(out, basis, x - 0.026F, y - 0.025F, x + 0.026F, y + 0.020F,
             r, g, b, 0.008F, 0.95F);
    add_screen_line(out, basis, x - 0.017F, y + 0.020F, x - 0.017F, y + 0.047F,
                    10U, r, g, b, 0.007F, 0.95F);
    add_screen_line(out, basis, x + 0.017F, y + 0.020F, x + 0.017F, y + 0.047F,
                    10U, r, g, b, 0.007F, 0.95F);
    add_screen_line(out, basis, x - 0.017F, y + 0.047F, x + 0.017F, y + 0.047F,
                    12U, r, g, b, 0.007F, 0.95F);
}

void add_menu_icon(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
                   int product, float x, float y, bool selected) {
    const float alpha = selected ? 1.0F : 0.58F;
    if (product == 1) {
        add_screen_line(out, basis, x - 0.030F, y - 0.022F, x + 0.030F, y + 0.022F,
                        22U, 0.28F, 1.0F, 0.34F, 0.010F, alpha);
        add_screen_line(out, basis, x + 0.030F, y + 0.022F, x + 0.044F, y + 0.034F,
                        10U, 0.88F, 0.96F, 0.90F, 0.008F, alpha);
    } else if (product == 2) {
        for (int i = 0; i < 30; ++i) {
            const float t = static_cast<float>(i) / 29.0F;
            const float angle = t * 2.0F * kPi;
            const float width = 0.030F * (0.35F + 0.65F * std::sin(t * kPi));
            const float px = x + std::cos(angle) * width;
            const float py = y - 0.012F + std::sin(angle) * 0.042F;
            out.push_back(point(screen_point(basis, px, py), 0.008F,
                                0.20F, 0.78F, 1.0F, alpha, 1.0F));
        }
    } else {
        add_cross(out, basis, x, y, 0.032F, 0.82F, 0.34F, 1.0F, alpha);
    }
}

void danger_color(ArDangerKind kind, float& r, float& g, float& b) noexcept {
    r = 1.0F; g = 0.06F; b = 0.04F;
    if (kind == ArDangerKind::drowning) { r = 0.08F; g = 0.64F; b = 1.0F; }
    else if (kind == ArDangerKind::pressure) { r = 0.18F; g = 0.48F; b = 0.92F; }
    else if (kind == ArDangerKind::fall) { r = 0.94F; g = 0.96F; b = 1.0F; }
    else if (kind == ArDangerKind::poison) { r = 0.20F; g = 1.0F; b = 0.18F; }
    else if (kind == ArDangerKind::treason) { r = 0.70F; g = 0.20F; b = 1.0F; }
}

void add_low_health_mask(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
                         float health_ratio, ArDangerKind kind) {
    if (health_ratio > 0.15F) return;
    // At 3% health the mask intentionally stops advancing, preserving a small play window.
    const float clamped_health = std::max(health_ratio, 0.03F);
    const float danger = std::clamp((0.15F - clamped_health) / 0.12F, 0.0F, 1.0F);
    const float side_inset = 0.015F + danger * 0.155F;
    const float vertical_inset = std::max(0.0F, (danger - 0.42F) / 0.58F) * 0.115F;
    const float left = -0.56F;
    const float right = 0.56F;
    const float bottom = -0.32F;
    const float top = 0.32F;
    const float alpha = 0.28F + danger * 0.34F;
    float r, g, b;
    danger_color(kind, r, g, b);
    for (int layer = 0; layer < 4; ++layer) {
        const float offset = static_cast<float>(layer) * 0.008F;
        add_screen_line(out, basis, left + side_inset + offset, bottom,
                        left + side_inset + offset, top, 56U,
                        r, g, b, 0.012F, alpha);
        add_screen_line(out, basis, right - side_inset - offset, bottom,
                        right - side_inset - offset, top, 56U,
                        r, g, b, 0.012F, alpha);
        if (vertical_inset > 0.0F) {
            add_screen_line(out, basis, left, top - vertical_inset - offset,
                            right, top - vertical_inset - offset, 72U,
                            r, g, b, 0.011F, alpha * 0.82F);
            add_screen_line(out, basis, left, bottom + vertical_inset + offset,
                            right, bottom + vertical_inset + offset, 72U,
                            r, g, b, 0.011F, alpha * 0.82F);
        }
    }
}

}  // namespace

void ArInterface::update(float dt_seconds) noexcept {
    feedback_seconds_ = std::max(0.0F, feedback_seconds_ - std::max(0.0F, dt_seconds));
    if (feedback_seconds_ <= 0.0F) {
        feedback_kind_ = ArFeedbackKind::none;
        feedback_value_ = 0;
    }
}

void ArInterface::notify(ArFeedbackKind kind, int value) noexcept {
    feedback_kind_ = kind;
    feedback_value_ = value;
    feedback_seconds_ = kind == ArFeedbackKind::failure || kind == ArFeedbackKind::safe_lock
        ? 0.85F : 1.25F;
}

std::vector<render::PointGpu> ArInterface::build_points(
    float time_seconds, const ArPose& pose, const ArInterfaceData& data) const {
    std::vector<render::PointGpu> points;
    points.reserve(9'500U);
    const auto basis = basis_for(pose);
    const auto overlay_plate_basis = basis_for(pose, 0.712F);
    const auto overlay_rear_basis = basis_for(pose, 0.720F);

    add_low_health_mask(points, basis, data.health_ratio, data.danger_kind);

    // Bottom vitals move halfway into their remaining edge gap.
    add_bar(points, basis, -0.64F, -0.345F, 0.24F, 0.026F,
            data.health_ratio, 1.0F, 0.12F, 0.08F);
    add_bar(points, basis, 0.40F, -0.345F, 0.24F, 0.026F,
            data.oxygen_ratio, 0.16F, 0.78F, 1.0F);
    // Secondary state stays as a thin inner line instead of occupying the corners.
    add_bar(points, basis, -0.64F, -0.309F, 0.17F, 0.012F,
            data.sabs_ratio, 0.72F, 0.32F, 1.0F);
    add_bar(points, basis, 0.47F, -0.309F, 0.17F, 0.012F,
            1.0F - std::clamp(data.carry_ratio, 0.0F, 1.0F),
            1.0F, 0.72F, 0.18F);

    // Top-left XAR tower. The bar fills from top to bottom and the number sits to its right.
    const float xar_ratio = std::clamp(static_cast<float>(data.xar) / 100.0F, 0.0F, 1.0F);
    add_vertical_bar(points, basis, -0.642F, 0.188F, 0.018F, 0.116F,
                     xar_ratio, 1.0F, 0.76F, 0.16F);
    add_screen_line(points, basis, -0.606F, 0.272F, -0.582F, 0.296F,
                    10U, 0.98F, 0.78F, 0.16F, 0.006F, 0.92F);
    add_screen_line(points, basis, -0.582F, 0.272F, -0.606F, 0.296F,
                    10U, 0.98F, 0.78F, 0.16F, 0.006F, 0.92F);
    add_number(points, font_.get(), basis, static_cast<int>(std::clamp<std::int64_t>(data.xar, 0, 9999)),
               -0.575F, 0.180F, 0.036F, 1.0F, 0.78F, 0.18F, 2);

    // Top-right weapon tower. Pistol uses magazine ratio; prybar exposes its condition channel.
    const float weapon_ratio = data.weapon_slot == 1
        ? std::clamp(static_cast<float>(data.magazine) / 12.0F, 0.0F, 1.0F)
        : 1.0F;
    const float weapon_r = data.magazine <= 0 && data.weapon_slot == 1 ? 1.0F :
                           (data.magazine <= 3 && data.weapon_slot == 1 ? 1.0F : 0.24F);
    const float weapon_g = data.magazine <= 0 && data.weapon_slot == 1 ? 0.08F :
                           (data.magazine <= 3 && data.weapon_slot == 1 ? 0.72F : 1.0F);
    const float weapon_b = data.magazine <= 0 && data.weapon_slot == 1 ? 0.06F :
                           (data.magazine <= 3 && data.weapon_slot == 1 ? 0.30F : 0.30F);
    add_vertical_bar(points, basis, 0.624F, 0.188F, 0.018F, 0.116F,
                     weapon_ratio, weapon_r, weapon_g, weapon_b);
    if (data.weapon_slot == 1) {
        add_number(points, font_.get(), basis, data.magazine,
                   0.500F, 0.180F, 0.036F, weapon_r, weapon_g, weapon_b, 2);
    } else {
        add_screen_line(points, basis, 0.554F, 0.225F, 0.594F, 0.265F,
                        14U, 0.90F, 0.48F, 0.16F, 0.008F, 0.92F);
        add_screen_line(points, basis, 0.594F, 0.265F, 0.583F, 0.287F,
                        9U, 1.0F, 0.68F, 0.22F, 0.008F, 0.96F);
    }

    if (data.scanner_active) {
        const float scan_pulse = 0.08F * (0.5F + 0.5F * std::sin(time_seconds * 5.5F));
        add_rect(points, basis, -0.205F, 0.112F, 0.205F, 0.206F,
                 0.18F, 0.88F, 1.0F, 0.006F, 0.40F + scan_pulse);
        add_screen_line(points, basis, -0.190F, 0.124F,
                        -0.190F + 0.38F * std::clamp(data.scanner_strength, 0.0F, 1.0F),
                        0.124F, 32U, 0.18F, 0.88F, 1.0F, 0.007F, 0.90F);
        const int count = std::clamp(data.scanner_contact_count, 0, 4);
        if (count == 0) {
            add_cross(points, basis, 0.0F, 0.164F, 0.018F,
                      0.32F, 0.56F, 0.62F, 0.62F);
        } else {
            const float spacing = 0.090F;
            const float start = -0.5F * spacing * static_cast<float>(count - 1);
            for (int i = 0; i < count; ++i) {
                const auto& contact = data.scanner_contacts[static_cast<std::size_t>(i)];
                add_scanner_contact(points, basis, contact.kind,
                                    start + spacing * static_cast<float>(i), 0.166F,
                                    0.050F, contact.strength, scan_pulse);
            }
        }
    }

    if (data.interaction_near && !data.vending_menu) {
        const float pulse = 0.010F * std::sin(time_seconds * 5.0F);
        add_chevron(points, basis, 0.0F, -0.096F + pulse, 0.034F,
                    0.22F, 1.0F, 0.62F);
        // The interaction key is now a real Rich-text glyph. Two compact
        // point-native sheets sit entirely inside its square so room points
        // cannot show through the letter.
        add_filled_rect(points, overlay_rear_basis, -0.036F, -0.190F, 0.036F, -0.118F,
                        0.0065F, 0.0065F, 0.004F, 0.024F, 0.020F, 1.0F, 0.0060F, 5.2F);
        add_filled_rect(points, overlay_plate_basis, -0.033F, -0.187F, 0.033F, -0.121F,
                        0.0055F, 0.0055F, 0.010F, 0.050F, 0.038F, 1.0F, 0.0052F, 5.1F);
        add_rect(points, basis, -0.038F, -0.192F, 0.038F, -0.116F,
                 0.22F, 1.0F, 0.62F, 0.007F, 0.92F);
        if (!add_centered_rich_text(points, font_.get(), basis, pose.forward, "F",
                                    0.0F, -0.154F, 0.059F,
                                    0.22F, 1.0F, 0.62F, 1'024U)) {
            add_screen_line(points, basis, -0.010F, -0.177F, -0.010F, -0.131F,
                            12U, 0.22F, 1.0F, 0.62F, 0.007F, 0.96F);
            add_screen_line(points, basis, -0.010F, -0.131F, 0.015F, -0.131F,
                            10U, 0.22F, 1.0F, 0.62F, 0.007F, 0.96F);
            add_screen_line(points, basis, -0.010F, -0.151F, 0.009F, -0.151F,
                            9U, 0.22F, 1.0F, 0.62F, 0.007F, 0.96F);
        }
    }

    if (data.safe_room) add_lock(points, basis, 0.0F, 0.245F, 0.22F, 0.92F, 1.0F);

    if (data.vending_menu) {
        // The vending menu is an AR overlay, so it needs its own opaque
        // point-native backer instead of depending on the room behind it.
        add_filled_rect(points, overlay_rear_basis, -0.374F, -0.214F, 0.374F, 0.214F,
                        0.0160F, 0.0150F, 0.004F, 0.018F, 0.024F, 1.0F, 0.0120F, 5.2F);
        add_filled_rect(points, overlay_plate_basis, -0.368F, -0.208F, 0.368F, 0.208F,
                        0.0135F, 0.0135F, 0.008F, 0.038F, 0.042F, 1.0F, 0.0105F, 5.1F);
        add_rect(points, basis, -0.38F, -0.22F, 0.38F, 0.22F,
                 0.18F, 0.92F, 0.78F, 0.010F, 0.96F);
        for (int product = 1; product <= 3; ++product) {
            const float cx = -0.22F + static_cast<float>(product - 1) * 0.22F;
            const bool selected = product == data.menu_product;
            add_rect(points, basis, cx - 0.08F, -0.055F, cx + 0.08F, 0.12F,
                     selected ? 0.30F : 0.14F,
                     selected ? 1.0F : 0.50F,
                     selected ? 0.72F : 0.46F,
                     selected ? 0.010F : 0.006F,
                     selected ? 0.96F : 0.56F);
            add_menu_icon(points, basis, product, cx, 0.034F, selected);
        }
        // Confirm/cancel affordances are separated toward the lower corners,
        // away from the quantity and price values in the center.
        add_check(points, basis, -0.300F, -0.154F, 0.027F,
                  0.24F, 1.0F, 0.52F, 0.98F);
        add_cross(points, basis, 0.300F, -0.154F, 0.025F,
                  1.0F, 0.34F, 0.18F, 0.98F);
        add_number(points, font_.get(), basis, data.menu_quantity, -0.105F, -0.176F,
                   0.052F, 0.96F, 0.96F, 0.82F, 1,
                   signalcloud::font::SimpleTextRole::hud_menu);
        add_cross(points, basis, -0.028F, -0.145F, 0.010F,
                  0.96F, 0.96F, 0.82F, 0.92F);
        add_number(points, font_.get(), basis, data.menu_unit_price * data.menu_quantity,
                   0.020F, -0.176F, 0.052F, 1.0F, 0.72F, 0.18F, 1,
                   signalcloud::font::SimpleTextRole::hud_menu);
        add_screen_line(points, basis, 0.102F, -0.153F, 0.122F, -0.133F,
                        10U, 1.0F, 0.72F, 0.18F, 0.006F, 0.92F);
        add_screen_line(points, basis, 0.122F, -0.153F, 0.102F, -0.133F,
                        10U, 1.0F, 0.72F, 0.18F, 0.006F, 0.92F);
        const float cursor_x = std::clamp(data.menu_cursor_x, -0.34F, 0.34F);
        const float cursor_y = std::clamp(data.menu_cursor_y, -0.18F, 0.18F);
        add_cross(points, basis, cursor_x, cursor_y, 0.015F,
                  1.0F, 1.0F, 1.0F, 0.98F);
    }

    if (feedback_seconds_ > 0.0F) {
        float r = 0.22F, g = 1.0F, b = 0.54F;
        if (feedback_kind_ == ArFeedbackKind::sale) { r = 1.0F; g = 0.76F; b = 0.16F; }
        else if (feedback_kind_ == ArFeedbackKind::purchase) { r = 0.22F; g = 0.82F; b = 1.0F; }
        else if (feedback_kind_ == ArFeedbackKind::use) { r = 0.76F; g = 0.42F; b = 1.0F; }
        else if (feedback_kind_ == ArFeedbackKind::failure || feedback_kind_ == ArFeedbackKind::safe_lock) {
            r = 1.0F; g = 0.12F; b = 0.08F;
        }
        const float phase = std::clamp(feedback_seconds_ / 1.25F, 0.0F, 1.0F);
        const float spread = 0.04F + (1.0F - phase) * 0.08F;
        for (int i = 0; i < 64; ++i) {
            const float angle = static_cast<float>(i) / 64.0F * 2.0F * kPi;
            const float x = std::cos(angle) * spread;
            const float y = 0.106F + std::sin(angle) * spread;
            points.push_back(point(screen_point(basis, x, y), 0.009F,
                                   r, g, b, 0.45F + phase * 0.45F, 1.0F));
        }
        if (feedback_kind_ == ArFeedbackKind::failure || feedback_kind_ == ArFeedbackKind::safe_lock) {
            add_screen_line(points, basis, -0.030F, 0.076F, 0.030F, 0.136F,
                            20U, r, g, b, 0.010F, 0.96F);
            add_screen_line(points, basis, 0.030F, 0.076F, -0.030F, 0.136F,
                            20U, r, g, b, 0.010F, 0.96F);
        } else {
            const float feedback_height = signalcloud::font::simple_external_height(
                signalcloud::font::SimpleTextRole::feedback, 0.048F);
            add_number(points, font_.get(), basis, std::abs(feedback_value_), -0.025F,
                       0.106F - feedback_height * 0.5F,
                       0.048F, r, g, b, 1, signalcloud::font::SimpleTextRole::feedback);
        }
    }

    if (data.recovery_active) {
        float r, g, b;
        danger_color(data.danger_kind, r, g, b);
        const float blackout = std::clamp(data.blackout_strength, 0.0F, 1.0F);
        const float dim_alpha = 0.18F + blackout * 0.78F;
        for (int row = 0; row < 14; ++row) {
            const float y = -0.32F + static_cast<float>(row) * (0.64F / 13.0F);
            add_screen_line(points, basis, -0.56F, y, 0.56F, y, 120U,
                            0.0F, 0.0F, 0.0F, 0.013F, dim_alpha);
        }
        add_rect(points, basis, -0.22F, -0.022F, 0.22F, 0.022F,
                 r, g, b, 0.008F, 0.72F);
        add_screen_line(points, basis, -0.205F, 0.0F,
                        -0.205F + 0.41F * std::clamp(data.recovery_progress, 0.0F, 1.0F),
                        0.0F, 60U, r, g, b, 0.012F, 0.98F);
    }

    return points;
}

}  // namespace signalcloud::ui
