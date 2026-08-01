#include "engine/scfont/font_service.hpp"
#include "engine/scfont/scfont.hpp"
#include "engine/scfont/text_point_adapter.hpp"

#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace {
int failures = 0;

void check(bool condition, const std::string& message) {
    if (condition) std::cout << "PASS: " << message << '\n';
    else {
        std::cerr << "FAIL: " << message << '\n';
        ++failures;
    }
}

bool near(float a, float b, float epsilon = 0.001F) {
    return std::abs(a - b) <= epsilon;
}

signalcloud::font::Font synthetic_font() {
    using namespace signalcloud::font;
    Font font;
    font.name = "synthetic";
    font.metrics.line_height = 10.0F;
    font.metrics.letter_spacing = 1.0F;
    font.metrics.word_spacing = 4.0F;
    Glyph glyph;
    glyph.codepoint = static_cast<std::uint32_t>('?');
    glyph.advance = 6.0F;
    Layer layer;
    layer.name = "depth";
    layer.opacity = 0.5F;
    layer.points.push_back({1.0F, 2.0F, 3.0F, 0.5F, 0x80402080U, 0});
    glyph.layers.push_back(layer);
    font.glyphs.emplace(glyph.codepoint, glyph);
    validate(font);
    return font;
}
}

int main(int argc, char** argv) {
    using namespace signalcloud;
    const std::filesystem::path root = argc > 1 ? argv[1] : std::filesystem::current_path();
    const auto terminal_path = root / "content/core/fonts/terminal_00/Terminal_00.scfont";

    const auto terminal = font::load_scfont(terminal_path);
    check(terminal.name == "SC_term_00", "Terminal_00 native SCFONT name loads");
    check(terminal.glyphs.size() == 123U, "Terminal_00 loads all 123 authored glyphs");
    const auto terminal_layout = font::layout_utf8(terminal, "Almond 09", 1.0F, 10'000U);
    check(!terminal_layout.points.empty() && terminal_layout.width > 20.0F,
          "Terminal_00 lays out mixed-case text with authored Advance");
    check(terminal_layout.missing_glyphs == 0U, "Terminal_00 proof text has no missing glyphs");

    font::Font layered;
    layered.name = "ordered layers";
    font::Glyph layered_glyph;
    layered_glyph.codepoint = static_cast<std::uint32_t>('A');
    layered_glyph.advance = 6.0F;
    layered_glyph.layers.push_back(font::Layer{"Behind", 1.0F, true, {{0,0,0,1,0xFFFFFFFFU,0}}});
    layered_glyph.layers.push_back(font::Layer{"Base", 1.0F, true, {{0,0,0,1,0xFFFFFFFFU,0}}});
    layered_glyph.layers.push_back(font::Layer{"Front", 1.0F, true, {{0,0,0,1,0xFFFFFFFFU,0}}});
    layered.glyphs.emplace(layered_glyph.codepoint, layered_glyph);
    const auto layered_layout = font::layout_utf8(layered, "A", 1.0F, 16U);
    check(layered_layout.points.size() == 3U &&
              near(layered_layout.points[0].z, -0.5F) &&
              near(layered_layout.points[1].z, 0.0F) &&
              near(layered_layout.points[2].z, 0.5F),
          "rich layout maps layers above base behind and layers below base in front");
    check(near(layered_layout.minimum_z, -0.5F) && near(layered_layout.maximum_z, 0.5F),
          "rich layout reports full authored layer depth bounds");

    const auto decoded = font::decode_utf8("A\xE2\x98\x83");
    check(decoded.size() == 2U && decoded[0] == static_cast<std::uint32_t>('A') &&
              decoded[1] == 0x2603U,
          "SCFONT runtime decodes UTF-8 codepoints without byte truncation");

    auto synthetic = synthetic_font();
    const auto fallback_layout = font::layout_utf8(synthetic, "\xE2\x98\x83", 1.0F, 32U);
    check(fallback_layout.points.size() == 1U,
          "missing Unicode glyph falls back to question mark after U+FFFD lookup");

    font::TextBasis basis;
    basis.origin = {10.0F, 20.0F, 30.0F};
    basis.right = {1.0F, 0.0F, 0.0F};
    basis.up = {0.0F, 1.0F, 0.0F};
    basis.depth = {0.0F, 0.0F, 1.0F};
    font::TextPointStyle style;
    style.point_radius = 0.002F;
    style.opacity = 0.5F;
    style.tint = {1.0F, 1.0F, 1.0F};
    std::vector<render::PointGpu> simple;
    std::vector<render::PointGpu> rich;
    (void)font::append_simple_text_points(simple, synthetic, "?", basis, 1.0F, style, 16U);
    (void)font::append_rich_text_points(rich, synthetic, "?", basis, 1.0F, style, 16U);
    check(simple.size() == 1U && rich.size() == 1U, "simple and rich adapters generate bounded points");
    if (!simple.empty() && !rich.empty()) {
        check(near(simple.front().position[2], 30.0F) && near(rich.front().position[2], 33.0F),
              "simple text flattens Z while rich text preserves authored depth");
        const float expected_alpha = 0.5F * 0.5F * (128.0F / 255.0F) * 0.5F;
        check(near(simple.front().color[3], expected_alpha, 0.002F),
              "point alpha, layer opacity, packed alpha, and text opacity multiply once");
    }

    font::FontService service;
    check(service.load("core.fonts.terminal_00", terminal_path),
          "FontService transactionally loads Terminal_00");
    check(service.set_default("core.fonts.terminal_00"), "FontService selects default font");
    const auto before_snapshot = service.default_font();
    const auto before_generation = service.generation("core.fonts.terminal_00");
    const auto malformed = root / "user_data" / "a5a3r2_invalid_font.scfont";
    std::filesystem::create_directories(malformed.parent_path());
    {
        std::ofstream stream(malformed, std::ios::trunc);
        stream << "SCFONT 1\nFONT \"broken\"\nMETRICS 9 8 5 7 0 2 1 4 nan\n";
    }
    check(!service.reload("core.fonts.terminal_00", malformed),
          "invalid protected candidate is rejected");
    check(service.default_font() == before_snapshot &&
              service.generation("core.fonts.terminal_00") == before_generation,
          "failed reload retains the previous immutable font generation");
    std::error_code remove_error;
    std::filesystem::remove(malformed, remove_error);

    font::TextPointStyle billboard_style;
    billboard_style.tint = {0.2F, 1.0F, 0.4F};
    billboard_style.replace_rgb = true;
    std::vector<render::PointGpu> near_points;
    std::vector<render::PointGpu> far_points;
    const auto near_stats = font::append_constant_apparent_billboard(
        near_points, terminal, "WELCOME", {0.0F, 1.5F, 0.0F}, {0.0F, 1.5F, 0.25F},
        0.42F, billboard_style, true, 8'000U);
    const auto far_stats = font::append_constant_apparent_billboard(
        far_points, terminal, "WELCOME", {0.0F, 1.5F, 0.0F}, {0.0F, 1.5F, 6.0F},
        0.42F, billboard_style, true, 8'000U);
    check(near_stats.text_points > 0U && far_stats.text_points > 0U,
          "constant-apparent WELCOME produces native Rich text at near and far distances");
    check(near(near_stats.world_width / near_stats.camera_distance,
               far_stats.world_width / far_stats.camera_distance, 0.0005F),
          "WELCOME apparent width remains constant below and above one metre");
    check(near(near_stats.point_radius / near_stats.scale,
               far_stats.point_radius / far_stats.scale, 0.001F) &&
              near_stats.point_radius / near_stats.scale < 0.25F,
          "world-sign dots retain separation instead of merging into bars");

    if (failures == 0) {
        std::cout << "All native SCFONT service, layout, adapter, and billboard checks passed.\n";
        return 0;
    }
    return 1;
}
