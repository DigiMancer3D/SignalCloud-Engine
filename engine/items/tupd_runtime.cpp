#include "engine/items/tupd_runtime.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <system_error>

namespace signalcloud::items {
namespace {

constexpr std::size_t kMaxAssetBytes = 2U * 1024U * 1024U;

std::string read_text(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("Unable to open Tupd asset: " + path.string());
    std::ostringstream buffer;
    buffer << input.rdbuf();
    std::string text = buffer.str();
    if (text.size() > kMaxAssetBytes) throw std::runtime_error("Tupd asset exceeds the 2 MiB runtime limit");
    return text;
}

std::string trim(std::string_view value) {
    std::size_t first = 0U;
    while (first < value.size() && std::isspace(static_cast<unsigned char>(value[first]))) ++first;
    std::size_t last = value.size();
    while (last > first && std::isspace(static_cast<unsigned char>(value[last - 1U]))) --last;
    return std::string(value.substr(first, last - first));
}

std::optional<std::size_t> value_start(std::string_view text, std::string_view key) {
    const std::string quoted = "\"" + std::string(key) + "\"";
    std::size_t position = text.find(quoted);
    if (position == std::string_view::npos) return std::nullopt;
    position = text.find(':', position + quoted.size());
    if (position == std::string_view::npos) return std::nullopt;
    ++position;
    while (position < text.size() && std::isspace(static_cast<unsigned char>(text[position]))) ++position;
    return position;
}

std::optional<std::string> json_string(std::string_view text, std::string_view key) {
    const auto start = value_start(text, key);
    if (!start || *start >= text.size() || text[*start] != '"') return std::nullopt;
    std::string output;
    bool escaped = false;
    for (std::size_t index = *start + 1U; index < text.size(); ++index) {
        const char c = text[index];
        if (escaped) {
            switch (c) {
                case 'n': output.push_back('\n'); break;
                case 'r': output.push_back('\r'); break;
                case 't': output.push_back('\t'); break;
                case '\\': output.push_back('\\'); break;
                case '"': output.push_back('"'); break;
                default: output.push_back(c); break;
            }
            escaped = false;
        } else if (c == '\\') {
            escaped = true;
        } else if (c == '"') {
            return output;
        } else {
            output.push_back(c);
        }
    }
    return std::nullopt;
}

std::optional<double> json_number(std::string_view text, std::string_view key) {
    const auto start = value_start(text, key);
    if (!start) return std::nullopt;
    std::size_t end = *start;
    while (end < text.size()) {
        const char c = text[end];
        if (!(std::isdigit(static_cast<unsigned char>(c)) || c == '-' || c == '+' || c == '.' || c == 'e' || c == 'E')) break;
        ++end;
    }
    if (end == *start) return std::nullopt;
    try {
        const double value = std::stod(std::string(text.substr(*start, end - *start)));
        return std::isfinite(value) ? std::optional(value) : std::nullopt;
    } catch (...) {
        return std::nullopt;
    }
}

std::optional<bool> json_bool(std::string_view text, std::string_view key) {
    const auto start = value_start(text, key);
    if (!start) return std::nullopt;
    if (text.substr(*start, 4U) == "true") return true;
    if (text.substr(*start, 5U) == "false") return false;
    return std::nullopt;
}

std::optional<std::string_view> json_array_view(std::string_view text, std::string_view key) {
    const auto start = value_start(text, key);
    if (!start || *start >= text.size() || text[*start] != '[') return std::nullopt;
    bool in_string = false;
    bool escaped = false;
    int depth = 0;
    for (std::size_t index = *start; index < text.size(); ++index) {
        const char c = text[index];
        if (in_string) {
            if (escaped) escaped = false;
            else if (c == '\\') escaped = true;
            else if (c == '"') in_string = false;
            continue;
        }
        if (c == '"') in_string = true;
        else if (c == '[') ++depth;
        else if (c == ']' && --depth == 0) return text.substr(*start + 1U, index - *start - 1U);
    }
    return std::nullopt;
}

std::vector<std::string> json_string_array(std::string_view text, std::string_view key) {
    const auto view = json_array_view(text, key);
    if (!view) return {};
    std::vector<std::string> values;
    bool in_string = false;
    bool escaped = false;
    std::string current;
    for (const char c : *view) {
        if (in_string) {
            if (escaped) {
                switch (c) {
                    case 'n': current.push_back('\n'); break;
                    case 'r': current.push_back('\r'); break;
                    case 't': current.push_back('\t'); break;
                    default: current.push_back(c); break;
                }
                escaped = false;
            } else if (c == '\\') escaped = true;
            else if (c == '"') {
                in_string = false;
                values.push_back(current);
                current.clear();
            } else current.push_back(c);
        } else if (c == '"') in_string = true;
    }
    return values;
}

std::string escape_json(std::string_view value) {
    std::string output;
    output.reserve(value.size() + 8U);
    for (const char c : value) {
        switch (c) {
            case '\\': output += "\\\\"; break;
            case '"': output += "\\\""; break;
            case '\n': output += "\\n"; break;
            case '\r': output += "\\r"; break;
            case '\t': output += "\\t"; break;
            default: output.push_back(c); break;
        }
    }
    return output;
}

std::string array_json(const std::vector<std::string>& values) {
    std::ostringstream output;
    output << '[';
    for (std::size_t index = 0U; index < values.size(); ++index) {
        if (index != 0U) output << ',';
        output << '"' << escape_json(values[index]) << '"';
    }
    output << ']';
    return output.str();
}

std::uint64_t fnv1a(std::string_view value) noexcept {
    std::uint64_t hash = 1469598103934665603ULL;
    for (const unsigned char c : value) {
        hash ^= c;
        hash *= 1099511628211ULL;
    }
    return hash;
}

std::string hex64(std::uint64_t value) {
    std::ostringstream output;
    output << std::hex << std::setfill('0') << std::setw(16) << value;
    return output.str();
}

bool contains(const std::vector<std::string>& values, std::string_view target) {
    return std::find(values.begin(), values.end(), target) != values.end();
}

void unique_bounded(std::vector<std::string>& values) {
    std::vector<std::string> output;
    output.reserve(std::min<std::size_t>(values.size(), 64U));
    for (auto& value : values) {
        value = trim(value);
        if (value.empty() || contains(output, value)) continue;
        output.push_back(value);
        if (output.size() >= 64U) break;
    }
    values = std::move(output);
}

std::string recipe_signature_material(const TupdRecipe& recipe,
                                      const TupdInventory& inventory,
                                      const TupdPreview& preview) {
    std::ostringstream material;
    material << recipe.recipe_id << '|' << recipe.recipe_revision << '|' << tupd_mode_name(recipe.mode) << '|'
             << recipe.base_item_id << '|' << inventory.weapon_definition_id << '|'
             << inventory.weapon_condition << '|' << inventory.weapon_weight << '|' << inventory.xar << '|'
             << preview.result_id << '|' << preview.condition_after << '|' << preview.weight_after << '|'
             << preview.stability_percent << '|' << preview.point_budget << '|';
    for (const auto& [id, count] : inventory.items) material << id << '=' << count << ';';
    for (const auto& input : recipe.input_ids) material << input << ';';
    for (const auto& connection : recipe.connections) material << connection << ';';
    for (const auto& connection : recipe.forced_connections) material << connection << ';';
    for (const auto& action : recipe.test_actions) material << action << ';';
    return material.str();
}

std::string recipe_json(const TupdRecipe& recipe) {
    std::ostringstream output;
    output << "{\n"
           << "  \"schema\": \"" << escape_json(recipe.schema) << "\",\n"
           << "  \"schema_major\": " << recipe.schema_major << ",\n"
           << "  \"schema_minor\": " << recipe.schema_minor << ",\n"
           << "  \"recipe_revision\": " << recipe.recipe_revision << ",\n"
           << "  \"recipe_id\": \"" << escape_json(recipe.recipe_id) << "\",\n"
           << "  \"label\": \"" << escape_json(recipe.label) << "\",\n"
           << "  \"mode\": \"" << tupd_mode_name(recipe.mode) << "\",\n"
           << "  \"base_item_id\": \"" << escape_json(recipe.base_item_id) << "\",\n"
           << "  \"inputs\": " << array_json(recipe.input_ids) << ",\n"
           << "  \"consumed_inputs\": " << array_json(recipe.consumed_ids) << ",\n"
           << "  \"required_interfaces\": " << array_json(recipe.required_interfaces) << ",\n"
           << "  \"optional_interfaces\": " << array_json(recipe.optional_interfaces) << ",\n"
           << "  \"connections\": " << array_json(recipe.connections) << ",\n"
           << "  \"forced_connections\": " << array_json(recipe.forced_connections) << ",\n"
           << "  \"validation_rules\": " << array_json(recipe.validation_rules) << ",\n"
           << "  \"test_actions\": " << array_json(recipe.test_actions) << ",\n"
           << "  \"cost_xar\": " << recipe.cost_xar << ",\n"
           << "  \"repair_percent\": " << recipe.repair_percent << ",\n"
           << "  \"stability_penalty\": " << recipe.stability_penalty << ",\n"
           << "  \"weight_penalty\": " << recipe.weight_penalty << ",\n"
           << "  \"malfunction_policy\": \"" << escape_json(recipe.malfunction_policy) << "\",\n"
           << "  \"result_id\": \"" << escape_json(recipe.result.result_id) << "\",\n"
           << "  \"result_kind\": \"" << escape_json(recipe.result.result_kind) << "\",\n"
           << "  \"result_name\": \"" << escape_json(recipe.result.display_name) << "\",\n"
           << "  \"result_interfaces\": " << array_json(recipe.result.interfaces) << ",\n"
           << "  \"result_sockets\": " << array_json(recipe.result.sockets) << ",\n"
           << "  \"result_tags\": " << array_json(recipe.result.tags) << ",\n"
           << "  \"point_budget\": " << recipe.result.point_budget << ",\n"
           << "  \"preview_shape\": \"" << escape_json(recipe.preview_shape) << "\",\n"
           << "  \"preview_color\": \"" << escape_json(recipe.preview_color) << "\",\n"
           << "  \"receipt_policy\": \"" << escape_json(recipe.receipt_policy) << "\"";
    for (const auto& [key, value] : recipe.extensions) output << ",\n  \"" << escape_json(key) << "\": " << value;
    output << "\n}\n";
    return output.str();
}

std::string instance_json(const TupdResultInstance& instance) {
    std::ostringstream output;
    output << "{\n"
           << "  \"schema\": \"signalcloud.tupd-instance\",\n"
           << "  \"schema_major\": " << instance.schema_major << ",\n"
           << "  \"schema_minor\": " << instance.schema_minor << ",\n"
           << "  \"instance_id\": \"" << escape_json(instance.instance_id) << "\",\n"
           << "  \"recipe_id\": \"" << escape_json(instance.recipe_id) << "\",\n"
           << "  \"recipe_revision\": " << instance.recipe_revision << ",\n"
           << "  \"result_id\": \"" << escape_json(instance.result_id) << "\",\n"
           << "  \"result_kind\": \"" << escape_json(instance.result_kind) << "\",\n"
           << "  \"display_name\": \"" << escape_json(instance.display_name) << "\",\n"
           << "  \"base_item_id\": \"" << escape_json(instance.base_item_id) << "\",\n"
           << "  \"condition\": " << instance.condition << ",\n"
           << "  \"weight\": " << instance.weight << ",\n"
           << "  \"stability_percent\": " << instance.stability_percent << ",\n"
           << "  \"point_budget\": " << instance.point_budget << ",\n"
           << "  \"interfaces\": " << array_json(instance.interfaces) << ",\n"
           << "  \"sockets\": " << array_json(instance.sockets) << ",\n"
           << "  \"tags\": " << array_json(instance.tags) << ",\n"
           << "  \"applied_parts\": " << array_json(instance.applied_parts) << ",\n"
           << "  \"connections\": " << array_json(instance.connections) << ",\n"
           << "  \"forced_connections\": " << array_json(instance.forced_connections) << ",\n"
           << "  \"test_actions\": " << array_json(instance.test_actions) << ",\n"
           << "  \"malfunction_policy\": \"" << escape_json(instance.malfunction_policy) << "\",\n"
           << "  \"equipped\": " << (instance.equipped ? "true" : "false") << ",\n"
           << "  \"spawned\": " << (instance.spawned ? "true" : "false") << ",\n"
           << "  \"broken\": " << (instance.broken ? "true" : "false") << ",\n"
           << "  \"test_count\": " << instance.test_count << ",\n"
           << "  \"last_action\": \"" << escape_json(instance.last_action) << "\",\n"
           << "  \"last_outcome\": \"" << escape_json(instance.last_outcome) << "\",\n"
           << "  \"signature\": \"" << escape_json(instance.signature) << "\"\n"
           << "}\n";
    return output.str();
}

template <typename Loader>
bool atomic_write_validated(const std::filesystem::path& path,
                            std::string_view text,
                            Loader&& loader,
                            std::string* error) {
    try {
        std::filesystem::create_directories(path.parent_path());
        const std::filesystem::path temporary = path.string() + ".tmp";
        {
            std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
            if (!output) throw std::runtime_error("Unable to open temporary Tupd output");
            output << text;
            output.flush();
            if (!output) throw std::runtime_error("Unable to flush temporary Tupd output");
        }
        std::string load_error;
        if (!loader(temporary, &load_error)) throw std::runtime_error("Temporary Tupd asset failed validation: " + load_error);
        std::error_code ec;
        std::filesystem::rename(temporary, path, ec);
        if (ec) {
            std::filesystem::remove(path, ec);
            ec.clear();
            std::filesystem::rename(temporary, path, ec);
        }
        if (ec) throw std::runtime_error("Unable to promote Tupd asset: " + ec.message());
        return true;
    } catch (const std::exception& exception) {
        if (error != nullptr) *error = exception.what();
        return false;
    }
}

}  // namespace

std::string_view tupd_mode_name(TupdMode mode) noexcept {
    switch (mode) {
        case TupdMode::modification: return "modification";
        case TupdMode::forced_modification: return "forced_modification";
        case TupdMode::upgrade: return "upgrade";
        case TupdMode::repair_small: return "repair_small";
        case TupdMode::repair_full: return "repair_full";
        case TupdMode::assembly: return "assembly";
        case TupdMode::unknown: return "unknown";
    }
    return "unknown";
}

TupdMode parse_tupd_mode(std::string_view value) noexcept {
    if (value == "modification") return TupdMode::modification;
    if (value == "forced_modification") return TupdMode::forced_modification;
    if (value == "upgrade") return TupdMode::upgrade;
    if (value == "repair_small") return TupdMode::repair_small;
    if (value == "repair_full") return TupdMode::repair_full;
    if (value == "assembly") return TupdMode::assembly;
    return TupdMode::unknown;
}

std::string_view tupd_test_action_name(TupdTestAction action) noexcept {
    switch (action) {
        case TupdTestAction::inspect: return "inspect";
        case TupdTestAction::handle: return "handle";
        case TupdTestAction::primary: return "primary";
        case TupdTestAction::collision: return "collision";
        case TupdTestAction::break_test: return "break";
        case TupdTestAction::light: return "light";
        case TupdTestAction::interact: return "interact";
        case TupdTestAction::unknown: return "unknown";
    }
    return "unknown";
}

TupdTestAction parse_tupd_test_action(std::string_view value) noexcept {
    if (value == "inspect") return TupdTestAction::inspect;
    if (value == "handle") return TupdTestAction::handle;
    if (value == "primary") return TupdTestAction::primary;
    if (value == "collision") return TupdTestAction::collision;
    if (value == "break") return TupdTestAction::break_test;
    if (value == "light") return TupdTestAction::light;
    if (value == "interact") return TupdTestAction::interact;
    return TupdTestAction::unknown;
}

std::string tupd_instance_state(const TupdResultInstance& instance) {
    if (instance.broken) return "BROKEN";
    if (instance.equipped) return "EQUIPPED";
    if (instance.spawned) return "SPAWNED";
    return "COMMITTED / NOT EQUIPPED";
}

TupdRecipe normalize_tupd_recipe(TupdRecipe recipe) noexcept {
    recipe.schema = "signalcloud.tupd-recipe";
    recipe.schema_major = std::clamp(recipe.schema_major, 1, 64);
    recipe.schema_minor = std::clamp(recipe.schema_minor, 0, 4096);
    recipe.recipe_revision = std::clamp(recipe.recipe_revision, 1, 9999);
    recipe.cost_xar = std::clamp(recipe.cost_xar, 0, 1'000'000);
    const auto finite = [](float value, float fallback) noexcept { return std::isfinite(value) ? value : fallback; };
    recipe.repair_percent = std::clamp(finite(recipe.repair_percent, 0.0F), 0.0F, 100.0F);
    recipe.stability_penalty = std::clamp(finite(recipe.stability_penalty, 0.0F), 0.0F, 100.0F);
    recipe.weight_penalty = std::clamp(finite(recipe.weight_penalty, 0.0F), -100.0F, 1000.0F);
    recipe.result.point_budget = std::clamp<std::size_t>(recipe.result.point_budget, 64U, 50'000U);
    unique_bounded(recipe.input_ids); unique_bounded(recipe.consumed_ids);
    unique_bounded(recipe.required_interfaces); unique_bounded(recipe.optional_interfaces);
    unique_bounded(recipe.connections); unique_bounded(recipe.forced_connections);
    unique_bounded(recipe.validation_rules); unique_bounded(recipe.test_actions);
    unique_bounded(recipe.result.interfaces); unique_bounded(recipe.result.sockets); unique_bounded(recipe.result.tags);
    recipe.test_actions.erase(std::remove_if(recipe.test_actions.begin(), recipe.test_actions.end(), [](const std::string& value) {
        return parse_tupd_test_action(value) == TupdTestAction::unknown;
    }), recipe.test_actions.end());
    if (recipe.test_actions.empty()) recipe.test_actions.push_back("inspect");
    if (recipe.base_item_id.empty()) recipe.base_item_id = recipe.input_ids.empty() ? "object.tupd-base" : recipe.input_ids.front();
    if (recipe.mode != TupdMode::assembly && !contains(recipe.input_ids, recipe.base_item_id)) recipe.input_ids.insert(recipe.input_ids.begin(), recipe.base_item_id);
    if (recipe.receipt_policy != "deterministic" && recipe.receipt_policy != "none") recipe.receipt_policy = "deterministic";
    if (recipe.preview_shape != "weapon" && recipe.preview_shape != "barrier" && recipe.preview_shape != "tool" && recipe.preview_shape != "assembly") recipe.preview_shape = "assembly";
    if (recipe.malfunction_policy.empty()) recipe.malfunction_policy = "none";
    return recipe;
}

bool load_tupd_recipe(const std::filesystem::path& path, TupdRecipe& recipe, std::string* error) {
    try {
        const std::string text = read_text(path);
        TupdRecipe candidate;
        if (const auto value = json_string(text, "schema")) candidate.schema = *value;
        if (candidate.schema != "signalcloud.tupd-recipe") throw std::runtime_error("Unsupported Tupd recipe schema: " + candidate.schema);
        if (const auto value = json_number(text, "schema_major")) candidate.schema_major = static_cast<int>(*value);
        if (const auto value = json_number(text, "schema_minor")) candidate.schema_minor = static_cast<int>(*value);
        if (const auto value = json_number(text, "recipe_revision")) candidate.recipe_revision = static_cast<int>(*value);
        if (const auto value = json_string(text, "recipe_id")) candidate.recipe_id = *value;
        if (const auto value = json_string(text, "label")) candidate.label = *value;
        if (const auto value = json_string(text, "mode")) candidate.mode = parse_tupd_mode(*value);
        if (const auto value = json_string(text, "base_item_id")) candidate.base_item_id = *value;
        candidate.input_ids = json_string_array(text, "inputs");
        candidate.consumed_ids = json_string_array(text, "consumed_inputs");
        candidate.required_interfaces = json_string_array(text, "required_interfaces");
        candidate.optional_interfaces = json_string_array(text, "optional_interfaces");
        candidate.connections = json_string_array(text, "connections");
        candidate.forced_connections = json_string_array(text, "forced_connections");
        candidate.validation_rules = json_string_array(text, "validation_rules");
        candidate.test_actions = json_string_array(text, "test_actions");
        if (const auto value = json_number(text, "cost_xar")) candidate.cost_xar = static_cast<int>(*value);
        if (const auto value = json_number(text, "repair_percent")) candidate.repair_percent = static_cast<float>(*value);
        if (const auto value = json_number(text, "stability_penalty")) candidate.stability_penalty = static_cast<float>(*value);
        if (const auto value = json_number(text, "weight_penalty")) candidate.weight_penalty = static_cast<float>(*value);
        if (const auto value = json_string(text, "malfunction_policy")) candidate.malfunction_policy = *value;
        if (const auto value = json_string(text, "result_id")) candidate.result.result_id = *value;
        if (const auto value = json_string(text, "result_kind")) candidate.result.result_kind = *value;
        if (const auto value = json_string(text, "result_name")) candidate.result.display_name = *value;
        candidate.result.interfaces = json_string_array(text, "result_interfaces");
        candidate.result.sockets = json_string_array(text, "result_sockets");
        candidate.result.tags = json_string_array(text, "result_tags");
        if (const auto value = json_number(text, "point_budget")) candidate.result.point_budget = *value > 0.0 ? static_cast<std::size_t>(*value) : 64U;
        if (const auto value = json_string(text, "preview_shape")) candidate.preview_shape = *value;
        if (const auto value = json_string(text, "preview_color")) candidate.preview_color = *value;
        if (const auto value = json_string(text, "receipt_policy")) candidate.receipt_policy = *value;
        candidate = normalize_tupd_recipe(std::move(candidate));
        if (candidate.recipe_id.empty()) throw std::runtime_error("Tupd recipe_id is required");
        if (candidate.label.empty()) candidate.label = candidate.recipe_id;
        if (candidate.mode == TupdMode::unknown) throw std::runtime_error("Tupd mode is unknown");
        if (candidate.input_ids.empty()) throw std::runtime_error("Tupd recipe requires at least one input");
        if (candidate.result.result_id.empty()) throw std::runtime_error("Tupd result_id is required");
        if (candidate.result.display_name.empty()) candidate.result.display_name = candidate.result.result_id;
        recipe = std::move(candidate);
        return true;
    } catch (const std::exception& exception) {
        if (error != nullptr) *error = exception.what();
        return false;
    }
}

bool save_tupd_recipe_atomic(const std::filesystem::path& path, const TupdRecipe& recipe, std::string* error) {
    const TupdRecipe normalized = normalize_tupd_recipe(recipe);
    return atomic_write_validated(path, recipe_json(normalized), [&](const std::filesystem::path& temporary, std::string* load_error) {
        TupdRecipe reloaded; return load_tupd_recipe(temporary, reloaded, load_error);
    }, error);
}

std::vector<std::filesystem::path> discover_tupd_recipes(const std::filesystem::path& project_root) {
    std::vector<std::filesystem::path> paths;
    const std::array<std::filesystem::path, 3U> roots{project_root / "content/core/tupd", project_root / "content/starter/tupd", project_root / "content/user/tupd"};
    for (const auto& root : roots) {
        std::error_code ec;
        if (!std::filesystem::is_directory(root, ec)) continue;
        for (std::filesystem::recursive_directory_iterator iterator(root, ec), end; iterator != end && !ec; iterator.increment(ec)) {
            if (iterator->is_regular_file() && iterator->path().extension() == ".tupd") paths.push_back(iterator->path());
        }
    }
    std::sort(paths.begin(), paths.end());
    return paths;
}

bool load_tupd_instance(const std::filesystem::path& path, TupdResultInstance& instance, std::string* error) {
    try {
        const std::string text = read_text(path);
        TupdResultInstance candidate;
        if (const auto value = json_string(text, "schema")) candidate.schema = *value;
        if (candidate.schema != "signalcloud.tupd-instance") throw std::runtime_error("Unsupported Tupd instance schema");
        if (const auto value = json_number(text, "schema_major")) candidate.schema_major = std::clamp(static_cast<int>(*value), 1, 64);
        if (const auto value = json_number(text, "schema_minor")) candidate.schema_minor = std::clamp(static_cast<int>(*value), 0, 4096);
        if (const auto value = json_string(text, "instance_id")) candidate.instance_id = *value;
        if (const auto value = json_string(text, "recipe_id")) candidate.recipe_id = *value;
        if (const auto value = json_number(text, "recipe_revision")) candidate.recipe_revision = std::clamp(static_cast<int>(*value), 1, 9999);
        if (const auto value = json_string(text, "result_id")) candidate.result_id = *value;
        if (const auto value = json_string(text, "result_kind")) candidate.result_kind = *value;
        if (const auto value = json_string(text, "display_name")) candidate.display_name = *value;
        if (const auto value = json_string(text, "base_item_id")) candidate.base_item_id = *value;
        if (const auto value = json_number(text, "condition")) candidate.condition = std::clamp(static_cast<float>(*value), 0.0F, 100.0F);
        if (const auto value = json_number(text, "weight")) candidate.weight = std::clamp(static_cast<float>(*value), 0.0F, 10000.0F);
        if (const auto value = json_number(text, "stability_percent")) candidate.stability_percent = std::clamp(static_cast<float>(*value), 0.0F, 100.0F);
        if (const auto value = json_number(text, "point_budget")) candidate.point_budget = std::clamp<std::size_t>(static_cast<std::size_t>(std::max(1.0, *value)), 64U, 50000U);
        candidate.interfaces = json_string_array(text, "interfaces"); candidate.sockets = json_string_array(text, "sockets"); candidate.tags = json_string_array(text, "tags");
        candidate.applied_parts = json_string_array(text, "applied_parts"); candidate.connections = json_string_array(text, "connections"); candidate.forced_connections = json_string_array(text, "forced_connections"); candidate.test_actions = json_string_array(text, "test_actions");
        if (const auto value = json_string(text, "malfunction_policy")) candidate.malfunction_policy = *value;
        if (const auto value = json_bool(text, "equipped")) candidate.equipped = *value;
        if (const auto value = json_bool(text, "spawned")) candidate.spawned = *value;
        if (const auto value = json_bool(text, "broken")) candidate.broken = *value;
        if (const auto value = json_number(text, "test_count")) candidate.test_count = std::clamp(static_cast<int>(*value), 0, 1'000'000);
        if (const auto value = json_string(text, "last_action")) candidate.last_action = *value;
        if (const auto value = json_string(text, "last_outcome")) candidate.last_outcome = *value;
        if (const auto value = json_string(text, "signature")) candidate.signature = *value;
        unique_bounded(candidate.interfaces); unique_bounded(candidate.sockets); unique_bounded(candidate.tags); unique_bounded(candidate.applied_parts); unique_bounded(candidate.connections); unique_bounded(candidate.forced_connections); unique_bounded(candidate.test_actions);
        if (candidate.instance_id.empty() || candidate.recipe_id.empty() || candidate.result_id.empty()) throw std::runtime_error("Tupd instance requires instance_id, recipe_id, and result_id");
        instance = std::move(candidate);
        return true;
    } catch (const std::exception& exception) {
        if (error != nullptr) *error = exception.what();
        return false;
    }
}

bool save_tupd_instance_atomic(const std::filesystem::path& path, const TupdResultInstance& instance, std::string* error) {
    return atomic_write_validated(path, instance_json(instance), [&](const std::filesystem::path& temporary, std::string* load_error) {
        TupdResultInstance reloaded; return load_tupd_instance(temporary, reloaded, load_error);
    }, error);
}

std::vector<std::filesystem::path> discover_tupd_instances(const std::filesystem::path& project_root) {
    std::vector<std::filesystem::path> paths;
    const std::array<std::filesystem::path, 3U> roots{project_root / "content/core/tupd", project_root / "content/starter/tupd", project_root / "content/user/tupd"};
    for (const auto& root : roots) {
        std::error_code ec;
        if (!std::filesystem::is_directory(root, ec)) continue;
        for (std::filesystem::recursive_directory_iterator iterator(root, ec), end; iterator != end && !ec; iterator.increment(ec)) {
            if (iterator->is_regular_file() && iterator->path().extension() == ".tupdinstance") paths.push_back(iterator->path());
        }
    }
    std::sort(paths.begin(), paths.end());
    return paths;
}

AssemblyGraph build_assembly_graph(const TupdRecipe& recipe) {
    AssemblyGraph graph;
    for (const auto& input : recipe.input_ids) graph.nodes.push_back({input, "", contains(recipe.consumed_ids, input)});
    const auto parse_connection = [&](std::string_view value, bool forced) {
        AssemblyConnection connection;
        const std::size_t arrow = value.find('>');
        const std::size_t at = value.find('@');
        if (arrow == std::string_view::npos) return connection;
        connection.from_id = trim(value.substr(0U, arrow));
        const std::size_t to_end = at == std::string_view::npos ? value.size() : at;
        connection.to_id = trim(value.substr(arrow + 1U, to_end - arrow - 1U));
        if (at != std::string_view::npos) connection.socket_id = trim(value.substr(at + 1U));
        connection.forced = forced;
        return connection;
    };
    for (const auto& encoded : recipe.connections) { auto connection = parse_connection(encoded, false); if (!connection.from_id.empty() && !connection.to_id.empty()) graph.connections.push_back(std::move(connection)); }
    for (const auto& encoded : recipe.forced_connections) { auto connection = parse_connection(encoded, true); if (!connection.from_id.empty() && !connection.to_id.empty()) graph.connections.push_back(std::move(connection)); }
    return graph;
}

TupdInventory make_tupd_test_inventory() {
    TupdInventory inventory;
    inventory.items = {{"weapon.service-pistol",1},{"weapon.service-pistol.duplicate",1},{"weapon.prybar",1},{"part.signal-grip",2},{"part.office-bracket",2},{"part.upgrade-stabilizer",1},{"part.wall-panel",2},{"part.mount-bracket",2},{"consumable.tupd-tape",6}};
    inventory.interfaces = {"weapon.base","weapon.service-pistol","weapon.duplicate.match","socket.grip","socket.body","socket.signal","upgrade.stability","object.office","object.barrier","tupd.tape","safe-room","sandbox"};
    inventory.xar = 120; inventory.weapon_condition = 62.0F; inventory.weapon_weight = 2.4F; inventory.weapon_definition_id = "weapon.service-pistol"; inventory.normal_save_fingerprint = "normal-save-untouched";
    return inventory;
}

TupdPreview preview_tupd(const TupdRecipe& recipe, const TupdInventory& inventory) {
    const TupdRecipe normalized = normalize_tupd_recipe(recipe);
    TupdPreview preview;
    preview.forced = normalized.mode == TupdMode::forced_modification || !normalized.forced_connections.empty();
    preview.result_id = normalized.result.result_id; preview.result_name = normalized.result.display_name;
    preview.condition_before = inventory.weapon_condition;
    preview.condition_after = std::clamp(inventory.weapon_condition + normalized.repair_percent, 0.0F, 100.0F);
    preview.weight_before = inventory.weapon_weight;
    preview.weight_delta = normalized.weight_penalty;
    preview.weight_after = std::max(0.0F, inventory.weapon_weight + normalized.weight_penalty);
    preview.stability_percent = std::clamp(100.0F - normalized.stability_penalty, 0.0F, 100.0F);
    preview.point_budget = normalized.result.point_budget; preview.xar_cost = normalized.cost_xar;
    preview.added_interfaces = normalized.result.interfaces; preview.added_sockets = normalized.result.sockets;
    preview.connection_count = normalized.connections.size(); preview.forced_connection_count = normalized.forced_connections.size();
    for (const auto& input : normalized.input_ids) { const auto found = inventory.items.find(input); if (found == inventory.items.end() || found->second <= 0) preview.errors.push_back("missing input: " + input); }
    for (const auto& interface_id : normalized.required_interfaces) {
        if (!inventory.interfaces.contains(interface_id)) {
            if (preview.forced && contains(normalized.validation_rules, "allow_forced_connection")) preview.warnings.push_back("forced interface: " + interface_id);
            else preview.errors.push_back("missing interface: " + interface_id);
        }
    }
    if (inventory.xar < normalized.cost_xar) preview.errors.push_back("insufficient test XAR");
    if (normalized.mode == TupdMode::repair_full && !inventory.interfaces.contains("weapon.duplicate.match")) preview.errors.push_back("matching duplicate weapon required");
    if (normalized.mode == TupdMode::repair_small && inventory.weapon_condition >= 100.0F) preview.warnings.push_back("weapon already at full condition");
    if (preview.forced) preview.warnings.push_back("forced connection carries stability/weight penalties");
    if (normalized.malfunction_policy != "none") preview.warnings.push_back("malfunction policy: " + normalized.malfunction_policy);
    preview.valid = preview.errors.empty();
    preview.signature = hex64(fnv1a(recipe_signature_material(normalized, inventory, preview)));
    return preview;
}

TupdComparison compare_tupd_result(const TupdPreview& preview) {
    TupdComparison comparison;
    comparison.condition_before = preview.condition_before; comparison.condition_after = preview.condition_after;
    comparison.weight_before = preview.weight_before; comparison.weight_after = preview.weight_after;
    comparison.stability_after = preview.stability_percent; comparison.point_budget = preview.point_budget;
    comparison.added_interfaces = preview.added_interfaces; comparison.added_sockets = preview.added_sockets;
    comparison.connection_count = preview.connection_count; comparison.forced_connection_count = preview.forced_connection_count;
    return comparison;
}

TupdReceipt commit_tupd(const TupdRecipe& recipe, TupdInventory& inventory, const TupdPreview& preview) {
    TupdReceipt receipt; receipt.recipe_id = recipe.recipe_id; receipt.result_id = recipe.result.result_id;
    receipt.xar_before = inventory.xar; receipt.xar_after = inventory.xar; receipt.condition_before = inventory.weapon_condition; receipt.condition_after = inventory.weapon_condition;
    if (!preview.valid) { receipt.signature = hex64(fnv1a(recipe.recipe_id + "|rejected|" + preview.signature)); receipt.receipt_id = "tupd-rejected-" + receipt.signature; return receipt; }
    TupdInventory candidate = inventory;
    for (const auto& consumed_id : recipe.consumed_ids) {
        auto found = candidate.items.find(consumed_id);
        if (found == candidate.items.end() || found->second <= 0) { receipt.signature = hex64(fnv1a(recipe.recipe_id + "|atomic-reject|" + consumed_id)); receipt.receipt_id = "tupd-rejected-" + receipt.signature; return receipt; }
        --found->second; receipt.consumed[consumed_id] += 1;
    }
    if (candidate.xar < recipe.cost_xar) { receipt.consumed.clear(); receipt.signature = hex64(fnv1a(recipe.recipe_id + "|atomic-reject-xar")); receipt.receipt_id = "tupd-rejected-" + receipt.signature; return receipt; }
    candidate.xar -= recipe.cost_xar; candidate.weapon_condition = preview.condition_after; candidate.weapon_weight = preview.weight_after;
    candidate.items[recipe.result.result_id] += 1; for (const auto& interface_id : recipe.result.interfaces) candidate.interfaces.insert(interface_id);
    inventory = std::move(candidate); receipt.committed = true; receipt.xar_after = inventory.xar; receipt.condition_after = inventory.weapon_condition;
    std::ostringstream material; material << recipe.recipe_id << '|' << preview.signature << '|' << receipt.xar_before << '|' << receipt.xar_after << '|' << receipt.condition_before << '|' << receipt.condition_after;
    for (const auto& [id,count] : receipt.consumed) material << '|' << id << '=' << count;
    receipt.signature = hex64(fnv1a(material.str())); receipt.receipt_id = "tupd-" + receipt.signature; return receipt;
}

TupdResultInstance create_tupd_result_instance(const TupdRecipe& recipe, const TupdPreview& preview, const TupdReceipt& receipt, const TupdInventory& inventory) {
    TupdResultInstance instance;
    if (!receipt.committed) return instance;
    instance.instance_id = "tupd-instance-" + receipt.signature;
    instance.recipe_id = recipe.recipe_id; instance.recipe_revision = recipe.recipe_revision;
    instance.result_id = recipe.result.result_id; instance.result_kind = recipe.result.result_kind; instance.display_name = recipe.result.display_name;
    instance.base_item_id = recipe.base_item_id; instance.condition = preview.condition_after; instance.weight = preview.weight_after; instance.stability_percent = preview.stability_percent; instance.point_budget = preview.point_budget;
    instance.interfaces = recipe.result.interfaces; instance.sockets = recipe.result.sockets; instance.tags = recipe.result.tags;
    for (const auto& input : recipe.input_ids) if (input != recipe.base_item_id && !contains(recipe.consumed_ids, input)) instance.applied_parts.push_back(input);
    instance.connections = recipe.connections; instance.forced_connections = recipe.forced_connections; instance.test_actions = recipe.test_actions; instance.malfunction_policy = recipe.malfunction_policy;
    std::ostringstream material; material << receipt.signature << '|' << instance.result_id << '|' << instance.condition << '|' << instance.weight << '|' << instance.stability_percent << '|' << inventory.normal_save_fingerprint;
    instance.signature = hex64(fnv1a(material.str())); return instance;
}

bool equip_or_spawn_tupd_instance(TupdResultInstance& instance) {
    if (instance.instance_id.empty() || instance.broken) return false;
    const bool equipment = instance.result_kind == "weapon" || instance.result_kind == "tool" || contains(instance.tags, "weapon") || contains(instance.tags, "tool");
    instance.equipped = equipment; instance.spawned = !equipment;
    instance.last_outcome = equipment ? "equipped in isolated Tupd sandbox" : "spawned in isolated Tupd sandbox";
    instance.signature = hex64(fnv1a(instance.signature + "|" + tupd_instance_state(instance)));
    return true;
}

TupdInstanceTest test_tupd_instance(TupdResultInstance& instance, TupdTestAction action) {
    TupdInstanceTest test; test.action = action; test.condition_before = instance.condition; test.condition_after = instance.condition;
    const std::string action_name(tupd_test_action_name(action));
    if (instance.instance_id.empty()) { test.outcome = "no committed result instance"; return test; }
    if (!instance.equipped && !instance.spawned) { test.outcome = "equip or spawn the result before testing"; return test; }
    if (instance.broken) { test.outcome = "result instance is already broken"; return test; }
    if (action == TupdTestAction::unknown || !contains(instance.test_actions, action_name)) { test.outcome = "test action is not declared by this recipe"; return test; }
    test.accepted = true;
    switch (action) {
        case TupdTestAction::inspect: test.outcome = "inspection evidence recorded"; break;
        case TupdTestAction::handle: test.outcome = instance.stability_percent >= 70.0F ? "handling remained stable" : "handling exposed forced-connection wobble"; break;
        case TupdTestAction::primary: instance.condition = std::max(0.0F, instance.condition - (instance.stability_percent < 70.0F ? 1.25F : 0.35F)); test.outcome = "primary action completed in sandbox"; break;
        case TupdTestAction::collision: instance.condition = std::max(0.0F, instance.condition - std::clamp(instance.weight * 0.08F, 0.25F, 3.0F)); test.outcome = "bounded collision evidence recorded"; break;
        case TupdTestAction::break_test: {
            const float damage = 18.0F + (100.0F - instance.stability_percent) * 0.35F;
            instance.condition = std::max(0.0F, instance.condition - damage);
            if (instance.condition <= 20.0F || instance.stability_percent < 45.0F) { instance.broken = true; test.broke = true; test.outcome = "result broke under bounded destructive test"; }
            else test.outcome = "result survived bounded destructive test";
            break;
        }
        case TupdTestAction::light: test.outcome = contains(instance.interfaces, "light") || contains(instance.tags, "signal") ? "light/signal channel responded" : "no dedicated light channel; material response recorded"; break;
        case TupdTestAction::interact: test.outcome = "interaction hook responded in isolated sandbox"; break;
        case TupdTestAction::unknown: break;
    }
    test.condition_after = instance.condition; instance.test_count += 1; instance.last_action = action_name; instance.last_outcome = test.outcome;
    std::ostringstream material; material << instance.signature << '|' << action_name << '|' << instance.test_count << '|' << test.condition_before << '|' << test.condition_after << '|' << test.outcome;
    test.signature = hex64(fnv1a(material.str())); instance.signature = hex64(fnv1a(instance.signature + "|" + test.signature)); return test;
}

bool write_tupd_receipt_atomic(const std::filesystem::path& path, const TupdReceipt& receipt, std::string* error) {
    try {
        std::filesystem::create_directories(path.parent_path()); const std::filesystem::path temporary = path.string() + ".tmp";
        std::ofstream output(temporary, std::ios::binary | std::ios::trunc); if (!output) throw std::runtime_error("Unable to open Tupd receipt output");
        output << "{\n  \"schema\": \"signalcloud.tupd-receipt\",\n  \"committed\": " << (receipt.committed ? "true" : "false") << ",\n  \"receipt_id\": \"" << escape_json(receipt.receipt_id) << "\",\n  \"recipe_id\": \"" << escape_json(receipt.recipe_id) << "\",\n  \"result_id\": \"" << escape_json(receipt.result_id) << "\",\n  \"xar_before\": " << receipt.xar_before << ",\n  \"xar_after\": " << receipt.xar_after << ",\n  \"condition_before\": " << receipt.condition_before << ",\n  \"condition_after\": " << receipt.condition_after << ",\n  \"signature\": \"" << escape_json(receipt.signature) << "\",\n  \"consumed\": {";
        bool first = true; for (const auto& [id,count] : receipt.consumed) { if (!first) output << ','; output << "\n    \"" << escape_json(id) << "\": " << count; first = false; }
        if (!receipt.consumed.empty()) output << '\n';
        output << "  }\n}\n";
        output.flush();
        if (!output) throw std::runtime_error("Unable to flush Tupd receipt output");
        output.close();
        std::error_code ec; std::filesystem::rename(temporary,path,ec); if (ec) { std::filesystem::remove(path,ec); ec.clear(); std::filesystem::rename(temporary,path,ec); } if (ec) throw std::runtime_error("Unable to promote Tupd receipt: " + ec.message()); return true;
    } catch (const std::exception& exception) { if (error != nullptr) *error = exception.what(); return false; }
}

TupdSandboxSession::TupdSandboxSession() : TupdSandboxSession(make_tupd_test_inventory()) {}
TupdSandboxSession::TupdSandboxSession(TupdInventory inventory) : initial_(std::move(inventory)), inventory_(initial_), normal_save_fingerprint_(initial_.normal_save_fingerprint) {}
bool TupdSandboxSession::normal_save_unchanged() const noexcept { return inventory_.normal_save_fingerprint == normal_save_fingerprint_ && initial_.normal_save_fingerprint == normal_save_fingerprint_; }
TupdPreview TupdSandboxSession::preview(const TupdRecipe& recipe) { preview_ = preview_tupd(recipe, inventory_); return preview_; }
TupdReceipt TupdSandboxSession::commit(const TupdRecipe& recipe) { preview_ = preview_tupd(recipe, inventory_); receipt_ = commit_tupd(recipe, inventory_, preview_); instance_.reset(); last_test_.reset(); tests_.clear(); if (receipt_.committed) instance_ = create_tupd_result_instance(recipe, preview_, receipt_, inventory_); return receipt_; }
bool TupdSandboxSession::equip_or_spawn_result() { return instance_.has_value() && equip_or_spawn_tupd_instance(*instance_); }
TupdInstanceTest TupdSandboxSession::test_result(TupdTestAction action) { TupdInstanceTest result; if (instance_) result = test_tupd_instance(*instance_, action); else result.outcome = "no committed result instance"; last_test_ = result; if (result.accepted) tests_.push_back(result); return result; }
void TupdSandboxSession::clear_result() { instance_.reset(); last_test_.reset(); tests_.clear(); }
void TupdSandboxSession::reset() { inventory_ = initial_; preview_ = {}; receipt_ = {}; clear_result(); }

}  // namespace signalcloud::items
