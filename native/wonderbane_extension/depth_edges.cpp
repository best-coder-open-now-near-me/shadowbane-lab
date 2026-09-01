#include "depth_edges.h"

#include "graphics_status.h"

#include <Windows.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>

namespace wonderbane::extension {
namespace {

constexpr unsigned int kGlActiveTexture = 0x84E0U;
constexpr unsigned int kGlAllAttribBits = 0x000FFFFFU;
constexpr unsigned int kGlAlphaTest = 0x0BC0U;
constexpr unsigned int kGlBlend = 0x0BE2U;
constexpr unsigned int kGlClampToEdge = 0x812FU;
constexpr unsigned int kGlColorLogicOp = 0x0BF2U;
constexpr unsigned int kGlCompileStatus = 0x8B81U;
constexpr unsigned int kGlCullFace = 0x0B44U;
constexpr unsigned int kGlCurrentProgram = 0x8B8DU;
constexpr unsigned int kGlDepthComponent = 0x1902U;
constexpr unsigned int kGlDepthComponent24 = 0x81A6U;
constexpr unsigned int kGlDepthTest = 0x0B71U;
constexpr unsigned int kGlDither = 0x0BD0U;
constexpr unsigned int kGlFog = 0x0B60U;
constexpr unsigned int kGlFragmentShader = 0x8B30U;
constexpr unsigned int kGlLighting = 0x0B50U;
constexpr unsigned int kGlLinkStatus = 0x8B82U;
constexpr unsigned int kGlMatrixMode = 0x0BA0U;
constexpr unsigned int kGlModelView = 0x1700U;
constexpr unsigned int kGlNearest = 0x2600U;
constexpr unsigned int kGlNoError = 0U;
constexpr unsigned int kGlOneMinusSrcAlpha = 0x0303U;
constexpr unsigned int kGlProjection = 0x1701U;
constexpr unsigned int kGlQuads = 0x0007U;
constexpr unsigned int kGlScissorTest = 0x0C11U;
constexpr unsigned int kGlSrcAlpha = 0x0302U;
constexpr unsigned int kGlStencilTest = 0x0B90U;
constexpr unsigned int kGlTexture0 = 0x84C0U;
constexpr unsigned int kGlTexture2D = 0x0DE1U;
constexpr unsigned int kGlTextureBinding2D = 0x8069U;
constexpr unsigned int kGlTextureMagFilter = 0x2800U;
constexpr unsigned int kGlTextureMinFilter = 0x2801U;
constexpr unsigned int kGlTextureWrapS = 0x2802U;
constexpr unsigned int kGlTextureWrapT = 0x2803U;
constexpr unsigned int kGlUnsignedInt = 0x1405U;
constexpr unsigned int kGlVertexShader = 0x8B31U;
constexpr float kRelativeDepthThreshold = 0.0125F;
constexpr float kAbsoluteDepthThreshold = 0.04F;

using GlActiveTexture = void(APIENTRY*)(unsigned int texture);
using GlAttachShader = void(APIENTRY*)(unsigned int program, unsigned int shader);
using GlBegin = void(APIENTRY*)(unsigned int mode);
using GlBindTexture = void(APIENTRY*)(unsigned int target, unsigned int texture);
using GlBlendFunc = void(APIENTRY*)(unsigned int source, unsigned int destination);
using GlColorMask = void(APIENTRY*)(
    unsigned char red,
    unsigned char green,
    unsigned char blue,
    unsigned char alpha
);
using GlCompileShader = void(APIENTRY*)(unsigned int shader);
using GlCopyTexSubImage2D = void(APIENTRY*)(
    unsigned int target,
    int level,
    int x_offset,
    int y_offset,
    int x,
    int y,
    int width,
    int height
);
using GlCreateProgram = unsigned int(APIENTRY*)();
using GlCreateShader = unsigned int(APIENTRY*)(unsigned int type);
using GlDeleteProgram = void(APIENTRY*)(unsigned int program);
using GlDeleteShader = void(APIENTRY*)(unsigned int shader);
using GlDepthMask = void(APIENTRY*)(unsigned char enabled);
using GlDisable = void(APIENTRY*)(unsigned int capability);
using GlEnable = void(APIENTRY*)(unsigned int capability);
using GlEnd = void(APIENTRY*)();
using GlGenTextures = void(APIENTRY*)(int count, unsigned int* textures);
using GlGetError = unsigned int(APIENTRY*)();
using GlGetIntegerv = void(APIENTRY*)(unsigned int name, int* value);
using GlGetProgramInfoLog = void(APIENTRY*)(
    unsigned int program,
    int capacity,
    int* length,
    char* log
);
using GlGetProgramiv = void(APIENTRY*)(
    unsigned int program,
    unsigned int name,
    int* value
);
using GlGetShaderInfoLog = void(APIENTRY*)(
    unsigned int shader,
    int capacity,
    int* length,
    char* log
);
using GlGetShaderiv = void(APIENTRY*)(
    unsigned int shader,
    unsigned int name,
    int* value
);
using GlGetUniformLocation = int(APIENTRY*)(unsigned int program, const char* name);
using GlIsProgram = unsigned char(APIENTRY*)(unsigned int program);
using GlLinkProgram = void(APIENTRY*)(unsigned int program);
using GlLoadIdentity = void(APIENTRY*)();
using GlMatrixMode = void(APIENTRY*)(unsigned int mode);
using GlPopAttrib = void(APIENTRY*)();
using GlPopMatrix = void(APIENTRY*)();
using GlPushAttrib = void(APIENTRY*)(unsigned int mask);
using GlPushMatrix = void(APIENTRY*)();
using GlShaderSource = void(APIENTRY*)(
    unsigned int shader,
    int count,
    const char* const* strings,
    const int* lengths
);
using GlTexCoord2f = void(APIENTRY*)(float s, float t);
using GlTexImage2D = void(APIENTRY*)(
    unsigned int target,
    int level,
    int internal_format,
    int width,
    int height,
    int border,
    unsigned int format,
    unsigned int type,
    const void* pixels
);
using GlTexParameteri = void(APIENTRY*)(
    unsigned int target,
    unsigned int name,
    int value
);
using GlUniform1i = void(APIENTRY*)(int location, int value);
using GlUniform2f = void(APIENTRY*)(int location, float first, float second);
using GlUniform3f = void(APIENTRY*)(
    int location,
    float first,
    float second,
    float third
);
using GlUseProgram = void(APIENTRY*)(unsigned int program);
using GlVertex2f = void(APIENTRY*)(float x, float y);
using WglGetCurrentContext = HGLRC(WINAPI*)();
using WglGetProcAddress = PROC(WINAPI*)(LPCSTR name);

struct DepthEdgeApi {
    GlActiveTexture active_texture = nullptr;
    GlAttachShader attach_shader = nullptr;
    GlBegin begin = nullptr;
    GlBindTexture bind_texture = nullptr;
    GlBlendFunc blend_func = nullptr;
    GlColorMask color_mask = nullptr;
    GlCompileShader compile_shader = nullptr;
    GlCopyTexSubImage2D copy_tex_sub_image_2d = nullptr;
    GlCreateProgram create_program = nullptr;
    GlCreateShader create_shader = nullptr;
    GlDeleteProgram delete_program = nullptr;
    GlDeleteShader delete_shader = nullptr;
    GlDepthMask depth_mask = nullptr;
    GlDisable disable = nullptr;
    GlEnable enable = nullptr;
    GlEnd end = nullptr;
    GlGenTextures gen_textures = nullptr;
    GlGetError get_error = nullptr;
    GlGetIntegerv get_integerv = nullptr;
    GlGetProgramInfoLog get_program_info_log = nullptr;
    GlGetProgramiv get_programiv = nullptr;
    GlGetShaderInfoLog get_shader_info_log = nullptr;
    GlGetShaderiv get_shaderiv = nullptr;
    GlGetUniformLocation get_uniform_location = nullptr;
    GlIsProgram is_program = nullptr;
    GlLinkProgram link_program = nullptr;
    GlLoadIdentity load_identity = nullptr;
    GlMatrixMode matrix_mode = nullptr;
    GlPopAttrib pop_attrib = nullptr;
    GlPopMatrix pop_matrix = nullptr;
    GlPushAttrib push_attrib = nullptr;
    GlPushMatrix push_matrix = nullptr;
    GlShaderSource shader_source = nullptr;
    GlTexCoord2f tex_coord_2f = nullptr;
    GlTexImage2D tex_image_2d = nullptr;
    GlTexParameteri tex_parameter_i = nullptr;
    GlUniform1i uniform_1i = nullptr;
    GlUniform2f uniform_2f = nullptr;
    GlUniform3f uniform_3f = nullptr;
    GlUseProgram use_program = nullptr;
    GlVertex2f vertex_2f = nullptr;
    WglGetCurrentContext get_current_context = nullptr;
    WglGetProcAddress get_proc_address = nullptr;
};

struct DepthEdgeRuntime {
    HGLRC context = nullptr;
    DepthEdgeApi api{};
    unsigned int program = 0U;
    unsigned int depth_texture = 0U;
    int sampler_location = -1;
    int texel_size_location = -1;
    int projection_location = -1;
    int texture_width = 0;
    int texture_height = 0;
    LONG generation = 0;
    bool failed = false;
};

struct DepthEdgeFrame {
    std::array<float, 16U> projection{};
    std::array<int, 4U> viewport{};
    bool pending = false;
    bool composited = false;
};

volatile LONG g_generation = 1;
thread_local DepthEdgeRuntime g_runtime{};
thread_local DepthEdgeFrame g_frame{};

const char kVertexSource[] = R"glsl(#version 120
varying vec2 wbDepthUv;

void main() {
    gl_Position = gl_Vertex;
    wbDepthUv = gl_MultiTexCoord0.st;
}
)glsl";

const char kFragmentSource[] = R"glsl(#version 120
uniform sampler2D wbDepthTexture;
uniform vec2 wbTexelSize;
uniform vec3 wbProjection;
varying vec2 wbDepthUv;

float wbEyeDepth(float windowDepth) {
    if (windowDepth >= 0.999999) return 1.0e20;
    float ndcDepth = windowDepth * 2.0 - 1.0;
    float denominator = ndcDepth * wbProjection.y - wbProjection.x;
    if (abs(denominator) < 0.000001) return 1.0e20;
    return abs(wbProjection.z / denominator);
}

void main() {
    float centerSample = texture2D(wbDepthTexture, wbDepthUv).r;
    if (centerSample >= 0.999999) discard;
    float center = wbEyeDepth(centerSample);
    float farther = center;
    farther = max(farther, wbEyeDepth(texture2D(wbDepthTexture, wbDepthUv + vec2( wbTexelSize.x, 0.0)).r));
    farther = max(farther, wbEyeDepth(texture2D(wbDepthTexture, wbDepthUv + vec2(-wbTexelSize.x, 0.0)).r));
    farther = max(farther, wbEyeDepth(texture2D(wbDepthTexture, wbDepthUv + vec2(0.0,  wbTexelSize.y)).r));
    farther = max(farther, wbEyeDepth(texture2D(wbDepthTexture, wbDepthUv + vec2(0.0, -wbTexelSize.y)).r));
    farther = max(farther, wbEyeDepth(texture2D(wbDepthTexture, wbDepthUv + vec2( wbTexelSize.x,  wbTexelSize.y)).r));
    farther = max(farther, wbEyeDepth(texture2D(wbDepthTexture, wbDepthUv + vec2(-wbTexelSize.x,  wbTexelSize.y)).r));
    farther = max(farther, wbEyeDepth(texture2D(wbDepthTexture, wbDepthUv + vec2( wbTexelSize.x, -wbTexelSize.y)).r));
    farther = max(farther, wbEyeDepth(texture2D(wbDepthTexture, wbDepthUv + vec2(-wbTexelSize.x, -wbTexelSize.y)).r));
    float threshold = max(0.04, center * 0.0125);
    if (farther - center <= threshold) discard;
    gl_FragColor = vec4(0.012, 0.010, 0.016, 0.86);
}
)glsl";

