#include "cel_shading.h"

#include <Windows.h>

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace wonderbane::extension {
namespace {

constexpr unsigned int kGlFlat = 0x1D00U;
constexpr unsigned int kGlPoints = 0x0000U;
constexpr unsigned int kGlLines = 0x0001U;
constexpr unsigned int kGlLineLoop = 0x0002U;
constexpr unsigned int kGlLineStrip = 0x0003U;
constexpr unsigned int kGlTriangles = 0x0004U;
constexpr unsigned int kGlTriangleStrip = 0x0005U;
constexpr unsigned int kGlTriangleFan = 0x0006U;
constexpr unsigned int kGlQuads = 0x0007U;
constexpr unsigned int kGlQuadStrip = 0x0008U;
constexpr unsigned int kGlPolygon = 0x0009U;
constexpr unsigned int kGlModelViewMatrix = 0x0BA6U;
constexpr unsigned int kGlProjectionMatrix = 0x0BA7U;
constexpr unsigned int kGlDepthWriteMask = 0x0B72U;
constexpr unsigned int kGlTexture2D = 0x0DE1U;
constexpr unsigned int kGlLighting = 0x0B50U;
constexpr unsigned int kGlFog = 0x0B60U;
constexpr unsigned int kGlCullFace = 0x0B44U;
constexpr unsigned int kGlBlend = 0x0BE2U;
constexpr unsigned int kGlAlphaTest = 0x0BC0U;
constexpr unsigned int kGlLineSmooth = 0x0B20U;
constexpr unsigned int kGlDither = 0x0BD0U;
constexpr unsigned int kGlColorLogicOp = 0x0BF2U;
constexpr unsigned int kGlFront = 0x0404U;
constexpr unsigned int kGlFrontAndBack = 0x0408U;
constexpr unsigned int kGlModelView = 0x1700U;
constexpr unsigned int kGlFill = 0x1B02U;
constexpr unsigned int kGlLine = 0x1B01U;
constexpr unsigned int kGlClear = 0x1500U;
constexpr unsigned int kGlAllAttribBits = 0x000FFFFFU;
constexpr int kMaximumOutlinedElementCount = 8192;
constexpr double kMaximumOutlineOriginDistance = 4096.0;
constexpr double kOutlineWorldThickness = 0.5;
constexpr double kMinimumVisibleOutlinePixels = 0.75;
constexpr float kMinimumRasterOutlinePixels = 1.0F;
constexpr float kMaximumRasterOutlinePixels = 4.0F;
constexpr float kMaximumOutlineHullScale = 1.25F;
constexpr std::size_t kCapturedDisplayListCapacity = 65536U;

using GlShadeModel = void(APIENTRY*)(unsigned int mode);
using GlBegin = void(APIENTRY*)(unsigned int mode);
using GlCallList = void(APIENTRY*)(unsigned int list);
using GlNewList = void(APIENTRY*)(unsigned int list, unsigned int mode);
using GlEndList = void(APIENTRY*)();
using GlVertex3f = void(APIENTRY*)(float x, float y, float z);
using GlDeleteLists = void(APIENTRY*)(unsigned int list, int range);
using GlViewport = void(APIENTRY*)(int x, int y, int width, int height);
using GlMatrixMode = void(APIENTRY*)(unsigned int mode);
using GlDrawArrays = void(APIENTRY*)(unsigned int mode, int first, int count);
using GlDrawElements = void(APIENTRY*)(
    unsigned int mode,
    int count,
    unsigned int type,
    const void* indices
);
using GlGetFloatv = void(APIENTRY*)(unsigned int name, float* values);
using GlGetBooleanv = void(APIENTRY*)(unsigned int name, unsigned char* values);
using GlPushAttrib = void(APIENTRY*)(unsigned int mask);
using GlPopAttrib = void(APIENTRY*)();
using GlPushMatrix = void(APIENTRY*)();
using GlPopMatrix = void(APIENTRY*)();
using GlTranslatef = void(APIENTRY*)(float x, float y, float z);
using GlScalef = void(APIENTRY*)(float x, float y, float z);
using GlEnable = void(APIENTRY*)(unsigned int capability);
using GlDisable = void(APIENTRY*)(unsigned int capability);
using GlCullFace = void(APIENTRY*)(unsigned int mode);
using GlPolygonMode = void(APIENTRY*)(unsigned int face, unsigned int mode);
using GlLineWidth = void(APIENTRY*)(float width);
using GlLogicOp = void(APIENTRY*)(unsigned int operation);
using GlDepthMask = void(APIENTRY*)(unsigned char flag);

PVOID volatile g_original_shade_model = nullptr;
PVOID volatile g_original_begin = nullptr;
PVOID volatile g_original_call_list = nullptr;
PVOID volatile g_original_new_list = nullptr;
PVOID volatile g_original_end_list = nullptr;
PVOID volatile g_original_vertex_3f = nullptr;
PVOID volatile g_original_delete_lists = nullptr;
PVOID volatile g_original_viewport = nullptr;
PVOID volatile g_original_matrix_mode = nullptr;
PVOID volatile g_original_draw_arrays = nullptr;
PVOID volatile g_original_draw_elements = nullptr;
PVOID volatile g_get_floatv = nullptr;
PVOID volatile g_get_booleanv = nullptr;
PVOID volatile g_push_attrib = nullptr;
PVOID volatile g_pop_attrib = nullptr;
PVOID volatile g_push_matrix = nullptr;
PVOID volatile g_pop_matrix = nullptr;
PVOID volatile g_translatef = nullptr;
PVOID volatile g_scalef = nullptr;
PVOID volatile g_enable = nullptr;
PVOID volatile g_disable = nullptr;
PVOID volatile g_cull_face = nullptr;
PVOID volatile g_polygon_mode = nullptr;
PVOID volatile g_line_width = nullptr;
PVOID volatile g_logic_op = nullptr;
PVOID volatile g_depth_mask = nullptr;
std::uint32_t* g_shade_model_slot = nullptr;
std::uint32_t* g_begin_slot = nullptr;
std::uint32_t* g_call_list_slot = nullptr;
std::uint32_t* g_new_list_slot = nullptr;
std::uint32_t* g_end_list_slot = nullptr;
std::uint32_t* g_vertex_3f_slot = nullptr;
std::uint32_t* g_delete_lists_slot = nullptr;
std::uint32_t* g_viewport_slot = nullptr;
std::uint32_t* g_matrix_mode_slot = nullptr;
std::uint32_t* g_draw_arrays_slot = nullptr;
std::uint32_t* g_draw_elements_slot = nullptr;
volatile LONG g_viewport_x = 0;
volatile LONG g_viewport_y = 0;
volatile LONG g_viewport_width = 0;
volatile LONG g_viewport_height = 0;
thread_local unsigned int g_current_matrix_mode = kGlModelView;

struct CapturedDisplayListBounds {
    OutlineBounds bounds{};
    bool valid = false;
};

struct ActiveDisplayListCapture {
    unsigned int list = 0U;
    OutlineBounds bounds{};
    bool active = false;
    bool has_vertex = false;
    bool invalid = false;
};

SRWLOCK g_display_list_lock = SRWLOCK_INIT;
std::array<CapturedDisplayListBounds, kCapturedDisplayListCapacity> g_display_list_bounds{};
thread_local ActiveDisplayListCapture g_active_display_list_capture{};

template <typename Function>
Function LoadFunction(PVOID volatile* const storage) noexcept {
    return reinterpret_cast<Function>(InterlockedCompareExchangePointer(
        storage,
        nullptr,
        nullptr
    ));
}

void BeginDisplayListCapture(const unsigned int list) noexcept {
    g_active_display_list_capture = {};
    g_active_display_list_capture.list = list;
    g_active_display_list_capture.active = true;
    if (list < g_display_list_bounds.size()) {
        AcquireSRWLockExclusive(&g_display_list_lock);
        g_display_list_bounds[list] = {};
        ReleaseSRWLockExclusive(&g_display_list_lock);
    }
}

void CaptureDisplayListVertex(const float x, const float y, const float z) noexcept {
    if (
        g_active_display_list_capture.active
        && !g_active_display_list_capture.invalid
    ) {
        if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z)) {
            g_active_display_list_capture.invalid = true;
            return;
        }
        if (!g_active_display_list_capture.has_vertex) {
            g_active_display_list_capture.bounds = {{x, y, z}, {x, y, z}};
            g_active_display_list_capture.has_vertex = true;
        } else if (!ExpandOutlineBounds(
                &g_active_display_list_capture.bounds,
                x,
                y,
                z
            )) {
            g_active_display_list_capture.invalid = true;
        }
    }
}

