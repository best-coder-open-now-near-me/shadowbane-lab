#include "furnishing_controls.h"
#undef NDEBUG
#include <cassert>
#include <array>
#include <cstring>
#include <thread>
namespace f=wonderbane::extension::furnishing;
namespace {
unsigned downs=0,ups=0,keys=0; WPARAM moved=0;
std::array<unsigned,6> actions{}; std::array<unsigned,5> forwarded{};
f::Address base=0; constexpr f::Address hud=0x90000,child=0xa0000;
constexpr std::array<f::Address,5> slots{0xe4,0xbc,0x128,0x1f0,0x1f4},methods{0x19a9c,0x1deee,0x1e6c8,0xa245,0xcc1b};
void Action(void*,f::PreviewControls::Action a,f::Address receiver) noexcept {
    assert(!receiver || receiver==hud); ++actions[static_cast<unsigned>(a)];
    if(a==f::PreviewControls::Action::select) { assert(forwarded[0]==1); }
    if(a==f::PreviewControls::Action::drop) { assert(!forwarded[1]); }
}
bool Read(f::Address at,void* out,std::size_t size) noexcept { std::memcpy(out,reinterpret_cast<void*>(at),size); return true; }
void __fastcall Selected(void* r,void*,f::Address a) { assert(reinterpret_cast<f::Address>(r)==hud && a==child); ++forwarded[0]; }
void __fastcall Dropped(void* r,void*,f::Address a) { assert(reinterpret_cast<f::Address>(r)==hud && a==child); ++forwarded[1]; }
void __fastcall Cancelled(void* r,void*) { assert(reinterpret_cast<f::Address>(r)==hud); ++forwarded[2]; }
void __fastcall Left(void* r,void*) { assert(reinterpret_cast<f::Address>(r)==hud); ++forwarded[3]; }
void __fastcall Right(void* r,void*) { assert(reinterpret_cast<f::Address>(r)==hud); ++forwarded[4]; }
f::Address& Slot(unsigned i) { return *reinterpret_cast<f::Address*>(base+0x1167c68+slots[i]); }
void Call(unsigned i) {
    if(i<2) { reinterpret_cast<void(__thiscall*)(void*,f::Address)>(Slot(i))(reinterpret_cast<void*>(hud),child); }
    else { reinterpret_cast<void(__thiscall*)(void*)>(Slot(i))(reinterpret_cast<void*>(hud)); }
}
LRESULT CALLBACK Window(HWND hwnd,UINT m,WPARAM w,LPARAM l) {
    if(m==WM_LBUTTONDOWN) { ++downs; } if(m==WM_LBUTTONUP) { ++ups; }
    if(m==WM_MOUSEMOVE) { moved=w; } if(m==WM_KEYDOWN || m==WM_KEYUP) { ++keys; }
    return DefWindowProcW(hwnd,m,w,l);
}
}
int main() {
    base=reinterpret_cast<f::Address>(VirtualAlloc(nullptr,0x1169000,MEM_COMMIT|MEM_RESERVE,PAGE_EXECUTE_READWRITE)); assert(base);
    const std::array<f::Address,5> targets{reinterpret_cast<f::Address>(&Selected),reinterpret_cast<f::Address>(&Dropped),
        reinterpret_cast<f::Address>(&Cancelled),reinterpret_cast<f::Address>(&Left),reinterpret_cast<f::Address>(&Right)};
    for(unsigned i=0;i<slots.size();++i) {
        Slot(i)=base+methods[i]; auto* thunk=reinterpret_cast<unsigned char*>(base+methods[i]); thunk[0]=0xe9;
        const auto displacement=targets[i]-(base+methods[i]+5); std::memcpy(thunk+1,&displacement,4);
    }
    FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(base),0x1169000);
    WNDCLASSW cls{}; cls.lpfnWndProc=&Window; cls.hInstance=GetModuleHandleW(nullptr); cls.lpszClassName=L"PreviewControlsFixture";
    assert(RegisterClassW(&cls));
    HWND window=CreateWindowW(cls.lpszClassName,L"",WS_OVERLAPPEDWINDOW,0,0,1000,800,nullptr,nullptr,cls.hInstance,nullptr); assert(window);
    f::PreviewControls controls({nullptr,&Action,&Read});
    Slot(3)=1; assert(!controls.Bind(window,base)); Slot(3)=base+methods[3];
    assert(controls.Bind(window,base) && controls.Current());
    assert(!FindWindowExW(window,nullptr,L"WonderBaneFurnishingPreview",nullptr));
    for(unsigned i=0;i<slots.size();++i) { Call(i); assert(forwarded[i]==1); }
    for(unsigned i=0;i<5;++i) { assert(actions[i]==1); }
    SendMessageW(window,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(200,200));
    SendMessageW(window,WM_MOUSEMOVE,MK_LBUTTON,MAKELPARAM(202,202));
    SendMessageW(window,WM_LBUTTONUP,0,MAKELPARAM(200,200)); assert(downs==1 && ups==1 && (moved&MK_LBUTTON));
    SendMessageW(window,WM_KEYDOWN,VK_ESCAPE,0); SendMessageW(window,WM_KEYUP,VK_ESCAPE,0); assert(keys==2 && actions[3]==2);
    const auto saved=actions;
    std::thread foreign([&]{ Call(4); }); foreign.join(); assert(actions==saved && forwarded[4]==2);
    const auto original=Slot(4); Slot(4)=1; assert(!controls.Current()); Slot(4)=original;
    controls.Retire(); assert(!controls.Current()); Call(4); assert(actions==saved && forwarded[4]==3);
    DestroyWindow(window);
    // Native forwarding thunks and observer storage stay live through process exit.
}
