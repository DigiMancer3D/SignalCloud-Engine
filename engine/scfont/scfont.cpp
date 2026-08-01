#include "engine/scfont/scfont.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace signalcloud::font {
namespace {

std::string quoted_value(std::istringstream& line) {
    std::string value;
    line >> std::quoted(value);
    if (!line) throw std::runtime_error("Expected quoted text");
    return value;
}

float finite(float value, const char* label) {
    if (!std::isfinite(value)) throw std::runtime_error(std::string(label) + " must be finite");
    return value;
}

}  // namespace

std::size_t base_layer_index(const Glyph& glyph) noexcept {
    for (std::size_t index = 0U; index < glyph.layers.size(); ++index) {
        std::string name = glyph.layers[index].name;
        std::transform(name.begin(), name.end(), name.begin(), [](unsigned char value) {
            return static_cast<char>(std::tolower(value));
        });
        if (name == "base" || name == "legacy core" || name == "starting layer" ||
            name == "start" || name == "core") {
            return index;
        }
    }
    return 0U;
}

float layer_depth_offset(const Glyph& glyph, std::size_t layer_index) noexcept {
    constexpr float layer_depth_step = 0.5F;
    const auto base = static_cast<std::ptrdiff_t>(base_layer_index(glyph));
    const auto current = static_cast<std::ptrdiff_t>(layer_index);
    return static_cast<float>(current - base) * layer_depth_step;
}

