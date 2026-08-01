#include "engine/world/world_seed.hpp"

#include <iomanip>
#include <sstream>

namespace signalcloud::world {
namespace {
std::uint64_t splitmix64(std::uint64_t value) noexcept {
    value += 0x9E3779B97F4A7C15ULL;
    value = (value ^ (value >> 30U)) * 0xBF58476D1CE4E5B9ULL;
    value = (value ^ (value >> 27U)) * 0x94D049BB133111EBULL;
    return value ^ (value >> 31U);
}
}

std::uint64_t mix_seed(std::uint64_t global_seed, ChunkKey chunk, std::uint32_t stream_id) noexcept {
    std::uint64_t value = splitmix64(global_seed);
    value ^= splitmix64(static_cast<std::uint32_t>(chunk.x));
    value ^= splitmix64(static_cast<std::uint32_t>(chunk.y) + 0x100000001B3ULL);
    value ^= splitmix64(static_cast<std::uint32_t>(chunk.z) + 0x9E3779B9ULL);
    value ^= splitmix64(stream_id);
    return splitmix64(value);
}

std::string seed_hex(std::uint64_t seed) {
    std::ostringstream output;
    output << std::hex << std::uppercase << std::setw(16) << std::setfill('0') << seed;
    return output.str();
}

}  // namespace signalcloud::world
