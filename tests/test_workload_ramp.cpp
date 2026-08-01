#include "engine/benchmark/workload_ramp.hpp"

#include <cassert>
#include <filesystem>
#include <fstream>
#include <set>

int main(int argc, char** argv) {
    namespace fs = std::filesystem;
    using namespace signalcloud::benchmark;

    const fs::path root = argc > 1 ? fs::path(argv[1]) : fs::current_path();
    const auto shipped = load_workload_registry(root / "user_data/machine_profiles/workload_registry.udata");
    assert(shipped.valid);
    assert(shipped.enabled_asset_count > 0U);
    assert(!shipped.registry_sha256.empty());

    const auto ramps = build_workload_ramps(shipped);
    assert(!ramps.empty());
    std::set<WorkloadAxis> axes;
    for (const auto& point : ramps) {
        assert(point.axis != WorkloadAxis::none);
        assert(point.level >= 1U);
        assert(point.step >= 1U);
        assert(point.step <= point.step_count);
        assert(!point.label.empty());
        axes.insert(point.axis);
    }
    assert(axes.size() == 7U);

    WorkloadRegistrySnapshot synthetic;
    synthetic.valid = true;
    synthetic.registry_sha256 = "fixture";
    synthetic.feature_channels["lights"] = 12U;
    synthetic.feature_channels["materials"] = 8U;
    synthetic.feature_channels["sound_ripples"] = 9U;
    synthetic.feature_channels["content_enemy"] = 4U;
    synthetic.feature_channels["playbook_evaluations"] = 10U;
    synthetic.feature_channels["tupd_test_objects"] = 24U;
    synthetic.feature_channels["scui_panels"] = 6U;
    const auto first = build_workload_ramps(synthetic);
    const auto second = build_workload_ramps(synthetic);
    assert(first.size() == second.size());
    for (std::size_t i = 0; i < first.size(); ++i) {
        assert(first[i].axis == second[i].axis);
        assert(first[i].level == second[i].level);
        assert(first[i].label == second[i].label);
    }
    return 0;
}
