#pragma once

#include <SDL3/SDL_audio.h>

namespace signalcloud::audio {

class SplashAudio {
public:
    SplashAudio() = default;
    ~SplashAudio();
    SplashAudio(const SplashAudio&) = delete;
    SplashAudio& operator=(const SplashAudio&) = delete;

    bool initialize() noexcept;
    void play(float strength, bool bomb) noexcept;
    void shutdown() noexcept;
    [[nodiscard]] bool available() const noexcept { return stream_ != nullptr; }

private:
    SDL_AudioStream* stream_{nullptr};
};

}  // namespace signalcloud::audio
