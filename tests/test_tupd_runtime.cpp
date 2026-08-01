#include "engine/items/tupd_runtime.hpp"

#include <filesystem>
#include <iostream>
#include <string>

namespace {
int fail(std::string_view message) {
    std::cerr << "Tupd runtime test failure: " << message << '\n';
    return 1;
}
}

int main(int argc, char** argv) {
    namespace fs = std::filesystem;
    const fs::path root = argc > 1 ? fs::path(argv[1]) : fs::current_path();

    signalcloud::items::TupdRecipe compatible;
    std::string error;
    if (!signalcloud::items::load_tupd_recipe(
            root / "content/starter/tupd/compatible_signal_grip/compatible_signal_grip.tupd",
            compatible, &error)) {
        return fail(error);
    }
    auto inventory = signalcloud::items::make_tupd_test_inventory();
    const auto preview = signalcloud::items::preview_tupd(compatible, inventory);
    if (!preview.valid || preview.forced || preview.point_budget != 1800U) {
        return fail("compatible modification preview contract");
    }
    const int tapes_before = inventory.items["consumable.tupd-tape"];
    const auto receipt = signalcloud::items::commit_tupd(compatible, inventory, preview);
    if (!receipt.committed || inventory.items["consumable.tupd-tape"] != tapes_before - 1 ||
        inventory.items["part.signal-grip"] != 1 || receipt.receipt_id.empty()) {
        return fail("compatible modification atomic commit");
    }

    signalcloud::items::TupdRecipe forced;
    if (!signalcloud::items::load_tupd_recipe(
            root / "content/starter/tupd/forced_office_bracket/forced_office_bracket.tupd",
            forced, &error)) {
        return fail(error);
    }
    const auto forced_preview = signalcloud::items::preview_tupd(
        forced, signalcloud::items::make_tupd_test_inventory());
    if (!forced_preview.valid || !forced_preview.forced || forced_preview.warnings.empty() ||
        forced_preview.stability_percent >= 100.0F) {
        return fail("forced connection preview penalties");
    }

    signalcloud::items::TupdRecipe full_repair;
    if (!signalcloud::items::load_tupd_recipe(
            root / "content/starter/tupd/full_repair/full_repair.tupd",
            full_repair, &error)) {
        return fail(error);
    }
    auto repair_inventory = signalcloud::items::make_tupd_test_inventory();
    const auto repair_preview = signalcloud::items::preview_tupd(full_repair, repair_inventory);
    const auto repair_receipt = signalcloud::items::commit_tupd(
        full_repair, repair_inventory, repair_preview);
    if (!repair_receipt.committed || repair_inventory.weapon_condition != 100.0F ||
        repair_inventory.items["weapon.service-pistol.duplicate"] != 0) {
        return fail("matching duplicate full repair");
    }

    auto rejected_inventory = signalcloud::items::make_tupd_test_inventory();
    rejected_inventory.items["consumable.tupd-tape"] = 0;
    const auto before = rejected_inventory.items;
    const auto rejected_preview = signalcloud::items::preview_tupd(compatible, rejected_inventory);
    const auto rejected_receipt = signalcloud::items::commit_tupd(
        compatible, rejected_inventory, rejected_preview);
    if (rejected_preview.valid || rejected_receipt.committed || rejected_inventory.items != before) {
        return fail("failed validation consumes nothing");
    }

    signalcloud::items::TupdSandboxSession sandbox;
    (void)sandbox.preview(compatible);
    (void)sandbox.commit(compatible);
    if (!sandbox.normal_save_unchanged()) return fail("sandbox changed normal save fingerprint");

    const fs::path temporary = fs::temp_directory_path() / "signalcloud_a8a1_roundtrip.tupd";
    if (!signalcloud::items::save_tupd_recipe_atomic(temporary, compatible, &error)) return fail(error);
    signalcloud::items::TupdRecipe reloaded;
    if (!signalcloud::items::load_tupd_recipe(temporary, reloaded, &error)) return fail(error);
    fs::remove(temporary);
    if (reloaded.recipe_id != compatible.recipe_id ||
        reloaded.result.result_id != compatible.result.result_id ||
        reloaded.connections != compatible.connections) {
        return fail("recipe round trip changed contract");
    }

    const auto discovered = signalcloud::items::discover_tupd_recipes(root);
    if (discovered.size() < 5U) return fail("starter recipe discovery");

    std::cout << "A8a1 Tupd runtime: shared recipe + atomic sandbox transaction PASS\n";
    return 0;
}
