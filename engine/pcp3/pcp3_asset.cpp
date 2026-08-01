#include "engine/pcp3/pcp3_asset.hpp"

#include "engine/data/udata.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <fstream>
#include <limits>
#include <optional>
#include <sstream>
#include <string_view>

namespace signalcloud::pcp3 {
namespace {

#pragma pack(push, 1)
struct CloudHeader {
    char magic[8];
    std::uint32_t version;
    std::uint32_t record_size;
    std::uint64_t point_count;
    std::array<std::uint8_t, 32> payload_sha256;
    std::uint64_t flags;
};

struct CloudRecord {
    float x, y, z, radius;
    float r, g, b, a;
    float nx, ny, nz, density;
    std::uint32_t layer_id;
    std::uint32_t flags;
    float attribute0;
    float attribute1;
};
#pragma pack(pop)

static_assert(sizeof(CloudHeader) == 64);
static_assert(sizeof(CloudRecord) == 64);


class Sha256 {
public:
    Sha256() { reset(); }

    void update(const std::uint8_t* data, std::size_t length) {
        for (std::size_t index = 0; index < length; ++index) {
            buffer_[buffer_length_++] = data[index];
            if (buffer_length_ == 64U) {
                transform(buffer_.data());
                bit_length_ += 512U;
                buffer_length_ = 0U;
            }
        }
    }

    [[nodiscard]] std::array<std::uint8_t, 32> finish() {
        std::array<std::uint8_t, 32> digest{};
        std::size_t index = buffer_length_;
        buffer_[index++] = 0x80U;
        if (index > 56U) {
            while (index < 64U) buffer_[index++] = 0U;
            transform(buffer_.data());
            index = 0U;
        }
        while (index < 56U) buffer_[index++] = 0U;
        bit_length_ += static_cast<std::uint64_t>(buffer_length_) * 8U;
        for (int shift = 7; shift >= 0; --shift) {
            buffer_[index++] = static_cast<std::uint8_t>((bit_length_ >> (shift * 8)) & 0xFFU);
        }
        transform(buffer_.data());
        for (std::size_t word = 0; word < state_.size(); ++word) {
            digest[word * 4U] = static_cast<std::uint8_t>((state_[word] >> 24U) & 0xFFU);
            digest[word * 4U + 1U] = static_cast<std::uint8_t>((state_[word] >> 16U) & 0xFFU);
            digest[word * 4U + 2U] = static_cast<std::uint8_t>((state_[word] >> 8U) & 0xFFU);
            digest[word * 4U + 3U] = static_cast<std::uint8_t>(state_[word] & 0xFFU);
        }
        return digest;
    }

private:
    static constexpr std::array<std::uint32_t, 64> constants_{
        0x428a2f98U,0x71374491U,0xb5c0fbcfU,0xe9b5dba5U,0x3956c25bU,0x59f111f1U,0x923f82a4U,0xab1c5ed5U,
        0xd807aa98U,0x12835b01U,0x243185beU,0x550c7dc3U,0x72be5d74U,0x80deb1feU,0x9bdc06a7U,0xc19bf174U,
        0xe49b69c1U,0xefbe4786U,0x0fc19dc6U,0x240ca1ccU,0x2de92c6fU,0x4a7484aaU,0x5cb0a9dcU,0x76f988daU,
        0x983e5152U,0xa831c66dU,0xb00327c8U,0xbf597fc7U,0xc6e00bf3U,0xd5a79147U,0x06ca6351U,0x14292967U,
        0x27b70a85U,0x2e1b2138U,0x4d2c6dfcU,0x53380d13U,0x650a7354U,0x766a0abbU,0x81c2c92eU,0x92722c85U,
        0xa2bfe8a1U,0xa81a664bU,0xc24b8b70U,0xc76c51a3U,0xd192e819U,0xd6990624U,0xf40e3585U,0x106aa070U,
        0x19a4c116U,0x1e376c08U,0x2748774cU,0x34b0bcb5U,0x391c0cb3U,0x4ed8aa4aU,0x5b9cca4fU,0x682e6ff3U,
        0x748f82eeU,0x78a5636fU,0x84c87814U,0x8cc70208U,0x90befffaU,0xa4506cebU,0xbef9a3f7U,0xc67178f2U,
    };

    static std::uint32_t rotr(std::uint32_t value, std::uint32_t count) noexcept {
        return (value >> count) | (value << (32U - count));
    }

    void reset() {
        state_ = {0x6a09e667U,0xbb67ae85U,0x3c6ef372U,0xa54ff53aU,
                  0x510e527fU,0x9b05688cU,0x1f83d9abU,0x5be0cd19U};
        buffer_.fill(0U);
        buffer_length_ = 0U;
        bit_length_ = 0U;
    }

    void transform(const std::uint8_t* block) {
        std::array<std::uint32_t, 64> words{};
        for (std::size_t index = 0; index < 16U; ++index) {
            words[index] = (static_cast<std::uint32_t>(block[index * 4U]) << 24U) |
                           (static_cast<std::uint32_t>(block[index * 4U + 1U]) << 16U) |
                           (static_cast<std::uint32_t>(block[index * 4U + 2U]) << 8U) |
                           static_cast<std::uint32_t>(block[index * 4U + 3U]);
        }
        for (std::size_t index = 16U; index < 64U; ++index) {
            const std::uint32_t s0 = rotr(words[index - 15U], 7U) ^ rotr(words[index - 15U], 18U) ^ (words[index - 15U] >> 3U);
            const std::uint32_t s1 = rotr(words[index - 2U], 17U) ^ rotr(words[index - 2U], 19U) ^ (words[index - 2U] >> 10U);
            words[index] = words[index - 16U] + s0 + words[index - 7U] + s1;
        }
        std::uint32_t a = state_[0], b = state_[1], c = state_[2], d = state_[3];
        std::uint32_t e = state_[4], f = state_[5], g = state_[6], h = state_[7];
        for (std::size_t index = 0; index < 64U; ++index) {
            const std::uint32_t sum1 = rotr(e, 6U) ^ rotr(e, 11U) ^ rotr(e, 25U);
            const std::uint32_t choice = (e & f) ^ ((~e) & g);
            const std::uint32_t temp1 = h + sum1 + choice + constants_[index] + words[index];
            const std::uint32_t sum0 = rotr(a, 2U) ^ rotr(a, 13U) ^ rotr(a, 22U);
            const std::uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
            const std::uint32_t temp2 = sum0 + majority;
            h = g; g = f; f = e; e = d + temp1;
            d = c; c = b; b = a; a = temp1 + temp2;
        }
        state_[0] += a; state_[1] += b; state_[2] += c; state_[3] += d;
        state_[4] += e; state_[5] += f; state_[6] += g; state_[7] += h;
    }

