#include "engine/ai/playbook.hpp"

#include <algorithm>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace signalcloud::ai {
namespace {

std::size_t bounded_size(std::string_view token, std::size_t maximum, std::string_view field) {
    std::size_t value = 0U;
    try {
        value = static_cast<std::size_t>(std::stoull(std::string(token)));
    } catch (const std::exception&) {
        throw std::runtime_error(std::string(field) + " is not an integer");
    }
    if (value > maximum) throw std::runtime_error(std::string(field) + " exceeds its bound");
    return value;
}

std::uint32_t bounded_u32(std::string_view token, std::uint32_t maximum, std::string_view field) {
    const std::size_t value = bounded_size(token, maximum, field);
    return static_cast<std::uint32_t>(value);
}

bool condition_true(std::string_view name, const PlaybookContext& context) {
    return name == "always" || context.true_conditions.contains(std::string(name));
}

bool edge_true(const PlaybookEdge& edge, const PlaybookContext& context) {
    if (edge.branch == "always" || edge.branch == "complete") return true;
    if (edge.branch == "timeout") return condition_true("timer.expired", context);
    if (edge.branch == "condition") return condition_true(edge.condition, context);
    if (edge.branch == "event") return context.event == edge.condition;
    return false;
}

}  // namespace

PlaybookRuntime PlaybookRuntime::load(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("unable to open playbook runtime: " + path.string());

    PlaybookRuntime runtime;
    std::string line;
    if (!std::getline(input, line) || line != "SCPLAY_RUNTIME 1") {
        throw std::runtime_error("unsupported playbook runtime header");
    }
    std::unordered_map<std::size_t, std::size_t> graph_lookup;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        std::istringstream stream(line);
        std::string record;
        stream >> record;
        if (record == "SOURCE_COUNT") {
            std::string count;
            stream >> count;
            (void)bounded_size(count, kMaxPlaybookGraphs, "source count");
        } else if (record == "GRAPH") {
            std::size_t wire_index = 0U;
            int version = 0;
            PlaybookGraph graph;
            stream >> wire_index >> graph.id >> version >> graph.mode >> graph.subject_kind
                   >> graph.subject_archetype >> graph.entry >> graph.max_steps >> graph.max_depth
                   >> graph.point_budget_cost >> graph.signature >> graph.source;
            if (!stream || version != 1) throw std::runtime_error("malformed GRAPH record");
            if (runtime.graphs_.size() >= kMaxPlaybookGraphs || graph.max_steps > kMaxPlaybookSteps ||
                graph.max_depth > 16U || graph.point_budget_cost > 65'535U) {
                throw std::runtime_error("GRAPH record exceeds bounded runtime limits");
            }
            graph_lookup[wire_index] = runtime.graphs_.size();
            runtime.graphs_.push_back(std::move(graph));
        } else if (record == "NODE") {
            std::size_t graph_index = 0U, node_index = 0U;
            PlaybookNode node;
            std::string timeout, cooldown;
            stream >> graph_index >> node_index >> node.id >> node.kind >> node.operation >> node.target
                   >> timeout >> cooldown >> node.bone;
            if (!stream || !graph_lookup.contains(graph_index)) throw std::runtime_error("malformed NODE record");
            auto& graph = runtime.graphs_[graph_lookup.at(graph_index)];
            if (node_index != graph.nodes.size() || graph.nodes.size() >= kMaxPlaybookNodes) {
                throw std::runtime_error("NODE order or bound violation");
            }
            node.timeout_ms = bounded_u32(timeout, 60'000U, "node timeout");
            node.cooldown_ms = bounded_u32(cooldown, 120'000U, "node cooldown");
            if (node.bone == "-") node.bone.clear();
            graph.nodes.push_back(std::move(node));
        } else if (record == "EDGE") {
            std::size_t graph_index = 0U;
            PlaybookEdge edge;
            unsigned int priority = 0U;
            stream >> graph_index >> edge.source >> edge.destination >> edge.branch >> edge.condition >> priority;
            if (!stream || !graph_lookup.contains(graph_index) || priority > 255U) {
                throw std::runtime_error("malformed EDGE record");
            }
            auto& graph = runtime.graphs_[graph_lookup.at(graph_index)];
            if (graph.edges.size() >= kMaxPlaybookEdges || edge.source >= graph.nodes.size() ||
                edge.destination >= graph.nodes.size()) {
                throw std::runtime_error("EDGE reference or bound violation");
            }
            edge.priority = static_cast<std::uint8_t>(priority);
            graph.edges.push_back(std::move(edge));
        } else if (record == "STATS") {
            stream >> runtime.stats_.graph_count >> runtime.stats_.node_count >> runtime.stats_.edge_count
                   >> runtime.stats_.point_budget_cost >> runtime.stats_.signature;
            if (!stream) throw std::runtime_error("malformed STATS record");
        } else if (record == "ENDGRAPH" || record == "END") {
            continue;
        } else {
            ++runtime.stats_.warning_count; // future records remain telemetry-only
        }
    }
    for (auto& graph : runtime.graphs_) {
        std::stable_sort(graph.edges.begin(), graph.edges.end(), [](const auto& a, const auto& b) {
            if (a.source != b.source) return a.source < b.source;
            if (a.priority != b.priority) return a.priority < b.priority;
            if (a.destination != b.destination) return a.destination < b.destination;
            if (a.branch != b.branch) return a.branch < b.branch;
            return a.condition < b.condition;
        });
    }
    if (!runtime.valid()) throw std::runtime_error("playbook runtime failed validation");
    return runtime;
}

const PlaybookGraph* PlaybookRuntime::find(std::string_view id) const noexcept {
    const auto it = std::find_if(graphs_.begin(), graphs_.end(), [id](const auto& graph) {
        return graph.id == id;
    });
    return it == graphs_.end() ? nullptr : &*it;
}

std::vector<PlaybookTraceStep> PlaybookRuntime::evaluate(
    std::string_view id, const PlaybookContext& context, std::size_t maximum_steps) const {
    const auto* graph = find(id);
    if (graph == nullptr) return {};
    const auto entry = std::find_if(graph->nodes.begin(), graph->nodes.end(), [graph](const auto& node) {
        return node.id == graph->entry;
    });
    if (entry == graph->nodes.end()) return {};
    std::size_t current = static_cast<std::size_t>(std::distance(graph->nodes.begin(), entry));
    const std::size_t limit = std::min({maximum_steps, graph->max_steps, kMaxPlaybookSteps});
    std::vector<PlaybookTraceStep> trace;
    trace.reserve(limit);
    for (std::size_t step = 0U; step < limit && current < graph->nodes.size(); ++step) {
        const auto& node = graph->nodes[current];
        trace.push_back({node.id, node.kind, node.operation, node.target});
        const auto selected = std::find_if(graph->edges.begin(), graph->edges.end(),
            [current, &context](const auto& edge) { return edge.source == current && edge_true(edge, context); });
        if (selected == graph->edges.end()) break;
        current = selected->destination;
    }
    return trace;
}

bool PlaybookRuntime::valid() const noexcept {
    if (graphs_.empty() || graphs_.size() > kMaxPlaybookGraphs) return false;
    std::size_t nodes = 0U, edges = 0U, cost = 0U;
    for (const auto& graph : graphs_) {
        if (graph.id.empty() || graph.nodes.empty() || graph.nodes.size() > kMaxPlaybookNodes ||
            graph.edges.size() > kMaxPlaybookEdges || graph.max_steps == 0U ||
            graph.max_steps > kMaxPlaybookSteps || graph.max_depth == 0U || graph.max_depth > 16U) {
            return false;
        }
        const bool has_entry = std::any_of(graph.nodes.begin(), graph.nodes.end(), [&graph](const auto& node) {
            return node.id == graph.entry;
        });
        if (!has_entry) return false;
        nodes += graph.nodes.size();
        edges += graph.edges.size();
        cost += graph.point_budget_cost;
    }
    return stats_.graph_count == graphs_.size() && stats_.node_count == nodes &&
           stats_.edge_count == edges && stats_.point_budget_cost == cost && !stats_.signature.empty();
}

}  // namespace signalcloud::ai
