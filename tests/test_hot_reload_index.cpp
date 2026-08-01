#include "engine/assets/hot_reload_index.hpp"

#include <filesystem>
#include <fstream>
#include <string>

int main() {
    namespace fs = std::filesystem;
    const fs::path root = fs::temp_directory_path() / "signalcloud_hot_reload_a3a1";
    fs::remove_all(root);
    fs::create_directories(root / "content/user/lights");
    fs::create_directories(root / "user_data/studio");
    std::ofstream(root / "content/user/lights/demo.slight") << "{}\n";
    std::ofstream out(root / "user_data/studio/hot_reload_candidates.udata");
    out << "@udata 1\n\n[index]\n"
        << "schema_name: \"signalcloud.hot-reload-index\";\n"
        << "mode: \"protected-authoring-only\";\nentry_count: 1;\n\n"
        << "[asset.0]\nasset_id: \"user.lights.demo\";\n"
        << "relative_path: \"content/user/lights/demo.slight\";\n"
        << "sha256: \"0123456789012345678901234567890123456789012345678901234567890123\";\n"
        << "asset_type: \"light_set\";\nsession_scope: \"authoring-preview\";\n";
    out.close();
    const auto index = signalcloud::assets::HotReloadIndex::load(
        root, root / "user_data/studio/hot_reload_candidates.udata");
    if (!index.valid() || index.entries().size() != 1U) return 1;
    if (index.entries().front().asset_id != "user.lights.demo") return 2;

    std::ofstream bad(root / "user_data/studio/bad.udata");
    bad << "@udata 1\n\n[index]\nschema_name: \"signalcloud.hot-reload-index\";\n"
        << "mode: \"normal-game\";\n\n[asset.0]\nasset_id: \"bad\";\n"
        << "relative_path: \"../outside.slight\";\n"
        << "sha256: \"0123456789012345678901234567890123456789012345678901234567890123\";\n";
    bad.close();
    const auto rejected = signalcloud::assets::HotReloadIndex::load(root, root / "user_data/studio/bad.udata");
    if (rejected.valid()) return 3;
    fs::remove_all(root);
    return 0;
}
