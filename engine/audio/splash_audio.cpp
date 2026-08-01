#include "engine/audio/splash_audio.hpp"

#include <SDL3/SDL.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

namespace signalcloud::audio {
namespace {
constexpr int kSampleRate = 48'000;
constexpr float kPi = 3.14159265358979323846F;
}

SplashAudio::~SplashAudio() { shutdown(); }

bool SplashAudio::initialize() noexcept {
    shutdown();
    SDL_AudioSpec spec{};
    spec.format = SDL_AUDIO_F32;
    spec.channels = 2;
    spec.freq = kSampleRate;
    stream_ = SDL_OpenAudioDeviceStream(
        SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, &spec, nullptr, nullptr);
    if (stream_ == nullptr) return false;
    if (!SDL_ResumeAudioStreamDevice(stream_)) {
        shutdown();
        return false;
    }
    return true;
}

void SplashAudio::play(float strength, bool bomb) noexcept {
    if (stream_ == nullptr) return;
    const float clamped = std::clamp(strength, 0.10F, 1.0F);
    const float duration = bomb ? 0.58F : 0.28F;
    const int frames = static_cast<int>(duration * static_cast<float>(kSampleRate));
    std::vector<float> samples(static_cast<std::size_t>(frames) * 2U);
    std::uint32_t noise_state = bomb ? 0xB0B5A11DU : 0x5A1A5EEDU;
    for (int i = 0; i < frames; ++i) {
        const float t = static_cast<float>(i) / static_cast<float>(kSampleRate);
        const float p = t / duration;
        const float envelope = std::max(0.0F, 1.0F - p);
        const float frequency = (bomb ? 92.0F : 145.0F) * (1.0F - 0.62F * p);
        noise_state ^= noise_state << 13U;
        noise_state ^= noise_state >> 17U;
        noise_state ^= noise_state << 5U;
        const float noise = (static_cast<float>(noise_state & 0xFFFFU) / 32767.5F) - 1.0F;
        const float low = std::sin(2.0F * kPi * frequency * t);
        const float slap = std::sin(2.0F * kPi * (bomb ? 310.0F : 420.0F) * t) *
                           std::exp(-t * (bomb ? 10.0F : 18.0F));
        const float value = (low * 0.52F + noise * 0.30F + slap * 0.18F) *
                            envelope * clamped * (bomb ? 0.52F : 0.30F);
        samples[static_cast<std::size_t>(i) * 2U] = value;
        samples[static_cast<std::size_t>(i) * 2U + 1U] = value;
    }
    if (!SDL_PutAudioStreamData(stream_, samples.data(),
                                static_cast<int>(samples.size() * sizeof(float)))) {
        shutdown();
    }
}

void SplashAudio::shutdown() noexcept {
    if (stream_ != nullptr) {
        SDL_DestroyAudioStream(stream_);
        stream_ = nullptr;
    }
}

}  // namespace signalcloud::audio