void EndDisplayListCapture() noexcept {
    if (
        g_active_display_list_capture.active
        && g_active_display_list_capture.list < g_display_list_bounds.size()
        && g_active_display_list_capture.has_vertex
        && !g_active_display_list_capture.invalid
    ) {
        AcquireSRWLockExclusive(&g_display_list_lock);
        CapturedDisplayListBounds& captured = (
            g_display_list_bounds[g_active_display_list_capture.list]
        );
        captured.bounds = g_active_display_list_capture.bounds;
        captured.valid = true;
        ReleaseSRWLockExclusive(&g_display_list_lock);
    }
    g_active_display_list_capture = {};
}

bool IsCompilingDisplayListOnCurrentThread() noexcept {
    return g_active_display_list_capture.active;
}

bool LookupDisplayListHull(
    const unsigned int list,
    OutlineHullTransform* const transform
) noexcept {
    if (transform == nullptr || list >= g_display_list_bounds.size()) {
        return false;
    }
    OutlineBounds bounds{};
    bool valid = false;
    AcquireSRWLockShared(&g_display_list_lock);
    valid = g_display_list_bounds[list].valid;
    if (valid) {
        bounds = g_display_list_bounds[list].bounds;
    }
    ReleaseSRWLockShared(&g_display_list_lock);
    return valid && CenteredOutlineHullTransform(
        &bounds,
        static_cast<float>(kOutlineWorldThickness),
        transform
    );
}

void ForgetDisplayListBounds(const unsigned int list, const int range) noexcept {
    if (range <= 0 || list >= g_display_list_bounds.size()) {
        return;
    }
    const std::size_t first = list;
    const std::size_t requested = static_cast<std::size_t>(range);
    const std::size_t available = g_display_list_bounds.size() - first;
    const std::size_t count = requested < available ? requested : available;
    AcquireSRWLockExclusive(&g_display_list_lock);
    for (std::size_t index = 0U; index < count; ++index) {
        g_display_list_bounds[first + index] = {};
    }
    ReleaseSRWLockExclusive(&g_display_list_lock);
}

void ClearDisplayListBounds() noexcept {
    AcquireSRWLockExclusive(&g_display_list_lock);
    for (CapturedDisplayListBounds& captured : g_display_list_bounds) {
        captured = {};
    }
    ReleaseSRWLockExclusive(&g_display_list_lock);
    g_active_display_list_capture = {};
}

struct OutlineApi {
    GlGetFloatv get_floatv;
    GlGetBooleanv get_booleanv;
    GlPushAttrib push_attrib;
    GlPopAttrib pop_attrib;
    GlPushMatrix push_matrix;
    GlPopMatrix pop_matrix;
    GlTranslatef translatef;
    GlScalef scalef;
    GlEnable enable;
    GlDisable disable;
    GlCullFace cull_face;
    GlPolygonMode polygon_mode;
    GlLineWidth line_width;
    GlLogicOp logic_op;
    GlDepthMask depth_mask;
};

