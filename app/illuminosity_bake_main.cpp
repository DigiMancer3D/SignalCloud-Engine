#include "engine/lighting/illuminosity_bake.hpp"
#include "engine/lighting/illuminosity_runtime.hpp"

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <string>

namespace {

struct Options {
    std::filesystem::path root{std::filesystem::current_path()};
    std::filesystem::path sidecar{"user_data/studio/illuminosity_runtime.udata"};
    std::filesystem::path output{"reports/illuminosity_bake_report.json"};
    std::string zone{"Reception Tape"};
    std::size_t grid{7U};
    float spacing{1.5F};
    float height{1.5F};
};

Options parse(int argc, char** argv) {
    Options options;
    bool root_set = false;
    for (int index = 1; index < argc; ++index) {
        const std::string value = argv[index];
        const auto next = [&]() -> std::string {
            if (index + 1 >= argc) throw std::runtime_error("missing value after " + value);
            return argv[++index];
        };
        if (value == "--sidecar") options.sidecar = next();
        else if (value == "--output") options.output = next();
        else if (value == "--zone") options.zone = next();
        else if (value == "--grid") options.grid = static_cast<std::size_t>(std::stoul(next()));
        else if (value == "--spacing") options.spacing = std::stof(next());
        else if (value == "--height") options.height = std::stof(next());
        else if (!root_set && !value.starts_with('-')) { options.root = value; root_set = true; }
        else throw std::runtime_error("unsupported argument: " + value);
    }
    options.root = std::filesystem::absolute(options.root).lexically_normal();
    if (!options.sidecar.is_absolute()) options.sidecar = options.root / options.sidecar;
    if (!options.output.is_absolute()) options.output = options.root / options.output;
    return options;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const Options options = parse(argc, argv);
        signalcloud::lighting::IlluminosityRuntime runtime(options.root, options.sidecar);
        std::string error;
        if (!runtime.reload(&error)) {
            std::cerr << "Illuminosity bake failed to load runtime: " << error << '\n';
            return 2;
        }
        signalcloud::lighting::IlluminosityBakeRequest request;
        request.center = {0.0F, options.height, 0.0F};
        request.zone = options.zone;
        request.grid_size = options.grid;
        request.spacing = options.spacing;
        const auto summary = signalcloud::lighting::bake_illuminosity_grid(runtime, request);
        if (!signalcloud::lighting::write_illuminosity_bake_report(
                options.root, options.output, runtime, summary, &error)) {
            std::cerr << "Illuminosity bake report failed: " << error << '\n';
            return 3;
        }
        std::cout << "Illuminosity bake: " << summary.samples.size() << " samples | min "
                  << summary.minimum_illuminosity_percent << " | avg "
                  << summary.average_illuminosity_percent << " | max "
                  << summary.maximum_illuminosity_percent << " | readable "
                  << summary.readable_samples << " | dark " << summary.dark_samples
                  << " | signature " << summary.deterministic_signature << '\n';
        std::cout << options.output << '\n';
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "Illuminosity bake failed: " << ex.what() << '\n';
        return 1;
    }
}