    std::array<std::uint32_t, 8> state_{};
    std::array<std::uint8_t, 64> buffer_{};
    std::size_t buffer_length_{0U};
    std::uint64_t bit_length_{0U};
};

bool checksum_is_present(const std::array<std::uint8_t, 32>& checksum) noexcept {
    return std::any_of(checksum.begin(), checksum.end(), [](std::uint8_t byte) { return byte != 0U; });
}

std::string trim(std::string value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return {};
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1U);
}

std::optional<std::string> raw_value(const data::UDataDocument& doc,
                                     std::string_view section,
                                     std::string_view key) {
    return doc.value(section, key);
}

std::optional<std::string> json_value_string(std::string raw) {
    const auto marker = raw.find("\"value\"");
    if (marker == std::string::npos) return std::nullopt;
    const auto colon = raw.find(':', marker);
    if (colon == std::string::npos) return std::nullopt;
    std::string value = trim(raw.substr(colon + 1U));
    if (!value.empty() && value.back() == '}') value.pop_back();
    value = trim(value);
    if (value.size() >= 2U && value.front() == '"' && value.back() == '"') {
        value = value.substr(1U, value.size() - 2U);
        std::string decoded;
        decoded.reserve(value.size());
        bool escape = false;
        for (char c : value) {
            if (escape) {
                switch (c) {
                    case 'n': decoded.push_back('\n'); break;
                    case 'r': decoded.push_back('\r'); break;
                    case 't': decoded.push_back('\t'); break;
                    default: decoded.push_back(c); break;
                }
                escape = false;
            } else if (c == '\\') {
                escape = true;
            } else {
                decoded.push_back(c);
            }
        }
        return decoded;
    }
    return value;
}

std::string string_value(const data::UDataDocument& doc, std::string_view section,
                         std::string_view key, std::string fallback = {}) {
    if (const auto raw = raw_value(doc, section, key)) {
        if (const auto value = json_value_string(*raw)) return *value;
    }
    return fallback;
}

bool bool_value(const data::UDataDocument& doc, std::string_view section,
                std::string_view key, bool fallback) {
    const std::string value = string_value(doc, section, key, fallback ? "true" : "false");
    return value == "true" || value == "1";
}

float float_value(const data::UDataDocument& doc, std::string_view section,
                  std::string_view key, float fallback) {
    const std::string value = string_value(doc, section, key, std::to_string(fallback));
    try {
        return std::stof(value);
    } catch (...) {
        return fallback;
    }
}

math::Vec3 vec3_value(const data::UDataDocument& doc, std::string_view section,
                      std::string_view key, math::Vec3 fallback) {
    const auto raw = raw_value(doc, section, key);
    if (!raw) return fallback;
    const auto marker = raw->find("\"value\"");
    const auto open = raw->find('[', marker);
    const auto close = raw->find(']', open);
    if (open == std::string::npos || close == std::string::npos) return fallback;
    std::stringstream stream(raw->substr(open + 1U, close - open - 1U));
    std::string item;
    std::array<float, 3> values{fallback.x, fallback.y, fallback.z};
    int index = 0;
    while (std::getline(stream, item, ',') && index < 3) {
        try {
            values[static_cast<std::size_t>(index)] = std::stof(trim(item));
        } catch (...) {
        }
        ++index;
    }
    return {values[0], values[1], values[2]};
}

std::vector<std::string> string_list_value(const data::UDataDocument& doc,
                                           std::string_view section,
                                           std::string_view key) {
    std::vector<std::string> result;
    const auto raw = raw_value(doc, section, key);
    if (!raw) return result;
    const auto marker = raw->find("\"value\"");
    const auto open = raw->find('[', marker);
    const auto close = raw->find(']', open);
    if (open == std::string::npos || close == std::string::npos) return result;
    const std::string body = raw->substr(open + 1U, close - open - 1U);
    bool quoted = false;
    bool escaped = false;
    std::string item;
    for (char c : body) {
        if (escaped) { item.push_back(c); escaped = false; continue; }
        if (c == '\\' && quoted) { escaped = true; continue; }
        if (c == '"') { quoted = !quoted; continue; }
        if (c == ',' && !quoted) {
            const auto cleaned = trim(item);
            if (!cleaned.empty()) result.push_back(cleaned);
            item.clear();
            continue;
        }
        item.push_back(c);
    }
    const auto cleaned = trim(item);
    if (!cleaned.empty()) result.push_back(cleaned);
    return result;
}

bool finite_point(const LayeredPoint& point) noexcept {
    const auto finite = [](float value) { return std::isfinite(value); };
    return finite(point.point.position[0]) && finite(point.point.position[1]) &&
           finite(point.point.position[2]) && finite(point.point.radius) &&
           finite(point.point.color[0]) && finite(point.point.color[1]) &&
           finite(point.point.color[2]) && finite(point.point.color[3]) &&
           finite(point.point.normal[0]) && finite(point.point.normal[1]) &&
           finite(point.point.normal[2]) && finite(point.point.density) &&
           finite(point.attribute0) && finite(point.attribute1);
}


constexpr float kPi = 3.14159265358979323846F;

std::vector<std::string> sections_with_prefix(const data::UDataDocument& document,
                                               std::string_view prefix) {
    std::vector<std::string> sections;
    for (const auto& entry : document.entries()) {
        if (!std::string_view(entry.section).starts_with(prefix)) continue;
        if (std::find(sections.begin(), sections.end(), entry.section) == sections.end()) {
            sections.push_back(entry.section);
        }
    }
    std::sort(sections.begin(), sections.end(), [](const std::string& left, const std::string& right) {
        const auto parse_index = [](const std::string& value) {
            const auto dot = value.rfind('.');
            if (dot == std::string::npos) return 0;
            try { return std::stoi(value.substr(dot + 1U)); } catch (...) { return 0; }
        };
        return parse_index(left) < parse_index(right);
    });
    return sections;
}

std::uint32_t semantic_flag(std::string_view semantic) noexcept {
    if (semantic == "wall") return 1U;
    if (semantic == "floor") return 2U;
    if (semantic == "ceiling") return 3U;
    if (semantic == "dust") return 4U;
    if (semantic == "portal") return 5U;
    if (semantic == "water_surface") return 6U;
    if (semantic == "water_volume") return 7U;
    if (semantic == "light") return 8U;
    if (semantic == "enemy_body") return 9U;
    if (semantic == "friendly_body") return 10U;
    if (semantic == "weapon") return 11U;
    if (semantic == "pickup") return 12U;
    if (semantic == "trigger") return 13U;
    if (semantic == "bone") return 14U;
    if (semantic == "liquid_flow") return 15U;
    return 0U;
}

void parse_hex_color(std::string value, float color[4]) noexcept {
    if (!value.empty() && value.front() == '#') value.erase(value.begin());
    if (value.size() != 6U && value.size() != 8U) return;
    try {
        color[0] = static_cast<float>(std::stoi(value.substr(0U, 2U), nullptr, 16)) / 255.0F;
        color[1] = static_cast<float>(std::stoi(value.substr(2U, 2U), nullptr, 16)) / 255.0F;
        color[2] = static_cast<float>(std::stoi(value.substr(4U, 2U), nullptr, 16)) / 255.0F;
        color[3] = value.size() == 8U
            ? static_cast<float>(std::stoi(value.substr(6U, 2U), nullptr, 16)) / 255.0F
            : 1.0F;
    } catch (...) {
    }
}

math::Vec3 rotate_xyz(math::Vec3 point, math::Vec3 degrees) noexcept {
    const float rx = degrees.x * kPi / 180.0F;
    const float ry = degrees.y * kPi / 180.0F;
    const float rz = degrees.z * kPi / 180.0F;
    const float cx = std::cos(rx), sx = std::sin(rx);
    const float cy = std::cos(ry), sy = std::sin(ry);
    const float cz = std::cos(rz), sz = std::sin(rz);
    point = {point.x, point.y * cx - point.z * sx, point.y * sx + point.z * cx};
    point = {point.x * cy + point.z * sy, point.y, -point.x * sy + point.z * cy};
    point = {point.x * cz - point.y * sz, point.x * sz + point.y * cz, point.z};
    return point;
}

RuntimeKeyframe sample_factory(const RuntimeFactory& factory, double time_seconds) noexcept {
    RuntimeKeyframe sample;
    if (factory.keyframes.empty()) return sample;
    float time = static_cast<float>(std::max(0.0, time_seconds));
    if (factory.loop && factory.duration > 0.0001F) time = std::fmod(time, factory.duration);
    if (time <= factory.keyframes.front().time) return factory.keyframes.front();
    if (time >= factory.keyframes.back().time) return factory.keyframes.back();
    for (std::size_t index = 1U; index < factory.keyframes.size(); ++index) {
        const auto& right = factory.keyframes[index];
        if (right.time < time) continue;
        const auto& left = factory.keyframes[index - 1U];
        const float span = std::max(0.0001F, right.time - left.time);
        const float amount = std::clamp((time - left.time) / span, 0.0F, 1.0F);
        const auto lerp = [amount](math::Vec3 a, math::Vec3 b) {
            return a + (b - a) * amount;
        };
        sample.time = time;
        sample.position = lerp(left.position, right.position);
        sample.rotation_degrees = lerp(left.rotation_degrees, right.rotation_degrees);
        sample.scale = lerp(left.scale, right.scale);
        return sample;
    }
    return factory.keyframes.back();
}

bool load_runtime_factory(const std::filesystem::path& path, RuntimeFactory& factory,
                          std::string* error) {
    try {
        const auto document = data::UDataDocument::load(path);
        factory.present = true;
        factory.enabled = bool_value(document, "factory", "enabled", false);
        factory.game_enabled = bool_value(document, "factory", "game_enabled", false);
        factory.stress_enabled = bool_value(document, "factory", "stress_enabled", true);
        factory.scanner_required = bool_value(document, "factory", "scanner_required", false);
        factory.proximity_required = bool_value(document, "factory", "proximity_required", false);
        factory.proximity_radius = std::clamp(float_value(document, "factory", "proximity_radius", 16.0F), 0.1F, 10'000.0F);
        factory.clip = string_value(document, "factory", "clip", "Default");
        factory.duration = std::max(0.001F, float_value(document, "factory", "duration", 1.0F));
        factory.loop = bool_value(document, "factory", "loop", true);
        factory.event_policy = string_value(document, "factory", "event_policy", "telemetry_only");
        factory.max_nested_points = static_cast<std::size_t>(std::clamp(
            float_value(document, "factory", "max_nested_points", 100'000.0F), 1'000.0F, 500'000.0F));
        factory.keyframes.clear();
        for (const auto& section : sections_with_prefix(document, "keyframe.")) {
            if (factory.keyframes.size() >= 64U) break;
            RuntimeKeyframe key;
            key.time = std::max(0.0F, float_value(document, section, "time", 0.0F));
            key.position = vec3_value(document, section, "position", {});
            key.rotation_degrees = vec3_value(document, section, "rotation", {});
            key.scale = vec3_value(document, section, "scale", {1.0F, 1.0F, 1.0F});
            factory.keyframes.push_back(key);
        }
        std::sort(factory.keyframes.begin(), factory.keyframes.end(), [](const auto& a, const auto& b) { return a.time < b.time; });
        factory.placements.clear();
        for (const auto& section : sections_with_prefix(document, "placement.")) {
            if (factory.placements.size() >= 64U) break;
            RuntimePlacement placement;
            placement.asset_id = string_value(document, section, "asset_id", "");
            placement.kind = string_value(document, section, "kind", "object");
            placement.position = vec3_value(document, section, "position", {});
            placement.rotation_degrees = vec3_value(document, section, "rotation", {});
            placement.scale = std::clamp(float_value(document, section, "scale", 1.0F), 0.001F, 1000.0F);
            placement.enabled = bool_value(document, section, "enabled", true);
            if (!placement.asset_id.empty()) factory.placements.push_back(std::move(placement));
        }
        factory.triggers.clear();
        for (const auto& section : sections_with_prefix(document, "trigger.")) {
            if (factory.triggers.size() >= 64U) break;
            RuntimeTrigger trigger;
            trigger.type = string_value(document, section, "type", "proximity");
            trigger.position = vec3_value(document, section, "position", {});
            trigger.radius = std::clamp(float_value(document, section, "radius", 1.0F), 0.05F, 10'000.0F);
            trigger.action = string_value(document, section, "action", "none");
            trigger.target = string_value(document, section, "target", "");
            trigger.delay = std::clamp(float_value(document, section, "delay", 0.0F), 0.0F, 3600.0F);
            trigger.cooldown = std::clamp(float_value(document, section, "cooldown", 1.3F), 0.05F, 60.0F);
            trigger.repeat = bool_value(document, section, "repeat", false);
            trigger.approved = string_value(document, section, "runtime_status", "telemetry_only") == "approved";
            factory.triggers.push_back(std::move(trigger));
        }
        factory.flow_nodes.clear();
        for (const auto& section : sections_with_prefix(document, "flow.")) {
            if (factory.flow_nodes.size() >= 64U) break;
            RuntimeFlowNode node;
            node.position = vec3_value(document, section, "position", {});
            node.direction = math::normalize_or(vec3_value(document, section, "direction", {1.0F, 0.0F, 0.0F}), {1.0F, 0.0F, 0.0F});
            node.strength = float_value(document, section, "strength", 1.0F);
            node.viscosity = std::max(0.0F, float_value(document, section, "viscosity", 1.0F));
            factory.flow_nodes.push_back(node);
        }
        factory.theme_slots.clear();
        for (const auto& section : sections_with_prefix(document, "theme.")) {
            if (factory.theme_slots.size() >= 64U) break;
            RuntimeThemeSlot slot;
            slot.semantic = string_value(document, section, "semantic", "generic");
            slot.semantic_flag = semantic_flag(slot.semantic);
            parse_hex_color(string_value(document, section, "color", "#D9CC94"), slot.color);
            factory.theme_slots.push_back(slot);
        }
        return true;
    } catch (const std::exception& exception) {
        if (error) *error = exception.what();
        return false;
    }
}

bool load_runtime_interaction(const std::filesystem::path& path,
                              RuntimeInteractionPolicy& policy,
                              std::string* error) {
    try {
        const auto document = data::UDataDocument::load(path);
        policy.present = true;
        policy.enabled = bool_value(document, "interaction", "enabled", false);
        policy.game_enabled = bool_value(document, "interaction", "game_enabled", false);
        policy.stress_enabled = bool_value(document, "interaction", "stress_enabled", true);
        policy.default_cooldown = std::clamp(float_value(document, "interaction", "default_cooldown", 1.3F), 0.05F, 60.0F);
        policy.alert_duration = std::clamp(float_value(document, "interaction", "alert_duration", 3.0F), 0.1F, 60.0F);
        policy.pulse_duration = std::clamp(float_value(document, "interaction", "pulse_duration", 1.25F), 0.1F, 30.0F);
        policy.proxy_lifetime = std::clamp(float_value(document, "interaction", "proxy_lifetime", 5.0F), 0.25F, 120.0F);
        policy.max_state_entries = static_cast<std::size_t>(std::clamp(
            float_value(document, "interaction", "max_state_entries", 256.0F), 16.0F, 1024.0F));
        policy.max_event_ledger = static_cast<std::size_t>(std::clamp(
            float_value(document, "interaction", "max_event_ledger", 256.0F), 16.0F, 1024.0F));
        policy.max_active_proxies = static_cast<std::size_t>(std::clamp(
            float_value(document, "interaction", "max_active_proxies", 16.0F), 1.0F, 64.0F));
        policy.reset_policy = string_value(document, "interaction", "reset_policy", "zone_exit");
        if (policy.reset_policy != "zone_exit" && policy.reset_policy != "session" && policy.reset_policy != "manual") {
            policy.reset_policy = "zone_exit";
        }
        policy.show_runtime_evidence = bool_value(document, "interaction", "show_runtime_evidence", true);
        policy.console_event_log = bool_value(document, "interaction", "console_event_log", true);
        return true;
    } catch (const std::exception& exception) {
        if (error) *error = exception.what();
        return false;
    }
}


bool load_runtime_entity(const std::filesystem::path& path, RuntimeEntity& entity,
                         std::string* error) {
    try {
        const auto document = data::UDataDocument::load(path);
        entity.present = true;
        entity.enabled = bool_value(document, "entity", "enabled", false);
        entity.game_enabled = bool_value(document, "entity", "game_enabled", false);
        entity.stress_enabled = bool_value(document, "entity", "stress_enabled", true);
        entity.entity_kind = string_value(document, "entity", "entity_kind", "enemy");
        entity.movement_profile = string_value(document, "entity", "movement_profile", "stationary");
        entity.movement_speed = std::clamp(float_value(document, "entity", "movement_speed", 1.5F), 0.0F, 20.0F);
        entity.movement_radius = std::clamp(float_value(document, "entity", "movement_radius", 6.0F), 0.0F, 100.0F);
        entity.hover_height = std::clamp(float_value(document, "entity", "hover_height", 0.35F), 0.0F, 10.0F);
        entity.hover_period = std::clamp(float_value(document, "entity", "hover_period", 2.0F), 0.1F, 60.0F);
        entity.detection_radius = std::clamp(float_value(document, "entity", "detection_radius", 10.0F), 0.1F, 500.0F);
        entity.attack_radius = std::clamp(float_value(document, "entity", "attack_radius", 2.5F), 0.1F, entity.detection_radius);
        entity.attack_cooldown = std::clamp(float_value(document, "entity", "attack_cooldown", 1.3F), 0.1F, 60.0F);
        entity.transition_seconds = std::clamp(float_value(document, "entity", "transition_seconds", 0.18F), 0.0F, 5.0F);
        entity.bone_deformation = bool_value(document, "entity", "bone_deformation", true);
        entity.show_rig_debug = bool_value(document, "entity", "show_rig_debug", true);
        entity.show_anchor_debug = bool_value(document, "entity", "show_anchor_debug", true);
        entity.show_state_debug = bool_value(document, "entity", "show_state_debug", true);
        entity.max_deformed_points = static_cast<std::size_t>(std::clamp(
            float_value(document, "entity", "max_deformed_points", 250'000.0F), 1'000.0F, 500'000.0F));
        entity.attack_anchor = string_value(document, "entity", "attack_anchor", "");
        entity.effect_anchor = string_value(document, "entity", "effect_anchor", "");
        entity.state_clips.clear();
        for (const std::string state : {"idle", "move", "alert", "attack"}) {
            RuntimeEntityClip clip;
            const std::string section = "state." + state;
            clip.clip = string_value(document, section, "clip", "Default");
            clip.duration = std::max(0.001F, float_value(document, section, "duration", 1.0F));
            clip.loop = bool_value(document, section, "loop", true);
            entity.state_clips.emplace(state, std::move(clip));
        }
        entity.bones.clear();
        for (const auto& section : sections_with_prefix(document, "bone.")) {
            if (entity.bones.size() >= 64U) break;
            RuntimeEntityBone bone;
            bone.name = string_value(document, section, "name", "bone");
            bone.parent_index = static_cast<int>(std::clamp(float_value(document, section, "parent_index", -1.0F), -1.0F, 63.0F));
            bone.start = vec3_value(document, section, "start", {});
            bone.end = vec3_value(document, section, "end", {0.0F, 1.0F, 0.0F});
            bone.weight_channel = static_cast<int>(std::clamp(float_value(document, section, "weight_channel", 0.0F), 0.0F, 63.0F));
            entity.bones.push_back(std::move(bone));
        }
        entity.bone_keyframes.clear();
        for (const auto& section : sections_with_prefix(document, "bone_keyframe.")) {
            if (entity.bone_keyframes.size() >= 512U) break;
            RuntimeEntityBoneKeyframe key;
            key.state = string_value(document, section, "state", "idle");
            key.bone_channel = static_cast<int>(std::clamp(float_value(document, section, "bone_channel", 0.0F), 0.0F, 63.0F));
            key.time = std::max(0.0F, float_value(document, section, "time", 0.0F));
            key.position = vec3_value(document, section, "position", {});
            key.rotation_degrees = vec3_value(document, section, "rotation", {});
            key.scale = vec3_value(document, section, "scale", {1.0F, 1.0F, 1.0F});
            entity.bone_keyframes.push_back(std::move(key));
        }
        entity.anchors.clear();
        for (const auto& section : sections_with_prefix(document, "anchor.")) {
            if (entity.anchors.size() >= 64U) break;
            RuntimeEntityAnchor anchor;
            anchor.name = string_value(document, section, "name", "anchor");
            anchor.role = string_value(document, section, "role", "generic");
            anchor.position = vec3_value(document, section, "position", {});
            entity.anchors.push_back(std::move(anchor));
        }
        return true;
    } catch (const std::exception& exception) {
        if (error) *error = exception.what();
        return false;
    }
}


bool load_runtime_world(const std::filesystem::path& path, RuntimeWorld& world,
                        std::string* error) {
    try {
        const auto document = data::UDataDocument::load(path);
        world.present = true;
        world.enabled = bool_value(document, "world", "enabled", false);
        world.game_enabled = bool_value(document, "world", "game_enabled", false);
        world.stress_enabled = bool_value(document, "world", "stress_enabled", true);
        world.world_id = string_value(document, "world", "world_id", "pcp3_world");
        world.room_id = string_value(document, "world", "room_id", "");
        world.room_name = string_value(document, "world", "room_name", world.room_id);
        world.host_zone = string_value(document, "world", "host_zone", "Reception Tape");
        world.safe_room = bool_value(document, "world", "safe_room", false);
        world.logical_level = static_cast<int>(std::clamp(float_value(document, "world", "logical_level", 0.0F), -4096.0F, 4096.0F));
        world.reset_policy = string_value(document, "world", "reset_policy", "zone_exit");
        world.execute_portals = bool_value(document, "world", "execute_portals", false);
        world.portal_interaction_required = bool_value(document, "world", "portal_interaction_required", true);
        world.portal_cooldown = std::clamp(float_value(document, "world", "portal_cooldown", 0.8F), 0.1F, 30.0F);
        world.show_portal_debug = bool_value(document, "world", "show_portal_debug", true);
        world.show_bounds_debug = bool_value(document, "world", "show_bounds_debug", false);
        world.max_portals = static_cast<std::size_t>(std::clamp(float_value(document, "world", "max_portals", 32.0F), 1.0F, 32.0F));
        world.max_placements = static_cast<std::size_t>(std::clamp(float_value(document, "world", "max_placements", 64.0F), 1.0F, 64.0F));
        world.apply_theme = bool_value(document, "theme", "apply", true);
        world.theme_asset_id = string_value(document, "theme", "theme_asset_id", "");
        world.liquid.enabled = bool_value(document, "liquid", "enabled", false);
        world.liquid.type = string_value(document, "liquid", "type", "water");
        parse_hex_color(string_value(document, "liquid", "color", "#2F6F8F"), world.liquid.color);
        world.liquid.color[3] = std::clamp(float_value(document, "liquid", "opacity", world.liquid.color[3]), 0.0F, 1.0F);
        world.liquid.wave_amplitude = std::clamp(float_value(document, "liquid", "wave_amplitude", 0.06F), 0.0F, 5.0F);
        world.liquid.wave_frequency = std::clamp(float_value(document, "liquid", "wave_frequency", 0.7F), 0.01F, 20.0F);
        world.liquid.flow_scale = std::clamp(float_value(document, "liquid", "flow_scale", 1.0F), 0.0F, 100.0F);
        world.liquid.max_points = static_cast<std::size_t>(std::clamp(float_value(document, "world", "max_liquid_points", 150000.0F), 1000.0F, 500000.0F));

        world.portals.clear();
        for (const auto& section : sections_with_prefix(document, "portal.")) {
            if (world.portals.size() >= world.max_portals) break;
            RuntimeWorldPortal portal;
            portal.id = string_value(document, section, "id", "portal");
            portal.kind = string_value(document, section, "kind", "door");
            portal.position = vec3_value(document, section, "position", {});
            portal.size = vec3_value(document, section, "size", {1.2F, 2.2F, 0.4F});
            portal.size.x = std::clamp(std::abs(portal.size.x), 0.05F, 100.0F);
            portal.size.y = std::clamp(std::abs(portal.size.y), 0.05F, 100.0F);
            portal.size.z = std::clamp(std::abs(portal.size.z), 0.05F, 100.0F);
            portal.destination_asset_id = string_value(document, section, "destination_asset_id", "");
            portal.destination_portal_id = string_value(document, section, "destination_portal_id", "");
            portal.arrival_offset = vec3_value(document, section, "arrival_offset", {0.0F, 0.0F, 1.4F});
            portal.arrival_yaw_degrees = float_value(document, section, "arrival_yaw_degrees", 0.0F);
            portal.interaction_required = bool_value(document, section, "interaction_required", world.portal_interaction_required);
            portal.one_way = bool_value(document, section, "one_way", false);
            portal.enabled = bool_value(document, section, "enabled", true);
            world.portals.push_back(std::move(portal));
        }

        world.spawn_points.clear();
        for (const auto& section : sections_with_prefix(document, "spawn.")) {
            if (world.spawn_points.size() >= 32U) break;
            RuntimeWorldSpawn spawn;
            spawn.id = string_value(document, section, "id", "spawn");
            spawn.role = string_value(document, section, "role", "default");
            spawn.position = vec3_value(document, section, "position", {});
            spawn.yaw_degrees = float_value(document, section, "yaw_degrees", 0.0F);
            spawn.enabled = bool_value(document, section, "enabled", true);
            world.spawn_points.push_back(std::move(spawn));
        }

        world.placements.clear();
        for (const auto& section : sections_with_prefix(document, "world_placement.")) {
            if (world.placements.size() >= world.max_placements) break;
            RuntimePlacement placement;
            placement.asset_id = string_value(document, section, "asset_id", "");
            placement.kind = string_value(document, section, "kind", "object");
            placement.position = vec3_value(document, section, "position", {});
            placement.rotation_degrees = vec3_value(document, section, "rotation", {});
            placement.scale = std::clamp(float_value(document, section, "scale", 1.0F), 0.001F, 1000.0F);
            placement.enabled = bool_value(document, section, "enabled", true);
            world.placements.push_back(std::move(placement));
        }

        world.theme_slots.clear();
        for (const auto& section : sections_with_prefix(document, "world_theme.")) {
            if (world.theme_slots.size() >= 64U) break;
            RuntimeThemeSlot slot;
            slot.semantic = string_value(document, section, "semantic", "generic");
            slot.semantic_flag = semantic_flag(slot.semantic);
            parse_hex_color(string_value(document, section, "color", "#D9CC94"), slot.color);
            world.theme_slots.push_back(std::move(slot));
        }

        world.flow_nodes.clear();
        for (const auto& section : sections_with_prefix(document, "world_flow.")) {
            if (world.flow_nodes.size() >= 64U) break;
            RuntimeFlowNode node;
            node.position = vec3_value(document, section, "position", {});
            node.direction = math::normalize_or(vec3_value(document, section, "direction", {1.0F, 0.0F, 0.0F}), {1.0F, 0.0F, 0.0F});
            node.strength = std::clamp(float_value(document, section, "strength", 1.0F), -100.0F, 100.0F);
            node.viscosity = std::clamp(float_value(document, section, "viscosity", 1.0F), 0.0F, 100.0F);
            world.flow_nodes.push_back(std::move(node));
        }
        return true;
    } catch (const std::exception& exception) {
        if (error) *error = exception.what();
        return false;
    }
}


bool load_runtime_encounter(const std::filesystem::path& path, RuntimeEncounter& encounter,
                            std::string* error) {
    try {
        const auto document = data::UDataDocument::load(path);
        encounter.present = true;
        encounter.enabled = bool_value(document, "encounter", "enabled", false);
        encounter.game_enabled = bool_value(document, "encounter", "game_enabled", false);
        encounter.stress_enabled = bool_value(document, "encounter", "stress_enabled", true);
        encounter.encounter_id = string_value(document, "encounter", "encounter_id", "encounter");
        encounter.host_zone = string_value(document, "encounter", "host_zone", "Reception Tape");
        encounter.start_condition = string_value(document, "encounter", "start_condition", "world_enter");
        encounter.start_position = vec3_value(document, "encounter", "start_position", {});
        encounter.start_radius = std::clamp(float_value(document, "encounter", "start_radius", 8.0F), 0.1F, 500.0F);
        encounter.start_delay = std::clamp(float_value(document, "encounter", "start_delay", 0.0F), 0.0F, 600.0F);
        encounter.completion_policy = string_value(document, "encounter", "completion_policy", "all_waves_cleared");
        encounter.completion_seconds = std::clamp(float_value(document, "encounter", "completion_seconds", 30.0F), 0.1F, 3600.0F);
        encounter.completion_delay = std::clamp(float_value(document, "encounter", "completion_delay", 1.0F), 0.0F, 60.0F);
        encounter.inter_wave_delay = std::clamp(float_value(document, "encounter", "inter_wave_delay", 1.3F), 0.0F, 60.0F);
        encounter.entity_lifetime = std::clamp(float_value(document, "encounter", "entity_lifetime", 8.0F), 0.25F, 600.0F);
        encounter.reset_policy = string_value(document, "encounter", "reset_policy", "zone_exit");
        encounter.show_debug = bool_value(document, "encounter", "show_debug", true);
        encounter.console_events = bool_value(document, "encounter", "console_events", true);
        encounter.max_waves = static_cast<std::size_t>(std::clamp(float_value(document, "encounter", "max_waves", 16.0F), 1.0F, 16.0F));
        encounter.max_active_entities = static_cast<std::size_t>(std::clamp(float_value(document, "encounter", "max_active_entities", 16.0F), 1.0F, 32.0F));
        encounter.max_total_spawns = static_cast<std::size_t>(std::clamp(float_value(document, "encounter", "max_total_spawns", 64.0F), 1.0F, 128.0F));
        encounter.max_friendlies = static_cast<std::size_t>(std::clamp(float_value(document, "encounter", "max_friendlies", 8.0F), 0.0F, 16.0F));
        encounter.max_boss_phases = static_cast<std::size_t>(std::clamp(float_value(document, "encounter", "max_boss_phases", 4.0F), 0.0F, 8.0F));
        encounter.reward_policy = string_value(document, "reward", "policy", "telemetry_only");
        encounter.reward_proofs = static_cast<int>(std::clamp(float_value(document, "reward", "proofs", 0.0F), 0.0F, 999.0F));
        encounter.reward_xar = static_cast<int>(std::clamp(float_value(document, "reward", "xar", 0.0F), 0.0F, 99999.0F));
        encounter.reward_scrap = static_cast<int>(std::clamp(float_value(document, "reward", "scrap", 0.0F), 0.0F, 9999.0F));

        encounter.waves.clear();
        for (const auto& section : sections_with_prefix(document, "wave.")) {
            if (encounter.waves.size() >= encounter.max_waves) break;
            RuntimeEncounterWave wave;
            wave.id = string_value(document, section, "id", "wave");
            wave.index = static_cast<int>(std::clamp(float_value(document, section, "index", static_cast<float>(encounter.waves.size() + 1U)), 0.0F, 999.0F));
            wave.asset_ids = string_list_value(document, section, "asset_ids");
            wave.count = static_cast<std::size_t>(std::clamp(float_value(document, section, "count", 1.0F), 1.0F, static_cast<float>(encounter.max_total_spawns)));
            wave.delay = std::clamp(float_value(document, section, "delay", 0.0F), 0.0F, 600.0F);
            wave.active_seconds = std::clamp(float_value(document, section, "active_seconds", encounter.entity_lifetime), 0.25F, 600.0F);
            wave.spawn_role = string_value(document, section, "spawn_role", "encounter");
            wave.spread_radius = std::clamp(float_value(document, section, "spread_radius", 3.0F), 0.0F, 100.0F);
            wave.completion_policy = string_value(document, section, "completion_policy", "lifetime");
            encounter.waves.push_back(std::move(wave));
        }
        std::sort(encounter.waves.begin(), encounter.waves.end(), [](const auto& left, const auto& right) {
            return left.index < right.index;
        });

        encounter.boss_phases.clear();
        for (const auto& section : sections_with_prefix(document, "boss_phase.")) {
            if (encounter.boss_phases.size() >= encounter.max_boss_phases) break;
            RuntimeBossPhase phase;
            phase.id = string_value(document, section, "id", "phase");
            phase.name = string_value(document, section, "name", phase.id);
            phase.progress_threshold = std::clamp(float_value(document, section, "progress_threshold", 0.0F), 0.0F, 1.0F);
            phase.clip = string_value(document, section, "clip", "Default");
            phase.movement_profile = string_value(document, section, "movement_profile", "stationary");
            phase.theme_target = string_value(document, section, "theme_target", "");
            phase.effect_anchor = string_value(document, section, "effect_anchor", "");
            encounter.boss_phases.push_back(std::move(phase));
        }
        std::sort(encounter.boss_phases.begin(), encounter.boss_phases.end(), [](const auto& left, const auto& right) {
            return left.progress_threshold < right.progress_threshold;
        });

        encounter.friendlies.clear();
        for (const auto& section : sections_with_prefix(document, "friendly.")) {
            if (encounter.friendlies.size() >= encounter.max_friendlies) break;
            RuntimeEncounterFriendly friendly;
            friendly.id = string_value(document, section, "id", "friendly");
            friendly.asset_id = string_value(document, section, "asset_id", "");
            friendly.position = vec3_value(document, section, "position", {});
            friendly.rotation_degrees = vec3_value(document, section, "rotation_degrees", {});
            friendly.scale = std::clamp(float_value(document, section, "scale", 1.0F), 0.001F, 1000.0F);
            friendly.group = string_value(document, section, "group", "friendlies");
            friendly.enabled = bool_value(document, section, "enabled", true);
            encounter.friendlies.push_back(std::move(friendly));
        }
        return true;
    } catch (const std::exception& exception) {
        if (error) *error = exception.what();
        return false;
    }
}

bool encounter_target_enabled(const RuntimeEncounter& encounter, PreviewPurpose purpose) noexcept {
    return purpose == PreviewPurpose::game ? encounter.game_enabled : encounter.stress_enabled;
}

bool world_target_enabled(const RuntimeWorld& world, PreviewPurpose purpose) noexcept {
    return purpose == PreviewPurpose::game ? world.game_enabled : world.stress_enabled;
}

bool entity_target_enabled(const RuntimeEntity& entity, PreviewPurpose purpose) noexcept {
    return purpose == PreviewPurpose::game ? entity.game_enabled : entity.stress_enabled;
}

struct RuntimeEntitySample {
    std::string state{"idle"};
    math::Vec3 movement_offset{};
    math::Vec3 facing_rotation{};
};

RuntimeEntitySample sample_entity_runtime(const RuntimeEntity& entity, math::Vec3 origin,
                                          RuntimeContext context) noexcept {
    RuntimeEntitySample sample;
    const math::Vec3 delta = context.viewer_position - origin;
    const float distance = math::length(delta);
    const float cooldown = std::max(0.1F, entity.attack_cooldown);
    const float phase = std::fmod(static_cast<float>(std::max(0.0, context.time_seconds)), cooldown);
    if (distance <= entity.attack_radius && phase <= std::min(0.25F, cooldown * 0.25F)) sample.state = "attack";
    else if (distance <= entity.attack_radius) sample.state = "alert";
    else if (distance <= entity.detection_radius) sample.state = "move";
    else sample.state = "idle";

    const float time = static_cast<float>(context.time_seconds);
    if (entity.movement_profile == "hover") {
        const float period = std::max(0.1F, entity.hover_period);
        sample.movement_offset.y = std::sin(time * 2.0F * kPi / period) * entity.hover_height;
    } else if (entity.movement_profile == "patrol_line") {
        sample.movement_offset.x = std::sin(time * std::max(0.05F, entity.movement_speed)) * entity.movement_radius;
    } else if (entity.movement_profile == "face_viewer") {
        if (std::abs(delta.x) + std::abs(delta.z) > 0.0001F) {
            sample.facing_rotation.y = std::atan2(delta.x, -delta.z) * 180.0F / kPi;
        }
    } else if (entity.movement_profile == "approach_viewer" || entity.movement_profile == "friendly_follow") {
        math::Vec3 horizontal{delta.x, 0.0F, delta.z};
        const float horizontal_distance = math::length(horizontal);
        const float stop_distance = entity.movement_profile == "friendly_follow"
            ? std::max(2.0F, entity.attack_radius)
            : entity.attack_radius;
        if (horizontal_distance > stop_distance + 0.01F) {
            const math::Vec3 direction = math::normalize_or(horizontal, {0.0F, 0.0F, -1.0F});
            const float wanted = std::min(entity.movement_radius, horizontal_distance - stop_distance);
            const float response = std::clamp(entity.movement_speed / 6.0F, 0.05F, 1.0F);
            sample.movement_offset = direction * (wanted * response);
            sample.facing_rotation.y = std::atan2(direction.x, -direction.z) * 180.0F / kPi;
        }
    }
    return sample;
}

RuntimeKeyframe sample_entity_bone(const RuntimeEntity& entity, std::string_view state,
                                   int channel, double time_seconds) noexcept {
    RuntimeKeyframe result;
    std::vector<const RuntimeEntityBoneKeyframe*> keys;
    for (const auto& key : entity.bone_keyframes) {
        if (key.state == state && key.bone_channel == channel) keys.push_back(&key);
    }
    if (keys.empty()) return result;
    std::sort(keys.begin(), keys.end(), [](const auto* a, const auto* b) { return a->time < b->time; });
    float duration = 1.0F;
    bool loop = true;
    if (const auto found = entity.state_clips.find(std::string(state)); found != entity.state_clips.end()) {
        duration = std::max(0.001F, found->second.duration);
        loop = found->second.loop;
    }
    float time = static_cast<float>(std::max(0.0, time_seconds));
    if (loop) time = std::fmod(time, duration);
    const auto copy_key = [](const RuntimeEntityBoneKeyframe& key) {
        RuntimeKeyframe value;
        value.time = key.time;
        value.position = key.position;
        value.rotation_degrees = key.rotation_degrees;
        value.scale = key.scale;
        return value;
    };
    if (time <= keys.front()->time) return copy_key(*keys.front());
    if (time >= keys.back()->time) return copy_key(*keys.back());
    for (std::size_t index = 1U; index < keys.size(); ++index) {
        const auto& right = *keys[index];
        if (right.time < time) continue;
        const auto& left = *keys[index - 1U];
        const float span = std::max(0.0001F, right.time - left.time);
        const float amount = std::clamp((time - left.time) / span, 0.0F, 1.0F);
        const auto lerp = [amount](math::Vec3 a, math::Vec3 b) { return a + (b - a) * amount; };
        result.time = time;
        result.position = lerp(left.position, right.position);
        result.rotation_degrees = lerp(left.rotation_degrees, right.rotation_degrees);
        result.scale = lerp(left.scale, right.scale);
        return result;
    }
    return copy_key(*keys.back());
}

math::Vec3 deform_entity_local(const LayeredPoint& source, const RuntimeEntity* entity,
                               std::string_view state, double time_seconds) noexcept {
    math::Vec3 original{source.point.position[0], source.point.position[1], source.point.position[2]};
    if (entity == nullptr || !entity->bone_deformation || entity->bones.empty()) return original;
    const int marker = static_cast<int>(std::lround(source.attribute1));
    int channel = -1;
    if (marker == 41) channel = 0;
    else if (marker >= 1000 && marker < 1064) channel = marker - 1000;
    if (channel < 0) return original;
    const float weight = std::clamp(source.attribute0, 0.0F, 1.0F);
    if (weight <= 0.0F) return original;
    int bone_index = -1;
    for (std::size_t index = 0U; index < entity->bones.size(); ++index) {
        if (entity->bones[index].weight_channel == channel) { bone_index = static_cast<int>(index); break; }
    }
    if (bone_index < 0) return original;
    std::array<int, 64> chain{};
    std::size_t count = 0U;
    int current = bone_index;
    while (current >= 0 && current < static_cast<int>(entity->bones.size()) && count < chain.size()) {
        chain[count++] = current;
        current = entity->bones[static_cast<std::size_t>(current)].parent_index;
    }
    math::Vec3 transformed = original;
    while (count > 0U) {
        const auto& bone = entity->bones[static_cast<std::size_t>(chain[--count])];
        const auto key = sample_entity_bone(*entity, state, bone.weight_channel, time_seconds);
        math::Vec3 local = transformed - bone.start;
        local = {local.x * key.scale.x, local.y * key.scale.y, local.z * key.scale.z};
        transformed = bone.start + rotate_xyz(local, key.rotation_degrees) + key.position;
    }
    return original + (transformed - original) * weight;
}

render::PointGpu transformed_point(const LayeredPoint& source, math::Vec3 offset,
                                   math::Vec3 scale, math::Vec3 rotation,
                                   const RuntimeFactory* factory,
                                   const RuntimeWorld* world = nullptr,
                                   const RuntimeAssetState* interaction_state = nullptr,
                                   double time_seconds = 0.0,
                                   const RuntimeEntity* entity = nullptr,
                                   std::string_view entity_state = "idle") noexcept {
    auto point = source.point;
    const math::Vec3 entity_local = deform_entity_local(source, entity, entity_state, time_seconds);
    math::Vec3 local{entity_local.x * scale.x, entity_local.y * scale.y, entity_local.z * scale.z};
    local = rotate_xyz(local, rotation);
    point.position[0] = local.x + offset.x;
    point.position[1] = local.y + offset.y;
    point.position[2] = local.z + offset.z;
    math::Vec3 normal = rotate_xyz({point.normal[0], point.normal[1], point.normal[2]}, rotation);
    point.normal[0] = normal.x; point.normal[1] = normal.y; point.normal[2] = normal.z;
    const float radius_scale = std::max({std::abs(scale.x), std::abs(scale.y), std::abs(scale.z), 0.0001F});
    point.radius = std::max(0.1F, point.radius * radius_scale);
    if (factory != nullptr) {
        for (const auto& slot : factory->theme_slots) {
            if (slot.semantic_flag != source.flags) continue;
            point.color[0] = slot.color[0]; point.color[1] = slot.color[1];
            point.color[2] = slot.color[2]; point.color[3] *= slot.color[3];
            break;
        }
    }
    if (world != nullptr) {
        if (world->apply_theme) {
            for (const auto& slot : world->theme_slots) {
                if (slot.semantic_flag != source.flags) continue;
                point.color[0] = slot.color[0]; point.color[1] = slot.color[1];
                point.color[2] = slot.color[2]; point.color[3] *= slot.color[3];
                break;
            }
        }
        if (world->liquid.enabled && (source.flags == 6U || source.flags == 7U)) {
            const float phase = static_cast<float>(time_seconds) * world->liquid.wave_frequency * 2.0F * kPi;
            const float spatial = (point.position[0] + point.position[2]) * 0.35F;
            const float amplitude = source.flags == 6U ? world->liquid.wave_amplitude : world->liquid.wave_amplitude * 0.25F;
            point.position[1] += std::sin(phase + spatial) * amplitude;
            point.color[0] = world->liquid.color[0]; point.color[1] = world->liquid.color[1];
            point.color[2] = world->liquid.color[2]; point.color[3] *= world->liquid.color[3];
        }
    }
    if (interaction_state != nullptr && !interaction_state->theme_target.empty()) {
        float override_color[4]{point.color[0], point.color[1], point.color[2], point.color[3]};
        bool found = false;
        if (interaction_state->theme_target.front() == '#') {
            parse_hex_color(interaction_state->theme_target, override_color);
            found = true;
        } else if (factory != nullptr) {
            for (const auto& slot : factory->theme_slots) {
                if (slot.semantic != interaction_state->theme_target) continue;
                override_color[0] = slot.color[0]; override_color[1] = slot.color[1];
                override_color[2] = slot.color[2]; override_color[3] = slot.color[3];
                found = true;
                break;
            }
        }
        if (found) {
            point.color[0] = override_color[0]; point.color[1] = override_color[1];
            point.color[2] = override_color[2]; point.color[3] *= override_color[3];
        }
    }
    if (interaction_state != nullptr && time_seconds < interaction_state->pulse_until && source.flags == 8U) {
        const float pulse = 1.25F + 0.25F * std::sin(static_cast<float>(time_seconds) * 12.0F);
        point.color[0] = std::clamp(point.color[0] * pulse, 0.0F, 1.0F);
        point.color[1] = std::clamp(point.color[1] * pulse, 0.0F, 1.0F);
        point.color[2] = std::clamp(point.color[2] * pulse, 0.0F, 1.0F);
        point.radius = std::max(point.radius, 1.4F * point.radius);
    }
    return point;
}

void append_sampled(std::vector<render::PointGpu>& target,
                    const std::vector<render::PointGpu>& source,
                    std::size_t limit) {
    if (source.empty() || target.size() >= limit) return;
    const std::size_t remaining = limit - target.size();
    if (source.size() <= remaining) {
        target.insert(target.end(), source.begin(), source.end());
        return;
    }
    const std::size_t stride = std::max<std::size_t>(1U, source.size() / remaining);
    for (std::size_t index = 0U; index < source.size() && target.size() < limit; index += stride) {
        target.push_back(source[index]);
    }
}

render::PointGpu evidence_point(math::Vec3 position, float r, float g, float b, float radius = 2.0F) noexcept {
    render::PointGpu point{};
    point.position[0] = position.x; point.position[1] = position.y; point.position[2] = position.z;
    point.radius = radius;
    point.color[0] = r; point.color[1] = g; point.color[2] = b; point.color[3] = 0.9F;
    point.normal[1] = 1.0F; point.density = 1.0F;
    return point;
}

void append_ring(std::vector<render::PointGpu>& target, math::Vec3 center, float radius,
                 float r, float g, float b, std::size_t limit) {
    const int count = std::clamp(static_cast<int>(radius * 20.0F), 20, 180);
    for (int axis = 0; axis < 3 && target.size() < limit; ++axis) {
        for (int index = 0; index < count && target.size() < limit; ++index) {
            const float angle = 2.0F * kPi * static_cast<float>(index) / static_cast<float>(count);
            math::Vec3 p = center;
            const int first = (axis + 1) % 3, second = (axis + 2) % 3;
            float* values[3]{&p.x, &p.y, &p.z};
            *values[first] += std::cos(angle) * radius;
            *values[second] += std::sin(angle) * radius;
            target.push_back(evidence_point(p, r, g, b, 1.7F));
        }
    }
}

void append_line(std::vector<render::PointGpu>& target, math::Vec3 start, math::Vec3 end,
                 float r, float g, float b, std::size_t limit) {
    const float length = math::length(end - start);
    const int count = std::clamp(static_cast<int>(length * 18.0F) + 2, 2, 160);
    for (int index = 0; index < count && target.size() < limit; ++index) {
        const float amount = static_cast<float>(index) / static_cast<float>(count - 1);
        target.push_back(evidence_point(start + (end - start) * amount, r, g, b, 1.8F));
    }
}


void append_box(std::vector<render::PointGpu>& target, math::Vec3 center, math::Vec3 size,
                float r, float g, float b, std::size_t limit) {
    const math::Vec3 half{std::abs(size.x) * 0.5F, std::abs(size.y) * 0.5F, std::abs(size.z) * 0.5F};
    const std::array<math::Vec3, 8> corners{{
        center + math::Vec3{-half.x, -half.y, -half.z}, center + math::Vec3{ half.x, -half.y, -half.z},
        center + math::Vec3{-half.x,  half.y, -half.z}, center + math::Vec3{ half.x,  half.y, -half.z},
        center + math::Vec3{-half.x, -half.y,  half.z}, center + math::Vec3{ half.x, -half.y,  half.z},
        center + math::Vec3{-half.x,  half.y,  half.z}, center + math::Vec3{ half.x,  half.y,  half.z},
    }};
    constexpr std::array<std::array<int, 2>, 12> edges{{
        {{0,1}},{{0,2}},{{1,3}},{{2,3}},{{4,5}},{{4,6}},{{5,7}},{{6,7}},
        {{0,4}},{{1,5}},{{2,6}},{{3,7}},
    }};
    for (const auto& edge : edges) {
        if (target.size() >= limit) break;
        append_line(target, corners[static_cast<std::size_t>(edge[0])], corners[static_cast<std::size_t>(edge[1])], r, g, b, limit);
    }
}

bool interaction_target_enabled(const RuntimeInteractionPolicy& policy, PreviewPurpose purpose) noexcept {
    return purpose == PreviewPurpose::game ? policy.game_enabled : policy.stress_enabled;
}

math::Vec3 transformed_trigger_center(const RuntimeTrigger& trigger, math::Vec3 root_offset,
                                      math::Vec3 root_scale, math::Vec3 root_rotation) noexcept {
    const math::Vec3 local{
        trigger.position.x * root_scale.x,
        trigger.position.y * root_scale.y,
        trigger.position.z * root_scale.z,
    };
    return root_offset + rotate_xyz(local, root_rotation);
}

void apply_interaction_action(const Asset& asset, const RuntimeTrigger& trigger, std::size_t trigger_index,
                              math::Vec3 world_position, RuntimeContext context, RuntimeInteractionState& state) {
    auto& asset_state = state.asset(asset.metadata.asset_id);
    if (trigger.action == "show") {
        asset_state.visible = true;
    } else if (trigger.action == "hide") {
        asset_state.visible = false;
    } else if (trigger.action == "reveal") {
        asset_state.visible = true;
        asset_state.revealed = true;
    } else if (trigger.action == "alert") {
        asset_state.alert_until = context.time_seconds + static_cast<double>(asset.runtime_interaction.alert_duration);
    } else if (trigger.action == "pulse_light") {
        asset_state.pulse_until = context.time_seconds + static_cast<double>(asset.runtime_interaction.pulse_duration);
    } else if (trigger.action == "set_theme") {
        asset_state.theme_target = trigger.target;
    } else if (trigger.action == "spawn_proxy") {
        asset_state.proxies.push_back({world_position, context.time_seconds + static_cast<double>(asset.runtime_interaction.proxy_lifetime)});
        if (asset_state.proxies.size() > asset.runtime_interaction.max_active_proxies) {
            const auto remove_count = asset_state.proxies.size() - asset.runtime_interaction.max_active_proxies;
            asset_state.proxies.erase(asset_state.proxies.begin(), asset_state.proxies.begin() + static_cast<std::ptrdiff_t>(remove_count));
        }
    }
    state.push_event(
        {context.time_seconds, asset.metadata.asset_id, trigger_index, trigger.action, trigger.target,
         asset.runtime_interaction.console_event_log},
        asset.runtime_interaction.max_event_ledger);
}

void evaluate_asset_interactions(const Asset& asset, PreviewPurpose purpose, RuntimeContext context,
                                 math::Vec3 root_offset, math::Vec3 root_scale, math::Vec3 root_rotation) {
    if (context.interaction_state == nullptr || !asset.runtime_interaction.present ||
        !asset.runtime_interaction.enabled || !interaction_target_enabled(asset.runtime_interaction, purpose)) return;
    auto& state = *context.interaction_state;
    for (std::size_t index = 0U; index < asset.runtime_factory.triggers.size(); ++index) {
        const auto& trigger = asset.runtime_factory.triggers[index];
        if (!trigger.approved || trigger.action == "none") continue;
        const math::Vec3 center = transformed_trigger_center(trigger, root_offset, root_scale, root_rotation);
        const bool inside = math::length(context.viewer_position - center) <= trigger.radius;
        bool condition = false;
        if (trigger.type == "proximity" || trigger.type == "threshold") condition = inside;
        else if (trigger.type == "scanner") condition = context.scanner_active;
        else if (trigger.type == "interaction") condition = inside && context.interaction_pressed;
        else if (trigger.type == "timer") condition = true;
        auto& memory = state.trigger(asset.metadata.asset_id, index);
        if (condition && !memory.condition_active) memory.armed_since = context.time_seconds;
        memory.condition_active = condition;
        if (!condition) continue;
        const double cooldown = static_cast<double>(trigger.cooldown > 0.0F ? trigger.cooldown : asset.runtime_interaction.default_cooldown);
        const bool delay_ready = context.time_seconds >= memory.armed_since + static_cast<double>(trigger.delay);
        const bool cooldown_ready = context.time_seconds >= memory.last_fired + cooldown;
        const bool lifetime_ready = !memory.fired_once || trigger.repeat;
        if (!delay_ready || !cooldown_ready || !lifetime_ready) continue;
        memory.fired_once = true;
        memory.last_fired = context.time_seconds;
        apply_interaction_action(asset, trigger, index, center, context, state);
    }
}

bool encounter_start_condition(const RuntimeEncounter& encounter, RuntimeContext context,
                               math::Vec3 origin) noexcept {
    if (encounter.start_condition == "world_enter" || encounter.start_condition == "timer") return true;
    if (encounter.start_condition == "scanner") return context.scanner_active;
    if (encounter.start_condition == "interaction") {
        return context.interaction_pressed &&
            math::length(context.viewer_position - (origin + encounter.start_position)) <= encounter.start_radius;
    }
    if (encounter.start_condition == "proximity") {
        return math::length(context.viewer_position - (origin + encounter.start_position)) <= encounter.start_radius;
    }
    return false;
}

RuntimeEncounterAssetState* update_encounter_runtime(const Asset& asset, PreviewPurpose purpose,
                                                     RuntimeContext context, math::Vec3 origin) {
    if (context.encounter_state == nullptr || !asset.runtime_encounter.present ||
        !asset.runtime_encounter.enabled || !encounter_target_enabled(asset.runtime_encounter, purpose)) return nullptr;
    auto& state = context.encounter_state->asset(asset.metadata.asset_id);
    const auto& encounter = asset.runtime_encounter;
    auto push = [&](std::string kind, std::size_t wave_index = 0U, std::string referenced = {}) {
        RuntimeEncounterEvent event;
        event.time_seconds = context.time_seconds;
        event.host_asset_id = asset.metadata.asset_id;
        event.encounter_id = encounter.encounter_id;
        event.kind = std::move(kind);
        event.wave_index = wave_index;
        event.referenced_asset_id = std::move(referenced);
        event.reward_policy = encounter.reward_policy;
        event.reward_proofs = encounter.reward_proofs;
        event.reward_xar = encounter.reward_xar;
        event.reward_scrap = encounter.reward_scrap;
        event.console_log = encounter.console_events;
        context.encounter_state->push_event(std::move(event));
    };

    state.instances.erase(std::remove_if(state.instances.begin(), state.instances.end(),
        [&](const RuntimeEncounterInstance& instance) {
            if (instance.friendly || instance.expires_at > context.time_seconds) return false;
            push("entity_retired", instance.wave_index, instance.asset_id);
            return true;
        }), state.instances.end());

    if (!state.started && encounter_start_condition(encounter, context, origin)) {
        if (!state.armed) {
            state.armed = true;
            state.armed_since = context.time_seconds;
        }
        if (context.time_seconds >= state.armed_since + encounter.start_delay) {
            state.started = true;
            state.started_at = context.time_seconds;
            state.wave_ready_at = context.time_seconds +
                (encounter.waves.empty() ? 0.0 : static_cast<double>(encounter.waves.front().delay));
            push("encounter_started");
        }
    }
    if (!state.started || state.completed) return &state;

    const std::size_t active_count = static_cast<std::size_t>(std::count_if(
        state.instances.begin(), state.instances.end(), [](const auto& instance) { return !instance.friendly; }));
    if (state.next_wave < encounter.waves.size() && active_count == 0U &&
        context.time_seconds >= state.wave_ready_at && state.total_spawned < encounter.max_total_spawns) {
        const auto& wave = encounter.waves[state.next_wave];
        const std::size_t room = encounter.max_active_entities > active_count
            ? encounter.max_active_entities - active_count : 0U;
        const std::size_t remaining = encounter.max_total_spawns - state.total_spawned;
        const std::size_t count = std::min({wave.count, room, remaining});
        push("wave_started", state.next_wave);
        for (std::size_t index = 0U; index < count; ++index) {
            if (wave.asset_ids.empty()) break;
            const float angle = 2.0F * kPi * static_cast<float>(index) /
                static_cast<float>(std::max<std::size_t>(1U, count));
            const float ring = wave.spread_radius * (0.35F + 0.65F * static_cast<float>((index % 3U) + 1U) / 3.0F);
            RuntimeEncounterInstance instance;
            instance.asset_id = wave.asset_ids[index % wave.asset_ids.size()];
            instance.position = origin + encounter.start_position +
                math::Vec3{std::cos(angle) * ring, 0.0F, std::sin(angle) * ring};
            instance.rotation_degrees.y = -angle * 180.0F / kPi;
            instance.scale = 1.0F;
            instance.wave_index = state.next_wave;
            instance.spawned_at = context.time_seconds;
            instance.expires_at = context.time_seconds + wave.active_seconds;
            state.instances.push_back(instance);
            ++state.total_spawned;
            push("entity_spawned", state.next_wave, instance.asset_id);
        }
        ++state.next_wave;
        const double next_delay = state.next_wave < encounter.waves.size()
            ? static_cast<double>(encounter.waves[state.next_wave].delay) : 0.0;
        state.wave_ready_at = context.time_seconds + static_cast<double>(wave.active_seconds) +
            static_cast<double>(encounter.inter_wave_delay) + next_delay;
    }

    bool complete = false;
    if (encounter.completion_policy == "timer") {
        complete = context.time_seconds >= state.started_at + encounter.completion_seconds;
    } else if (encounter.completion_policy == "all_waves_cleared") {
        const bool no_active = std::none_of(state.instances.begin(), state.instances.end(),
            [](const auto& instance) { return !instance.friendly; });
        complete = state.next_wave >= encounter.waves.size() && no_active &&
            context.time_seconds >= state.wave_ready_at + encounter.completion_delay;
    }
    if (complete) {
        state.completed = true;
        state.completed_at = context.time_seconds;
        push("encounter_completed", state.next_wave == 0U ? 0U : state.next_wave - 1U);
        if (!state.completion_emitted) {
            state.completion_emitted = true;
            push("reward_hook", state.next_wave == 0U ? 0U : state.next_wave - 1U);
        }
    }
    return &state;
}

}  // namespace

bool load_runtime_streaming(const std::filesystem::path& path,
                            RuntimeStreaming& streaming,
                            std::string* error) {
    try {
        const auto document = data::UDataDocument::load(path);
        streaming.present = true;
        streaming.enabled = bool_value(document, "streaming", "enabled", false);
        streaming.game_enabled = bool_value(document, "streaming", "game_enabled", false);
        streaming.stress_enabled = bool_value(document, "streaming", "stress_enabled", true);
        streaming.profile = string_value(document, "streaming", "profile", "adaptive_8m");
        streaming.lod_policy = string_value(document, "streaming", "lod_policy", "distance_semantic");
        streaming.chunk_edge = std::clamp(float_value(document, "streaming", "chunk_edge", 8.0F), 1.0F, 128.0F);
        streaming.chunk_point_target = static_cast<std::size_t>(std::clamp(
            float_value(document, "streaming", "chunk_point_target", 65'536.0F), 1'024.0F, 500'000.0F));
        streaming.max_resident_chunks = static_cast<std::size_t>(std::clamp(
            float_value(document, "streaming", "max_resident_chunks", 64.0F), 1.0F, 4'096.0F));
        streaming.background_loading = bool_value(document, "streaming", "background_loading", true);
        streaming.preload_adjacent = bool_value(document, "streaming", "preload_adjacent", true);
        streaming.near_distance = std::clamp(float_value(document, "streaming", "near_distance", 16.0F), 0.1F, 10'000.0F);
        streaming.mid_distance = std::clamp(float_value(document, "streaming", "mid_distance", 48.0F), streaming.near_distance, 20'000.0F);
        streaming.far_distance = std::clamp(float_value(document, "streaming", "far_distance", 120.0F), streaming.mid_distance, 50'000.0F);
        streaming.near_ratio = std::clamp(float_value(document, "streaming", "near_ratio", 1.0F), 0.0F, 1.0F);
        streaming.mid_ratio = std::clamp(float_value(document, "streaming", "mid_ratio", 0.55F), 0.0F, 1.0F);
        streaming.far_ratio = std::clamp(float_value(document, "streaming", "far_ratio", 0.22F), 0.0F, 1.0F);
        streaming.very_far_ratio = std::clamp(float_value(document, "streaming", "very_far_ratio", 0.06F), 0.0F, 1.0F);
        streaming.minimum_points = static_cast<std::size_t>(std::clamp(
            float_value(document, "streaming", "minimum_points", 512.0F), 1.0F, 500'000.0F));
        streaming.maximum_points = static_cast<std::size_t>(std::clamp(
            float_value(document, "streaming", "maximum_points", 500'000.0F),
            static_cast<float>(streaming.minimum_points), 500'000.0F));
        streaming.frame_upload_budget_points = static_cast<std::size_t>(std::clamp(
            float_value(document, "streaming", "frame_upload_budget_points", 100'000.0F), 1'000.0F, 2'000'000.0F));
        streaming.preserve_semantic_points = bool_value(document, "streaming", "preserve_semantic_points", true);
        streaming.semantic_reserve_ratio = std::clamp(float_value(document, "streaming", "semantic_reserve_ratio", 0.12F), 0.0F, 1.0F);
        streaming.stability_hysteresis = std::clamp(float_value(document, "streaming", "stability_hysteresis", 0.12F), 0.0F, 1.0F);
        streaming.show_debug = bool_value(document, "streaming", "show_debug", false);
        return true;
    } catch (const std::exception& exception) {
        if (error) *error = exception.what();
        return false;
    }
}

std::size_t streaming_point_budget(const RuntimeStreaming& streaming,
                                   std::size_t available_points,
                                   float distance) noexcept {
    if (available_points == 0U) return 0U;
    float ratio = streaming.near_ratio;
    if (streaming.lod_policy != "fixed") {
        if (distance > streaming.far_distance) ratio = streaming.very_far_ratio;
        else if (distance > streaming.mid_distance) ratio = streaming.far_ratio;
        else if (distance > streaming.near_distance) ratio = streaming.mid_ratio;
    }
    ratio = std::clamp(ratio, 0.0F, 1.0F);
    const double exact = static_cast<double>(available_points) * static_cast<double>(ratio);
    const auto requested = static_cast<std::size_t>(std::ceil(std::max(0.0, exact - 1.0e-6)));
    const std::size_t minimum = std::min(available_points, streaming.minimum_points);
    return std::min({available_points, streaming.maximum_points, std::max(minimum, requested)});
}

std::vector<std::size_t> streaming_sample_indices(
    const std::vector<LayeredPoint>& points,
    const RuntimeStreaming& streaming,
    std::size_t budget) {
    budget = std::min(budget, points.size());
    std::vector<std::size_t> selected;
    selected.reserve(budget);
    if (budget == 0U) return selected;
    if (budget == points.size()) {
        selected.resize(points.size());
        for (std::size_t i = 0U; i < points.size(); ++i) selected[i] = i;
        return selected;
    }

    std::vector<std::size_t> priority;
    std::vector<std::size_t> ordinary;
    priority.reserve(points.size() / 4U + 1U);
    ordinary.reserve(points.size());
    for (std::size_t i = 0U; i < points.size(); ++i) {
        if (points[i].flags != 0U) priority.push_back(i);
        else ordinary.push_back(i);
    }

    const auto append_even = [&](const std::vector<std::size_t>& source, std::size_t count) {
        if (source.empty() || count == 0U) return;
        count = std::min(count, source.size());
        for (std::size_t slot = 0U; slot < count; ++slot) {
            const std::size_t index = std::min(source.size() - 1U,
                static_cast<std::size_t>((static_cast<unsigned long long>(slot) * source.size()) / count));
            selected.push_back(source[index]);
        }
    };

    std::size_t reserve = 0U;
    if (streaming.preserve_semantic_points && !priority.empty()) {
        reserve = static_cast<std::size_t>(std::ceil(static_cast<double>(budget) *
            static_cast<double>(std::clamp(streaming.semantic_reserve_ratio, 0.0F, 1.0F))));
        reserve = std::min({reserve, priority.size(), budget});
    }
    append_even(priority, reserve);
    append_even(ordinary, budget - selected.size());
    if (selected.size() < budget) append_even(priority, budget - selected.size());

    std::sort(selected.begin(), selected.end());
    selected.erase(std::unique(selected.begin(), selected.end()), selected.end());
    if (selected.size() < budget) {
        std::size_t cursor = 0U;
        while (selected.size() < budget && cursor < points.size()) {
            if (!std::binary_search(selected.begin(), selected.end(), cursor)) {
                selected.insert(std::lower_bound(selected.begin(), selected.end(), cursor), cursor);
            }
            ++cursor;
        }
    }
    if (selected.size() > budget) selected.resize(budget);
    return selected;
}

void RuntimeInteractionState::reset() {
    assets_.clear();
    triggers_.clear();
    events_.clear();
}

void RuntimeInteractionState::begin_zone(std::string_view zone, std::string_view reset_policy) {
    if (zone_ == zone) return;
    if (!zone_.empty() && reset_policy == "zone_exit") reset();
    zone_ = std::string(zone);
}

RuntimeAssetState& RuntimeInteractionState::asset(std::string_view asset_id) {
    return assets_[std::string(asset_id)];
}

RuntimeTriggerMemory& RuntimeInteractionState::trigger(std::string_view asset_id, std::size_t trigger_index) {
    return triggers_[std::string(asset_id) + "#" + std::to_string(trigger_index)];
}

void RuntimeInteractionState::push_event(RuntimeInteractionEvent event, std::size_t limit) {
    const std::size_t safe_limit = std::max<std::size_t>(1U, limit);
    events_.push_back(std::move(event));
    while (events_.size() > safe_limit) events_.pop_front();
}

std::vector<RuntimeInteractionEvent> RuntimeInteractionState::take_events() {
    std::vector<RuntimeInteractionEvent> result;
    result.reserve(events_.size());
    while (!events_.empty()) {
        result.push_back(std::move(events_.front()));
        events_.pop_front();
    }
    return result;
}

void RuntimeInteractionState::prune(double now, std::size_t max_states, std::size_t max_proxies) {
    const std::size_t state_limit = std::max<std::size_t>(16U, max_states);
    while (triggers_.size() > state_limit) triggers_.erase(triggers_.begin());
    while (assets_.size() > state_limit) assets_.erase(assets_.begin());
    for (auto& [asset_id, value] : assets_) {
        (void)asset_id;
        value.proxies.erase(std::remove_if(value.proxies.begin(), value.proxies.end(),
                                          [now](const RuntimeProxyState& proxy) { return proxy.expires_at <= now; }),
                            value.proxies.end());
        if (value.proxies.size() > max_proxies) {
            value.proxies.erase(value.proxies.begin(),
                                value.proxies.begin() + static_cast<std::ptrdiff_t>(value.proxies.size() - max_proxies));
        }
    }
}

void RuntimeEncounterState::reset() {
    assets_.clear();
    events_.clear();
}

void RuntimeEncounterState::begin_zone(std::string_view zone, std::string_view reset_policy) {
    if (zone_ == zone) return;
    if (!zone_.empty() && reset_policy == "zone_exit") reset();
    zone_ = std::string(zone);
}

RuntimeEncounterAssetState& RuntimeEncounterState::asset(std::string_view asset_id) {
    return assets_[std::string(asset_id)];
}

void RuntimeEncounterState::push_event(RuntimeEncounterEvent event, std::size_t limit) {
    const std::size_t safe_limit = std::max<std::size_t>(16U, limit);
    events_.push_back(std::move(event));
    while (events_.size() > safe_limit) events_.pop_front();
}

std::vector<RuntimeEncounterEvent> RuntimeEncounterState::take_events() {
    std::vector<RuntimeEncounterEvent> result;
    result.reserve(events_.size());
    while (!events_.empty()) {
        result.push_back(std::move(events_.front()));
        events_.pop_front();
    }
    return result;
}

void RuntimeEncounterState::prune(double now, std::size_t max_assets, std::size_t max_instances) {
    const std::size_t asset_limit = std::max<std::size_t>(1U, max_assets);
    while (assets_.size() > asset_limit) assets_.erase(assets_.begin());
    for (auto& [asset_id, state] : assets_) {
        (void)asset_id;
        state.instances.erase(std::remove_if(state.instances.begin(), state.instances.end(),
            [now](const RuntimeEncounterInstance& instance) {
                return !instance.friendly && instance.expires_at <= now;
            }), state.instances.end());
        if (state.instances.size() > max_instances) {
            state.instances.erase(state.instances.begin(), state.instances.begin() +
                static_cast<std::ptrdiff_t>(state.instances.size() - max_instances));
        }
    }
}

std::vector<render::PointGpu> Asset::render_points(math::Vec3 offset, float scale) const {
    std::vector<render::PointGpu> points;
    points.reserve(layered_points.size());
    const float safe_scale = std::isfinite(scale) && std::abs(scale) > 0.0001F ? scale : 1.0F;
    for (const auto& source : layered_points) {
        auto point = source.point;
        point.position[0] = point.position[0] * safe_scale + offset.x;
        point.position[1] = point.position[1] * safe_scale + offset.y;
        point.position[2] = point.position[2] * safe_scale + offset.z;
        point.radius = std::max(0.1F, point.radius * std::abs(safe_scale));
        points.push_back(point);
    }
    return points;
}

bool Asset::finite() const noexcept {
    return std::all_of(layered_points.begin(), layered_points.end(), finite_point);
}

bool load_cloud(const std::filesystem::path& path, Asset& asset, std::string* error) {
    try {
        std::ifstream input(path, std::ios::binary);
        if (!input) throw std::runtime_error("Unable to open PCP3 cloud: " + path.string());
        CloudHeader header{};
        input.read(reinterpret_cast<char*>(&header), sizeof(header));
        if (input.gcount() != static_cast<std::streamsize>(sizeof(header))) {
            throw std::runtime_error("PCP3 cloud header is incomplete.");
        }
        if (std::memcmp(header.magic, "PCP3CLD1", 8) != 0) {
            throw std::runtime_error("PCP3 cloud magic does not match PCP3CLD1.");
        }
        if (header.version != 1U || header.record_size != sizeof(CloudRecord)) {
            throw std::runtime_error("Unsupported PCP3 cloud version or record size.");
        }
        constexpr std::uint64_t hard_limit = 250'000'000ULL;
        if (header.point_count > hard_limit) {
            throw std::runtime_error("PCP3 cloud exceeds the current PCP3 safety limit.");
        }
        asset.layered_points.clear();
        asset.layered_points.reserve(static_cast<std::size_t>(header.point_count));
        Sha256 payload_hash;
        asset.bounds_min = {std::numeric_limits<float>::max(), std::numeric_limits<float>::max(), std::numeric_limits<float>::max()};
        asset.bounds_max = {std::numeric_limits<float>::lowest(), std::numeric_limits<float>::lowest(), std::numeric_limits<float>::lowest()};
        for (std::uint64_t index = 0; index < header.point_count; ++index) {
            CloudRecord record{};
            input.read(reinterpret_cast<char*>(&record), sizeof(record));
            if (!input) throw std::runtime_error("PCP3 cloud payload ended early.");
            payload_hash.update(reinterpret_cast<const std::uint8_t*>(&record), sizeof(record));
            LayeredPoint point;
            point.point.position[0] = record.x;
            point.point.position[1] = record.y;
            point.point.position[2] = record.z;
            point.point.radius = record.radius;
            point.point.color[0] = record.r;
            point.point.color[1] = record.g;
            point.point.color[2] = record.b;
            point.point.color[3] = record.a;
            point.point.normal[0] = record.nx;
            point.point.normal[1] = record.ny;
            point.point.normal[2] = record.nz;
            point.point.density = record.density;
            point.layer_id = record.layer_id;
            point.flags = record.flags;
            point.attribute0 = record.attribute0;
            point.attribute1 = record.attribute1;
            if (!finite_point(point)) continue;
            asset.layered_points.push_back(point);
            asset.bounds_min.x = std::min(asset.bounds_min.x, record.x);
            asset.bounds_min.y = std::min(asset.bounds_min.y, record.y);
            asset.bounds_min.z = std::min(asset.bounds_min.z, record.z);
            asset.bounds_max.x = std::max(asset.bounds_max.x, record.x);
            asset.bounds_max.y = std::max(asset.bounds_max.y, record.y);
            asset.bounds_max.z = std::max(asset.bounds_max.z, record.z);
        }
        if (checksum_is_present(header.payload_sha256) && payload_hash.finish() != header.payload_sha256) {
            throw std::runtime_error("PCP3 cloud payload checksum failed validation.");
        }
        if (asset.layered_points.empty()) {
            asset.bounds_min = {};
            asset.bounds_max = {};
        }
        asset.metadata.cloud_path = path;
        return true;
    } catch (const std::exception& exception) {
        if (error) *error = exception.what();
        return false;
    }
}

bool load_asset(const std::filesystem::path& udata_path, Asset& asset, std::string* error) {
    try {
        const auto document = data::UDataDocument::load(udata_path);
        asset.metadata.udata_path = udata_path;
        asset.metadata.asset_id = string_value(document, "header", "asset_id", udata_path.stem().string());
        asset.metadata.display_name = string_value(document, "header", "display_name", asset.metadata.asset_id);
        asset.metadata.environment_type = string_value(document, "header", "asset_kind", "environment_object");
        asset.metadata.project_id = string_value(document, "header", "project_id", "");
        asset.metadata.enabled = bool_value(document, "runtime", "enabled", true);
        asset.metadata.auto_preview_in_game = bool_value(document, "runtime", "auto_preview_in_game", false);
        asset.metadata.preview_zone = string_value(document, "runtime", "preview_zone", "Reception Tape");
        asset.metadata.preview_position = vec3_value(document, "runtime", "preview_position", {2.0F, 1.0F, -3.0F});
        asset.metadata.preview_scale = float_value(document, "runtime", "preview_scale", 1.0F);
        const std::string cloud_name = string_value(document, "body", "cloud_file", asset.metadata.asset_id + ".pcp3cloud");
        const auto cloud_path = udata_path.parent_path() / cloud_name;
        if (!load_cloud(cloud_path, asset, error)) return false;
        const std::string factory_name = string_value(document, "runtime_factory", "udata_sidecar_file", "");
        if (!factory_name.empty()) {
            const auto factory_path = udata_path.parent_path() / factory_name;
            if (std::filesystem::exists(factory_path)) {
                std::string factory_error;
                if (!load_runtime_factory(factory_path, asset.runtime_factory, &factory_error) && error != nullptr) {
                    *error = "Runtime Factory disabled after parse failure: " + factory_error;
                }
            }
        }
        const std::string entity_name = string_value(document, "runtime_entity", "udata_sidecar_file", "");
        if (!entity_name.empty()) {
            const auto entity_path = udata_path.parent_path() / entity_name;
            if (std::filesystem::exists(entity_path)) {
                std::string entity_error;
                if (!load_runtime_entity(entity_path, asset.runtime_entity, &entity_error) && error != nullptr) {
                    *error = "Runtime Entity disabled after parse failure: " + entity_error;
                }
            }
        }
        const std::string interaction_name = string_value(document, "runtime_interaction", "udata_sidecar_file", "");
        if (!interaction_name.empty()) {
            const auto interaction_path = udata_path.parent_path() / interaction_name;
            if (std::filesystem::exists(interaction_path)) {
                std::string interaction_error;
                if (!load_runtime_interaction(interaction_path, asset.runtime_interaction, &interaction_error) && error != nullptr) {
                    *error = "Runtime Interaction disabled after parse failure: " + interaction_error;
                }
            }
        }
        const std::string world_name = string_value(document, "runtime_world", "udata_sidecar_file", "");
        if (!world_name.empty()) {
            const auto world_path = udata_path.parent_path() / world_name;
            if (std::filesystem::exists(world_path)) {
                std::string world_error;
                if (!load_runtime_world(world_path, asset.runtime_world, &world_error) && error != nullptr) {
                    *error = "Runtime World disabled after parse failure: " + world_error;
                }
            }
        }
        const std::string encounter_name = string_value(document, "runtime_encounter", "udata_sidecar_file", "");
        if (!encounter_name.empty()) {
            const auto encounter_path = udata_path.parent_path() / encounter_name;
            if (std::filesystem::exists(encounter_path)) {
                std::string encounter_error;
                if (!load_runtime_encounter(encounter_path, asset.runtime_encounter, &encounter_error) && error != nullptr) {
                    *error = "Runtime Encounter disabled after parse failure: " + encounter_error;
                }
            }
        }
        const std::string streaming_name = string_value(document, "runtime_streaming", "udata_sidecar_file", "");
        if (!streaming_name.empty()) {
            const auto streaming_path = udata_path.parent_path() / streaming_name;
            if (std::filesystem::exists(streaming_path)) {
                std::string streaming_error;
                if (!load_runtime_streaming(streaming_path, asset.runtime_streaming, &streaming_error) && error != nullptr) {
                    *error = "Runtime Streaming disabled after parse failure: " + streaming_error;
                }
            }
        }
        return true;
    } catch (const std::exception& exception) {
        if (error) *error = exception.what();
        return false;
    }
}

std::vector<Asset> discover_assets(const std::filesystem::path& project_root,
                                   std::vector<std::string>* warnings) {
    std::vector<Asset> assets;
    const auto root = project_root / "content" / "pcp3_assets";
    if (!std::filesystem::is_directory(root)) return assets;
    std::error_code error;
    for (const auto& entry : std::filesystem::recursive_directory_iterator(root, error)) {
        if (error) break;
        if (!entry.is_regular_file() || entry.path().extension() != ".udata") continue;
        const std::string filename = entry.path().filename().string();
        // Content ABI envelopes describe assets for validation and packaging; they are not
        // PCP3 runtime sidecars and must never be interpreted as point-cloud metadata.
        if (filename.ends_with(".asset.udata") || filename.ends_with(".pcp3factory.udata") ||
            filename.ends_with(".pcp3interaction.udata") || filename.ends_with(".pcp3entity.udata") ||
            filename.ends_with(".pcp3world.udata") || filename.ends_with(".pcp3encounter.udata") ||
            filename.ends_with(".pcp3stream.udata")) continue;
        Asset asset;
        std::string load_error;
        if (load_asset(entry.path(), asset, &load_error)) {
            if (asset.metadata.enabled) assets.push_back(std::move(asset));
        } else if (warnings) {
            warnings->push_back(entry.path().string() + ": " + load_error);
        }
    }
    std::sort(assets.begin(), assets.end(), [](const Asset& a, const Asset& b) {
        return a.metadata.asset_id < b.metadata.asset_id;
    });
    return assets;
}

std::vector<render::PointGpu> points_for_zone(const std::vector<Asset>& assets,
                                               std::string_view zone,
                                               PreviewPurpose purpose,
                                               RuntimeContext context,
                                               std::size_t point_limit) {
    std::vector<render::PointGpu> points;
    const std::size_t safe_limit = std::max<std::size_t>(1U, point_limit);
    const auto find_asset = [&](std::string_view asset_id) -> const Asset* {
        const auto match = std::find_if(assets.begin(), assets.end(), [&](const Asset& candidate) {
            return candidate.metadata.asset_id == asset_id;
        });
        return match == assets.end() ? nullptr : &*match;
    };

    std::size_t interaction_state_cap = 16U;
    std::size_t interaction_proxy_cap = 1U;
    if (context.interaction_state != nullptr) {
        bool reset_on_zone_exit = false;
        for (const auto& asset : assets) {
            const bool target = interaction_target_enabled(asset.runtime_interaction, purpose);
            if (!asset.runtime_interaction.present || !asset.runtime_interaction.enabled || !target) continue;
            reset_on_zone_exit = reset_on_zone_exit || asset.runtime_interaction.reset_policy == "zone_exit";
            interaction_state_cap = std::max(interaction_state_cap, asset.runtime_interaction.max_state_entries);
            interaction_proxy_cap = std::max(interaction_proxy_cap, asset.runtime_interaction.max_active_proxies);
        }
        context.interaction_state->begin_zone(zone, reset_on_zone_exit ? "zone_exit" : "session");
    }

    std::size_t encounter_asset_cap = 16U;
    std::size_t encounter_instance_cap = 16U;
    if (context.encounter_state != nullptr) {
        bool reset_on_zone_exit = false;
        for (const auto& asset : assets) {
            const bool target = encounter_target_enabled(asset.runtime_encounter, purpose);
            if (!asset.runtime_encounter.present || !asset.runtime_encounter.enabled || !target) continue;
            reset_on_zone_exit = reset_on_zone_exit || asset.runtime_encounter.reset_policy == "zone_exit";
            encounter_asset_cap = std::max<std::size_t>(encounter_asset_cap, 64U);
            encounter_instance_cap = std::max(encounter_instance_cap, asset.runtime_encounter.max_active_entities + asset.runtime_encounter.max_friendlies);
        }
        context.encounter_state->begin_zone(zone, reset_on_zone_exit ? "zone_exit" : "session");
    }

    for (const auto& asset : assets) {
        if (!asset.metadata.enabled) continue;
        const bool factory_present = asset.runtime_factory.present && asset.runtime_factory.enabled;
        const bool factory_target = purpose == PreviewPurpose::game
            ? asset.runtime_factory.game_enabled
            : asset.runtime_factory.stress_enabled;
        const bool factory_active = factory_present && factory_target;
        const bool entity_present = asset.runtime_entity.present && asset.runtime_entity.enabled;
        const bool entity_active = entity_present && entity_target_enabled(asset.runtime_entity, purpose);
        const bool world_present = asset.runtime_world.present && asset.runtime_world.enabled;
        const bool world_active = world_present && world_target_enabled(asset.runtime_world, purpose);
        const bool world_zone_match = world_active && (asset.runtime_world.host_zone == zone || asset.metadata.preview_zone == zone);
        const bool encounter_present = asset.runtime_encounter.present && asset.runtime_encounter.enabled;
        const bool encounter_active = encounter_present && encounter_target_enabled(asset.runtime_encounter, purpose);
        const bool encounter_zone_match = encounter_active && (asset.runtime_encounter.host_zone == zone || asset.metadata.preview_zone == zone);
        const bool streaming_active = asset.runtime_streaming.present && asset.runtime_streaming.enabled &&
            (purpose == PreviewPurpose::game ? asset.runtime_streaming.game_enabled : asset.runtime_streaming.stress_enabled);
        const bool metadata_zone_match = asset.metadata.preview_zone == zone;
        if (!metadata_zone_match && !world_zone_match && !encounter_zone_match) continue;
        if (purpose == PreviewPurpose::game && !asset.metadata.auto_preview_in_game && !factory_active && !entity_active && !world_zone_match && !encounter_zone_match) continue;
        if (world_active && !world_zone_match && !factory_active && !entity_active && !encounter_zone_match) continue;
        if (encounter_active && !encounter_zone_match && !factory_active && !entity_active && !world_zone_match) continue;

        RuntimeKeyframe root_sample;
        if (factory_active) root_sample = sample_factory(asset.runtime_factory, context.time_seconds);
        const math::Vec3 root_scale{
            asset.metadata.preview_scale * root_sample.scale.x,
            asset.metadata.preview_scale * root_sample.scale.y,
            asset.metadata.preview_scale * root_sample.scale.z,
        };
        const math::Vec3 base_origin = asset.metadata.preview_position + root_sample.position;
        RuntimeEntitySample entity_sample;
        if (entity_active) entity_sample = sample_entity_runtime(asset.runtime_entity, base_origin, context);
        const math::Vec3 root_offset = base_origin + entity_sample.movement_offset;
        const math::Vec3 root_rotation = root_sample.rotation_degrees + entity_sample.facing_rotation;

        RuntimeEncounterAssetState* encounter_asset_state = nullptr;
        if (encounter_zone_match) {
            encounter_asset_state = update_encounter_runtime(asset, purpose, context, root_offset);
        }

        const bool interaction_active = factory_active && asset.runtime_interaction.present &&
            asset.runtime_interaction.enabled && interaction_target_enabled(asset.runtime_interaction, purpose) &&
            context.interaction_state != nullptr;
        RuntimeAssetState* interaction_asset_state = nullptr;
        if (interaction_active) {
            evaluate_asset_interactions(asset, purpose, context, root_offset, root_scale, root_rotation);
            interaction_asset_state = &context.interaction_state->asset(asset.metadata.asset_id);
        }
        const bool revealed = interaction_asset_state != nullptr && interaction_asset_state->revealed;
        if (factory_active && asset.runtime_factory.scanner_required && !context.scanner_active && !revealed) continue;
        if (factory_active && asset.runtime_factory.proximity_required && !revealed &&
            math::length(context.viewer_position - asset.metadata.preview_position) > asset.runtime_factory.proximity_radius) continue;
        if (interaction_asset_state != nullptr && !interaction_asset_state->visible) continue;

        std::vector<std::size_t> streamed_indices;
        if (streaming_active) {
            const float stream_distance = math::length(context.viewer_position - root_offset);
            std::size_t stream_budget = streaming_point_budget(
                asset.runtime_streaming, asset.layered_points.size(), stream_distance);
            stream_budget = std::min(stream_budget, safe_limit - points.size());
            streamed_indices = streaming_sample_indices(asset.layered_points, asset.runtime_streaming, stream_budget);
        }

        std::vector<render::PointGpu> base_points;
        base_points.reserve(streaming_active ? streamed_indices.size() : asset.layered_points.size());
        std::size_t entity_deformed = 0U;
        const auto append_source = [&](const LayeredPoint& source) {
            const bool weighted = static_cast<int>(std::lround(source.attribute1)) == 41 ||
                (static_cast<int>(std::lround(source.attribute1)) >= 1000 && static_cast<int>(std::lround(source.attribute1)) < 1064);
            const RuntimeEntity* deform_entity = entity_active && (!weighted || entity_deformed < asset.runtime_entity.max_deformed_points)
                ? &asset.runtime_entity : nullptr;
            if (weighted && deform_entity != nullptr) ++entity_deformed;
            base_points.push_back(transformed_point(
                source, root_offset, root_scale, root_rotation,
                factory_active ? &asset.runtime_factory : nullptr,
                world_active ? &asset.runtime_world : nullptr,
                interaction_asset_state, context.time_seconds,
                deform_entity, entity_sample.state));
        };
        if (streaming_active) {
            for (const std::size_t index : streamed_indices) append_source(asset.layered_points[index]);
        } else {
            for (const auto& source : asset.layered_points) append_source(source);
        }
        append_sampled(points, base_points, safe_limit);
        if (points.size() >= safe_limit) break;

        if (factory_active) {
            std::size_t nested_used = 0U;
            for (const auto& placement : asset.runtime_factory.placements) {
                if (!placement.enabled || nested_used >= asset.runtime_factory.max_nested_points || points.size() >= safe_limit) break;
                const Asset* nested = find_asset(placement.asset_id);
                if (nested == nullptr || nested == &asset || !nested->metadata.enabled) continue;
                const math::Vec3 local_position{
                    placement.position.x * root_scale.x,
                    placement.position.y * root_scale.y,
                    placement.position.z * root_scale.z,
                };
                const math::Vec3 nested_offset = root_offset + rotate_xyz(local_position, root_rotation);
                const math::Vec3 nested_scale{
                    root_scale.x * placement.scale,
                    root_scale.y * placement.scale,
                    root_scale.z * placement.scale,
                };
                const math::Vec3 nested_rotation = root_rotation + placement.rotation_degrees;
                const std::size_t nested_cap = std::min({asset.runtime_factory.max_nested_points - nested_used,
                                                         safe_limit - points.size(), nested->layered_points.size()});
                if (nested_cap == 0U) continue;
                const std::size_t stride = std::max<std::size_t>(1U, nested->layered_points.size() / nested_cap);
                for (std::size_t index = 0U; index < nested->layered_points.size() && nested_used < asset.runtime_factory.max_nested_points && points.size() < safe_limit; index += stride) {
                    points.push_back(transformed_point(nested->layered_points[index], nested_offset, nested_scale, nested_rotation, nullptr, nullptr));
                    ++nested_used;
                }
            }

            if (context.debug_evidence || context.scanner_active || purpose == PreviewPurpose::stress) {
                for (const auto& trigger : asset.runtime_factory.triggers) {
                    if (points.size() >= safe_limit) break;
                    const math::Vec3 center = transformed_trigger_center(trigger, root_offset, root_scale, root_rotation);
                    append_ring(points, center, trigger.radius * std::max(0.25F, asset.metadata.preview_scale),
                                trigger.approved ? 0.95F : 0.7F, trigger.approved ? 0.45F : 0.7F, 0.2F, safe_limit);
                }
                for (const auto& node : asset.runtime_factory.flow_nodes) {
                    if (points.size() >= safe_limit) break;
                    const math::Vec3 local{
                        node.position.x * root_scale.x,
                        node.position.y * root_scale.y,
                        node.position.z * root_scale.z,
                    };
                    const math::Vec3 start = root_offset + rotate_xyz(local, root_rotation);
                    const math::Vec3 direction = rotate_xyz(node.direction, root_rotation);
                    const float length = std::clamp(std::abs(node.strength) * (1.0F + 0.25F * node.viscosity), 0.5F, 16.0F);
                    append_line(points, start, start + direction * length, 0.2F, 0.75F, 1.0F, safe_limit);
                }
            }
        }


        if (world_active) {
            std::size_t nested_used = 0U;
            for (const auto& placement : asset.runtime_world.placements) {
                if (!placement.enabled || nested_used >= 500'000U || points.size() >= safe_limit) break;
                const Asset* nested = find_asset(placement.asset_id);
                if (nested == nullptr || nested == &asset || !nested->metadata.enabled) continue;
                const math::Vec3 local_position{
                    placement.position.x * root_scale.x,
                    placement.position.y * root_scale.y,
                    placement.position.z * root_scale.z,
                };
                const math::Vec3 nested_offset = root_offset + rotate_xyz(local_position, root_rotation);
                const math::Vec3 nested_scale{root_scale.x * placement.scale, root_scale.y * placement.scale, root_scale.z * placement.scale};
                const math::Vec3 nested_rotation = root_rotation + placement.rotation_degrees;
                const std::size_t nested_cap = std::min({std::size_t{500'000U} - nested_used,
                                                         safe_limit - points.size(), nested->layered_points.size()});
                if (nested_cap == 0U) continue;
                const std::size_t stride = std::max<std::size_t>(1U, nested->layered_points.size() / nested_cap);
                for (std::size_t index = 0U; index < nested->layered_points.size() && nested_used < 500'000U && points.size() < safe_limit; index += stride) {
                    points.push_back(transformed_point(nested->layered_points[index], nested_offset, nested_scale, nested_rotation, nullptr, nullptr));
                    ++nested_used;
                }
            }
            if (context.debug_evidence || context.scanner_active || purpose == PreviewPurpose::stress) {
                if (asset.runtime_world.show_bounds_debug && points.size() < safe_limit) {
                    const math::Vec3 local_center = (asset.bounds_min + asset.bounds_max) * 0.5F;
                    const math::Vec3 local_size = asset.bounds_max - asset.bounds_min;
                    append_box(points, root_offset + rotate_xyz({local_center.x * root_scale.x, local_center.y * root_scale.y, local_center.z * root_scale.z}, root_rotation),
                               {std::abs(local_size.x * root_scale.x), std::abs(local_size.y * root_scale.y), std::abs(local_size.z * root_scale.z)},
                               0.35F, 0.9F, 0.45F, safe_limit);
                }
                if (asset.runtime_world.show_portal_debug) {
                    for (const auto& portal : asset.runtime_world.portals) {
                        if (!portal.enabled || points.size() >= safe_limit) continue;
                        const math::Vec3 local{portal.position.x * root_scale.x, portal.position.y * root_scale.y, portal.position.z * root_scale.z};
                        append_box(points, root_offset + rotate_xyz(local, root_rotation),
                                   {portal.size.x * std::abs(root_scale.x), portal.size.y * std::abs(root_scale.y), portal.size.z * std::abs(root_scale.z)},
                                   portal.destination_asset_id.empty() ? 1.0F : 0.2F,
                                   portal.destination_asset_id.empty() ? 0.35F : 0.95F, 0.85F, safe_limit);
                    }
                }
                for (const auto& node : asset.runtime_world.flow_nodes) {
                    if (points.size() >= safe_limit) break;
                    const math::Vec3 local{node.position.x * root_scale.x, node.position.y * root_scale.y, node.position.z * root_scale.z};
                    const math::Vec3 start = root_offset + rotate_xyz(local, root_rotation);
                    const math::Vec3 direction = rotate_xyz(node.direction, root_rotation);
                    const float length = std::clamp(std::abs(node.strength) * asset.runtime_world.liquid.flow_scale * (1.0F + 0.1F * node.viscosity), 0.4F, 20.0F);
                    append_line(points, start, start + direction * length, 0.15F, 0.65F, 1.0F, safe_limit);
                }
            }
        }

        if (encounter_zone_match && encounter_asset_state != nullptr) {
            const auto append_reference = [&](std::string_view asset_id, math::Vec3 offset,
                                              math::Vec3 rotation, float scale) {
                if (points.size() >= safe_limit) return;
                const Asset* referenced = find_asset(asset_id);
                if (referenced == nullptr || referenced == &asset || !referenced->metadata.enabled) return;
                const bool nested_entity_active = referenced->runtime_entity.present && referenced->runtime_entity.enabled &&
                    entity_target_enabled(referenced->runtime_entity, purpose);
                RuntimeEntitySample nested_sample;
                if (nested_entity_active) nested_sample = sample_entity_runtime(referenced->runtime_entity, offset, context);
                const math::Vec3 nested_offset = offset + nested_sample.movement_offset;
                const math::Vec3 nested_rotation = rotation + nested_sample.facing_rotation;
                const math::Vec3 nested_scale{scale, scale, scale};
                const std::size_t remaining = safe_limit - points.size();
                const std::size_t cap = std::min<std::size_t>(remaining, 100'000U);
                const std::size_t stride = std::max<std::size_t>(1U, referenced->layered_points.size() / std::max<std::size_t>(1U, cap));
                std::size_t used = 0U;
                for (std::size_t index = 0U; index < referenced->layered_points.size() && used < cap && points.size() < safe_limit; index += stride) {
                    const auto& source = referenced->layered_points[index];
                    points.push_back(transformed_point(
                        source, nested_offset, nested_scale, nested_rotation,
                        nullptr, nullptr, nullptr, context.time_seconds,
                        nested_entity_active ? &referenced->runtime_entity : nullptr,
                        nested_sample.state));
                    ++used;
                }
            };

            for (const auto& friendly : asset.runtime_encounter.friendlies) {
                if (!friendly.enabled || friendly.asset_id.empty() || points.size() >= safe_limit) continue;
                const math::Vec3 local{friendly.position.x * root_scale.x, friendly.position.y * root_scale.y, friendly.position.z * root_scale.z};
                append_reference(friendly.asset_id, root_offset + rotate_xyz(local, root_rotation),
                                 root_rotation + friendly.rotation_degrees,
                                 std::max(0.001F, friendly.scale * asset.metadata.preview_scale));
            }
            for (const auto& instance : encounter_asset_state->instances) {
                if (instance.friendly || points.size() >= safe_limit) continue;
                append_reference(instance.asset_id, instance.position, instance.rotation_degrees,
                                 std::max(0.001F, instance.scale));
            }

            if (asset.runtime_encounter.show_debug &&
                (context.debug_evidence || context.scanner_active || purpose == PreviewPurpose::stress)) {
                const math::Vec3 center = root_offset + asset.runtime_encounter.start_position;
                append_ring(points, center, asset.runtime_encounter.start_radius, 0.95F, 0.35F, 0.95F, safe_limit);
                if (encounter_asset_state->started && !encounter_asset_state->completed) {
                    const float wave_radius = 0.8F + 0.25F * static_cast<float>(encounter_asset_state->next_wave);
                    append_ring(points, center + math::Vec3{0.0F, 0.15F, 0.0F}, wave_radius, 1.0F, 0.45F, 0.15F, safe_limit);
                }
                if (!asset.runtime_encounter.boss_phases.empty() && encounter_asset_state->started) {
                    double estimated = 0.0;
                    for (const auto& wave : asset.runtime_encounter.waves) {
                        estimated += wave.delay + wave.active_seconds + asset.runtime_encounter.inter_wave_delay;
                    }
                    const float progress = estimated <= 0.001 ? 1.0F : std::clamp(
                        static_cast<float>((context.time_seconds - encounter_asset_state->started_at) / estimated), 0.0F, 1.0F);
                    const RuntimeBossPhase* phase = nullptr;
                    for (const auto& candidate : asset.runtime_encounter.boss_phases) {
                        if (candidate.progress_threshold <= progress) phase = &candidate;
                    }
                    if (phase != nullptr) {
                        append_ring(points, center + math::Vec3{0.0F, 0.35F, 0.0F}, 1.25F,
                                    0.75F, 0.2F, 1.0F, safe_limit);
                    }
                }
                if (encounter_asset_state->completed) {
                    append_ring(points, center, 1.6F, 0.25F, 1.0F, 0.45F, safe_limit);
                }
            }
        }

        if (entity_active && (context.debug_evidence || context.scanner_active || purpose == PreviewPurpose::stress)) {
            const auto transform_entity_position = [&](math::Vec3 local) {
                local = {local.x * root_scale.x, local.y * root_scale.y, local.z * root_scale.z};
                return root_offset + rotate_xyz(local, root_rotation);
            };
            if (asset.runtime_entity.show_rig_debug) {
                for (const auto& bone : asset.runtime_entity.bones) {
                    if (points.size() >= safe_limit) break;
                    append_line(points, transform_entity_position(bone.start), transform_entity_position(bone.end),
                                0.25F, 0.65F, 1.0F, safe_limit);
                }
            }
            if (asset.runtime_entity.show_anchor_debug) {
                for (const auto& anchor : asset.runtime_entity.anchors) {
                    if (points.size() >= safe_limit) break;
                    const math::Vec3 center = transform_entity_position(anchor.position);
                    const float size = anchor.role == "attack" ? 0.55F : 0.4F;
                    const float r = anchor.role == "attack" ? 1.0F : 0.35F;
                    const float g = anchor.role == "effect" ? 0.9F : 0.35F;
                    append_line(points, center - math::Vec3{size, 0.0F, 0.0F}, center + math::Vec3{size, 0.0F, 0.0F}, r, g, 0.8F, safe_limit);
                    append_line(points, center - math::Vec3{0.0F, size, 0.0F}, center + math::Vec3{0.0F, size, 0.0F}, r, g, 0.8F, safe_limit);
                    append_line(points, center - math::Vec3{0.0F, 0.0F, size}, center + math::Vec3{0.0F, 0.0F, size}, r, g, 0.8F, safe_limit);
                }
            }
            if (asset.runtime_entity.show_state_debug && points.size() < safe_limit) {
                float r = 0.35F, g = 0.8F, b = 0.45F;
                if (entity_sample.state == "move") { r = 0.25F; g = 0.65F; b = 1.0F; }
                else if (entity_sample.state == "alert") { r = 1.0F; g = 0.65F; b = 0.15F; }
                else if (entity_sample.state == "attack") { r = 1.0F; g = 0.2F; b = 0.15F; }
                append_ring(points, root_offset, std::max(0.45F, asset.runtime_entity.attack_radius * 0.2F), r, g, b, safe_limit);
            }
        }

        if (interaction_asset_state != nullptr && asset.runtime_interaction.show_runtime_evidence) {
            if (context.time_seconds < interaction_asset_state->alert_until && points.size() < safe_limit) {
                const float pulse_radius = 1.5F + 0.35F * std::sin(static_cast<float>(context.time_seconds) * 9.0F);
                append_ring(points, root_offset, std::max(0.5F, pulse_radius), 1.0F, 0.35F, 0.12F, safe_limit);
            }
            for (const auto& proxy : interaction_asset_state->proxies) {
                if (proxy.expires_at <= context.time_seconds || points.size() >= safe_limit) continue;
                const float size = 0.75F;
                append_line(points, proxy.position - math::Vec3{size, 0.0F, 0.0F}, proxy.position + math::Vec3{size, 0.0F, 0.0F}, 0.9F, 0.2F, 1.0F, safe_limit);
                append_line(points, proxy.position - math::Vec3{0.0F, size, 0.0F}, proxy.position + math::Vec3{0.0F, size, 0.0F}, 0.9F, 0.2F, 1.0F, safe_limit);
                append_line(points, proxy.position - math::Vec3{0.0F, 0.0F, size}, proxy.position + math::Vec3{0.0F, 0.0F, size}, 0.9F, 0.2F, 1.0F, safe_limit);
            }
        }
        if (points.size() >= safe_limit) break;
    }
    if (context.interaction_state != nullptr) {
        context.interaction_state->prune(context.time_seconds, interaction_state_cap, interaction_proxy_cap);
    }
    if (context.encounter_state != nullptr) {
        context.encounter_state->prune(context.time_seconds, encounter_asset_cap, encounter_instance_cap);
    }
    return points;
}

std::optional<WorldPortalTransfer> world_portal_transfer(
    const std::vector<Asset>& assets, std::string_view zone, PreviewPurpose purpose,
    math::Vec3 viewer_position, bool interaction_pressed) {
    const auto find_asset = [&](std::string_view asset_id) -> const Asset* {
        const auto match = std::find_if(assets.begin(), assets.end(), [&](const Asset& candidate) {
            return candidate.metadata.asset_id == asset_id;
        });
        return match == assets.end() ? nullptr : &*match;
    };
    for (const auto& asset : assets) {
        const auto& world = asset.runtime_world;
        if (!asset.metadata.enabled || !world.present || !world.enabled || !world_target_enabled(world, purpose)) continue;
        if (!world.execute_portals || (world.host_zone != zone && asset.metadata.preview_zone != zone)) continue;
        const float scale = std::max(0.001F, std::abs(asset.metadata.preview_scale));
        for (const auto& portal : world.portals) {
            if (!portal.enabled || portal.destination_asset_id.empty()) continue;
            const math::Vec3 center = asset.metadata.preview_position + portal.position * scale;
            const math::Vec3 half{portal.size.x * scale * 0.5F, portal.size.y * scale * 0.5F, portal.size.z * scale * 0.5F};
            const math::Vec3 delta = viewer_position - center;
            if (std::abs(delta.x) > half.x || std::abs(delta.y) > half.y || std::abs(delta.z) > half.z) continue;
            if ((portal.interaction_required || world.portal_interaction_required) && !interaction_pressed) continue;
            const Asset* destination_asset = find_asset(portal.destination_asset_id);
            if (destination_asset == nullptr || !destination_asset->metadata.enabled || !destination_asset->runtime_world.present) continue;
            math::Vec3 destination = destination_asset->metadata.preview_position;
            float yaw = portal.arrival_yaw_degrees;
            std::string destination_portal_id = portal.destination_portal_id;
            const auto& destination_world = destination_asset->runtime_world;
            const RuntimeWorldPortal* destination_portal = nullptr;
            if (!destination_portal_id.empty()) {
                const auto found = std::find_if(destination_world.portals.begin(), destination_world.portals.end(), [&](const RuntimeWorldPortal& value) {
                    return value.id == destination_portal_id && value.enabled;
                });
                if (found != destination_world.portals.end()) destination_portal = &*found;
            }
            if (destination_portal != nullptr) {
                destination = destination_asset->metadata.preview_position +
                    (destination_portal->position + portal.arrival_offset) * std::max(0.001F, std::abs(destination_asset->metadata.preview_scale));
                if (std::abs(yaw) < 0.001F) yaw = destination_portal->arrival_yaw_degrees;
            } else {
                const auto spawn = std::find_if(destination_world.spawn_points.begin(), destination_world.spawn_points.end(), [](const RuntimeWorldSpawn& value) {
                    return value.enabled && value.role == "default";
                });
                if (spawn != destination_world.spawn_points.end()) {
                    destination = destination_asset->metadata.preview_position + spawn->position * std::max(0.001F, std::abs(destination_asset->metadata.preview_scale));
                    if (std::abs(yaw) < 0.001F) yaw = spawn->yaw_degrees;
                } else {
                    destination += portal.arrival_offset;
                }
            }
            WorldPortalTransfer transfer;
            transfer.valid = true;
            transfer.source_asset_id = asset.metadata.asset_id;
            transfer.source_portal_id = portal.id;
            transfer.destination_asset_id = destination_asset->metadata.asset_id;
            transfer.destination_portal_id = destination_portal_id;
            transfer.destination_zone = destination_world.host_zone.empty() ? destination_asset->metadata.preview_zone : destination_world.host_zone;
            transfer.destination = destination;
            transfer.destination_yaw_degrees = yaw;
            transfer.cooldown_seconds = std::max(world.portal_cooldown, 0.1F);
            return transfer;
        }
    }
    return std::nullopt;
}

}  // namespace signalcloud::pcp3
