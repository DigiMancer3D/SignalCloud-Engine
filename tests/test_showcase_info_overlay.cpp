#include "engine/scfont/scfont.hpp"
#include "engine/ui/showcase_info_overlay.hpp"

#include <cmath>
#include <filesystem>
#include <iostream>
#include <string_view>
#include <vector>

namespace {
int fail(std::string_view message) {
    std::cerr << "Showcase info overlay test failure: " << message << '\n';
    return 1;
}
}

int main(int argc, char** argv) {
    namespace fs = std::filesystem;
    const fs::path root = argc > 1 ? fs::path(argv[1]) : fs::current_path();
    const auto font = signalcloud::font::load_scfont(
        root / "content/core/fonts/terminal_00/Terminal_00.scfont");

    signalcloud::ui::ShowcaseInfoOverlayCamera camera;
    camera.eye = {8.0F, 5.0F, 9.0F};
    camera.center = {0.0F, 2.0F, 0.0F};
    camera.aspect = 16.0F / 9.0F;

    std::vector<signalcloud::render::PointGpu> points;
    const auto stats = signalcloud::ui::append_showcase_info_overlay(
        points, font,
        "SHOWCASE A7a2r2 DROP RUNNING\nVIEW MATERIAL LOD 100%\n"
        "COLLISION ON ACTOR OFF FOLLOW OFF LOOP ON\n"
        "1-5 TEST C COLLISION L LOD V VIEW P ACTOR\n"
        "T FOLLOW O LOOP F/HOME RESET S SNAPSHOT I INFO",
        camera);

    if (!(stats.scale > 0.0F && stats.width > 0.0F && stats.height > 0.0F &&
          stats.text_points > 0U && stats.backplate_points > 0U &&
          points.size() == stats.text_points + stats.backplate_points)) {
        return fail("wide overlay geometry contract");
    }

    std::size_t solid_points = 0U;
    for (const auto& point : points) {
        if (!std::isfinite(point.position[0]) || !std::isfinite(point.position[1]) ||
            !std::isfinite(point.position[2]) || !std::isfinite(point.radius)) {
            return fail("non-finite point");
        }
        if (point.density >= 4.5F) ++solid_points;
    }
    if (solid_points != stats.backplate_points) return fail("backplate density contract");

    std::vector<signalcloud::render::PointGpu> narrow_points;
    camera.aspect = 4.0F / 3.0F;
    const auto narrow = signalcloud::ui::append_showcase_info_overlay(
        narrow_points, font, "SHOWCASE\nI INFO", camera);
    if (narrow.text_points == 0U || narrow.backplate_points == 0U) {
        return fail("narrow overlay geometry contract");
    }

    std::cout << "A7a2r2 Showcase top-left info overlay: point UI + backplate PASS\n";
    return 0;
}
