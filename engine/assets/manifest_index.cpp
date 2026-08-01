#include "engine/assets/manifest_index.hpp"

#include <algorithm>
#include <fstream>
#include <set>
#include <sstream>
#include <stdexcept>

namespace signalcloud::assets {
namespace {

std::vector<std::string> parse_csv_row(const std::string& line) {
    std::vector<std::string> fields;
    std::string field;
    bool quoted = false;
    for (std::size_t i = 0; i < line.size(); ++i) {
        const char ch = line[i];
        if (ch == '"') {
            if (quoted && i + 1 < line.size() && line[i + 1] == '"') {
                field.push_back('"');
                ++i;
            } else {
                quoted = !quoted;
            }
        } else if (ch == ',' && !quoted) {
            fields.push_back(field);
            field.clear();
        } else {
            field.push_back(ch);
        }
    }
    fields.push_back(field);
    return fields;
}

}  // namespace

ManifestIndex ManifestIndex::load_csv(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) {
        throw std::runtime_error("Unable to open manifest: " + path.string());
    }

    ManifestIndex index;
    std::string line;
    bool first = true;
    while (std::getline(input, line)) {
        if (first) {
            first = false;
            continue;
        }
        if (line.empty()) {
            continue;
        }
        const auto fields = parse_csv_row(line);
        if (fields.size() != 9) {
            throw std::runtime_error("Manifest row has the wrong number of columns.");
        }
        ManifestRecord record;
        record.asset_id = fields[0];
        record.asset_type = fields[1];
        record.family = fields[2];
        record.pack = fields[3];
        record.relative_path = fields[4];
        record.size_bytes = static_cast<std::uintmax_t>(std::stoull(fields[5]));
        record.sha256 = fields[6];
        record.enabled = fields[8] == "true";
        index.records_.push_back(std::move(record));
    }
    return index;
}

std::vector<std::string> ManifestIndex::validate() const {
    std::vector<std::string> errors;
    std::set<std::string> paths;
    for (const ManifestRecord& record : records_) {
        if (record.asset_id.empty()) {
            errors.emplace_back("Manifest record has no asset_id: " + record.relative_path.string());
        }
        if (record.sha256.size() != 64) {
            errors.emplace_back("Invalid SHA-256 length: " + record.relative_path.string());
        }
        if (!paths.insert(record.relative_path.generic_string()).second) {
            errors.emplace_back("Duplicate manifest path: " + record.relative_path.string());
        }
    }
    return errors;
}

}  // namespace signalcloud::assets
