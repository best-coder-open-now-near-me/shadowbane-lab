#include "cel_shading.h"
#include "import_hook.h"

// Exercise the actual private import-hook adapters without exposing a test API
// in the production DLL or patching any process import table.
#include "cel_shading.cpp"

#include <Windows.h>

#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include <thread>

namespace {

constexpr std::size_t kImageSize = 0x1000U;
constexpr std::uint32_t kNtRva = 0x80U;
constexpr std::uint32_t kImportRva = 0x200U;
constexpr std::uint32_t kLibraryRva = 0x300U;
constexpr std::uint32_t kNamesRva = 0x340U;
constexpr std::uint32_t kAddressesRva = 0x3A0U;
constexpr std::array<std::uint32_t, 19U> kImportNameRvas{
    0x420U,
    0x440U,
    0x460U,
    0x480U,
    0x4A0U,
    0x4C0U,
    0x4E0U,
    0x500U,
    0x520U,
    0x540U,
    0x560U,
    0x580U,
    0x5A0U,
    0x5C0U,
    0x5E0U,
    0x600U,
    0x620U,
    0x640U,
    0x660U,
};
constexpr std::array<const char*, 19U> kImportNames{
    "glShadeModel",
    "glBegin",
    "glCallList",
    "glNewList",
    "glEndList",
    "glVertex3f",
    "glDeleteLists",
    "glViewport",
    "glMatrixMode",
    "glDrawArrays",
    "glDrawElements",
    "glVertexPointer",
    "glEnableClientState",
    "glDisableClientState",
    "glTexCoordPointer",
    "glEnd",
    "glEnable",
    "glDisable",
    "glDepthMask",
};
constexpr std::array<std::uint32_t, 19U> kImportAddresses{
    0x12345678U,
    0x23456789U,
    0x3456789AU,
    0x456789ABU,
    0x56789ABCU,
    0x6789ABCDU,
    0x789ABCDEU,
    0x89ABCDEFU,
    0x9ABCDEF0U,
    0xABCDEF01U,
    0xBCDEF012U,
    0xCDEF0123U,
    0xDEF01234U,
    0xEF012345U,
    0xF0123456U,
    0x10234567U,
    0x21345678U,
    0x32345678U,
    0x42345678U,
};

int Fail(const wchar_t* const operation) noexcept {
    ::fwprintf(stderr, L"%s failed\n", operation);
    return 1;
}

void WriteImport(
    std::vector<std::uint8_t>& image,
    const std::size_t index,
    const std::uint32_t name_rva,
    const char* const name,
    const std::uint32_t address
) {
    auto* const names = reinterpret_cast<IMAGE_THUNK_DATA32*>(image.data() + kNamesRva);
    auto* const addresses = reinterpret_cast<IMAGE_THUNK_DATA32*>(
        image.data() + kAddressesRva
    );
    names[index].u1.AddressOfData = name_rva;
    addresses[index].u1.Function = address;
    auto* const import_name = reinterpret_cast<IMAGE_IMPORT_BY_NAME*>(image.data() + name_rva);
    import_name->Hint = static_cast<WORD>(index);
    std::memcpy(import_name->Name, name, std::strlen(name) + 1U);
}

std::vector<std::uint8_t> Fixture() {
    std::vector<std::uint8_t> image(kImageSize);
    auto* const dos = reinterpret_cast<IMAGE_DOS_HEADER*>(image.data());
    dos->e_magic = IMAGE_DOS_SIGNATURE;
    dos->e_lfanew = kNtRva;
    auto* const nt = reinterpret_cast<IMAGE_NT_HEADERS32*>(image.data() + kNtRva);
    nt->Signature = IMAGE_NT_SIGNATURE;
    nt->FileHeader.Machine = IMAGE_FILE_MACHINE_I386;
    nt->OptionalHeader.Magic = IMAGE_NT_OPTIONAL_HDR32_MAGIC;
    nt->OptionalHeader.SizeOfImage = static_cast<std::uint32_t>(image.size());
    nt->OptionalHeader.NumberOfRvaAndSizes = IMAGE_NUMBEROF_DIRECTORY_ENTRIES;
    nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT] = {
        kImportRva,
        2U * sizeof(IMAGE_IMPORT_DESCRIPTOR),
    };
    auto* const imports = reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>(
        image.data() + kImportRva
    );
    imports[0].Name = kLibraryRva;
    imports[0].OriginalFirstThunk = kNamesRva;
    imports[0].FirstThunk = kAddressesRva;
    std::memcpy(image.data() + kLibraryRva, "OPENGL32.dll", 13U);
    for (std::size_t index = 0U; index < kImportNames.size(); ++index) {
        WriteImport(
            image,
            index,
            kImportNameRvas[index],
            kImportNames[index],
            kImportAddresses[index]
        );
    }
    return image;
}

