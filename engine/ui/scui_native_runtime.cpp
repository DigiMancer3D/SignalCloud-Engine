#include "engine/ui/scui_native_runtime.hpp"

#include "engine/scfont/text_point_adapter.hpp"
#include "engine/scfont/text_scale_profile.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <charconv>
#include <cmath>
#include <exception>
#include <iomanip>
#include <limits>
#include <sstream>
#include <type_traits>
#include <utility>

namespace signalcloud::ui {
namespace {

constexpr float kPanelLeft = 0.015F;
constexpr float kPanelRight = 0.985F;
constexpr float kPanelTop = 0.018F;
constexpr float kPanelBottom = 0.982F;
constexpr float kRowsTop = 0.220F;
constexpr float kRowsBottom = 0.790F;
constexpr float kValueLeft = 0.535F;
constexpr float kValueRight = 0.915F;
constexpr float kLabelLeft = 0.055F;
constexpr float kLabelRight = 0.500F;

struct Color {
    float r{0.72F};
    float g{0.86F};
    float b{0.92F};
    float a{0.92F};
};

struct ScreenBasis {
    math::Vec3 center{};
    math::Vec3 right{};
    math::Vec3 up{};
};

render::PointGpu point(math::Vec3 position, float radius, Color color,
                       float density = 1.0F) noexcept {
    return {{position.x, position.y, position.z}, radius,
            {color.r, color.g, color.b, color.a}, {0.0F, 1.0F, 0.0F}, density};
}

ScreenBasis basis_for(const ArPose& pose, float distance = 0.665F) noexcept {
    const auto forward = math::normalize_or(pose.forward, {0.0F, 0.0F, -1.0F});
    const auto right = math::normalize_or(pose.right, {1.0F, 0.0F, 0.0F});
    const auto up = math::normalize_or(math::cross(right, forward), {0.0F, 1.0F, 0.0F});
    return {pose.camera_position + forward * distance, right, up};
}

float logical_x(float normalized_x) noexcept {
    return (normalized_x - 0.5F) * 1.58F;
}

float logical_y(float normalized_y) noexcept {
    return (0.5F - normalized_y) * 0.96F;
}

math::Vec3 screen_point(const ScreenBasis& basis, float normalized_x, float normalized_y) noexcept {
    return basis.center + basis.right * logical_x(normalized_x) + basis.up * logical_y(normalized_y);
}

void add_line(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
              float x0, float y0, float x1, float y1, std::uint32_t count,
              Color color, float radius = 0.0065F) {
    if (count == 0U) return;
    const auto start = screen_point(basis, x0, y0);
    const auto finish = screen_point(basis, x1, y1);
    for (std::uint32_t index = 0U; index < count; ++index) {
        const float t = count == 1U ? 0.0F : static_cast<float>(index) / static_cast<float>(count - 1U);
        out.push_back(point(start + (finish - start) * t, radius, color));
    }
}

void add_rect(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
              float left, float top, float right, float bottom,
              Color color, float radius = 0.0065F) {
    add_line(out, basis, left, top, right, top, 42U, color, radius);
    add_line(out, basis, right, top, right, bottom, 24U, color, radius);
    add_line(out, basis, right, bottom, left, bottom, 42U, color, radius);
    add_line(out, basis, left, bottom, left, top, 24U, color, radius);
}

void add_circle(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
                float center_x, float center_y, float circle_radius,
                std::uint32_t count, Color color, float point_radius = 0.0065F) {
    if (count < 3U || circle_radius <= 0.0F) return;
    constexpr float tau = 6.28318530718F;
    for (std::uint32_t index = 0U; index < count; ++index) {
        const float angle = tau * static_cast<float>(index) / static_cast<float>(count);
        out.push_back(point(screen_point(basis, center_x + std::cos(angle) * circle_radius,
                                         center_y + std::sin(angle) * circle_radius),
                            point_radius, color, 1.1F));
    }
}

std::size_t add_filled_rect(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
                            float left, float top, float right, float bottom,
                            float step_x, float step_y, Color color,
                            float radius = 0.0090F, float density = 1.20F) {
    if (!(right > left) || !(bottom > top) || step_x <= 0.0F || step_y <= 0.0F) return 0U;
    const std::size_t columns = std::clamp<std::size_t>(
        static_cast<std::size_t>(std::ceil((right - left) / step_x)) + 1U, 2U, 160U);
    const std::size_t rows = std::clamp<std::size_t>(
        static_cast<std::size_t>(std::ceil((bottom - top) / step_y)) + 1U, 2U, 120U);
    const std::size_t before = out.size();
    for (std::size_t row = 0U; row < rows; ++row) {
        const float y = rows == 1U ? top :
            top + (bottom - top) * static_cast<float>(row) / static_cast<float>(rows - 1U);
        const float stagger = (row % 2U == 0U) ? 0.0F : step_x * 0.5F;
        for (std::size_t column = 0U; column < columns; ++column) {
            float x = columns == 1U ? left :
                left + (right - left) * static_cast<float>(column) / static_cast<float>(columns - 1U);
            x = std::min(right, x + stagger);
            out.push_back(point(screen_point(basis, x, y), radius, color, density));
        }
    }
    return out.size() - before;
}

std::array<std::uint8_t, 7> glyph7(char raw) noexcept {
    const char c = static_cast<char>(std::toupper(static_cast<unsigned char>(raw)));
    switch (c) {
        case 'A': return {0x0E,0x11,0x11,0x1F,0x11,0x11,0x11};
        case 'B': return {0x1E,0x11,0x11,0x1E,0x11,0x11,0x1E};
        case 'C': return {0x0E,0x11,0x10,0x10,0x10,0x11,0x0E};
        case 'D': return {0x1E,0x11,0x11,0x11,0x11,0x11,0x1E};
        case 'E': return {0x1F,0x10,0x10,0x1E,0x10,0x10,0x1F};
        case 'F': return {0x1F,0x10,0x10,0x1E,0x10,0x10,0x10};
        case 'G': return {0x0E,0x11,0x10,0x17,0x11,0x11,0x0E};
        case 'H': return {0x11,0x11,0x11,0x1F,0x11,0x11,0x11};
        case 'I': return {0x1F,0x04,0x04,0x04,0x04,0x04,0x1F};
        case 'J': return {0x01,0x01,0x01,0x01,0x11,0x11,0x0E};
        case 'K': return {0x11,0x12,0x14,0x18,0x14,0x12,0x11};
        case 'L': return {0x10,0x10,0x10,0x10,0x10,0x10,0x1F};
        case 'M': return {0x11,0x1B,0x15,0x15,0x11,0x11,0x11};
        case 'N': return {0x11,0x19,0x15,0x13,0x11,0x11,0x11};
        case 'O': return {0x0E,0x11,0x11,0x11,0x11,0x11,0x0E};
        case 'P': return {0x1E,0x11,0x11,0x1E,0x10,0x10,0x10};
        case 'Q': return {0x0E,0x11,0x11,0x11,0x15,0x12,0x0D};
        case 'R': return {0x1E,0x11,0x11,0x1E,0x14,0x12,0x11};
        case 'S': return {0x0F,0x10,0x10,0x0E,0x01,0x01,0x1E};
        case 'T': return {0x1F,0x04,0x04,0x04,0x04,0x04,0x04};
        case 'U': return {0x11,0x11,0x11,0x11,0x11,0x11,0x0E};
        case 'V': return {0x11,0x11,0x11,0x11,0x11,0x0A,0x04};
        case 'W': return {0x11,0x11,0x11,0x15,0x15,0x15,0x0A};
        case 'X': return {0x11,0x11,0x0A,0x04,0x0A,0x11,0x11};
        case 'Y': return {0x11,0x11,0x0A,0x04,0x04,0x04,0x04};
        case 'Z': return {0x1F,0x01,0x02,0x04,0x08,0x10,0x1F};
        case '0': return {0x0E,0x11,0x13,0x15,0x19,0x11,0x0E};
        case '1': return {0x04,0x0C,0x04,0x04,0x04,0x04,0x0E};
        case '2': return {0x0E,0x11,0x01,0x02,0x04,0x08,0x1F};
        case '3': return {0x1E,0x01,0x01,0x0E,0x01,0x01,0x1E};
        case '4': return {0x02,0x06,0x0A,0x12,0x1F,0x02,0x02};
        case '5': return {0x1F,0x10,0x10,0x1E,0x01,0x01,0x1E};
        case '6': return {0x0E,0x10,0x10,0x1E,0x11,0x11,0x0E};
        case '7': return {0x1F,0x01,0x02,0x04,0x08,0x08,0x08};
        case '8': return {0x0E,0x11,0x11,0x0E,0x11,0x11,0x0E};
        case '9': return {0x0E,0x11,0x11,0x0F,0x01,0x01,0x0E};
        case '-': return {0x00,0x00,0x00,0x1F,0x00,0x00,0x00};
        case '_': return {0x00,0x00,0x00,0x00,0x00,0x00,0x1F};
        case '.': return {0x00,0x00,0x00,0x00,0x00,0x0C,0x0C};
        case ':': return {0x00,0x0C,0x0C,0x00,0x0C,0x0C,0x00};
        case '/': return {0x01,0x02,0x02,0x04,0x08,0x08,0x10};
        case '[': return {0x0E,0x08,0x08,0x08,0x08,0x08,0x0E};
        case ']': return {0x0E,0x02,0x02,0x02,0x02,0x02,0x0E};
        case '(': return {0x02,0x04,0x08,0x08,0x08,0x04,0x02};
        case ')': return {0x08,0x04,0x02,0x02,0x02,0x04,0x08};
        case '+': return {0x00,0x04,0x04,0x1F,0x04,0x04,0x00};
        case '%': return {0x19,0x1A,0x02,0x04,0x08,0x0B,0x13};
        case '>': return {0x08,0x04,0x02,0x01,0x02,0x04,0x08};
        case '<': return {0x02,0x04,0x08,0x10,0x08,0x04,0x02};
        case '=': return {0x00,0x00,0x1F,0x00,0x1F,0x00,0x00};
        case '?': return {0x0E,0x11,0x01,0x02,0x04,0x00,0x04};
        case '!': return {0x04,0x04,0x04,0x04,0x04,0x00,0x04};
        default: return {0x00,0x00,0x00,0x00,0x00,0x00,0x00};
    }
}

std::array<std::uint8_t, 9> glyph(char raw) noexcept {
    const auto base = glyph7(raw);
    // Expand the accepted 5x7 alphabet into a taller 5x9 point alphabet.
    // The duplicated cap and baseline rows improve recognition without
    // changing the character shapes or requiring texture fonts.
    return {base[0], base[0], base[1], base[2], base[3],
            base[4], base[5], base[6], base[6]};
}

std::string encode_utf8(const std::vector<std::uint32_t>& codepoints) {
    std::string result;
    for (std::uint32_t code : codepoints) {
        if (code <= 0x7FU) {
            result.push_back(static_cast<char>(code));
        } else if (code <= 0x7FFU) {
            result.push_back(static_cast<char>(0xC0U | (code >> 6U)));
            result.push_back(static_cast<char>(0x80U | (code & 0x3FU)));
        } else if (code <= 0xFFFFU) {
            result.push_back(static_cast<char>(0xE0U | (code >> 12U)));
            result.push_back(static_cast<char>(0x80U | ((code >> 6U) & 0x3FU)));
            result.push_back(static_cast<char>(0x80U | (code & 0x3FU)));
        } else {
            result.push_back(static_cast<char>(0xF0U | (code >> 18U)));
            result.push_back(static_cast<char>(0x80U | ((code >> 12U) & 0x3FU)));
            result.push_back(static_cast<char>(0x80U | ((code >> 6U) & 0x3FU)));
            result.push_back(static_cast<char>(0x80U | (code & 0x3FU)));
        }
    }
    return result;
}

std::string legacy_upper_truncated(std::string_view text, std::size_t maximum) {
    std::string result;
    result.reserve(std::min(maximum, text.size()));
    for (const char c : text) {
        if (result.size() >= maximum) break;
        const unsigned char byte = static_cast<unsigned char>(c);
        result.push_back(byte < 128U ? static_cast<char>(std::toupper(byte)) : '?');
    }
    return result;
}

std::string truncate_utf8(std::string_view text, std::size_t maximum) {
    auto codepoints = signalcloud::font::decode_utf8(text);
    if (codepoints.size() > maximum) codepoints.resize(maximum);
    return encode_utf8(codepoints);
}

std::vector<std::string> legacy_wrap_text(std::string_view text, std::size_t maximum_chars,
                                          std::size_t maximum_lines) {
    std::vector<std::string> result;
    if (maximum_chars == 0U || maximum_lines == 0U) return result;

    std::string normalized;
    normalized.reserve(text.size());
    bool pending_space = false;
    for (const char raw : text) {
        const unsigned char byte = static_cast<unsigned char>(raw);
        if (std::isspace(byte) != 0) {
            pending_space = !normalized.empty();
            continue;
        }
        if (pending_space) {
            normalized.push_back(' ');
            pending_space = false;
        }
        normalized.push_back(byte < 128U ? raw : '?');
    }
    if (normalized.empty()) return result;

    std::string current;
    std::size_t cursor = 0U;
    while (cursor < normalized.size()) {
        const std::size_t next_space = normalized.find(' ', cursor);
        const std::size_t word_end = next_space == std::string::npos ? normalized.size() : next_space;
        std::string word = normalized.substr(cursor, word_end - cursor);
        cursor = next_space == std::string::npos ? normalized.size() : next_space + 1U;

        while (word.size() > maximum_chars) {
            if (!current.empty()) {
                result.push_back(std::move(current));
                current.clear();
            }
            result.push_back(word.substr(0U, maximum_chars));
            word.erase(0U, maximum_chars);
        }
        if (word.empty()) continue;
        if (current.empty()) current = std::move(word);
        else if (current.size() + 1U + word.size() <= maximum_chars) {
            current.push_back(' ');
            current += word;
        } else {
            result.push_back(std::move(current));
            current = std::move(word);
        }
    }
    if (!current.empty()) result.push_back(std::move(current));

    if (result.size() > maximum_lines) {
        // Keep the last complete fitting line. The prior three-dot suffix
        // consumed usable width and made labels appear clipped before the
        // panel edge even when the final word itself would fit.
        result.resize(maximum_lines);
    }
    return result;
}

float font_text_width(const signalcloud::font::Font& font, std::string_view text, float scale) {
    try {
        return signalcloud::font::layout_utf8(font, text, scale, 8'192U).width;
    } catch (const std::exception&) {
        return std::numeric_limits<float>::infinity();
    }
}

std::vector<std::string> font_wrap_text(const signalcloud::font::Font& font,
                                        std::string_view text, float maximum_width,
                                        float scale, std::size_t maximum_lines) {
    std::vector<std::vector<std::uint32_t>> words;
    std::vector<std::uint32_t> word;
    for (const auto codepoint : signalcloud::font::decode_utf8(text)) {
        const bool whitespace = codepoint == '\n' || codepoint == '\r' || codepoint == '\t' || codepoint == ' ';
        if (whitespace) {
            if (!word.empty()) {
                words.push_back(std::move(word));
                word.clear();
            }
        } else {
            word.push_back(codepoint);
        }
    }
    if (!word.empty()) words.push_back(std::move(word));

    std::vector<std::string> lines;
    std::string current;
    for (const auto& codepoints : words) {
        std::string candidate_word = encode_utf8(codepoints);
        if (font_text_width(font, candidate_word, scale) > maximum_width) {
            std::vector<std::uint32_t> chunk;
            for (const auto codepoint : codepoints) {
                auto expanded = chunk;
                expanded.push_back(codepoint);
                if (!chunk.empty() && font_text_width(font, encode_utf8(expanded), scale) > maximum_width) {
                    if (!current.empty()) {
                        lines.push_back(std::move(current));
                        current.clear();
                    }
                    lines.push_back(encode_utf8(chunk));
                    chunk.clear();
                }
                chunk.push_back(codepoint);
            }
            candidate_word = encode_utf8(chunk);
        }
        const std::string candidate = current.empty() ? candidate_word : current + " " + candidate_word;
        if (current.empty() || font_text_width(font, candidate, scale) <= maximum_width) {
            current = candidate;
        } else {
            lines.push_back(std::move(current));
            current = candidate_word;
        }
    }
    if (!current.empty()) lines.push_back(std::move(current));
    if (lines.empty()) return lines;

    if (lines.size() > maximum_lines) {
        // Width-aware wrapping already guarantees every retained line fits.
        // Do not append an ellipsis: it steals the width of three glyphs and
        // caused the early cut-offs visible in the A6a2r1 screenshots.
        lines.resize(maximum_lines);
    }
    return lines;
}

void add_legacy_text(std::vector<render::PointGpu>& out, const ScreenBasis& basis,
                     float x, float y, std::string_view text, float scale, Color color,
                     std::size_t maximum = 42U) {
    float cursor = x;
    const float advance = scale * 6.8F;
    const std::string render_text = legacy_upper_truncated(text, maximum);
    for (const char c : render_text) {
        if (c == ' ') {
            cursor += advance;
            continue;
        }
        const auto rows = glyph(c);
        for (std::size_t row = 0U; row < rows.size(); ++row) {
            for (std::size_t column = 0U; column < 5U; ++column) {
                const std::uint8_t mask = static_cast<std::uint8_t>(1U << (4U - column));
                if ((rows[row] & mask) == 0U) continue;
                const float nx = cursor + static_cast<float>(column) * scale;
                const float ny = y + static_cast<float>(row) * scale;
                out.push_back(point(screen_point(basis, nx, ny),
                                    std::clamp(scale * 0.31F, 0.00085F, 0.00165F), color));
            }
        }
        cursor += advance;
    }
}

void add_text(std::vector<render::PointGpu>& out, const signalcloud::font::Font* font,
              const ScreenBasis& basis, float x, float y, std::string_view text,
              float scale, Color color, std::size_t maximum = 42U) {
    if (font != nullptr) {
        try {
            // The caller's legacy scale represents roughly one row in the old
            // nine-row alphabet. Convert it to the SCFONT line metric so the
            // external text keeps the same outer height while retaining the
            // font's authored Advance and character spacing.
            const float font_scale = signalcloud::font::simple_text_scale(
                signalcloud::font::SimpleTextRole::scui_menu, scale);
            signalcloud::font::TextBasis text_basis;
            text_basis.origin = screen_point(basis, x, y);
            text_basis.right = basis.right * 1.08F;
            text_basis.up = basis.up;
            text_basis.depth = math::normalize_or(math::cross(text_basis.right, text_basis.up),
                                                  {0.0F, 0.0F, 1.0F});
            signalcloud::font::TextPointStyle style;
            // Keep each sprite clearly below the one-grid-unit separation.
            // A5a3r1 used 0.58x and compressed Y to 0.70x, which made adjacent
            // rows overlap into the unreadable blocks shown in the screenshots.
            style.point_radius = std::clamp(font_scale * 0.20F, 0.00078F, 0.00215F);
            style.opacity = color.a;
            style.tint = {color.r, color.g, color.b};
            style.replace_rgb = true;
            style.density = 1.05F;
            const std::string render_text = truncate_utf8(text, maximum);
            (void)signalcloud::font::append_simple_text_points(
                out, *font, render_text, text_basis, font_scale, style, 4'096U);
            return;
        } catch (const std::exception&) {
            // The emergency hard-coded alphabet remains available when a font
            // is absent, malformed, or exceeds a local layout budget.
        }
    }
    add_legacy_text(
        out, basis, x, y, text,
        signalcloud::font::simple_text_scale(signalcloud::font::SimpleTextRole::scui_menu, scale),
        color, maximum);
}

void add_right_aligned_text(std::vector<render::PointGpu>& out,
                            const signalcloud::font::Font* font,
                            const ScreenBasis& basis, float right, float y,
                            std::string_view text, float scale, Color color,
                            std::size_t maximum = 42U) {
    float normalized_width = 0.0F;
    if (font != nullptr) {
        const float font_scale = signalcloud::font::simple_text_scale(
            signalcloud::font::SimpleTextRole::scui_menu, scale);
        const float world_width = font_text_width(*font, truncate_utf8(text, maximum), font_scale) * 1.08F;
        if (std::isfinite(world_width)) normalized_width = world_width / 1.58F;
    } else {
        const float legacy_scale = signalcloud::font::simple_text_scale(
            signalcloud::font::SimpleTextRole::scui_menu, scale);
        normalized_width = static_cast<float>(std::min(maximum, text.size())) * legacy_scale * 6.8F / 1.58F;
    }
    add_text(out, font, basis, std::max(kPanelLeft + 0.030F, right - normalized_width),
             y, text, scale, color, maximum);
}

std::size_t add_wrapped_text(std::vector<render::PointGpu>& out,
                             const signalcloud::font::Font* font,
                             const ScreenBasis& basis, float left, float top, float right,
                             std::string_view text, float scale, Color color,
                             std::size_t maximum_lines = 2U, float line_step = 0.032F) {
    if (!(right > left) || scale <= 0.0F || maximum_lines == 0U) return 0U;
    std::vector<std::string> lines;
    if (font != nullptr) {
        lines = font_wrap_text(
            *font, text, right - left,
            signalcloud::font::simple_text_scale(signalcloud::font::SimpleTextRole::scui_menu, scale),
            maximum_lines);
    } else {
        const float advance = scale * 6.8F;
        const std::size_t maximum_chars = std::max<std::size_t>(1U,
            static_cast<std::size_t>(std::floor((right - left) / advance)));
        lines = legacy_wrap_text(text, maximum_chars, maximum_lines);
    }
    for (std::size_t index = 0U; index < lines.size(); ++index) {
        add_text(out, font, basis, left, top + static_cast<float>(index) * line_step,
                 lines[index], scale, color, 96U);
    }
    return lines.size();
}

Color style_color(std::string_view role, bool focused, bool enabled) noexcept {
    if (!enabled) return {0.30F, 0.34F, 0.38F, 0.58F};
    if (focused) return {0.96F, 0.76F, 0.18F, 1.0F};
    if (role == "primary") return {0.20F, 0.92F, 1.0F, 0.94F};
    if (role == "action") return {0.34F, 1.0F, 0.54F, 0.96F};
    if (role == "status") return {0.52F, 0.82F, 1.0F, 0.92F};
    if (role == "warning") return {1.0F, 0.34F, 0.18F, 0.96F};
    if (role == "info") return {0.62F, 0.72F, 0.88F, 0.88F};
    return {0.70F, 0.88F, 0.92F, 0.90F};
}

std::string escape_json(std::string_view text) {
    std::string result;
    result.reserve(text.size() + 8U);
    for (const char c : text) {
        switch (c) {
            case '\\': result += "\\\\"; break;
            case '"': result += "\\\""; break;
            case '\n': result += "\\n"; break;
            case '\r': result += "\\r"; break;
            case '\t': result += "\\t"; break;
            default: result.push_back(c); break;
        }
    }
    return result;
}

std::string format_number(double value) {
    std::ostringstream out;
    const double rounded = std::round(value);
    if (std::abs(value - rounded) < 0.000001) {
        out << static_cast<long long>(rounded);
    } else {
        out << std::fixed << std::setprecision(2) << value;
        std::string text = out.str();
        while (!text.empty() && text.back() == '0') text.pop_back();
        if (!text.empty() && text.back() == '.') text.pop_back();
        return text;
    }
    return out.str();
}

bool finite_normalized(float value) noexcept {
    return std::isfinite(value) && value >= 0.0F && value <= 1.0F;
}

}  // namespace

ScuiNativeRuntime::ScuiNativeRuntime(ScuiPanel panel, std::size_t rows_per_page)
    : panel_(std::move(panel)),
      layout_(ScuiNativeLayout::build(panel_, std::max<std::size_t>(1U, rows_per_page))),
      rows_per_page_(std::max<std::size_t>(1U, rows_per_page)) {
    for (const auto& [binding, raw] : panel_.initial_values) {
        values_[binding] = parse_value(raw);
    }
    normalize_focus();
}

std::string_view ScuiNativeRuntime::focused_control_id() const noexcept {
    if (layout_.focus_order.empty() || focus_index_ >= layout_.focus_order.size()) return {};
    return layout_.focus_order[focus_index_];
}

ScuiNativeRuntimeStats ScuiNativeRuntime::stats() const noexcept {
    return {layout_.page_count, current_page_, layout_.focus_order.size(), last_generated_points_,
            last_backplate_points_, last_wrapped_text_lines_, last_notice_points_,
            dispatched_events_, blocked_commands_};
}

void ScuiNativeRuntime::set_open(bool open) noexcept {
    open_ = open && valid();
    pointer_visible_ = false;
    if (!open_) clear_notice();
    normalize_focus();
}

bool ScuiNativeRuntime::register_command(std::string command_id) {
    return command_registry_.register_command(std::move(command_id));
}

bool ScuiNativeRuntime::command_allowed(std::string_view command_id) const noexcept {
    return command_registry_.contains(command_id);
}

bool ScuiNativeRuntime::handle_key(ScuiNativeKey key) {
    if (!open_) return false;
    switch (key) {
        case ScuiNativeKey::focus_previous: return move_focus(-1);
        case ScuiNativeKey::focus_next: return move_focus(1);
        case ScuiNativeKey::page_previous: return move_page(-1);
        case ScuiNativeKey::page_next: return move_page(1);
        case ScuiNativeKey::cancel:
            set_open(false);
            return true;
        case ScuiNativeKey::adjust_previous:
        case ScuiNativeKey::adjust_next:
        case ScuiNativeKey::confirm: {
            const auto* control = focused_control();
            if (control == nullptr) return false;
            const int direction = key == ScuiNativeKey::adjust_previous ? -1
                : (key == ScuiNativeKey::adjust_next ? 1 : 0);
            return activate_control(*control, direction, false);
        }
    }
    return false;
}

bool ScuiNativeRuntime::handle_pointer_move(float normalized_x, float normalized_y) noexcept {
    if (!open_ || !finite_normalized(normalized_x) || !finite_normalized(normalized_y)) return false;
    pointer_x_ = normalized_x;
    pointer_y_ = normalized_y;
    pointer_visible_ = true;
    const auto* row = row_at_pointer(normalized_y);
    if (row != nullptr && normalized_x >= kPanelLeft && normalized_x <= kPanelRight && row->focusable) {
        return focus_control(row->control_id);
    }
    return true;
}

bool ScuiNativeRuntime::handle_pointer_activate(float normalized_x, float normalized_y) {
    if (!open_ || !finite_normalized(normalized_x) || !finite_normalized(normalized_y)) return false;
    pointer_x_ = normalized_x;
    pointer_y_ = normalized_y;
    pointer_visible_ = true;

    if (normalized_y >= 0.80F && normalized_y <= 0.90F) {
        if (normalized_x < 0.45F) return move_page(-1);
        if (normalized_x > 0.55F) return move_page(1);
    }

    const auto* row = row_at_pointer(normalized_y);
    if (row == nullptr || normalized_x < kPanelLeft || normalized_x > kPanelRight) return false;
    (void)focus_control(row->control_id);
    const auto* control = panel_.control(row->control_id);
    if (control == nullptr || !control->enabled) return false;
    return activate_control(*control, 1, true, normalized_x);
}

bool ScuiNativeRuntime::handle_wheel(float delta) {
    if (!open_ || delta == 0.0F) return false;
    const auto* control = focused_control();
    if (control != nullptr && (control->type == ScuiControlType::slider ||
                               control->type == ScuiControlType::number ||
                               control->type == ScuiControlType::dropdown ||
                               control->type == ScuiControlType::radio ||
                               control->type == ScuiControlType::list)) {
        return activate_control(*control, delta > 0.0F ? 1 : -1, false);
    }
    return move_focus(delta > 0.0F ? -1 : 1);
}

bool ScuiNativeRuntime::set_number(std::string_view binding, double value) {
    if (binding.empty() || !std::isfinite(value)) return false;
    values_[std::string(binding)] = value;
    return true;
}

bool ScuiNativeRuntime::set_boolean(std::string_view binding, bool value) {
    if (binding.empty()) return false;
    values_[std::string(binding)] = value;
    return true;
}

bool ScuiNativeRuntime::set_string(std::string_view binding, std::string value) {
    if (binding.empty()) return false;
    values_[std::string(binding)] = std::move(value);
    return true;
}

bool ScuiNativeRuntime::set_choices(std::string_view control_id, std::vector<std::string> choices,
                                     std::optional<std::string> selected) {
    if (control_id.empty() || choices.empty()) return false;
    auto match = std::find_if(panel_.controls.begin(), panel_.controls.end(), [control_id](const ScuiControl& control) {
        return control.id == control_id;
    });
    if (match == panel_.controls.end()) return false;
    choices.erase(std::remove_if(choices.begin(), choices.end(), [](const std::string& value) {
        return value.empty();
    }), choices.end());
    std::sort(choices.begin(), choices.end());
    choices.erase(std::unique(choices.begin(), choices.end()), choices.end());
    if (choices.empty()) return false;
    match->choices = std::move(choices);
    if (!match->value_binding.empty()) {
        std::string next = selected.value_or(string(match->value_binding).value_or(match->choices.front()));
        if (std::find(match->choices.begin(), match->choices.end(), next) == match->choices.end()) {
            next = match->choices.front();
        }
        (void)set_string(match->value_binding, std::move(next));
    }
    return true;
}

void ScuiNativeRuntime::show_notice(ScuiNativeNoticeKind kind, std::string message,
                                     float current_time_seconds, float duration_seconds) {
    notice_kind_ = kind;
    notice_message_ = std::move(message);
    notice_started_seconds_ = current_time_seconds;
    notice_duration_seconds_ = std::clamp(duration_seconds, 0.4F, 6.0F);
    notice_until_seconds_ = current_time_seconds + notice_duration_seconds_;
}

void ScuiNativeRuntime::clear_notice() noexcept {
    notice_message_.clear();
    notice_started_seconds_ = 0.0F;
    notice_duration_seconds_ = 0.0F;
    notice_until_seconds_ = 0.0F;
    last_notice_points_ = 0U;
}

std::optional<double> ScuiNativeRuntime::number(std::string_view binding) const noexcept {
    const auto match = values_.find(binding);
    if (match == values_.end()) return std::nullopt;
    if (const auto* value = std::get_if<double>(&match->second)) return *value;
    return std::nullopt;
}

std::optional<bool> ScuiNativeRuntime::boolean(std::string_view binding) const noexcept {
    const auto match = values_.find(binding);
    if (match == values_.end()) return std::nullopt;
    if (const auto* value = std::get_if<bool>(&match->second)) return *value;
    return std::nullopt;
}

std::optional<std::string> ScuiNativeRuntime::string(std::string_view binding) const {
    const auto match = values_.find(binding);
    if (match == values_.end()) return std::nullopt;
    if (const auto* value = std::get_if<std::string>(&match->second)) return *value;
    return std::nullopt;
}

std::string ScuiNativeRuntime::display_value(const ScuiControl& control) const {
    if (control.value_binding.empty()) {
        return control.type == ScuiControlType::button || control.type == ScuiControlType::confirmation
            ? "RUN" : "";
    }
    const Value value = value_for_binding(control.value_binding);
    if (const auto* boolean_value = std::get_if<bool>(&value)) return *boolean_value ? "ON" : "OFF";
    if (const auto* number_value = std::get_if<double>(&value)) return format_number(*number_value);
    if (const auto* string_value = std::get_if<std::string>(&value)) return *string_value;
    return "--";
}

std::map<std::string, std::string, std::less<>> ScuiNativeRuntime::state_json() const {
    std::map<std::string, std::string, std::less<>> result;
    for (const auto& [binding, value] : values_) {
        result[binding] = std::visit([](const auto& item) -> std::string {
            using T = std::decay_t<decltype(item)>;
            if constexpr (std::is_same_v<T, std::monostate>) return "null";
            if constexpr (std::is_same_v<T, bool>) return item ? "true" : "false";
            if constexpr (std::is_same_v<T, double>) return format_number(item);
            if constexpr (std::is_same_v<T, std::string>) return "\"" + escape_json(item) + "\"";
            return "null";
        }, value);
    }
    return result;
}

void ScuiNativeRuntime::apply_state_json(
    const std::map<std::string, std::string, std::less<>>& values) {
    for (const auto& [binding, raw] : values) {
        const Value parsed = parse_value(raw);
        if (!std::holds_alternative<std::monostate>(parsed)) values_[binding] = parsed;
    }
}

std::vector<render::PointGpu> ScuiNativeRuntime::build_points(
    float time_seconds, const ArPose& pose) const {
    std::vector<render::PointGpu> out;
    if (!open_ || !valid()) {
        last_generated_points_ = 0U;
        last_backplate_points_ = 0U;
        last_wrapped_text_lines_ = 0U;
        last_notice_points_ = 0U;
        return out;
    }
    out.reserve(24'000U);
    const auto basis = basis_for(pose);
    const auto row_plate_basis = basis_for(pose, 0.676F);
    const auto panel_plate_basis = basis_for(pose, 0.684F);
    const auto panel_rear_basis = basis_for(pose, 0.694F);
    const float pulse = 0.04F * (0.5F + 0.5F * std::sin(time_seconds * 4.0F));
    const Color border{0.18F, 0.88F, 1.0F, 0.94F};
    const Color subtle{0.18F, 0.42F, 0.52F, 0.28F};
    const Color title_color{0.82F, 0.96F, 1.0F, 0.98F};
    std::size_t backplate_points = 0U;
    std::size_t wrapped_text_lines = 0U;
    std::size_t notice_points = 0U;

    // Two interleaved, depth-separated sheets make the point-native backer
    // visually opaque without turning it into a texture quad. The rear sheet
    // uses a slightly cooler hue and shifted bounds so world signs and room
    // points cannot align with holes in the front lattice.
    backplate_points += add_filled_rect(
        out, panel_rear_basis,
        kPanelLeft + 0.002F, kPanelTop + 0.004F,
        kPanelRight - 0.010F, kPanelBottom - 0.012F,
        0.0115F, 0.0125F, {0.006F, 0.012F, 0.024F, 1.0F}, 0.0106F, 5.10F);
    backplate_points += add_filled_rect(
        out, panel_plate_basis,
        kPanelLeft + 0.006F, kPanelTop + 0.008F,
        kPanelRight - 0.006F, kPanelBottom - 0.008F,
        0.0098F, 0.0112F, {0.012F, 0.022F, 0.036F, 1.0F}, 0.0098F, 5.05F);
    backplate_points += add_filled_rect(
        out, panel_plate_basis,
        kPanelLeft + 0.020F, 0.096F,
        kPanelRight - 0.020F, 0.226F,
        0.0110F, 0.0130F, {0.015F, 0.040F, 0.055F, 0.92F}, 0.0092F, 5.00F);
    backplate_points += add_filled_rect(
        out, panel_plate_basis,
        kPanelLeft + 0.020F, 0.770F,
        kPanelRight - 0.020F, 0.902F,
        0.0110F, 0.0130F, {0.012F, 0.032F, 0.046F, 0.94F}, 0.0092F, 5.00F);

    add_rect(out, basis, kPanelLeft, kPanelTop, kPanelRight, kPanelBottom, border, 0.0075F);
    add_rect(out, basis, kPanelLeft + 0.008F, kPanelTop + 0.010F,
             kPanelRight - 0.008F, kPanelBottom - 0.010F, subtle, 0.0045F);
    for (int line = 0; line < 12; ++line) {
        const float y = kPanelTop + 0.035F + static_cast<float>(line) * 0.065F;
        add_line(out, basis, kPanelLeft + 0.014F, y, kPanelRight - 0.014F, y,
                 58U, {0.10F, 0.34F, 0.42F, 0.10F + pulse}, 0.0038F);
    }

    const std::size_t title_lines = add_wrapped_text(
        out, font_.get(), basis, 0.055F, 0.062F, 0.945F, panel_.title,
        0.00425F, title_color, 2U, 0.070F);
    wrapped_text_lines += title_lines;

    const float row_height = (kRowsBottom - kRowsTop) / static_cast<float>(rows_per_page_);
    for (const auto& row : layout_.rows) {
        if (row.page != current_page_) continue;
        const auto* control = panel_.control(row.control_id);
        if (control == nullptr) continue;
        const float top = kRowsTop + static_cast<float>(row.row) * row_height + 0.006F;
        const float bottom = top + row_height - 0.012F;
        const bool focused = row.control_id == focused_control_id();
        const Color color = style_color(control->style_role, focused, control->enabled);
        const Color frame_color{color.r, color.g, color.b, focused ? 0.98F : 0.58F};
        const Color row_fill = focused
            ? Color{0.18F, 0.105F, 0.018F, 0.72F}
            : Color{0.018F, 0.050F, 0.064F, 0.62F};
        backplate_points += add_filled_rect(
            out, row_plate_basis, 0.034F, top + 0.003F, 0.966F, bottom - 0.003F,
            0.0120F, 0.0140F, row_fill, 0.0089F, 5.00F);
        add_rect(out, basis, 0.032F, top, 0.968F, bottom, frame_color,
                 focused ? 0.0075F : 0.0052F);
        if (focused) {
            add_line(out, basis, 0.041F, top + 0.009F, 0.041F, bottom - 0.009F,
                     18U, {1.0F, 0.72F, 0.16F, 0.98F}, 0.009F);
        }

        const std::string label = control->label.empty() ? control->id : control->label;
        const bool full_width_label = control->type == ScuiControlType::label;
        wrapped_text_lines += add_wrapped_text(
            out, font_.get(), basis, kLabelLeft, top + 0.016F,
            full_width_label ? 0.950F : kLabelRight,
            label, full_width_label ? 0.00318F : 0.00305F, color,
            2U, full_width_label ? 0.0580F : 0.0560F);

        const std::string value = display_value(*control);
        if (control->type == ScuiControlType::toggle) {
            add_rect(out, basis, 0.800F, top + 0.020F, 0.865F, bottom - 0.020F, color, 0.006F);
            if (boolean(control->value_binding).value_or(false)) {
                add_line(out, basis, 0.762F, top + 0.055F, 0.780F, bottom - 0.032F,
                         10U, color, 0.007F);
                add_line(out, basis, 0.780F, bottom - 0.032F, 0.808F, top + 0.030F,
                         12U, color, 0.007F);
            }
            add_text(out, font_.get(), basis, 0.878F, top + 0.024F, value, 0.0033F, color, 5U);
        } else if (control->type == ScuiControlType::slider ||
                   control->type == ScuiControlType::number ||
                   control->type == ScuiControlType::progress) {
            const double low = control->minimum.value_or(0.0);
            const double high = control->maximum.value_or(100.0);
            const double current = number(control->value_binding).value_or(low);
            const float ratio = high > low
                ? static_cast<float>(std::clamp((current - low) / (high - low), 0.0, 1.0)) : 0.0F;
            const float bar_y = (top + bottom) * 0.5F + 0.010F;
            add_line(out, basis, kValueLeft, bar_y, kValueRight, bar_y, 30U,
                     {color.r * 0.45F, color.g * 0.45F, color.b * 0.45F, 0.72F}, 0.005F);
            add_line(out, basis, kValueLeft, bar_y,
                     kValueLeft + (kValueRight - kValueLeft) * ratio, bar_y,
                     std::max<std::uint32_t>(2U, static_cast<std::uint32_t>(30.0F * ratio)),
                     color, 0.007F);
            if (control->type != ScuiControlType::progress) {
                const float marker = kValueLeft + (kValueRight - kValueLeft) * ratio;
                add_line(out, basis, marker, bar_y - 0.026F, marker, bar_y + 0.026F,
                         12U, color, 0.008F);
            }
            add_text(out, font_.get(), basis, 0.668F, top + 0.012F, value, 0.0030F, color, 14U);
        } else if (control->type == ScuiControlType::dropdown ||
                   control->type == ScuiControlType::radio ||
                   control->type == ScuiControlType::list) {
            add_text(out, font_.get(), basis, 0.585F, top + 0.024F, "<", 0.0038F, color, 2U);
            wrapped_text_lines += add_wrapped_text(
                out, font_.get(), basis, 0.575F, top + 0.014F, 0.900F, value,
                0.00295F, color, 2U, 0.0540F);
            add_text(out, font_.get(), basis, 0.925F, top + 0.024F, ">", 0.0038F, color, 2U);
        } else if (control->type == ScuiControlType::button ||
                   control->type == ScuiControlType::confirmation) {
            add_rect(out, basis, 0.720F, top + 0.018F, 0.930F, bottom - 0.018F, color, 0.006F);
            add_text(out, font_.get(), basis, 0.770F, top + 0.026F, value, 0.0035F, color, 8U);
        } else if (!value.empty() && !full_width_label) {
            wrapped_text_lines += add_wrapped_text(
                out, font_.get(), basis, 0.540F, top + 0.016F, 0.930F, value,
                0.00295F, color, 2U, 0.0540F);
        }
    }

    const std::string page = "PAGE " + std::to_string(current_page_ + 1U) + "/" +
        std::to_string(std::max<std::size_t>(1U, layout_.page_count));
    add_text(out, font_.get(), basis, 0.405F, 0.795F, page, 0.0039F,
             {0.88F, 0.92F, 1.0F, 0.92F}, 14U);
    add_text(out, font_.get(), basis, 0.145F, 0.850F, "< PAGE", 0.0034F,
             current_page_ > 0U ? border : Color{0.30F,0.34F,0.38F,0.45F}, 8U);
    add_text(out, font_.get(), basis, 0.730F, 0.850F, "PAGE >", 0.0034F,
             current_page_ + 1U < layout_.page_count ? border : Color{0.30F,0.34F,0.38F,0.45F}, 8U);

    const Color footer_color{0.48F, 0.70F, 0.76F, 0.82F};
    add_text(out, font_.get(), basis, 0.055F, 0.925F, "NATIVE POINT SCUI",
             0.0029F, footer_color, 24U);
    add_right_aligned_text(out, font_.get(), basis, 0.945F, 0.925F,
                           "ARROWS / ENTER", 0.0029F, footer_color, 24U);
    wrapped_text_lines += 2U;

    if (!notice_message_.empty() && time_seconds <= notice_until_seconds_) {
        const auto notice_basis = basis_for(pose, 0.638F);
        Color notice_color{0.30F, 0.78F, 1.0F, 0.98F};
        if (notice_kind_ == ScuiNativeNoticeKind::success) {
            notice_color = {0.24F, 1.0F, 0.48F, 1.0F};
        } else if (notice_kind_ == ScuiNativeNoticeKind::warning) {
            notice_color = {1.0F, 0.78F, 0.18F, 1.0F};
        } else if (notice_kind_ == ScuiNativeNoticeKind::failure) {
            notice_color = {1.0F, 0.28F, 0.20F, 1.0F};
        }
        const float age = std::max(0.0F, time_seconds - notice_started_seconds_);
        const float intro = std::clamp(age / 0.18F, 0.0F, 1.0F);
        const float remaining = std::max(0.0F, notice_until_seconds_ - time_seconds);
        const float fade = std::clamp(remaining / 0.34F, 0.0F, 1.0F);
        const float overshoot = std::sin(intro * 3.14159265359F) * 0.18F;
        const float end_expand = 1.0F - std::clamp(remaining / 0.26F, 0.0F, 1.0F);
        const float emblem_scale = std::max(0.05F, intro + overshoot);
        const float ring_radius = (0.047F + end_expand * 0.016F) * emblem_scale;
        notice_color.a *= fade;
        const std::size_t before_notice = out.size();
        add_circle(out, notice_basis, 0.500F, 0.115F, ring_radius, 72U, notice_color, 0.0082F);
        // Small outward sparks create the requested growth-explosion entry.
        if (intro < 1.0F) {
            for (std::uint32_t spark = 0U; spark < 12U; ++spark) {
                const float angle = static_cast<float>(spark) / 12.0F * 6.28318530718F;
                const float inner = ring_radius * 1.08F;
                const float outer = inner + (1.0F - intro) * 0.040F;
                add_line(out, notice_basis,
                         0.500F + std::cos(angle) * inner, 0.115F + std::sin(angle) * inner,
                         0.500F + std::cos(angle) * outer, 0.115F + std::sin(angle) * outer,
                         5U, notice_color, 0.0062F);
            }
        }
        const float glyph_scale = emblem_scale;
        const auto scaled_x = [glyph_scale](float x) { return 0.500F + (x - 0.500F) * glyph_scale; };
        const auto scaled_y = [glyph_scale](float y) { return 0.115F + (y - 0.115F) * glyph_scale; };
        if (notice_kind_ == ScuiNativeNoticeKind::success) {
            add_line(out, notice_basis, scaled_x(0.472F), scaled_y(0.116F),
                     scaled_x(0.491F), scaled_y(0.137F), 14U, notice_color, 0.0080F * glyph_scale);
            add_line(out, notice_basis, scaled_x(0.491F), scaled_y(0.137F),
                     scaled_x(0.531F), scaled_y(0.087F), 22U, notice_color, 0.0080F * glyph_scale);
        } else if (notice_kind_ == ScuiNativeNoticeKind::failure) {
            add_line(out, notice_basis, scaled_x(0.470F), scaled_y(0.085F),
                     scaled_x(0.530F), scaled_y(0.145F), 22U, notice_color, 0.0080F * glyph_scale);
            add_line(out, notice_basis, scaled_x(0.530F), scaled_y(0.085F),
                     scaled_x(0.470F), scaled_y(0.145F), 22U, notice_color, 0.0080F * glyph_scale);
        } else {
            add_text(out, font_.get(), notice_basis, 0.487F, 0.091F,
                     notice_kind_ == ScuiNativeNoticeKind::warning ? "!" : "I",
                     0.0054F * glyph_scale, notice_color, 1U);
        }
        wrapped_text_lines += add_wrapped_text(out, font_.get(), notice_basis, 0.350F, 0.184F, 0.650F,
                                                notice_message_, 0.00345F, notice_color, 2U, 0.055F);
        notice_points = out.size() - before_notice;
    }

    if (pointer_visible_) {
        const Color cursor{1.0F, 0.42F, 0.18F, 0.98F};
        add_line(out, basis, pointer_x_ - 0.010F, pointer_y_, pointer_x_ + 0.010F, pointer_y_,
                 10U, cursor, 0.006F);
        add_line(out, basis, pointer_x_, pointer_y_ - 0.016F, pointer_x_, pointer_y_ + 0.016F,
                 10U, cursor, 0.006F);
    }

    last_generated_points_ = out.size();
    last_backplate_points_ = backplate_points;
    last_wrapped_text_lines_ = wrapped_text_lines;
    last_notice_points_ = notice_points;
    return out;
}

std::vector<ScuiPanelEvent> ScuiNativeRuntime::take_events() {
    std::vector<ScuiPanelEvent> result;
    result.swap(events_);
    return result;
}

const ScuiControl* ScuiNativeRuntime::focused_control() const noexcept {
    return panel_.control(focused_control_id());
}

const ScuiNativeRow* ScuiNativeRuntime::row_for_control(std::string_view control_id) const noexcept {
    const auto match = std::find_if(layout_.rows.begin(), layout_.rows.end(), [control_id](const ScuiNativeRow& row) {
        return row.control_id == control_id;
    });
    return match == layout_.rows.end() ? nullptr : &*match;
}

const ScuiNativeRow* ScuiNativeRuntime::row_at_pointer(float normalized_y) const noexcept {
    if (normalized_y < kRowsTop || normalized_y > kRowsBottom) return nullptr;
    const float row_height = (kRowsBottom - kRowsTop) / static_cast<float>(rows_per_page_);
    const std::size_t row_index = std::min(rows_per_page_ - 1U,
        static_cast<std::size_t>((normalized_y - kRowsTop) / row_height));
    const auto match = std::find_if(layout_.rows.begin(), layout_.rows.end(), [this, row_index](const ScuiNativeRow& row) {
        return row.page == current_page_ && row.row == row_index;
    });
    return match == layout_.rows.end() ? nullptr : &*match;
}

std::optional<std::size_t> ScuiNativeRuntime::focus_index_for(std::string_view control_id) const noexcept {
    const auto match = std::find(layout_.focus_order.begin(), layout_.focus_order.end(), control_id);
    if (match == layout_.focus_order.end()) return std::nullopt;
    return static_cast<std::size_t>(std::distance(layout_.focus_order.begin(), match));
}

ScuiNativeRuntime::Value ScuiNativeRuntime::value_for_binding(std::string_view binding) const {
    if (binding.empty()) return {};
    const auto match = values_.find(binding);
    return match == values_.end() ? Value{} : match->second;
}

ScuiNativeRuntime::Value ScuiNativeRuntime::parse_value(std::string_view raw) {
    std::string value(raw);
    value.erase(value.begin(), std::find_if(value.begin(), value.end(), [](unsigned char c) {
        return std::isspace(c) == 0;
    }));
    value.erase(std::find_if(value.rbegin(), value.rend(), [](unsigned char c) {
        return std::isspace(c) == 0;
    }).base(), value.end());
    if (value == "true") return true;
    if (value == "false") return false;
    if (value.size() >= 2U && value.front() == '"' && value.back() == '"') {
        return value.substr(1U, value.size() - 2U);
    }
    double number_value = 0.0;
    const auto parsed = std::from_chars(value.data(), value.data() + value.size(), number_value);
    if (parsed.ec == std::errc{} && parsed.ptr == value.data() + value.size()) return number_value;
    return {};
}

bool ScuiNativeRuntime::move_focus(int direction) {
    if (layout_.focus_order.empty()) return false;
    const std::size_t count = layout_.focus_order.size();
    if (direction < 0) focus_index_ = (focus_index_ + count - 1U) % count;
    else focus_index_ = (focus_index_ + 1U) % count;
    sync_page_to_focus();
    return true;
}

bool ScuiNativeRuntime::move_page(int direction) {
    if (layout_.page_count <= 1U) return false;
    if (direction < 0) {
        current_page_ = current_page_ == 0U ? layout_.page_count - 1U : current_page_ - 1U;
    } else {
        current_page_ = (current_page_ + 1U) % layout_.page_count;
    }
    const auto match = std::find_if(layout_.focus_order.begin(), layout_.focus_order.end(), [this](const std::string& id) {
        const auto* row = row_for_control(id);
        return row != nullptr && row->page == current_page_;
    });
    if (match != layout_.focus_order.end()) {
        focus_index_ = static_cast<std::size_t>(std::distance(layout_.focus_order.begin(), match));
    }
    return true;
}

bool ScuiNativeRuntime::focus_control(std::string_view control_id) {
    const auto index = focus_index_for(control_id);
    if (!index.has_value()) return false;
    const bool changed = focus_index_ != *index;
    focus_index_ = *index;
    sync_page_to_focus();
    return changed;
}

bool ScuiNativeRuntime::activate_control(const ScuiControl& control, int direction,
                                         bool pointer_activation,
                                         std::optional<float> normalized_x) {
    if (!control.enabled || !control.visible) return false;
    const int safe_direction = direction < 0 ? -1 : 1;
    std::string payload = "{}";
    bool changed = false;

    switch (control.type) {
        case ScuiControlType::toggle: {
            const bool next = !boolean(control.value_binding).value_or(false);
            changed = set_boolean(control.value_binding, next);
            payload = std::string("{\"value\":") + (next ? "true}" : "false}");
            break;
        }
        case ScuiControlType::dropdown:
        case ScuiControlType::radio:
        case ScuiControlType::list: {
            if (control.choices.empty()) return false;
            const std::string current = string(control.value_binding).value_or(control.choices.front());
            auto match = std::find(control.choices.begin(), control.choices.end(), current);
            std::size_t index = match == control.choices.end() ? 0U :
                static_cast<std::size_t>(std::distance(control.choices.begin(), match));
            if (direction == 0) {
                // Confirm dispatches the current selection rather than unexpectedly
                // cycling it. Left/right and wheel remain the adjustment controls.
                changed = true;
            } else {
                if (safe_direction < 0) index = (index + control.choices.size() - 1U) % control.choices.size();
                else index = (index + 1U) % control.choices.size();
                changed = set_string(control.value_binding, control.choices[index]);
            }
            payload = "{\"value\":\"" + escape_json(control.choices[index]) + "\"}";
            break;
        }
        case ScuiControlType::slider:
        case ScuiControlType::number: {
            const double low = control.minimum.value_or(0.0);
            const double high = control.maximum.value_or(100.0);
            const double step = control.step.value_or(1.0);
            double next = number(control.value_binding).value_or(low);
            if (pointer_activation && normalized_x.has_value() && *normalized_x >= kValueLeft) {
                const float ratio = std::clamp((*normalized_x - kValueLeft) / (kValueRight - kValueLeft), 0.0F, 1.0F);
                next = low + (high - low) * static_cast<double>(ratio);
                if (step > 0.0) next = low + std::round((next - low) / step) * step;
            } else {
                next += static_cast<double>(safe_direction) * step;
            }
            next = std::clamp(next, low, high);
            changed = set_number(control.value_binding, next);
            payload = "{\"value\":" + format_number(next) + "}";
            break;
        }
        case ScuiControlType::button:
        case ScuiControlType::confirmation:
            changed = true;
            break;
        case ScuiControlType::color:
        case ScuiControlType::tree:
        case ScuiControlType::graph_inspector:
            changed = true;
            payload = "{\"native_action\":\"confirm\"}";
            break;
        case ScuiControlType::label:
        case ScuiControlType::progress:
        case ScuiControlType::tabs:
        case ScuiControlType::unsupported:
            return false;
    }

    if (changed && !control.command_id.empty()) {
        (void)emit_event(control, std::move(payload));
    }
    return changed;
}

bool ScuiNativeRuntime::emit_event(const ScuiControl& control, std::string payload_json) {
    ScuiPanelEvent event;
    event.panel_id = panel_.panel_id;
    event.control_id = control.id;
    event.command_id = control.command_id;
    event.payload_json = std::move(payload_json);
    std::ostringstream transaction;
    transaction << "scui-native-" << std::setw(6) << std::setfill('0') << ++transaction_serial_;
    event.transaction_id = transaction.str();
    if (!command_registry_.may_dispatch(event)) {
        ++blocked_commands_;
        return false;
    }
    events_.push_back(std::move(event));
    ++dispatched_events_;
    return true;
}

void ScuiNativeRuntime::normalize_focus() noexcept {
    if (layout_.focus_order.empty()) {
        focus_index_ = 0U;
        current_page_ = 0U;
        return;
    }
    focus_index_ = std::min(focus_index_, layout_.focus_order.size() - 1U);
    sync_page_to_focus();
}

void ScuiNativeRuntime::sync_page_to_focus() noexcept {
    const auto* row = row_for_control(focused_control_id());
    if (row != nullptr) current_page_ = row->page;
}

}  // namespace signalcloud::ui
