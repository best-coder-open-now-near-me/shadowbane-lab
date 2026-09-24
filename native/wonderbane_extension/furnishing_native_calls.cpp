#include "furnishing_native_calls.h"
#include "graphics_status.h"
#include "movement_native_image.h"
#include "movement_lifetime.h"
#include <cstring>
#include <cmath>

namespace wonderbane::extension::furnishing {
static_assert(sizeof(void*) == sizeof(Address));
namespace {
bool Pointer(Address p) noexcept { return p >= 0x10000 && p < 0x7fff0000 && p % 4 == 0; }
template<class T> bool ReadValue(Address p, T& out) noexcept { return NativeCalls::Read(p, &out, sizeof(out)); }
}
bool NativeCalls::Read(Address at, void* out, std::size_t size) noexcept {
    if (!Pointer(at) || !out || !size || size > 0x7fff0000U - at) { return false; }
    __try { std::memcpy(out, reinterpret_cast<const void*>(at), size); return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool NativeCalls::Configure() noexcept {
    if (base_ || window_) { return false; }
    std::uintptr_t base = 0;
    if ((!GraphicsExecutableSha256Matches("6347b420c6c151995f168f16fd1624408dd8911698d11a4a74b26d211fb49f19")
        && !GraphicsExecutableSha256Matches("7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f"))
        || !movement::VerifyNativeMovementImage(base) || !Pointer(static_cast<Address>(base)) || base > 0x7d000000) { return false; }
    base_ = static_cast<Address>(base);
    calls_.retain = reinterpret_cast<decltype(calls_.retain)>(base_ + 0x131190);
    calls_.clone = reinterpret_cast<decltype(calls_.clone)>(base_ + 0x1c68f0);
    calls_.release = reinterpret_cast<decltype(calls_.release)>(base_ + 0x89bd0);
    calls_.compose = reinterpret_cast<decltype(calls_.compose)>(base_ + 0x1c5950);
    calls_.enqueue = reinterpret_cast<decltype(calls_.enqueue)>(base_ + 0x1cb020);
    calls_.floor = reinterpret_cast<decltype(calls_.floor)>(base_ + 0x5936d0);
    calls_.erase = reinterpret_cast<decltype(calls_.erase)>(base_ + 0x4d9a70);
    return true;
}
bool NativeCalls::Bind(HWND window) noexcept {
    if (!base_ || window_) { return false; }
    DWORD process = 0; const auto thread = GetCurrentThreadId();
    const auto context = calls_.context();
    if (!window || !context || GetWindowThreadProcessId(window, &process) != thread
        || process != GetCurrentProcessId() || WindowFromDC(calls_.dc()) != window) { return false; }
    window_ = window; thread_ = thread; context_ = context; return true;
}
bool NativeCalls::Owner() const noexcept {
    DWORD process = 0;
    return base_ && window_ && thread_ == GetCurrentThreadId()
        && GetWindowThreadProcessId(window_, &process) == thread_ && process == GetCurrentProcessId()
        && context_ && calls_.context() == context_ && WindowFromDC(calls_.dc()) == window_;
}
bool NativeCalls::Reference(Address object, bool model, Address& adjusted) const noexcept {
    adjusted = 0; Address type = 0, vb = 0, offset = 0, table = 0, release = 0, count = 0;
    const Address expected = model ? 0x718U : 0x154U;
    if (!Pointer(object) || object > 0x7fff0000U - expected - 8
        || !ReadValue(object, type) || type != base_ + (model ? 0x1143540U : 0x1149dbcU)
        || !ReadValue(object + 8, vb) || vb != base_ + (model ? 0x114369cU : 0x1149e04U)
        || !ReadValue(vb + 4, offset) || offset != expected - 8
        || !ReadValue(object + expected, table) || table != base_ + (model ? 0x11434ccU : 0x1149d70U)
        || !ReadValue(table + 8, release) || release != base_ + 0x26f49
        || !ReadValue(object + expected + 4, count) || !count || count > 0x1000000) { return false; }
    if (model) {
        std::uintptr_t receiver = 0;
        if (!movement::NativeMovementReferenceInterface(reinterpret_cast<void*>(object), receiver)
            || receiver != object + expected) { return false; }
    } else {
        Address finalizer = 0;
        if (!ReadValue(table + 4, finalizer) || finalizer != base_ + 0x127ab) { return false; }
    }
    adjusted = object + expected; return true;
}
bool NativeCalls::Cxx(Action action, Address receiver, Address* slot, const Transform* pose, Address argument) noexcept {
    try {
        switch (action) {
        case Action::retain: calls_.retain(reinterpret_cast<void*>(receiver), slot); break;
        case Action::clone: calls_.clone(reinterpret_cast<void*>(receiver), slot, true); break;
        case Action::release: calls_.release(slot, nullptr); break;
        case Action::compose: calls_.compose(reinterpret_cast<void*>(receiver), pose); break;
        case Action::enqueue: calls_.enqueue(reinterpret_cast<void*>(receiver + 0x30), reinterpret_cast<void*>(argument)); break;
        case Action::erase: calls_.erase(reinterpret_cast<void*>(receiver), reinterpret_cast<void*>(argument)); break;
        }
        return true;
    } catch (...) { return false; }
}
bool NativeCalls::Guard(Action action, Address receiver, Address* slot, const Transform* pose, Address argument) noexcept {
    __try { return Cxx(action, receiver, slot, pose, argument); }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool NativeCalls::RetainModel(Address model, Address* slot) noexcept {
    Address adjusted = 0;
    return Owner() && slot && *slot == model && Reference(model, true, adjusted)
        && Guard(Action::retain, adjusted, slot, nullptr, 0);
}
bool NativeCalls::Clone(Address render, Address* slot) noexcept {
    Address adjusted = 0;
    return Owner() && slot && !*slot && Reference(render, false, adjusted)
        && Guard(Action::clone, render, slot, nullptr, 0);
}
bool NativeCalls::Release(Address* slot) noexcept {
    if (!Owner() || !slot) { return false; }
    if (!*slot) { return true; }
    Address adjusted = 0, type = 0;
    return ReadValue(*slot, type) && Reference(*slot, type == base_ + 0x1143540, adjusted)
        && Guard(Action::release, 0, slot, nullptr, 0) && !*slot;
}
bool NativeCalls::Compose(Address render, const Transform& pose) noexcept {
    Address adjusted = 0;
    return Owner() && ValidTransform(pose) && Reference(render, false, adjusted)
        && Guard(Action::compose, render, nullptr, &pose, 0);
}
bool NativeCalls::Enqueue(Address render, Address queue) noexcept {
    Address adjusted = 0;
    return Owner() && Pointer(queue) && Reference(render, false, adjusted)
        && Guard(Action::enqueue, render, nullptr, nullptr, queue);
}
bool NativeCalls::Pool(QueueReceipt::Pool& pool) const noexcept {
    pool = {};
    return Owner() && ReadValue(base_ + 0x1388bf4, pool.begin)
        && ReadValue(base_ + 0x12d6de8, pool.capacity) && ReadValue(base_ + 0x1388c08, pool.used);
}
bool NativeCalls::Erase(Address queue, Address node) noexcept {
    return Owner() && Pointer(queue) && Pointer(node) && Guard(Action::erase, queue, nullptr, nullptr, node);
}
NativeCalls::FloorResult NativeCalls::FloorCxx(Address hud, int x, int y, std::array<float,3>& point) noexcept {
    try { return calls_.floor(reinterpret_cast<void*>(hud), x, y, &point) ? FloorResult::hit : FloorResult::miss; }
    catch (...) { return FloorResult::fault; }
}
NativeCalls::FloorResult NativeCalls::FloorGuard(Address hud, int x, int y, std::array<float,3>& point) noexcept {
    __try { return FloorCxx(hud,x,y,point); }
    __except(EXCEPTION_EXECUTE_HANDLER) { return FloorResult::fault; }
}
NativeCalls::FloorResult NativeCalls::Floor(const Selection& s, int x, int y, std::array<float,3>& out) noexcept {
    out = {};
    Address type=0, structure=0, floor=0;
    if (!Owner() || !calls_.floor || !ReadValue(s.hud,type) || type!=base_+0x1167c68
        || !ReadValue(s.hud+0x64c,structure) || structure!=s.structure
        || !ReadValue(s.hud+0x628,floor) || floor!=s.floor) { return FloorResult::unavailable; }
    std::array<float,3> point{};
    const auto result=FloorGuard(s.hud,x,y,point);
    if (result==FloorResult::hit) {
        for (float v:point) { if (!std::isfinite(v)) { return FloorResult::fault; } }
        if (!Owner()) { return FloorResult::fault; }
        out=point;
    }
    return result;
}

}