bool test_alpha_enabled = false;
unsigned int test_query_count = 0U;
std::uintptr_t test_context = 1U;

void APIENTRY FakeStateQuery(const unsigned int name, unsigned char* const value) {
    ++test_query_count;
    *value = name == 0x0BC0U && test_alpha_enabled ? TRUE : FALSE;
}

HGLRC WINAPI FakeCurrentContext() {
    return reinterpret_cast<HGLRC>(test_context);
}

std::array<float, 16U> test_camera_view{
    0, 0, -1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 200, -40, 300, 1};
std::array<float, 16U> test_camera_projection{
    1, 0, 0, 0, 0, 1.5F, 0, 0, 0, 0, -1.01F, -1, 0, 0, -4, 0};
std::array<int, 4U> test_camera_viewport{0, 0, 1920, 955};
int test_camera_depth = 1;
unsigned int test_camera_queries = 0;
void APIENTRY FakeCameraFloats(unsigned int name, float* values) {
    ++test_camera_queries;
    const auto& source = name == 0x0BA6U ? test_camera_view : test_camera_projection;
    std::memcpy(values, source.data(), sizeof(float) * source.size());
}
void APIENTRY FakeCameraIntegers(unsigned int name, int* values) {
    ++test_camera_queries;
    if (name == 0x0BA3U) *values = test_camera_depth;
    else std::memcpy(values, test_camera_viewport.data(), sizeof(int) * test_camera_viewport.size());
}

