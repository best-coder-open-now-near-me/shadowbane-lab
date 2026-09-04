#include "navigation_viewer.h"

#include <Windows.h>
#include <gl/GL.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>

namespace wonderbane::extension {
namespace {
using ActiveTexture = void(APIENTRY*)(GLenum);
using UseProgram = void(APIENTRY*)(GLuint);
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

struct Glyph { char letter; std::array<unsigned char, 7> rows; };
constexpr Glyph kGlyphs[] = {
    {'A',{14,17,17,31,17,17,17}}, {'B',{30,17,17,30,17,17,30}},
    {'C',{14,17,16,16,16,17,14}}, {'D',{30,17,17,17,17,17,30}},
    {'E',{31,16,16,30,16,16,31}}, {'F',{31,16,16,30,16,16,16}},
    {'G',{14,17,16,23,17,17,15}}, {'H',{17,17,17,31,17,17,17}},
    {'I',{14,4,4,4,4,4,14}}, {'J',{7,2,2,2,18,18,12}},
    {'K',{17,18,20,24,20,18,17}}, {'L',{16,16,16,16,16,16,31}},
    {'M',{17,27,21,21,17,17,17}}, {'N',{17,25,21,19,17,17,17}},
    {'O',{14,17,17,17,17,17,14}}, {'P',{30,17,17,30,16,16,16}},
    {'Q',{14,17,17,17,21,18,13}}, {'R',{30,17,17,30,20,18,17}},
    {'S',{15,16,16,14,1,1,30}}, {'T',{31,4,4,4,4,4,4}},
    {'U',{17,17,17,17,17,17,14}}, {'V',{17,17,17,17,17,10,4}},
    {'W',{17,17,17,21,21,27,17}}, {'X',{17,17,10,4,10,17,17}},
    {'Y',{17,17,10,4,4,4,4}}, {'Z',{31,1,2,4,8,16,31}},
    {'0',{14,17,19,21,25,17,14}}, {'1',{4,12,4,4,4,4,14}},
    {'2',{14,17,1,2,4,8,31}}, {'3',{30,1,1,14,1,1,30}},
    {'4',{2,6,10,18,31,2,2}}, {'5',{31,16,16,30,1,1,30}},
    {'6',{14,16,16,30,17,17,14}}, {'7',{31,1,2,4,8,8,8}},
    {'8',{14,17,17,14,17,17,14}}, {'9',{14,17,17,15,1,1,14}},
    {'/',{1,1,2,4,8,16,16}}, {'-',{0,0,0,31,0,0,0}},
    {':',{0,4,4,0,4,4,0}}, {'.',{0,0,0,0,0,4,4}},
};
void Quad(float x, float y, float width, float height) noexcept {
    glVertex2f(x, y); glVertex2f(x + width, y);
    glVertex2f(x + width, y + height); glVertex2f(x, y + height);
}
void Text(float x, const float y, const float scale, const char* text) noexcept {
    glBegin(GL_QUADS);
    for (std::size_t i = 0; i < 40U && text[i] != '\0'; ++i, x += 6.0F * scale) {
        for (const auto& glyph : kGlyphs) {
            if (glyph.letter != text[i]) continue;
            for (unsigned row = 0; row < 7U; ++row) {
                for (unsigned col = 0; col < 5U; ++col) {
                    if ((glyph.rows[row] & (1U << (4U - col))) != 0U) {
                        Quad(x + static_cast<float>(col) * scale,
                             y + static_cast<float>(row) * scale, scale, scale);
                    }
                }
            }
            break;
        }
    }
    glEnd();
}
void Color(const std::uint32_t layer, const bool overlap = false) noexcept {
    if (overlap) { glColor4f(1.0F, 0.18F, 0.16F, 1.0F); return; }
    switch (layer) {
    case 1U: glColor4f(0.65F, 0.5F, 1.0F, 0.9F); break;
    case 2U: glColor4f(0.2F, 1.0F, 0.45F, 1.0F); break;
    case 4U: glColor4f(1.0F, 0.75F, 0.25F, 0.8F); break;
    case 8U: glColor4f(1.0F, 0.3F, 0.3F, 0.9F); break;
    case 16U: glColor4f(1.0F, 0.6F, 0.3F, 0.9F); break;
    case 32U: glColor4f(0.75F, 0.75F, 0.35F, 0.5F); break;
    case 64U: glColor4f(1.0F, 1.0F, 1.0F, 1.0F); break;
    case 128U: glColor4f(0.2F, 0.85F, 1.0F, 1.0F); break;
    default: glColor4f(1.0F, 0.3F, 0.85F, 1.0F); break;
    }
}
bool StackRoom(GLenum depth_name, GLenum max_name) noexcept {
    GLint depth = 0, maximum = 0;
    glGetIntegerv(depth_name, &depth); glGetIntegerv(max_name, &maximum);
    return depth >= 0 && depth < maximum;
}
void WorldLines(const navigation::FrameHeader& frame, const navigation::Line* lines,
                const bool xray) noexcept {
    glBegin(GL_LINES);
    for (std::uint32_t i = 0; i < frame.line_count; ++i) {
        const auto& line = lines[i];
        if ((line.flags & navigation::kWorldHeight) == 0U
            || (line.layer & frame.layer_mask) == 0U) continue;
        if (xray) glColor4f(0.9F, 0.4F, 1.0F, 0.65F);
        else Color(line.layer);
        glVertex3fv(line.start); glVertex3fv(line.end);
    }
    glEnd();
}
void ProjectedView(const navigation::FrameHeader& frame, const navigation::Line* lines,
                   const GLint* viewport, const bool camera_available) noexcept {
    const float width = static_cast<float>(viewport[2]);
    const float height = static_cast<float>(viewport[3]);
    const float side = (std::min)({320.0F, width * 0.34F, height - 150.0F});
    const float left = width - side - 12.0F, top = 42.0F;
    const float font = side >= 290.0F ? 2.0F : 1.0F;
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_LINE_STIPPLE);
    glMatrixMode(GL_PROJECTION); glLoadIdentity(); glOrtho(0, width, height, 0, -1, 1);
    glMatrixMode(GL_MODELVIEW); glLoadIdentity();
    glColor4f(0.035F, 0.05F, 0.075F, 0.9F);
    glBegin(GL_QUADS); Quad(left - 6, 8, side + 12, side + 140); glEnd();
    glColor4f(0.9F, 0.93F, 1.0F, 1.0F);
    Text(left, 16, font, "PROJECTED HEIGHT UNKNOWN");
    glColor4f(0.25F, 0.3F, 0.4F, 1.0F);
    glBegin(GL_LINE_LOOP);
    glVertex2f(left, top); glVertex2f(left + side, top);
    glVertex2f(left + side, top + side); glVertex2f(left, top + side); glEnd();
    const float scale = (side - 12.0F) / (frame.view_radius * 2.0F);
    // Clip only the projected map, restoring the owner's scissor state via attribs.
    glEnable(GL_SCISSOR_TEST);
    glScissor(viewport[0] + static_cast<int>(left),
              viewport[1] + static_cast<int>(height - top - side),
              static_cast<int>(side), static_cast<int>(side));
    glBegin(GL_LINES);
    for (std::uint32_t i = 0; i < frame.line_count; ++i) {
        const auto& line = lines[i];
        if ((line.layer & frame.layer_mask) == 0U) continue;
        Color(line.layer, (line.flags & navigation::kOverlap) != 0U);
        for (const auto* point : {line.start, line.end}) {
            glVertex2f(left + side / 2 + (point[0] - frame.center_lt) * scale,
                       top + side / 2 + (point[2] + frame.center_lg) * scale);
        }
    }
    glEnd(); glDisable(GL_SCISSOR_TEST);
    constexpr const char* labels[] = {"RAW SEARCH", "FINAL ROUTE", "CLEARANCE", "MODEL CELLS",
                                     "LEARNED", "COST/DENSITY", "OBJECTIVE", "TRAIL", "EVENTS"};
    for (unsigned i = 0; i < 9U; ++i) {
        if ((frame.layer_mask & (1U << i)) != 0U) Color(1U << i);
        else glColor4f(0.3F, 0.3F, 0.3F, 1.0F);
        Text(left + static_cast<float>(i % 2U) * side / 2,
             top + side + 8 + static_cast<float>(i / 2U) * 16, font, labels[i]);
    }
    glColor4f(1.0F, 0.85F, 0.5F, 1.0F);
    Text(left, top + side + 88, 1, (frame.flags & navigation::kFrozen) ? "FROZEN / LT RIGHT LG UP" : "LIVE / LT RIGHT LG UP");
    Text(left, top + side + 100, 1,
         frame.omitted_lines || frame.status ? "TRUNCATED MODEL / SEE PANEL" :
         !camera_available ? "WORLD CAMERA UNAVAILABLE" :
         (frame.flags & navigation::kXray) ? "WORLD XRAY TRAIL IS DASHED" : "WORLD TRAIL USES SCENE DEPTH");
}
}  // namespace