bool LoadOutlineApi(OutlineApi* const api) noexcept {
    if (api == nullptr) {
        return false;
    }
    *api = {
        LoadFunction<GlGetFloatv>(&g_get_floatv),
        LoadFunction<GlGetBooleanv>(&g_get_booleanv),
        LoadFunction<GlPushAttrib>(&g_push_attrib),
        LoadFunction<GlPopAttrib>(&g_pop_attrib),
        LoadFunction<GlPushMatrix>(&g_push_matrix),
        LoadFunction<GlPopMatrix>(&g_pop_matrix),
        LoadFunction<GlTranslatef>(&g_translatef),
        LoadFunction<GlScalef>(&g_scalef),
        LoadFunction<GlEnable>(&g_enable),
        LoadFunction<GlDisable>(&g_disable),
        LoadFunction<GlCullFace>(&g_cull_face),
        LoadFunction<GlPolygonMode>(&g_polygon_mode),
        LoadFunction<GlLineWidth>(&g_line_width),
        LoadFunction<GlLogicOp>(&g_logic_op),
        LoadFunction<GlDepthMask>(&g_depth_mask),
    };
    return api->get_floatv != nullptr
        && api->get_booleanv != nullptr
        && api->push_attrib != nullptr
        && api->pop_attrib != nullptr
        && api->push_matrix != nullptr
        && api->pop_matrix != nullptr
        && api->translatef != nullptr
        && api->scalef != nullptr
        && api->enable != nullptr
        && api->disable != nullptr
        && api->cull_face != nullptr
        && api->polygon_mode != nullptr
        && api->line_width != nullptr
        && api->logic_op != nullptr
        && api->depth_mask != nullptr;
}

template <typename Draw>
void DrawWithSilhouette(
    const Draw& draw,
    const OutlineHullTransform* const hull = nullptr
) noexcept {
    OutlineApi api{};
    std::array<float, 16U> projection{};
    std::array<float, 16U> model_view{};
    std::array<int, 4U> viewport{};
    int matrix_mode = 0;
    unsigned char depth_writes = FALSE;
    if (!LoadOutlineApi(&api)) {
        draw();
        return;
    }
    api.get_floatv(kGlProjectionMatrix, projection.data());
    api.get_floatv(kGlModelViewMatrix, model_view.data());
    viewport = {
        static_cast<int>(InterlockedCompareExchange(&g_viewport_x, 0, 0)),
        static_cast<int>(InterlockedCompareExchange(&g_viewport_y, 0, 0)),
        static_cast<int>(InterlockedCompareExchange(&g_viewport_width, 0, 0)),
        static_cast<int>(InterlockedCompareExchange(&g_viewport_height, 0, 0)),
    };
    matrix_mode = static_cast<int>(g_current_matrix_mode);
    api.get_booleanv(kGlDepthWriteMask, &depth_writes);
    const float outline_width = PerspectiveOutlineLineWidth(
        projection.data(),
        projection.size(),
        model_view.data(),
        model_view.size(),
        viewport.data(),
        viewport.size()
    );
    if (
        !IsPerspectiveProjectionMatrix(projection.data(), projection.size())
        || !IsLocalOutlineModelViewMatrix(model_view.data(), model_view.size())
        || outline_width <= 0.0F
        || depth_writes == FALSE
    ) {
        draw();
        return;
    }

    api.push_attrib(kGlAllAttribBits);
    api.disable(kGlTexture2D);
    api.disable(kGlLighting);
    api.disable(kGlFog);
    api.disable(kGlBlend);
    api.disable(kGlAlphaTest);
    api.disable(kGlLineSmooth);
    api.disable(kGlDither);
    api.enable(kGlColorLogicOp);
    api.logic_op(kGlClear);
    api.depth_mask(FALSE);
    if (hull != nullptr && matrix_mode == static_cast<int>(kGlModelView)) {
        api.enable(kGlCullFace);
        api.cull_face(kGlFront);
        api.polygon_mode(kGlFrontAndBack, kGlFill);
        api.push_matrix();
        api.translatef(hull->center[0], hull->center[1], hull->center[2]);
        api.scalef(hull->scale, hull->scale, hull->scale);
        api.translatef(-hull->center[0], -hull->center[1], -hull->center[2]);
        draw();
        api.pop_matrix();
    }
    api.disable(kGlCullFace);
    api.polygon_mode(kGlFrontAndBack, kGlLine);
    api.line_width(outline_width);
    draw();
    api.pop_attrib();

    draw();
}

template <typename Value>
Value* ImageValue(
    std::uint8_t* const image,
    const std::size_t image_size,
    const std::uint32_t rva,
    const std::size_t count = 1U
) noexcept {
    if (
        image == nullptr
        || count == 0U
        || count > image_size / sizeof(Value)
        || rva > image_size
        || count * sizeof(Value) > image_size - rva
    ) {
        return nullptr;
    }
    return reinterpret_cast<Value*>(image + rva);
}

bool EqualAsciiInsensitive(
    const std::uint8_t* const image,
    const std::size_t image_size,
    const std::uint32_t rva,
    const char* const expected
) noexcept {
    if (image == nullptr || expected == nullptr || rva >= image_size) {
        return false;
    }
    std::size_t offset = rva;
    for (std::size_t index = 0U; ; ++index) {
        if (offset >= image_size) {
            return false;
        }
        const unsigned char actual = image[offset++];
        const unsigned char wanted = static_cast<unsigned char>(expected[index]);
        const auto fold = [](const unsigned char value) noexcept {
            return value >= static_cast<unsigned char>('A')
                    && value <= static_cast<unsigned char>('Z')
                ? static_cast<unsigned char>(value + ('a' - 'A'))
                : value;
        };
        if (fold(actual) != fold(wanted)) {
            return false;
        }
        if (actual == 0U) {
            return true;
        }
    }
}