bool CheckReviewedSceneCamera() {
    using namespace wonderbane::extension;
    g_get_current_context = reinterpret_cast<PVOID>(&FakeCurrentContext);
    g_get_floatv = reinterpret_cast<PVOID>(&FakeCameraFloats);
    g_get_integerv = reinterpret_cast<PVOID>(&FakeCameraIntegers);
    const auto view = test_camera_view;
    const auto projection = test_camera_projection;
    const auto viewport = test_camera_viewport;
    const auto begin = [&]() {
        g_scene_frame = {};
        g_scene_frame.boundary_mapping_verified = true;
        g_main_scene_context = FakeCurrentContext();
        test_camera_view = view; test_camera_projection = projection;
        test_camera_viewport = viewport; test_camera_depth = 1;
        ObserveMainSceneClear(&g_scene_frame);
        BeginMainSceneCamera();
    };
    const auto world = []() {
        (void)AdvanceSceneFrame(&g_scene_frame,
            {DrawLayer::world_opaque, DrawClassificationReason::depth_writing_opaque});
    };
    const auto finish = [&]() {
        GraphicsCameraState camera{};
        return BeginReviewedSceneUiBoundary(&g_scene_frame) && FinishMainSceneCamera(&camera);
    };
    // The real queue pushes model-view, then loads object transforms. None of
    // those temporary matrices can replace or poison the boundary-owned camera.
    test_camera_queries = 0;
    begin();
    test_camera_depth = 2; test_camera_view[12] += 1000;
    world();
    test_camera_depth = 3; test_camera_view[0] = 0.5F;
    world();
    test_camera_depth = 1; test_camera_view = view;
    bool ok = finish() && test_camera_queries == 8U;
    GraphicsCameraState camera{};
    ok = ok && !FinishMainSceneCamera(&camera);  // No second consumer.
    for (int fault = 0; fault < 10; ++fault) {
        begin(); world();
        switch (fault) {
        case 0: test_camera_view[12] += 1; break;
        case 1: test_camera_projection[0] += 0.1F; break;
        case 2: ++test_camera_viewport[2]; break;
        case 3: test_camera_depth = 2; break;
        case 4: ++test_context; break;
        case 5: g_scene_frame.main_scene_invalidated = true; break;
        case 6: ObserveMainSceneClear(&g_scene_frame); break;
        case 7: g_scene_frame.boundary_mapping_verified = false; break;
        case 8: g_immediate_primitive_open = true; break;
        case 9: g_get_floatv = nullptr; break;
        }
        ok = !finish() && ok;
        if (fault == 4) --test_context;
        g_immediate_primitive_open = false;
        g_get_floatv = reinterpret_cast<PVOID>(&FakeCameraFloats);
    }
    begin(); ok = !finish() && ok;  // Empty scene cannot supply a camera.
    begin(); test_camera_depth = 2; BeginMainSceneCamera();
    test_camera_depth = 1; world(); ok = !finish() && ok;
    begin(); test_camera_view[0] = 2; BeginMainSceneCamera();
    test_camera_view = view; world(); ok = !finish() && ok;
    begin(); g_scene_frame = {}; world(); ok = !finish() && ok;  // Frame expired.
    g_scene_frame = {}; g_main_scene_context = nullptr;
    g_main_scene_camera_valid = false;
    g_get_floatv = nullptr; g_get_integerv = nullptr; g_get_current_context = nullptr;
    test_camera_view = view; test_camera_depth = 1;
    return ok;
}

void APIENTRY FakeRestoreAttributes() { test_alpha_enabled = true; }
void APIENTRY FakeExecuteList(unsigned int) { test_alpha_enabled = true; }
void APIENTRY FakeFinishList() {}

void CaptureTestTriangle() {
    using namespace wonderbane::extension;
    CaptureDisplayListBegin(0x0004U);
    CaptureDisplayListVertex(0.0F, 0.0F, 0.0F);
    CaptureDisplayListVertex(1.0F, 0.0F, 0.0F);
    CaptureDisplayListVertex(0.0F, 1.0F, 0.0F);
    CloseCapturedPrimitive();
}

