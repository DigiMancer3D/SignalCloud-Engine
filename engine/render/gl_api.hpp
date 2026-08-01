#pragma once

#include <SDL3/SDL.h>
#include <SDL3/SDL_opengl.h>

#include <string>

namespace signalcloud::render {

class GLApi {
public:
    using FnGetString = const GLubyte* (*)(GLenum);
    using FnGetStringi = const GLubyte* (*)(GLenum, GLuint);
    using FnGetIntegerv = void (*)(GLenum, GLint*);
    using FnGetInteger64v = void (*)(GLenum, GLint64*);
    using FnGetIntegeriV = void (*)(GLenum, GLuint, GLint*);
    using FnGetFloatv = void (*)(GLenum, GLfloat*);
    using FnViewport = void (*)(GLint, GLint, GLsizei, GLsizei);
    using FnClearColor = void (*)(GLfloat, GLfloat, GLfloat, GLfloat);
    using FnClear = void (*)(GLbitfield);
    using FnEnable = void (*)(GLenum);
    using FnDisable = void (*)(GLenum);
    using FnBlendFunc = void (*)(GLenum, GLenum);
    using FnDepthFunc = void (*)(GLenum);
    using FnGenVertexArrays = void (*)(GLsizei, GLuint*);
    using FnBindVertexArray = void (*)(GLuint);
    using FnDeleteVertexArrays = void (*)(GLsizei, const GLuint*);
    using FnGenBuffers = void (*)(GLsizei, GLuint*);
    using FnBindBuffer = void (*)(GLenum, GLuint);
    using FnBufferData = void (*)(GLenum, GLsizeiptr, const void*, GLenum);
    using FnDeleteBuffers = void (*)(GLsizei, const GLuint*);
    using FnEnableVertexAttribArray = void (*)(GLuint);
    using FnVertexAttribPointer = void (*)(GLuint, GLint, GLenum, GLboolean, GLsizei, const void*);
    using FnCreateShader = GLuint (*)(GLenum);
    using FnShaderSource = void (*)(GLuint, GLsizei, const GLchar* const*, const GLint*);
    using FnCompileShader = void (*)(GLuint);
    using FnGetShaderiv = void (*)(GLuint, GLenum, GLint*);
    using FnGetShaderInfoLog = void (*)(GLuint, GLsizei, GLsizei*, GLchar*);
    using FnDeleteShader = void (*)(GLuint);
    using FnCreateProgram = GLuint (*)();
    using FnAttachShader = void (*)(GLuint, GLuint);
    using FnLinkProgram = void (*)(GLuint);
    using FnGetProgramiv = void (*)(GLuint, GLenum, GLint*);
    using FnGetProgramInfoLog = void (*)(GLuint, GLsizei, GLsizei*, GLchar*);
    using FnUseProgram = void (*)(GLuint);
    using FnDeleteProgram = void (*)(GLuint);
    using FnGetUniformLocation = GLint (*)(GLuint, const GLchar*);
    using FnUniformMatrix4fv = void (*)(GLint, GLsizei, GLboolean, const GLfloat*);
    using FnUniform1f = void (*)(GLint, GLfloat);
    using FnUniform1i = void (*)(GLint, GLint);
    using FnUniform3f = void (*)(GLint, GLfloat, GLfloat, GLfloat);
    using FnDrawArrays = void (*)(GLenum, GLint, GLsizei);
    using FnGenQueries = void (*)(GLsizei, GLuint*);
    using FnDeleteQueries = void (*)(GLsizei, const GLuint*);
    using FnBeginQuery = void (*)(GLenum, GLuint);
    using FnEndQuery = void (*)(GLenum);
    using FnGetQueryObjectiv = void (*)(GLuint, GLenum, GLint*);
    using FnGetQueryObjectui64v = void (*)(GLuint, GLenum, GLuint64*);
    using FnPixelStorei = void (*)(GLenum, GLint);
    using FnReadPixels = void (*)(GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, void*);

    bool load(std::string* error = nullptr);

    FnGetString get_string{};
    FnGetStringi get_string_i{};
    FnGetIntegerv get_integerv{};
    FnGetInteger64v get_integer64v{};
    FnGetIntegeriV get_integer_i_v{};
    FnGetFloatv get_floatv{};
    FnViewport viewport{};
    FnClearColor clear_color{};
    FnClear clear{};
    FnEnable enable{};
    FnDisable disable{};
    FnBlendFunc blend_func{};
    FnDepthFunc depth_func{};
    FnGenVertexArrays gen_vertex_arrays{};
    FnBindVertexArray bind_vertex_array{};
    FnDeleteVertexArrays delete_vertex_arrays{};
    FnGenBuffers gen_buffers{};
    FnBindBuffer bind_buffer{};
    FnBufferData buffer_data{};
    FnDeleteBuffers delete_buffers{};
    FnEnableVertexAttribArray enable_vertex_attrib_array{};
    FnVertexAttribPointer vertex_attrib_pointer{};
    FnCreateShader create_shader{};
    FnShaderSource shader_source{};
    FnCompileShader compile_shader{};
    FnGetShaderiv get_shader_iv{};
    FnGetShaderInfoLog get_shader_info_log{};
    FnDeleteShader delete_shader{};
    FnCreateProgram create_program{};
    FnAttachShader attach_shader{};
    FnLinkProgram link_program{};
    FnGetProgramiv get_program_iv{};
    FnGetProgramInfoLog get_program_info_log{};
    FnUseProgram use_program{};
    FnDeleteProgram delete_program{};
    FnGetUniformLocation get_uniform_location{};
    FnUniformMatrix4fv uniform_matrix4fv{};
    FnUniform1f uniform1f{};
    FnUniform1i uniform1i{};
    FnUniform3f uniform3f{};
    FnDrawArrays draw_arrays{};
    FnGenQueries gen_queries{};
    FnDeleteQueries delete_queries{};
    FnBeginQuery begin_query{};
    FnEndQuery end_query{};
    FnGetQueryObjectiv get_query_object_iv{};
    FnGetQueryObjectui64v get_query_object_ui64v{};
    FnPixelStorei pixel_store_i{};
    FnReadPixels read_pixels{};
};

}  // namespace signalcloud::render