void validate(const Font& font) {
    if (font.name.empty()) throw std::runtime_error("Font name cannot be empty");
    if (!(font.metrics.em_size > 0.0F) || !(font.metrics.line_height > 0.0F)) {
        throw std::runtime_error("em_size and line_height must be positive");
    }
    if (font.glyphs.size() > 65'536U) throw std::runtime_error("Glyph count exceeds safety limit");
    std::size_t total_points = 0U;
    for (const auto& [codepoint, glyph] : font.glyphs) {
        if (codepoint > 0x10FFFFU || glyph.codepoint != codepoint) {
            throw std::runtime_error("Invalid glyph codepoint");
        }
        if (!(glyph.advance >= 0.0F) || !std::isfinite(glyph.advance)) {
            throw std::runtime_error("Invalid glyph advance");
        }
        if (glyph.layers.size() > 256U) throw std::runtime_error("Glyph layer count exceeds safety limit");
        for (const auto& layer : glyph.layers) {
            if (layer.name.empty()) throw std::runtime_error("Layer name cannot be empty");
            if (!std::isfinite(layer.opacity) || layer.opacity < 0.0F || layer.opacity > 1.0F) {
                throw std::runtime_error("Layer opacity must be from 0 to 1");
            }
            total_points += layer.points.size();
            if (total_points > 10'000'000U) throw std::runtime_error("Font point count exceeds safety limit");
            for (const auto& point : layer.points) {
                finite(point.x, "point x");
                finite(point.y, "point y");
                finite(point.z, "point z");
                if (!std::isfinite(point.alpha) || point.alpha < 0.0F || point.alpha > 1.0F) {
                    throw std::runtime_error("Point alpha must be from 0 to 1");
                }
            }
        }
    }
}

Font load_scfont(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("Cannot open font: " + path.string());
    Font font;
    Glyph* glyph = nullptr;
    Layer* layer = nullptr;
    bool header = false;
    std::string raw;
    std::size_t number = 0U;
    while (std::getline(input, raw)) {
        ++number;
        if (raw.empty() || raw[0] == '#') continue;
        std::istringstream line(raw);
        std::string command;
        line >> command;
        try {
            if (command == "SCFONT") {
                int version{};
                line >> version;
                if (version != 1) throw std::runtime_error("Unsupported SCFONT version");
                header = true;
            } else if (command == "FONT") {
                font.name = quoted_value(line);
            } else if (command == "METRICS") {
                line >> font.metrics.em_size >> font.metrics.cap_height >> font.metrics.x_height
                     >> font.metrics.baseline >> font.metrics.ascender >> font.metrics.descender
                     >> font.metrics.letter_spacing >> font.metrics.word_spacing >> font.metrics.line_height;
            } else if (command == "GLYPH") {
                std::uint32_t codepoint{};
                float advance{};
                line >> codepoint >> advance;
                auto [position, inserted] = font.glyphs.emplace(codepoint, Glyph{codepoint, advance, {}});
                if (!inserted) throw std::runtime_error("Duplicate glyph");
                glyph = &position->second;
                layer = nullptr;
            } else if (command == "LAYER") {
                if (glyph == nullptr) throw std::runtime_error("LAYER outside GLYPH");
                std::string name = quoted_value(line);
                float opacity{};
                int visible{};
                line >> opacity >> visible;
                glyph->layers.push_back(Layer{name, opacity, visible != 0, {}});
                layer = &glyph->layers.back();
            } else if (command == "POINT") {
                if (layer == nullptr) throw std::runtime_error("POINT outside LAYER");
                Point point;
                line >> point.x >> point.y >> point.z >> point.alpha;
                if (!line) throw std::runtime_error("Malformed POINT");
                std::string color;
                if (line >> color) {
                    try {
                        point.color = static_cast<std::uint32_t>(std::stoul(color, nullptr, 16));
                    } catch (const std::exception&) {
                        throw std::runtime_error("Malformed POINT color");
                    }
                    if (!(line >> point.group)) point.group = 0;
                }
                layer->points.push_back(point);
            } else if (command == "ENDLAYER") {
                layer = nullptr;
            } else if (command == "ENDGLYPH") {
                layer = nullptr;
                glyph = nullptr;
            } else if (command == "END") {
                break;
            } else {
                throw std::runtime_error("Unknown command: " + command);
            }
        } catch (const std::exception& error) {
            throw std::runtime_error(path.string() + ":" + std::to_string(number) + ": " + error.what());
        }
    }
    if (!header) throw std::runtime_error("Missing SCFONT 1 header");
    validate(font);
    return font;
}

void save_scfont(const std::filesystem::path& path, const Font& font) {
    validate(font);
    const auto temporary = path.string() + ".tmp";
    std::ofstream output(temporary, std::ios::trunc);
    if (!output) throw std::runtime_error("Cannot write font: " + path.string());
    output << "SCFONT 1\nFONT " << std::quoted(font.name) << '\n';
    const auto& m = font.metrics;
    output << std::setprecision(8) << "METRICS " << m.em_size << ' ' << m.cap_height << ' '
           << m.x_height << ' ' << m.baseline << ' ' << m.ascender << ' ' << m.descender << ' '
           << m.letter_spacing << ' ' << m.word_spacing << ' ' << m.line_height << '\n';
    std::vector<std::uint32_t> codes;
    codes.reserve(font.glyphs.size());
    for (const auto& item : font.glyphs) codes.push_back(item.first);
    std::sort(codes.begin(), codes.end());
    for (const auto code : codes) {
        const auto& glyph = font.glyphs.at(code);
        output << "GLYPH " << code << ' ' << glyph.advance << '\n';
        for (const auto& layer : glyph.layers) {
            output << "LAYER " << std::quoted(layer.name) << ' ' << layer.opacity << ' '
                   << (layer.visible ? 1 : 0) << '\n';
            for (const auto& point : layer.points) {
                output << "POINT " << point.x << ' ' << point.y << ' ' << point.z << ' ' << point.alpha
                       << ' ' << std::hex << std::uppercase << std::setw(8) << std::setfill('0')
                       << point.color << std::dec << std::nouppercase << std::setfill(' ')
                       << ' ' << point.group << '\n';
            }
            output << "ENDLAYER\n";
        }
        output << "ENDGLYPH\n";
    }
    output << "END\n";
    output.close();
    if (!output) throw std::runtime_error("Failed while writing font");
    std::filesystem::rename(temporary, path);
}

std::vector<std::uint32_t> decode_utf8(std::string_view text) {
    std::vector<std::uint32_t> result;
    for (std::size_t index = 0; index < text.size();) {
        const auto first = static_cast<unsigned char>(text[index]);
        std::uint32_t code{};
        std::size_t count{};
        if (first < 0x80U) { code = first; count = 1U; }
        else if ((first & 0xE0U) == 0xC0U) { code = first & 0x1FU; count = 2U; }
        else if ((first & 0xF0U) == 0xE0U) { code = first & 0x0FU; count = 3U; }
        else if ((first & 0xF8U) == 0xF0U) { code = first & 0x07U; count = 4U; }
        else { result.push_back(0xFFFDU); ++index; continue; }
        if (index + count > text.size()) { result.push_back(0xFFFDU); break; }
        bool valid = true;
        for (std::size_t offset = 1U; offset < count; ++offset) {
            const auto byte = static_cast<unsigned char>(text[index + offset]);
            if ((byte & 0xC0U) != 0x80U) { valid = false; break; }
            code = (code << 6U) | (byte & 0x3FU);
        }
        if (!valid || code > 0x10FFFFU || (code >= 0xD800U && code <= 0xDFFFU)) {
            result.push_back(0xFFFDU);
            ++index;
        } else {
            result.push_back(code);
            index += count;
        }
    }
    return result;
}

LayoutResult layout_utf8(const Font& font, std::string_view text, float scale,
                         std::size_t maximum_points) {
    validate(font);
    if (!(scale > 0.0F) || !std::isfinite(scale)) throw std::runtime_error("Scale must be positive");
    LayoutResult result;
    float cursor_x = 0.0F;
    float cursor_y = 0.0F;
    float maximum_x = 0.0F;
    for (const auto code : decode_utf8(text)) {
        if (code == '\n') {
            maximum_x = std::max(maximum_x, cursor_x);
            cursor_x = 0.0F;
            cursor_y += font.metrics.line_height * scale;
            continue;
        }
        if (code == ' ') {
            cursor_x += font.metrics.word_spacing * scale;
            continue;
        }
        auto found = font.glyphs.find(code);
        if (found == font.glyphs.end()) found = font.glyphs.find(0xFFFDU);
        if (found == font.glyphs.end()) found = font.glyphs.find(static_cast<std::uint32_t>('?'));
        if (found == font.glyphs.end()) {
            ++result.missing_glyphs;
            cursor_x += font.metrics.word_spacing * scale;
            continue;
        }
        const auto& glyph = found->second;
        for (std::size_t layer_index = 0; layer_index < glyph.layers.size(); ++layer_index) {
            const auto& layer = glyph.layers[layer_index];
            if (!layer.visible) continue;
            const float layer_z = layer_depth_offset(glyph, layer_index);
            for (const auto& point : layer.points) {
                if (result.points.size() >= maximum_points) throw std::runtime_error("Text point budget exceeded");
                const float positioned_z = (point.z + layer_z) * scale;
                if (result.points.empty()) {
                    result.minimum_z = positioned_z;
                    result.maximum_z = positioned_z;
                } else {
                    result.minimum_z = std::min(result.minimum_z, positioned_z);
                    result.maximum_z = std::max(result.maximum_z, positioned_z);
                }
                result.points.push_back({
                    cursor_x + point.x * scale, cursor_y + point.y * scale, positioned_z,
                    point.alpha * layer.opacity, point.color, code,
                    static_cast<std::uint32_t>(layer_index)
                });
            }
        }
        cursor_x += (glyph.advance + font.metrics.letter_spacing) * scale;
    }
    maximum_x = std::max(maximum_x, cursor_x);
    result.width = maximum_x;
    result.height = cursor_y + font.metrics.line_height * scale;
    return result;
}

}  // namespace signalcloud::font
