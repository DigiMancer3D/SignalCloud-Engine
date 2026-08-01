#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <string_view>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace signalcloud::ai {

inline constexpr std::size_t kMaxPlaybookGraphs = 32U;
inline constexpr std::size_t kMaxPlaybookNodes = 64U;
inline constexpr std::size_t kMaxPlaybookEdges = 96U;
inline constexpr std::size_t kMaxPlaybookSteps = 64U;

struct PlaybookNode {
    std::string id;
    std::string kind;
    std::string operation;
    std::string target;
    std::uint32_t timeout_ms{0U};
    std::uint32_t cooldown_ms{0U};
    std::string bone;
};

struct PlaybookEdge {
    std::size_t source{0U};
    std::size_t destination{0U};
    std::string branch;
    std::string condition;
    std::uint8_t priority{0U};
};

struct PlaybookGraph {
    std::string id;
    std::string mode;
    std::string subject_kind;
    std::string subject_archetype;
    std::string entry;
    std::size_t max_steps{1U};
    std::size_t max_depth{1U};
    std::size_t point_budget_cost{0U};
    std::string signature;
    std::string source;
    std::vector<PlaybookNode> nodes;
    std::vector<PlaybookEdge> edges;
};

struct PlaybookRuntimeStats {
    std::size_t graph_count{0U};
    std::size_t node_count{0U};
    std::size_t edge_count{0U};
    std::size_t point_budget_cost{0U};
    std::string signature;
    std::size_t warning_count{0U};
};

struct PlaybookContext {
    std::string event;
    std::unordered_set<std::string> true_conditions;
};

struct PlaybookTraceStep {
    std::string node_id;
    std::string kind;
    std::string operation;
    std::string target;
};

class PlaybookRuntime {
public:
    static PlaybookRuntime load(const std::filesystem::path& path);

    [[nodiscard]] const PlaybookRuntimeStats& stats() const noexcept { return stats_; }
    [[nodiscard]] const std::vector<PlaybookGraph>& graphs() const noexcept { return graphs_; }
    [[nodiscard]] const PlaybookGraph* find(std::string_view id) const noexcept;
    [[nodiscard]] std::vector<PlaybookTraceStep> evaluate(
        std::string_view id, const PlaybookContext& context,
        std::size_t maximum_steps = kMaxPlaybookSteps) const;
    [[nodiscard]] bool valid() const noexcept;

private:
    std::vector<PlaybookGraph> graphs_;
    PlaybookRuntimeStats stats_;
};

}  // namespace signalcloud::ai