bool CheckDisplayListSourceOwnership() {
    using namespace wonderbane::extension;
    g_get_current_context = reinterpret_cast<PVOID>(&FakeCurrentContext);
    BeginDisplayListCapture(101U);
    CaptureTestTriangle();
    EndDisplayListCapture();
    bool ok = IsDisplayListSourceStateStable(101U);
    ++test_context;
    ok = ok && !IsDisplayListSourceStateStable(101U);
    --test_context;
    BeginDisplayListCapture(101U);  // Redefinition must retire old provenance.
    CaptureTestTriangle();
    ListStateBindTexture(0x0DE1U, 22U);
    ListStateBindTexture(0x0DE1U, 1U);  // Even restored state remains unsafe.
    EndDisplayListCapture();
    ok = ok && !IsDisplayListSourceStateStable(101U);

    BeginDisplayListCapture(102U);
    CaptureTestTriangle();
    ListStateAlphaFunc(0x0204U, 0.5F);
    EndDisplayListCapture();
    ok = ok && !IsDisplayListSourceStateStable(102U);
    BeginDisplayListCapture(103U);
    CaptureTestTriangle();
    ListStatePushMatrix();
    ListStateTranslatef(1.0F, 0.0F, 0.0F);
    ListStatePopMatrix();
    EndDisplayListCapture();
    ok = ok && !IsDisplayListSourceStateStable(103U);
    BeginDisplayListCapture(104U);
    CaptureTestTriangle();
    g_active_display_list_capture.nested_lists.push_back(101U);
    EndDisplayListCapture();
    ok = ok && !IsDisplayListSourceStateStable(104U);
    ok = ok && !IsDisplayListSourceStateStable(105U);
    const auto rejects_material_change = [](const auto& change) {
        BeginDisplayListCapture(105U);
        CaptureTestTriangle();
        change();
        EndDisplayListCapture();
        return !IsDisplayListSourceStateStable(105U);
    };
    ok = ok && rejects_material_change([] { ListStateMaterialfv(0x0408U, 0x1201U, nullptr); });
    ok = ok && rejects_material_change([] { ListStateTexGeni(0x2000U, 0x2500U, 0x2400); });
    ok = ok && rejects_material_change([] { ListStateDepthFunc(0x0203U); });
    ok = ok && rejects_material_change([] { ListStateRecti(0, 0, 1, 1); });

    CapturedEdgeMap edges{};
    CapturedVertex first{{0.0F, 0.0F, 0.0F}, {0.0F, 0.0F}, true};
    CapturedVertex second{{1.0F, 0.0F, 0.0F}, {1.0F, 0.0F}, true};
    AddFaceEdge(&edges, first, second, {0.0F, 0.0F, 1.0F});
    ok = ok && edges.begin()->second.edge.has_tex_coords;
    first.tex_coord = {0.5F, 0.5F};
    AddFaceEdge(&edges, first, second, {0.0F, 1.0F, 0.0F});
    ok = ok && !edges.begin()->second.edge.has_tex_coords;
    ClearDisplayListBounds();
    g_get_current_context = nullptr;
    return ok;
}

bool CheckStateRestoreRegressions() {
    using namespace wonderbane::extension;
    g_get_booleanv = reinterpret_cast<PVOID>(&FakeStateQuery);
    g_get_current_context = reinterpret_cast<PVOID>(&FakeCurrentContext);
    g_original_pop_attrib = reinterpret_cast<PVOID>(&FakeRestoreAttributes);
    g_original_call_list = reinterpret_cast<PVOID>(&FakeExecuteList);
    g_original_end_list = reinterpret_cast<PVOID>(&FakeFinishList);
    g_fixed_function_state = {};
    g_fixed_function_context = nullptr;
    test_alpha_enabled = false;
    test_query_count = 0U;
    bool ok = RefreshFixedFunctionState() && !g_fixed_function_state.alpha_test_enabled;
    const auto initial_queries = test_query_count;
    ok = ok && RefreshFixedFunctionState() && test_query_count == initial_queries;

    StrongPopAttrib();
    ok = ok && !g_fixed_function_state.valid && RefreshFixedFunctionState()
        && g_fixed_function_state.alpha_test_enabled;
    test_alpha_enabled = false;
    InvalidateFixedFunctionState(&g_fixed_function_state);
    ok = ok && RefreshFixedFunctionState() && !g_fixed_function_state.alpha_test_enabled;
    StrongCallList(42U);  // Missing outline API deliberately takes original draw path.
    ok = ok && !g_fixed_function_state.valid && RefreshFixedFunctionState()
        && g_fixed_function_state.alpha_test_enabled;

    BeginDisplayListCapture(43U);
    test_alpha_enabled = false;  // A compile-and-execute list changed real state.
    const auto before_compile_query = test_query_count;
    ok = ok && !AreNativeDrawQueriesSafe() && !RefreshFixedFunctionState() && test_query_count == before_compile_query;
    StrongEndList();
    ok = ok && !g_fixed_function_state.valid && RefreshFixedFunctionState()
        && !g_fixed_function_state.alpha_test_enabled;

    g_immediate_primitive_open = true;
    const auto before_immediate_query = test_query_count;
    StrongCallList(44U);
    ok = ok && !AreNativeDrawQueriesSafe() && !RefreshFixedFunctionState() && test_query_count == before_immediate_query;
    g_immediate_primitive_open = false;
    ok = ok && AreNativeDrawQueriesSafe() && RefreshFixedFunctionState() && g_fixed_function_state.alpha_test_enabled;

    ++test_context;
    test_alpha_enabled = false;
    ok = ok && RefreshFixedFunctionState() && !g_fixed_function_state.alpha_test_enabled;
    g_get_booleanv = nullptr;
    g_get_current_context = nullptr;
    g_original_pop_attrib = nullptr;
    g_original_call_list = nullptr;
    g_original_end_list = nullptr;
    g_fixed_function_state = {};
    g_fixed_function_context = nullptr;
    return ok;
}