bool IsInvalidWglAddress(const PROC address) noexcept {
    const auto value = reinterpret_cast<std::uintptr_t>(address);
    return address == nullptr || value == 1U || value == 2U || value == 3U
        || value == static_cast<std::uintptr_t>(-1);
}

PROC ResolveFunction(
    const HMODULE opengl,
    const WglGetProcAddress get_proc_address,
    const char* const name
) noexcept {
    PROC address = nullptr;
    if (get_proc_address != nullptr) {
        address = get_proc_address(name);
    }
    if (IsInvalidWglAddress(address) && opengl != nullptr) {
        address = reinterpret_cast<PROC>(GetProcAddress(opengl, name));
    }
    return IsInvalidWglAddress(address) ? nullptr : address;
}

template <typename Function>
Function Resolve(
    const HMODULE opengl,
    const WglGetProcAddress get_proc_address,
    const char* const name
) noexcept {
    return reinterpret_cast<Function>(ResolveFunction(opengl, get_proc_address, name));
}

bool ResolveApi(DepthEdgeApi* const api) noexcept {
    if (api == nullptr) {
        return false;
    }
    const HMODULE opengl = GetModuleHandleW(L"OPENGL32.dll");
    if (opengl == nullptr) {
        return false;
    }
    api->get_current_context = reinterpret_cast<WglGetCurrentContext>(
        GetProcAddress(opengl, "wglGetCurrentContext")
    );
    api->get_proc_address = reinterpret_cast<WglGetProcAddress>(
        GetProcAddress(opengl, "wglGetProcAddress")
    );
    const auto get_proc = api->get_proc_address;
#define WB_RESOLVE(member, type, symbol) \
    api->member = Resolve<type>(opengl, get_proc, symbol)
    WB_RESOLVE(active_texture, GlActiveTexture, "glActiveTexture");
    WB_RESOLVE(attach_shader, GlAttachShader, "glAttachShader");
    WB_RESOLVE(begin, GlBegin, "glBegin");
    WB_RESOLVE(bind_texture, GlBindTexture, "glBindTexture");
    WB_RESOLVE(blend_func, GlBlendFunc, "glBlendFunc");
    WB_RESOLVE(color_mask, GlColorMask, "glColorMask");
    WB_RESOLVE(compile_shader, GlCompileShader, "glCompileShader");
    WB_RESOLVE(copy_tex_sub_image_2d, GlCopyTexSubImage2D, "glCopyTexSubImage2D");
    WB_RESOLVE(create_program, GlCreateProgram, "glCreateProgram");
    WB_RESOLVE(create_shader, GlCreateShader, "glCreateShader");
    WB_RESOLVE(delete_program, GlDeleteProgram, "glDeleteProgram");
    WB_RESOLVE(delete_shader, GlDeleteShader, "glDeleteShader");
    WB_RESOLVE(depth_mask, GlDepthMask, "glDepthMask");
    WB_RESOLVE(disable, GlDisable, "glDisable");
    WB_RESOLVE(enable, GlEnable, "glEnable");
    WB_RESOLVE(end, GlEnd, "glEnd");
    WB_RESOLVE(gen_textures, GlGenTextures, "glGenTextures");
    WB_RESOLVE(get_error, GlGetError, "glGetError");
    WB_RESOLVE(get_integerv, GlGetIntegerv, "glGetIntegerv");
    WB_RESOLVE(get_program_info_log, GlGetProgramInfoLog, "glGetProgramInfoLog");
    WB_RESOLVE(get_programiv, GlGetProgramiv, "glGetProgramiv");
    WB_RESOLVE(get_shader_info_log, GlGetShaderInfoLog, "glGetShaderInfoLog");
    WB_RESOLVE(get_shaderiv, GlGetShaderiv, "glGetShaderiv");
    WB_RESOLVE(get_uniform_location, GlGetUniformLocation, "glGetUniformLocation");
    WB_RESOLVE(is_program, GlIsProgram, "glIsProgram");
    WB_RESOLVE(link_program, GlLinkProgram, "glLinkProgram");
    WB_RESOLVE(load_identity, GlLoadIdentity, "glLoadIdentity");
    WB_RESOLVE(matrix_mode, GlMatrixMode, "glMatrixMode");
    WB_RESOLVE(pop_attrib, GlPopAttrib, "glPopAttrib");
    WB_RESOLVE(pop_matrix, GlPopMatrix, "glPopMatrix");
    WB_RESOLVE(push_attrib, GlPushAttrib, "glPushAttrib");
    WB_RESOLVE(push_matrix, GlPushMatrix, "glPushMatrix");
    WB_RESOLVE(shader_source, GlShaderSource, "glShaderSource");
    WB_RESOLVE(tex_coord_2f, GlTexCoord2f, "glTexCoord2f");
    WB_RESOLVE(tex_image_2d, GlTexImage2D, "glTexImage2D");
    WB_RESOLVE(tex_parameter_i, GlTexParameteri, "glTexParameteri");
    WB_RESOLVE(uniform_1i, GlUniform1i, "glUniform1i");
    WB_RESOLVE(uniform_2f, GlUniform2f, "glUniform2f");
    WB_RESOLVE(uniform_3f, GlUniform3f, "glUniform3f");
    WB_RESOLVE(use_program, GlUseProgram, "glUseProgram");
    WB_RESOLVE(vertex_2f, GlVertex2f, "glVertex2f");
#undef WB_RESOLVE
    return api->active_texture != nullptr && api->attach_shader != nullptr
        && api->begin != nullptr && api->bind_texture != nullptr
        && api->blend_func != nullptr && api->color_mask != nullptr
        && api->compile_shader != nullptr && api->copy_tex_sub_image_2d != nullptr
        && api->create_program != nullptr && api->create_shader != nullptr
        && api->delete_program != nullptr && api->delete_shader != nullptr
        && api->depth_mask != nullptr && api->disable != nullptr
        && api->enable != nullptr && api->end != nullptr
        && api->gen_textures != nullptr && api->get_error != nullptr
        && api->get_integerv != nullptr && api->get_programiv != nullptr
        && api->get_shaderiv != nullptr && api->get_uniform_location != nullptr
        && api->is_program != nullptr && api->link_program != nullptr
        && api->load_identity != nullptr && api->matrix_mode != nullptr
        && api->pop_attrib != nullptr && api->pop_matrix != nullptr
        && api->push_attrib != nullptr && api->push_matrix != nullptr
        && api->shader_source != nullptr && api->tex_coord_2f != nullptr
        && api->tex_image_2d != nullptr && api->tex_parameter_i != nullptr
        && api->uniform_1i != nullptr && api->uniform_2f != nullptr
        && api->uniform_3f != nullptr && api->use_program != nullptr
        && api->vertex_2f != nullptr && api->get_current_context != nullptr;
}

