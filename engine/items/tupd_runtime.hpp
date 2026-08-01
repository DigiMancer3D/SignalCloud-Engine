#pragma once

#include <cstddef>
#include <filesystem>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace signalcloud::items {

enum class TupdMode {
    modification,
    forced_modification,
    upgrade,
    repair_small,
    repair_full,
    assembly,
    unknown,
};

enum class TupdTestAction {
    inspect,
    handle,
    primary,
    collision,
    break_test,
    light,
    interact,
    unknown,
};

struct ItemDefinition {
    std::string item_id;
    std::string item_kind{"object"};
    float unit_weight{0.0F};
    std::size_t stack_limit{1U};
    std::vector<std::string> interfaces;
};

struct WeaponDefinition {
    std::string item_id;
    std::string weapon_class;
    std::string ammo_type;
    float base_condition{100.0F};
    std::vector<std::string> sockets;
};

struct PartDefinition {
    std::string item_id;
    std::string interface_id;
    float weight{0.0F};
    bool forceable{false};
};

struct SocketDefinition {
    std::string socket_id;
    std::string interface_id;
    std::vector<std::string> accepts;
    bool forceable{false};
};

struct ModificationDefinition {
    std::string modification_id;
    std::string part_id;
    std::string socket_id;
    float weight_delta{0.0F};
    float stability_delta{0.0F};
};

struct UpgradeDefinition {
    std::string upgrade_id;
    std::string stat_id;
    float amount{0.0F};
    float cap{0.0F};
};

struct TupdResultDefinition {
    std::string result_id;
    std::string result_kind{"object"};
    std::string display_name;
    std::vector<std::string> interfaces;
    std::vector<std::string> sockets;
    std::vector<std::string> tags;
    std::size_t point_budget{1200U};
};

struct TupdRecipe {
    std::string schema{"signalcloud.tupd-recipe"};
    int schema_major{1};
    int schema_minor{1};
    int recipe_revision{1};
    std::string recipe_id;
    std::string label;
    TupdMode mode{TupdMode::unknown};
    std::string base_item_id{"weapon.service-pistol"};
    std::vector<std::string> input_ids;
    std::vector<std::string> consumed_ids;
    std::vector<std::string> required_interfaces;
    std::vector<std::string> optional_interfaces;
    std::vector<std::string> connections;
    std::vector<std::string> forced_connections;
    std::vector<std::string> validation_rules;
    std::vector<std::string> test_actions;
    int cost_xar{0};
    float repair_percent{0.0F};
    float stability_penalty{0.0F};
    float weight_penalty{0.0F};
    std::string malfunction_policy{"none"};
    TupdResultDefinition result;
    std::string preview_shape{"assembly"};
    std::string preview_color{"#45d8ef"};
    std::string receipt_policy{"deterministic"};
    std::map<std::string, std::string> extensions;
};

struct AssemblyNode {
    std::string item_id;
    std::string interface_id;
    bool consumed{false};
};

struct AssemblyConnection {
    std::string from_id;
    std::string to_id;
    std::string socket_id;
    bool forced{false};
};

struct AssemblyGraph {
    std::vector<AssemblyNode> nodes;
    std::vector<AssemblyConnection> connections;
};

struct TupdInventory {
    std::map<std::string, int> items;
    std::set<std::string> interfaces;
    int xar{0};
    float weapon_condition{62.0F};
    float weapon_weight{2.4F};
    std::string weapon_definition_id{"weapon.service-pistol"};
    std::string normal_save_fingerprint{"normal-save-untouched"};
};

struct TupdComparison {
    float condition_before{0.0F};
    float condition_after{0.0F};
    float weight_before{0.0F};
    float weight_after{0.0F};
    float stability_before{100.0F};
    float stability_after{100.0F};
    std::size_t point_budget{0U};
    std::vector<std::string> added_interfaces;
    std::vector<std::string> added_sockets;
    std::size_t connection_count{0U};
    std::size_t forced_connection_count{0U};
};

struct TupdPreview {
    bool valid{false};
    bool forced{false};
    std::vector<std::string> errors;
    std::vector<std::string> warnings;
    std::string result_id;
    std::string result_name;
    float condition_before{0.0F};
    float condition_after{0.0F};
    float weight_before{0.0F};
    float weight_after{0.0F};
    float weight_delta{0.0F};
    float stability_percent{100.0F};
    std::size_t point_budget{0U};
    int xar_cost{0};
    std::vector<std::string> added_interfaces;
    std::vector<std::string> added_sockets;
    std::size_t connection_count{0U};
    std::size_t forced_connection_count{0U};
    std::string signature;
};

struct TupdReceipt {
    bool committed{false};
    std::string receipt_id;
    std::string recipe_id;
    std::string result_id;
    int xar_before{0};
    int xar_after{0};
    float condition_before{0.0F};
    float condition_after{0.0F};
    std::map<std::string, int> consumed;
    std::string signature;
};