void APIENTRY StrongShadeModel(const unsigned int) noexcept {
    const auto original = LoadFunction<GlShadeModel>(&g_original_shade_model);
    if (original != nullptr) {
        original(kGlFlat);
    }
}

void APIENTRY StrongBegin(const unsigned int mode) noexcept {
    const auto shade_model = LoadFunction<GlShadeModel>(&g_original_shade_model);
    if (shade_model != nullptr) {
        shade_model(kGlFlat);
    }
    const auto original = LoadFunction<GlBegin>(&g_original_begin);
    if (original != nullptr) {
        original(mode);
    }
}

void APIENTRY StrongNewList(const unsigned int list, const unsigned int mode) noexcept {
    const auto original = LoadFunction<GlNewList>(&g_original_new_list);
    if (original != nullptr) {
        BeginDisplayListCapture(list);
        original(list, mode);
    }
}

void APIENTRY StrongEndList() noexcept {
    const auto original = LoadFunction<GlEndList>(&g_original_end_list);
    if (original != nullptr) {
        original();
        EndDisplayListCapture();
    }
}

void APIENTRY StrongVertex3f(const float x, const float y, const float z) noexcept {
    CaptureDisplayListVertex(x, y, z);
    const auto original = LoadFunction<GlVertex3f>(&g_original_vertex_3f);
    if (original != nullptr) {
        original(x, y, z);
    }
}

void APIENTRY StrongDeleteLists(const unsigned int list, const int range) noexcept {
    const auto original = LoadFunction<GlDeleteLists>(&g_original_delete_lists);
    if (original != nullptr) {
        original(list, range);
        ForgetDisplayListBounds(list, range);
    }
}

void APIENTRY StrongViewport(
    const int x,
    const int y,
    const int width,
    const int height
) noexcept {
    const auto original = LoadFunction<GlViewport>(&g_original_viewport);
    if (original != nullptr) {
        original(x, y, width, height);
        if (!IsCompilingDisplayListOnCurrentThread()) {
            InterlockedExchange(&g_viewport_x, x);
            InterlockedExchange(&g_viewport_y, y);
            InterlockedExchange(&g_viewport_width, width);
            InterlockedExchange(&g_viewport_height, height);
        }
    }
}

void APIENTRY StrongMatrixMode(const unsigned int mode) noexcept {
    const auto original = LoadFunction<GlMatrixMode>(&g_original_matrix_mode);
    if (original != nullptr) {
        original(mode);
        if (!IsCompilingDisplayListOnCurrentThread()) {
            g_current_matrix_mode = mode;
        }
    }
}

void APIENTRY StrongCallList(const unsigned int list) noexcept {
    const auto original = LoadFunction<GlCallList>(&g_original_call_list);
    if (original != nullptr) {
        if (IsCompilingDisplayListOnCurrentThread()) {
            original(list);
            return;
        }
        OutlineHullTransform hull{};
        const bool has_hull = LookupDisplayListHull(list, &hull);
        DrawWithSilhouette(
            [original, list]() noexcept { original(list); },
            has_hull ? &hull : nullptr
        );
    }
}

void APIENTRY StrongDrawArrays(
    const unsigned int mode,
    const int first,
    const int count
) noexcept {
    const auto original = LoadFunction<GlDrawArrays>(&g_original_draw_arrays);
    if (original != nullptr) {
        const auto draw = [original, mode, first, count]() noexcept {
            original(mode, first, count);
        };
        if (IsCompilingDisplayListOnCurrentThread()) {
            draw();
        } else if (IsOutlinePrimitive(mode, count)) {
            DrawWithSilhouette(draw);
        } else {
            draw();
        }
    }
}

void APIENTRY StrongDrawElements(
    const unsigned int mode,
    const int count,
    const unsigned int type,
    const void* const indices
) noexcept {
    const auto original = LoadFunction<GlDrawElements>(&g_original_draw_elements);
    if (original != nullptr) {
        const auto draw = [original, mode, count, type, indices]() noexcept {
            original(mode, count, type, indices);
        };
        if (IsCompilingDisplayListOnCurrentThread()) {
            draw();
        } else if (IsOutlinePrimitive(mode, count)) {
            DrawWithSilhouette(draw);
        } else {
            draw();
        }
    }
}

DWORD ReplaceImportSlot(
    std::uint32_t* const slot,
    const std::uint32_t expected,
    const std::uint32_t replacement
) noexcept {
    DWORD previous_protection = 0U;
    if (VirtualProtect(
            slot,
            sizeof(*slot),
            PAGE_READWRITE,
            &previous_protection
        ) == FALSE) {
        return GetLastError();
    }
    const LONG previous = InterlockedCompareExchange(
        reinterpret_cast<volatile LONG*>(slot),
        static_cast<LONG>(replacement),
        static_cast<LONG>(expected)
    );
    DWORD ignored_protection = 0U;
    const BOOL restore_result = VirtualProtect(
        slot,
        sizeof(*slot),
        previous_protection,
        &ignored_protection
    );
    if (previous != static_cast<LONG>(expected)) {
        return ERROR_INVALID_DATA;
    }
    if (restore_result == FALSE) {
        const DWORD restore_error = GetLastError();
        InterlockedCompareExchange(
            reinterpret_cast<volatile LONG*>(slot),
            static_cast<LONG>(expected),
            static_cast<LONG>(replacement)
        );
        VirtualProtect(
            slot,
            sizeof(*slot),
            previous_protection,
            &ignored_protection
        );
        return restore_error;
    }
    return ERROR_SUCCESS;
}

struct ImportHookPlan {
    const char* symbol_name;
    PVOID replacement;
    PVOID original;
    std::uint32_t* slot;
    PVOID volatile* original_storage;
    std::uint32_t** slot_storage;
};