void DebugLog(
    const char* const prefix,
    const unsigned int object,
    const bool shader,
    const DepthEdgeApi& api
) noexcept {
    std::array<char, 1024U> log{};
    int length = 0;
    if (shader && api.get_shader_info_log != nullptr) {
        api.get_shader_info_log(object, static_cast<int>(log.size()), &length, log.data());
    } else if (!shader && api.get_program_info_log != nullptr) {
        api.get_program_info_log(object, static_cast<int>(log.size()), &length, log.data());
    }
    OutputDebugStringA(prefix);
    if (length > 0) {
        OutputDebugStringA(log.data());
    }
    OutputDebugStringA("\n");
}

bool CompileShader(
    const unsigned int type,
    const char* const source,
    unsigned int* const shader,
    DepthEdgeApi& api
) noexcept {
    if (shader == nullptr) {
        return false;
    }
    *shader = api.create_shader(type);
    if (*shader == 0U) {
        return false;
    }
    api.shader_source(*shader, 1, &source, nullptr);
    api.compile_shader(*shader);
    int compiled = 0;
    api.get_shaderiv(*shader, kGlCompileStatus, &compiled);
    if (compiled == 0) {
        DebugLog("WonderBane depth-edge shader compilation failed: ", *shader, true, api);
        api.delete_shader(*shader);
        *shader = 0U;
        return false;
    }
    return true;
}