bool CheckOptionalImportPlans() {
    using namespace wonderbane::extension;
    ImportHookPlan plan{"glPopAttrib", reinterpret_cast<PVOID>(2U),
        reinterpret_cast<PVOID>(1U), nullptr, nullptr, nullptr, false};
    bool ok = ValidateResolvedImportHookPlan(plan) == ERROR_SUCCESS;
    plan.required = true;
    ok = ok && ValidateResolvedImportHookPlan(plan) == ERROR_PROC_NOT_FOUND;
    plan.required = false;
    std::uint32_t slot = 1U;
    plan.slot = &slot;
    ok = ok && ValidateResolvedImportHookPlan(plan) == ERROR_SUCCESS;
    slot = 3U;
    ok = ok && ValidateResolvedImportHookPlan(plan) == ERROR_INVALID_ADDRESS;
    plan.original = nullptr;
    ok = ok && ValidateResolvedImportHookPlan(plan) == ERROR_PROC_NOT_FOUND;

    // The extension still needs its own glPopAttrib helper when no client IAT
    // slot exists. That helper must not look like a partially installed hook.
    g_pop_attrib = reinterpret_cast<PVOID>(&FakeRestoreAttributes);
    const auto retained_original = g_original_pop_attrib;
    StopStrongCelShading();
    ok = ok && g_pop_attrib == nullptr && g_original_pop_attrib == retained_original
        && g_pop_attrib_slot == nullptr;
    return ok;
}

}  // namespace

HANDLE render_entered = nullptr;
HANDLE render_release = nullptr;
BOOL WINAPI HeldSwap(HDC) {
    SetEvent(render_entered);
    WaitForSingleObject(render_release, INFINITE);
    return TRUE;
}
bool CheckInFlightCleanup() {
    using namespace wonderbane::extension;
    render_entered = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    render_release = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    g_original_swap_buffers = reinterpret_cast<PVOID>(&HeldSwap);
    std::uint32_t imported = static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(&StrongSwapBuffers));
    g_swap_buffers_slot = &imported;
    std::thread callback([] { StrongSwapBuffers(nullptr); });
    WaitForSingleObject(render_entered, INFINITE);
    if (TryAcquireSRWLockExclusive(&g_render_lifetime)) { std::abort(); }
    HANDLE stop_entered = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    std::thread cleanup([&] { SetEvent(stop_entered); StopStrongCelShading(); });
    WaitForSingleObject(stop_entered, INFINITE);
    SetEvent(render_release);
    callback.join(); cleanup.join();
    const bool ok = !g_swap_buffers_slot
        && imported == static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(&HeldSwap))
        && StrongSwapBuffers(nullptr) == TRUE;
    StopStrongCelShading();
    CloseHandle(stop_entered); CloseHandle(render_entered); CloseHandle(render_release);
    return ok;
}

