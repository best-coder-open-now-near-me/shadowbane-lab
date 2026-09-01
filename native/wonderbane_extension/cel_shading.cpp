#include "cel_shading.h"
#include "banded_lighting.h"

#include <Windows.h>

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <unordered_map>
#include <utility>
#include <vector>

namespace wonderbane::extension {
namespace {

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
constexpr unsigned int kGlDepthTest = 0x0B71U;
constexpr unsigned int kGlFloat = 0x1406U;
constexpr unsigned int kGlUnsignedByte = 0x1401U;
constexpr unsigned int kGlUnsignedShort = 0x1403U;
constexpr unsigned int kGlUnsignedInt = 0x1405U;
constexpr unsigned int kGlVertexArray = 0x8074U;
constexpr unsigned int kGlTextureCoordArray = 0x8078U;
constexpr unsigned int kGlFront = 0x0404U;
constexpr unsigned int kGlBack = 0x0405U;
constexpr unsigned int kGlFrontAndBack = 0x0408U;
constexpr unsigned int kGlModelView = 0x1700U;
constexpr unsigned int kGlFill = 0x1B02U;
constexpr unsigned int kGlLine = 0x1B01U;
constexpr unsigned int kGlClear = 0x1500U;
constexpr unsigned int kGlLequal = 0x0203U;
constexpr unsigned int kGlAllAttribBits = 0x000FFFFFU;
constexpr int kMaximumOutlinedElementCount = 65536;
constexpr int kMaximumFeatureEdgeElementCount = 8192;
constexpr double kMaximumOutlineOriginDistance = 4096.0;
constexpr double kOutlineWorldThickness = 0.5;
constexpr double kMinimumVisibleOutlinePixels = 0.75;
constexpr float kTargetOutlinePixels = 1.35F;
constexpr float kMinimumFeatureEdgeOutlinePixels = 1.0F;
constexpr float kMinimumInteriorContourPixels = 1.0F;
constexpr float kMaximumInteriorContourPixels = 1.0F;
constexpr float kFeatureEdgeCosineThreshold = 0.82F;
constexpr float kMaximumOutlineHullScale = 1.25F;
constexpr std::size_t kCapturedDisplayListCapacity = 65536U;
constexpr std::size_t kMaximumCapturedVerticesPerList = 65536U;
constexpr std::size_t kMaximumFeatureEdgesPerList = 4096U;

using GlShadeModel = void(APIENTRY*)(unsigned int mode);
using GlBegin = void(APIENTRY*)(unsigned int mode);
using GlEnd = void(APIENTRY*)();
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
using GlVertexPointer = void(APIENTRY*)(
    int size,
    unsigned int type,
    int stride,
    const void* pointer
);
using GlTexCoordPointer = void(APIENTRY*)(
    int size,
    unsigned int type,
    int stride,
    const void* pointer
);
using GlTexCoord2f = void(APIENTRY*)(float s, float t);
using GlEnableClientState = void(APIENTRY*)(unsigned int array);
using GlDisableClientState = void(APIENTRY*)(unsigned int array);
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
using GlDepthFunc = void(APIENTRY*)(unsigned int function);
using GlPolygonOffset = void(APIENTRY*)(float factor, float units);

PVOID volatile g_original_shade_model = nullptr;
PVOID volatile g_original_begin = nullptr;
PVOID volatile g_end = nullptr;
PVOID volatile g_original_call_list = nullptr;
PVOID volatile g_original_new_list = nullptr;
PVOID volatile g_original_end_list = nullptr;
PVOID volatile g_original_vertex_3f = nullptr;
PVOID volatile g_original_delete_lists = nullptr;
PVOID volatile g_original_viewport = nullptr;
PVOID volatile g_original_matrix_mode = nullptr;
PVOID volatile g_original_draw_arrays = nullptr;
PVOID volatile g_original_draw_elements = nullptr;
PVOID volatile g_original_vertex_pointer = nullptr;
PVOID volatile g_original_tex_coord_pointer = nullptr;
PVOID volatile g_tex_coord_2f = nullptr;
PVOID volatile g_original_enable_client_state = nullptr;
PVOID volatile g_original_disable_client_state = nullptr;
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
PVOID volatile g_depth_func = nullptr;
PVOID volatile g_polygon_offset = nullptr;
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
std::uint32_t* g_vertex_pointer_slot = nullptr;
std::uint32_t* g_tex_coord_pointer_slot = nullptr;
std::uint32_t* g_enable_client_state_slot = nullptr;
std::uint32_t* g_disable_client_state_slot = nullptr;
volatile LONG g_viewport_x = 0;
volatile LONG g_viewport_y = 0;
volatile LONG g_viewport_width = 0;
volatile LONG g_viewport_height = 0;
thread_local unsigned int g_current_matrix_mode = kGlModelView;

struct VertexArrayState {
    const void* pointer = nullptr;
    int size = 0;
    unsigned int type = 0U;
    int stride = 0;
    bool enabled = false;
};

thread_local VertexArrayState g_vertex_array_state{};
thread_local VertexArrayState g_tex_coord_array_state{};

struct CapturedVertex {
    std::array<float, 3U> position{};
    std::array<float, 2U> tex_coord{};
    bool has_tex_coord = false;
};

struct CapturedDisplayListBounds {
    OutlineBounds bounds{};
    struct FeatureEdge {
        std::array<float, 3U> first{};
        std::array<float, 3U> second{};
        std::array<float, 2U> first_tex_coord{};
        std::array<float, 2U> second_tex_coord{};
        bool has_tex_coords = false;
    };
    std::vector<FeatureEdge> feature_edges{};
    bool valid = false;
};

struct CapturedPrimitiveRange {
    unsigned int mode = 0U;
    std::size_t first = 0U;
    std::size_t count = 0U;
};

struct ActiveDisplayListCapture {
    unsigned int list = 0U;
    OutlineBounds bounds{};
    bool active = false;
    bool has_vertex = false;
    bool invalid = false;
    bool primitive_open = false;
    std::vector<CapturedVertex> vertices{};
    std::vector<CapturedPrimitiveRange> primitives{};
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

struct VertexKey {
    std::array<std::uint32_t, 3U> bits{};
    bool operator==(const VertexKey& other) const noexcept { return bits == other.bits; }
    bool operator<(const VertexKey& other) const noexcept { return bits < other.bits; }
};

struct EdgeKey {
    VertexKey first{};
    VertexKey second{};
    bool operator==(const EdgeKey& other) const noexcept {
        return first == other.first && second == other.second;
    }
};

struct EdgeKeyHash {
    std::size_t operator()(const EdgeKey& edge) const noexcept {
        std::size_t hash = 2166136261U;
        for (const VertexKey* vertex : {&edge.first, &edge.second}) {
            for (const std::uint32_t bits : vertex->bits) {
                hash ^= bits;
                hash *= 16777619U;
            }
        }
        return hash;
    }
};

struct EdgeFaces {
    CapturedDisplayListBounds::FeatureEdge edge{};
    std::array<float, 3U> first_normal{};
    std::size_t face_count = 0U;
    bool sharp = false;
};

VertexKey MakeVertexKey(const std::array<float, 3U>& vertex) noexcept {
    VertexKey key{};
    for (std::size_t index = 0U; index < vertex.size(); ++index) {
        const float canonical = vertex[index] == 0.0F ? 0.0F : vertex[index];
        std::memcpy(&key.bits[index], &canonical, sizeof(canonical));
    }
    return key;
}

std::array<float, 3U> FaceNormal(
    const std::array<float, 3U>& first,
    const std::array<float, 3U>& second,
    const std::array<float, 3U>& third
) noexcept {
    const std::array<float, 3U> left{
        second[0] - first[0], second[1] - first[1], second[2] - first[2]
    };
    const std::array<float, 3U> right{
        third[0] - first[0], third[1] - first[1], third[2] - first[2]
    };
    std::array<float, 3U> normal{
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    };
    const float length = std::sqrt(
        normal[0] * normal[0]
        + normal[1] * normal[1]
        + normal[2] * normal[2]
    );
    if (!std::isfinite(length) || length <= 0.00001F) {
        return {};
    }
    for (float& component : normal) {
        component /= length;
    }
    return normal;
}

using CapturedEdgeMap = std::unordered_map<EdgeKey, EdgeFaces, EdgeKeyHash>;

void AddFaceEdge(
    CapturedEdgeMap* const edges,
    const CapturedVertex& first_vertex,
    const CapturedVertex& second_vertex,
    const std::array<float, 3U>& normal
) {
    const auto& first = first_vertex.position;
    const auto& second = second_vertex.position;
    VertexKey first_key = MakeVertexKey(first);
    VertexKey second_key = MakeVertexKey(second);
    if (first_key == second_key) {
        return;
    }
    CapturedDisplayListBounds::FeatureEdge edge{};
    edge.first = first;
    edge.second = second;
    edge.first_tex_coord = first_vertex.tex_coord;
    edge.second_tex_coord = second_vertex.tex_coord;
    edge.has_tex_coords = first_vertex.has_tex_coord && second_vertex.has_tex_coord;
    if (second_key < first_key) {
        std::swap(first_key, second_key);
        std::swap(edge.first, edge.second);
        std::swap(edge.first_tex_coord, edge.second_tex_coord);
    }
    EdgeFaces& faces = (*edges)[{first_key, second_key}];
    if (faces.face_count == 0U) {
        faces.edge = edge;
        faces.first_normal = normal;
    } else {
        const float cosine = (
            faces.first_normal[0] * normal[0]
            + faces.first_normal[1] * normal[1]
            + faces.first_normal[2] * normal[2]
        );
        if (!std::isfinite(cosine) || cosine < kFeatureEdgeCosineThreshold) {
            faces.sharp = true;
        }
    }
    ++faces.face_count;
}

void AddFace(
    CapturedEdgeMap* const edges,
    const CapturedVertex* const vertices,
    const std::size_t count
) {
    if (edges == nullptr || vertices == nullptr || count < 3U) {
        return;
    }
    std::array<float, 3U> normal{};
    for (std::size_t index = 2U; index < count; ++index) {
        normal = FaceNormal(
            vertices[0].position,
            vertices[index - 1U].position,
            vertices[index].position
        );
        if (normal != std::array<float, 3U>{}) {
            break;
        }
    }
    if (normal == std::array<float, 3U>{}) {
        return;
    }
    for (std::size_t index = 0U; index < count; ++index) {
        AddFaceEdge(edges, vertices[index], vertices[(index + 1U) % count], normal);
    }
}

std::vector<CapturedDisplayListBounds::FeatureEdge> BuildFeatureEdges(
    const ActiveDisplayListCapture& capture
) {
    CapturedEdgeMap edges{};
    for (const CapturedPrimitiveRange& primitive : capture.primitives) {
        if (primitive.first > capture.vertices.size()
            || primitive.count > capture.vertices.size() - primitive.first) {
            continue;
        }
        const auto* const vertices = capture.vertices.data() + primitive.first;
        const std::size_t count = primitive.count;
        if (primitive.mode == kGlTriangles) {
            for (std::size_t index = 0U; index + 2U < count; index += 3U) {
                AddFace(&edges, vertices + index, 3U);
            }
        } else if (primitive.mode == kGlTriangleStrip) {
            for (std::size_t index = 2U; index < count; ++index) {
                const CapturedVertex face[3U]{
                    vertices[index % 2U == 0U ? index - 2U : index - 1U],
                    vertices[index % 2U == 0U ? index - 1U : index - 2U],
                    vertices[index]
                };
                AddFace(&edges, face, 3U);
            }
        } else if (primitive.mode == kGlTriangleFan) {
            for (std::size_t index = 2U; index < count; ++index) {
                const CapturedVertex face[3U]{
                    vertices[0], vertices[index - 1U], vertices[index]
                };
                AddFace(&edges, face, 3U);
            }
        } else if (primitive.mode == kGlQuads) {
            for (std::size_t index = 0U; index + 3U < count; index += 4U) {
                AddFace(&edges, vertices + index, 4U);
            }
        } else if (primitive.mode == kGlQuadStrip) {
            for (std::size_t index = 0U; index + 3U < count; index += 2U) {
                const CapturedVertex face[4U]{
                    vertices[index], vertices[index + 1U],
                    vertices[index + 3U], vertices[index + 2U]
                };
                AddFace(&edges, face, 4U);
            }
        } else if (primitive.mode == kGlPolygon) {
            AddFace(&edges, vertices, count);
        }
    }
    std::vector<CapturedDisplayListBounds::FeatureEdge> result{};
    result.reserve(edges.size() < kMaximumFeatureEdgesPerList
        ? edges.size() : kMaximumFeatureEdgesPerList);
    for (const auto& entry : edges) {
        const EdgeFaces& faces = entry.second;
        if (faces.face_count == 1U || faces.sharp || faces.face_count > 2U) {
            if (result.size() == kMaximumFeatureEdgesPerList) {
                return {};
            }
            result.push_back(faces.edge);
        }
    }
    return result;
}

bool IsReadableMemoryRange(const void* const pointer, const std::size_t size) noexcept {
    if (pointer == nullptr || size == 0U) {
        return false;
    }
    const std::uintptr_t first = reinterpret_cast<std::uintptr_t>(pointer);
    if (size - 1U > UINTPTR_MAX - first) {
        return false;
    }
    const std::uintptr_t last = first + size - 1U;
    std::uintptr_t cursor = first;
    while (cursor <= last) {
        MEMORY_BASIC_INFORMATION information{};
        if (VirtualQuery(
                reinterpret_cast<const void*>(cursor),
                &information,
                sizeof(information)
            ) != sizeof(information)
            || information.State != MEM_COMMIT
            || (information.Protect & (PAGE_GUARD | PAGE_NOACCESS)) != 0U) {
            return false;
        }
        const DWORD readable = information.Protect & 0xFFU;
        if (readable != PAGE_READONLY
            && readable != PAGE_READWRITE
            && readable != PAGE_WRITECOPY
            && readable != PAGE_EXECUTE_READ
            && readable != PAGE_EXECUTE_READWRITE
            && readable != PAGE_EXECUTE_WRITECOPY) {
            return false;
        }
        const std::uintptr_t base = reinterpret_cast<std::uintptr_t>(
            information.BaseAddress
        );
        if (information.RegionSize > UINTPTR_MAX - base) {
            return false;
        }
        const std::uintptr_t next = base + information.RegionSize;
        if (next == 0U || next <= cursor) {
            return false;
        }
        if (next > last) {
            return true;
        }
        cursor = next;
    }
    return true;
}

bool ReadElementIndex(
    const void* const indices,
    const unsigned int type,
    const std::size_t position,
    std::uint32_t* const value
) noexcept {
    if (indices == nullptr || value == nullptr) {
        return false;
    }
    if (type == kGlUnsignedByte) {
        const auto* typed = static_cast<const std::uint8_t*>(indices);
        *value = typed[position];
        return true;
    }
    if (type == kGlUnsignedShort) {
        const auto* typed = static_cast<const std::uint16_t*>(indices);
        *value = typed[position];
        return true;
    }
    if (type == kGlUnsignedInt) {
        const auto* typed = static_cast<const std::uint32_t*>(indices);
        *value = typed[position];
        return true;
    }
    return false;
}

std::size_t ElementIndexSize(const unsigned int type) noexcept {
    if (type == kGlUnsignedByte) {
        return sizeof(std::uint8_t);
    }
    if (type == kGlUnsignedShort) {
        return sizeof(std::uint16_t);
    }
    if (type == kGlUnsignedInt) {
        return sizeof(std::uint32_t);
    }
    return 0U;
}

std::vector<CapturedDisplayListBounds::FeatureEdge> BuildArrayFeatureEdges(
    const unsigned int mode,
    const int first,
    const int count,
    const unsigned int index_type,
    const void* const indices,
    OutlineHullTransform* const hull
) noexcept {
    std::vector<CapturedDisplayListBounds::FeatureEdge> empty{};
    const VertexArrayState state = g_vertex_array_state;
    const VertexArrayState tex_coord_state = g_tex_coord_array_state;
    if (hull != nullptr) {
        *hull = {};
    }
    if (!state.enabled || state.pointer == nullptr || state.type != kGlFloat
        || state.size < 2 || state.size > 4 || state.stride < 0
        || count <= 0 || count > kMaximumOutlinedElementCount || first < 0) {
        return empty;
    }
    const std::size_t component_bytes = static_cast<std::size_t>(state.size)
        * sizeof(float);
    const std::size_t stride = state.stride == 0
        ? component_bytes : static_cast<std::size_t>(state.stride);
    if (stride < component_bytes) {
        return empty;
    }
    const std::size_t requested = static_cast<std::size_t>(count);
    const bool indexed = indices != nullptr;
    const std::size_t index_size = indexed ? ElementIndexSize(index_type) : 0U;
    if (indexed && (index_size == 0U || requested > SIZE_MAX / index_size
        || !IsReadableMemoryRange(indices, requested * index_size))) {
        return empty;
    }
    std::size_t maximum_vertex_index = 0U;
    if (indexed) {
        for (std::size_t position = 0U; position < requested; ++position) {
            std::uint32_t vertex_index = 0U;
            if (!ReadElementIndex(indices, index_type, position, &vertex_index)) {
                return empty;
            }
            if (vertex_index > maximum_vertex_index) {
                maximum_vertex_index = vertex_index;
            }
        }
    } else {
        const std::size_t sequential_first = static_cast<std::size_t>(first);
        if (requested - 1U > SIZE_MAX - sequential_first) {
            return empty;
        }
        maximum_vertex_index = sequential_first + requested - 1U;
    }
    if (maximum_vertex_index > (SIZE_MAX - component_bytes) / stride) {
        return empty;
    }
    const std::size_t required_vertex_bytes = maximum_vertex_index * stride
        + component_bytes;
    if (!IsReadableMemoryRange(state.pointer, required_vertex_bytes)) {
        return empty;
    }
    const bool collect_feature_edges = count <= kMaximumFeatureEdgeElementCount;
    const bool has_tex_coords = collect_feature_edges && tex_coord_state.enabled
        && tex_coord_state.pointer != nullptr
        && tex_coord_state.type == kGlFloat
        && tex_coord_state.size >= 2
        && tex_coord_state.size <= 4
        && tex_coord_state.stride >= 0;
    std::size_t tex_coord_component_bytes = 0U;
    std::size_t tex_coord_stride = 0U;
    if (has_tex_coords) {
        tex_coord_component_bytes = static_cast<std::size_t>(tex_coord_state.size)
            * sizeof(float);
        tex_coord_stride = tex_coord_state.stride == 0
            ? tex_coord_component_bytes
            : static_cast<std::size_t>(tex_coord_state.stride);
        if (tex_coord_stride < tex_coord_component_bytes
            || maximum_vertex_index
                > (SIZE_MAX - tex_coord_component_bytes) / tex_coord_stride
            || !IsReadableMemoryRange(
                tex_coord_state.pointer,
                maximum_vertex_index * tex_coord_stride + tex_coord_component_bytes
            )) {
            tex_coord_component_bytes = 0U;
            tex_coord_stride = 0U;
        }
    }
    try {
        ActiveDisplayListCapture capture{};
        if (collect_feature_edges) {
            capture.vertices.reserve(requested);
        }
        OutlineBounds bounds{};
        bool has_bounds = false;
        for (std::size_t position = 0U; position < requested; ++position) {
            std::uint32_t vertex_index = 0U;
            if (indexed) {
                if (!ReadElementIndex(indices, index_type, position, &vertex_index)) {
                    return empty;
                }
            } else {
                const std::size_t sequential = static_cast<std::size_t>(first) + position;
                if (sequential > UINT32_MAX) {
                    return empty;
                }
                vertex_index = static_cast<std::uint32_t>(sequential);
            }
            if (vertex_index > (SIZE_MAX - component_bytes) / stride) {
                return empty;
            }
            const std::size_t offset = static_cast<std::size_t>(vertex_index) * stride;
            const std::uintptr_t base = reinterpret_cast<std::uintptr_t>(state.pointer);
            if (offset > UINTPTR_MAX - base) {
                return empty;
            }
            const auto* vertex_pointer = reinterpret_cast<const std::uint8_t*>(
                base + offset
            );
            const auto* components = reinterpret_cast<const float*>(vertex_pointer);
            const std::array<float, 3U> vertex{
                components[0], components[1], state.size >= 3 ? components[2] : 0.0F
            };
            if (!std::isfinite(vertex[0]) || !std::isfinite(vertex[1])
                || !std::isfinite(vertex[2])) {
                return empty;
            }
            if (!has_bounds) {
                bounds = {
                    {vertex[0], vertex[1], vertex[2]},
                    {vertex[0], vertex[1], vertex[2]},
                };
                has_bounds = true;
            } else if (!ExpandOutlineBounds(
                    &bounds, vertex[0], vertex[1], vertex[2]
                )) {
                return empty;
            }
            if (!collect_feature_edges) {
                continue;
            }
            CapturedVertex captured{};
            captured.position = vertex;
            if (tex_coord_stride != 0U) {
                const std::size_t tex_coord_offset = static_cast<std::size_t>(
                    vertex_index
                ) * tex_coord_stride;
                const std::uintptr_t tex_coord_base = reinterpret_cast<std::uintptr_t>(
                    tex_coord_state.pointer
                );
                if (tex_coord_offset > UINTPTR_MAX - tex_coord_base) {
                    return empty;
                }
                const auto* tex_coord_components = reinterpret_cast<const float*>(
                    tex_coord_base + tex_coord_offset
                );
                if (!std::isfinite(tex_coord_components[0])
                    || !std::isfinite(tex_coord_components[1])) {
                    return empty;
                }
                captured.tex_coord = {
                    tex_coord_components[0], tex_coord_components[1]
                };
                captured.has_tex_coord = true;
            }
            capture.vertices.push_back(captured);
        }
        if (has_bounds && hull != nullptr) {
            CenteredOutlineHullTransform(
                &bounds,
                static_cast<float>(kOutlineWorldThickness),
                hull
            );
        }
        if (!collect_feature_edges) {
            return empty;
        }
        capture.primitives.push_back({mode, 0U, capture.vertices.size()});
        return BuildFeatureEdges(capture);
    } catch (...) {
        return empty;
    }
}

void CloseCapturedPrimitive() noexcept {
    if (!g_active_display_list_capture.primitive_open) {
        return;
    }
    CapturedPrimitiveRange& primitive = g_active_display_list_capture.primitives.back();
    primitive.count = g_active_display_list_capture.vertices.size() - primitive.first;
    g_active_display_list_capture.primitive_open = false;
}

void CaptureDisplayListBegin(const unsigned int mode) noexcept {
    if (!g_active_display_list_capture.active || g_active_display_list_capture.invalid) {
        return;
    }
    try {
        CloseCapturedPrimitive();
        g_active_display_list_capture.primitives.push_back({
            mode, g_active_display_list_capture.vertices.size(), 0U
        });
        g_active_display_list_capture.primitive_open = true;
    } catch (...) {
        g_active_display_list_capture.invalid = true;
    }
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
        if (!g_active_display_list_capture.primitive_open
            || g_active_display_list_capture.vertices.size()
                == kMaximumCapturedVerticesPerList) {
            g_active_display_list_capture.invalid = true;
            return;
        }
        try {
            CapturedVertex captured{};
            captured.position = {x, y, z};
            g_active_display_list_capture.vertices.push_back(captured);
        } catch (...) {
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
    CloseCapturedPrimitive();
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
        try {
            captured.feature_edges = BuildFeatureEdges(g_active_display_list_capture);
        } catch (...) {
            captured.feature_edges.clear();
        }
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
    GlDepthFunc depth_func;
    GlPolygonOffset polygon_offset;
};

struct ArrayFeatureRequest {
    unsigned int mode = 0U;
    int first = 0;
    int count = 0;
    unsigned int index_type = 0U;
    const void* indices = nullptr;
};

bool IsFilledPrimitiveMode(const unsigned int mode) noexcept {
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

template <typename Draw>
void DrawWithBandedLighting(const Draw& draw) noexcept {
    BandedLightingDraw banded{};
    BeginBandedLightingDraw(&banded);
    draw();
    EndBandedLightingDraw(&banded);
}

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
        LoadFunction<GlDepthFunc>(&g_depth_func),
        LoadFunction<GlPolygonOffset>(&g_polygon_offset),
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
        && api->depth_mask != nullptr
        && api->depth_func != nullptr
        && api->polygon_offset != nullptr;
}

void DrawFeatureEdgeSegments(
    const std::vector<CapturedDisplayListBounds::FeatureEdge>& edges,
    const OutlineApi& api,
    const float outline_width,
    const bool preserve_alpha_test
) noexcept {
    const float contour_width = InteriorContourLineWidth(outline_width);
    const auto begin = LoadFunction<GlBegin>(&g_original_begin);
    const auto vertex = LoadFunction<GlVertex3f>(&g_original_vertex_3f);
    const auto tex_coord = LoadFunction<GlTexCoord2f>(&g_tex_coord_2f);
    const auto end = LoadFunction<GlEnd>(&g_end);
    if (contour_width <= 0.0F || begin == nullptr || vertex == nullptr
        || end == nullptr || edges.empty()) {
        return;
    }
    api.push_attrib(kGlAllAttribBits);
    if (!preserve_alpha_test) {
        api.disable(kGlTexture2D);
        api.disable(kGlAlphaTest);
    }
    api.disable(kGlLighting);
    api.disable(kGlFog);
    api.disable(kGlBlend);
    api.disable(kGlLineSmooth);
    api.disable(kGlDither);
    api.enable(kGlColorLogicOp);
    api.logic_op(kGlClear);
    api.enable(kGlDepthTest);
    api.depth_func(kGlLequal);
    api.depth_mask(FALSE);
    api.disable(kGlCullFace);
    api.line_width(contour_width);
    begin(kGlLines);
    for (const CapturedDisplayListBounds::FeatureEdge& edge : edges) {
        if (preserve_alpha_test && (!edge.has_tex_coords || tex_coord == nullptr)) {
            continue;
        }
        if (preserve_alpha_test) {
            tex_coord(edge.first_tex_coord[0], edge.first_tex_coord[1]);
        }
        vertex(edge.first[0], edge.first[1], edge.first[2]);
        if (preserve_alpha_test) {
            tex_coord(edge.second_tex_coord[0], edge.second_tex_coord[1]);
        }
        vertex(edge.second[0], edge.second[1], edge.second[2]);
    }
    end();
    api.pop_attrib();
}

void DrawDisplayListFeatureEdges(
    const unsigned int list,
    const OutlineApi& api,
    const float outline_width,
    const bool preserve_alpha_test
) noexcept {
    if (list >= g_display_list_bounds.size()) {
        return;
    }
    AcquireSRWLockShared(&g_display_list_lock);
    const CapturedDisplayListBounds& captured = g_display_list_bounds[list];
    if (captured.valid) {
        DrawFeatureEdgeSegments(
            captured.feature_edges, api, outline_width, preserve_alpha_test
        );
    }
    ReleaseSRWLockShared(&g_display_list_lock);
}

template <typename Draw>
void DrawWithSilhouette(
    const Draw& draw,
    const OutlineHullTransform* const hull = nullptr,
    const unsigned int feature_list = UINT32_MAX,
    const ArrayFeatureRequest* const array_features = nullptr
) noexcept {
    OutlineApi api{};
    std::array<float, 16U> projection{};
    std::array<float, 16U> model_view{};
    std::array<int, 4U> viewport{};
    int matrix_mode = 0;
    unsigned char depth_writes = FALSE;
    unsigned char alpha_test_enabled = FALSE;
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
    api.get_booleanv(kGlAlphaTest, &alpha_test_enabled);
    const float outline_width = PerspectiveOutlineLineWidth(
        projection.data(),
        projection.size(),
        model_view.data(),
        model_view.size(),
        viewport.data(),
        viewport.size()
    );
    if (!IsPerspectiveProjectionMatrix(projection.data(), projection.size())) {
        draw();
        return;
    }

    const bool outline_enabled = (
        IsLocalOutlineModelViewMatrix(model_view.data(), model_view.size())
        && outline_width > 0.0F
        && depth_writes != FALSE
    );

    OutlineHullTransform array_hull{};
    const auto feature_edges = !outline_enabled || array_features == nullptr
        ? std::vector<CapturedDisplayListBounds::FeatureEdge>{}
        : BuildArrayFeatureEdges(
            array_features->mode,
            array_features->first,
            array_features->count,
            array_features->index_type,
            array_features->indices,
            &array_hull
        );
    const OutlineHullTransform* effective_hull = hull;
    if (effective_hull == nullptr && array_hull.radius > 0.0F) {
        effective_hull = &array_hull;
    }
    OutlineHullTransform screen_hull{};
    if (effective_hull != nullptr) {
        screen_hull = *effective_hull;
        const double depth = std::fabs(static_cast<double>(model_view[14]));
        const double projection_scale = std::fabs(
            static_cast<double>(projection[5])
        );
        const double pixels_per_world = depth > 0.001
            ? static_cast<double>(viewport[3]) * projection_scale / (2.0 * depth)
            : 0.0;
        if (pixels_per_world > 0.0 && std::isfinite(pixels_per_world)
            && effective_hull->radius > 0.0F) {
            const double requested_scale = 1.0
                + static_cast<double>(outline_width)
                    / pixels_per_world
                    / static_cast<double>(effective_hull->radius);
            screen_hull.scale = static_cast<float>(std::min(
                requested_scale,
                static_cast<double>(kMaximumOutlineHullScale)
            ));
        }
    }

    const bool use_centered_hull = (
        outline_enabled
        &&
        effective_hull != nullptr
        && screen_hull.scale > 1.0F
        && matrix_mode == static_cast<int>(kGlModelView)
    );
    if (use_centered_hull) {
        api.push_attrib(kGlAllAttribBits);
        api.disable(kGlLighting);
        api.disable(kGlFog);
        api.disable(kGlBlend);
        if (alpha_test_enabled == FALSE) {
            api.disable(kGlTexture2D);
            api.disable(kGlAlphaTest);
        }
        api.disable(kGlLineSmooth);
        api.disable(kGlDither);
        api.enable(kGlColorLogicOp);
        api.logic_op(kGlClear);
        api.depth_mask(FALSE);
        api.enable(kGlCullFace);
        api.cull_face(kGlFront);
        api.polygon_mode(kGlFrontAndBack, kGlFill);
        api.push_matrix();
        api.translatef(
            screen_hull.center[0], screen_hull.center[1], screen_hull.center[2]
        );
        api.scalef(screen_hull.scale, screen_hull.scale, screen_hull.scale);
        api.translatef(
            -screen_hull.center[0], -screen_hull.center[1], -screen_hull.center[2]
        );
        draw();
        api.pop_matrix();
        api.pop_attrib();
    }

    DrawWithBandedLighting(draw);
    if (outline_enabled && feature_list != UINT32_MAX) {
        DrawDisplayListFeatureEdges(
            feature_list, api, outline_width, alpha_test_enabled != FALSE
        );
    } else if (outline_enabled && !feature_edges.empty()) {
        DrawFeatureEdgeSegments(
            feature_edges, api, outline_width, alpha_test_enabled != FALSE
        );
    }
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

void APIENTRY StrongShadeModel(const unsigned int mode) noexcept {
    const auto original = LoadFunction<GlShadeModel>(&g_original_shade_model);
    if (original != nullptr) {
        original(mode);
    }
}

void APIENTRY StrongBegin(const unsigned int mode) noexcept {
    CaptureDisplayListBegin(mode);
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
            has_hull ? &hull : nullptr,
            list
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
            const ArrayFeatureRequest request{mode, first, count, 0U, nullptr};
            DrawWithSilhouette(draw, nullptr, UINT32_MAX, &request);
        } else if (count >= 3 && IsFilledPrimitiveMode(mode)) {
            DrawWithBandedLighting(draw);
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
            const ArrayFeatureRequest request{mode, 0, count, type, indices};
            DrawWithSilhouette(draw, nullptr, UINT32_MAX, &request);
        } else if (count >= 3 && IsFilledPrimitiveMode(mode)) {
            DrawWithBandedLighting(draw);
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
        return kTargetOutlinePixels;
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
    return kTargetOutlinePixels;
}

float InteriorContourLineWidth(const float outline_width) noexcept {
    if (
        !std::isfinite(outline_width)
        || outline_width < kMinimumFeatureEdgeOutlinePixels
    ) {
        return 0.0F;
    }
    const float requested = outline_width * 0.35F;
    if (requested <= kMinimumInteriorContourPixels) {
        return kMinimumInteriorContourPixels;
    }
    if (requested >= kMaximumInteriorContourPixels) {
        return kMaximumInteriorContourPixels;
    }
    return requested;
}

std::size_t TriangleFeatureEdgeCount(
    const float* const vertices,
    const std::size_t float_count
) noexcept {
    if (vertices == nullptr || float_count == 0U || float_count % 9U != 0U) {
        return 0U;
    }
    try {
        ActiveDisplayListCapture capture{};
        capture.vertices.reserve(float_count / 3U);
        for (std::size_t index = 0U; index < float_count; index += 3U) {
            capture.vertices.push_back({
                vertices[index], vertices[index + 1U], vertices[index + 2U]
            });
        }
        capture.primitives.push_back({kGlTriangles, 0U, capture.vertices.size()});
        return BuildFeatureEdges(capture).size();
    } catch (...) {
        return 0U;
    }
}

void APIENTRY StrongVertexPointer(
    const int size,
    const unsigned int type,
    const int stride,
    const void* const pointer
) noexcept {
    const auto original = LoadFunction<GlVertexPointer>(&g_original_vertex_pointer);
    if (original != nullptr) {
        original(size, type, stride, pointer);
        g_vertex_array_state.pointer = pointer;
        g_vertex_array_state.size = size;
        g_vertex_array_state.type = type;
        g_vertex_array_state.stride = stride;
    }
}

void APIENTRY StrongTexCoordPointer(
    const int size,
    const unsigned int type,
    const int stride,
    const void* const pointer
) noexcept {
    const auto original = LoadFunction<GlTexCoordPointer>(
        &g_original_tex_coord_pointer
    );
    if (original != nullptr) {
        original(size, type, stride, pointer);
        g_tex_coord_array_state.pointer = pointer;
        g_tex_coord_array_state.size = size;
        g_tex_coord_array_state.type = type;
        g_tex_coord_array_state.stride = stride;
    }
}

void APIENTRY StrongEnableClientState(const unsigned int array) noexcept {
    const auto original = LoadFunction<GlEnableClientState>(
        &g_original_enable_client_state
    );
    if (original != nullptr) {
        original(array);
        if (array == kGlVertexArray) {
            g_vertex_array_state.enabled = true;
        } else if (array == kGlTextureCoordArray) {
            g_tex_coord_array_state.enabled = true;
        }
    }
}

void APIENTRY StrongDisableClientState(const unsigned int array) noexcept {
    const auto original = LoadFunction<GlDisableClientState>(
        &g_original_disable_client_state
    );
    if (original != nullptr) {
        original(array);
        if (array == kGlVertexArray) {
            g_vertex_array_state.enabled = false;
        } else if (array == kGlTextureCoordArray) {
            g_tex_coord_array_state.enabled = false;
        }
    }
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
    candidate.radius = static_cast<float>(radius);
    *transform = candidate;
    return true;
}

bool IsOutlinePrimitive(const unsigned int mode, const int count) noexcept {
    if (count < 3 || count > kMaximumOutlinedElementCount) {
        return false;
    }
    return IsFilledPrimitiveMode(mode);
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
        || g_vertex_pointer_slot != nullptr
        || g_tex_coord_pointer_slot != nullptr
        || g_enable_client_state_slot != nullptr
        || g_disable_client_state_slot != nullptr
        || g_original_shade_model != nullptr
        || g_original_begin != nullptr
        || g_end != nullptr
        || g_original_call_list != nullptr
        || g_original_new_list != nullptr
        || g_original_end_list != nullptr
        || g_original_vertex_3f != nullptr
        || g_original_delete_lists != nullptr
        || g_original_viewport != nullptr
        || g_original_matrix_mode != nullptr
        || g_original_draw_arrays != nullptr
        || g_original_draw_elements != nullptr
        || g_original_vertex_pointer != nullptr
        || g_original_tex_coord_pointer != nullptr
        || g_original_enable_client_state != nullptr
        || g_original_disable_client_state != nullptr
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
    std::array<ImportHookPlan, 15U> plans{{
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
            "glVertexPointer",
            reinterpret_cast<PVOID>(&StrongVertexPointer),
            nullptr,
            nullptr,
            &g_original_vertex_pointer,
            &g_vertex_pointer_slot,
        },
        {
            "glTexCoordPointer",
            reinterpret_cast<PVOID>(&StrongTexCoordPointer),
            nullptr,
            nullptr,
            &g_original_tex_coord_pointer,
            &g_tex_coord_pointer_slot,
        },
        {
            "glEnableClientState",
            reinterpret_cast<PVOID>(&StrongEnableClientState),
            nullptr,
            nullptr,
            &g_original_enable_client_state,
            &g_enable_client_state_slot,
        },
        {
            "glDisableClientState",
            reinterpret_cast<PVOID>(&StrongDisableClientState),
            nullptr,
            nullptr,
            &g_original_disable_client_state,
            &g_disable_client_state_slot,
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

    std::array<HelperFunctionPlan, 19U> helpers{{
        {"glEnd", &g_end, nullptr},
        {"glTexCoord2f", &g_tex_coord_2f, nullptr},
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
        {"glDepthFunc", &g_depth_func, nullptr},
        {"glPolygonOffset", &g_polygon_offset, nullptr},
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
    g_vertex_array_state = {};
    g_tex_coord_array_state = {};
    ResetBandedLighting();
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
            &g_disable_client_state_slot,
            &g_original_disable_client_state,
            reinterpret_cast<PVOID>(&StrongDisableClientState)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_enable_client_state_slot,
            &g_original_enable_client_state,
            reinterpret_cast<PVOID>(&StrongEnableClientState)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_tex_coord_pointer_slot,
            &g_original_tex_coord_pointer,
            reinterpret_cast<PVOID>(&StrongTexCoordPointer)
        )) {
        restored = false;
    }
    if (!RestoreHook(
            &g_vertex_pointer_slot,
            &g_original_vertex_pointer,
            reinterpret_cast<PVOID>(&StrongVertexPointer)
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
        g_vertex_array_state = {};
        g_tex_coord_array_state = {};
        ResetBandedLighting();
        InterlockedExchangePointer(&g_end, nullptr);
        InterlockedExchangePointer(&g_tex_coord_2f, nullptr);
        InterlockedExchangePointer(&g_polygon_offset, nullptr);
        InterlockedExchangePointer(&g_depth_func, nullptr);
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