bool BuildResources(DepthEdgeRuntime* const runtime) noexcept {
    if (runtime == nullptr) {
        return false;
    }
    DepthEdgeApi& api = runtime->api;
    unsigned int vertex_shader = 0U;
    unsigned int fragment_shader = 0U;
    if (!CompileShader(kGlVertexShader, kVertexSource, &vertex_shader, api)
        || !CompileShader(kGlFragmentShader, kFragmentSource, &fragment_shader, api)) {
        if (vertex_shader != 0U) {
            api.delete_shader(vertex_shader);
        }
        return false;
    }
    const unsigned int program = api.create_program();
    if (program == 0U) {
        api.delete_shader(fragment_shader);
        api.delete_shader(vertex_shader);
        return false;
    }
    api.attach_shader(program, vertex_shader);
    api.attach_shader(program, fragment_shader);
    api.link_program(program);
    api.delete_shader(fragment_shader);
    api.delete_shader(vertex_shader);
    int linked = 0;
    api.get_programiv(program, kGlLinkStatus, &linked);
    if (linked == 0) {
        DebugLog("WonderBane depth-edge program link failed: ", program, false, api);
        api.delete_program(program);
        return false;
    }
    runtime->sampler_location = api.get_uniform_location(program, "wbDepthTexture");
    runtime->texel_size_location = api.get_uniform_location(program, "wbTexelSize");
    runtime->projection_location = api.get_uniform_location(program, "wbProjection");
    if (runtime->sampler_location < 0 || runtime->texel_size_location < 0
        || runtime->projection_location < 0) {
        api.delete_program(program);
        return false;
    }
    unsigned int texture = 0U;
    api.gen_textures(1, &texture);
    if (texture == 0U) {
        api.delete_program(program);
        return false;
    }
    runtime->program = program;
    runtime->depth_texture = texture;
    OutputDebugStringA("WonderBane fixed-pixel depth-edge program linked.\n");
    return true;
}