bool RenderNavigationGeometry(const navigation::FrameHeader& frame,
                              const navigation::Line* const lines,
                              const GraphicsCameraState* const camera) noexcept {
    if ((frame.flags & navigation::kEnabled) == 0U || lines == nullptr
        || frame.line_count > navigation::kMaximumLines || !std::isfinite(frame.view_radius)
        || frame.view_radius <= 0.0F || wglGetCurrentContext() == nullptr) return false;
    GLint viewport[4]{};
    glGetIntegerv(GL_VIEWPORT, viewport);
    if (viewport[2] < 480 || viewport[3] < 360
        || !StackRoom(GL_ATTRIB_STACK_DEPTH, GL_MAX_ATTRIB_STACK_DEPTH)
        || !StackRoom(GL_MODELVIEW_STACK_DEPTH, GL_MAX_MODELVIEW_STACK_DEPTH)
        || !StackRoom(GL_PROJECTION_STACK_DEPTH, GL_MAX_PROJECTION_STACK_DEPTH)) return false;
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
    const bool camera_available = camera != nullptr
        && std::memcmp(camera->viewport, viewport, sizeof(viewport)) == 0;
    // Core OpenGL imports belong to this extension, not the game's hooked IAT.
    // Restoring the driver state keeps the existing fixed-function mirror coherent.
    glPushAttrib(GL_ALL_ATTRIB_BITS);
    glMatrixMode(GL_PROJECTION); glPushMatrix();
    glMatrixMode(GL_MODELVIEW); glPushMatrix();
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
    glDisable(GL_LINE_STIPPLE); glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glDepthMask(GL_FALSE); glLineWidth(1.0F); glPolygonMode(GL_FRONT_AND_BACK, GL_FILL);
    if (camera_available) {
        glMatrixMode(GL_PROJECTION); glLoadMatrixf(camera->projection_matrix);
        glMatrixMode(GL_MODELVIEW); glLoadMatrixf(camera->view_matrix);
        if ((frame.flags & navigation::kXray) != 0U) {
            glDisable(GL_DEPTH_TEST); glEnable(GL_LINE_STIPPLE); glLineStipple(1, 0x0F0F);
            WorldLines(frame, lines, true);
        }
        glDisable(GL_LINE_STIPPLE); glEnable(GL_DEPTH_TEST); glDepthFunc(GL_LEQUAL);
        WorldLines(frame, lines, false);
    }
    ProjectedView(frame, lines, viewport, camera_available);
    glMatrixMode(GL_MODELVIEW); glPopMatrix();
    glMatrixMode(GL_PROJECTION); glPopMatrix();
    glPopAttrib();
    if (use_program) use_program(static_cast<GLuint>(program));
    if (blend_separate) blend_separate(static_cast<GLenum>(equation_rgb), static_cast<GLenum>(equation_alpha));
    else if (blend_equation) blend_equation(static_cast<GLenum>(equation_rgb));
    if (active_texture) active_texture(static_cast<GLenum>(active));
    glMatrixMode(static_cast<GLenum>(matrix_mode));
    return true;
}

}  // namespace wonderbane::extension
