#include "navigation_viewer.h"
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
    GL_POLYGON_OFFSET_LINE, GL_POLYGON_OFFSET_FILL, GL_DITHER, GL_CLIP_PLANE0};
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
    if (argc == 2) {
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
