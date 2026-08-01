#include "engine/render/gl_api.hpp"

#include <sstream>

namespace signalcloud::render {
namespace {

template <typename Function>
Function load_gl(const char* name) {
    return reinterpret_cast<Function>(SDL_GL_GetProcAddress(name));
}

}  // namespace

bool GLApi::load(std::string* error) {
#define SC_LOAD(member, type, symbol) member = load_gl<type>(symbol)
    SC_LOAD(get_string, FnGetString, "glGetString");
    SC_LOAD(get_string_i, FnGetStringi, "glGetStringi");
    SC_LOAD(get_integerv, FnGetIntegerv, "glGetIntegerv");
    SC_LOAD(get_integer64v, FnGetInteger64v, "glGetInteger64v");
    SC_LOAD(get_integer_i_v, FnGetIntegeriV, "glGetIntegeri_v");
    SC_LOAD(get_floatv, FnGetFloatv, "glGetFloatv");
    SC_LOAD(viewport, FnViewport, "glViewport");
    SC_LOAD(clear_color, FnClearColor, "glClearColor");
    SC_LOAD(clear, FnClear, "glClear");
    SC_LOAD(enable, FnEnable, "glEnable");
    SC_LOAD(disable, FnDisable, "glDisable");
    SC_LOAD(blend_func, FnBlendFunc, "glBlendFunc");
    SC_LOAD(depth_func, FnDepthFunc, "glDepthFunc");
    SC_LOAD(gen_vertex_arrays, FnGenVertexArrays, "glGenVertexArrays");
    SC_LOAD(bind_vertex_array, FnBindVertexArray, "glBindVertexArray");
    SC_LOAD(delete_vertex_arrays, FnDeleteVertexArrays, "glDeleteVertexArrays");
    SC_LOAD(gen_buffers, FnGenBuffers, "glGenBuffers");
    SC_LOAD(bind_buffer, FnBindBuffer, "glBindBuffer");
    SC_LOAD(buffer_data, FnBufferData, "glBufferData");
    SC_LOAD(delete_buffers, FnDeleteBuffers, "glDeleteBuffers");
    SC_LOAD(enable_vertex_attrib_array, FnEnableVertexAttribArray, "glEnableVertexAttribArray");
    SC_LOAD(vertex_attrib_pointer, FnVertexAttribPointer, "glVertexAttribPointer");
    SC_LOAD(create_shader, FnCreateShader, "glCreateShader");
    SC_LOAD(shader_source, FnShaderSource, "glShaderSource");
    SC_LOAD(compile_shader, FnCompileShader, "glCompileShader");
    SC_LOAD(get_shader_iv, FnGetShaderiv, "glGetShaderiv");
    SC_LOAD(get_shader_info_log, FnGetShaderInfoLog, "glGetShaderInfoLog");
    SC_LOAD(delete_shader, FnDeleteShader, "glDeleteShader");
    SC_LOAD(create_program, FnCreateProgram, "glCreateProgram");
    SC_LOAD(attach_shader, FnAttachShader, "glAttachShader");
    SC_LOAD(link_program, FnLinkProgram, "glLinkProgram");
    SC_LOAD(get_program_iv, FnGetProgramiv, "glGetProgramiv");
    SC_LOAD(get_program_info_log, FnGetProgramInfoLog, "glGetProgramInfoLog");
    SC_LOAD(use_program, FnUseProgram, "glUseProgram");
    SC_LOAD(delete_program, FnDeleteProgram, "glDeleteProgram");
    SC_LOAD(get_uniform_location, FnGetUniformLocation, "glGetUniformLocation");
    SC_LOAD(uniform_matrix4fv, FnUniformMatrix4fv, "glUniformMatrix4fv");
    SC_LOAD(uniform1f, FnUniform1f, "glUniform1f");
    SC_LOAD(uniform1i, FnUniform1i, "glUniform1i");
    SC_LOAD(uniform3f, FnUniform3f, "glUniform3f");
    SC_LOAD(draw_arrays, FnDrawArrays, "glDrawArrays");
    SC_LOAD(gen_queries, FnGenQueries, "glGenQueries");
    SC_LOAD(delete_queries, FnDeleteQueries, "glDeleteQueries");
    SC_LOAD(begin_query, FnBeginQuery, "glBeginQuery");
    SC_LOAD(end_query, FnEndQuery, "glEndQuery");
    SC_LOAD(get_query_object_iv, FnGetQueryObjectiv, "glGetQueryObjectiv");
    SC_LOAD(get_query_object_ui64v, FnGetQueryObjectui64v, "glGetQueryObjectui64v");
    SC_LOAD(pixel_store_i, FnPixelStorei, "glPixelStorei");
    SC_LOAD(read_pixels, FnReadPixels, "glReadPixels");
#undef SC_LOAD

    const bool required = get_string && get_integerv && viewport && clear_color && clear && enable &&
        blend_func && depth_func && gen_vertex_arrays && bind_vertex_array && delete_vertex_arrays &&
        gen_buffers && bind_buffer && buffer_data && delete_buffers && enable_vertex_attrib_array &&
        vertex_attrib_pointer && create_shader && shader_source && compile_shader && get_shader_iv &&
        get_shader_info_log && delete_shader && create_program && attach_shader && link_program &&
        get_program_iv && get_program_info_log && use_program && delete_program && get_uniform_location &&
        uniform_matrix4fv && uniform1f && uniform1i && uniform3f && draw_arrays;
    if (!required && error != nullptr) {
        *error = "One or more required OpenGL 3.3 entry points could not be loaded.";
    }
    return required;
}

}  // namespace signalcloud::render
