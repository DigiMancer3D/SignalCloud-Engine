#pragma once

#include "engine/math/vec.hpp"
#include "engine/render/point_types.hpp"

#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace signalcloud::economy {

enum class ItemKind : std::uint8_t {
    signal_scrap,
    almond_water,
    ammo_pack,
    death_proof,
    sabs_patch,
};

enum class InteractionTarget : std::uint8_t {
    none,
    pickup,
    scavenger,
    vending,
    ammo_tablet,
};

struct InventoryStack {
    ItemKind kind{ItemKind::signal_scrap};
    std::uint32_t quantity{0};
};

struct LootPickup {
    std::uint64_t id{0};
    ItemKind kind{ItemKind::signal_scrap};
    math::Vec3 position{};
    std::uint32_t quantity{1};
    bool collected{false};
};

struct DeathPenalty {
    std::int64_t xar_lost{0};
    std::uint32_t scrap_lost{0};
    std::uint32_t proofs_preserved{0};
};

struct EconomyEvent {
    bool handled{false};
    bool success{false};
    bool menu_opened{false};
    bool menu_closed{false};
    int ammo_added{0};
    float health_restored{0.0F};
    float oxygen_restored{0.0F};
    float sabs_wetness_added{0.0F};
    std::int64_t xar_delta{0};
    std::uint32_t quantity{0};
    ItemKind item{ItemKind::signal_scrap};
    std::string message;
};

[[nodiscard]] std::string_view item_kind_name(ItemKind kind) noexcept;
[[nodiscard]] float item_weight(ItemKind kind) noexcept;
[[nodiscard]] std::string_view interaction_target_name(InteractionTarget target) noexcept;

class EconomySystem {
public:
    static EconomySystem make_pivot11();
    static EconomySystem make_pivot12();

    void reset();
    void update(float dt_seconds, bool scanner_active) noexcept;
    void add_claimed_proof(std::uint32_t quantity = 1U);
    [[nodiscard]] DeathPenalty apply_death_penalty() noexcept;

    [[nodiscard]] EconomyEvent interact(math::Vec3 player_position,
                                        std::string_view active_zone,
                                        int belt_slot);
    [[nodiscard]] EconomyEvent use_belt_item(int belt_slot);
    [[nodiscard]] EconomyEvent confirm_vending_purchase(math::Vec3 player_position);
    void close_vending_menu() noexcept;
    void set_menu_product(int product) noexcept;
    void adjust_menu_product(int direction) noexcept;
    void adjust_menu_quantity(int direction) noexcept;
    void move_menu_cursor(float dx, float dy) noexcept;

    [[nodiscard]] InteractionTarget interaction_target(math::Vec3 player_position,
                                                       std::string_view active_zone,
                                                       float extra_range = 0.0F) const noexcept;
    [[nodiscard]] std::vector<render::PointGpu> build_visual_points(
        float time_seconds, std::string_view active_zone,
        math::Vec3 player_position) const;
    [[nodiscard]] std::vector<render::PointGpu> build_visual_points(
        float time_seconds, std::string_view active_zone) const {
        return build_visual_points(time_seconds, active_zone, {});
    }

    [[nodiscard]] std::uint32_t quantity(ItemKind kind) const noexcept;
    [[nodiscard]] float carried_weight() const noexcept;
    [[nodiscard]] float capacity() const noexcept { return capacity_; }
    [[nodiscard]] float encumbrance_ratio() const noexcept;
    [[nodiscard]] float movement_scale() const noexcept;
    [[nodiscard]] std::int64_t xar_balance() const noexcept { return xar_balance_; }
    [[nodiscard]] float sabs_wetness_seconds() const noexcept { return sabs_wetness_seconds_; }
    [[nodiscard]] float sabs_wetness_ratio() const noexcept;
    [[nodiscard]] float scanner_strength() const noexcept;
    [[nodiscard]] const std::vector<LootPickup>& pickups() const noexcept { return pickups_; }
    [[nodiscard]] std::uint32_t sold_proofs() const noexcept { return sold_proofs_; }
    [[nodiscard]] std::uint32_t purchases() const noexcept { return purchases_; }
    [[nodiscard]] std::string_view last_hint() const noexcept { return last_hint_; }
    [[nodiscard]] bool vending_menu_active() const noexcept { return vending_menu_active_; }
    [[nodiscard]] int menu_product() const noexcept { return menu_product_; }
    [[nodiscard]] int menu_quantity() const noexcept { return menu_quantity_; }
    [[nodiscard]] int menu_unit_price() const noexcept;
    [[nodiscard]] float menu_cursor_x() const noexcept { return menu_cursor_x_; }
    [[nodiscard]] float menu_cursor_y() const noexcept { return menu_cursor_y_; }

private:
    bool add_item(ItemKind kind, std::uint32_t quantity);
    bool remove_item(ItemKind kind, std::uint32_t quantity) noexcept;
    std::uint32_t sell_all(ItemKind kind, std::int64_t unit_value) noexcept;
    void record_visual(math::Vec3 origin, math::Vec3 target, bool success,
                       std::int64_t value) noexcept;
    [[nodiscard]] ItemKind menu_item() const noexcept;

    std::vector<InventoryStack> inventory_;
    std::vector<LootPickup> pickups_;
    float capacity_{24.0F};
    std::int64_t xar_balance_{10};
    float sabs_wetness_seconds_{45.0F};
    float maximum_sabs_wetness_seconds_{120.0F};
    std::uint32_t sold_proofs_{0};
    std::uint32_t purchases_{0};
    bool vending_menu_active_{false};
    bool ar_menu_enabled_{true};
    int menu_product_{1};
    int menu_quantity_{1};
    float menu_cursor_x_{-0.22F};
    float menu_cursor_y_{0.02F};
    float visual_feedback_seconds_{0.0F};
    math::Vec3 visual_feedback_origin_{};
    math::Vec3 visual_feedback_target_{};
    bool visual_feedback_success_{true};
    std::int64_t visual_feedback_value_{0};
    std::string last_hint_{"Scavenging loop ready"};
};

}  // namespace signalcloud::economy
