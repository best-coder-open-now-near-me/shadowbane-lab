#include "navigation_viewer.h"
#include "navigation_channel.h"

namespace wonderbane::extension {
namespace {
SRWLOCK g_draw_lock = SRWLOCK_INIT;
NavigationFrameBuffer g_frame;
}
void DrawNavigationInspector() noexcept {
    if (!TryAcquireSRWLockExclusive(&g_draw_lock)) return;
    if (ReadNavigationFrame(&g_frame) && (g_frame.header.flags & navigation::kEnabled) != 0U) {
        GraphicsCameraState camera{};
        const bool available = ReadPendingGraphicsCameraState(&camera);
        (void)RenderNavigationGeometry(g_frame.header,
            reinterpret_cast<const navigation::Line*>(g_frame.bytes.data() + sizeof(navigation::FrameHeader)),
            available ? &camera : nullptr);
    }
    ReleaseSRWLockExclusive(&g_draw_lock);
}
}  // namespace wonderbane::extension
