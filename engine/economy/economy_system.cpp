#include "engine/economy/economy_system.hpp"

#include <algorithm>
#include <cmath>

namespace signalcloud::economy {
namespace {
constexpr std::string_view kEconomyZone = "Scavenger Exchange";
constexpr float kPi = 3.14159265358979323846F;
constexpr math::Vec3 kScavengerTerminal{1061.82F, 1.18F, -160.0F};
constexpr math::Vec3 kScavengerNormal{-1.0F, 0.0F, 0.0F};
constexpr math::Vec3 kVendingTerminal{1073.0F, 1.18F, -150.18F};
constexpr math::Vec3 kVendingNormal{0.0F, 0.0F, -1.0F};
constexpr math::Vec3 kAmmoTerminal{1073.0F, 1.18F, -169.82F};
constexpr math::Vec3 kAmmoNormal{0.0F, 0.0F, 1.0F};
constexpr std::int64_t kAmmoTabletCost = 5;
constexpr int kAmmoTabletRounds = 18;
constexpr float kActivationRange = 2.85F;
constexpr float kPromptRange = 4.25F;

float distance_xz(math::Vec3 a, math::Vec3 b) noexcept {
    const float dx = a.x - b.x;
    const float dz = a.z - b.z;
    return std::sqrt(dx * dx + dz * dz);
}

std::uint32_t hash32(std::uint64_t value) noexcept {
    value ^= value >> 33U;
    value *= 0xff51afd7ed558ccdULL;
    value ^= value >> 33U;
    value *= 0xc4ceb9fe1a85ec53ULL;
    value ^= value >> 33U;
    return static_cast<std::uint32_t>(value ^ (value >> 32U));
}

float unit_hash(std::uint64_t value) noexcept {
    return static_cast<float>(hash32(value) & 0x00FFFFFFU) /
           static_cast<float>(0x01000000U);
}

render::PointGpu point(math::Vec3 p, float radius, float r, float g, float b,
                       float alpha = 1.0F, float density = 1.0F) noexcept {
    return {{p.x, p.y, p.z}, radius, {r, g, b, alpha},
            {0.0F, 1.0F, 0.0F}, density};
}

void add_cluster(std::vector<render::PointGpu>& out, math::Vec3 center,
                 math::Vec3 scale, std::uint32_t count, std::uint64_t seed,
                 float r, float g, float b, float radius, float pulse) {
    out.reserve(out.size() + count);
    for (std::uint32_t i = 0; i < count; ++i) {
        const float u = unit_hash(seed + static_cast<std::uint64_t>(i) * 3U);
        const float v = unit_hash(seed + static_cast<std::uint64_t>(i) * 3U + 1U);
        const float w = unit_hash(seed + static_cast<std::uint64_t>(i) * 3U + 2U);
        const float angle = u * 2.0F * kPi;
        const float shell = 0.28F + 0.72F * w;
        const math::Vec3 p{
            center.x + std::cos(angle) * scale.x * shell,
            center.y + (v * 2.0F - 1.0F) * scale.y * shell + pulse,
            center.z + std::sin(angle) * scale.z * shell,
        };
        const float variation = 0.82F + 0.30F * unit_hash(seed ^ (static_cast<std::uint64_t>(i) << 8U));
        out.push_back(point(p, radius * (0.78F + u * 0.38F),
                            std::clamp(r * variation, 0.0F, 1.0F),
                            std::clamp(g * variation, 0.0F, 1.0F),
                            std::clamp(b * variation, 0.0F, 1.0F), 0.96F, 1.0F));
    }
}

void add_line(std::vector<render::PointGpu>& out, math::Vec3 a, math::Vec3 b,
              std::uint32_t count, float r, float g, float blue,
              float radius, float alpha = 0.96F) {
    if (count == 0U) return;
    for (std::uint32_t i = 0; i < count; ++i) {
        const float t = count <= 1U ? 0.0F : static_cast<float>(i) / static_cast<float>(count - 1U);
        out.push_back(point(a + (b - a) * t, radius, r, g, blue, alpha, 1.0F));
    }
}

void add_panel_line(std::vector<render::PointGpu>& out, math::Vec3 center,
                    math::Vec3 tangent, math::Vec3 normal,
                    float x0, float y0, float x1, float y1,
                    std::uint32_t count, float r, float g, float b,
                    float radius = 0.024F, float alpha = 0.96F) {
    const auto a = center + tangent * x0 + math::Vec3{0.0F, y0, 0.0F} + normal * 0.02F;
    const auto c = center + tangent * x1 + math::Vec3{0.0F, y1, 0.0F} + normal * 0.02F;
    add_line(out, a, c, count, r, g, b, radius, alpha);
}

void add_terminal(std::vector<render::PointGpu>& out, math::Vec3 center,
                  math::Vec3 normal, float r, float g, float b,
                  bool vending, bool prompt_active) {
    normal = math::normalize_or(normal, {0.0F, 0.0F, -1.0F});
    const math::Vec3 tangent{-normal.z, 0.0F, normal.x};
    const float half_w = vending ? 0.76F : 0.92F;
    const float bottom = -0.96F;
    const float top = vending ? 1.05F : 0.92F;
    add_panel_line(out, center, tangent, normal, -half_w, bottom, -half_w, top,
                   90U, r, g, b, 0.028F);
    add_panel_line(out, center, tangent, normal, half_w, bottom, half_w, top,
                   90U, r, g, b, 0.028F);
    add_panel_line(out, center, tangent, normal, -half_w, top, half_w, top,
                   80U, r, g, b, 0.028F);
    add_panel_line(out, center, tangent, normal, -half_w, bottom, half_w, bottom,
                   80U, r, g, b, 0.028F);
    for (int row = 0; row < (vending ? 5 : 3); ++row) {
        const float y = -0.48F + static_cast<float>(row) * 0.29F;
        add_panel_line(out, center, tangent, normal, -half_w * 0.72F, y,
                       half_w * 0.72F, y, 54U,
                       r * 0.75F, g * 0.90F, std::min(1.0F, b * 1.18F), 0.021F);
    }
    // A shallow forward hood makes the readable face unambiguous without
    // turning the device back into a full box.
    add_panel_line(out, center + normal * 0.08F, tangent, normal,
                   -half_w, top, -half_w * 0.72F, top + 0.10F,
                   24U, r, g, b, 0.022F, 0.82F);
    add_panel_line(out, center + normal * 0.08F, tangent, normal,
                   half_w, top, half_w * 0.72F, top + 0.10F,
                   24U, r, g, b, 0.022F, 0.82F);

    if (prompt_active) {
        const math::Vec3 sign_center = center + math::Vec3{0.0F, top + 0.42F, 0.0F} + normal * 0.08F;
        add_line(out, sign_center - tangent * 0.26F + math::Vec3{0.0F, 0.16F, 0.0F},
                 sign_center, 24U, 0.24F, 1.0F, 0.60F, 0.030F);
        add_line(out, sign_center,
                 sign_center + tangent * 0.26F + math::Vec3{0.0F, 0.16F, 0.0F},
                 24U, 0.24F, 1.0F, 0.60F, 0.030F);
        if (vending) {
            for (int i = -1; i <= 1; ++i) {
                const auto p = sign_center + tangent * static_cast<float>(i) * 0.22F +
                               math::Vec3{0.0F, 0.34F, 0.0F};
                add_cluster(out, p, {0.08F, 0.08F, 0.04F}, 45U,
                            0xA12000ULL + static_cast<std::uint64_t>(i + 2) * 37U,
                            i == -1 ? 0.28F : (i == 0 ? 0.20F : 0.82F),
                            i == -1 ? 1.0F : (i == 0 ? 0.78F : 0.34F),
                            i == -1 ? 0.34F : 1.0F, 0.024F, 0.0F);
            }
        } else {
            add_line(out, sign_center - tangent * 0.18F + math::Vec3{0.0F, 0.27F, 0.0F},
                     sign_center + tangent * 0.18F + math::Vec3{0.0F, 0.57F, 0.0F},
                     28U, 1.0F, 0.75F, 0.18F, 0.028F);
            add_line(out, sign_center + tangent * 0.18F + math::Vec3{0.0F, 0.27F, 0.0F},
                     sign_center - tangent * 0.18F + math::Vec3{0.0F, 0.57F, 0.0F},
                     28U, 1.0F, 0.75F, 0.18F, 0.028F);
        }
    }
}

}  // namespace

std::string_view item_kind_name(ItemKind kind) noexcept {
    switch (kind) {
        case ItemKind::signal_scrap: return "SIGNAL SCRAP";
        case ItemKind::almond_water: return "ALMOND WATER";
        case ItemKind::ammo_pack: return "AMMO PACK";
        case ItemKind::death_proof: return "LIVE 3D PROOF";
        case ItemKind::sabs_patch: return "SABS WET PATCH";
    }
    return "UNKNOWN";
}

std::string_view interaction_target_name(InteractionTarget target) noexcept {
    switch (target) {
        case InteractionTarget::none: return "NONE";
        case InteractionTarget::pickup: return "PICKUP";
        case InteractionTarget::scavenger: return "SCAVENGER";
        case InteractionTarget::vending: return "ALMOND TABLET";
        case InteractionTarget::ammo_tablet: return "AMMO TABLET";
    }
    return "NONE";
}

float item_weight(ItemKind kind) noexcept {
    switch (kind) {
        case ItemKind::signal_scrap: return 1.25F;
        case ItemKind::almond_water: return 0.75F;
        case ItemKind::ammo_pack: return 1.10F;
        case ItemKind::death_proof: return 0.35F;
        case ItemKind::sabs_patch: return 0.25F;
    }
    return 0.0F;
}

EconomySystem EconomySystem::make_pivot11() {
    EconomySystem result;
    result.reset();
    result.ar_menu_enabled_ = false;
    return result;
}

EconomySystem EconomySystem::make_pivot12() {
    EconomySystem result;
    result.reset();
    result.ar_menu_enabled_ = true;
    return result;
}

void EconomySystem::reset() {
    inventory_.clear();
    pickups_.clear();
    xar_balance_ = 10;
    sabs_wetness_seconds_ = 45.0F;
    sold_proofs_ = 0;
    purchases_ = 0;
    vending_menu_active_ = false;
    menu_product_ = 1;
    menu_quantity_ = 1;
    menu_cursor_x_ = -0.22F;
    menu_cursor_y_ = 0.02F;
    visual_feedback_seconds_ = 0.0F;
    visual_feedback_value_ = 0;
    last_hint_ = "Use the XAR/EX Tablet, Almond Tablet, or Ammo Tablet in the exchange";

    pickups_ = {
        {1U, ItemKind::signal_scrap, {1052.5F, 0.35F, -169.0F}, 2U, false},
        {2U, ItemKind::signal_scrap, {1057.0F, 0.35F, -146.5F}, 3U, false},
        {3U, ItemKind::almond_water, {1068.0F, 0.45F, -171.0F}, 1U, false},
        {4U, ItemKind::ammo_pack, {1077.5F, 0.42F, -165.0F}, 1U, false},
        {5U, ItemKind::sabs_patch, {1081.0F, 0.40F, -148.0F}, 1U, false},
    };
}

void EconomySystem::update(float dt_seconds, bool scanner_active) noexcept {
    if (scanner_active) {
        sabs_wetness_seconds_ = std::max(0.0F, sabs_wetness_seconds_ - dt_seconds);
    } else {
        sabs_wetness_seconds_ = std::max(0.0F, sabs_wetness_seconds_ - dt_seconds * 0.08F);
    }
    visual_feedback_seconds_ = std::max(0.0F, visual_feedback_seconds_ - dt_seconds);
}

DeathPenalty EconomySystem::apply_death_penalty() noexcept {
    DeathPenalty result;
    const std::int64_t percentage = std::max<std::int64_t>(0, xar_balance_ * 15 / 100);
    result.xar_lost = std::min<std::int64_t>(30, percentage);
    xar_balance_ = std::max<std::int64_t>(0, xar_balance_ - result.xar_lost);
    const std::uint32_t scrap = quantity(ItemKind::signal_scrap);
    result.scrap_lost = scrap / 2U;
    if (result.scrap_lost > 0U) remove_item(ItemKind::signal_scrap, result.scrap_lost);
    result.proofs_preserved = quantity(ItemKind::death_proof);
    close_vending_menu();
    last_hint_ = "Recovery fee applied; map memory, equipment, and secured proofs preserved";
    return result;
}

void EconomySystem::add_claimed_proof(std::uint32_t quantity_value) {
    if (quantity_value == 0U) return;
    if (add_item(ItemKind::death_proof, quantity_value)) {
        last_hint_ = "Live 3D proof secured in inventory";
    } else {
        last_hint_ = "Proof claim registered but inventory is over capacity";
    }
}

bool EconomySystem::add_item(ItemKind kind, std::uint32_t quantity_value) {
    if (quantity_value == 0U) return true;
    const float added_weight = item_weight(kind) * static_cast<float>(quantity_value);
    if (carried_weight() + added_weight > capacity_ + 0.001F) return false;
    for (auto& stack : inventory_) {
        if (stack.kind != kind) continue;
        stack.quantity += quantity_value;
        return true;
    }
    inventory_.push_back({kind, quantity_value});
    return true;
}

bool EconomySystem::remove_item(ItemKind kind, std::uint32_t quantity_value) noexcept {
    for (auto& stack : inventory_) {
        if (stack.kind != kind || stack.quantity < quantity_value) continue;
        stack.quantity -= quantity_value;
        return true;
    }
    return false;
}

std::uint32_t EconomySystem::sell_all(ItemKind kind, std::int64_t unit_value) noexcept {
    for (auto& stack : inventory_) {
        if (stack.kind != kind) continue;
        const std::uint32_t sold = stack.quantity;
        stack.quantity = 0U;
        xar_balance_ += static_cast<std::int64_t>(sold) * unit_value;
        return sold;
    }
    return 0U;
}

void EconomySystem::record_visual(math::Vec3 origin, math::Vec3 target,
                                  bool success, std::int64_t value) noexcept {
    visual_feedback_origin_ = origin;
    visual_feedback_target_ = target;
    visual_feedback_success_ = success;
    visual_feedback_value_ = value;
    visual_feedback_seconds_ = success ? 1.15F : 0.72F;
}

InteractionTarget EconomySystem::interaction_target(math::Vec3 player_position,
                                                     std::string_view active_zone,
                                                     float extra_range) const noexcept {
    if (active_zone != kEconomyZone) return InteractionTarget::none;
    const float pickup_range = 2.35F + extra_range;
    for (const auto& pickup : pickups_) {
        if (!pickup.collected && distance_xz(player_position, pickup.position) <= pickup_range) {
            return InteractionTarget::pickup;
        }
    }
    if (distance_xz(player_position, kScavengerTerminal) <= kActivationRange + extra_range) {
        return InteractionTarget::scavenger;
    }
    if (distance_xz(player_position, kVendingTerminal) <= kActivationRange + extra_range) {
        return InteractionTarget::vending;
    }
    if (distance_xz(player_position, kAmmoTerminal) <= kActivationRange + extra_range) {
        return InteractionTarget::ammo_tablet;
    }
    return InteractionTarget::none;
}

EconomyEvent EconomySystem::interact(math::Vec3 player_position,
                                     std::string_view active_zone,
                                     int belt_slot) {
    EconomyEvent event;
    if (active_zone != kEconomyZone) return event;

    for (auto& pickup : pickups_) {
        if (pickup.collected || distance_xz(player_position, pickup.position) > 2.35F) continue;
        event.handled = true;
        event.item = pickup.kind;
        event.quantity = pickup.quantity;
        if (!add_item(pickup.kind, pickup.quantity)) {
            event.message = "Inventory capacity reached; leave or sell weight first";
            last_hint_ = event.message;
            record_visual(pickup.position, player_position, false, 0);
            return event;
        }
        pickup.collected = true;
        event.success = true;
        event.message = "Collected " + std::to_string(pickup.quantity) + " " +
                        std::string(item_kind_name(pickup.kind));
        last_hint_ = event.message;
        record_visual(pickup.position, player_position, true,
                      static_cast<std::int64_t>(pickup.quantity));
        return event;
    }

    if (distance_xz(player_position, kScavengerTerminal) <= kActivationRange) {
        event.handled = true;
        const std::int64_t before = xar_balance_;
        const std::uint32_t scrap = sell_all(ItemKind::signal_scrap, 2);
        const std::uint32_t proofs = sell_all(ItemKind::death_proof, 12);
        sold_proofs_ += proofs;
        event.xar_delta = xar_balance_ - before;
        event.success = event.xar_delta > 0;
        event.message = event.success
            ? "Scavenger exchanged " + std::to_string(scrap) + " scrap and " +
              std::to_string(proofs) + " proofs for " + std::to_string(event.xar_delta) + " XAR"
            : "Scavenger found nothing saleable in the inventory";
        last_hint_ = event.message;
        record_visual(kScavengerTerminal, player_position, event.success, event.xar_delta);
        return event;
    }

    if (distance_xz(player_position, kAmmoTerminal) <= kActivationRange) {
        event.handled = true;
        event.item = ItemKind::ammo_pack;
        event.quantity = 1U;
        if (xar_balance_ < kAmmoTabletCost) {
            event.message = "Ammo Tablet requires 5 XAR for an 18-round transfer";
            last_hint_ = event.message;
            record_visual(kAmmoTerminal, player_position, false, -kAmmoTabletCost);
            return event;
        }
        xar_balance_ -= kAmmoTabletCost;
        ++purchases_;
        event.success = true;
        event.ammo_added = kAmmoTabletRounds;
        event.xar_delta = -kAmmoTabletCost;
        event.message = "Ammo Tablet transferred 18 rounds directly to weapon reserve for 5 XAR";
        last_hint_ = event.message;
        record_visual(kAmmoTerminal, player_position, true, -kAmmoTabletCost);
        return event;
    }

    if (distance_xz(player_position, kVendingTerminal) <= kActivationRange) {
        event.handled = true;
        if (!ar_menu_enabled_) {
            vending_menu_active_ = true;
            menu_product_ = std::clamp(belt_slot, 1, 3);
            menu_quantity_ = 1;
            event = confirm_vending_purchase(player_position);
            vending_menu_active_ = false;
            return event;
        }
        if (!vending_menu_active_) {
            vending_menu_active_ = true;
            menu_product_ = std::clamp(belt_slot, 1, 3);
            menu_quantity_ = 1;
            menu_cursor_x_ = -0.22F + static_cast<float>(menu_product_ - 1) * 0.22F;
            menu_cursor_y_ = 0.02F;
            event.success = true;
            event.menu_opened = true;
            event.message = "AR vending menu opened";
            last_hint_ = event.message;
            record_visual(kVendingTerminal, player_position, true, 0);
            return event;
        }
        return confirm_vending_purchase(player_position);
    }

    event.handled = true;
    event.message = "Move toward a glowing AR marker before interacting";
    last_hint_ = event.message;
    record_visual(player_position + math::Vec3{0.0F, 0.4F, 0.0F}, player_position,
                  false, 0);
    return event;
}

ItemKind EconomySystem::menu_item() const noexcept {
    if (menu_product_ == 2) return ItemKind::almond_water;
    if (menu_product_ == 3) return ItemKind::sabs_patch;
    return ItemKind::ammo_pack;
}

int EconomySystem::menu_unit_price() const noexcept {
    if (menu_product_ == 2) return 4;
    if (menu_product_ == 3) return 6;
    return 5;
}

EconomyEvent EconomySystem::confirm_vending_purchase(math::Vec3 player_position) {
    EconomyEvent event;
    event.handled = true;
    if (!vending_menu_active_) {
        event.message = "Open the vending AR menu first";
        last_hint_ = event.message;
        return event;
    }
    const ItemKind item = menu_item();
    const int unit_price = menu_unit_price();
    const std::uint32_t amount = static_cast<std::uint32_t>(std::clamp(menu_quantity_, 1, 9));
    const std::int64_t cost = static_cast<std::int64_t>(unit_price) * amount;
    event.item = item;
    event.quantity = amount;
    if (xar_balance_ < cost) {
        event.message = "Not enough XAR for the selected quantity";
        last_hint_ = event.message;
        record_visual(kVendingTerminal, player_position, false, -cost);
        return event;
    }
    if (!add_item(item, amount)) {
        event.message = "Inventory capacity reached; purchase refused";
        last_hint_ = event.message;
        record_visual(kVendingTerminal, player_position, false, -cost);
        return event;
    }
    xar_balance_ -= cost;
    purchases_ += amount;
    event.success = true;
    event.xar_delta = -cost;
    event.message = "Purchased " + std::to_string(amount) + " " +
                    std::string(item_kind_name(item)) + " for " +
                    std::to_string(cost) + " XAR";
    last_hint_ = event.message;
    record_visual(kVendingTerminal, player_position, true, -cost);
    return event;
}

void EconomySystem::close_vending_menu() noexcept {
    vending_menu_active_ = false;
    menu_quantity_ = 1;
    last_hint_ = "AR vending menu closed";
}

void EconomySystem::set_menu_product(int product) noexcept {
    menu_product_ = std::clamp(product, 1, 3);
    menu_cursor_x_ = -0.22F + static_cast<float>(menu_product_ - 1) * 0.22F;
}

void EconomySystem::adjust_menu_product(int direction) noexcept {
    if (direction == 0) return;
    int next = menu_product_ + (direction > 0 ? 1 : -1);
    if (next < 1) next = 3;
    if (next > 3) next = 1;
    set_menu_product(next);
}

void EconomySystem::adjust_menu_quantity(int direction) noexcept {
    if (direction == 0) return;
    menu_quantity_ = std::clamp(menu_quantity_ + (direction > 0 ? 1 : -1), 1, 9);
    menu_cursor_y_ = std::clamp(menu_cursor_y_ + static_cast<float>(direction) * 0.018F,
                                -0.16F, 0.16F);
}

void EconomySystem::move_menu_cursor(float dx, float dy) noexcept {
    menu_cursor_x_ = std::clamp(menu_cursor_x_ + dx, -0.34F, 0.34F);
    menu_cursor_y_ = std::clamp(menu_cursor_y_ + dy, -0.18F, 0.18F);
    if (menu_cursor_x_ < -0.11F) menu_product_ = 1;
    else if (menu_cursor_x_ > 0.11F) menu_product_ = 3;
    else menu_product_ = 2;
}

EconomyEvent EconomySystem::use_belt_item(int belt_slot) {
    EconomyEvent event;
    event.handled = true;
    ItemKind item = ItemKind::ammo_pack;
    if (belt_slot == 2) item = ItemKind::almond_water;
    else if (belt_slot == 3) item = ItemKind::sabs_patch;
    else if (belt_slot > 3) {
        event.message = "Usable belt slots: 1 ammo, 2 Almond Water, 3 SABS patch";
        last_hint_ = event.message;
        return event;
    }
    event.item = item;
    event.quantity = 1U;
    if (!remove_item(item, 1U)) {
        event.message = "No " + std::string(item_kind_name(item)) + " in inventory";
        last_hint_ = event.message;
        return event;
    }
    event.success = true;
    if (item == ItemKind::ammo_pack) {
        event.ammo_added = 18;
        event.message = "Loaded an ammo pack into reserve";
    } else if (item == ItemKind::almond_water) {
        event.health_restored = 18.0F;
        event.oxygen_restored = 16.0F;
        event.sabs_wetness_added = 32.0F;
        event.message = "Drank Almond Water and dampened the SABS contacts";
    } else {
        event.sabs_wetness_added = 70.0F;
        event.message = "Applied a SABS wet patch";
    }
    sabs_wetness_seconds_ = std::min(maximum_sabs_wetness_seconds_,
                                     sabs_wetness_seconds_ + event.sabs_wetness_added);
    last_hint_ = event.message;
    return event;
}

std::vector<render::PointGpu> EconomySystem::build_visual_points(
    float time_seconds, std::string_view active_zone,
    math::Vec3 player_position) const {
    std::vector<render::PointGpu> points;
    if (active_zone != kEconomyZone) return points;
    points.reserve(6'000U);
    const float pickup_pulse = 0.045F * std::sin(time_seconds * 2.8F);
    const bool scavenger_prompt = distance_xz(player_position, kScavengerTerminal) <= kPromptRange;
    const bool vending_prompt = distance_xz(player_position, kVendingTerminal) <= kPromptRange;
    const bool ammo_prompt = distance_xz(player_position, kAmmoTerminal) <= kPromptRange;
    add_terminal(points, kScavengerTerminal, kScavengerNormal,
                 0.25F, 0.92F, 0.48F, false, scavenger_prompt);
    add_terminal(points, kVendingTerminal, kVendingNormal,
                 0.95F, 0.70F, 0.20F, true, vending_prompt);
    add_terminal(points, kAmmoTerminal, kAmmoNormal,
                 0.96F, 0.12F, 0.08F, true, ammo_prompt);
    for (const auto& pickup : pickups_) {
        if (pickup.collected) continue;
        float r = 0.75F, g = 0.72F, b = 0.30F;
        math::Vec3 scale{0.32F, 0.26F, 0.32F};
        std::uint32_t count = 210U;
        if (pickup.kind == ItemKind::almond_water) { r = 0.20F; g = 0.82F; b = 0.96F; scale = {0.22F, 0.48F, 0.22F}; }
        if (pickup.kind == ItemKind::ammo_pack) { r = 0.25F; g = 0.82F; b = 0.32F; scale = {0.42F, 0.25F, 0.30F}; }
        if (pickup.kind == ItemKind::sabs_patch) { r = 0.78F; g = 0.34F; b = 0.96F; scale = {0.30F, 0.16F, 0.30F}; count = 160U; }
        add_cluster(points, pickup.position, scale, count, 0xEC0000ULL + pickup.id * 131U,
                    r, g, b, 0.042F, pickup_pulse);
        if (distance_xz(player_position, pickup.position) <= kPromptRange) {
            const auto top = pickup.position + math::Vec3{0.0F, scale.y + 0.55F, 0.0F};
            add_line(points, top + math::Vec3{-0.20F, 0.18F, 0.0F}, top,
                     18U, 0.24F, 1.0F, 0.62F, 0.026F);
            add_line(points, top, top + math::Vec3{0.20F, 0.18F, 0.0F},
                     18U, 0.24F, 1.0F, 0.62F, 0.026F);
        }
    }

    if (visual_feedback_seconds_ > 0.0F) {
        const float phase = std::clamp(visual_feedback_seconds_ / 1.15F, 0.0F, 1.0F);
        const float r = visual_feedback_success_ ? 0.22F : 1.0F;
        const float g = visual_feedback_success_ ? 1.0F : 0.10F;
        const float b = visual_feedback_success_ ? 0.56F : 0.08F;
        const auto target = visual_feedback_target_ + math::Vec3{0.0F, 0.65F, 0.0F};
        const auto origin = visual_feedback_origin_ + math::Vec3{0.0F, 0.65F, 0.0F};
        for (std::uint32_t i = 0; i < 180U; ++i) {
            const float t = static_cast<float>(i) / 179.0F;
            const float wave = std::sin(t * 6.0F * kPi + time_seconds * 12.0F) * 0.08F * phase;
            math::Vec3 p = origin + (target - origin) * t;
            p.y += wave;
            points.push_back(point(p, 0.024F, r, g, b, 0.40F + phase * 0.52F, 1.0F));
        }
        const float ring_radius = 0.20F + (1.0F - phase) * 0.70F;
        for (int i = 0; i < 96; ++i) {
            const float angle = static_cast<float>(i) / 96.0F * 2.0F * kPi;
            const math::Vec3 p = visual_feedback_origin_ + math::Vec3{
                std::cos(angle) * ring_radius, 1.05F, std::sin(angle) * ring_radius};
            points.push_back(point(p, 0.028F, r, g, b, 0.35F + phase * 0.55F, 1.0F));
        }
    }
    return points;
}

std::uint32_t EconomySystem::quantity(ItemKind kind) const noexcept {
    for (const auto& stack : inventory_) if (stack.kind == kind) return stack.quantity;
    return 0U;
}

float EconomySystem::carried_weight() const noexcept {
    float total = 0.0F;
    for (const auto& stack : inventory_) {
        total += item_weight(stack.kind) * static_cast<float>(stack.quantity);
    }
    return total;
}

float EconomySystem::encumbrance_ratio() const noexcept {
    return std::clamp(carried_weight() / std::max(0.1F, capacity_), 0.0F, 1.0F);
}

float EconomySystem::movement_scale() const noexcept {
    const float ratio = encumbrance_ratio();
    if (ratio <= 0.75F) return 1.0F;
    const float overload = (ratio - 0.75F) / 0.25F;
    return 1.0F - std::clamp(overload, 0.0F, 1.0F) * 0.28F;
}

float EconomySystem::sabs_wetness_ratio() const noexcept {
    return std::clamp(sabs_wetness_seconds_ / maximum_sabs_wetness_seconds_, 0.0F, 1.0F);
}

float EconomySystem::scanner_strength() const noexcept {
    return 0.35F + 0.65F * sabs_wetness_ratio();
}

}  // namespace signalcloud::economy