bool EnsureResources() noexcept {
    const LONG generation = InterlockedCompareExchange(&g_generation, 0, 0);
    if (g_runtime.generation != generation) {
        g_runtime = {};
        g_runtime.generation = generation;
    }
    if (g_runtime.context != nullptr && g_runtime.api.get_current_context != nullptr) {
        const HGLRC current = g_runtime.api.get_current_context();
        if (current == g_runtime.context && g_runtime.program != 0U
            && g_runtime.api.is_program(g_runtime.program) != FALSE) {
            return true;
        }
        if (current == g_runtime.context && g_runtime.failed) {
            return false;
        }
        g_runtime = {};
        g_runtime.generation = generation;
    }
    if (!ResolveApi(&g_runtime.api)) {
        g_runtime.failed = true;
        ReportDepthEdgePassFailure("opengl-entry-resolution-failed");
        return false;
    }
    g_runtime.context = g_runtime.api.get_current_context();
    if (g_runtime.context == nullptr) {
        g_runtime.failed = true;
        ReportDepthEdgePassFailure("current-context-unavailable");
        return false;
    }
    if (!BuildResources(&g_runtime)) {
        g_runtime.failed = true;
        ReportDepthEdgePassFailure("depth-edge-resource-creation-failed");
        return false;
    }
    return true;
}

