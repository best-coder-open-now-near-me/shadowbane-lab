#pragma once
#include "furnishing_selection.h"
#include <Windows.h>
namespace wonderbane::extension::furnishing {
class PreviewControls {
public:
    enum class Action { start, left, right, cancel, hold };
    enum class Hit { outside, inside, unavailable };
    struct Events {
        void* context=nullptr;
        void (*action)(void*,Action) noexcept=nullptr;
        bool (*current)(void*,const Selection&) noexcept=nullptr;
        Hit (*contains)(void*,const Selection&,int,int) noexcept=nullptr;
    };
    explicit PreviewControls(Events e) noexcept : events_(e) {}
    bool Bind(HWND) noexcept;
    void Show(const Selection*,bool active,const wchar_t* status) noexcept;
    void Hide() noexcept;
    void Retire() noexcept;
private:
    static LRESULT CALLBACK Panel(HWND,UINT,WPARAM,LPARAM);
    static LRESULT CALLBACK Window(HWND,UINT,WPARAM,LPARAM,UINT_PTR,DWORD_PTR);
    void Send(Action) noexcept;
    void Paint() noexcept;
    HWND window_=nullptr,panel_=nullptr;
    DWORD thread_=0;
    Events events_{};
    Selection selection_{};
    const wchar_t* status_=L"Select an item to preview";
    int pressed_=-1;
    bool visible_=false,active_=false,mouse_owned_=false,escape_owned_=false;
};
}
