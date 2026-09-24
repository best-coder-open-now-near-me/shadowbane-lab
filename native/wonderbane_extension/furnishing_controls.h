#pragma once
#include "furnishing_selection.h"
#include <Windows.h>
namespace wonderbane::extension::furnishing {
// A process-pinned observer of the Furniture HUD's existing virtual dispatch.
// Every native action is forwarded once; this class owns no placement input.
class PreviewControls {
public:
    enum class Action { select, left, right, cancel, drop, suspend };
    struct Events {
        void* context=nullptr;
        void (*action)(void*,Action,Address) noexcept=nullptr;
        bool (*read)(Address,void*,std::size_t) noexcept=nullptr;
    };
    explicit PreviewControls(Events e) noexcept : events_(e) {}
    bool Bind(HWND,Address reviewed_base) noexcept;
    bool Current() const noexcept;
    void Retire() noexcept;
private:
    static void __fastcall Selected(void*,void*,Address);
    static void __fastcall Dropped(void*,void*,Address);
    static void __fastcall Cancelled(void*,void*);
    static void __fastcall Left(void*,void*);
    static void __fastcall Right(void*,void*);
    static LRESULT CALLBACK Window(HWND,UINT,WPARAM,LPARAM,UINT_PTR,DWORD_PTR);
    void Send(Action,Address) noexcept;
    HWND window_=nullptr;
    DWORD thread_=0;
    Events events_{};
    Address base_=0;
    bool retired_=false,installed_=false;
};
}
