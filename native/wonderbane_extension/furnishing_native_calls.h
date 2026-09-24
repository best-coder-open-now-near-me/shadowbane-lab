#pragma once
#include "furnishing_selection.h"
#include "furnishing_queue.h"
#include <Windows.h>

namespace wonderbane::extension::furnishing {
// Exact-image native ABI adapters. Resource/selection qualification and queue
// membership are separate prerequisites supplied by RenderOwner and its runtime.
// No method is registered at startup by this class; Configure executes no game code.
class NativeCalls {
public:
    bool Configure() noexcept;
    bool Bind(HWND) noexcept; // verified owner with current drawable; one binding
    bool Owner() const noexcept;
    Address Base() const noexcept { return base_; }
    bool RetainModel(Address model, Address* slot) noexcept;
    bool Clone(Address render, Address* slot) noexcept;
    bool Release(Address* slot) noexcept;
    bool Compose(Address render, const Transform&) noexcept;
    bool Enqueue(Address render, Address queue) noexcept;
    enum class FloorResult { unavailable, miss, hit, fault };
    FloorResult Floor(const Selection&, int x, int y, std::array<float,3>&) noexcept;
    bool Pool(QueueReceipt::Pool&) const noexcept;
    bool Erase(Address queue, Address node) noexcept;
    static bool Read(Address, void*, std::size_t) noexcept;
private:
    enum class Action { retain, clone, release, compose, enqueue, erase };
    struct Calls {
        void (__thiscall* retain)(void*, Address*) = nullptr;
        void (__thiscall* clone)(void*, Address*, bool) = nullptr;
        void (__thiscall* release)(Address*, void*) = nullptr;
        void (__thiscall* compose)(void*, const Transform*) = nullptr;
        void (__thiscall* enqueue)(void*, void*) = nullptr;
        void (__thiscall* erase)(void*, void*) = nullptr;
        bool (__thiscall* floor)(void*, int, int, std::array<float,3>*) = nullptr;
        HGLRC (WINAPI* context)() = &wglGetCurrentContext;
        HDC (WINAPI* dc)() = &wglGetCurrentDC;
    } calls_{};
    bool Reference(Address object, bool model, Address& adjusted) const noexcept;
    bool Cxx(Action, Address receiver, Address* slot, const Transform*, Address argument) noexcept;
    bool Guard(Action, Address receiver, Address* slot, const Transform*, Address argument) noexcept;
    FloorResult FloorCxx(Address hud, int x, int y, std::array<float,3>&) noexcept;
    FloorResult FloorGuard(Address hud, int x, int y, std::array<float,3>&) noexcept;
    Address base_ = 0;
    HWND window_ = nullptr;
    HGLRC context_ = nullptr;
    DWORD thread_ = 0;
    friend struct NativeCallsTestAccess;
};
}