struct HelperFunctionPlan {
    const char* symbol_name;
    PVOID volatile* storage;
    PVOID resolved;
};

bool RestoreHook(
    std::uint32_t** const slot_storage,
    PVOID volatile* const original_storage,
    PVOID const replacement
) noexcept {
    std::uint32_t* const slot = *slot_storage;
    PVOID const original = LoadFunction<PVOID>(original_storage);
    if (slot == nullptr && original == nullptr) {
        return true;
    }
    if (slot == nullptr || original == nullptr) {
        return false;
    }
    const std::uintptr_t original_address = reinterpret_cast<std::uintptr_t>(original);
    const std::uintptr_t replacement_address = reinterpret_cast<std::uintptr_t>(replacement);
    if (original_address > UINT32_MAX || replacement_address > UINT32_MAX) {
        return false;
    }
    const DWORD result = ReplaceImportSlot(
        slot,
        static_cast<std::uint32_t>(replacement_address),
        static_cast<std::uint32_t>(original_address)
    );
    if (result != ERROR_SUCCESS) {
        return false;
    }
    *slot_storage = nullptr;
    InterlockedExchangePointer(original_storage, nullptr);
    return true;
}

}  // namespace

bool IsPerspectiveProjectionMatrix(
    const float* const matrix,
    const std::size_t count
) noexcept {
    if (matrix == nullptr || count != 16U) {
        return false;
    }
    for (std::size_t index = 0U; index < count; ++index) {
        if (!std::isfinite(matrix[index])) {
            return false;
        }
    }
    return std::fabs(matrix[15]) < 0.001F
        && std::fabs(matrix[11]) > 0.25F;
}

bool IsLocalOutlineModelViewMatrix(
    const float* const matrix,
    const std::size_t count
) noexcept {
    if (matrix == nullptr || count != 16U) {
        return false;
    }
    for (std::size_t index = 0U; index < count; ++index) {
        if (!std::isfinite(matrix[index])) {
            return false;
        }
    }
    if (
        std::fabs(matrix[3]) > 0.001F
        || std::fabs(matrix[7]) > 0.001F
        || std::fabs(matrix[11]) > 0.001F
        || std::fabs(matrix[15] - 1.0F) > 0.001F
    ) {
        return false;
    }
    const double x = matrix[12];
    const double y = matrix[13];
    const double z = matrix[14];
    const double maximum_squared = (
        kMaximumOutlineOriginDistance * kMaximumOutlineOriginDistance
    );
    return x * x + y * y + z * z <= maximum_squared;
}

float PerspectiveOutlineLineWidth(
    const float* const projection,
    const std::size_t projection_count,
    const float* const model_view,
    const std::size_t model_view_count,
    const int* const viewport,
    const std::size_t viewport_count
) noexcept {
    if (
        projection == nullptr
        || projection_count != 16U
        || model_view == nullptr
        || model_view_count != 16U
        || viewport == nullptr
        || viewport_count != 4U
        || viewport[2] <= 0
        || viewport[3] <= 0
    ) {
        return 0.0F;
    }
    if (
        !std::isfinite(projection[5])
        || !std::isfinite(model_view[14])
    ) {
        return 0.0F;
    }
    const double depth = std::fabs(static_cast<double>(model_view[14]));
    if (depth < 0.001) {
        return kMaximumRasterOutlinePixels;
    }
    const double pixels = (
        static_cast<double>(viewport[3])
        * std::fabs(static_cast<double>(projection[5]))
        * kOutlineWorldThickness
        / (2.0 * depth)
    );
    if (!std::isfinite(pixels) || pixels < kMinimumVisibleOutlinePixels) {
        return 0.0F;
    }
    if (pixels <= kMinimumRasterOutlinePixels) {
        return kMinimumRasterOutlinePixels;
    }
    if (pixels >= kMaximumRasterOutlinePixels) {
        return kMaximumRasterOutlinePixels;
    }
    return static_cast<float>(pixels);
}

bool ExpandOutlineBounds(
    OutlineBounds* const bounds,
    const float x,
    const float y,
    const float z
) noexcept {
    if (
        bounds == nullptr
        || !std::isfinite(x)
        || !std::isfinite(y)
        || !std::isfinite(z)
    ) {
        return false;
    }
    const std::array<float, 3U> vertex{x, y, z};
    for (std::size_t axis = 0U; axis < vertex.size(); ++axis) {
        if (
            !std::isfinite(bounds->minimum[axis])
            || !std::isfinite(bounds->maximum[axis])
            || bounds->minimum[axis] > bounds->maximum[axis]
        ) {
            return false;
        }
        if (vertex[axis] < bounds->minimum[axis]) {
            bounds->minimum[axis] = vertex[axis];
        }
        if (vertex[axis] > bounds->maximum[axis]) {
            bounds->maximum[axis] = vertex[axis];
        }
    }
    return true;
}

bool CenteredOutlineHullTransform(
    const OutlineBounds* const bounds,
    const float world_thickness,
    OutlineHullTransform* const transform
) noexcept {
    if (
        bounds == nullptr
        || transform == nullptr
        || !std::isfinite(world_thickness)
        || world_thickness <= 0.0F
    ) {
        return false;
    }
    double radius_squared = 0.0;
    OutlineHullTransform candidate{};
    for (std::size_t axis = 0U; axis < 3U; ++axis) {
        const float minimum = bounds->minimum[axis];
        const float maximum = bounds->maximum[axis];
        if (
            !std::isfinite(minimum)
            || !std::isfinite(maximum)
            || minimum > maximum
        ) {
            return false;
        }
        candidate.center[axis] = minimum + (maximum - minimum) * 0.5F;
        const double half_extent = (
            static_cast<double>(maximum) - static_cast<double>(minimum)
        ) * 0.5;
        radius_squared += half_extent * half_extent;
    }
    const double radius = std::sqrt(radius_squared);
    if (!std::isfinite(radius) || radius < 0.001) {
        return false;
    }
    const double requested_scale = 1.0
        + static_cast<double>(world_thickness) / radius;
    candidate.scale = static_cast<float>(
        requested_scale > kMaximumOutlineHullScale
            ? kMaximumOutlineHullScale
            : requested_scale
    );
    if (!std::isfinite(candidate.scale) || candidate.scale <= 1.0F) {
        return false;
    }
    *transform = candidate;
    return true;
}