void ClearErrors(const DepthEdgeApi& api) noexcept {
    for (unsigned int count = 0U; count < 16U; ++count) {
        if (api.get_error() == kGlNoError) {
            return;
        }
    }
}

bool CopyDepthTexture(const DepthEdgeFrame& frame) noexcept {
    DepthEdgeApi& api = g_runtime.api;
    const int width = frame.viewport[2];
    const int height = frame.viewport[3];
    if (width <= 0 || height <= 0) {
        return false;
    }
    if (g_runtime.texture_width != width || g_runtime.texture_height != height) {
        api.tex_image_2d(
            kGlTexture2D,
            0,
            static_cast<int>(kGlDepthComponent24),
            width,
            height,
            0,
            kGlDepthComponent,
            kGlUnsignedInt,
            nullptr
        );
        api.tex_parameter_i(
            kGlTexture2D, kGlTextureMinFilter, static_cast<int>(kGlNearest)
        );
        api.tex_parameter_i(
            kGlTexture2D, kGlTextureMagFilter, static_cast<int>(kGlNearest)
        );
        api.tex_parameter_i(
            kGlTexture2D, kGlTextureWrapS, static_cast<int>(kGlClampToEdge)
        );
        api.tex_parameter_i(
            kGlTexture2D, kGlTextureWrapT, static_cast<int>(kGlClampToEdge)
        );
        if (api.get_error() != kGlNoError) {
            return false;
        }
        g_runtime.texture_width = width;
        g_runtime.texture_height = height;
    }
    api.copy_tex_sub_image_2d(
        kGlTexture2D,
        0,
        0,
        0,
        frame.viewport[0],
        frame.viewport[1],
        width,
        height
    );
    return api.get_error() == kGlNoError;
}

