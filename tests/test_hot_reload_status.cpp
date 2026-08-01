#include "engine/assets/hot_reload_status.hpp"

#include <filesystem>
#include <fstream>

int main() {
    namespace fs = std::filesystem;
    const fs::path root = fs::temp_directory_path() / "signalcloud_hot_reload_status_a5a3r2";
    fs::remove_all(root);
    fs::create_directories(root / "content/core/ui");
    fs::create_directories(root / "content/user/lights");
    fs::create_directories(root / "content/user/materials");
    fs::create_directories(root / "content/user/audio");
    fs::create_directories(root / "content/user/fonts");
    fs::create_directories(root / "content/pcp3_assets/environment_object/demo");
    fs::create_directories(root / "user_data/studio/hot_reload/pcp3");
    fs::create_directories(root / "user_data/studio/hot_reload/illuminosity");
    fs::create_directories(root / "user_data/studio/hot_reload/materials");
    fs::create_directories(root / "user_data/studio/hot_reload/audio");
    fs::create_directories(root / "user_data/studio/hot_reload/fonts");
    std::ofstream(root / "content/core/ui/demo.scui") << "@udata 1\n";
    std::ofstream(root / "content/user/lights/demo.slight") << "{}\n";
    std::ofstream(root / "content/user/materials/demo.jmap") << "{}\n";
    std::ofstream(root / "content/user/audio/demo.scaudio") << "{}\n";
    std::ofstream(root / "content/user/fonts/demo.scfont") << "SCFONT 1\n";
    std::ofstream(root / "content/pcp3_assets/environment_object/demo/demo.pcp3") << "{}\n";
    std::ofstream(root / "user_data/studio/hot_reload/light.udata") << "@udata 1\n";
    std::ofstream(root / "user_data/studio/hot_reload/illuminosity/light.udata") << "@udata 1\n";
    std::ofstream(root / "user_data/studio/hot_reload/materials/demo.udata") << "@udata 1\n";
    std::ofstream(root / "user_data/studio/hot_reload/audio/demo.udata") << "@udata 1\n";
    std::ofstream(root / "user_data/studio/hot_reload/fonts/demo.scfont") << "SCFONT 1\n";
    std::ofstream(root / "user_data/studio/hot_reload/pcp3/demo.udata") << "@udata 1\n";

    std::ofstream out(root / "user_data/studio/hot_reload_latest.udata");
    out << "@udata 1\n\n[status]\n"
        << "schema_name: \"signalcloud.hot-reload-status\";\n"
        << "mode: \"protected-authoring-preview\";\n"
        << "transaction_id: \"abc123def4567890\";\n"
        << "generated_unix: 1234;\nchanged_count: 6;\n\n"
        << "[asset.0]\nasset_id: \"ui.demo\";\n"
        << "relative_path: \"content/core/ui/demo.scui\";\nasset_type: \"scui\";\n"
        << "indexed_sha256: \"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\";\n"
        << "observed_sha256: \"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\";\n"
        << "status: \"changed\";\nstaged_state_path: \"\";\n"
        << "compiled_runtime_path: \"\";\n"
        << "companion_sha256: \"\";\npoint_count: 0;\n\n"
        << "[asset.1]\nasset_id: \"light.demo\";\n"
        << "relative_path: \"content/user/lights/demo.slight\";\nasset_type: \"light_set\";\n"
        << "indexed_sha256: \"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\";\n"
        << "observed_sha256: \"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\";\n"
        << "status: \"changed\";\n"
        << "staged_state_path: \"user_data/studio/hot_reload/light.udata\";\n"
        << "compiled_runtime_path: \"user_data/studio/hot_reload/illuminosity/light.udata\";\n"
        << "companion_sha256: \"\";\npoint_count: 0;\n\n"
        << "[asset.2]\nasset_id: \"pcp3.demo\";\n"
        << "relative_path: \"content/pcp3_assets/environment_object/demo/demo.pcp3\";\n"
        << "asset_type: \"pcp3_project\";\n"
        << "indexed_sha256: \"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\";\n"
        << "observed_sha256: \"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff\";\n"
        << "status: \"changed\";\n"
        << "staged_state_path: \"user_data/studio/hot_reload/pcp3/demo.udata\";\n"
        << "compiled_runtime_path: \"\";\n"
        << "companion_sha256: \"1111111111111111111111111111111111111111111111111111111111111111\";\n"
        << "point_count: 22;\n\n"
        << "[asset.3]\nasset_id: \"material.demo\";\n"
        << "relative_path: \"content/user/materials/demo.jmap\";\nasset_type: \"jitter_map\";\n"
        << "indexed_sha256: \"2222222222222222222222222222222222222222222222222222222222222222\";\n"
        << "observed_sha256: \"3333333333333333333333333333333333333333333333333333333333333333\";\n"
        << "status: \"changed\";\nstaged_state_path: \"\";\n"
        << "compiled_runtime_path: \"user_data/studio/hot_reload/materials/demo.udata\";\n"
        << "companion_sha256: \"\";\npoint_count: 0;\n\n"
        << "[asset.4]\nasset_id: \"audio.demo\";\n"
        << "relative_path: \"content/user/audio/demo.scaudio\";\nasset_type: \"audio_interference_profile\";\n"
        << "indexed_sha256: \"4444444444444444444444444444444444444444444444444444444444444444\";\n"
        << "observed_sha256: \"5555555555555555555555555555555555555555555555555555555555555555\";\n"
        << "status: \"changed\";\nstaged_state_path: \"\";\n"
        << "compiled_runtime_path: \"user_data/studio/hot_reload/audio/demo.udata\";\n"
        << "companion_sha256: \"\";\npoint_count: 0;\n\n"
        << "[asset.5]\nasset_id: \"font.demo\";\n"
        << "relative_path: \"content/user/fonts/demo.scfont\";\nasset_type: \"signalcloud_font\";\n"
        << "indexed_sha256: \"6666666666666666666666666666666666666666666666666666666666666666\";\n"
        << "observed_sha256: \"7777777777777777777777777777777777777777777777777777777777777777\";\n"
        << "status: \"changed\";\nstaged_state_path: \"user_data/studio/hot_reload/fonts/demo.scfont\";\n"
        << "compiled_runtime_path: \"\";\n"
        << "companion_sha256: \"\";\npoint_count: 0;\n";
    out.close();

    const auto status = signalcloud::assets::HotReloadStatus::load(
        root, root / "user_data/studio/hot_reload_latest.udata");
    if (!status.valid()) return 1;
    if (status.generated_unix() != 1234U || status.changed_count() != 6U) return 2;
    if (status.transaction_id() != "abc123def4567890") return 3;
    if (status.changed_scui_count() != 1U || status.changed_light_count() != 1U ||
        status.changed_pcp3_count() != 1U || status.changed_material_count() != 1U ||
        status.changed_audio_count() != 1U || status.changed_font_count() != 1U) return 4;
    if (status.changed_for_path("content/core/ui/demo.scui") == nullptr) return 5;
    const auto* light = status.changed_light_set();
    if (light == nullptr || light->staged_state_path.empty() || light->compiled_runtime_path.empty()) return 6;
    const auto pcp3 = status.changed_pcp3_projects();
    if (pcp3.size() != 1U || pcp3.front()->point_count != 22U) return 7;
    const auto* material = status.changed_material_set();
    if (material == nullptr || material->compiled_runtime_path.empty()) return 8;
    const auto* audio = status.changed_audio_profile();
    if (audio == nullptr || audio->compiled_runtime_path.empty()) return 9;
    const auto* font = status.changed_font();
    if (font == nullptr || font->staged_state_path.empty()) return 10;

    std::ofstream bad(root / "user_data/studio/bad_status.udata");
    bad << "@udata 1\n\n[status]\nschema_name: \"signalcloud.hot-reload-status\";\n"
        << "mode: \"protected-authoring-preview\";\n\n[asset.0]\nasset_id: \"bad\";\n"
        << "relative_path: \"content/user/materials/demo.jmap\";\n"
        << "asset_type: \"jitter_map\";\nstatus: \"changed\";\n"
        << "observed_sha256: \"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\";\n"
        << "compiled_runtime_path: \"\";\n";
    bad.close();
    const auto rejected = signalcloud::assets::HotReloadStatus::load(
        root, root / "user_data/studio/bad_status.udata");
    if (rejected.valid()) return 11;
    fs::remove_all(root);
    return 0;
}
