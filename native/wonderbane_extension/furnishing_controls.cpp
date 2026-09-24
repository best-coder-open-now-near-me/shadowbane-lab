#include "furnishing_controls.h"
#include "import_hook.h"
#include "render_lifetime.h"
#include <CommCtrl.h>
#include <atomic>
namespace wonderbane::extension::furnishing {
namespace {
constexpr UINT_PTR subclass=0x57424650;
constexpr Address table=0x1167c68;
constexpr std::array<Address,5> offsets{0xe4,0xbc,0x128,0x1f0,0x1f4};
constexpr std::array<Address,5> methods{0x19a9c,0x1deee,0x1e6c8,0xa245,0xcc1b};
std::atomic<PreviewControls*> observer{nullptr};
// Published before any replacement, retained even after Stop/window retirement.
std::array<Address,5> originals{},replacements{};
void Forward(unsigned i,void* receiver) { reinterpret_cast<void(__thiscall*)(void*)>(originals[i])(receiver); }
void Forward(unsigned i,void* receiver,Address argument) { reinterpret_cast<void(__thiscall*)(void*,Address)>(originals[i])(receiver,argument); }
}
bool PreviewControls::Bind(HWND window,Address base) noexcept {
    if(window_ || observer.load(std::memory_order_acquire) || !events_.read) { return false; }
    DWORD pid=0; const auto thread=GetCurrentThreadId();
    if(!window || GetWindowThreadProcessId(window,&pid)!=thread || pid!=GetCurrentProcessId()) { return false; }
    for(unsigned i=0;i<offsets.size();++i) {
        Address actual=0;
        if(!events_.read(base+table+offsets[i],&actual,4) || actual!=base+methods[i]) { return false; }
        originals[i]=actual;
    }
    replacements={reinterpret_cast<Address>(&Selected),reinterpret_cast<Address>(&Dropped),reinterpret_cast<Address>(&Cancelled),
        reinterpret_cast<Address>(&Left),reinterpret_cast<Address>(&Right)};
    window_=window; thread_=thread; base_=base;
    PreviewControls* expected=nullptr;
    if(!observer.compare_exchange_strong(expected,this,std::memory_order_release)) { return false; }
    // Runtime storage is already pinned. Partial installation remains a forwarding
    // observer, never an invitation to overwrite a foreign slot or retry.
    for(unsigned i=0;i<offsets.size();++i) {
        if(ReplaceImportAddressSlot(reinterpret_cast<Address*>(base+table+offsets[i]),originals[i],replacements[i])!=ERROR_SUCCESS) {
            Retire(); return false;
        }
    }
    if(!SetWindowSubclass(window,&Window,subclass,reinterpret_cast<DWORD_PTR>(this))) { Retire(); return false; }
    installed_=true; return true;
}
bool PreviewControls::Current() const noexcept {
    if(GetCurrentThreadId()!=thread_ || !installed_ || retired_) { return false; }
    for(unsigned i=0;i<offsets.size();++i) {
        Address actual=0;
        if(!events_.read(base_+table+offsets[i],&actual,4) || actual!=replacements[i]) { return false; }
    }
    return true;
}
void PreviewControls::Send(Action action,Address hud) noexcept {
    const RenderCallbackLease lease;
    if(GetCurrentThreadId()==thread_ && !retired_ && events_.action) { events_.action(events_.context,action,hud); }
}
void PreviewControls::Retire() noexcept {
    if(GetCurrentThreadId()!=thread_) { return; }
    retired_=true;
    if(window_) { RemoveWindowSubclass(window_,&Window,subclass); window_=nullptr; }
}
void __fastcall PreviewControls::Selected(void* hud,void*,Address child) {
    Forward(0,hud,child);
    observer.load(std::memory_order_acquire)->Send(Action::select,reinterpret_cast<Address>(hud));
}
void __fastcall PreviewControls::Dropped(void* hud,void*,Address child) {
    observer.load(std::memory_order_acquire)->Send(Action::drop,reinterpret_cast<Address>(hud));
    Forward(1,hud,child);
}
void __fastcall PreviewControls::Cancelled(void* hud,void*) {
    observer.load(std::memory_order_acquire)->Send(Action::cancel,reinterpret_cast<Address>(hud)); Forward(2,hud);
}
void __fastcall PreviewControls::Left(void* hud,void*) {
    observer.load(std::memory_order_acquire)->Send(Action::left,reinterpret_cast<Address>(hud)); Forward(3,hud);
}
void __fastcall PreviewControls::Right(void* hud,void*) {
    observer.load(std::memory_order_acquire)->Send(Action::right,reinterpret_cast<Address>(hud)); Forward(4,hud);
}
LRESULT CALLBACK PreviewControls::Window(HWND hwnd,UINT message,WPARAM wp,LPARAM lp,UINT_PTR,DWORD_PTR ref) {
    auto& self=*reinterpret_cast<PreviewControls*>(ref);
    if(message==WM_NCDESTROY) { self.Send(Action::cancel,0); self.Retire(); }
    else if(message==WM_KEYDOWN && wp==VK_ESCAPE) { self.Send(Action::cancel,0); }
    else if((message==WM_ACTIVATEAPP && !wp) || message==WM_CANCELMODE || message==WM_KILLFOCUS) { self.Send(Action::suspend,0); }
    return DefSubclassProc(hwnd,message,wp,lp);
}
}
