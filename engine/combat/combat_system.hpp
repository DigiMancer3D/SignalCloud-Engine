#pragma once

#include "engine/math/vec.hpp"
#include "engine/render/point_types.hpp"

#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace signalcloud::world { class LiminalLevel; }

namespace signalcloud::combat {

enum class CreatureKind : std::uint8_t {
    hash_dog,
    formless_shadow,
};

enum class CreatureState : std::uint8_t {
    idle,
    investigate,
    hunt,
    attack,
    dodge,
    dead,
};

enum class AttackVisualKind : std::uint8_t {
    none,
    claw_arc,
    shadow_lance,
};

struct CombatEntity {
    std::uint64_t id{0};
    CreatureKind kind{CreatureKind::hash_dog};
    CreatureState state{CreatureState::idle};
    math::Vec3 position{};
    math::Vec3 home{};
    math::Vec3 target{};
    math::Vec3 forward{1.0F, 0.0F, 0.0F};
    math::Vec3 velocity{};
    math::Vec3 dodge_velocity{};
    std::string zone{"Live-Fire Signal Range"};
    float health{100.0F};
    float maximum_health{100.0F};
    float radius{1.0F};
    float hearing_radius{24.0F};
    float sight_radius{18.0F};
    float attack_range{1.7F};
    float attack_cooldown{0.0F};
    float alert_seconds{0.0F};
    float gait_phase{0.0F};
    float dodge_seconds{0.0F};
    float dodge_cooldown{0.0F};
    float deformation{0.0F};
    float patrol_half_x{22.0F};
    float patrol_half_z{18.0F};
    math::Vec3 last_seen_position{};
    math::Vec3 route_goal{};
    std::vector<math::Vec3> route;
    std::size_t route_index{0U};
    float memory_seconds{0.0F};
    float repath_seconds{0.0F};
    float blocked_seconds{0.0F};
    float stuck_seconds{0.0F};
    bool swimming{false};
    bool threshold_pending{false};
    std::string threshold_destination_zone{};
    math::Vec3 threshold_destination{};
    math::Vec3 threshold_preview_position{};
    math::Vec3 threshold_preview_forward{0.0F, 0.0F, -1.0F};
    float threshold_seconds{0.0F};
    float threshold_total_seconds{0.0F};
    std::uint32_t hit_reactions{0};
    bool alive{true};
    bool world_managed{false};
};

struct DeathProof {
    std::uint64_t id{0};
    std::uint64_t signature{0};
    CreatureKind source_kind{CreatureKind::hash_dog};
    math::Vec3 position{};
    std::string zone{"Live-Fire Signal Range"};
    float value{0.0F};
    bool claimed{false};
};

struct FireResult {
    bool fired{false};
    bool dry_fire{false};
    bool hit{false};
    bool killed{false};
    bool shadow_resisted{false};
    bool reaction_dodge{false};
    std::uint64_t entity_id{0};
    float damage{0.0F};
    math::Vec3 impact{};
    std::string message;
};

struct ThresholdPursuitUpdate {
    std::uint32_t arrived{0};
    std::uint32_t expired{0};
    std::uint32_t cancelled{0};
};

struct PerceptionEnvelope {
    bool downward_advantage{false};
    float effective_sight_radius{0.0F};
    float maximum_hearing_radius{0.0F};
    float required_loudness{0.0F};
};

[[nodiscard]] PerceptionEnvelope perception_envelope(
    CreatureKind kind, float base_sight_radius, float base_hearing_radius,
    float creature_sensor_y, float target_y, float noise_distance) noexcept;

struct CombatUpdate {
    float player_damage{0.0F};
    bool enemy_attack{false};
    bool heard_noise{false};
    std::string hint;
};

struct ViewmodelPose {
    math::Vec3 camera_position{};
    math::Vec3 forward{0.0F, 0.0F, -1.0F};
    math::Vec3 right{1.0F, 0.0F, 0.0F};
    float pitch_degrees{0.0F};
    float movement_amount{0.0F};
    bool sprinting{false};
    bool crouched{false};
    bool swimming{false};
    int weapon_slot{1};
};

[[nodiscard]] std::string_view creature_kind_name(CreatureKind kind) noexcept;
[[nodiscard]] std::string_view creature_state_name(CreatureState state) noexcept;
[[nodiscard]] std::string_view attack_visual_name(AttackVisualKind kind) noexcept;

class CombatSystem {
public:
    static CombatSystem make_pivot9();
    static CombatSystem make_pivot10();

