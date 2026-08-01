#include "engine/combat/combat_system.hpp"
#include "engine/world/liminal_level.hpp"
#include "engine/world/player_controller.hpp"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string_view>

namespace {
int failures = 0;

void check(bool condition, std::string_view message) {
    if (!condition) {
        ++failures;
        std::cerr << "FAIL: " << message << '\n';
    }
}

bool near(float a, float b, float epsilon = 0.001F) {
    return std::abs(a - b) <= epsilon;
}

const signalcloud::world::ThresholdEnvelope* find_envelope(
    const signalcloud::world::LiminalLevel& level,
    std::string_view a, std::string_view b) {
    for (const auto& envelope : level.threshold_envelopes()) {
        if ((envelope.zone_a == a && envelope.zone_b == b) ||
            (envelope.zone_a == b && envelope.zone_b == a)) return &envelope;
    }
    return nullptr;
}

}  // namespace

int main() {
    using namespace signalcloud;
    const auto level = world::LiminalLevel::make_pivot9_combat(0xDDACB40DEB350782ULL);

    check(level.areas().size() >= 25U, "Pivot 9 adds the live-fire signal range");
    check(level.portals().size() >= 21U, "Pivot 9 adds range entrance and return portals");
    check(level.zone_name(level.combat_lab_spawn()) == "Live-Fire Signal Range",
          "combat spawn resolves to the live-fire range");

    const auto* rotated_fix = find_envelope(level, "Traversal & Water Lab", "Fallen Office");
    check(rotated_fix != nullptr, "Traversal/Fallen shared threshold exists");
    if (rotated_fix != nullptr) {
        check(near(std::abs(rotated_fix->aperture.normal.x), 1.0F) &&
              near(rotated_fix->aperture.normal.z, 0.0F),
              "shared vertical threshold normal is snapped to the wall axis");
        check(near(rotated_fix->aperture.center.x, 656.0F),
              "rotated-frame correction preserves the accepted wall plane");
    }

    auto combat = combat::CombatSystem::make_pivot9();
    check(combat.entities().size() == 2U, "range begins with one hash dog and one shadow");
    auto visuals = combat.build_visual_points(0.0F, "Live-Fire Signal Range");
    check(visuals.size() >= 2'000U, "formed and formless entities produce dynamic points");
    bool finite = true;
    for (const auto& point : visuals) {
        for (float value : point.position) finite = finite && std::isfinite(value);
        finite = finite && std::isfinite(point.radius);
    }
    check(finite, "dynamic creature points are finite");
    check(combat.void_strength("Live-Fire Signal Range") > 0.8F,
          "living formless shadow creates a void field");

    const math::Vec3 pistol_origin{999.0F, 1.05F, -160.0F};
    for (int i = 0; i < 3; ++i) {
        const auto shot = combat.fire_primary(pistol_origin, {1.0F, 0.0F, 0.0F}, 1, true);
        check(shot.fired && shot.hit, "service pistol ray hits the formed hash dog");
        combat.update_timers(0.20F);
    }
    check(combat.kills() == 1U, "three pistol hits kill the hash dog");
    check(combat.proofs().size() == 1U, "dead creature leaves one live 3D proof");
    if (!combat.proofs().empty()) {
        check(combat.claim_near(combat.proofs().front().position),
              "nearby death proof can be claimed");
    } else {
        check(false, "nearby death proof can be claimed");
    }
    check(combat.claimed_proofs() == 1U, "claimed proof count advances once");

    const math::Vec3 shadow_origin{1002.0F, 1.05F, -140.0F};
    auto resisted = combat.fire_primary(shadow_origin, {0.0F, 0.0F, -1.0F}, 1, false);
    check(resisted.hit && resisted.shadow_resisted,
          "unscanned shot is mostly resisted by the formless shadow");
    combat.update_timers(0.20F);
    bool shadow_killed = false;
    for (int i = 0; i < 6 && !shadow_killed; ++i) {
        const auto shot = combat.fire_primary(shadow_origin, {0.0F, 0.0F, -1.0F}, 1, true);
        shadow_killed = shot.killed;
        combat.update_timers(0.20F);
    }
    check(shadow_killed, "scanner-revealed shots can kill the formless shadow");
    check(combat.proofs().size() == 2U, "both creature families produce proofs");
    check(combat.void_strength("Live-Fire Signal Range") == 0.0F,
          "void field ends when the shadow is killed");

    combat.reset_wave();
    combat.emit_noise({1000.0F, 0.0F, -160.0F}, 1.0F, "Live-Fire Signal Range");
    const auto heard = combat.update(0.016F, {984.0F, 1.72F, -176.0F},
                                    "Live-Fire Signal Range");
    check(heard.heard_noise, "creatures hear a loud range signal");
    bool investigating = false;
    for (const auto& entity : combat.entities()) {
        investigating = investigating || entity.state == combat::CreatureState::investigate ||
                        entity.state == combat::CreatureState::hunt;
    }
    check(investigating, "hearing changes at least one creature behavior state");

    world::PlayerController player(level.combat_lab_spawn());
    world::PlayerMoveInput input;
    input.quick_action_pressed = true;
    player.update(input, {1.0F, 0.0F, 0.0F}, 0.016F, level);
    check(player.evade_count() == 1U, "keyboard or mouse quick action starts one evade");
    check(player.combat_invulnerable(), "evade grants a brief combat defense window");
    const float health_before = player.health();
    player.apply_damage(20.0F);
    check(near(player.health(), health_before), "evade defense rejects immediate damage");

    if (failures != 0) {
        std::cerr << failures << " Pivot 9 checks failed.\n";
        return EXIT_FAILURE;
    }
    std::cout << "All SignalCloud Pivot 9 combat and frame-normal checks passed.\n";
    return EXIT_SUCCESS;
}