bool CompositeDepthEdges(const DepthEdgeFrame& frame) noexcept {
    if (!EnsureResources()) {
        return false;
    }
    DepthEdgeApi& api = g_runtime.api;
    int previous_program = 0;
    int previous_active_texture = 0;
    int previous_matrix_mode = 0;
    api.get_integerv(kGlCurrentProgram, &previous_program);
    api.get_integerv(kGlActiveTexture, &previous_active_texture);
    api.get_integerv(kGlMatrixMode, &previous_matrix_mode);
    api.push_attrib(kGlAllAttribBits);
    api.active_texture(kGlTexture0);
    int previous_texture = 0;
    api.get_integerv(kGlTextureBinding2D, &previous_texture);
    api.bind_texture(kGlTexture2D, g_runtime.depth_texture);
    ClearErrors(api);
    if (!CopyDepthTexture(frame)) {
        api.bind_texture(kGlTexture2D, static_cast<unsigned int>(previous_texture));
        api.active_texture(static_cast<unsigned int>(previous_active_texture));
        api.pop_attrib();
        api.matrix_mode(static_cast<unsigned int>(previous_matrix_mode));
        ReportDepthEdgePassFailure("default-depth-copy-failed");
        return false;
    }

    api.disable(kGlAlphaTest);
    api.disable(kGlColorLogicOp);
    api.disable(kGlCullFace);
    api.disable(kGlDepthTest);
    api.disable(kGlDither);
    api.disable(kGlFog);
    api.disable(kGlLighting);
    api.disable(kGlScissorTest);
    api.disable(kGlStencilTest);
    api.enable(kGlBlend);
    api.enable(kGlTexture2D);
    api.blend_func(kGlSrcAlpha, kGlOneMinusSrcAlpha);
    api.color_mask(TRUE, TRUE, TRUE, TRUE);
    api.depth_mask(FALSE);
    api.use_program(g_runtime.program);
    api.uniform_1i(g_runtime.sampler_location, 0);
    api.uniform_2f(
        g_runtime.texel_size_location,
        1.0F / static_cast<float>(frame.viewport[2]),
        1.0F / static_cast<float>(frame.viewport[3])
    );
    api.uniform_3f(
        g_runtime.projection_location,
        frame.projection[10],
        frame.projection[11],
        frame.projection[14]
    );

    api.matrix_mode(kGlProjection);
    api.push_matrix();
    api.load_identity();
    api.matrix_mode(kGlModelView);
    api.push_matrix();
    api.load_identity();
    api.begin(kGlQuads);
    api.tex_coord_2f(0.0F, 0.0F);
    api.vertex_2f(-1.0F, -1.0F);
    api.tex_coord_2f(1.0F, 0.0F);
    api.vertex_2f(1.0F, -1.0F);
    api.tex_coord_2f(1.0F, 1.0F);
    api.vertex_2f(1.0F, 1.0F);
    api.tex_coord_2f(0.0F, 1.0F);
    api.vertex_2f(-1.0F, 1.0F);
    api.end();
    const bool rendered = api.get_error() == kGlNoError;
    api.pop_matrix();
    api.matrix_mode(kGlProjection);
    api.pop_matrix();
    api.use_program(static_cast<unsigned int>(previous_program));
    api.bind_texture(kGlTexture2D, static_cast<unsigned int>(previous_texture));
    api.active_texture(static_cast<unsigned int>(previous_active_texture));
    api.pop_attrib();
    api.matrix_mode(static_cast<unsigned int>(previous_matrix_mode));
    if (!rendered) {
        ReportDepthEdgePassFailure("depth-edge-fullscreen-draw-failed");
        return false;
    }
    ReportDepthEdgePassComposite();
    return true;
}

}  // namespace

