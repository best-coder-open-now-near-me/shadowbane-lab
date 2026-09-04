#include "banded_lighting.h"
#include "graphics_control.h"

#include <Windows.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>

namespace wonderbane::extension {
namespace {

constexpr unsigned int kGlActiveTexture = 0x84E0U;
constexpr unsigned int kGlBlend = 0x0BE2U;
constexpr unsigned int kGlCompileStatus = 0x8B81U;
constexpr unsigned int kGlCurrentProgram = 0x8B8DU;
constexpr unsigned int kGlDecal = 0x2101U;
constexpr unsigned int kGlDepthWriteMask = 0x0B72U;
constexpr unsigned int kGlFog = 0x0B60U;
constexpr unsigned int kGlFogMode = 0x0B65U;
constexpr unsigned int kGlFragmentShader = 0x8B30U;
constexpr unsigned int kGlLinkStatus = 0x8B82U;
constexpr unsigned int kGlModulate = 0x2100U;
constexpr unsigned int kGlReplace = 0x1E01U;
constexpr unsigned int kGlTexture0 = 0x84C0U;
constexpr unsigned int kGlTexture2D = 0x0DE1U;
constexpr unsigned int kGlTextureEnv = 0x2300U;
constexpr unsigned int kGlTextureEnvMode = 0x2200U;
constexpr unsigned int kGlVertexShader = 0x8B31U;

constexpr std::array<float, 3U> kThresholds{0.22F, 0.43F, 0.66F};
constexpr std::array<CelBandColor, 4U> kBandColors{{
    {0.23F, 0.24F, 0.26F},
    {0.54F, 0.58F, 0.65F},
    {0.78F, 0.81F, 0.84F},
    {1.00F, 0.99F, 0.95F},
}};

using GlAttachShader = void(APIENTRY*)(unsigned int program, unsigned int shader);
using GlCompileShader = void(APIENTRY*)(unsigned int shader);
using GlCreateProgram = unsigned int(APIENTRY*)();
using GlCreateShader = unsigned int(APIENTRY*)(unsigned int type);
using GlDeleteProgram = void(APIENTRY*)(unsigned int program);
using GlDeleteShader = void(APIENTRY*)(unsigned int shader);
using GlGetIntegerv = void(APIENTRY*)(unsigned int name, int* value);
using GlGetBooleanv = void(APIENTRY*)(unsigned int name, unsigned char* value);
using GlGetProgramInfoLog = void(APIENTRY*)(
    unsigned int program, int capacity, int* length, char* log
);
using GlGetProgramiv = void(APIENTRY*)(
    unsigned int program, unsigned int name, int* value
);
using GlGetShaderInfoLog = void(APIENTRY*)(
    unsigned int shader, int capacity, int* length, char* log
);
using GlGetShaderiv = void(APIENTRY*)(
    unsigned int shader, unsigned int name, int* value
);
using GlGetTexEnviv = void(APIENTRY*)(
    unsigned int target, unsigned int name, int* value
);
using GlGetUniformLocation = int(APIENTRY*)(unsigned int program, const char* name);
using GlIsEnabled = unsigned char(APIENTRY*)(unsigned int capability);
using GlIsProgram = unsigned char(APIENTRY*)(unsigned int program);
using GlLinkProgram = void(APIENTRY*)(unsigned int program);
using GlShaderSource = void(APIENTRY*)(
    unsigned int shader, int count, const char* const* strings, const int* lengths
);
using GlUniform1i = void(APIENTRY*)(int location, int value);
using GlUniform1f = void(APIENTRY*)(int location, float value);
using GlUniform3f = void(APIENTRY*)(int location, float first, float second, float third);
using GlUseProgram = void(APIENTRY*)(unsigned int program);
using WglGetCurrentContext = HGLRC(WINAPI*)();
using WglGetProcAddress = PROC(WINAPI*)(LPCSTR name);

struct BandedApi {
    GlAttachShader attach_shader = nullptr;
    GlCompileShader compile_shader = nullptr;
    GlCreateProgram create_program = nullptr;
    GlCreateShader create_shader = nullptr;
    GlDeleteProgram delete_program = nullptr;
    GlDeleteShader delete_shader = nullptr;
    GlGetIntegerv get_integerv = nullptr;
    GlGetBooleanv get_booleanv = nullptr;
    GlGetProgramInfoLog get_program_info_log = nullptr;
    GlGetProgramiv get_programiv = nullptr;
    GlGetShaderInfoLog get_shader_info_log = nullptr;
    GlGetShaderiv get_shaderiv = nullptr;
    GlGetTexEnviv get_tex_enviv = nullptr;
    GlGetUniformLocation get_uniform_location = nullptr;
    GlIsEnabled is_enabled = nullptr;
    GlIsProgram is_program = nullptr;
    GlLinkProgram link_program = nullptr;
    GlShaderSource shader_source = nullptr;
    GlUniform1i uniform_1i = nullptr;
    GlUniform1f uniform_1f = nullptr;
    GlUniform3f uniform_3f = nullptr;
    GlUseProgram use_program = nullptr;
    WglGetCurrentContext get_current_context = nullptr;
    WglGetProcAddress get_proc_address = nullptr;
};

struct BandedProgram {
    HGLRC context = nullptr;
    BandedApi api{};
    unsigned int program = 0U;
    int sampler_location = -1;
    int texture_enabled_location = -1;
    int texture_env_mode_location = -1;
    int fog_enabled_location = -1;
    int fog_mode_location = -1;
    int band_thresholds_location = -1;
    std::array<int, 4U> band_color_locations{{-1, -1, -1, -1}};
    int vertex_tint_gamma_location = -1;
    int distant_highlight_compression_location = -1;
    std::uint32_t graphics_parameter_revision = 0U;
    LONG generation = 0;
    bool failed = false;
};

volatile LONG g_generation = 1;
thread_local BandedProgram g_program{};

const char kVertexSource[] = R"glsl(#version 120
varying float wbIntensity;

void main() {
    gl_Position = ftransform();
    gl_FrontColor = gl_Color;
    gl_BackColor = gl_Color;
    gl_TexCoord[0] = gl_TextureMatrix[0] * gl_MultiTexCoord0;

    vec3 transformedNormal = gl_NormalMatrix * gl_Normal;
    float normalLength = length(transformedNormal);
    vec3 normal = normalLength > 0.0001
        ? transformedNormal / normalLength
        : vec3(0.0, 0.0, 1.0);
    vec3 lightDirection = normalize(vec3(-0.35, 0.55, 0.76));
    float diffuse = max(dot(normal, lightDirection), 0.0);
    wbIntensity = clamp(0.30 + 0.82 * diffuse, 0.0, 1.0);

    vec4 eyePosition = gl_ModelViewMatrix * gl_Vertex;
    gl_FogFragCoord = abs(eyePosition.z);
}
)glsl";

const char kFragmentSource[] = R"glsl(#version 120
uniform sampler2D wbTexture;
uniform int wbTextureEnabled;
uniform int wbTextureEnvMode;
uniform int wbFogEnabled;
uniform int wbFogMode;
uniform vec3 wbBandThresholds;
uniform vec3 wbBandColor0;
uniform vec3 wbBandColor1;
uniform vec3 wbBandColor2;
uniform vec3 wbBandColor3;
uniform float wbVertexTintGamma;
uniform float wbDistantHighlightCompression;
varying float wbIntensity;

vec3 wbBand(float intensity) {
    float pixelVariation = fwidth(intensity);
    float transitionWidth = clamp(pixelVariation * 1.25, 0.004, 0.06);
    float distantAlias = smoothstep(0.025, 0.10, pixelVariation);
    vec3 brightest = mix(
        wbBandColor3,
        wbBandColor2,
        distantAlias * wbDistantHighlightCompression
    );
    vec3 color = wbBandColor0;
    color = mix(
        color,
        wbBandColor1,
        smoothstep(
            wbBandThresholds.x - transitionWidth,
            wbBandThresholds.x + transitionWidth,
            intensity
        )
    );
    color = mix(
        color,
        wbBandColor2,
        smoothstep(
            wbBandThresholds.y - transitionWidth,
            wbBandThresholds.y + transitionWidth,
            intensity
        )
    );
    return mix(
        color,
        brightest,
        smoothstep(
            wbBandThresholds.z - transitionWidth,
            wbBandThresholds.z + transitionWidth,
            intensity
        )
    );
}

void main() {
    vec3 vertexTint = pow(
        clamp(gl_Color.rgb, 0.0, 1.0),
        vec3(wbVertexTintGamma)
    );
    vec4 texel = wbTextureEnabled != 0
        ? texture2D(wbTexture, gl_TexCoord[0].st)
        : vec4(1.0);
    vec3 baseColor = vertexTint;
    float alpha = gl_Color.a;
    if (wbTextureEnabled != 0) {
        if (wbTextureEnvMode == 7681) {
            baseColor = texel.rgb;
            alpha = texel.a;
        } else if (wbTextureEnvMode == 8449) {
            baseColor = mix(vertexTint, texel.rgb, texel.a);
        } else {
            baseColor = texel.rgb * vertexTint;
            alpha = texel.a * gl_Color.a;
        }
    }
    vec4 result = vec4(baseColor * wbBand(wbIntensity), alpha);

    if (wbFogEnabled != 0) {
        float distance = abs(gl_FogFragCoord);
        float fogFactor = (gl_Fog.end - distance) * gl_Fog.scale;
        if (wbFogMode == 2048) {
            fogFactor = exp(-gl_Fog.density * distance);
        } else if (wbFogMode == 2049) {
            float densityDistance = gl_Fog.density * distance;
            fogFactor = exp(-(densityDistance * densityDistance));
        }
        result = mix(gl_Fog.color, result, clamp(fogFactor, 0.0, 1.0));
    }
    gl_FragColor = result;
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

bool ResolveApi(BandedApi* const api) noexcept {
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
    api->attach_shader = Resolve<GlAttachShader>(opengl, get_proc, "glAttachShader");
    api->compile_shader = Resolve<GlCompileShader>(opengl, get_proc, "glCompileShader");
    api->create_program = Resolve<GlCreateProgram>(opengl, get_proc, "glCreateProgram");
    api->create_shader = Resolve<GlCreateShader>(opengl, get_proc, "glCreateShader");
    api->delete_program = Resolve<GlDeleteProgram>(opengl, get_proc, "glDeleteProgram");
    api->delete_shader = Resolve<GlDeleteShader>(opengl, get_proc, "glDeleteShader");
    api->get_integerv = Resolve<GlGetIntegerv>(opengl, get_proc, "glGetIntegerv");
    api->get_booleanv = Resolve<GlGetBooleanv>(opengl, get_proc, "glGetBooleanv");
    api->get_program_info_log = Resolve<GlGetProgramInfoLog>(
        opengl, get_proc, "glGetProgramInfoLog"
    );
    api->get_programiv = Resolve<GlGetProgramiv>(opengl, get_proc, "glGetProgramiv");
    api->get_shader_info_log = Resolve<GlGetShaderInfoLog>(
        opengl, get_proc, "glGetShaderInfoLog"
    );
    api->get_shaderiv = Resolve<GlGetShaderiv>(opengl, get_proc, "glGetShaderiv");
    api->get_tex_enviv = Resolve<GlGetTexEnviv>(opengl, get_proc, "glGetTexEnviv");
    api->get_uniform_location = Resolve<GlGetUniformLocation>(
        opengl, get_proc, "glGetUniformLocation"
    );
    api->is_enabled = Resolve<GlIsEnabled>(opengl, get_proc, "glIsEnabled");
    api->is_program = Resolve<GlIsProgram>(opengl, get_proc, "glIsProgram");
    api->link_program = Resolve<GlLinkProgram>(opengl, get_proc, "glLinkProgram");
    api->shader_source = Resolve<GlShaderSource>(opengl, get_proc, "glShaderSource");
    api->uniform_1i = Resolve<GlUniform1i>(opengl, get_proc, "glUniform1i");
    api->uniform_1f = Resolve<GlUniform1f>(opengl, get_proc, "glUniform1f");
    api->uniform_3f = Resolve<GlUniform3f>(opengl, get_proc, "glUniform3f");
    api->use_program = Resolve<GlUseProgram>(opengl, get_proc, "glUseProgram");
    return api->attach_shader != nullptr && api->compile_shader != nullptr
        && api->create_program != nullptr && api->create_shader != nullptr
        && api->delete_program != nullptr && api->delete_shader != nullptr
        && api->get_integerv != nullptr && api->get_booleanv != nullptr
        && api->get_programiv != nullptr
        && api->get_shaderiv != nullptr && api->get_tex_enviv != nullptr
        && api->get_uniform_location != nullptr && api->is_enabled != nullptr
        && api->is_program != nullptr && api->link_program != nullptr
        && api->shader_source != nullptr && api->uniform_1i != nullptr
        && api->uniform_1f != nullptr && api->uniform_3f != nullptr
        && api->use_program != nullptr && api->get_current_context != nullptr;
}

void DebugLog(
    const char* const prefix,
    const unsigned int object,
    const bool shader,
    const BandedApi& api
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

bool BuildProgram(BandedProgram* const state) noexcept {
    if (state == nullptr) {
        return false;
    }
    BandedApi& api = state->api;
    const unsigned int vertex_shader = api.create_shader(kGlVertexShader);
    if (vertex_shader == 0U) {
        return false;
    }
    const char* vertex_source = kVertexSource;
    api.shader_source(vertex_shader, 1, &vertex_source, nullptr);
    api.compile_shader(vertex_shader);
    int compiled = 0;
    api.get_shaderiv(vertex_shader, kGlCompileStatus, &compiled);
    if (compiled == 0) {
        DebugLog(
            "WonderBane banded vertex shader compilation failed: ",
            vertex_shader,
            true,
            api
        );
        api.delete_shader(vertex_shader);
        return false;
    }
    const unsigned int fragment_shader = api.create_shader(kGlFragmentShader);
    if (fragment_shader == 0U) {
        api.delete_shader(vertex_shader);
        return false;
    }
    const char* fragment_source = kFragmentSource;
    api.shader_source(fragment_shader, 1, &fragment_source, nullptr);
    api.compile_shader(fragment_shader);
    compiled = 0;
    api.get_shaderiv(fragment_shader, kGlCompileStatus, &compiled);
    if (compiled == 0) {
        DebugLog(
            "WonderBane banded fragment shader compilation failed: ",
            fragment_shader,
            true,
            api
        );
        api.delete_shader(fragment_shader);
        api.delete_shader(vertex_shader);
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
        DebugLog(
            "WonderBane banded fragment program link failed: ",
            program,
            false,
            api
        );
        api.delete_program(program);
        return false;
    }
    state->program = program;
    state->sampler_location = api.get_uniform_location(program, "wbTexture");
    state->texture_enabled_location = api.get_uniform_location(
        program, "wbTextureEnabled"
    );
    state->texture_env_mode_location = api.get_uniform_location(
        program, "wbTextureEnvMode"
    );
    state->fog_enabled_location = api.get_uniform_location(program, "wbFogEnabled");
    state->fog_mode_location = api.get_uniform_location(program, "wbFogMode");
    state->band_thresholds_location = api.get_uniform_location(
        program, "wbBandThresholds"
    );
    state->band_color_locations = {
        api.get_uniform_location(program, "wbBandColor0"),
        api.get_uniform_location(program, "wbBandColor1"),
        api.get_uniform_location(program, "wbBandColor2"),
        api.get_uniform_location(program, "wbBandColor3"),
    };
    state->vertex_tint_gamma_location = api.get_uniform_location(
        program, "wbVertexTintGamma"
    );
    state->distant_highlight_compression_location = api.get_uniform_location(
        program, "wbDistantHighlightCompression"
    );
    const bool has_uniforms = state->sampler_location >= 0
        && state->texture_enabled_location >= 0
        && state->texture_env_mode_location >= 0
        && state->fog_enabled_location >= 0
        && state->fog_mode_location >= 0
        && state->band_thresholds_location >= 0
        && std::all_of(
            state->band_color_locations.begin(),
            state->band_color_locations.end(),
            [](const int location) { return location >= 0; }
        )
        && state->vertex_tint_gamma_location >= 0
        && state->distant_highlight_compression_location >= 0;
    if (!has_uniforms) {
        api.delete_program(program);
        state->program = 0U;
    }
    if (has_uniforms) {
        OutputDebugStringA("WonderBane normal-driven cel program linked.\n");
    }
    return has_uniforms;
}

bool EnsureProgram() noexcept {
    const LONG generation = InterlockedCompareExchange(&g_generation, 0, 0);
    if (g_program.generation != generation) {
        g_program = {};
        g_program.generation = generation;
    }
    if (g_program.context != nullptr && g_program.api.get_current_context != nullptr) {
        const HGLRC current = g_program.api.get_current_context();
        if (current == g_program.context && g_program.program != 0U
            && g_program.api.is_program(g_program.program) != FALSE) {
            return true;
        }
        if (current == g_program.context && g_program.failed) {
            return false;
        }
        g_program = {};
        g_program.generation = generation;
    }
    if (!ResolveApi(&g_program.api)) {
        if (g_program.api.get_current_context != nullptr) {
            g_program.context = g_program.api.get_current_context();
        }
        g_program.failed = true;
        return false;
    }
    g_program.context = g_program.api.get_current_context();
    if (g_program.context == nullptr) {
        g_program.failed = true;
        return false;
    }
    if (!BuildProgram(&g_program)) {
        g_program.failed = true;
        return false;
    }
    return true;
}

}  // namespace

std::size_t CelBandIndex(const float intensity) noexcept {
    if (std::isnan(intensity)) {
        return 0U;
    }
    return static_cast<std::size_t>(
        std::upper_bound(kThresholds.begin(), kThresholds.end(), intensity)
        - kThresholds.begin()
    );
}

CelBandColor CelBandForIntensity(const float intensity) noexcept {
    return kBandColors[CelBandIndex(intensity)];
}

bool IsBandedLightingSceneState(
    const bool depth_writes,
    const bool blend_enabled
) noexcept {
    return depth_writes && !blend_enabled;
}

const char* BandedLightingFragmentSource() noexcept {
    return kFragmentSource;
}

const char* BandedLightingVertexSource() noexcept {
    return kVertexSource;
}

bool BeginBandedLightingDraw(BandedLightingDraw* const draw) noexcept {
    if (draw == nullptr) {
        return false;
    }
    *draw = {};
    const std::uint32_t parameter_revision = CurrentGraphicsParametersRevision();
    const GraphicsParameters parameters = CurrentGraphicsParameters();
    if ((parameters.flags & kGraphicsControlBandedLighting) == 0U) {
        return false;
    }
    if (!EnsureProgram()) {
        return false;
    }
    BandedApi& api = g_program.api;
    int current_program = 0;
    int active_texture = 0;
    unsigned char depth_writes = FALSE;
    api.get_integerv(kGlCurrentProgram, &current_program);
    api.get_integerv(kGlActiveTexture, &active_texture);
    api.get_booleanv(kGlDepthWriteMask, &depth_writes);
    if (current_program != 0
        || active_texture != static_cast<int>(kGlTexture0)
        || !IsBandedLightingSceneState(
            depth_writes != FALSE,
            api.is_enabled(kGlBlend) != FALSE
        )) {
        return false;
    }
    const bool texture_enabled = api.is_enabled(kGlTexture2D) != FALSE;
    int texture_mode = static_cast<int>(kGlModulate);
    if (texture_enabled) {
        api.get_tex_enviv(kGlTextureEnv, kGlTextureEnvMode, &texture_mode);
        if (texture_mode != static_cast<int>(kGlModulate)
            && texture_mode != static_cast<int>(kGlReplace)
            && texture_mode != static_cast<int>(kGlDecal)) {
            return false;
        }
    }
    const bool fog_enabled = api.is_enabled(kGlFog) != FALSE;
    int fog_mode = 0;
    if (fog_enabled) {
        api.get_integerv(kGlFogMode, &fog_mode);
    }
    api.use_program(g_program.program);
    api.uniform_1i(g_program.sampler_location, 0);
    api.uniform_1i(g_program.texture_enabled_location, texture_enabled ? 1 : 0);
    api.uniform_1i(g_program.texture_env_mode_location, texture_mode);
    api.uniform_1i(g_program.fog_enabled_location, fog_enabled ? 1 : 0);
    api.uniform_1i(g_program.fog_mode_location, fog_mode);
    if (g_program.graphics_parameter_revision != parameter_revision) {
        api.uniform_3f(
            g_program.band_thresholds_location,
            parameters.band_thresholds[0],
            parameters.band_thresholds[1],
            parameters.band_thresholds[2]
        );
        for (std::size_t index = 0U; index < parameters.band_colors.size(); ++index) {
            const auto& color = parameters.band_colors[index];
            api.uniform_3f(
                g_program.band_color_locations[index], color[0], color[1], color[2]
            );
        }
        api.uniform_1f(
            g_program.vertex_tint_gamma_location,
            parameters.vertex_tint_gamma
        );
        api.uniform_1f(
            g_program.distant_highlight_compression_location,
            parameters.distant_highlight_compression
        );
        g_program.graphics_parameter_revision = parameter_revision;
    }
    draw->previous_program = current_program;
    draw->active = true;
    return true;
}

void EndBandedLightingDraw(BandedLightingDraw* const draw) noexcept {
    if (draw == nullptr || !draw->active || g_program.api.use_program == nullptr) {
        return;
    }
    g_program.api.use_program(static_cast<unsigned int>(draw->previous_program));
    *draw = {};
}

void ResetBandedLighting() noexcept {
    InterlockedIncrement(&g_generation);
    g_program = {};
}

}  // namespace wonderbane::extension
