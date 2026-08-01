#pragma once

#include "engine/ui/scui_native_runtime.hpp"

#include <filesystem>
#include <string>
#include <string_view>

namespace signalcloud::ui {

class ScuiNativeBindingStore {
public:
    ScuiNativeBindingStore(std::filesystem::path path, std::string source_document);

    [[nodiscard]] const std::filesystem::path& path() const noexcept { return path_; }
    [[nodiscard]] std::string_view source_document() const noexcept { return source_document_; }

    bool load(ScuiNativeRuntime& runtime, std::string* error = nullptr) const;
    bool save(const ScuiNativeRuntime& runtime, std::string* error = nullptr) const;

private:
    std::filesystem::path path_;
    std::string source_document_;
};

}  // namespace signalcloud::ui
