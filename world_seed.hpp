#pragma once

#include <cstdint>
#include <string>

namespace signalcloud::world {

struct ChunkKey {
    std::int32_t x{0};
    std::int32_t y{0};
    std::int32_t z{0};
    friend bool operator==(const ChunkKey&, const ChunkKey&) = default;
};

[[nodiscard]] std::uint64_t mix_seed(std::uint64_t global_seed, ChunkKey chunk,
                                     std::uint32_t stream_id = 0) noexcept;
[[nodiscard]] std::string seed_hex(std::uint64_t seed);

}  // namespace signalcloud::world
