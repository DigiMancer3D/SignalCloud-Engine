#pragma once

#include <cstdint>
#include <filesystem>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace signalcloud::font {

struct Point {
    float x{};
    float y{};
    float z{};
    float alpha{1.0F};
    std::uint32_t color{0x45D8EFFFU};
    std::int32_t group{};
};

struct Layer {
    std::string name{"Base"};
    float opacity{1.0F};
    bool visible{true};
    std::vector<Point> points;
};

struct Glyph {
    std::uint32_t codepoint{};
    float advance{6.0F};
    std::vector<Layer> layers;
};

struct Metrics {
    float em_size{9.0F};
    float cap_height{8.0F};
    float x_height{5.0F};
    float baseline{7.0F};
    float ascender{0.0F};
    float descender{2.0F};
    float letter_spacing{1.0F};
    float word_spacing{4.0F};
    float line_height{11.0F};
};

struct Font {
    std::string name{"Untitled SignalCloud Font"};
    Metrics metrics;
    std::unordered_map<std::uint32_t, Glyph> glyphs;
};

struct PositionedPoint {
    float x{};
    float y{};
    float z{};
    float alpha{1.0F};
    std::uint32_t color{0x45D8EFFFU};
    std::uint32_t codepoint{};
    std::uint32_t layer{};
};

struct LayoutResult {
    std::vector<PositionedPoint> points;
    float width{};
    float height{};
    float minimum_z{};
    float maximum_z{};
    std::size_t missing_glyphs{};
};

Font load_scfont(const std::filesystem::path& path);
void save_scfont(const std::filesystem::path& path, const Font& font);
void validate(const Font& font);
std::size_t base_layer_index(const Glyph& glyph) noexcept;
float layer_depth_offset(const Glyph& glyph, std::size_t layer_index) noexcept;
LayoutResult layout_utf8(const Font& font, std::string_view text, float scale = 1.0F,
                         std::size_t maximum_points = 1'000'000U);
std::vector<std::uint32_t> decode_utf8(std::string_view text);

}  // namespace signalcloud::font
