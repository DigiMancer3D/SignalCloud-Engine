#pragma once

#include "engine/math/vec.hpp"
#include "engine/render/point_types.hpp"

#include <cstdint>
#include <deque>
#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace signalcloud::pcp3 {

struct LayeredPoint {
    render::PointGpu point{};
    std::uint32_t layer_id{0};
    std::uint32_t flags{0};
    float attribute0{0.0F};
    float attribute1{0.0F};
};

struct RuntimeKeyframe {
    float time{0.0F};
    math::Vec3 position{};
    math::Vec3 rotation_degrees{};
    math::Vec3 scale{1.0F, 1.0F, 1.0F};
};

struct RuntimePlacement {
    std::string asset_id;
    std::string kind{"object"};
    math::Vec3 position{};
    math::Vec3 rotation_degrees{};
    float scale{1.0F};
    bool enabled{true};
};

struct RuntimeTrigger {
    std::string type{"proximity"};
    math::Vec3 position{};
    float radius{1.0F};
    std::string action{"none"};
    std::string target;
    float delay{0.0F};
    float cooldown{1.3F};
    bool repeat{false};
    bool approved{false};
};

struct RuntimeFlowNode {
    math::Vec3 position{};
    math::Vec3 direction{1.0F, 0.0F, 0.0F};
    float strength{1.0F};
    float viscosity{1.0F};
};

struct RuntimeThemeSlot {
    std::string semantic{"generic"};
    std::uint32_t semantic_flag{0};
    float color[4]{0.85F, 0.80F, 0.58F, 1.0F};
};



struct RuntimeEntityBone {
    std::string name;
    int parent_index{-1};
    math::Vec3 start{};
    math::Vec3 end{0.0F, 1.0F, 0.0F};
    int weight_channel{0};
};

struct RuntimeEntityBoneKeyframe {
    std::string state{"idle"};
    int bone_channel{0};
    float time{0.0F};
    math::Vec3 position{};
    math::Vec3 rotation_degrees{};
    math::Vec3 scale{1.0F, 1.0F, 1.0F};
};

struct RuntimeEntityAnchor {
    std::string name;
    std::string role{"generic"};
    math::Vec3 position{};
};

struct RuntimeEntityClip {
    std::string clip{"Default"};
    float duration{1.0F};
    bool loop{true};
};