bool IsOutlinePrimitive(const unsigned int mode, const int count) noexcept {
    if (count < 3 || count > kMaximumOutlinedElementCount) {
        return false;
    }
    switch (mode) {
        case kGlTriangles:
        case kGlTriangleStrip:
        case kGlTriangleFan:
        case kGlQuads:
        case kGlQuadStrip:
        case kGlPolygon:
            return true;
        case kGlPoints:
        case kGlLines:
        case kGlLineLoop:
        case kGlLineStrip:
        default:
            return false;
    }
}

std::uint32_t* FindImportAddressSlot(
    std::uint8_t* const image,
    const std::size_t image_size,
    const char* const library_name,
    const char* const symbol_name
) noexcept {
    if (
        image == nullptr
        || library_name == nullptr
        || symbol_name == nullptr
        || library_name[0] == '\0'
        || symbol_name[0] == '\0'
        || image_size < sizeof(IMAGE_DOS_HEADER)
    ) {
        return nullptr;
    }
    const auto* const dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(image);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0) {
        return nullptr;
    }
    const std::size_t nt_offset = static_cast<std::size_t>(dos->e_lfanew);
    if (nt_offset > image_size || sizeof(IMAGE_NT_HEADERS32) > image_size - nt_offset) {
        return nullptr;
    }
    const auto* const nt = reinterpret_cast<const IMAGE_NT_HEADERS32*>(image + nt_offset);
    if (
        nt->Signature != IMAGE_NT_SIGNATURE
        || nt->FileHeader.Machine != IMAGE_FILE_MACHINE_I386
        || nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR32_MAGIC
        || nt->OptionalHeader.SizeOfImage != image_size
        || nt->OptionalHeader.NumberOfRvaAndSizes <= IMAGE_DIRECTORY_ENTRY_IMPORT
    ) {
        return nullptr;
    }
    const IMAGE_DATA_DIRECTORY imports = (
        nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT]
    );
    if (
        imports.VirtualAddress == 0U
        || imports.Size < sizeof(IMAGE_IMPORT_DESCRIPTOR)
        || imports.VirtualAddress > image_size
        || imports.Size > image_size - imports.VirtualAddress
    ) {
        return nullptr;
    }

    const std::size_t descriptor_count = imports.Size / sizeof(IMAGE_IMPORT_DESCRIPTOR);
    auto* const descriptors = ImageValue<IMAGE_IMPORT_DESCRIPTOR>(
        image,
        image_size,
        imports.VirtualAddress,
        descriptor_count
    );
    if (descriptors == nullptr) {
        return nullptr;
    }
    std::uint32_t* found = nullptr;
    bool terminated = false;
    for (std::size_t descriptor_index = 0U; descriptor_index < descriptor_count; ++descriptor_index) {
        const IMAGE_IMPORT_DESCRIPTOR& descriptor = descriptors[descriptor_index];
        if (
            descriptor.Name == 0U
            && descriptor.FirstThunk == 0U
            && descriptor.OriginalFirstThunk == 0U
            && descriptor.TimeDateStamp == 0U
            && descriptor.ForwarderChain == 0U
        ) {
            terminated = true;
            break;
        }
        if (!EqualAsciiInsensitive(image, image_size, descriptor.Name, library_name)) {
            continue;
        }
        const std::uint32_t names_rva = descriptor.OriginalFirstThunk != 0U
            ? descriptor.OriginalFirstThunk
            : descriptor.FirstThunk;
        if (
            names_rva == 0U
            || names_rva >= image_size
            || descriptor.FirstThunk == 0U
            || descriptor.FirstThunk >= image_size
        ) {
            return nullptr;
        }
        const std::size_t name_capacity = (image_size - names_rva) / sizeof(IMAGE_THUNK_DATA32);
        const std::size_t address_capacity = (
            image_size - descriptor.FirstThunk
        ) / sizeof(IMAGE_THUNK_DATA32);
        const std::size_t thunk_count = name_capacity < address_capacity
            ? name_capacity
            : address_capacity;
        auto* const names = ImageValue<IMAGE_THUNK_DATA32>(
            image,
            image_size,
            names_rva,
            thunk_count
        );
        auto* const addresses = ImageValue<IMAGE_THUNK_DATA32>(
            image,
            image_size,
            descriptor.FirstThunk,
            thunk_count
        );
        if (names == nullptr || addresses == nullptr) {
            return nullptr;
        }
        bool thunk_terminated = false;
        for (std::size_t thunk_index = 0U; thunk_index < thunk_count; ++thunk_index) {
            const std::uint32_t name_rva = names[thunk_index].u1.AddressOfData;
            if (name_rva == 0U) {
                thunk_terminated = true;
                break;
            }
            if ((name_rva & IMAGE_ORDINAL_FLAG32) != 0U) {
                continue;
            }
            constexpr std::uint32_t kImportHintSize = sizeof(std::uint16_t);
            if (
                name_rva > image_size
                || kImportHintSize > image_size - name_rva
                || !EqualAsciiInsensitive(
                    image,
                    image_size,
                    name_rva + kImportHintSize,
                    symbol_name
                )
            ) {
                continue;
            }
            auto* const candidate = reinterpret_cast<std::uint32_t*>(
                &addresses[thunk_index].u1.Function
            );
            if (found != nullptr) {
                return nullptr;
            }
            found = candidate;
        }
        if (!thunk_terminated) {
            return nullptr;
        }
    }
    return terminated ? found : nullptr;
}