int wmain() {
    if (!CheckInFlightCleanup()) { return Fail(L"in-flight renderer cleanup/call-through"); }
    if (!CheckReviewedSceneCamera()) {
        return Fail(L"reviewed scene camera ownership and nested world transforms");
    }
    if (!CheckOptionalImportPlans()) {
        return Fail(L"optional import validation and helper-only rollback");
    }
    if (!CheckStateRestoreRegressions()) {
        return Fail(L"restored/display-list/context state coherence");
    }
    if (!CheckDisplayListSourceOwnership()) {
        return Fail(L"display-list and cutout UV source ownership");
    }
    std::vector<std::uint8_t> image = Fixture();
    for (std::size_t index = 0U; index < kImportNames.size(); ++index) {
        std::uint32_t* const slot = wonderbane::extension::FindImportAddressSlot(
            image.data(),
            image.size(),
            "opengl32.DLL",
            kImportNames[index]
        );
        if (slot == nullptr || *slot != kImportAddresses[index]) {
            return Fail(L"exact import resolution");
        }
    }
    if (wonderbane::extension::FindImportAddressSlot(
            image.data(),
            image.size(),
            "OPENGL32.dll",
            "glColor4f"
        ) != nullptr) {
        return Fail(L"missing symbol rejection");
    }
    auto* const names = reinterpret_cast<IMAGE_THUNK_DATA32*>(image.data() + kNamesRva);
    auto* const addresses = reinterpret_cast<IMAGE_THUNK_DATA32*>(
        image.data() + kAddressesRva
    );
    names[kImportNames.size()].u1.AddressOfData = kImportNameRvas[0];
    addresses[kImportNames.size()].u1.Function = 0xCDEF0123U;
    if (wonderbane::extension::FindImportAddressSlot(
            image.data(),
            image.size(),
            "OPENGL32.dll",
            "glShadeModel"
        ) != nullptr) {
        return Fail(L"duplicate symbol rejection");
    }
    image = Fixture();
    auto* const nt = reinterpret_cast<IMAGE_NT_HEADERS32*>(image.data() + kNtRva);
    nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].Size = (
        sizeof(IMAGE_IMPORT_DESCRIPTOR)
    );
    if (wonderbane::extension::FindImportAddressSlot(
            image.data(),
            image.size(),
            "OPENGL32.dll",
            "glShadeModel"
        ) != nullptr) {
        return Fail(L"unterminated descriptor rejection");
    }
    image = Fixture();
    auto* const imports = reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>(
        image.data() + kImportRva
    );
    imports[0].FirstThunk = static_cast<std::uint32_t>(image.size());
    if (wonderbane::extension::FindImportAddressSlot(
            image.data(),
            image.size(),
            "OPENGL32.dll",
            "glShadeModel"
        ) != nullptr) {
        return Fail(L"out-of-range thunk rejection");
    }

    constexpr std::array<float, 16U> perspective{
        1.0F, 0.0F, 0.0F, 0.0F,
        0.0F, 1.0F, 0.0F, 0.0F,
        0.0F, 0.0F, -1.0F, -1.0F,
        0.0F, 0.0F, -0.2F, 0.0F,
    };
    constexpr std::array<float, 16U> orthographic{
        1.0F, 0.0F, 0.0F, 0.0F,
        0.0F, 1.0F, 0.0F, 0.0F,
        0.0F, 0.0F, -1.0F, 0.0F,
        0.0F, 0.0F, 0.0F, 1.0F,
    };
    if (!wonderbane::extension::IsPerspectiveProjectionMatrix(
            perspective.data(),
            perspective.size()
        )) {
        return Fail(L"perspective projection acceptance");
    }
    if (wonderbane::extension::IsPerspectiveProjectionMatrix(
            orthographic.data(),
            orthographic.size()
        )) {
        return Fail(L"orthographic projection rejection");
    }
    constexpr std::array<float, 16U> local_model_view{
        1.0F, 0.0F, 0.0F, 0.0F,
        0.0F, 1.0F, 0.0F, 0.0F,
        0.0F, 0.0F, 1.0F, 0.0F,
        128.0F, -64.0F, -512.0F, 1.0F,
    };
    std::array<float, 16U> distant_model_view = local_model_view;
    distant_model_view[12] = 90000.0F;
    std::array<float, 16U> non_affine_model_view = local_model_view;
    non_affine_model_view[15] = 0.0F;
    if (
        !wonderbane::extension::IsLocalOutlineModelViewMatrix(
            local_model_view.data(),
            local_model_view.size()
        )
        || wonderbane::extension::IsLocalOutlineModelViewMatrix(
            distant_model_view.data(),
            distant_model_view.size()
        )
        || wonderbane::extension::IsLocalOutlineModelViewMatrix(
            non_affine_model_view.data(),
            non_affine_model_view.size()
        )
    ) {
        return Fail(L"local model-view outline policy");
    }
    constexpr wonderbane::extension::OutlineBounds glyph_bounds{
        {0.0F, 0.0F, 0.0F},
        {16.0F, 24.0F, 0.0F},
    };
    constexpr wonderbane::extension::OutlineBounds volume_bounds{
        {0.0F, 0.0F, 0.0F},
        {16.0F, 24.0F, 8.0F},
    };
    if (
        !wonderbane::extension::IsPlanarOverlayGeometry(
            &glyph_bounds, 4U, 1U
        )
        || !wonderbane::extension::IsPlanarOverlayGeometry(
            &glyph_bounds, 6U, 1U
        )
        || wonderbane::extension::IsPlanarOverlayGeometry(
            &volume_bounds, 4U, 1U
        )
        || wonderbane::extension::IsPlanarOverlayGeometry(
            &glyph_bounds, 8193U, 1U
        )
    ) {
        return Fail(L"planar overlay exclusion policy");
    }
    if (
        !wonderbane::extension::IsPlanarOverlayDrawState(
            true, true, true, false, false, false
        )
        || !wonderbane::extension::IsPlanarOverlayDrawState(
            true, true, false, true, false, false
        )
        || wonderbane::extension::IsPlanarOverlayDrawState(
            true, true, true, false, true, false
        )
        || wonderbane::extension::IsPlanarOverlayDrawState(
            true, true, true, false, false, true
        )
        || wonderbane::extension::IsPlanarOverlayDrawState(
            false, true, true, false, false, false
        )
    ) {
        return Fail(L"planar overlay render-state policy");
    }
    if (
        !wonderbane::extension::IsFeatureAccentDrawState(
            true, true, false, true
        )
        || !wonderbane::extension::IsFeatureAccentDrawState(
            true, false, false, true
        )
        || wonderbane::extension::IsFeatureAccentDrawState(
            true, false, true, true
        )
        || wonderbane::extension::IsFeatureAccentDrawState(
            true, true, true, true
        )
        || wonderbane::extension::IsFeatureAccentDrawState(
            true, false, false, false
        )
        || wonderbane::extension::IsFeatureAccentDrawState(
            false, true, false, true
        )
    ) {
        return Fail(L"layered equipment feature-accent policy");
    }
    constexpr std::array<int, 4U> viewport{0, 0, 1200, 800};
    std::array<float, 16U> near_model_view = local_model_view;
    near_model_view[14] = -50.0F;
    std::array<float, 16U> middle_model_view = local_model_view;
    middle_model_view[14] = -100.0F;
    std::array<float, 16U> far_model_view = local_model_view;
    far_model_view[14] = -400.0F;
    const float near_width = wonderbane::extension::PerspectiveOutlineLineWidth(
        perspective.data(), perspective.size(),
        near_model_view.data(), near_model_view.size(),
        viewport.data(), viewport.size()
    );
    const float middle_width = wonderbane::extension::PerspectiveOutlineLineWidth(
        perspective.data(), perspective.size(),
        middle_model_view.data(), middle_model_view.size(),
        viewport.data(), viewport.size()
    );
    const float far_width = wonderbane::extension::PerspectiveOutlineLineWidth(
        perspective.data(), perspective.size(),
        far_model_view.data(), far_model_view.size(),
        viewport.data(), viewport.size()
    );
    if (
        std::fabs(near_width - 1.35F) > 0.001F
        || std::fabs(middle_width - 1.35F) > 0.001F
        || far_width != 0.0F
    ) {
        return Fail(L"perspective outline width policy");
    }
    if (
        std::fabs(wonderbane::extension::InteriorContourLineWidth(4.0F) - 1.0F) > 0.001F
        || std::fabs(wonderbane::extension::InteriorContourLineWidth(1.35F) - 1.0F) > 0.001F
        || wonderbane::extension::InteriorContourLineWidth(0.9F) != 0.0F
        || wonderbane::extension::InteriorContourLineWidth(NAN) != 0.0F
    ) {
        return Fail(L"bounded interior contour width policy");
    }
    constexpr float coplanar_triangles[]{
        0.0F, 0.0F, 0.0F, 1.0F, 0.0F, 0.0F, 1.0F, 1.0F, 0.0F,
        0.0F, 0.0F, 0.0F, 1.0F, 1.0F, 0.0F, 0.0F, 1.0F, 0.0F,
    };
    constexpr float creased_triangles[]{
        0.0F, 0.0F, 0.0F, 1.0F, 0.0F, 0.0F, 1.0F, 1.0F, 0.0F,
        0.0F, 0.0F, 0.0F, 1.0F, 1.0F, 0.0F, 0.0F, 1.0F, 1.0F,
    };
    if (
        wonderbane::extension::TriangleFeatureEdgeCount(
            coplanar_triangles, std::size(coplanar_triangles)
        ) != 4U
        || wonderbane::extension::TriangleFeatureEdgeCount(
            creased_triangles, std::size(creased_triangles)
        ) != 5U
    ) {
        return Fail(L"feature-edge crease selection");
    }
    wonderbane::extension::OutlineBounds expanded{{90.0F, -5.0F, -2.0F}, {110.0F, 5.0F, 2.0F}};
    if (
        !wonderbane::extension::ExpandOutlineBounds(&expanded, 112.0F, 6.0F, 3.0F)
        || expanded.maximum[0] != 112.0F
        || expanded.maximum[1] != 6.0F
        || expanded.maximum[2] != 3.0F
    ) {
        return Fail(L"display-list bounds expansion");
    }
    constexpr wonderbane::extension::OutlineBounds centered_bounds{
        {90.0F, -5.0F, -2.0F},
        {110.0F, 5.0F, 2.0F},
    };
    wonderbane::extension::OutlineHullTransform hull{};
    if (
        !wonderbane::extension::CenteredOutlineHullTransform(
            &centered_bounds,
            0.5F,
            &hull
        )
        || std::fabs(hull.center[0] - 100.0F) > 0.001F
        || std::fabs(hull.center[1]) > 0.001F
        || std::fabs(hull.center[2]) > 0.001F
        || std::fabs(hull.scale[0] - 1.05F) > 0.001F
        || std::fabs(hull.scale[1] - 1.10F) > 0.001F
        || std::fabs(hull.scale[2] - 1.25F) > 0.001F
        || std::fabs(hull.half_extent[0] - 10.0F) > 0.001F
        || std::fabs(hull.half_extent[1] - 5.0F) > 0.001F
        || std::fabs(hull.half_extent[2] - 2.0F) > 0.001F
    ) {
        return Fail(L"centered outline hull transform");
    }
    constexpr wonderbane::extension::OutlineBounds tiny_bounds{
        {-0.1F, -0.1F, -0.1F},
        {0.1F, 0.1F, 0.1F},
    };
    if (
        !wonderbane::extension::CenteredOutlineHullTransform(
            &tiny_bounds,
            0.5F,
            &hull
        )
        || std::fabs(hull.scale[0] - 1.25F) > 0.001F
        || std::fabs(hull.scale[1] - 1.25F) > 0.001F
        || std::fabs(hull.scale[2] - 1.25F) > 0.001F
    ) {
        return Fail(L"bounded outline hull scale");
    }
    if (
        !wonderbane::extension::IsOutlinePrimitive(0x0004U, 36)
        || wonderbane::extension::IsOutlinePrimitive(0x0001U, 36)
        || !wonderbane::extension::IsOutlinePrimitive(0x0004U, 8193)
        || wonderbane::extension::IsOutlinePrimitive(0x0004U, 65537)
    ) {
        return Fail(L"bounded outline primitive policy");
    }
    return 0;
}
