#include "engine/platform/capability_report.hpp"

#include "engine/render/memory_budget.hpp"

#include <algorithm>
#include <fstream>
#include <set>
#include <sstream>

namespace signalcloud::platform {
namespace {
std::string gl_string(const render::GLApi& gl, GLenum name) {
    const GLubyte* value = gl.get_string(name);
    return value ? reinterpret_cast<const char*>(value) : "unavailable";
}
}

CapabilityReport collect_capability_report(const render::GLApi& gl, std::string_view video_driver) {
    CapabilityReport report;
    report.vendor = gl_string(gl, GL_VENDOR);
    report.renderer = gl_string(gl, GL_RENDERER);
    report.version = gl_string(gl, GL_VERSION);
    gl.get_integerv(GL_MAJOR_VERSION, &report.gl_major);
    gl.get_integerv(GL_MINOR_VERSION, &report.gl_minor);

    std::set<std::string> extensions;
    GLint extension_count = 0;
    if (gl.get_string_i != nullptr) {
        gl.get_integerv(GL_NUM_EXTENSIONS, &extension_count);
        for (GLint i = 0; i < extension_count; ++i) {
            const GLubyte* extension = gl.get_string_i(GL_EXTENSIONS, static_cast<GLuint>(i));
            if (extension != nullptr) extensions.emplace(reinterpret_cast<const char*>(extension));
        }
    }
    const auto has = [&](const char* name) { return extensions.contains(name); };
    report.compute_shader = report.gl_major > 4 || (report.gl_major == 4 && report.gl_minor >= 3) || has("GL_ARB_compute_shader");
    report.shader_storage = report.gl_major > 4 || (report.gl_major == 4 && report.gl_minor >= 3) || has("GL_ARB_shader_storage_buffer_object");
    report.persistent_mapping = report.gl_major > 4 || (report.gl_major == 4 && report.gl_minor >= 4) || has("GL_ARB_buffer_storage");
    report.int64_atomics = has("GL_ARB_gpu_shader_int64") || has("GL_NV_shader_atomic_int64");
    report.timer_query = gl.gen_queries && gl.delete_queries && gl.begin_query && gl.end_query &&
        gl.get_query_object_iv && gl.get_query_object_ui64v;

    GLint max_texture = 0;
    GLint max_vertex_attribs = 0;
    GLfloat point_range[2]{0.0F, 0.0F};
    gl.get_integerv(GL_MAX_TEXTURE_SIZE, &max_texture);
    gl.get_integerv(GL_MAX_VERTEX_ATTRIBS, &max_vertex_attribs);
    gl.get_floatv(GL_ALIASED_POINT_SIZE_RANGE, point_range);

    GLint ssbo_bindings = 0;
    GLint compute_invocations = 0;
    GLint64 ssbo_size = 0;
    if (report.shader_storage) {
        gl.get_integerv(GL_MAX_SHADER_STORAGE_BUFFER_BINDINGS, &ssbo_bindings);
        if (gl.get_integer64v != nullptr) gl.get_integer64v(GL_MAX_SHADER_STORAGE_BLOCK_SIZE, &ssbo_size);
    }
    if (report.compute_shader) gl.get_integerv(GL_MAX_COMPUTE_WORK_GROUP_INVOCATIONS, &compute_invocations);

    std::ostringstream output;
    output << "ALMOND SIGNAL: LIVE TAPE / SIGNALCLOUD ENGINE\n"
           << "Pivot capability report v0.13.0-a3\n\n"
           << "SDL video driver: " << video_driver << '\n'
           << "OpenGL vendor: " << report.vendor << '\n'
           << "OpenGL renderer: " << report.renderer << '\n'
           << "OpenGL version: " << report.version << '\n'
           << "OpenGL parsed version: " << report.gl_major << '.' << report.gl_minor << '\n'
           << "GLSL version: " << gl_string(gl, GL_SHADING_LANGUAGE_VERSION) << '\n'
           << "Maximum texture size: " << max_texture << '\n'
           << "Maximum vertex attributes: " << max_vertex_attribs << '\n'
           << "Point-size range: " << point_range[0] << " to " << point_range[1] << " pixels\n\n"
           << "Compute shaders: " << (report.compute_shader ? "available" : "not available") << '\n'
           << "Shader storage buffers: " << (report.shader_storage ? "available" : "not available") << '\n'
           << "Persistent mapped storage: " << (report.persistent_mapping ? "available" : "not available") << '\n'
           << "64-bit shader atomics: " << (report.int64_atomics ? "available" : "not available") << '\n'
           << "Maximum SSBO bindings: " << ssbo_bindings << '\n'
           << "Maximum SSBO block size: " << ssbo_size << " bytes\n"
           << "Maximum compute work-group invocations: " << compute_invocations << "\n\n"
           << "Point memory estimates (48-byte visible point):\n";
    for (const auto& estimate : render::standard_point_presets()) {
        output << "  " << estimate.points << " points: "
               << render::format_mebibytes(estimate.bytes_single) << " single / "
               << render::format_mebibytes(estimate.bytes_triple) << " triple-buffered\n";
    }
    output << "\nSelected Pivot 13 a3 path: adaptive 8M streamed environment plus collision-aware threat navigation, timed threshold pursuit, vertical perception, JAM topology, cause-aware recovery, and protected-room fallback.\n"
           << "The verified Intel/Mesa baseline remains 8M resident points; active-room submission stays governed while world threats use obstacle-aware dynamic movement.\n"
           << "The compatibility renderer remains active. Sustained frame pressure queues a 4M fallback that is applied only in a protected room; room transitions never regenerate the resident cloud.\n";
    report.text = output.str();
    return report;
}

bool write_capability_report(const CapabilityReport& report, const std::filesystem::path& path,
                             std::string* error) {
    try {
        std::filesystem::create_directories(path.parent_path());
        std::ofstream output(path, std::ios::binary | std::ios::trunc);
        if (!output) throw std::runtime_error("Unable to create capability report.");
        output << report.text;
        return static_cast<bool>(output);
    } catch (const std::exception& ex) {
        if (error != nullptr) *error = ex.what();
        return false;
    }
}

}  // namespace signalcloud::platform