DWORD StartStrongCelShading() noexcept {
    static_assert(sizeof(void*) == sizeof(std::uint32_t));
    if (
        g_shade_model_slot != nullptr
        || g_begin_slot != nullptr
        || g_call_list_slot != nullptr
        || g_new_list_slot != nullptr
        || g_end_list_slot != nullptr
        || g_vertex_3f_slot != nullptr
        || g_delete_lists_slot != nullptr
        || g_viewport_slot != nullptr
        || g_matrix_mode_slot != nullptr
        || g_draw_arrays_slot != nullptr
        || g_draw_elements_slot != nullptr
        || g_original_shade_model != nullptr
        || g_original_begin != nullptr
        || g_original_call_list != nullptr
        || g_original_new_list != nullptr
        || g_original_end_list != nullptr
        || g_original_vertex_3f != nullptr
        || g_original_delete_lists != nullptr
        || g_original_viewport != nullptr
        || g_original_matrix_mode != nullptr
        || g_original_draw_arrays != nullptr
        || g_original_draw_elements != nullptr
        || g_get_floatv != nullptr
        || g_get_booleanv != nullptr
        || g_push_attrib != nullptr
        || g_pop_attrib != nullptr
        || g_push_matrix != nullptr
        || g_pop_matrix != nullptr
        || g_translatef != nullptr
        || g_scalef != nullptr
        || g_enable != nullptr
        || g_disable != nullptr
        || g_cull_face != nullptr
        || g_polygon_mode != nullptr
        || g_line_width != nullptr
        || g_logic_op != nullptr
        || g_depth_mask != nullptr
    ) {
        return ERROR_ALREADY_INITIALIZED;
    }
    const HMODULE executable = GetModuleHandleW(nullptr);
    const HMODULE opengl = GetModuleHandleW(L"OPENGL32.dll");
    if (executable == nullptr || opengl == nullptr) {
        return ERROR_MOD_NOT_FOUND;
    }
    const auto* const dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(executable);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0) {
        return ERROR_BAD_EXE_FORMAT;
    }
    const auto* const nt = reinterpret_cast<const IMAGE_NT_HEADERS32*>(
        reinterpret_cast<const std::uint8_t*>(executable) + dos->e_lfanew
    );
    if (
        nt->Signature != IMAGE_NT_SIGNATURE
        || nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR32_MAGIC
    ) {
        return ERROR_BAD_EXE_FORMAT;
    }
    std::array<ImportHookPlan, 11U> plans{{
        {
            "glShadeModel",
            reinterpret_cast<PVOID>(&StrongShadeModel),
            nullptr,
            nullptr,
            &g_original_shade_model,
            &g_shade_model_slot,
        },
        {
            "glBegin",
            reinterpret_cast<PVOID>(&StrongBegin),
            nullptr,
            nullptr,
            &g_original_begin,
            &g_begin_slot,
        },
        {
            "glCallList",
            reinterpret_cast<PVOID>(&StrongCallList),
            nullptr,
            nullptr,
            &g_original_call_list,
            &g_call_list_slot,
        },
        {
            "glNewList",
            reinterpret_cast<PVOID>(&StrongNewList),
            nullptr,
            nullptr,
            &g_original_new_list,
            &g_new_list_slot,
        },
        {
            "glEndList",
            reinterpret_cast<PVOID>(&StrongEndList),
            nullptr,
            nullptr,
            &g_original_end_list,
            &g_end_list_slot,
        },
        {
            "glVertex3f",
            reinterpret_cast<PVOID>(&StrongVertex3f),
            nullptr,
            nullptr,
            &g_original_vertex_3f,
            &g_vertex_3f_slot,
        },
        {
            "glDeleteLists",
            reinterpret_cast<PVOID>(&StrongDeleteLists),
            nullptr,
            nullptr,
            &g_original_delete_lists,
            &g_delete_lists_slot,
        },
        {
            "glViewport",
            reinterpret_cast<PVOID>(&StrongViewport),
            nullptr,
            nullptr,
            &g_original_viewport,
            &g_viewport_slot,
        },
        {
            "glMatrixMode",
            reinterpret_cast<PVOID>(&StrongMatrixMode),
            nullptr,
            nullptr,
            &g_original_matrix_mode,
            &g_matrix_mode_slot,
        },
        {
            "glDrawArrays",
            reinterpret_cast<PVOID>(&StrongDrawArrays),
            nullptr,
            nullptr,
            &g_original_draw_arrays,
            &g_draw_arrays_slot,
        },
        {
            "glDrawElements",
            reinterpret_cast<PVOID>(&StrongDrawElements),
            nullptr,
            nullptr,
            &g_original_draw_elements,
            &g_draw_elements_slot,
        },
    }};
    auto* const image = reinterpret_cast<std::uint8_t*>(executable);
    for (ImportHookPlan& plan : plans) {
        plan.slot = FindImportAddressSlot(
            image,
            nt->OptionalHeader.SizeOfImage,
            "OPENGL32.dll",
            plan.symbol_name
        );
        plan.original = reinterpret_cast<PVOID>(GetProcAddress(opengl, plan.symbol_name));
        if (plan.slot == nullptr || plan.original == nullptr) {
            return ERROR_PROC_NOT_FOUND;
        }
        const std::uintptr_t original_address = reinterpret_cast<std::uintptr_t>(plan.original);
        const std::uintptr_t replacement_address = reinterpret_cast<std::uintptr_t>(
            plan.replacement
        );
        if (
            original_address > UINT32_MAX
            || replacement_address > UINT32_MAX
            || *plan.slot != static_cast<std::uint32_t>(original_address)
        ) {
            return ERROR_INVALID_ADDRESS;
        }
    }
    for (std::size_t left = 0U; left < plans.size(); ++left) {
        for (std::size_t right = left + 1U; right < plans.size(); ++right) {
            if (plans[left].slot == plans[right].slot) {
                return ERROR_INVALID_DATA;
            }
        }
    }

    std::array<HelperFunctionPlan, 15U> helpers{{
        {"glGetFloatv", &g_get_floatv, nullptr},
        {"glGetBooleanv", &g_get_booleanv, nullptr},
        {"glPushAttrib", &g_push_attrib, nullptr},
        {"glPopAttrib", &g_pop_attrib, nullptr},
        {"glPushMatrix", &g_push_matrix, nullptr},
        {"glPopMatrix", &g_pop_matrix, nullptr},
        {"glTranslatef", &g_translatef, nullptr},
        {"glScalef", &g_scalef, nullptr},
        {"glEnable", &g_enable, nullptr},
        {"glDisable", &g_disable, nullptr},
        {"glCullFace", &g_cull_face, nullptr},
        {"glPolygonMode", &g_polygon_mode, nullptr},
        {"glLineWidth", &g_line_width, nullptr},
        {"glLogicOp", &g_logic_op, nullptr},
        {"glDepthMask", &g_depth_mask, nullptr},
    }};
    for (HelperFunctionPlan& helper : helpers) {
        helper.resolved = reinterpret_cast<PVOID>(GetProcAddress(opengl, helper.symbol_name));
        if (helper.resolved == nullptr) {
            return ERROR_PROC_NOT_FOUND;
        }
    }
    for (HelperFunctionPlan& helper : helpers) {
        InterlockedExchangePointer(helper.storage, helper.resolved);
    }
    ClearDisplayListBounds();
    InterlockedExchange(&g_viewport_x, 0);
    InterlockedExchange(&g_viewport_y, 0);
    InterlockedExchange(&g_viewport_width, 0);
    InterlockedExchange(&g_viewport_height, 0);
    g_current_matrix_mode = kGlModelView;
    for (ImportHookPlan& plan : plans) {
        InterlockedExchangePointer(plan.original_storage, plan.original);
        const DWORD result = ReplaceImportSlot(
            plan.slot,
            static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(plan.original)),
            static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(plan.replacement))
        );
        if (result != ERROR_SUCCESS) {
            const auto replacement_address = static_cast<std::uint32_t>(
                reinterpret_cast<std::uintptr_t>(plan.replacement)
            );
            if (*plan.slot == replacement_address) {
                *plan.slot_storage = plan.slot;
            } else {
                InterlockedExchangePointer(plan.original_storage, nullptr);
            }
            StopStrongCelShading();
            return result;
        }
        *plan.slot_storage = plan.slot;
    }
    return ERROR_SUCCESS;
}

