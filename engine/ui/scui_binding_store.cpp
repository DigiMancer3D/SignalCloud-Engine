#include "engine/ui/scui_binding_store.hpp"

#include "engine/data/udata.hpp"

#include <filesystem>
#include <stdexcept>

namespace signalcloud::ui {

ScuiNativeBindingStore::ScuiNativeBindingStore(
    std::filesystem::path path, std::string source_document)
    : path_(std::move(path)), source_document_(std::move(source_document)) {}

bool ScuiNativeBindingStore::load(ScuiNativeRuntime& runtime, std::string* error) const {
    try {
        if (!std::filesystem::exists(path_)) return true;
        const auto document = data::UDataDocument::load(path_);
        if (document.has_errors()) throw std::runtime_error("native SCUI binding state contains errors");
        std::map<std::string, std::string, std::less<>> values;
        for (const auto& entry : document.entries()) {
            if (entry.section == "state") values[entry.key] = entry.raw_json;
        }
        runtime.apply_state_json(values);
        return true;
    } catch (const std::exception& exc) {
        if (error != nullptr) *error = exc.what();
        return false;
    }
}

bool ScuiNativeBindingStore::save(const ScuiNativeRuntime& runtime, std::string* error) const {
    try {
        data::UDataDocument document;
        document.set("panel", "panel_id", "\"" + runtime.panel().panel_id + "\"");
        document.set("panel", "source_document", "\"" + source_document_ + "\"");
        document.set("panel", "mode", "\"protected-native-overlay\"");
        for (const auto& [binding, raw] : runtime.state_json()) {
            document.set("state", binding, raw);
        }
        std::filesystem::create_directories(path_.parent_path());
        return document.save_atomic(path_, error);
    } catch (const std::exception& exc) {
        if (error != nullptr) *error = exc.what();
        return false;
    }
}

}  // namespace signalcloud::ui