float ReconstructPerspectiveEyeDepth(
    const float window_depth,
    const float projection_10,
    const float projection_11,
    const float projection_14
) noexcept {
    if (!std::isfinite(window_depth) || !std::isfinite(projection_10)
        || !std::isfinite(projection_11) || !std::isfinite(projection_14)
        || window_depth < 0.0F || window_depth >= 0.999999F) {
        return std::numeric_limits<float>::infinity();
    }
    const float ndc_depth = window_depth * 2.0F - 1.0F;
    const float denominator = ndc_depth * projection_11 - projection_10;
    if (!std::isfinite(denominator) || std::fabs(denominator) < 0.000001F) {
        return std::numeric_limits<float>::infinity();
    }
    return std::fabs(projection_14 / denominator);
}

bool IsForegroundDepthDiscontinuity(
    const float center_depth,
    const float* const neighbour_depths,
    const std::size_t neighbour_count,
    const float projection_10,
    const float projection_11,
    const float projection_14
) noexcept {
    if (neighbour_depths == nullptr || neighbour_count == 0U) {
        return false;
    }
    const float center = ReconstructPerspectiveEyeDepth(
        center_depth, projection_10, projection_11, projection_14
    );
    if (!std::isfinite(center)) {
        return false;
    }
    float farther = center;
    for (std::size_t index = 0U; index < neighbour_count; ++index) {
        const float neighbour = ReconstructPerspectiveEyeDepth(
            neighbour_depths[index], projection_10, projection_11, projection_14
        );
        farther = std::max(farther, neighbour);
    }
    const float threshold = std::max(
        kAbsoluteDepthThreshold, center * kRelativeDepthThreshold
    );
    return farther - center > threshold;
}

const char* DepthEdgeFragmentSource() noexcept {
    return kFragmentSource;
}

const char* DepthEdgeVertexSource() noexcept {
    return kVertexSource;
}

void MarkDepthEdgeSceneDraw(
    const float* const projection,
    const std::size_t projection_count,
    const int* const viewport,
    const std::size_t viewport_count
) noexcept {
    if (projection == nullptr || projection_count != g_frame.projection.size()
        || viewport == nullptr || viewport_count != g_frame.viewport.size()
        || viewport[2] <= 0 || viewport[3] <= 0 || g_frame.composited) {
        return;
    }
    std::copy_n(projection, g_frame.projection.size(), g_frame.projection.begin());
    std::copy_n(viewport, g_frame.viewport.size(), g_frame.viewport.begin());
    g_frame.pending = true;
}

void CompositeDepthEdgesBeforeUi() noexcept {
    if (!g_frame.pending || g_frame.composited) {
        return;
    }
    const DepthEdgeFrame frame = g_frame;
    g_frame.pending = false;
    g_frame.composited = true;
    CompositeDepthEdges(frame);
}

void EndDepthEdgeFrame() noexcept {
    g_frame = {};
}

void ResetDepthEdges() noexcept {
    InterlockedIncrement(&g_generation);
    g_runtime = {};
    g_frame = {};
}

}  // namespace wonderbane::extension
