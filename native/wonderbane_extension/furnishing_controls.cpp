#include "furnishing_controls.h"
#include "furnishing_pose.h"
#include <CommCtrl.h>
#include <windowsx.h>
#include <algorithm>
namespace wonderbane::extension::furnishing {
namespace {
constexpr UINT_PTR subclass=0x57424650;
constexpr wchar_t panel_class[]=L"WonderBaneFurnishingPreview";
constexpr int width=490,height=66;
}
bool PreviewControls::Bind(HWND window) noexcept {
    if(window_) { return window==window_; }
    DWORD pid=0; thread_=GetCurrentThreadId();
    if(!window || GetWindowThreadProcessId(window,&pid)!=thread_ || pid!=GetCurrentProcessId()) { return false; }
    WNDCLASSW cls{}; cls.lpfnWndProc=&Panel; cls.hInstance=GetModuleHandleW(nullptr);
    cls.lpszClassName=panel_class; cls.hCursor=LoadCursorW(nullptr,IDC_ARROW);
    if(!RegisterClassW(&cls) && GetLastError()!=ERROR_CLASS_ALREADY_EXISTS) { return false; }
    window_=window;
    panel_=CreateWindowExW(WS_EX_NOACTIVATE,panel_class,L"Furnishing preview",WS_CHILD|WS_CLIPSIBLINGS,
        0,0,width,height,window,nullptr,cls.hInstance,this);
    if(!panel_ || !SetWindowSubclass(window,&Window,subclass,reinterpret_cast<DWORD_PTR>(this))) {
        if(panel_) { DestroyWindow(panel_); } panel_=nullptr; window_=nullptr; return false;
    }
    return true;
}
void PreviewControls::Send(Action action) noexcept { if(events_.action) { events_.action(events_.context,action); } }
void PreviewControls::Show(const Selection* s,bool active,const wchar_t* status) noexcept {
    if(!s || !window_ || !panel_ || GetCurrentThreadId()!=thread_) { Hide(); return; }
    const bool changed=!visible_ || active_!=active || status_!=status;
    selection_=*s; active_=active; status_=status;
    RECT client{}; if(!GetClientRect(window_,&client) || client.right<width || client.bottom<height) { Hide(); return; }
    SetWindowPos(panel_,HWND_TOP,8,std::max(0L,client.bottom-height-8),width,height,SWP_NOACTIVATE|SWP_SHOWWINDOW);
    visible_=true; if(changed) { InvalidateRect(panel_,nullptr,FALSE); }
}
void PreviewControls::Hide() noexcept {
    active_=false; visible_=false;
    if(panel_ && GetCurrentThreadId()==thread_) { ShowWindow(panel_,SW_HIDE); }
}
void PreviewControls::Retire() noexcept {
    if(GetCurrentThreadId()!=thread_) { return; }
    Hide(); if(panel_) { DestroyWindow(panel_); panel_=nullptr; }
    if(window_) { RemoveWindowSubclass(window_,&Window,subclass); window_=nullptr; }
}
void PreviewControls::Paint() noexcept {
    PAINTSTRUCT paint{}; HDC dc=BeginPaint(panel_,&paint); if(!dc) { return; }
    RECT bounds{0,0,width,height}; FillRect(dc,&bounds,GetSysColorBrush(COLOR_BTNFACE));
    const auto font=SelectObject(dc,GetStockObject(DEFAULT_GUI_FONT)); SetBkMode(dc,TRANSPARENT);
    SetTextColor(dc,GetSysColor(COLOR_BTNTEXT));
    const wchar_t* labels[]={active_?L"Preview active":L"Preview",L"Rotate left",L"Rotate right",L"Cancel"};
    for(int i=0;i<4;++i) {
        RECT button{8+i*119,6,119+i*119,31};
        DrawEdge(dc,&button,BDR_RAISEDINNER,BF_RECT); DrawTextW(dc,labels[i],-1,&button,DT_CENTER|DT_VCENTER|DT_SINGLELINE);
    }
    RECT text{8,37,width-8,height-4}; DrawTextW(dc,status_,-1,&text,DT_LEFT|DT_VCENTER|DT_SINGLELINE|DT_END_ELLIPSIS);
    SelectObject(dc,font); EndPaint(panel_,&paint);
}
LRESULT CALLBACK PreviewControls::Panel(HWND hwnd,UINT message,WPARAM wp,LPARAM lp) {
    auto* self=reinterpret_cast<PreviewControls*>(GetWindowLongPtrW(hwnd,GWLP_USERDATA));
    if(message==WM_NCCREATE) {
        self=static_cast<PreviewControls*>(reinterpret_cast<CREATESTRUCTW*>(lp)->lpCreateParams);
        SetWindowLongPtrW(hwnd,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(self));
    }
    if(self) {
        if(message==WM_MOUSEACTIVATE) { return MA_NOACTIVATE; }
        if(message==WM_ERASEBKGND) { return 1; }
        if(message==WM_PAINT) { self->Paint(); return 0; }
        if(message==WM_LBUTTONDOWN) {
            const int x=GET_X_LPARAM(lp)-8, y=GET_Y_LPARAM(lp);
            self->pressed_=(x>=0 && x<476 && x%119<111 && y>=6 && y<=31)?x/119:-1;
            if(self->pressed_>=0) { SetCapture(hwnd); } return 0;
        }
        if(message==WM_LBUTTONUP) {
            const int x=GET_X_LPARAM(lp)-8;
            const int pressed=self->pressed_; self->pressed_=-1;
            if(GetCapture()==hwnd) { ReleaseCapture(); }
            if(x>=0 && x<476 && x%119<111 && x/119==pressed && GET_Y_LPARAM(lp)>=6 && GET_Y_LPARAM(lp)<=31) {
                const Action actions[]={Action::start,Action::left,Action::right,Action::cancel};
                if(x/119==3 || (self->events_.current && self->events_.current(self->events_.context,self->selection_))) {
                    if(x/119==0) { self->active_=true; }
                    self->Send(actions[x/119]);
                }
            }
            return 0;
        }
    }
    return DefWindowProcW(hwnd,message,wp,lp);
}
LRESULT CALLBACK PreviewControls::Window(HWND hwnd,UINT message,WPARAM wp,LPARAM lp,UINT_PTR,DWORD_PTR ref) {
    auto& self=*reinterpret_cast<PreviewControls*>(ref);
    if(GetCurrentThreadId()!=self.thread_) { return DefSubclassProc(hwnd,message,wp,lp); }
    if(message==WM_NCDESTROY) { self.Send(Action::cancel); self.Retire(); return DefSubclassProc(hwnd,message,wp,lp); }
    if((message==WM_ACTIVATEAPP && !wp) || message==WM_CANCELMODE
        || (message==WM_KILLFOCUS && reinterpret_cast<HWND>(wp)!=self.panel_)) { self.Send(Action::cancel); }
    if(message==WM_CAPTURECHANGED && self.mouse_owned_ && reinterpret_cast<HWND>(lp)!=hwnd) {
        self.Send(Action::cancel); // keep the owned release until it arrives
    }
    if(message==WM_KEYUP && wp==VK_ESCAPE && self.escape_owned_) { self.escape_owned_=false; return 0; }
    if(message==WM_KEYDOWN && wp==VK_ESCAPE && self.active_) {
        self.escape_owned_=true; self.Send(Action::cancel); return 0;
    }
    if(message==WM_LBUTTONUP && self.mouse_owned_) {
        self.mouse_owned_=false;
        if(GetCapture()==hwnd) { ReleaseCapture(); }
        if(self.active_) { self.Send(Action::hold); } return 0;
    }
    if((message==WM_LBUTTONDOWN || message==WM_LBUTTONDBLCLK) && self.mouse_owned_ && GetCapture()!=hwnd) {
        self.mouse_owned_=false; // a fresh down proves an earlier outside release
    }
    if((message==WM_LBUTTONDOWN || message==WM_LBUTTONDBLCLK) && self.visible_ && self.active_
        && self.events_.contains && self.events_.contains(self.events_.context,self.selection_,GET_X_LPARAM(lp),GET_Y_LPARAM(lp))) {
        // Even a now-stale preview never forwards its initiating placement click.
        self.mouse_owned_=true;
        if(!self.events_.current || !self.events_.current(self.events_.context,self.selection_)) { self.Send(Action::cancel); }
        SetCapture(hwnd); return 0;
    }
    if(message==WM_MOUSEMOVE && self.mouse_owned_) { wp&=~WPARAM(MK_LBUTTON); }
    return DefSubclassProc(hwnd,message,wp,lp);
}
}
