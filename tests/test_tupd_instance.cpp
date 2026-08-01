#include "engine/items/tupd_runtime.hpp"

#include <filesystem>
#include <iostream>
#include <string>

namespace {
int fail(std::string_view message) {
    std::cerr << "Tupd result instance test failure: " << message << '\n';
    return 1;
}
}

int main(int argc, char** argv) {
    namespace fs = std::filesystem;
    const fs::path root = argc > 1 ? fs::path(argv[1]) : fs::current_path();
    std::string error;

    signalcloud::items::TupdRecipe weapon_recipe;
    if (!signalcloud::items::load_tupd_recipe(
            root / "content/starter/tupd/compatible_signal_grip/compatible_signal_grip.tupd",
            weapon_recipe, &error)) return fail(error);
    if (weapon_recipe.recipe_revision != 1 || weapon_recipe.test_actions.size() < 5U ||
        weapon_recipe.result.sockets.empty() || weapon_recipe.result.tags.empty()) {
        return fail("A8a2 recipe revision/socket/test contract");
    }

    signalcloud::items::TupdSandboxSession sandbox;
    const auto preview = sandbox.preview(weapon_recipe);
    const auto comparison = signalcloud::items::compare_tupd_result(preview);
    if (!preview.valid || comparison.weight_after <= comparison.weight_before ||
        comparison.added_sockets.empty()) return fail("before/after comparison evidence");
    const auto receipt = sandbox.commit(weapon_recipe);
    if (!receipt.committed || !sandbox.result_instance() ||
        signalcloud::items::tupd_instance_state(*sandbox.result_instance()) != "COMMITTED / NOT EQUIPPED") {
        return fail("commit creates explicit not-equipped result");
    }
    const auto blocked_test = sandbox.test_result(signalcloud::items::TupdTestAction::inspect);
    if (blocked_test.accepted) return fail("test must require equip/spawn");
    if (!sandbox.equip_or_spawn_result() || !sandbox.result_instance()->equipped ||
        sandbox.result_instance()->spawned) return fail("weapon result equips explicitly");
    const auto inspect = sandbox.test_result(signalcloud::items::TupdTestAction::inspect);
    const auto primary = sandbox.test_result(signalcloud::items::TupdTestAction::primary);
    if (!inspect.accepted || !primary.accepted || inspect.signature == primary.signature ||
        sandbox.result_instance()->test_count != 2) return fail("declared tests are distinct and counted");

    const fs::path instance_path = fs::temp_directory_path() / "signalcloud_a8a2_result.tupdinstance";
    if (!signalcloud::items::save_tupd_instance_atomic(instance_path, *sandbox.result_instance(), &error)) return fail(error);
    signalcloud::items::TupdResultInstance reloaded;
    if (!signalcloud::items::load_tupd_instance(instance_path, reloaded, &error)) return fail(error);
    fs::remove(instance_path);
    if (reloaded.instance_id != sandbox.result_instance()->instance_id || !reloaded.equipped ||
        reloaded.test_count != 2 || reloaded.sockets.empty()) return fail("instance round trip");

    signalcloud::items::TupdRecipe barrier_recipe;
    if (!signalcloud::items::load_tupd_recipe(
            root / "content/starter/tupd/office_barrier/office_barrier.tupd",
            barrier_recipe, &error)) return fail(error);
    signalcloud::items::TupdSandboxSession barrier;
    (void)barrier.preview(barrier_recipe);
    if (!barrier.commit(barrier_recipe).committed || !barrier.equip_or_spawn_result() ||
        !barrier.result_instance()->spawned || barrier.result_instance()->equipped) {
        return fail("object result spawns explicitly");
    }
    const auto collision = barrier.test_result(signalcloud::items::TupdTestAction::collision);
    const auto interact = barrier.test_result(signalcloud::items::TupdTestAction::interact);
    if (!collision.accepted || !interact.accepted) return fail("object declared tests");
    if (!barrier.normal_save_unchanged()) return fail("result testing touched normal save");

    std::cout << "A8a2 Tupd result instance: commit/equip-spawn/test/export contract PASS\n";
    return 0;
}