    void reset();
    void update_timers(float dt_seconds) noexcept;
    CombatUpdate update(float dt_seconds, math::Vec3 player_position,
                        std::string_view active_zone,
                        const world::LiminalLevel* level = nullptr);
    FireResult fire_primary(math::Vec3 origin, math::Vec3 direction,
                            int weapon_slot, bool scanner_reveal,
                            std::string_view active_zone = "Live-Fire Signal Range");
    void reload() noexcept;
    void add_reserve_ammo(int rounds) noexcept;
    void emit_noise(math::Vec3 position, float loudness,
                    std::string_view source_zone);
    bool claim_near(math::Vec3 position, std::string_view active_zone,
                    float radius = 2.6F) noexcept;
    bool claim_near(math::Vec3 position, float radius = 2.6F) noexcept {
        return claim_near(position, "Live-Fire Signal Range", radius);
    }
    void reset_wave() noexcept;
    std::uint64_t spawn_world_entity(CreatureKind kind, math::Vec3 position,
                                     std::string_view zone,
                                     float patrol_half_x = 6.0F,
                                     float patrol_half_z = 6.0F);
    std::uint32_t despawn_world_entities(std::string_view zone) noexcept;
    bool migrate_one_world_entity(std::string_view source_zone,
                                  std::string_view destination_zone,
                                  math::Vec3 destination_home,
                                  float patrol_half_x,
                                  float patrol_half_z) noexcept;
    std::uint32_t migrate_pursuing_world_entities(std::string_view source_zone,
                                                   std::string_view destination_zone,
                                                   math::Vec3 destination_home,
                                                   float patrol_half_x,
                                                   float patrol_half_z,
                                                   std::uint32_t maximum_count = 1U) noexcept;
    std::uint32_t queue_threshold_pursuit(
        const world::LiminalLevel& level,
        std::string_view source_zone,
        std::string_view destination_zone,
        math::Vec3 source_threshold,
        math::Vec3 destination_entry,
        math::Vec3 destination_forward,
        float patrol_half_x,
        float patrol_half_z,
        float pursuit_window_seconds = 3.0F,
        std::uint32_t maximum_count = 2U);
    ThresholdPursuitUpdate update_threshold_pursuits(
        float dt_seconds, const world::LiminalLevel& level,
        std::string_view player_zone);
    [[nodiscard]] std::size_t living_in_zone(std::string_view zone) const noexcept;
    [[nodiscard]] std::size_t world_entity_count() const noexcept;
    [[nodiscard]] std::size_t pending_threshold_count() const noexcept;
    [[nodiscard]] bool entity_position_is_finite() const noexcept;
    void on_player_recovery_started() noexcept;
    void on_player_recovered() noexcept;

    [[nodiscard]] std::vector<render::PointGpu> build_visual_points(
        float time_seconds, std::string_view active_zone) const;
    [[nodiscard]] std::vector<render::PointGpu> build_viewmodel_points(
        float time_seconds, const ViewmodelPose& pose) const;
    [[nodiscard]] math::Vec3 void_position(std::string_view active_zone = "Live-Fire Signal Range") const noexcept;
    [[nodiscard]] float void_radius(std::string_view active_zone = "Live-Fire Signal Range") const noexcept;
    [[nodiscard]] float void_strength(std::string_view active_zone) const noexcept;
    [[nodiscard]] const std::vector<CombatEntity>& entities() const noexcept { return entities_; }
    [[nodiscard]] const std::vector<DeathProof>& proofs() const noexcept { return proofs_; }
    [[nodiscard]] int magazine() const noexcept { return magazine_; }
    [[nodiscard]] int reserve_ammo() const noexcept { return reserve_ammo_; }
    [[nodiscard]] std::uint32_t claimed_proofs() const noexcept { return claimed_proofs_; }
    [[nodiscard]] std::uint32_t kills() const noexcept { return kills_; }
    [[nodiscard]] float fire_cooldown() const noexcept { return fire_cooldown_; }
    [[nodiscard]] std::string_view last_hint() const noexcept { return last_hint_; }
    [[nodiscard]] AttackVisualKind attack_visual_kind() const noexcept { return attack_visual_kind_; }
    [[nodiscard]] float attack_visual_seconds() const noexcept { return attack_visual_seconds_; }
    [[nodiscard]] std::size_t last_world_visual_count() const noexcept { return last_world_visual_count_; }
    [[nodiscard]] std::size_t last_viewmodel_visual_count() const noexcept { return last_viewmodel_visual_count_; }

private:
    void kill_entity(CombatEntity& entity);
    void begin_reaction_dodge(CombatEntity& entity, math::Vec3 incoming_direction) noexcept;
    [[nodiscard]] CombatEntity* closest_ray_hit(math::Vec3 origin, math::Vec3 direction,
                                                float maximum_range, float* distance_out,
                                                std::string_view active_zone) noexcept;
    [[nodiscard]] CombatEntity* closest_melee_target(math::Vec3 origin, math::Vec3 direction,
                                                     float range,
                                                     std::string_view active_zone) noexcept;

    std::vector<CombatEntity> entities_;
    std::vector<DeathProof> proofs_;
    math::Vec3 last_noise_position_{};
    std::string last_noise_zone_;
    float last_noise_loudness_{0.0F};
    float noise_seconds_{0.0F};
    float fire_cooldown_{0.0F};
    float reload_seconds_{0.0F};
    int magazine_{12};
    int reserve_ammo_{48};
    std::uint32_t claimed_proofs_{0};
    std::uint32_t kills_{0};
    std::uint64_t next_proof_id_{1};
    std::uint64_t next_entity_id_{3};
    math::Vec3 tracer_start_{};
    math::Vec3 tracer_end_{};
    float tracer_seconds_{0.0F};
    float melee_swing_seconds_{0.0F};
    AttackVisualKind attack_visual_kind_{AttackVisualKind::none};
    math::Vec3 attack_visual_start_{};
    math::Vec3 attack_visual_end_{};
    float attack_visual_seconds_{0.0F};
    std::string last_hint_;
    mutable std::size_t last_world_visual_count_{0U};
    mutable std::size_t last_viewmodel_visual_count_{0U};
};

}  // namespace signalcloud::combat
