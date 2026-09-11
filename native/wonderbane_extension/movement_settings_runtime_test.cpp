// Production settings admission, stop and actual panel; only OS/native endpoints
// are controlled. No visible window, registry preference or game input mutation.
#define main NativeBackendRegressionMain
#include "movement_native_stop_test.cpp"
#undef main
#include "movement_runtime.cpp"
#include "movement_settings.cpp"
namespace wm = wonderbane::extension::movement;
namespace {
wm::NativeScene observed{};
HWND foreground=nullptr;
bool text_owned=false;
bool __cdecl TextGate(){return text_owned;}
void* __fastcall FocusGate(void*,void*){return nullptr;}
void* __fastcall HitGate(void*,void*,int,int){return nullptr;}
HWND WINAPI Foreground(){return foreground;}
BOOL WINAPI QuietShow(HWND,int){return TRUE;}
BOOL WINAPI QuietForeground(HWND window){foreground=window;return TRUE;}
bool Persist(const wm::Settings&) noexcept{return true;}
void __cdecl OriginalKey(std::uint32_t,std::uint32_t,std::uint32_t,std::uint32_t){}
}
namespace wonderbane::extension {
bool MovementInputTraceEnabled() noexcept { return false; }
void PublishMovementInputTrace(const MovementInputRecord&) noexcept {}
DWORD StartNativeMovementUpdates(const ProcessIdentity&,NativeMovementUpdate) noexcept{return ERROR_SUCCESS;}
void StopNativeMovementUpdates() noexcept{}
namespace movement {
bool NativeMovementLifetimeCurrent(const NativeScene& s) noexcept{return s.epoch && s.epoch==observed.epoch && s.actor==observed.actor && s.world==observed.world && s.window==observed.window && s.parent==observed.parent;}
bool ObserveNativeMovementLifetime(void*,NativeScene& s) noexcept{s=observed;return true;}
bool StartNativeMovementLifetime(HWND) noexcept{return true;}
void RetireNativeMovementLifetime() noexcept{}
struct NativeUiTestAccess {
 static void Bind(NativeUi& ui,std::uintptr_t base,HWND window){
 ui.base_=base;ui.window_=window;ui.thread_=GetCurrentThreadId();ui.bound_=true;
 ui.calls_.text=&TextGate;
 ui.calls_.focused=reinterpret_cast<decltype(ui.calls_.focused)>(&FocusGate);
 ui.calls_.hit=reinterpret_cast<decltype(ui.calls_.hit)>(&HitGate);
 }
};
struct WindowsInputTestAccess {
 static bool Bind(WindowsInput& input,HWND window,std::uint32_t* slot){
 input.platform_.foreground=&Foreground;
 return input.BindVerified(window,slot,&OriginalKey);
 }
};
}}
int main(){
 Fixture f;auto& rt=wm::runtime;
 f.runtime_composition=f.basis_mode=true;
 rt.window=f.window;rt.thread=GetCurrentThreadId();rt.initialized=true;
 FILETIME creation{},end{},kernel{},user{};GetProcessTimes(GetCurrentProcess(),&creation,&end,&kernel,&user);
 rt.process={GetCurrentProcessId(),(std::uint64_t{creation.dwHighDateTime}<<32)|creation.dwLowDateTime};
 wm::NativeStopTestAccess::Bind(rt.native,f.base,f.window);rt.native.EndUpdate();
 observed={reinterpret_cast<std::uintptr_t>(f.actor.data()),0,reinterpret_cast<std::uintptr_t>(f.world.data()),reinterpret_cast<std::uintptr_t>(f.game_window.data()),{17,31},1};
 const auto base=reinterpret_cast<std::uintptr_t>(f.base);
 const auto manager=base+0x1145000, input=base+0x1146000, table=base+0x1147000;
 Put(f.base,0x16a7c00,manager);Put(f.base,0x16ac67c,input);
 Put(reinterpret_cast<void*>(input),0x10,base+0x2112);Put(reinterpret_cast<void*>(input),0x18,base+0x4e0d);
 Put(f.game_window.data(),4,table);Put(reinterpret_cast<void*>(table),0x1c,base+0x25167);
 RECT bounds{};GetClientRect(f.window,&bounds);Put(f.game_window.data(),8,bounds);
 Put(f.base,0x16a2fdc,bounds.right);Put(f.base,0x16a2fe0,bounds.bottom);
 wm::NativeUiTestAccess::Bind(rt.ui,base,f.window);
 std::uint32_t slot=reinterpret_cast<std::uint32_t>(&OriginalKey);
 Check(wm::WindowsInputTestAccess::Bind(rt.input,f.window,&slot),"real input/settings-message hook");
 wm::panel.show=&QuietShow;wm::panel.foreground=&QuietForeground;wm::panel.persist=&Persist;
 rt.Update(f.game_window.data());rt.Update(f.game_window.data());
 const auto message=RegisterWindowMessageW(wm::settings_message_name);
 const auto open=[&]{return SendMessageW(f.window,message,static_cast<WPARAM>(rt.process.creation_filetime_utc),static_cast<LPARAM>(rt.process.creation_filetime_utc>>32));};
 Check(open()==TRUE && wm::panel.window,"external foreground opens actual native panel through registered message");
 Check(foreground==wm::panel.window,"panel becomes selected settings surface");
 Check(open()==TRUE,"reopen while settings panel owns focus");
 const auto previous_revision=rt.revision;wm::panel.Apply();Check(rt.revision==previous_revision+1,"actual panel apply allowed while panel owns focus");
 DestroyWindow(wm::panel.window);foreground=nullptr;text_owned=true;
 Check(open()==FALSE && !wm::panel.window,"native text entry rejects panel opening");
 text_owned=false;Check(open()==TRUE,"return from text ownership recovers");
 if(wm::panel.window)DestroyWindow(wm::panel.window);
 rt.input.Retire();return failures?1:0;
}