void StopStrongCelShading() noexcept {
    bool restored = true;
    if (!RestoreHook(
            &g_draw_elements_slot,
            &g_original_draw_elements,
            reinterpret_cast<PVOID>(&StrongDrawElements)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_draw_arrays_slot,
            &g_original_draw_arrays,
            reinterpret_cast<PVOID>(&StrongDrawArrays)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_call_list_slot,
            &g_original_call_list,
            reinterpret_cast<PVOID>(&StrongCallList)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_matrix_mode_slot,
            &g_original_matrix_mode,
            reinterpret_cast<PVOID>(&StrongMatrixMode)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_viewport_slot,
            &g_original_viewport,
            reinterpret_cast<PVOID>(&StrongViewport)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_delete_lists_slot,
            &g_original_delete_lists,
            reinterpret_cast<PVOID>(&StrongDeleteLists)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_vertex_3f_slot,
            &g_original_vertex_3f,
            reinterpret_cast<PVOID>(&StrongVertex3f)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_end_list_slot,
            &g_original_end_list,
            reinterpret_cast<PVOID>(&StrongEndList)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_new_list_slot,
            &g_original_new_list,
            reinterpret_cast<PVOID>(&StrongNewList)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_begin_slot,
            &g_original_begin,
            reinterpret_cast<PVOID>(&StrongBegin)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_shade_model_slot,
            &g_original_shade_model,
            reinterpret_cast<PVOID>(&StrongShadeModel)
        )) {
        restored = false;
    }
    if (restored) {
        ClearDisplayListBounds();
        InterlockedExchange(&g_viewport_height, 0);
        InterlockedExchange(&g_viewport_width, 0);
        InterlockedExchange(&g_viewport_y, 0);
        InterlockedExchange(&g_viewport_x, 0);
        g_current_matrix_mode = kGlModelView;
        InterlockedExchangePointer(&g_depth_mask, nullptr);
        InterlockedExchangePointer(&g_logic_op, nullptr);
        InterlockedExchangePointer(&g_line_width, nullptr);
        InterlockedExchangePointer(&g_polygon_mode, nullptr);
        InterlockedExchangePointer(&g_cull_face, nullptr);
        InterlockedExchangePointer(&g_disable, nullptr);
        InterlockedExchangePointer(&g_enable, nullptr);
        InterlockedExchangePointer(&g_scalef, nullptr);
        InterlockedExchangePointer(&g_translatef, nullptr);
        InterlockedExchangePointer(&g_pop_matrix, nullptr);
        InterlockedExchangePointer(&g_push_matrix, nullptr);
        InterlockedExchangePointer(&g_pop_attrib, nullptr);
        InterlockedExchangePointer(&g_push_attrib, nullptr);
        InterlockedExchangePointer(&g_get_booleanv, nullptr);
        InterlockedExchangePointer(&g_get_floatv, nullptr);
    }
}

}  // namespace wonderbane::extension
