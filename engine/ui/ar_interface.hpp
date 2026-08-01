#pragma once

#include "engine/math/vec.hpp"
#include "engine/render/point_types.hpp"
#include "engine/scfont/scfont.hpp"

#include <array>
#include <cstdint>
#include <memory>
#include <utility>
#include <vector>

namespace signalcloud::ui {

enum class ScannerContactKind : std::uint8_t {
    none,
    room,
    formed,
    formless,
    exchange,
    loot,
};

struct ScannerContact {
    ScannerContactKind kind{ScannerContactKind::none};
    float strength{0.0F};
};

enum class ArDangerKind : std::uint8_t {
    combat,
    drowning,
    pressure,
    fall,
    poison,
    treason,
};

enum class ArFeedbackKind : std::uint8_t {
    none,
    pickup,
    sale,
    purchase,
    use,
    failure,
    safe_lock,
};

struct ArPose {
    math::Vec3 camera_position{};
    math::Vec3 forward{0.0F, 0.0F, -1.0F};
    math::Vec3 right{1.0F, 0.0F, 0.0F};
};

struct ArInterfaceData {
    float health_ratio{1.0F};
    float oxygen_ratio{1.0F};
    float sabs_ratio{1.0F};
    float carry_ratio{0.0F};
    std::int64_t xar{0};
    int magazine{0};
    int reserve{0};
    int weapon_slot{1};
    int belt_slot{1};
    bool interaction_near{false};
    bool safe_room{false};
    bool vending_menu{false};
    int menu_product{1};
    int menu_quantity{1};
    int menu_unit_price{0};
    float menu_cursor_x{0.0F};
    float menu_cursor_y{0.0F};
    bool detailed_hint{false};
    bool scanner_active{false};
    float scanner_strength{0.0F};
    std::array<ScannerContact, 4> scanner_contacts{};
    int scanner_contact_count{0};
    ArDangerKind danger_kind{ArDangerKind::combat};
    bool recovery_active{false};
    float recovery_progress{0.0F};
    float blackout_strength{0.0F};
};

class ArInterface {
public:
    void set_font(std::shared_ptr<const font::Font> font) noexcept { font_ = std::move(font); }
    [[nodiscard]] bool external_font_active() const noexcept { return static_cast<bool>(font_); }
    void update(float dt_seconds) noexcept;
    void notify(ArFeedbackKind kind, int value = 0) noexcept;

    [[nodiscard]] std::vector<render::PointGpu> build_points(
        float time_seconds, const ArPose& pose, const ArInterfaceData& data) const;

    [[nodiscard]] ArFeedbackKind feedback_kind() const noexcept { return feedback_kind_; }
    [[nodiscard]] float feedback_seconds() const noexcept { return feedback_seconds_; }
    [[nodiscard]] int feedback_value() const noexcept { return feedback_value_; }

private:
    std::shared_ptr<const font::Font> font_;
    ArFeedbackKind feedback_kind_{ArFeedbackKind::none};
    float feedback_seconds_{0.0F};
    int feedback_value_{0};
};

}  // namespace signalcloud::ui