struct TupdResultInstance {
    std::string schema{"signalcloud.tupd-instance"};
    int schema_major{1};
    int schema_minor{0};
    std::string instance_id;
    std::string recipe_id;
    int recipe_revision{1};
    std::string result_id;
    std::string result_kind{"object"};
    std::string display_name;
    std::string base_item_id;
    float condition{0.0F};
    float weight{0.0F};
    float stability_percent{100.0F};
    std::size_t point_budget{0U};
    std::vector<std::string> interfaces;
    std::vector<std::string> sockets;
    std::vector<std::string> tags;
    std::vector<std::string> applied_parts;
    std::vector<std::string> connections;
    std::vector<std::string> forced_connections;
    std::vector<std::string> test_actions;
    std::string malfunction_policy{"none"};
    bool equipped{false};
    bool spawned{false};
    bool broken{false};
    int test_count{0};
    std::string last_action;
    std::string last_outcome;
    std::string signature;
};

struct TupdInstanceTest {
    bool accepted{false};
    TupdTestAction action{TupdTestAction::unknown};
    std::string outcome;
    float condition_before{0.0F};
    float condition_after{0.0F};
    bool broke{false};
    std::string signature;
};

[[nodiscard]] std::string_view tupd_mode_name(TupdMode mode) noexcept;
[[nodiscard]] TupdMode parse_tupd_mode(std::string_view value) noexcept;
[[nodiscard]] std::string_view tupd_test_action_name(TupdTestAction action) noexcept;
[[nodiscard]] TupdTestAction parse_tupd_test_action(std::string_view value) noexcept;
[[nodiscard]] std::string tupd_instance_state(const TupdResultInstance& instance);
[[nodiscard]] TupdRecipe normalize_tupd_recipe(TupdRecipe recipe) noexcept;
[[nodiscard]] bool load_tupd_recipe(const std::filesystem::path& path,
                                    TupdRecipe& recipe,
                                    std::string* error = nullptr);
[[nodiscard]] bool save_tupd_recipe_atomic(const std::filesystem::path& path,
                                           const TupdRecipe& recipe,
                                           std::string* error = nullptr);
[[nodiscard]] std::vector<std::filesystem::path> discover_tupd_recipes(
    const std::filesystem::path& project_root);
[[nodiscard]] bool load_tupd_instance(const std::filesystem::path& path,
                                      TupdResultInstance& instance,
                                      std::string* error = nullptr);
[[nodiscard]] bool save_tupd_instance_atomic(const std::filesystem::path& path,
                                             const TupdResultInstance& instance,
                                             std::string* error = nullptr);
[[nodiscard]] std::vector<std::filesystem::path> discover_tupd_instances(
    const std::filesystem::path& project_root);
[[nodiscard]] AssemblyGraph build_assembly_graph(const TupdRecipe& recipe);
[[nodiscard]] TupdInventory make_tupd_test_inventory();
[[nodiscard]] TupdPreview preview_tupd(const TupdRecipe& recipe,
                                       const TupdInventory& inventory);
[[nodiscard]] TupdComparison compare_tupd_result(const TupdPreview& preview);
[[nodiscard]] TupdReceipt commit_tupd(const TupdRecipe& recipe,
                                      TupdInventory& inventory,
                                      const TupdPreview& preview);
[[nodiscard]] TupdResultInstance create_tupd_result_instance(const TupdRecipe& recipe,
                                                             const TupdPreview& preview,
                                                             const TupdReceipt& receipt,
                                                             const TupdInventory& inventory);
[[nodiscard]] bool equip_or_spawn_tupd_instance(TupdResultInstance& instance);
[[nodiscard]] TupdInstanceTest test_tupd_instance(TupdResultInstance& instance,
                                                  TupdTestAction action);
[[nodiscard]] bool write_tupd_receipt_atomic(const std::filesystem::path& path,
                                             const TupdReceipt& receipt,
                                             std::string* error = nullptr);

class TupdSandboxSession {
public:
    TupdSandboxSession();
    explicit TupdSandboxSession(TupdInventory inventory);

    [[nodiscard]] const TupdInventory& inventory() const noexcept { return inventory_; }
    [[nodiscard]] const TupdPreview& last_preview() const noexcept { return preview_; }
    [[nodiscard]] const TupdReceipt& last_receipt() const noexcept { return receipt_; }
    [[nodiscard]] const std::optional<TupdResultInstance>& result_instance() const noexcept { return instance_; }
    [[nodiscard]] const std::optional<TupdInstanceTest>& last_test() const noexcept { return last_test_; }
    [[nodiscard]] const std::vector<TupdInstanceTest>& test_history() const noexcept { return tests_; }
    [[nodiscard]] std::string_view normal_save_fingerprint() const noexcept {
        return normal_save_fingerprint_;
    }
    [[nodiscard]] bool normal_save_unchanged() const noexcept;

    TupdPreview preview(const TupdRecipe& recipe);
    TupdReceipt commit(const TupdRecipe& recipe);
    bool equip_or_spawn_result();
    TupdInstanceTest test_result(TupdTestAction action);
    void clear_result();
    void reset();

private:
    TupdInventory initial_;
    TupdInventory inventory_;
    TupdPreview preview_;
    TupdReceipt receipt_;
    std::optional<TupdResultInstance> instance_;
    std::optional<TupdInstanceTest> last_test_;
    std::vector<TupdInstanceTest> tests_;
    std::string normal_save_fingerprint_;
};

}  // namespace signalcloud::items