struct RuntimeEntity {
    bool present{false};
    bool enabled{false};
    bool game_enabled{false};
    bool stress_enabled{true};
    std::string entity_kind{"enemy"};
    std::string movement_profile{"stationary"};
    float movement_speed{1.5F};
    float movement_radius{6.0F};
    float hover_height{0.35F};
    float hover_period{2.0F};
    float detection_radius{10.0F};
    float attack_radius{2.5F};
    float attack_cooldown{1.3F};
    float transition_seconds{0.18F};
    bool bone_deformation{true};
    bool show_rig_debug{true};
    bool show_anchor_debug{true};
    bool show_state_debug{true};
    std::size_t max_deformed_points{250'000U};
    std::string attack_anchor;
    std::string effect_anchor;
    std::unordered_map<std::string, RuntimeEntityClip> state_clips;
    std::vector<RuntimeEntityBone> bones;
    std::vector<RuntimeEntityBoneKeyframe> bone_keyframes;
    std::vector<RuntimeEntityAnchor> anchors;
};

struct RuntimeInteractionPolicy {
    bool present{false};
    bool enabled{false};
    bool game_enabled{false};
    bool stress_enabled{true};
    float default_cooldown{1.3F};
    float alert_duration{3.0F};
    float pulse_duration{1.25F};
    float proxy_lifetime{5.0F};
    std::size_t max_state_entries{256U};
    std::size_t max_event_ledger{256U};
    std::size_t max_active_proxies{16U};
    std::string reset_policy{"zone_exit"};
    bool show_runtime_evidence{true};
    bool console_event_log{true};
};

struct RuntimeInteractionEvent {
    double time_seconds{0.0};
    std::string asset_id;
    std::size_t trigger_index{0U};
    std::string action;
    std::string target;
    bool console_log{true};
};

struct RuntimeProxyState {
    math::Vec3 position{};
    double expires_at{0.0};
};

struct RuntimeAssetState {
    bool visible{true};
    bool revealed{false};
    double alert_until{0.0};
    double pulse_until{0.0};
    std::string theme_target;
    std::vector<RuntimeProxyState> proxies;
};

struct RuntimeTriggerMemory {
    bool condition_active{false};
    bool fired_once{false};
    double armed_since{0.0};
    double last_fired{-1.0e30};
};

class RuntimeInteractionState {
public:
    void reset();
    void begin_zone(std::string_view zone, std::string_view reset_policy);
    [[nodiscard]] RuntimeAssetState& asset(std::string_view asset_id);
    [[nodiscard]] RuntimeTriggerMemory& trigger(std::string_view asset_id, std::size_t trigger_index);
    void push_event(RuntimeInteractionEvent event, std::size_t limit);
    [[nodiscard]] std::vector<RuntimeInteractionEvent> take_events();
    void prune(double now, std::size_t max_states, std::size_t max_proxies);

private:
    std::string zone_;
    std::unordered_map<std::string, RuntimeAssetState> assets_;
    std::unordered_map<std::string, RuntimeTriggerMemory> triggers_;
    std::deque<RuntimeInteractionEvent> events_;
};

struct RuntimeFactory {
    bool present{false};
    bool enabled{false};
    bool game_enabled{false};
    bool stress_enabled{true};
    bool scanner_required{false};
    bool proximity_required{false};
    float proximity_radius{16.0F};
    std::string clip{"Default"};
    float duration{1.0F};
    bool loop{true};
    std::string event_policy{"telemetry_only"};
    std::size_t max_nested_points{100'000U};
    std::vector<RuntimeKeyframe> keyframes;
    std::vector<RuntimePlacement> placements;
    std::vector<RuntimeTrigger> triggers;
    std::vector<RuntimeFlowNode> flow_nodes;
    std::vector<RuntimeThemeSlot> theme_slots;
};

struct RuntimeWorldPortal {
    std::string id;
    std::string kind{"door"};
    math::Vec3 position{};
    math::Vec3 size{1.2F, 2.2F, 0.4F};
    std::string destination_asset_id;
    std::string destination_portal_id;
    math::Vec3 arrival_offset{0.0F, 0.0F, 1.4F};
    float arrival_yaw_degrees{0.0F};
    bool interaction_required{true};
    bool one_way{false};
    bool enabled{true};
};

struct RuntimeWorldSpawn {
    std::string id;
    std::string role{"default"};
    math::Vec3 position{};
    float yaw_degrees{0.0F};
    bool enabled{true};
};

struct RuntimeWorldLiquid {
    bool enabled{false};
    std::string type{"water"};
    float color[4]{0.18F, 0.44F, 0.56F, 0.72F};
    float wave_amplitude{0.06F};
    float wave_frequency{0.7F};
    float flow_scale{1.0F};
    std::size_t max_points{150'000U};
};

struct RuntimeWorld {
    bool present{false};
    bool enabled{false};
    bool game_enabled{false};
    bool stress_enabled{true};
    std::string world_id{"pcp3_world"};
    std::string room_id;
    std::string room_name;
    std::string host_zone{"Reception Tape"};
    bool safe_room{false};
    int logical_level{0};
    std::string reset_policy{"zone_exit"};
    bool execute_portals{false};
    bool portal_interaction_required{true};
    float portal_cooldown{0.8F};
    bool show_portal_debug{true};
    bool show_bounds_debug{false};
    bool apply_theme{true};
    std::string theme_asset_id;
    std::size_t max_portals{32U};
    std::size_t max_placements{64U};
    RuntimeWorldLiquid liquid;
    std::vector<RuntimeWorldPortal> portals;
    std::vector<RuntimeWorldSpawn> spawn_points;
    std::vector<RuntimePlacement> placements;
    std::vector<RuntimeThemeSlot> theme_slots;
    std::vector<RuntimeFlowNode> flow_nodes;
};

struct RuntimeEncounterWave {
    std::string id;
    int index{0};
    std::vector<std::string> asset_ids;
    std::size_t count{1U};
    float delay{0.0F};
    float active_seconds{8.0F};
    std::string spawn_role{"encounter"};
    float spread_radius{3.0F};
    std::string completion_policy{"lifetime"};
};

struct RuntimeBossPhase {
    std::string id;
    std::string name;
    float progress_threshold{0.0F};
    std::string clip{"Default"};
    std::string movement_profile{"stationary"};
    std::string theme_target;
    std::string effect_anchor;
};

struct RuntimeEncounterFriendly {
    std::string id;
    std::string asset_id;
    math::Vec3 position{};
    math::Vec3 rotation_degrees{};
    float scale{1.0F};
    std::string group{"friendlies"};
    bool enabled{true};
};

struct RuntimeStreaming {
    bool present{false};
    bool enabled{false};
    bool game_enabled{false};
    bool stress_enabled{true};
    std::string profile{"adaptive_8m"};
    std::string lod_policy{"distance_semantic"};
    float chunk_edge{8.0F};
    std::size_t chunk_point_target{65'536U};
    std::size_t max_resident_chunks{64U};
    bool background_loading{true};
    bool preload_adjacent{true};
    float near_distance{16.0F};
    float mid_distance{48.0F};
    float far_distance{120.0F};
    float near_ratio{1.0F};
    float mid_ratio{0.55F};
    float far_ratio{0.22F};
    float very_far_ratio{0.06F};
    std::size_t minimum_points{512U};
    std::size_t maximum_points{500'000U};
    std::size_t frame_upload_budget_points{100'000U};
    bool preserve_semantic_points{true};
    float semantic_reserve_ratio{0.12F};
    float stability_hysteresis{0.12F};
    bool show_debug{false};
};

struct RuntimeEncounter {
    bool present{false};
    bool enabled{false};
    bool game_enabled{false};
    bool stress_enabled{true};
    std::string encounter_id;
    std::string host_zone{"Reception Tape"};
    std::string start_condition{"world_enter"};
    math::Vec3 start_position{};
    float start_radius{8.0F};
    float start_delay{0.0F};
    std::string completion_policy{"all_waves_cleared"};
    float completion_seconds{30.0F};
    float completion_delay{1.0F};
    float inter_wave_delay{1.3F};
    float entity_lifetime{8.0F};
    std::string reset_policy{"zone_exit"};
    std::string reward_policy{"telemetry_only"};
    int reward_proofs{0};
    int reward_xar{0};
    int reward_scrap{0};
    bool show_debug{true};
    bool console_events{true};
    std::size_t max_waves{16U};
    std::size_t max_active_entities{16U};
    std::size_t max_total_spawns{64U};
    std::size_t max_friendlies{8U};
    std::size_t max_boss_phases{4U};
    std::vector<RuntimeEncounterWave> waves;
    std::vector<RuntimeBossPhase> boss_phases;
    std::vector<RuntimeEncounterFriendly> friendlies;
};

struct RuntimeEncounterInstance {
    std::string asset_id;
    math::Vec3 position{};
    math::Vec3 rotation_degrees{};
    float scale{1.0F};
    std::size_t wave_index{0U};
    double spawned_at{0.0};
    double expires_at{0.0};
    bool friendly{false};
};

struct RuntimeEncounterEvent {
    double time_seconds{0.0};
    std::string host_asset_id;
    std::string encounter_id;
    std::string kind;
    std::size_t wave_index{0U};
    std::string referenced_asset_id;
    std::string reward_policy;
    int reward_proofs{0};
    int reward_xar{0};
    int reward_scrap{0};
    bool console_log{true};
};

struct RuntimeEncounterAssetState {
    bool armed{false};
    bool started{false};
    bool completed{false};
    bool completion_emitted{false};
    double armed_since{0.0};
    double started_at{0.0};
    double wave_ready_at{0.0};
    double completed_at{0.0};
    std::size_t next_wave{0U};
    std::size_t total_spawned{0U};
    std::vector<RuntimeEncounterInstance> instances;
};

class RuntimeEncounterState {
public:
    void reset();
    void begin_zone(std::string_view zone, std::string_view reset_policy);
    [[nodiscard]] RuntimeEncounterAssetState& asset(std::string_view asset_id);
    void push_event(RuntimeEncounterEvent event, std::size_t limit = 256U);
    [[nodiscard]] std::vector<RuntimeEncounterEvent> take_events();
    void prune(double now, std::size_t max_assets = 64U, std::size_t max_instances = 128U);

private:
    std::string zone_;
    std::unordered_map<std::string, RuntimeEncounterAssetState> assets_;
    std::deque<RuntimeEncounterEvent> events_;
};

struct WorldPortalTransfer {
    bool valid{false};
    std::string source_asset_id;
    std::string source_portal_id;
    std::string destination_asset_id;
    std::string destination_portal_id;
    std::string destination_zone;
    math::Vec3 destination{};
    float destination_yaw_degrees{0.0F};
    float cooldown_seconds{0.8F};
};

struct AssetMetadata {
    std::string asset_id;
    std::string display_name;
    std::string environment_type;
    std::string project_id;
    std::filesystem::path udata_path;
    std::filesystem::path cloud_path;
    bool enabled{true};
    bool auto_preview_in_game{false};
    std::string preview_zone{"Reception Tape"};
    math::Vec3 preview_position{2.0F, 1.0F, -3.0F};
    float preview_scale{1.0F};
};

struct Asset {
    AssetMetadata metadata;
    RuntimeFactory runtime_factory;
    RuntimeInteractionPolicy runtime_interaction;
    RuntimeEntity runtime_entity;
    RuntimeWorld runtime_world;
    RuntimeEncounter runtime_encounter;
    RuntimeStreaming runtime_streaming;
    std::vector<LayeredPoint> layered_points;
    math::Vec3 bounds_min{};
    math::Vec3 bounds_max{};

    [[nodiscard]] std::vector<render::PointGpu> render_points(
        math::Vec3 offset = {}, float scale = 1.0F) const;
    [[nodiscard]] bool finite() const noexcept;
};

bool load_cloud(const std::filesystem::path& path, Asset& asset, std::string* error = nullptr);
bool load_asset(const std::filesystem::path& udata_path, Asset& asset, std::string* error = nullptr);
bool load_runtime_streaming(const std::filesystem::path& path, RuntimeStreaming& streaming,
                            std::string* error = nullptr);
[[nodiscard]] std::size_t streaming_point_budget(const RuntimeStreaming& streaming,
                                                  std::size_t available_points,
                                                  float distance) noexcept;
[[nodiscard]] std::vector<std::size_t> streaming_sample_indices(
    const std::vector<LayeredPoint>& points, const RuntimeStreaming& streaming,
    std::size_t budget);
std::vector<Asset> discover_assets(const std::filesystem::path& project_root,
                                   std::vector<std::string>* warnings = nullptr);

enum class PreviewPurpose { game, stress };

struct RuntimeContext {
    double time_seconds{0.0};
    bool scanner_active{false};
    bool debug_evidence{false};
    bool interaction_pressed{false};
    math::Vec3 viewer_position{};
    RuntimeInteractionState* interaction_state{nullptr};
    RuntimeEncounterState* encounter_state{nullptr};
};

std::vector<render::PointGpu> points_for_zone(const std::vector<Asset>& assets,
                                               std::string_view zone,
                                               PreviewPurpose purpose,
                                               RuntimeContext context = {},
                                               std::size_t point_limit = 500'000U);

[[nodiscard]] std::optional<WorldPortalTransfer> world_portal_transfer(
    const std::vector<Asset>& assets, std::string_view zone, PreviewPurpose purpose,
    math::Vec3 viewer_position, bool interaction_pressed);
inline std::vector<render::PointGpu> points_for_zone(const std::vector<Asset>& assets,
                                                      std::string_view zone,
                                                      PreviewPurpose purpose,
                                                      std::size_t point_limit) {
    return points_for_zone(assets, zone, purpose, RuntimeContext{}, point_limit);
}

}  // namespace signalcloud::pcp3
