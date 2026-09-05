#include "scene_draw.h"
#include <Windows.h>
#include <gl/GL.h>
#include <cstdint>
#include <cstring>
namespace wonderbane::extension {
namespace {
using ActiveTexture = void(APIENTRY*)(GLenum);
using UseProgram = void(APIENTRY*)(GLuint);
using BindProgramPipeline = void(APIENTRY*)(GLuint);
using BlendEquation = void(APIENTRY*)(GLenum);
using BlendEquationSeparate = void(APIENTRY*)(GLenum, GLenum);
constexpr GLenum kTexture0 = 0x84C0U;
constexpr GLenum kActiveTexture = 0x84E0U;
constexpr GLenum kCurrentProgram = 0x8B8DU;

PROC Extension(const char* name) noexcept {
    const PROC result = wglGetProcAddress(name);
    const auto value = reinterpret_cast<std::uintptr_t>(result);
    return value <= 3U || value == UINTPTR_MAX ? nullptr : result;
}

bool HasExtension(const char* extensions, const char* name) noexcept {
    if (!extensions) return false;
    const std::size_t length = std::strlen(name);
    for (const char* match = extensions; (match = std::strstr(match, name)) != nullptr; match += length) {
        if ((match == extensions || match[-1] == ' ')
            && (match[length] == '\0' || match[length] == ' ')) return true;
    }
    return false;
}

bool StackRoom(GLenum depth_name, GLenum max_name) noexcept {
    GLint depth = 0, maximum = 0;
    glGetIntegerv(depth_name, &depth); glGetIntegerv(max_name, &maximum);
    return depth >= 0 && depth < maximum;
}
}
bool RenderSceneGeometry(const GraphicsCameraState* camera, SceneDraw draw, void* user) noexcept {
    if (!draw || !wglGetCurrentContext()
        || !StackRoom(GL_ATTRIB_STACK_DEPTH, GL_MAX_ATTRIB_STACK_DEPTH)
        || !StackRoom(GL_MODELVIEW_STACK_DEPTH, GL_MAX_MODELVIEW_STACK_DEPTH)
        || !StackRoom(GL_PROJECTION_STACK_DEPTH, GL_MAX_PROJECTION_STACK_DEPTH)) return false;
    GLint viewport[4]{}; glGetIntegerv(GL_VIEWPORT, viewport);
    if (camera && std::memcmp(camera->viewport,viewport,sizeof(viewport))) return false;
    const auto* version = reinterpret_cast<const char*>(glGetString(GL_VERSION));
    if (version == nullptr || version[0] < '1' || version[0] > '9') return false;
    const bool modern = version[0] >= '2';
    const bool texture3d = modern || (version[0] == '1' && version[1] == '.' && version[2] >= '2');
    // Legacy ARB programs are a separate state machine from GLSL. Do not draw
    // through an unreviewed active program path; leave it untouched.
    const auto* extensions = reinterpret_cast<const char*>(glGetString(GL_EXTENSIONS));
    if (extensions != nullptr && (
        (std::strstr(extensions, "GL_ARB_vertex_program") != nullptr && glIsEnabled(0x8620U))
        || (std::strstr(extensions, "GL_ARB_fragment_program") != nullptr && glIsEnabled(0x8804U)))) return false;
    // UseProgram(0) exposes any bound separate pipeline; it does not disable it.
    // EXT_separate_shader_objects predates the core/ARB pipeline object API.
    const bool pipelines = version[0] > '4'
        || (version[0] == '4' && version[1] == '.' && version[2] >= '1')
        || HasExtension(extensions, "GL_ARB_separate_shader_objects");
    const auto bind_pipeline = pipelines
        ? reinterpret_cast<BindProgramPipeline>(Extension("glBindProgramPipeline")) : nullptr;
    GLint pipeline = -1;
    if (pipelines) {
        if (!bind_pipeline) return false;
        glGetIntegerv(0x825AU, &pipeline); // GL_PROGRAM_PIPELINE_BINDING
        if (pipeline == -1) return false; // Unknown binding: leave native state untouched.
    }
    const auto active_texture = reinterpret_cast<ActiveTexture>(Extension("glActiveTexture"));
    const auto use_program = reinterpret_cast<UseProgram>(Extension("glUseProgram"));
    const auto blend_equation = reinterpret_cast<BlendEquation>(Extension("glBlendEquation"));
    const auto blend_separate = reinterpret_cast<BlendEquationSeparate>(Extension("glBlendEquationSeparate"));
    if (modern && (active_texture == nullptr || use_program == nullptr || blend_equation == nullptr)) return false;
    if (Extension("glBindFramebuffer") != nullptr || Extension("glBindFramebufferEXT") != nullptr) {
        GLint framebuffer = 0; glGetIntegerv(0x8CA6U, &framebuffer);
        if (framebuffer != 0) return false;
    }
    GLint units = 1, active = kTexture0, program = 0, matrix_mode = 0;
    GLint equation_rgb = 0x8006, equation_alpha = 0x8006;
    if (active_texture) {
        glGetIntegerv(0x84E2U, &units); glGetIntegerv(kActiveTexture, &active);
        if (units < 1 || units > 32) return false;
    }
    if (use_program) glGetIntegerv(kCurrentProgram, &program);
    if (blend_equation) glGetIntegerv(0x8009U, &equation_rgb);
    if (blend_separate) glGetIntegerv(0x883DU, &equation_alpha);
    glGetIntegerv(GL_MATRIX_MODE, &matrix_mode);
    // Core OpenGL imports belong to this extension, not the game's hooked IAT.
    // Restoring the driver state keeps the existing fixed-function mirror coherent.
    glPushAttrib(GL_ALL_ATTRIB_BITS);
    glMatrixMode(GL_PROJECTION); glPushMatrix();
    glMatrixMode(GL_MODELVIEW); glPushMatrix();
    if (bind_pipeline) bind_pipeline(0U);
    if (use_program) use_program(0U);
    if (blend_equation) blend_equation(0x8006U);
    for (GLint unit = 0; unit < units; ++unit) {
        if (active_texture) active_texture(kTexture0 + static_cast<GLenum>(unit));
        glDisable(GL_TEXTURE_1D); glDisable(GL_TEXTURE_2D);
        if (texture3d) glDisable(0x806FU);
        if (active_texture) glDisable(0x8513U);
    }
    for (GLenum plane = GL_CLIP_PLANE0; plane <= GL_CLIP_PLANE5; ++plane) glDisable(plane);
    glDisable(GL_ALPHA_TEST); glDisable(GL_COLOR_LOGIC_OP); glDisable(GL_CULL_FACE);
    glDisable(GL_DITHER); glDisable(GL_FOG); glDisable(GL_LIGHTING);
    glDisable(GL_SCISSOR_TEST); glDisable(GL_STENCIL_TEST); glDisable(GL_LINE_SMOOTH);
    glDisable(GL_POLYGON_OFFSET_FILL); glDisable(GL_POLYGON_OFFSET_LINE);
    glDisable(GL_POLYGON_STIPPLE); glDisable(GL_POLYGON_SMOOTH);
    glDisable(GL_LINE_STIPPLE); glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glDepthMask(GL_FALSE); glLineWidth(1.0F); glPolygonMode(GL_FRONT_AND_BACK, GL_FILL);
    glEnable(GL_DEPTH_TEST); glDepthFunc(GL_LEQUAL);
    if (camera) {
        glMatrixMode(GL_PROJECTION); glLoadMatrixf(camera->projection_matrix);
        glMatrixMode(GL_MODELVIEW); glLoadMatrixf(camera->view_matrix);
    }
    draw(user);
    glMatrixMode(GL_MODELVIEW); glPopMatrix();
    glMatrixMode(GL_PROJECTION); glPopMatrix();
    glPopAttrib();
    if (use_program) use_program(static_cast<GLuint>(program));
    if (bind_pipeline) bind_pipeline(static_cast<GLuint>(pipeline));
    if (blend_separate) blend_separate(static_cast<GLenum>(equation_rgb), static_cast<GLenum>(equation_alpha));
    else if (blend_equation) blend_equation(static_cast<GLenum>(equation_rgb));
    if (active_texture) active_texture(static_cast<GLenum>(active));
    glMatrixMode(static_cast<GLenum>(matrix_mode));
    return true;
}
}
