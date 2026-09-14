#include "navigation_viewer.h"
#include "scene_draw.h"

#include <Windows.h>
#include <gl/GL.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>

namespace wonderbane::extension {
namespace {
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
                   const GLint* viewport, const bool camera_available,
                   const bool live_placement) noexcept {
    const float width = static_cast<float>(viewport[2]);
    const float height = static_cast<float>(viewport[3]);
    const float side = (std::min)({320.0F, width * 0.34F, height - 150.0F});
    // Keep both HUD corners available, including the game's top-right minimap.
    const float left = (width - side) / 2.0F, top = 42.0F;
    const float font = side >= 290.0F ? 2.0F : 1.0F;
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_LINE_STIPPLE);
    glMatrixMode(GL_PROJECTION); glLoadIdentity(); glOrtho(0, width, height, 0, -1, 1);
    glMatrixMode(GL_MODELVIEW); glLoadIdentity();
    glColor4f(0.035F, 0.05F, 0.075F, 0.9F);
    glBegin(GL_QUADS); Quad(left - 6, 8, side + 12, side + 140); glEnd();
    glColor4f(0.9F, 0.93F, 1.0F, 1.0F);
    Text(left, 16, font, live_placement ? "PROJECTED HEIGHT UNKNOWN" : "CAPTURE / PROJECTED ONLY");
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
    Text(left, top + side + 88, 1, !live_placement ? "CAPTURE / LT RIGHT LG UP" :
         (frame.flags & navigation::kFrozen) ? "FROZEN / LT RIGHT LG UP" : "LIVE / LT RIGHT LG UP");
    Text(left, top + side + 100, 1,
         !live_placement ? "WORLD PLACEMENT EXPIRED / SEE PANEL" :
         frame.omitted_lines || frame.status ? "TRUNCATED MODEL / SEE PANEL" :
         !camera_available ? "WORLD CAMERA UNAVAILABLE" :
         (frame.flags & navigation::kXray) ? "WORLD XRAY TRAIL IS DASHED" : "WORLD TRAIL USES SCENE DEPTH");
}
}  // namespace

bool RenderNavigationGeometry(const navigation::FrameHeader& frame,
                              const navigation::Line* const lines,
                              const GraphicsCameraState* const camera,
                              const bool live_placement) noexcept {
    if ((frame.flags & navigation::kEnabled) == 0U || lines == nullptr
        || frame.line_count > navigation::kMaximumLines || !std::isfinite(frame.view_radius)
        || frame.view_radius <= 0.0F || wglGetCurrentContext() == nullptr) return false;
    GLint viewport[4]{};
    glGetIntegerv(GL_VIEWPORT, viewport);
    if (viewport[2] < 480 || viewport[3] < 360) return false;
    const bool camera_available = live_placement && camera != nullptr
        && std::memcmp(camera->viewport, viewport, sizeof(viewport)) == 0;
    struct Draw { const navigation::FrameHeader& frame; const navigation::Line* lines;
                  const GraphicsCameraState* camera; const GLint* viewport;
                  bool camera_available, live_placement; };
    Draw args{frame,lines,camera,viewport,camera_available,live_placement};
    return RenderSceneGeometry(camera_available ? camera : nullptr, [](void* raw) noexcept {
        const auto& args = *static_cast<Draw*>(raw);
        const auto& frame=args.frame; const auto* lines=args.lines;
        const auto* camera=args.camera; const auto* viewport=args.viewport;
        const bool camera_available=args.camera_available, live_placement=args.live_placement;
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
    ProjectedView(frame, lines, viewport, camera_available, live_placement);
    }, &args);
}

}  // namespace wonderbane::extension
