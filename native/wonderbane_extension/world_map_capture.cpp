#include "world_map_capture.h"
#include "world_map_projection.h"

#include <Windows.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iterator>

namespace wonderbane::extension {
namespace {

constexpr std::uintptr_t kReviewedImageBase = 0x00400000U;
constexpr std::uint32_t kReviewedImageSize = 0x01766000U;
constexpr std::uint32_t kReviewedEntryPointRva = 0x008D8C4AU;
constexpr std::uint16_t kReviewedSectionCount = 6U;
constexpr std::uint32_t kObjectVtableRva = 0x01170BC8U;
constexpr std::uint32_t kControlVtableRva = 0x01170B8CU;
constexpr std::uint32_t kWorldDefinitionPointerRva = 0x016A7C3CU;
constexpr std::array<std::uint32_t, 4> kObjectVtablePrefix{
    0x0042554AU,
    0x00409115U,
    0x00417EA4U,
    0x0041E9D4U,
};
constexpr std::array<std::uint32_t, 4> kControlVtablePrefix{
    0x0041D57FU,
    0x00425E3CU,
    0x00403E45U,
    0x0042122EU,
};
constexpr std::uintptr_t kMinimumUserAddress = 0x00010000U;
constexpr std::uintptr_t kMaximumUserAddress = 0x7FFEFFFFU;
constexpr std::size_t kScanChunkSize = 64U * 1024U;
constexpr std::size_t kMaximumCandidates = 16U;
constexpr std::size_t kWorldMapObjectSize = 1048U;
constexpr std::size_t kRectangleOffset = 8U;
constexpr std::size_t kHiddenOffset = 208U;
constexpr std::size_t kLeftPaddingOffset = 820U;
constexpr std::size_t kTopPaddingOffset = 824U;
constexpr std::size_t kRightPaddingOffset = 828U;
constexpr std::size_t kBottomPaddingOffset = 832U;
constexpr std::size_t kZoomOffset = 892U;
constexpr std::size_t kTexturePointerOffset = 1024U;
constexpr std::size_t kHorizontalPanOffset = 1040U;
constexpr std::size_t kVerticalPanOffset = 1044U;
constexpr std::size_t kWorldDefinitionSize = 24U;
constexpr std::size_t kWorldLengthTilesOffset = 16U;
constexpr std::size_t kWorldWidthTilesOffset = 20U;
constexpr double kWorldCoordinateScale = 256.0;
constexpr std::int32_t kMinimumMapPixels = 128;
constexpr std::int32_t kMaximumMapPixels = 8192;
constexpr float kMinimumZoom = 0.125F;
constexpr float kMaximumZoom = 16.0F;
constexpr std::int32_t kMaximumWorldTiles = 4096;
constexpr ULONGLONG kObservationIntervalMilliseconds = 50U;
constexpr ULONGLONG kMaximumObservationAgeMilliseconds = 250U;
constexpr ULONGLONG kObjectScanIntervalMilliseconds = 1000U;
constexpr ULONGLONG kPendingButtonUpMilliseconds = 2000U;
constexpr UINT_PTR kObservationTimerId = 1U;
constexpr UINT kObservationTimerMilliseconds = 50U;
constexpr DWORD kCaptureStartupTimeoutMilliseconds = 5000U;

struct WorldMapSnapshot {
    bool valid;
    bool open;
    std::int32_t left;
    std::int32_t top;
    std::int32_t right;
    std::int32_t bottom;
    std::int32_t left_padding;
    std::int32_t top_padding;
    std::int32_t right_padding;
    std::int32_t bottom_padding;
    float zoom;
    std::int32_t horizontal_pan;
    std::int32_t vertical_pan;
    double world_length;
    double world_width;
    std::uint64_t snapshot_hash;
    HWND window;
    POINT client_origin;
    ULONGLONG observed_at;
};

struct PendingButtonUp {
    bool active;
    std::uint32_t button;
    HWND window;
    ULONGLONG expires_at;
};

HANDLE g_capture_thread = nullptr;
HANDLE g_capture_ready = nullptr;
volatile LONG g_capture_start_result = ERROR_INVALID_STATE;
DWORD g_capture_thread_id = 0U;
HMODULE g_extension_module = nullptr;
ProcessIdentity g_process_identity{};
HHOOK g_mouse_hook = nullptr;
std::uintptr_t g_world_map_object = 0U;
ULONGLONG g_last_object_scan = 0U;
WorldMapSnapshot g_snapshot{};
PendingButtonUp g_pending_button_up{};

template <typename Value>
bool CopyFromBytes(
    const std::uint8_t* const source,
    const std::size_t source_size,
    const std::size_t offset,
    Value* const destination
) noexcept {
    if (
        source == nullptr
        || destination == nullptr
        || offset > source_size
        || sizeof(Value) > source_size - offset
    ) {
        return false;
    }
    std::memcpy(destination, source + offset, sizeof(Value));
    return true;
}

bool ReadMemory(
    const std::uintptr_t address,
    void* const destination,
    const std::size_t size
) noexcept {
    if (
        destination == nullptr
        || size == 0U
        || address < kMinimumUserAddress
        || address > kMaximumUserAddress
        || size - 1U > kMaximumUserAddress - address
    ) {
        return false;
    }
    SIZE_T bytes_read = 0U;
    return ReadProcessMemory(
               GetCurrentProcess(),
               reinterpret_cast<const void*>(address),
               destination,
               size,
               &bytes_read
           ) != FALSE
        && bytes_read == size;
}

bool ReadReviewedVtables() noexcept {
    std::array<std::uint32_t, 4> object_prefix{};
    std::array<std::uint32_t, 4> control_prefix{};
    return ReadMemory(
               kReviewedImageBase + kObjectVtableRva,
               object_prefix.data(),
               sizeof(object_prefix)
           )
        && ReadMemory(
            kReviewedImageBase + kControlVtableRva,
            control_prefix.data(),
            sizeof(control_prefix)
        )
        && object_prefix == kObjectVtablePrefix
        && control_prefix == kControlVtablePrefix;
}

bool ReadWorldDimensions(
    double* const world_length,
    double* const world_width,
    std::uint64_t* const snapshot_hash
) noexcept {
    std::uint32_t world_definition = 0U;
    if (!ReadMemory(
            kReviewedImageBase + kWorldDefinitionPointerRva,
            &world_definition,
            sizeof(world_definition)
        )) {
        return false;
    }
    if (
        world_definition < kMinimumUserAddress
        || world_definition > kMaximumUserAddress - kWorldDefinitionSize
        || world_definition % alignof(std::uint32_t) != 0U
    ) {
        return false;
    }
    std::array<std::uint8_t, kWorldDefinitionSize> first{};
    std::array<std::uint8_t, kWorldDefinitionSize> second{};
    if (
        !ReadMemory(world_definition, first.data(), first.size())
        || !ReadMemory(world_definition, second.data(), second.size())
        || first != second
    ) {
        return false;
    }
    std::int32_t length_tiles = 0;
    std::int32_t width_tiles = 0;
    if (
        !CopyFromBytes(
            first.data(),
            first.size(),
            kWorldLengthTilesOffset,
            &length_tiles
        )
        || !CopyFromBytes(
            first.data(),
            first.size(),
            kWorldWidthTilesOffset,
            &width_tiles
        )
        || length_tiles <= 0
        || width_tiles <= 0
        || length_tiles > kMaximumWorldTiles
        || width_tiles > kMaximumWorldTiles
    ) {
        return false;
    }
    *world_length = static_cast<double>(length_tiles) * kWorldCoordinateScale;
    *world_width = static_cast<double>(width_tiles) * kWorldCoordinateScale;
    std::uint64_t hash = 14695981039346656037ULL;
    const auto mix = [&hash](const std::uint8_t value) noexcept {
        hash ^= value;
        hash *= 1099511628211ULL;
    };
    for (const std::uint8_t value : first) {
        mix(value);
    }
    for (std::size_t index = 0U; index < sizeof(world_definition); ++index) {
        mix(static_cast<std::uint8_t>(world_definition >> (index * 8U)));
    }
    *snapshot_hash = hash;
    return true;
}

bool ReadWorldMapSnapshot(
    const std::uintptr_t address,
    WorldMapSnapshot* const snapshot
) noexcept {
    if (snapshot == nullptr) {
        return false;
    }
    std::array<std::uint8_t, kWorldMapObjectSize> payload{};
    std::array<std::uint8_t, kWorldMapObjectSize> confirmation{};
    if (
        !ReadMemory(address, payload.data(), payload.size())
        || !ReadMemory(address, confirmation.data(), confirmation.size())
        || payload != confirmation
    ) {
        return false;
    }
    std::uint32_t object_vtable = 0U;
    std::uint32_t control_vtable = 0U;
    std::int32_t left = 0;
    std::int32_t top = 0;
    std::int32_t right = 0;
    std::int32_t bottom = 0;
    std::int32_t left_padding = 0;
    std::int32_t top_padding = 0;
    std::int32_t right_padding = 0;
    std::int32_t bottom_padding = 0;
    float zoom = 0.0F;
    std::uint32_t texture_pointer = 0U;
    std::int32_t horizontal_pan = 0;
    std::int32_t vertical_pan = 0;
    if (
        !CopyFromBytes(payload.data(), payload.size(), 0U, &object_vtable)
        || !CopyFromBytes(payload.data(), payload.size(), 4U, &control_vtable)
        || !CopyFromBytes(payload.data(), payload.size(), kRectangleOffset, &left)
        || !CopyFromBytes(payload.data(), payload.size(), kRectangleOffset + 4U, &top)
        || !CopyFromBytes(payload.data(), payload.size(), kRectangleOffset + 8U, &right)
        || !CopyFromBytes(payload.data(), payload.size(), kRectangleOffset + 12U, &bottom)
        || !CopyFromBytes(
            payload.data(),
            payload.size(),
            kLeftPaddingOffset,
            &left_padding
        )
        || !CopyFromBytes(
            payload.data(),
            payload.size(),
            kTopPaddingOffset,
            &top_padding
        )
        || !CopyFromBytes(
            payload.data(),
            payload.size(),
            kRightPaddingOffset,
            &right_padding
        )
        || !CopyFromBytes(
            payload.data(),
            payload.size(),
            kBottomPaddingOffset,
            &bottom_padding
        )
        || !CopyFromBytes(payload.data(), payload.size(), kZoomOffset, &zoom)
        || !CopyFromBytes(
            payload.data(),
            payload.size(),
            kTexturePointerOffset,
            &texture_pointer
        )
        || !CopyFromBytes(
            payload.data(),
            payload.size(),
            kHorizontalPanOffset,
            &horizontal_pan
        )
        || !CopyFromBytes(
            payload.data(),
            payload.size(),
            kVerticalPanOffset,
            &vertical_pan
        )
    ) {
        return false;
    }
    const std::int32_t width = right - left;
    const std::int32_t height = bottom - top;
    const std::uint8_t hidden = payload[kHiddenOffset];
    const std::int32_t maximum_pan = kMaximumMapPixels * 16 * 4;
    if (
        object_vtable != kReviewedImageBase + kObjectVtableRva
        || control_vtable != kReviewedImageBase + kControlVtableRva
        || width < kMinimumMapPixels
        || width > kMaximumMapPixels
        || height < kMinimumMapPixels
        || height > kMaximumMapPixels
        || (hidden != 0U && hidden != 1U)
        || left_padding < 0
        || top_padding < 0
        || right_padding < 0
        || bottom_padding < 0
        || left_padding + right_padding >= width
        || top_padding + bottom_padding >= height
        || !std::isfinite(zoom)
        || zoom < kMinimumZoom
        || zoom > kMaximumZoom
        || (
            texture_pointer != 0U
            && (
                texture_pointer < kMinimumUserAddress
                || texture_pointer > kMaximumUserAddress
                || texture_pointer % alignof(std::uint32_t) != 0U
            )
        )
        || std::abs(static_cast<std::int64_t>(horizontal_pan)) > maximum_pan
        || std::abs(static_cast<std::int64_t>(vertical_pan)) > maximum_pan
    ) {
        return false;
    }
    double world_length = 0.0;
    double world_width = 0.0;
    std::uint64_t snapshot_hash = 0U;
    if (!ReadWorldDimensions(&world_length, &world_width, &snapshot_hash)) {
        return false;
    }
    for (const std::uint8_t value : payload) {
        snapshot_hash ^= value;
        snapshot_hash *= 1099511628211ULL;
    }
    snapshot->valid = true;
    snapshot->open = hidden == 0U && texture_pointer != 0U;
    snapshot->left = left;
    snapshot->top = top;
    snapshot->right = right;
    snapshot->bottom = bottom;
    snapshot->left_padding = left_padding;
    snapshot->top_padding = top_padding;
    snapshot->right_padding = right_padding;
    snapshot->bottom_padding = bottom_padding;
    snapshot->zoom = zoom;
    snapshot->horizontal_pan = horizontal_pan;
    snapshot->vertical_pan = vertical_pan;
    snapshot->world_length = world_length;
    snapshot->world_width = world_width;
    snapshot->snapshot_hash = snapshot_hash;
    return true;
}

bool DiscoverWorldMapObject(std::uintptr_t* const unique_address) noexcept {
    if (unique_address == nullptr) {
        return false;
    }
    auto* const buffer = static_cast<std::uint8_t*>(VirtualAlloc(
        nullptr,
        kScanChunkSize,
        MEM_COMMIT | MEM_RESERVE,
        PAGE_READWRITE
    ));
    if (buffer == nullptr) {
        return false;
    }
    const std::uint32_t expected_vtable = static_cast<std::uint32_t>(
        kReviewedImageBase + kObjectVtableRva
    );
    std::array<std::uintptr_t, kMaximumCandidates> candidates{};
    std::size_t candidate_count = 0U;
    std::uintptr_t address = kMinimumUserAddress;
    while (address <= kMaximumUserAddress) {
        MEMORY_BASIC_INFORMATION region{};
        if (VirtualQuery(
                reinterpret_cast<const void*>(address),
                &region,
                sizeof(region)
            ) == 0U) {
            break;
        }
        const auto region_base = reinterpret_cast<std::uintptr_t>(region.BaseAddress);
        const std::uintptr_t maximum_end = kMaximumUserAddress + 1U;
        const std::uintptr_t region_size = static_cast<std::uintptr_t>(region.RegionSize);
        const std::uintptr_t region_end = (
            region_base >= maximum_end || region_size > maximum_end - region_base
        ) ? maximum_end : region_base + region_size;
        if (
            region.State == MEM_COMMIT
            && region.Type == MEM_PRIVATE
            && region.Protect == PAGE_READWRITE
        ) {
            for (
                std::uintptr_t chunk = region_base;
                chunk < region_end;
                chunk += kScanChunkSize
            ) {
                const std::size_t chunk_size = static_cast<std::size_t>(
                    std::min<std::uintptr_t>(kScanChunkSize, region_end - chunk)
                );
                SIZE_T bytes_read = 0U;
                if (
                    ReadProcessMemory(
                        GetCurrentProcess(),
                        reinterpret_cast<const void*>(chunk),
                        buffer,
                        chunk_size,
                        &bytes_read
                    ) == FALSE
                    || bytes_read != chunk_size
                ) {
                    continue;
                }
                const std::size_t first_offset = static_cast<std::size_t>(
                    (alignof(std::uint32_t) - chunk % alignof(std::uint32_t))
                    % alignof(std::uint32_t)
                );
                for (
                    std::size_t offset = first_offset;
                    offset + sizeof(expected_vtable) <= chunk_size;
                    offset += alignof(std::uint32_t)
                ) {
                    std::uint32_t candidate_vtable = 0U;
                    std::memcpy(
                        &candidate_vtable,
                        buffer + offset,
                        sizeof(candidate_vtable)
                    );
                    if (candidate_vtable != expected_vtable) {
                        continue;
                    }
                    WorldMapSnapshot candidate{};
                    const std::uintptr_t candidate_address = chunk + offset;
                    if (!ReadWorldMapSnapshot(candidate_address, &candidate)) {
                        continue;
                    }
                    if (candidate_count >= candidates.size()) {
                        VirtualFree(buffer, 0U, MEM_RELEASE);
                        return false;
                    }
                    candidates[candidate_count++] = candidate_address;
                }
            }
        }
        if (region_end <= address) {
            break;
        }
        address = region_end;
    }
    VirtualFree(buffer, 0U, MEM_RELEASE);
    if (candidate_count != 1U) {
        return false;
    }
    *unique_address = candidates[0];
    return true;
}

bool ForegroundClient(HWND* const window, POINT* const client_origin) noexcept {
    if (window == nullptr || client_origin == nullptr) {
        return false;
    }
    const HWND foreground = GetForegroundWindow();
    if (foreground == nullptr) {
        return false;
    }
    DWORD process_id = 0U;
    if (
        GetWindowThreadProcessId(foreground, &process_id) == 0U
        || process_id != g_process_identity.process_id
    ) {
        return false;
    }
    POINT origin{0, 0};
    if (ClientToScreen(foreground, &origin) == FALSE) {
        return false;
    }
    *window = foreground;
    *client_origin = origin;
    return true;
}

void ObserveWorldMap() noexcept {
    const ULONGLONG now = GetTickCount64();
    WorldMapSnapshot snapshot{};
    if (
        g_world_map_object != 0U
        && !ReadWorldMapSnapshot(g_world_map_object, &snapshot)
    ) {
        g_world_map_object = 0U;
    }
    if (
        g_world_map_object == 0U
        && (
            g_last_object_scan == 0U
            || now - g_last_object_scan >= kObjectScanIntervalMilliseconds
        )
    ) {
        g_last_object_scan = now;
        DiscoverWorldMapObject(&g_world_map_object);
        if (g_world_map_object != 0U) {
            ReadWorldMapSnapshot(g_world_map_object, &snapshot);
        }
    }
    if (!snapshot.valid) {
        g_snapshot = {};
        return;
    }
    HWND window = nullptr;
    POINT origin{};
    if (!ForegroundClient(&window, &origin)) {
        g_snapshot = {};
        return;
    }
    snapshot.window = window;
    snapshot.client_origin = origin;
    snapshot.observed_at = now;
    g_snapshot = snapshot;
}

bool ResolveDestination(
    const WorldMapSnapshot& snapshot,
    const POINT desktop_point,
    double* const lt,
    double* const lg,
    std::int32_t* const client_x,
    std::int32_t* const client_y
) noexcept {
    if (
        !snapshot.valid
        || lt == nullptr
        || lg == nullptr
        || client_x == nullptr
        || client_y == nullptr
    ) {
        return false;
    }
    const WorldMapProjection projection{
        snapshot.open,
        snapshot.left,
        snapshot.top,
        snapshot.right,
        snapshot.bottom,
        snapshot.left_padding,
        snapshot.top_padding,
        snapshot.right_padding,
        snapshot.bottom_padding,
        snapshot.zoom,
        snapshot.horizontal_pan,
        snapshot.vertical_pan,
        snapshot.world_length,
        snapshot.world_width,
    };
    ResolvedWorldMapDestination destination{};
    if (!ProjectWorldMapDestination(
            projection,
            snapshot.client_origin,
            desktop_point,
            &destination
        )) {
        return false;
    }
    *lt = destination.lt;
    *lg = destination.lg;
    *client_x = destination.client_x;
    *client_y = destination.client_y;
    return true;
}

LRESULT CALLBACK MouseHook(
    const int code,
    const WPARAM message,
    const LPARAM event_pointer
) noexcept {
    if (code < 0 || event_pointer == 0) {
        return CallNextHookEx(g_mouse_hook, code, message, event_pointer);
    }
    const auto& mouse = *reinterpret_cast<const MSLLHOOKSTRUCT*>(event_pointer);
    if (!IsAcceptedWorldMapPointerInput(mouse.flags, mouse.dwExtraInfo)) {
        return CallNextHookEx(g_mouse_hook, code, message, event_pointer);
    }
    std::uint32_t button = 0U;
    bool button_down = false;
    bool button_up = false;
    if (message == WM_LBUTTONDOWN || message == WM_LBUTTONUP) {
        button = kLeftPointerButton;
        button_down = message == WM_LBUTTONDOWN;
        button_up = message == WM_LBUTTONUP;
    } else if (message == WM_RBUTTONDOWN || message == WM_RBUTTONUP) {
        button = kRightPointerButton;
        button_down = message == WM_RBUTTONDOWN;
        button_up = message == WM_RBUTTONUP;
    }
    if (button == 0U) {
        return CallNextHookEx(g_mouse_hook, code, message, event_pointer);
    }

    const ULONGLONG now = GetTickCount64();
    HWND foreground = nullptr;
    POINT origin{};
    const bool foreground_matches = ForegroundClient(&foreground, &origin);
    if (button_up) {
        const bool suppress = (
            g_pending_button_up.active
            && g_pending_button_up.button == button
            && now <= g_pending_button_up.expires_at
            && foreground_matches
            && foreground == g_pending_button_up.window
        );
        g_pending_button_up = {};
        if (suppress) {
            return 1;
        }
        return CallNextHookEx(g_mouse_hook, code, message, event_pointer);
    }
    if (!button_down) {
        return CallNextHookEx(g_mouse_hook, code, message, event_pointer);
    }
    g_pending_button_up = {};
    const WorldMapSnapshot snapshot = g_snapshot;
    if (
        !foreground_matches
        || foreground != snapshot.window
        || origin.x != snapshot.client_origin.x
        || origin.y != snapshot.client_origin.y
        || now < snapshot.observed_at
        || now - snapshot.observed_at > kMaximumObservationAgeMilliseconds
    ) {
        return CallNextHookEx(g_mouse_hook, code, message, event_pointer);
    }
    double lt = 0.0;
    double lg = 0.0;
    std::int32_t client_x = 0;
    std::int32_t client_y = 0;
    if (!ResolveDestination(
            snapshot,
            mouse.pt,
            &lt,
            &lg,
            &client_x,
            &client_y
        )) {
        return CallNextHookEx(g_mouse_hook, code, message, event_pointer);
    }
    FILETIME captured_at{};
    GetSystemTimeAsFileTime(&captured_at);
    ULARGE_INTEGER captured_value{};
    captured_value.LowPart = captured_at.dwLowDateTime;
    captured_value.HighPart = captured_at.dwHighDateTime;
    const WorldMapDestination event{
        button,
        captured_value.QuadPart,
        static_cast<std::uint64_t>(reinterpret_cast<std::uintptr_t>(foreground)),
        lt,
        lg,
        snapshot.snapshot_hash,
        mouse.pt.x,
        mouse.pt.y,
        client_x,
        client_y,
    };
    if (!TryPublishWorldMapDestination(event)) {
        return CallNextHookEx(g_mouse_hook, code, message, event_pointer);
    }
    g_pending_button_up = PendingButtonUp{
        true,
        button,
        foreground,
        now + kPendingButtonUpMilliseconds,
    };
    return 1;
}

DWORD WINAPI CaptureThread(void*) noexcept {
    g_capture_thread_id = GetCurrentThreadId();
    g_mouse_hook = SetWindowsHookExW(
        WH_MOUSE_LL,
        MouseHook,
        g_extension_module,
        0U
    );
    if (g_mouse_hook == nullptr) {
        InterlockedExchange(
            &g_capture_start_result,
            static_cast<LONG>(GetLastError())
        );
        SetEvent(g_capture_ready);
        return 0U;
    }
    if (SetTimer(nullptr, kObservationTimerId, kObservationTimerMilliseconds, nullptr) == 0U) {
        const DWORD error = GetLastError();
        UnhookWindowsHookEx(g_mouse_hook);
        g_mouse_hook = nullptr;
        InterlockedExchange(&g_capture_start_result, static_cast<LONG>(error));
        SetEvent(g_capture_ready);
        return 0U;
    }
    ObserveWorldMap();
    InterlockedExchange(&g_capture_start_result, ERROR_SUCCESS);
    SetEvent(g_capture_ready);
    MSG message{};
    while (true) {
        const BOOL status = GetMessageW(&message, nullptr, 0U, 0U);
        if (status <= 0) {
            break;
        }
        if (message.message == WM_TIMER && message.wParam == kObservationTimerId) {
            ObserveWorldMap();
        }
    }
    KillTimer(nullptr, kObservationTimerId);
    UnhookWindowsHookEx(g_mouse_hook);
    g_mouse_hook = nullptr;
    g_snapshot = {};
    g_pending_button_up = {};
    return 0U;
}

}  // namespace

bool IsReviewedWorldMapClient() noexcept {
    wchar_t executable_path[32768]{};
    const DWORD length = GetModuleFileNameW(
        nullptr,
        executable_path,
        static_cast<DWORD>(std::size(executable_path))
    );
    if (
        length == 0U
        || static_cast<std::size_t>(length) >= std::size(executable_path)
    ) {
        return false;
    }
    const wchar_t* file_name = executable_path;
    for (const wchar_t* cursor = executable_path; *cursor != L'\0'; ++cursor) {
        if (*cursor == L'\\' || *cursor == L'/') {
            file_name = cursor + 1;
        }
    }
    if (lstrcmpiW(file_name, L"sb.exe") != 0) {
        return false;
    }
    const HMODULE module = GetModuleHandleW(nullptr);
    if (reinterpret_cast<std::uintptr_t>(module) != kReviewedImageBase) {
        return false;
    }
    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(module);
    if (
        dos->e_magic != IMAGE_DOS_SIGNATURE
        || dos->e_lfanew <= 0
        || static_cast<std::uint32_t>(dos->e_lfanew)
            > kReviewedImageSize - sizeof(IMAGE_NT_HEADERS32)
    ) {
        return false;
    }
    const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS32*>(
        reinterpret_cast<const std::uint8_t*>(module) + dos->e_lfanew
    );
    if (
        nt->Signature != IMAGE_NT_SIGNATURE
        || nt->FileHeader.Machine != IMAGE_FILE_MACHINE_I386
        || nt->FileHeader.NumberOfSections != kReviewedSectionCount
        || nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR32_MAGIC
        || nt->OptionalHeader.ImageBase != kReviewedImageBase
        || nt->OptionalHeader.SizeOfImage != kReviewedImageSize
        || nt->OptionalHeader.AddressOfEntryPoint != kReviewedEntryPointRva
    ) {
        return false;
    }
    std::uint8_t entry_prefix[5]{};
    if (
        !ReadMemory(
            kReviewedImageBase + kReviewedEntryPointRva,
            entry_prefix,
            sizeof(entry_prefix)
        )
        || entry_prefix[0] != 0xE9U
    ) {
        return false;
    }
    return ReadReviewedVtables();
}

DWORD StartWorldMapCapture(
    const HMODULE extension_module,
    const ProcessIdentity& identity
) noexcept {
    if (
        extension_module == nullptr
        || identity.process_id != GetCurrentProcessId()
        || identity.creation_filetime_utc == 0U
        || g_capture_thread != nullptr
        || g_capture_ready != nullptr
        || !IsReviewedWorldMapClient()
    ) {
        return ERROR_NOT_SUPPORTED;
    }
    g_extension_module = extension_module;
    g_process_identity = identity;
    g_capture_ready = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (g_capture_ready == nullptr) {
        return GetLastError();
    }
    InterlockedExchange(&g_capture_start_result, ERROR_IO_PENDING);
    g_capture_thread = CreateThread(nullptr, 0U, CaptureThread, nullptr, 0U, nullptr);
    if (g_capture_thread == nullptr) {
        const DWORD error = GetLastError();
        CloseHandle(g_capture_ready);
        g_capture_ready = nullptr;
        return error;
    }
    const DWORD wait_result = WaitForSingleObject(
        g_capture_ready,
        kCaptureStartupTimeoutMilliseconds
    );
    if (wait_result != WAIT_OBJECT_0) {
        const DWORD error = wait_result == WAIT_TIMEOUT ? ERROR_TIMEOUT : GetLastError();
        if (g_capture_thread_id != 0U) {
            PostThreadMessageW(g_capture_thread_id, WM_QUIT, 0U, 0);
        }
        WaitForSingleObject(g_capture_thread, kCaptureStartupTimeoutMilliseconds);
        CloseHandle(g_capture_thread);
        g_capture_thread = nullptr;
        CloseHandle(g_capture_ready);
        g_capture_ready = nullptr;
        return error;
    }
    const DWORD result = static_cast<DWORD>(InterlockedCompareExchange(
        &g_capture_start_result,
        0,
        0
    ));
    if (result != ERROR_SUCCESS) {
        WaitForSingleObject(g_capture_thread, kCaptureStartupTimeoutMilliseconds);
        CloseHandle(g_capture_thread);
        g_capture_thread = nullptr;
        CloseHandle(g_capture_ready);
        g_capture_ready = nullptr;
        return result;
    }
    return ERROR_SUCCESS;
}

void StopWorldMapCapture() noexcept {
    if (g_capture_thread != nullptr) {
        if (g_capture_thread_id != 0U) {
            PostThreadMessageW(g_capture_thread_id, WM_QUIT, 0U, 0);
        }
        WaitForSingleObject(g_capture_thread, kCaptureStartupTimeoutMilliseconds);
        CloseHandle(g_capture_thread);
        g_capture_thread = nullptr;
    }
    if (g_capture_ready != nullptr) {
        CloseHandle(g_capture_ready);
        g_capture_ready = nullptr;
    }
    g_capture_thread_id = 0U;
    g_extension_module = nullptr;
    g_process_identity = {};
    g_world_map_object = 0U;
    g_last_object_scan = 0U;
    g_snapshot = {};
    g_pending_button_up = {};
}

}  // namespace wonderbane::extension
