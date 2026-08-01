#include "engine/pcp3/pcp3_asset.hpp"

#include <cmath>
#include <iostream>
#include <vector>

using signalcloud::pcp3::Asset;
using signalcloud::pcp3::LayeredPoint;
using signalcloud::pcp3::PreviewPurpose;
using signalcloud::pcp3::RuntimeContext;
using signalcloud::pcp3::RuntimeInteractionState;
using signalcloud::pcp3::RuntimeTrigger;

namespace {

Asset make_asset() {
    Asset asset;
    asset.metadata.asset_id = "interaction_asset";
    asset.metadata.display_name = "Interaction Asset";
    asset.metadata.preview_zone = "Test Zone";
    asset.metadata.preview_position = {0.0F, 0.0F, 0.0F};
    asset.metadata.preview_scale = 1.0F;
    asset.metadata.enabled = true;
    asset.metadata.auto_preview_in_game = true;
    asset.runtime_factory.present = true;
    asset.runtime_factory.enabled = true;
    asset.runtime_factory.game_enabled = true;
    asset.runtime_factory.stress_enabled = true;
    asset.runtime_factory.duration = 1.0F;
    asset.runtime_factory.loop = true;
    asset.runtime_interaction.present = true;
    asset.runtime_interaction.enabled = true;
    asset.runtime_interaction.game_enabled = true;
    asset.runtime_interaction.stress_enabled = true;
    asset.runtime_interaction.default_cooldown = 1.3F;
    asset.runtime_interaction.max_state_entries = 64U;
    asset.runtime_interaction.max_event_ledger = 64U;
    asset.runtime_interaction.max_active_proxies = 4U;

    LayeredPoint point;
    point.point.position[0] = 0.0F;
    point.point.position[1] = 0.0F;
    point.point.position[2] = 0.0F;
    point.point.radius = 2.0F;
    point.point.color[0] = 0.25F;
    point.point.color[1] = 0.5F;
    point.point.color[2] = 0.75F;
    point.point.color[3] = 1.0F;
    point.point.normal[1] = 1.0F;
    point.point.density = 1.0F;
    point.flags = 8U;
    asset.layered_points.push_back(point);
    return asset;
}

RuntimeTrigger trigger(std::string type, std::string action) {
    RuntimeTrigger value;
    value.type = std::move(type);
    value.action = std::move(action);
    value.position = {0.0F, 0.0F, 0.0F};
    value.radius = 4.0F;
    value.cooldown = 1.3F;
    value.approved = true;
    return value;
}

}  // namespace

int main() {
    auto asset = make_asset();
    std::vector<Asset> assets{asset};
    RuntimeInteractionState state;
    RuntimeContext context;
    context.viewer_position = {0.0F, 0.0F, 0.0F};
    context.interaction_state = &state;

    // Scanner reveal bypasses the global scanner gate after firing.
    assets[0].runtime_factory.scanner_required = true;
    assets[0].runtime_factory.triggers = {trigger("scanner", "reveal")};
    context.time_seconds = 0.0;
    context.scanner_active = false;
    auto points = signalcloud::pcp3::points_for_zone(assets, "Test Zone", PreviewPurpose::game, context, 1000U);
    if (!points.empty()) return 1;
    context.time_seconds = 0.1;
    context.scanner_active = true;
    points = signalcloud::pcp3::points_for_zone(assets, "Test Zone", PreviewPurpose::game, context, 1000U);
    if (points.empty()) return 2;
    auto events = state.take_events();
    if (events.size() != 1U || events.front().action != "reveal") return 3;
    context.time_seconds = 0.2;
    context.scanner_active = false;
    points = signalcloud::pcp3::points_for_zone(assets, "Test Zone", PreviewPurpose::game, context, 1000U);
    if (points.empty()) return 4;

    // Hide is reversible by resetting the bounded session state.
    state.reset();
    assets[0].runtime_factory.scanner_required = false;
    assets[0].runtime_factory.triggers = {trigger("proximity", "hide")};
    context.time_seconds = 1.0;
    points = signalcloud::pcp3::points_for_zone(assets, "Test Zone", PreviewPurpose::game, context, 1000U);
    if (!points.empty()) return 5;
    events = state.take_events();
    if (events.size() != 1U || events.front().action != "hide") return 6;
    state.reset();
    assets[0].runtime_factory.triggers.clear();
    context.time_seconds = 1.1;
    points = signalcloud::pcp3::points_for_zone(assets, "Test Zone", PreviewPurpose::game, context, 1000U);
    if (points.size() != 1U) return 7;

    // Interaction-driven proxy evidence is bounded and produces one ledger event.
    state.reset();
    auto proxy_trigger = trigger("interaction", "spawn_proxy");
    assets[0].runtime_factory.triggers = {proxy_trigger};
    context.interaction_pressed = true;
    context.time_seconds = 2.0;
    points = signalcloud::pcp3::points_for_zone(assets, "Test Zone", PreviewPurpose::game, context, 1000U);
    if (points.size() <= 1U) return 8;
    events = state.take_events();
    if (events.size() != 1U || events.front().action != "spawn_proxy") return 9;

    // Light pulse modifies the light semantic without changing source geometry.
    state.reset();
    assets[0].runtime_factory.triggers = {trigger("timer", "pulse_light")};
    context.interaction_pressed = false;
    context.time_seconds = 3.0;
    const float original_red = assets[0].layered_points.front().point.color[0];
    points = signalcloud::pcp3::points_for_zone(assets, "Test Zone", PreviewPurpose::game, context, 1000U);
    if (points.empty() || points.front().color[0] <= original_red) return 10;
    if (std::abs(assets[0].layered_points.front().point.color[0] - original_red) > 0.0001F) return 11;

    std::cout << "PCP3 guarded interaction runtime PASS\n";
    return 0;
}
