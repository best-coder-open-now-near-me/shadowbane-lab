#include "terrain_trace.h"
#include "extension_api.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include <new>

namespace wonderbane::extension {
namespace {

constexpr unsigned int kTexture2d = 0x0DE1U;
constexpr unsigned int kTexture0 = 0x84C0U;
constexpr std::size_t kMaxDraws = 8192U;
constexpr std::size_t kMaxUnits = 4U;
constexpr std::size_t kMaxStack = 24U;
// The diagnostic is deliberately not usable as a frame-time benchmark.
constexpr double kQueryBudgetSeconds = 0.250;
enum class Phase { disabled, idle, armed, capturing, sealed, pending, publishing };

struct GlApi {
    void (APIENTRY* integer)(unsigned int, int*) = nullptr;
    void (APIENTRY* real)(unsigned int, float*) = nullptr;
    void (APIENTRY* parameter)(unsigned int, unsigned int, int*) = nullptr;
    void (APIENTRY* level)(unsigned int, int, unsigned int, int*) = nullptr;
    void (APIENTRY* environment)(unsigned int, unsigned int, int*) = nullptr;
    const unsigned char* (APIENTRY* string)(unsigned int) = nullptr;
    void (APIENTRY* active)(unsigned int) = nullptr;
    HGLRC (WINAPI* context)() = nullptr;
    PROC (WINAPI* proc)(LPCSTR) = nullptr;
};
struct TextureState {
    int enabled = 0, binding = 0;
    // width, height, internal format, border; level zero only.
    std::array<int, 4U> level{};
    // min/mag filters, wrap S/T.
    std::array<int, 4U> sampler{};
    int env_mode = 0;
    // combine RGB/alpha, RGB sources 0..2, alpha sources 0..2,
    // RGB operands 0..2, alpha operands 0..2, RGB/alpha scales.
    std::array<int, 16U> combine{};
    std::array<float, 16U> matrix{};
};
struct DrawRecord {
    std::uint64_t qpc = 0;
    std::uint32_t caller_rva = 0;
    TerrainSubmission submission{};
    unsigned int mode = 0, index_type = 0, list = 0;
    int first = 0, count = 0;
    bool list_source_stable = false;
    unsigned int stack_count = 0;
    std::array<std::uint32_t, kMaxStack> stack{};
    // depth test/write/func, alpha test/func, blend/src/dst, lighting, fog, cull.
    std::array<int, 11U> state{};
    float alpha_ref = 0.0F;
    std::array<float, 4U> color{};
    std::array<float, 16U> model_view{}, projection{};
    std::array<int, 4U> viewport{};
    int active_unit = 0;
    bool active_unit_restored = true;
    std::array<TextureState, kMaxUnits> textures{};
};
struct TraceFrame {
    std::uint64_t sequence = 0, requested_qpc = 0, start_qpc = 0, end_qpc = 0;
    std::uint64_t query_ticks = 0;
    HGLRC context = nullptr;
    DWORD thread = 0;
    bool main_clear = false, done3d = false, extra_depth_clear = false;
    bool context_mismatch = false, helpers_available = false;
    bool multitexture = false, combine_supported = false;
    unsigned int unit_count = 0, omitted_units = 0;
    std::uint64_t observed = 0, overflow = 0, unsafe = 0, budget_skipped = 0;
    std::size_t retained = 0;
    std::array<DrawRecord, kMaxDraws> draws{};
};

SRWLOCK g_lock = SRWLOCK_INIT;
std::atomic<Phase> g_phase{Phase::disabled};
TraceFrame* g_frame = nullptr;
GlApi g_gl{};
HANDLE g_request = nullptr;
std::uintptr_t g_image_base = 0;
std::size_t g_image_size = 0;
std::uint64_t g_creation = 0, g_frequency = 0, g_sequence = 0;
DWORD g_pid = 0;
wchar_t g_directory[MAX_PATH]{};
char g_executable_sha256[65U]{};

struct Exclusive {
    Exclusive() noexcept { AcquireSRWLockExclusive(&g_lock); }
    ~Exclusive() { ReleaseSRWLockExclusive(&g_lock); }
};
std::uint64_t Counter() noexcept {
    LARGE_INTEGER value{};
    QueryPerformanceCounter(&value);
    return static_cast<std::uint64_t>(value.QuadPart);
}
bool Token(const char* text, const char* token) noexcept {
    if (text == nullptr) { return false; }
    const std::size_t size = std::strlen(token);
    for (const char* at = text; (at = std::strstr(at, token)) != nullptr; at += size) {
        if ((at == text || at[-1] == ' ') && (at[size] == '\0' || at[size] == ' ')) {
            return true;
        }
    }
    return false;
}
bool Version13(const char* version) noexcept {
    int major = 0, minor = 0;
    return version != nullptr && sscanf_s(version, "%d.%d", &major, &minor) == 2
        && (major > 1 || (major == 1 && minor >= 3));
}
bool ValidProc(PROC proc) noexcept {
    const auto address = reinterpret_cast<std::uintptr_t>(proc);
    return address > 3U && address != UINTPTR_MAX;
}
bool LocalOrdinaryDirectory(const wchar_t* path) noexcept {
    // Refuse UNC, device paths, mapped network drives, and reparse parents.
    if (path == nullptr || std::wcslen(path) < 3U || path[1] != L':'
        || path[2] != L'\\') { return false; }
    wchar_t root[]{path[0], L':', L'\\', L'\0'};
    if (GetDriveTypeW(root) != DRIVE_FIXED) { return false; }
    wchar_t prefix[MAX_PATH]{};
    if (wcscpy_s(prefix, path) != 0) { return false; }
    const std::size_t length = std::wcslen(prefix);
    for (std::size_t index = 3U; index <= length; ++index) {
        if (index != length && prefix[index] != L'\\') { continue; }
        const wchar_t saved = prefix[index];
        prefix[index] = L'\0';
        const DWORD attributes = GetFileAttributesW(prefix);
        prefix[index] = saved;
        if (attributes == INVALID_FILE_ATTRIBUTES
            || (attributes & FILE_ATTRIBUTE_DIRECTORY) == 0U
            || (attributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0U) { return false; }
    }
    return true;
}
void LoadGl() noexcept {
    const HMODULE module = GetModuleHandleW(L"opengl32.dll");
    if (module == nullptr) { return; }
#define WB_TRACE_GL(field, name) g_gl.field = reinterpret_cast<decltype(g_gl.field)>(GetProcAddress(module, name))
    WB_TRACE_GL(integer, "glGetIntegerv");
    WB_TRACE_GL(real, "glGetFloatv");
    WB_TRACE_GL(parameter, "glGetTexParameteriv");
    WB_TRACE_GL(level, "glGetTexLevelParameteriv");
    WB_TRACE_GL(environment, "glGetTexEnviv");
    WB_TRACE_GL(string, "glGetString");
    WB_TRACE_GL(context, "wglGetCurrentContext");
    WB_TRACE_GL(proc, "wglGetProcAddress");
#undef WB_TRACE_GL
}
void DetectCapabilities(TraceFrame& frame) noexcept {
    frame.helpers_available = g_gl.integer != nullptr && g_gl.real != nullptr
        && g_gl.parameter != nullptr && g_gl.level != nullptr
        && g_gl.environment != nullptr && g_gl.string != nullptr;
    if (!frame.helpers_available) { return; }
    const auto* version = reinterpret_cast<const char*>(g_gl.string(0x1F02U));
    const auto* extensions = reinterpret_cast<const char*>(g_gl.string(0x1F03U));
    if (version == nullptr) { frame.helpers_available = false; return; }
    const bool core = Version13(version);
    frame.multitexture = core || Token(extensions, "GL_ARB_multitexture");
    frame.combine_supported = core || Token(extensions, "GL_ARB_texture_env_combine")
        || Token(extensions, "GL_EXT_texture_env_combine");
    g_gl.active = nullptr;
    int units = 1;
    if (frame.multitexture) {
        const PROC active = g_gl.proc == nullptr ? nullptr : g_gl.proc(
            core ? "glActiveTexture" : "glActiveTextureARB");
        if (!ValidProc(active)) { frame.helpers_available = false; return; }
        g_gl.active = reinterpret_cast<decltype(g_gl.active)>(active);
        g_gl.integer(0x84E2U, &units); // GL_MAX_TEXTURE_UNITS
    }
    if (units < 1 || units > 256) { frame.helpers_available = false; return; }
    frame.unit_count = static_cast<unsigned int>(std::min(units, static_cast<int>(kMaxUnits)));
    frame.omitted_units = static_cast<unsigned int>(units) - frame.unit_count;
}
bool OwnerMatches(TraceFrame& frame) noexcept {
    if (GetCurrentThreadId() != frame.thread || g_gl.context == nullptr
        || g_gl.context() != frame.context) {
        frame.context_mismatch = true;
        return false;
    }
    return true;
}
void ReadState(DrawRecord& draw, const TraceFrame& frame) noexcept {
    constexpr unsigned int states[]{0x0B71U, 0x0B72U, 0x0B74U, 0x0BC0U,
        0x0BC1U, 0x0BE2U, 0x0BE1U, 0x0BE0U, 0x0B50U, 0x0B60U, 0x0B44U};
    for (std::size_t index = 0; index < draw.state.size(); ++index) {
        g_gl.integer(states[index], &draw.state[index]);
    }
    g_gl.real(0x0BC2U, &draw.alpha_ref);
    g_gl.real(0x0B00U, draw.color.data());
    g_gl.real(0x0BA6U, draw.model_view.data());
    g_gl.real(0x0BA7U, draw.projection.data());
    g_gl.integer(0x0BA2U, draw.viewport.data());
    draw.active_unit = static_cast<int>(kTexture0);
    if (frame.multitexture) { g_gl.integer(0x84E0U, &draw.active_unit); }
    for (unsigned int unit = 0; unit < frame.unit_count; ++unit) {
        if (g_gl.active != nullptr) { g_gl.active(kTexture0 + unit); }
        auto& texture = draw.textures[unit];
        g_gl.integer(kTexture2d, &texture.enabled);
        g_gl.integer(0x8069U, &texture.binding);
        g_gl.real(0x0BA8U, texture.matrix.data());
        g_gl.environment(0x2300U, 0x2200U, &texture.env_mode);
        constexpr unsigned int parameters[]{0x2801U, 0x2800U, 0x2802U, 0x2803U};
        constexpr unsigned int levels[]{0x1000U, 0x1001U, 0x1003U, 0x1005U};
        for (std::size_t index = 0; index < 4U; ++index) {
            g_gl.parameter(kTexture2d, parameters[index], &texture.sampler[index]);
            g_gl.level(kTexture2d, 0, levels[index], &texture.level[index]);
        }
        if (frame.combine_supported) {
            constexpr unsigned int combine[]{0x8571U, 0x8572U,
                0x8580U, 0x8581U, 0x8582U, 0x8588U, 0x8589U, 0x858AU,
                0x8590U, 0x8591U, 0x8592U, 0x8598U, 0x8599U, 0x859AU,
                0x8573U, 0x0D1CU};
            for (std::size_t index = 0; index < texture.combine.size(); ++index) {
                g_gl.environment(0x2300U, combine[index], &texture.combine[index]);
            }
        }
    }
    if (g_gl.active != nullptr) {
        g_gl.active(static_cast<unsigned int>(draw.active_unit));
        int restored = 0;
        g_gl.integer(0x84E0U, &restored);
        draw.active_unit_restored = restored == draw.active_unit;
    }
}

// Streaming JSON runs only on the existing publisher, never on a draw hook.
struct Json {
    HANDLE file = INVALID_HANDLE_VALUE;
    bool ok = true;
    std::array<char, 65536U> buffer{};
    std::size_t used = 0;
    void Flush() noexcept {
        if (!ok || used == 0U) { return; }
        DWORD written = 0;
        ok = WriteFile(file, buffer.data(), static_cast<DWORD>(used), &written, nullptr)
            != FALSE && written == used;
        used = 0;
    }
    void Print(const char* format, ...) noexcept {
        char part[2048U]{};
        va_list arguments;
        va_start(arguments, format);
        const int length = vsnprintf_s(part, sizeof(part), _TRUNCATE, format, arguments);
        va_end(arguments);
        if (length < 0) { ok = false; return; }
        if (used + static_cast<std::size_t>(length) > buffer.size()) { Flush(); }
        if (!ok) { return; }
        std::memcpy(buffer.data() + used, part, static_cast<std::size_t>(length));
        used += static_cast<std::size_t>(length);
    }
    template <typename T, std::size_t N>
    void Array(const std::array<T, N>& values, std::size_t count = N) noexcept {
        Print("[");
        for (std::size_t i = 0; i < count; ++i) {
            if (i != 0) { Print(","); }
            const double value = static_cast<double>(values[i]);
            if (std::isfinite(value)) { Print("%.9g", value); }
            else { Print("null"); }
        }
        Print("]");
    }
};
void WriteFrame(Json& json, const TraceFrame& frame) noexcept {
    const bool interval_complete = frame.main_clear && frame.done3d
        && !frame.extra_depth_clear && !frame.context_mismatch;
    json.Print("{\"schema_version\":1,\"extension_version\":\"%u.%u.%u\","
        "\"process_id\":%lu,\"process_creation_filetime_utc\":%llu,"
        "\"executable_sha256\":\"%s\",\"sequence\":%llu,"
        "\"qpc_frequency\":%llu,\"requested_qpc\":%llu,\"start_qpc\":%llu,"
        "\"end_qpc\":%llu,\"query_ticks\":%llu,\"render_thread_id\":%lu,"
        "\"context_token\":%llu,\"reviewed_interval_complete\":%s,"
        "\"main_clear_seen\":%s,\"done3d_seen\":%s,\"extra_depth_clear\":%s,"
        "\"context_or_thread_mismatch\":%s,\"helpers_available\":%s,"
        "\"unit_count\":%u,\"omitted_units\":%u,\"combine_supported\":%s,"
        "\"observed_submissions\":%llu,\"retained_submissions\":%zu,"
        "\"capacity_skipped\":%llu,\"unsafe_query_skipped\":%llu,"
        "\"query_budget_skipped\":%llu,",
        WONDERBANE_EXTENSION_VERSION_MAJOR, WONDERBANE_EXTENSION_VERSION_MINOR,
        WONDERBANE_EXTENSION_VERSION_PATCH,
        g_pid, g_creation, g_executable_sha256, frame.sequence, g_frequency,
        frame.requested_qpc, frame.start_qpc, frame.end_qpc, frame.query_ticks,
        frame.thread, static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(frame.context)),
        interval_complete ? "true" : "false", frame.main_clear ? "true" : "false",
        frame.done3d ? "true" : "false", frame.extra_depth_clear ? "true" : "false",
        frame.context_mismatch ? "true" : "false", frame.helpers_available ? "true" : "false",
        frame.unit_count, frame.omitted_units, frame.combine_supported ? "true" : "false",
        frame.observed, frame.retained, frame.overflow, frame.unsafe, frame.budget_skipped);
    json.Print("\"scope\":{\"pixels_read\":false,\"texture_bytes_read\":false,"
        "\"texture_target\":\"2D-level-zero\",\"texture_ids_are_cache_keys\":false,"
        "\"display_lists\":\"entry-state-only-not-internal-draws\","
        "\"stack\":\"bounded-client-rvas-evidence-not-authority\","
        "\"timings\":\"intrusive-diagnostic-not-frame-benchmark\","
        "\"state\":\"original-submission-before-extension-passes\","
        "\"unhooked_or_driver_internal_draws_observed\":false},\"draws\":[");
    for (std::size_t index = 0; index < frame.retained; ++index) {
        const auto& draw = frame.draws[index];
        if (index != 0) { json.Print(","); }
        json.Print("{\"ordinal\":%zu,\"qpc\":%llu,\"submission\":%u,"
            "\"caller_rva\":%u,\"mode\":%u,\"first\":%d,\"count\":%d,"
            "\"index_type\":%u,\"list\":%u,\"list_source_stable\":%s,\"client_stack_rvas\":",
            index + 1U, draw.qpc, static_cast<unsigned int>(draw.submission), draw.caller_rva,
            draw.mode, draw.first, draw.count, draw.index_type, draw.list,
            draw.list_source_stable ? "true" : "false");
        json.Array(draw.stack, draw.stack_count);
        json.Print(",\"state\":"); json.Array(draw.state);
        json.Print(",\"alpha_ref\":"); json.Array(std::array<float, 1>{draw.alpha_ref});
        json.Print(",\"color\":"); json.Array(draw.color);
        json.Print(",\"model_view\":"); json.Array(draw.model_view);
        json.Print(",\"projection\":"); json.Array(draw.projection);
        json.Print(",\"viewport\":"); json.Array(draw.viewport);
        json.Print(",\"active_unit\":%d,\"active_unit_restored\":%s,\"textures\":[",
            draw.active_unit, draw.active_unit_restored ? "true" : "false");
        for (unsigned int unit = 0; unit < frame.unit_count; ++unit) {
            const auto& texture = draw.textures[unit];
            if (unit != 0) { json.Print(","); }
            json.Print("{\"unit\":%u,\"enabled\":%d,\"binding\":%d,\"level\":",
                unit, texture.enabled, texture.binding);
            json.Array(texture.level);
            json.Print(",\"sampler\":"); json.Array(texture.sampler);
            json.Print(",\"env_mode\":%d,\"combine\":", texture.env_mode);
            if (frame.combine_supported) { json.Array(texture.combine); }
            else { json.Print("null"); }
            json.Print(",\"matrix\":"); json.Array(texture.matrix);
            json.Print("}");
        }
        json.Print("]}");
    }
    json.Print("]}\n");
}

} // namespace

void StartTerrainTrace(const wchar_t* status_path, const std::uintptr_t image_base,
    const std::size_t image_size, const char* executable_sha256) noexcept {
#ifdef WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY
    (void)status_path; (void)image_base; (void)image_size; (void)executable_sha256;
#else
    wchar_t enabled[4U]{};
    if (GetEnvironmentVariableW(L"WONDERBANE_TERRAIN_TRACE", enabled, 4U) != 1U
        || enabled[0] != L'1' || image_base == 0 || image_size == 0
        || executable_sha256 == nullptr || std::strlen(executable_sha256) != 64U) { return; }
    Exclusive lock;
    if (g_phase.load() != Phase::disabled || status_path == nullptr
        || wcscpy_s(g_directory, status_path) != 0) { return; }
    wchar_t* slash = std::wcsrchr(g_directory, L'\\');
    if (slash == nullptr) { return; }
    *slash = L'\0';
    if (!LocalOrdinaryDirectory(g_directory)) { return; }
    FILETIME creation{}, exit{}, kernel{}, user{};
    LARGE_INTEGER frequency{};
    if (!GetProcessTimes(GetCurrentProcess(), &creation, &exit, &kernel, &user)
        || !QueryPerformanceFrequency(&frequency) || frequency.QuadPart <= 0) { return; }
    g_creation = (static_cast<std::uint64_t>(creation.dwHighDateTime) << 32U)
        | creation.dwLowDateTime;
    g_pid = GetCurrentProcessId();
    wchar_t event_name[128U]{};
    swprintf_s(event_name, L"Local\\WonderBaneTerrainTrace-%lu-%llu", g_pid, g_creation);
    g_request = CreateEventW(nullptr, FALSE, FALSE, event_name);
    if (g_request == nullptr) { return; }
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        CloseHandle(g_request); g_request = nullptr; return;
    }
    g_frame = new (std::nothrow) TraceFrame{};
    if (g_frame == nullptr) { CloseHandle(g_request); g_request = nullptr; return; }
    g_image_base = image_base;
    g_image_size = image_size;
    g_frequency = static_cast<std::uint64_t>(frequency.QuadPart);
    strcpy_s(g_executable_sha256, executable_sha256);
    LoadGl();
    g_phase.store(Phase::idle);
#endif
}
void StopTerrainTrace() noexcept {
    if (g_phase.load() == Phase::disabled) { return; }
    Exclusive lock;
    g_phase.store(Phase::disabled);
    if (g_request != nullptr) { CloseHandle(g_request); g_request = nullptr; }
    delete g_frame; g_frame = nullptr;
}
void TerrainTraceClear(const bool reviewed, const unsigned int mask) noexcept {
    const Phase phase = g_phase.load();
    if (phase != Phase::armed && phase != Phase::capturing) { return; }
    Exclusive lock;
    if (g_phase.load() == Phase::armed && reviewed) {
        auto& frame = *g_frame;
        frame.context = g_gl.context == nullptr ? nullptr : g_gl.context();
        frame.thread = GetCurrentThreadId();
        frame.start_qpc = Counter();
        frame.main_clear = frame.context != nullptr;
        if (frame.main_clear) { DetectCapabilities(frame); }
        g_phase.store(Phase::capturing);
    } else if (g_phase.load() == Phase::capturing && (mask & 0x100U) != 0U) {
        g_frame->extra_depth_clear = true;
    }
}
void TerrainTraceDone3d() noexcept {
    if (g_phase.load() != Phase::capturing) { return; }
    Exclusive lock;
    if (g_phase.load() != Phase::capturing) { return; }
    if (OwnerMatches(*g_frame)) { g_frame->done3d = true; }
    g_phase.store(Phase::sealed);
}
void TerrainTraceDraw(const TerrainSubmission submission, const std::uintptr_t caller,
    const unsigned int mode, const int first, const int count, const unsigned int index_type,
    const unsigned int list, const bool list_source_stable, const bool query_safe) noexcept {
    if (g_phase.load() != Phase::capturing) { return; }
    Exclusive lock;
    if (g_phase.load() != Phase::capturing) { return; }
    auto& frame = *g_frame;
    ++frame.observed;
    if (!query_safe || !frame.helpers_available || !OwnerMatches(frame)) {
        ++frame.unsafe; return;
    }
    if (frame.retained == kMaxDraws) { ++frame.overflow; return; }
    if (static_cast<double>(frame.query_ticks) / static_cast<double>(g_frequency)
        >= kQueryBudgetSeconds) { ++frame.budget_skipped; return; }
    auto& draw = frame.draws[frame.retained++];
    draw = {};
    draw.qpc = Counter();
    draw.submission = submission;
    draw.mode = mode; draw.first = first; draw.count = count;
    draw.index_type = index_type; draw.list = list; draw.list_source_stable = list_source_stable;
    if (caller >= g_image_base && caller - g_image_base < g_image_size) {
        draw.caller_rva = static_cast<std::uint32_t>(caller - g_image_base);
    }
    void* stack[kMaxStack]{};
    const USHORT captured = CaptureStackBackTrace(1U, static_cast<DWORD>(kMaxStack), stack, nullptr);
    for (USHORT index = 0; index < captured; ++index) {
        const auto address = reinterpret_cast<std::uintptr_t>(stack[index]);
        if (address >= g_image_base && address - g_image_base < g_image_size) {
            draw.stack[draw.stack_count++] = static_cast<std::uint32_t>(address - g_image_base);
        }
    }
    ReadState(draw, frame);
    frame.query_ticks += Counter() - draw.qpc;
}
bool TerrainTracePresent() noexcept {
    const Phase phase = g_phase.load();
    if (phase == Phase::disabled || phase == Phase::pending || phase == Phase::publishing) {
        return false;
    }
    Exclusive lock;
    const Phase current = g_phase.load();
    if (current == Phase::idle && WaitForSingleObject(g_request, 0) == WAIT_OBJECT_0) {
        // Reset only metadata; bounded record storage is overwritten lazily.
        g_frame->sequence = ++g_sequence;
        g_frame->requested_qpc = Counter();
        g_frame->start_qpc = g_frame->end_qpc = g_frame->query_ticks = 0;
        g_frame->context = nullptr; g_frame->thread = 0;
        g_frame->main_clear = g_frame->done3d = g_frame->extra_depth_clear = false;
        g_frame->context_mismatch = g_frame->helpers_available = false;
        g_frame->multitexture = g_frame->combine_supported = false;
        g_frame->unit_count = g_frame->omitted_units = 0;
        g_frame->observed = g_frame->overflow = g_frame->unsafe = g_frame->budget_skipped = 0;
        g_frame->retained = 0;
        g_phase.store(Phase::armed);
    } else if (current == Phase::armed || current == Phase::capturing || current == Phase::sealed) {
        g_frame->end_qpc = Counter();
        if (current != Phase::armed) { OwnerMatches(*g_frame); }
        g_phase.store(Phase::pending);
        return true;
    }
    return false;
}
void PublishPendingTerrainTrace() noexcept {
    if (g_phase.load() != Phase::pending) { return; }
    Exclusive lock;
    if (g_phase.load() != Phase::pending) { return; }
    g_phase.store(Phase::publishing);
    wchar_t final_path[MAX_PATH]{}, temporary_path[MAX_PATH]{};
    const auto& frame = *g_frame;
    const bool paths = swprintf_s(final_path, L"%s\\terrain-trace-%lu-%llu-%llu.json",
        g_directory, g_pid, g_creation, frame.sequence) > 0
        && swprintf_s(temporary_path, L"%s.partial", final_path) > 0;
    if (paths && LocalOrdinaryDirectory(g_directory)) {
        const HANDLE file = CreateFileW(temporary_path, GENERIC_WRITE, 0U, nullptr,
            CREATE_NEW, FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
        if (file != INVALID_HANDLE_VALUE) {
            Json json; json.file = file;
            WriteFrame(json, frame); json.Flush();
            const bool complete = json.ok && FlushFileBuffers(file) != FALSE;
            CloseHandle(file);
            if (complete) { MoveFileExW(temporary_path, final_path, MOVEFILE_WRITE_THROUGH); }
            // Failures remain .partial and are never represented as complete evidence.
        }
    }
    g_phase.store(Phase::idle);
}

} // namespace wonderbane::extension
