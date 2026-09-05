#include "navigation_viewer.h"
#include "effects_draw.h"
#include "scene_draw.h"
#include "selected_cue_gpu.h"
#include "sky.h"
#include <Windows.h>
#include <gl/GL.h>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <vector>

using namespace wonderbane::extension;
namespace {
int failures = 0;
using ActiveTexture = void(APIENTRY*)(GLenum);
using UseProgram = void(APIENTRY*)(GLuint);
ActiveTexture active_texture = nullptr;
UseProgram use_program = nullptr;
void Check(bool ok, const char* message) {
    if (!ok) { std::fprintf(stderr, "%s\n", message); ++failures; }
}
constexpr GLenum kEnables[] = {GL_DEPTH_TEST, GL_FOG, GL_LIGHTING, GL_BLEND,
    GL_ALPHA_TEST, GL_SCISSOR_TEST, GL_STENCIL_TEST, GL_CULL_FACE, GL_TEXTURE_1D,
    GL_TEXTURE_2D, GL_LINE_STIPPLE, GL_LINE_SMOOTH, GL_COLOR_LOGIC_OP,
    GL_POLYGON_OFFSET_LINE, GL_POLYGON_OFFSET_FILL, GL_DITHER, GL_CLIP_PLANE0,
    GL_POLYGON_STIPPLE, GL_POLYGON_SMOOTH};
struct State {
    std::array<GLboolean, std::size(kEnables)> enables{};
    GLint mode{}, function{}, source{}, destination{};
    GLint viewport[4]{}, scissor[4]{}, polygon[2]{};
    GLboolean depth{}, color[4]{};
    GLint active = 0, program = 0, texture2d[3]{};
    GLfloat model[16]{}, projection[16]{}, texture[16]{}, current[4]{}, width{};
};
State Capture() {
    State state{};
    for (std::size_t i = 0; i < std::size(kEnables); ++i) state.enables[i] = glIsEnabled(kEnables[i]);
    glGetIntegerv(GL_MATRIX_MODE, &state.mode); glGetIntegerv(GL_DEPTH_FUNC, &state.function);
    glGetIntegerv(GL_BLEND_SRC, &state.source); glGetIntegerv(GL_BLEND_DST, &state.destination);
    glGetIntegerv(GL_VIEWPORT, state.viewport); glGetIntegerv(GL_SCISSOR_BOX, state.scissor);
    glGetIntegerv(GL_POLYGON_MODE, state.polygon);
    glGetBooleanv(GL_DEPTH_WRITEMASK, &state.depth); glGetBooleanv(GL_COLOR_WRITEMASK, state.color);
    glGetFloatv(GL_MODELVIEW_MATRIX, state.model); glGetFloatv(GL_PROJECTION_MATRIX, state.projection);
    glGetFloatv(GL_TEXTURE_MATRIX, state.texture); glGetFloatv(GL_CURRENT_COLOR, state.current);
    glGetFloatv(GL_LINE_WIDTH, &state.width);
    if (use_program) glGetIntegerv(0x8B8DU, &state.program);
    if (active_texture) {
        glGetIntegerv(0x84E0U, &state.active);
        for (unsigned i = 0; i < 3U; ++i) {
            active_texture(0x84C0U + i);
            state.texture2d[i] = glIsEnabled(GL_TEXTURE_2D);
        }
        active_texture(static_cast<GLenum>(state.active));
    }
    return state;
}
void Same(const State& a, const State& b) {
    Check(a.enables == b.enables, "enable state restored");
    Check(a.active == b.active && a.program == b.program
        && std::memcmp(a.texture2d,b.texture2d,sizeof(a.texture2d)) == 0,
        "GLSL program and all sampled texture units restored");
    Check(a.mode == b.mode && a.function == b.function && a.source == b.source
          && a.destination == b.destination && a.depth == b.depth && a.width == b.width, "scalar state restored");
    Check(std::memcmp(a.viewport,b.viewport,sizeof(a.viewport)) == 0
        && std::memcmp(a.scissor,b.scissor,sizeof(a.scissor)) == 0
        && std::memcmp(a.polygon,b.polygon,sizeof(a.polygon)) == 0
        && std::memcmp(a.color,b.color,sizeof(a.color)) == 0, "viewport/mask state restored");
    Check(std::memcmp(a.model,b.model,sizeof(a.model)) == 0
        && std::memcmp(a.projection,b.projection,sizeof(a.projection)) == 0
        && std::memcmp(a.texture,b.texture,sizeof(a.texture)) == 0
        && std::memcmp(a.current,b.current,sizeof(a.current)) == 0, "matrices/current color restored");
}
unsigned ColoredPixels() {
    std::array<unsigned char, 100U * 5U * 3U> pixels{};
    glReadPixels(42, 237, 100, 5, GL_RGB, GL_UNSIGNED_BYTE, pixels.data());
    unsigned count = 0;
    for (std::size_t i = 0; i < pixels.size(); i += 3U) {
        if (pixels[i] || pixels[i+1] || pixels[i+2]) ++count;
    }
    return count;
}
// Production render functions share the real WGL context and state guard.
// This checks composition/resource ownership, not native transparency acceptance.
void CombinedProbe(const GraphicsCameraState& camera, bool measure) {
    const State original = Capture();
    HRSRC resource = FindResourceW(GetModuleHandleW(nullptr), MAKEINTRESOURCEW(201), RT_RCDATA);
    Check(resource && SizeofResource(GetModuleHandleW(nullptr), resource) == sizeof(sky::Asset),
          "combined test uses packaged sky asset");
    if (!resource) return;
    sky::Asset asset{};
    const void* bytes = LockResource(LoadResource(GetModuleHandleW(nullptr), resource));
    Check(bytes != nullptr, "load combined sky asset"); if (!bytes) return;
    std::memcpy(&asset, bytes, sizeof(asset));
    struct Combination { const GraphicsCameraState* camera; const sky::Asset* asset; unsigned flags; bool verify; };
    LARGE_INTEGER frequency{}; QueryPerformanceFrequency(&frequency);
    for (unsigned flags = 0; flags < 16; ++flags) {
        cue::ReleaseMask();
        Combination combination{&camera, &asset, flags, !measure};
        LARGE_INTEGER begin{}, end{}; glFinish(); QueryPerformanceCounter(&begin);
        const unsigned frames = measure ? 8U : 1U;
        for (unsigned frame = 0; frame < frames; ++frame) {
            Check(RenderSceneGeometry(&camera, [](void* value) noexcept {
                const auto& c = *static_cast<Combination*>(value);
                glDepthMask(GL_TRUE); glClearDepth(1); glClearColor(0,0,0,1);
                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
                const auto before_sky = c.verify ? Capture() : State{};
                if (c.flags & 8U) {
                    sky::Settings settings{}; settings.enabled = 1;
                    Check(sky::Render(*c.asset, settings, *c.camera), "combined early sky");
                }
                if(c.verify) Same(before_sky, Capture());
                if (c.flags & 4U) Check(cue::BeginMask(), "combined cue begin");
                glEnable(GL_DEPTH_TEST); glDepthFunc(GL_LESS); glDepthMask(GL_TRUE);
                glDisable(GL_BLEND); glColor4f(0,0,0,1);
                const GLfloat vertices[]{-.25F,-.5F,0,.25F,-.5F,0,.25F,.5F,0,-.25F,.5F,0};
                glPushClientAttrib(GL_CLIENT_VERTEX_ARRAY_BIT);
                glEnableClientState(GL_VERTEX_ARRAY); glVertexPointer(3,GL_FLOAT,0,vertices);
                auto mesh=[](void*) noexcept { glDrawArrays(GL_QUADS,0,4); };
                for (unsigned node=0; node<46; ++node) {
                    if (c.flags & 4U) {
                        Check(cue::BeforeOwnedDraw(), "combined owned wrapper");
                        const auto material = c.verify ? Capture() : State{};
                        Check(cue::CaptureGeometry(mesh,nullptr), "combined raw material capture");
                        if(c.verify) Same(material, Capture());
                    }
                    mesh(nullptr);
                    if (c.flags & 4U) Check(cue::AfterOwnedDraw(), "combined owned wrapper complete");
                }
                glPopClientAttrib();
                const auto before_overlays = c.verify ? Capture() : State{};
                GLfloat depth_before=0,depth_after=0;
                if(c.verify) glReadPixels(c.camera->viewport[2]/2,c.camera->viewport[3]/2,1,1,GL_DEPTH_COMPONENT,GL_FLOAT,&depth_before);
                if (c.flags & 4U) {
                    cue::Settings settings{}; settings.enabled=1;
                    Check(cue::CompositeMask(settings,{}), "combined whole-character cue");
                }
                if(c.verify) Same(before_overlays, Capture());
                if (c.flags & 2U) {
                    effects::Config config{}; config.flags=1;
                    effects::Geometry geometry{}; geometry.count=1;
                    geometry.quads[0]={{{-.85F,-.05F,-.2F},{-.6F,-.05F,-.2F},
                        {-.6F,.05F,-.2F},{-.85F,.05F,-.2F}},.7F,.2F};
                    Check(RenderEffectsGeometry(config,geometry,*c.camera), "combined particles");
                }
                if(c.verify) Same(before_overlays, Capture());
                if (c.flags & 1U) {
                    navigation::FrameHeader frame{};
                    frame.flags=navigation::kEnabled|navigation::kUnknownHeight;
                    frame.layer_mask=navigation::kAllLayers; frame.line_count=1; frame.view_radius=50;
                    navigation::Line line{navigation::kTrailLayer,navigation::kWorldHeight,
                        {-.85F,.1F,-.2F},{-.6F,.1F,-.2F}};
                    Check(RenderNavigationGeometry(frame,&line,c.camera), "combined navigation");
                }
                if(c.verify) Same(before_overlays, Capture());
                if(c.verify) glReadPixels(c.camera->viewport[2]/2,c.camera->viewport[3]/2,1,1,GL_DEPTH_COMPONENT,GL_FLOAT,&depth_after);
                Check(depth_before == depth_after, "combined overlays preserve native scene depth");
            }, &combination), "combined scene guard");
            if(!measure) Same(original, Capture());
        }
        glFinish(); QueryPerformanceCounter(&end);
        const auto allocated=cue::AllocatedMaskBytes();
        if (measure) std::printf("Combined flags=%u (nav1/effects2/cue4/sky8),46 nodes: %.3f ms/frame, cue=%llu bytes\n",
            flags,1000.0*static_cast<double>(end.QuadPart-begin.QuadPart)/frequency.QuadPart/frames,
            static_cast<unsigned long long>(allocated));
        Check(allocated <= static_cast<std::uint64_t>(camera.viewport[2])*camera.viewport[3]*8, "combined raw mesh resource bound");
        cue::DiscardMask(); cue::ReleaseMask();
        Check(cue::AllocatedMaskBytes()==0, "combined interruption releases cue resources");
        Same(original,Capture());
    }
}

// Quantifies the late-pass limitation without treating it as accepted behavior.
// --verify-native-transparency turns the outstanding requirement into a failing
// acceptance probe; normal regressions still validate the reference fixture.
void TransparencyProbe(const GraphicsCameraState& camera, bool require_correct) {
    effects::Geometry geometry{};
    geometry.count = 1;
    geometry.quads[0] = {{{-0.85F,-0.05F,-0.2F},{-0.6F,-0.05F,-0.2F},
                          {-0.6F,0.05F,-0.2F},{-0.85F,0.05F,-0.2F}},1.0F,0.0F};
    effects::Config config{};
    config.flags = 1; config.red = 0; config.green = 0; config.blue = 1;
    const State original = Capture();
    auto reset = [&]() {
        Check(RenderSceneGeometry(&camera, [](void*) noexcept {
            glDepthMask(GL_TRUE); glClearDepth(1.0); glClearColor(0,0,0,1);
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        }, nullptr), "prepare transparency fixture");
    };
    auto glass = [&](bool writes_depth) {
        Check(RenderSceneGeometry(&camera, [](void* raw) noexcept {
            glDepthMask(*static_cast<bool*>(raw) ? GL_TRUE : GL_FALSE);
            glColor4f(1,0,0,0.5F);
            glBegin(GL_QUADS);
            glVertex3f(-0.85F,-0.05F,-0.6F); glVertex3f(-0.6F,-0.05F,-0.6F);
            glVertex3f(-0.6F,0.05F,-0.6F); glVertex3f(-0.85F,0.05F,-0.6F);
            glEnd();
        }, &writes_depth), "native-style foreground alpha surface");
    };
    for (bool in_front : {false, true}) {
      for (auto& point : geometry.quads[0].points) point.z = in_front ? -0.8F : -0.2F;
      for (bool writes_depth : {false, true}) {
        unsigned char reference[3]{}, actual[3]{}, early[3]{};
        reset();
        if (in_front) glass(writes_depth);
        Check(RenderEffectsGeometry(config, geometry, camera), "reference ordered effect");
        if (!in_front) glass(writes_depth);
        glReadPixels(100,240,1,1,GL_RGB,GL_UNSIGNED_BYTE,reference);
        Check(std::abs(int(reference[0])-(in_front ? 0 : 128))<=2 && reference[1]==0
              && std::abs(int(reference[2])-(in_front ? 255 : 128))<=2,
              "reference alpha transmission in both relative depth orders");
        reset(); glass(writes_depth);
        Check(RenderEffectsGeometry(config, geometry, camera), "current late effect");
        glReadPixels(100,240,1,1,GL_RGB,GL_UNSIGNED_BYTE,actual);
        const int error = std::abs(int(actual[0])-int(reference[0]))
                        + std::abs(int(actual[1])-int(reference[1]))
                        + std::abs(int(actual[2])-int(reference[2]));
        reset();
        Check(RenderEffectsGeometry(config, geometry, camera), "early-pass counterexample");
        glass(writes_depth);
        glReadPixels(100,240,1,1,GL_RGB,GL_UNSIGNED_BYTE,early);
        // Drawing every effect earlier is also wrong: a behind native fragment
        // blends over front particles, because particles must not write depth.
        if (in_front) Check(early[0] > 120 && early[2] < 135,
                            "wholesale early pass cannot satisfy front effect ordering");
        std::printf("Native transparency requirement: effect-front=%d depth-write=%d expected RGB=%u,%u,%u "
                    "late-pass RGB=%u,%u,%u absolute error=%d/765 %s\n",
                    int(in_front), int(writes_depth), unsigned(reference[0]), unsigned(reference[1]),
                    unsigned(reference[2]), unsigned(actual[0]), unsigned(actual[1]),
                    unsigned(actual[2]), error, error<=6 ? "PASS" : "UNRESOLVED");
        if (require_correct) Check(error<=6, "native/effect transparency must respect relative depth");
        Same(original, Capture());
      }
    }
    // Before/after scene RGBA+depth cannot recover source alpha. A translucent
    // surface matching the existing RGB leaves identical scene samples for
    // different alpha values, but must attenuate a behind effect differently.
    std::array<std::array<unsigned char,4>,2> observed{}, required{};
    std::array<float,2> observed_depth{};
    for (auto& point : geometry.quads[0].points) point.z = -0.2F;
    for (unsigned sample=0;sample<2;++sample) {
        float alpha=sample ? 0.75F : 0.25F;
        auto background = [&]() {
            Check(RenderSceneGeometry(&camera, [](void*) noexcept {
                glDepthMask(GL_TRUE);glClearDepth(1);glClearColor(0,0,0,1);
                glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
            }, nullptr), "prepare transmission information fixture");
        };
        auto surface = [&]() {
            Check(RenderSceneGeometry(&camera, [](void* raw) noexcept {
                glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_FALSE);
                glColor4f(0,0,0,*static_cast<float*>(raw));
                glBegin(GL_QUADS);
                glVertex3f(-0.85F,-0.05F,-0.6F);glVertex3f(-0.6F,-0.05F,-0.6F);
                glVertex3f(-0.6F,0.05F,-0.6F);glVertex3f(-0.85F,0.05F,-0.6F);
                glEnd();
            }, &alpha), "draw ambiguous native transmission");
        };
        background();surface();
        glReadPixels(100,240,1,1,GL_RGBA,GL_UNSIGNED_BYTE,observed[sample].data());
        glReadPixels(100,240,1,1,GL_DEPTH_COMPONENT,GL_FLOAT,&observed_depth[sample]);
        background();
        Check(RenderEffectsGeometry(config,geometry,camera), "reference transmitted effect");
        surface();
        glReadPixels(100,240,1,1,GL_RGBA,GL_UNSIGNED_BYTE,required[sample].data());
        Same(original,Capture());
    }
    Check(observed[0]==observed[1] && observed_depth[0]==observed_depth[1],
          "different native alpha can leave identical scene RGBA and depth");
    Check(std::abs(int(required[0][2])-191)<=2 && std::abs(int(required[1][2])-64)<=2,
          "identical observed scene requires distinct effect transmission");
    std::printf("Transmission information: identical scene RGBA/depth, required behind blue=%u vs %u; "
                "source alpha is not recoverable from scene snapshots\n",
                unsigned(required[0][2]),unsigned(required[1][2]));
}

}
int main(int argc, char** argv) {
    WNDCLASSW klass{};
    klass.style = CS_OWNDC; klass.lpfnWndProc = DefWindowProcW;
    klass.hInstance = GetModuleHandleW(nullptr); klass.lpszClassName = L"WonderBaneNavigationDrawTest";
    if (!RegisterClassW(&klass)) return 2;
    RECT bounds{0,0,640,480}; AdjustWindowRect(&bounds, WS_OVERLAPPEDWINDOW, FALSE);
    HWND window = CreateWindowW(klass.lpszClassName, L"", WS_OVERLAPPEDWINDOW,
                                0, 0, bounds.right-bounds.left, bounds.bottom-bounds.top,
                                nullptr, nullptr, klass.hInstance, nullptr);
    if (!window) return 3;
    HDC dc = GetDC(window);
    PIXELFORMATDESCRIPTOR format{};
    format.nSize = sizeof(format); format.nVersion = 1;
    format.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
    format.iPixelType = PFD_TYPE_RGBA; format.cColorBits = 32; format.cDepthBits = 24;
    format.cStencilBits = 8; format.iLayerType = PFD_MAIN_PLANE;
    const int index = ChoosePixelFormat(dc, &format);
    if (!index || !SetPixelFormat(dc, index, &format)) return 4;
    HGLRC context = wglCreateContext(dc);
    if (!context || !wglMakeCurrent(dc, context)) return 5;
    std::printf("OpenGL draw test: %s\n", glGetString(GL_VERSION));
    const bool combined_render = argc == 2 && (
        std::strcmp(argv[1], "--combined-render") == 0
        || std::strcmp(argv[1], "--combined-cost") == 0
        || std::strcmp(argv[1], "--combined-cost-1080") == 0);
    if (combined_render && !wglGetProcAddress("glGenFramebuffers")) {
        std::fprintf(stderr, "SKIP: combined cue rendering requires framebuffer objects\n");
        wglMakeCurrent(nullptr, nullptr); wglDeleteContext(context);
        ReleaseDC(window, dc); DestroyWindow(window);
        UnregisterClassW(klass.lpszClassName, klass.hInstance);
        return 77;
    }
    glViewport(0,0,640,480); glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glClearColor(0,0,0,1); glClearDepth(0.5); glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    glEnable(GL_FOG); glEnable(GL_LIGHTING); glEnable(GL_ALPHA_TEST);
    glEnable(GL_SCISSOR_TEST); glScissor(3,4,5,6);
    glEnable(GL_TEXTURE_2D); glEnable(GL_LINE_STIPPLE); glLineStipple(2, 0x3333);
    glEnable(GL_DEPTH_TEST); glDepthFunc(GL_GREATER); glDepthMask(GL_TRUE);
    glBlendFunc(GL_ONE, GL_ZERO); glLineWidth(2.0F); glPolygonMode(GL_FRONT_AND_BACK, GL_LINE);
    glColorMask(GL_FALSE,GL_TRUE,GL_FALSE,GL_TRUE); glColor4f(0.1F,0.2F,0.3F,0.4F);
    glMatrixMode(GL_MODELVIEW); glLoadIdentity(); glTranslatef(1,2,3);
    glMatrixMode(GL_PROJECTION); glLoadIdentity(); glScalef(2,3,4);
    glMatrixMode(GL_TEXTURE); glLoadIdentity(); glTranslatef(4,5,6);
    active_texture = reinterpret_cast<ActiveTexture>(wglGetProcAddress("glActiveTexture"));
    use_program = reinterpret_cast<UseProgram>(wglGetProcAddress("glUseProgram"));
    if (active_texture) {
        active_texture(0x84C0U); glEnable(GL_TEXTURE_2D);
        active_texture(0x84C1U); glDisable(GL_TEXTURE_2D);
        active_texture(0x84C2U); glEnable(GL_TEXTURE_2D);
    }
    if (use_program) {
        const auto create_shader = reinterpret_cast<GLuint(APIENTRY*)(GLenum)>(wglGetProcAddress("glCreateShader"));
        const auto shader_source = reinterpret_cast<void(APIENTRY*)(GLuint, GLsizei, const char* const*, const GLint*)>(wglGetProcAddress("glShaderSource"));
        const auto compile = reinterpret_cast<void(APIENTRY*)(GLuint)>(wglGetProcAddress("glCompileShader"));
        const auto create_program = reinterpret_cast<GLuint(APIENTRY*)()>(wglGetProcAddress("glCreateProgram"));
        const auto attach = reinterpret_cast<void(APIENTRY*)(GLuint, GLuint)>(wglGetProcAddress("glAttachShader"));
        const auto link = reinterpret_cast<void(APIENTRY*)(GLuint)>(wglGetProcAddress("glLinkProgram"));
        const auto status = reinterpret_cast<void(APIENTRY*)(GLuint, GLenum, GLint*)>(wglGetProcAddress("glGetProgramiv"));
        const char* vertex_source = "#version 110\nvoid main(){gl_Position=ftransform();}";
        const char* fragment_source = "#version 110\nvoid main(){gl_FragColor=vec4(1.,0.,0.,1.);}";
        const GLuint vertex = create_shader(0x8B31U), fragment = create_shader(0x8B30U);
        shader_source(vertex, 1, &vertex_source, nullptr); compile(vertex);
        shader_source(fragment, 1, &fragment_source, nullptr); compile(fragment);
        const GLuint program = create_program(); attach(program, vertex); attach(program, fragment); link(program);
        GLint linked = 0; status(program, 0x8B82U, &linked);
        Check(linked != 0, "prepare nondefault GLSL owner");
        if (linked) use_program(program);
        // All objects belong to this test context and are released with it.
    }
    const State state = Capture();
    navigation::FrameHeader frame{};
    frame.flags = navigation::kEnabled | navigation::kUnknownHeight;
    frame.layer_mask = navigation::kAllLayers; frame.line_count = 1; frame.view_radius = 50;
    navigation::Line line{navigation::kTrailLayer, navigation::kWorldHeight,
        {-0.85F,0.0F,0.2F}, {-0.6F,0.0F,0.2F}};
    GraphicsCameraState camera{};
    for (unsigned i = 0; i < 16U; i += 5U) camera.view_matrix[i] = camera.projection_matrix[i] = 1;
    camera.viewport[2] = 640; camera.viewport[3] = 480;
    Check(RenderNavigationGeometry(frame, &line, &camera), "render normal inspector");
    glFinish(); Same(state, Capture());
    Check(ColoredPixels() == 0, "normal trail is occluded by scene depth");
    GLfloat depth = 0; glReadPixels(100,240,1,1,GL_DEPTH_COMPONENT,GL_FLOAT,&depth);
    Check(std::fabs(depth - 0.5F) < 0.0001F, "inspector never writes scene depth");
    frame.flags |= navigation::kXray;
    Check(RenderNavigationGeometry(frame, &line, &camera), "render distinct xray");
    glFinish(); Same(state, Capture());
    const auto xray = ColoredPixels();
    Check(xray > 0 && xray < 90, "xray is visibly dashed behind depth");
    frame.flags &= ~navigation::kXray;
    line.start[2] = line.end[2] = -0.2F;
    Check(RenderNavigationGeometry(frame, &line, &camera), "render visible measured trail");
    glFinish(); Same(state, Capture());
    Check(ColoredPixels() > xray, "visible trail is solid");
    glReadPixels(100,240,1,1,GL_DEPTH_COMPONENT,GL_FLOAT,&depth);
    Check(std::fabs(depth - 0.5F) < 0.0001F, "visible pass also preserves scene depth");
    glPushAttrib(GL_ALL_ATTRIB_BITS);
    glDisable(GL_SCISSOR_TEST); glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
    glClear(GL_COLOR_BUFFER_BIT); glPopAttrib();
    frame.flags |= navigation::kXray;
    Check(RenderNavigationGeometry(frame, &line, &camera, false), "expired capture still draws projected map");
    glFinish(); Same(state, Capture());
    Check(ColoredPixels() == 0, "expired capture never draws world trail even with a camera and xray");
    unsigned char center_pixel[3]{}, hud_pixel[3]{};
    glReadPixels(320,450,1,1,GL_RGB,GL_UNSIGNED_BYTE,center_pixel);
    glReadPixels(620,440,1,1,GL_RGB,GL_UNSIGNED_BYTE,hud_pixel);
    Check(center_pixel[0] || center_pixel[1] || center_pixel[2], "projected capture persists near top center");
    Check(!(hud_pixel[0] || hud_pixel[1] || hud_pixel[2]), "top-right minimap region remains clear");
    frame.flags &= ~navigation::kXray;
    LARGE_INTEGER frequency{}, begin{}, end{};
    QueryPerformanceFrequency(&frequency); glFinish(); QueryPerformanceCounter(&begin);
    for (unsigned sample = 0; sample < 20U; ++sample) {
        (void)RenderNavigationGeometry(frame, &line, &camera);
    }
    glFinish(); QueryPerformanceCounter(&end);
    std::printf("Enabled draw mean (test context, one trail segment): %.3f ms\n",
        1000.0 * static_cast<double>(end.QuadPart - begin.QuadPart)
        / static_cast<double>(frequency.QuadPart) / 20.0);
    std::vector<navigation::Line> bounded(navigation::kMaximumLines, line);
    frame.line_count = static_cast<std::uint32_t>(bounded.size());
    QueryPerformanceCounter(&begin);
    for (unsigned sample = 0; sample < 5U; ++sample) {
        (void)RenderNavigationGeometry(frame, bounded.data(), &camera);
    }
    glFinish(); QueryPerformanceCounter(&end);
    std::printf("Maximum line capacity draw mean (test context): %.3f ms\n",
        1000.0 * static_cast<double>(end.QuadPart - begin.QuadPart)
        / static_cast<double>(frequency.QuadPart) / 5.0);
    // Exercise the production effects renderer against a real depth buffer.
    glPushAttrib(GL_ALL_ATTRIB_BITS);
    glDisable(GL_SCISSOR_TEST); glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
    glClear(GL_COLOR_BUFFER_BIT); glPopAttrib();
    effects::Geometry effect_geometry{};
    effect_geometry.count=1;
    effect_geometry.quads[0]={{{-0.85F,-0.05F,0.2F},{-0.6F,-0.05F,0.2F},
                              {-0.6F,0.05F,0.2F},{-0.85F,0.05F,0.2F}},0.7F,0.2F};
    effects::Config effect_config{}; effect_config.flags=1;
    Check(RenderEffectsGeometry(effect_config,effect_geometry,camera),"production effect draw");
    glFinish(); Same(state,Capture());
    Check(ColoredPixels()==0,"effect behind scene depth is occluded");
    for (auto& point:effect_geometry.quads[0].points) point.z=-0.2F;
    Check(RenderEffectsGeometry(effect_config,effect_geometry,camera),"visible particle quad");
    glFinish(); Same(state,Capture());
    Check(ColoredPixels()>0,"visible particle has coverage");
    glReadPixels(100,240,1,1,GL_DEPTH_COMPONENT,GL_FLOAT,&depth);
    Check(std::fabs(depth-0.5F)<0.0001F,"particles preserve scene depth");
    effect_config.flags=9;
    Check(RenderEffectsGeometry(effect_config,effect_geometry,camera),"additive burst");
    glFinish(); Same(state,Capture());
    effect_config.flags=0;
    Check(!RenderEffectsGeometry(effect_config,effect_geometry,camera),"disabled effects draw nothing");
    Same(state,Capture());
    const bool verify_transparency = argc == 2
        && std::strcmp(argv[1], "--verify-native-transparency") == 0;
    const bool cost_1080 = argc == 2 && std::strcmp(argv[1], "--combined-cost-1080") == 0;
    const bool combined_cost = cost_1080 || (argc == 2 && std::strcmp(argv[1], "--combined-cost") == 0);
    if (cost_1080) {
        RECT larger{0,0,1920,1080}; AdjustWindowRect(&larger,WS_OVERLAPPEDWINDOW,FALSE);
        Check(SetWindowPos(window,nullptr,0,0,larger.right-larger.left,larger.bottom-larger.top,
            SWP_NOZORDER|SWP_NOACTIVATE)!=0,"resize real combined test framebuffer");
        GraphicsCameraState larger_camera=camera;larger_camera.viewport[2]=1920;larger_camera.viewport[3]=1080;
        glViewport(0,0,1920,1080);CombinedProbe(larger_camera,true);
        Check(SetWindowPos(window,nullptr,0,0,bounds.right-bounds.left,bounds.bottom-bounds.top,
            SWP_NOZORDER|SWP_NOACTIVATE)!=0,"restore real test framebuffer");
        glViewport(0,0,640,480);
    } else if (combined_render) CombinedProbe(camera, combined_cost);
    TransparencyProbe(camera, verify_transparency);
    if (argc == 2 && !verify_transparency && !combined_render) {
        // Synthetic test framebuffer only. Capture happens outside the renderer.
        std::vector<unsigned char> pixels(640U*480U*3U);
        glReadPixels(0,0,640,480,GL_RGB,GL_UNSIGNED_BYTE,pixels.data());
        std::ofstream output(argv[1], std::ios::binary);
        output << "P6\n640 480\n255\n";
        for (int row = 479; row >= 0; --row) {
            output.write(reinterpret_cast<const char*>(pixels.data() + static_cast<std::size_t>(row)*640U*3U), 640*3);
        }
        Check(output.good(), "write synthetic framebuffer evidence");
    }
    frame.flags = 0;
    Check(!RenderNavigationGeometry(frame, &line, &camera), "disabled viewer has no draw");
    Same(state, Capture());
    Check(glGetError() == GL_NO_ERROR, "no GL state errors");
    wglMakeCurrent(nullptr, nullptr); wglDeleteContext(context);
    ReleaseDC(window, dc); DestroyWindow(window); UnregisterClassW(klass.lpszClassName, klass.hInstance);
    return failures ? 1 : 0;
}
