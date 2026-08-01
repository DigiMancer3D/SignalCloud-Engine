#include "engine/lighting/illuminosity_bake.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <system_error>

namespace signalcloud::lighting {
namespace {

std::uint64_t fnv1a(std::uint64_t hash, std::uint64_t value) noexcept {
    hash ^= value;
    hash *= 1099511628211ULL;
    return hash;
}

std::uint64_t quantized(float value) noexcept {
    if (!std::isfinite(value)) return 0U;
    return static_cast<std::uint64_t>(std::llround(static_cast<double>(value) * 10000.0));
}

std::string json_escape(std::string_view text) {
    std::ostringstream out;
    for (const unsigned char ch : text) {
        switch (ch) {
        case '"': out << "\\\""; break;
        case '\\': out << "\\\\"; break;
        case '\n': out << "\\n"; break;
        case '\r': out << "\\r"; break;
        case '\t': out << "\\t"; break;
        default:
            if (ch < 0x20U) {
                out << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                    << static_cast<unsigned int>(ch) << std::dec;
            } else {
                out << static_cast<char>(ch);
            }
        }
    }
    return out.str();
}

bool inside_root(const std::filesystem::path& root, const std::filesystem::path& path) {
    const auto canonical_root = std::filesystem::weakly_canonical(root);
    const auto canonical_path = std::filesystem::weakly_canonical(path);
    auto root_it = canonical_root.begin();
    auto path_it = canonical_path.begin();
    for (; root_it != canonical_root.end(); ++root_it, ++path_it) {
        if (path_it == canonical_path.end() || *root_it != *path_it) return false;
    }
    return true;
}

}  // namespace

IlluminosityBakeSummary bake_illuminosity_grid(
    const IlluminosityRuntime& runtime, const IlluminosityBakeRequest& raw_request) {
    IlluminosityBakeSummary summary;
    summary.request = raw_request;
    summary.request.grid_size = std::clamp<std::size_t>(raw_request.grid_size, 3U, 33U);
    if ((summary.request.grid_size % 2U) == 0U) ++summary.request.grid_size;
    summary.request.spacing = std::clamp(raw_request.spacing, 0.1F, 20.0F);
    summary.samples.reserve(summary.request.grid_size * summary.request.grid_size);

    float minimum = std::numeric_limits<float>::max();
    float maximum = 0.0F;
    double total = 0.0;
    std::uint64_t signature = 1469598103934665603ULL;
    signature = fnv1a(signature, runtime.stats().deterministic_signature);
    signature = fnv1a(signature, summary.request.grid_size);
    signature = fnv1a(signature, quantized(summary.request.spacing));
    for (const unsigned char c : summary.request.zone) signature = fnv1a(signature, c);

    const int half = static_cast<int>(summary.request.grid_size / 2U);
    for (int z = -half; z <= half; ++z) {
        for (int x = -half; x <= half; ++x) {
            const math::Vec3 position{
                summary.request.center.x + static_cast<float>(x) * summary.request.spacing,
                summary.request.center.y,
                summary.request.center.z + static_cast<float>(z) * summary.request.spacing,
            };
            const auto probe = runtime.probe_surface(position, summary.request.zone);
            IlluminosityBakeSample sample;
            sample.position = position;
            sample.illuminosity_percent = probe.effective_illuminosity_percent;
            sample.visibility = probe.visibility;
            sample.contributing_lights = probe.contributing_lights;
            sample.quality_band = probe.quality_band;
            summary.samples.push_back(sample);
            minimum = std::min(minimum, sample.illuminosity_percent);
            maximum = std::max(maximum, sample.illuminosity_percent);
            total += sample.illuminosity_percent;
            if (sample.illuminosity_percent >= 45.0F) ++summary.readable_samples;
            if (sample.illuminosity_percent <= 3.0F) ++summary.dark_samples;
            signature = fnv1a(signature, quantized(position.x));
            signature = fnv1a(signature, quantized(position.y));
            signature = fnv1a(signature, quantized(position.z));
            signature = fnv1a(signature, quantized(sample.illuminosity_percent));
            signature = fnv1a(signature, sample.contributing_lights);
        }
    }
    if (summary.samples.empty()) minimum = 0.0F;
    summary.minimum_illuminosity_percent = minimum;
    summary.maximum_illuminosity_percent = maximum;
    summary.average_illuminosity_percent = summary.samples.empty()
        ? 0.0F : static_cast<float>(total / static_cast<double>(summary.samples.size()));
    summary.deterministic_signature = signature;
    return summary;
}

bool write_illuminosity_bake_report(
    const std::filesystem::path& project_root,
    const std::filesystem::path& output_path,
    const IlluminosityRuntime& runtime,
    const IlluminosityBakeSummary& summary,
    std::string* error) {
    try {
        const auto root = std::filesystem::weakly_canonical(project_root);
        const auto output = output_path.is_absolute() ? output_path : root / output_path;
        if (!inside_root(root, output)) {
            if (error != nullptr) *error = "Illuminosity bake report must remain inside the project root.";
            return false;
        }
        std::filesystem::create_directories(output.parent_path());
        const auto temporary = std::filesystem::path(output.string() + ".tmp");
        std::ofstream stream(temporary, std::ios::trunc);
        if (!stream) {
            if (error != nullptr) *error = "Unable to open temporary Illuminosity bake report.";
            return false;
        }
        stream << std::fixed << std::setprecision(6);
        stream << "{\n"
               << "  \"schema\": \"signalcloud_illuminosity_bake_v1\",\n"
               << "  \"source_document\": \"" << json_escape(runtime.stats().source_document) << "\",\n"
               << "  \"zone\": \"" << json_escape(summary.request.zone) << "\",\n"
               << "  \"grid_size\": " << summary.request.grid_size << ",\n"
               << "  \"spacing\": " << summary.request.spacing << ",\n"
               << "  \"sample_count\": " << summary.samples.size() << ",\n"
               << "  \"minimum_illuminosity_percent\": " << summary.minimum_illuminosity_percent << ",\n"
               << "  \"maximum_illuminosity_percent\": " << summary.maximum_illuminosity_percent << ",\n"
               << "  \"average_illuminosity_percent\": " << summary.average_illuminosity_percent << ",\n"
               << "  \"readable_samples\": " << summary.readable_samples << ",\n"
               << "  \"dark_samples\": " << summary.dark_samples << ",\n"
               << "  \"runtime_signature\": " << runtime.stats().deterministic_signature << ",\n"
               << "  \"deterministic_signature\": " << summary.deterministic_signature << ",\n"
               << "  \"samples\": [\n";
        for (std::size_t index = 0U; index < summary.samples.size(); ++index) {
            const auto& sample = summary.samples[index];
            stream << "    {\"position\":[" << sample.position.x << ',' << sample.position.y << ','
                   << sample.position.z << "],\"illuminosity_percent\":"
                   << sample.illuminosity_percent << ",\"visibility\":" << sample.visibility
                   << ",\"contributing_lights\":" << sample.contributing_lights
                   << ",\"quality_band\":\"" << json_escape(sample.quality_band) << "\"}"
                   << (index + 1U == summary.samples.size() ? "\n" : ",\n");
        }
        stream << "  ]\n}\n";
        stream.close();
        if (!stream) {
            std::filesystem::remove(temporary);
            if (error != nullptr) *error = "Unable to finish Illuminosity bake report.";
            return false;
        }
        std::error_code ec;
        std::filesystem::rename(temporary, output, ec);
        if (ec) {
            std::filesystem::remove(output, ec);
            ec.clear();
            std::filesystem::rename(temporary, output, ec);
        }
        if (ec) {
            std::filesystem::remove(temporary);
            if (error != nullptr) *error = ec.message();
            return false;
        }
        return true;
    } catch (const std::exception& ex) {
        if (error != nullptr) *error = ex.what();
        return false;
    }
}

}  // namespace signalcloud::lighting
