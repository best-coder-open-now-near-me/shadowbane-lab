#include "controls.h"
#include "status.h"
#include "parent_frame.h"
#include "scene.h"
#include <commctrl.h>
#include <cmath>
namespace steam_wasd {
namespace {
using Ptr = std::uintptr_t;
template<class T> T& at(Ptr p) { return *reinterpret_cast<T*>(p); }
template<class F> F call(Ptr rva) { return reinterpret_cast<F>(reinterpret_cast<Ptr>(GetModuleHandleW(nullptr)) + rva); }
Ptr base{};
HWND hwnd{};
DWORD thread{};
UINT command{};
Shared* shared{};
Shared stats{};
Controls controls{};
bool executing{}, enabled{}, faulted{}, subclassed{};
unsigned captured{}, char_keys{};
LONG initialized{};
using Update = void(*)(void*, double);
Update original{};
using Vec = NativePoint;
struct Ground { Vec point; unsigned pad{}; void* actor{}; void* parent{}; };
static_assert(sizeof(Ground)==32);
Scene owner{};
Scene observed{};
bool have_scene{};
void* retained{};
void* conversion_parent{};
void* message{};
ULONGLONG last_move{};
Direction last_direction{};

template<class T> T global(Ptr rva) { return at<T>(base+rva); }
Vec position(Ptr actor) { return at<Vec>(at<Ptr>(at<Ptr>(actor+0x668))+0x60); }
Ptr parent(Ptr actor) { return at<Ptr>(at<Ptr>(at<Ptr>(actor+0x668))+0x10); }
bool finite(Vec p) { return std::isfinite(p.x)&&std::isfinite(p.y)&&std::isfinite(p.z); }
bool capture(Scene& s) {
    s.actor=global<Ptr>(profile::actor); s.window=global<Ptr>(profile::window); s.world=global<Ptr>(profile::world);
    if (!s.actor || !s.window || !s.world || at<Ptr>(s.actor)!=base+profile::actor_vtable
        || at<Ptr>(s.window)!=base+profile::window_vtable || at<unsigned>(s.window+0xb8)!=2) return false;
    s.id=at<std::uint64_t>(s.actor+0x18); s.parent=parent(s.actor);
    return s.id && finite(position(s.actor));
}
bool current() { Scene s; return capture(s) && same(s,owner); }
void release_owner() {
    call<void**(*)(void**,void*)>(profile::actor_ref)(&retained,nullptr);
    owner={}; last_move=0;
}
void release_message() {
    void* p=message; message=nullptr;
    if (p && p!=reinterpret_cast<void*>(~Ptr{}))
        reinterpret_cast<void(*)(void*,void**)>(at<Ptr>(at<Ptr>(reinterpret_cast<Ptr>(p))+16))(p,&message);
}
void send_message() {
    if (!message) return;
    auto* connection=call<void*(*)()>(profile::connection)();
    if (!connection || !current()) { release_message(); return; }
    // Native send consumes this exact owned reference, including failure paths.
    call<void(*)(void*,void**)>(profile::send)(connection,&message);
    ++stats.messages;
}
struct Node { Node *left,*parent,*right; unsigned char color,nil; unsigned char pad[6]; std::uint64_t key; double when; unsigned action; };
struct Map { Node* head; std::uint64_t size; };
static_assert(sizeof(Node)==56);
Node* find(Map& map, std::uint64_t id) {
    if (!map.head || !map.head->nil || map.size>1000000) throw 1;
    Node* n=map.head->parent;
    for (unsigned depth=0; depth<64; ++depth) {
        if (!n) throw 1;
        if (n->nil) { if(n!=map.head) throw 1; return nullptr; }
        if (id==n->key) return n;
        n=id<n->key ? n->left:n->right;
    }
    throw 1;
}
bool cancel() {
    if (!current()) return false;
    at<unsigned short>(owner.actor+0x1130)=0;
    at<unsigned short>(owner.window+0x269)=0;
    call<void(*)(void*,const std::uint64_t*)>(profile::clear_actions)(reinterpret_cast<void*>(owner.world),&owner.id);
    if (!current()) return false;
    auto& map=at<Map>(owner.world+0x1a0);
    if (Node* node=find(map,owner.id)) {
        auto* detached=call<Node*(*)(Map*,Node*)>(profile::detach)(&map,node);
        if (detached!=node) throw 1;
        call<void(*)(void*,size_t)>(profile::free_node)(detached,sizeof(Node));
    }
    if (!current()) return false;
    Ptr begin=at<Ptr>(owner.actor+0x1118), end=at<Ptr>(owner.actor+0x1120), capacity=at<Ptr>(owner.actor+0x1128);
    if (end<begin || capacity<end || end-begin>24*100000 || (end-begin)%24) throw 1;
    if (begin!=end) {
        call<void(*)(void*,void*)>(profile::erase_path)(reinterpret_cast<void*>(begin),reinterpret_cast<void*>(end));
        if (!current() || at<Ptr>(owner.actor+0x1118)!=begin) return false;
        at<Ptr>(owner.actor+0x1120)=begin;
    }
    at<unsigned char>(owner.actor+0x1132)=0;
    Ptr request=global<Ptr>(profile::request);
    if (request && at<unsigned>(request)==0) { at<unsigned char>(request+4)=0; at<unsigned>(request)=1; }
    return current() && !find(at<Map>(owner.world+0x1a0),owner.id)
        && !find(at<Map>(owner.world+0x148),owner.id) && !at<Ptr>(owner.actor+0xf78);
}
bool refresh_owner(const Scene& scene) {
    const auto result=rebase(owner,scene);
    if(result==Rebase::retired) return false;
    if(result==Rebase::parent_changed) {++stats.scene_changes;last_move=0;}
    return true;
}
void stop() {
    if (!retained) return;
    Scene scene;
    // A doorway can change the frame before key-up is dispatched. Stop the same
    // owned actor in its new frame; never transfer ownership to another actor.
    if (!capture(scene) || !refresh_owner(scene)) { ++stats.scene_changes; release_owner(); return; }
    if (!cancel()) throw 1;
    Vec p=position(owner.actor);
    call<void(*)(void*,const Vec*)>(profile::destination)(retained,&p);
    if (!current()) { release_owner(); return; }
    const int state=call<int(*)(void*)>(profile::get_state)(retained);
    if (state==7) {
        call<void**(*)(void*,void**,bool,unsigned,bool)>(profile::state)(retained,&message,true,5,true);
        if (!current()) { release_message(); release_owner(); return; }
    }
    if (!cancel()) throw 1;
    at<unsigned char>(owner.actor+0xb18)=0;
    at<unsigned short>(owner.window+0x269)=0;
    send_message(); ++stats.stops;
    release_owner();
}
unsigned key_bit(WPARAM key) {
    switch(key) { case 'W': return w; case 'A': return a; case 'S': return s; case 'D': return d; default:return 0; }
}
unsigned physical_keys() { unsigned keys=0; for (auto k : {'W','A','S','D'}) if(GetAsyncKeyState(k)&0x8000) keys|=key_bit(k); return keys; }
bool modified() { return (GetAsyncKeyState(VK_CONTROL)|GetAsyncKeyState(VK_MENU)|GetAsyncKeyState(VK_SHIFT)|GetAsyncKeyState(VK_LWIN)|GetAsyncKeyState(VK_RWIN))&0x8000; }
unsigned gate(const Scene& scene) {
    if (!enabled) return 1;
    if (GetForegroundWindow()!=hwnd || IsIconic(hwnd)) return 2;
    if (global<Ptr>(profile::modal) || !at<unsigned char>(scene.window+0xc9)) return 4;
    Ptr input=global<Ptr>(profile::input);
    if (!input || at<unsigned>(input+0x44)!=0 || modified()) return 5;
    if (call<bool(*)()>(profile::text_input)()) return 6;
    auto* focus=call<void*(*)(void*)>(profile::focus)(reinterpret_cast<void*>(scene.window));
    if (focus) { auto kind=at<unsigned>(reinterpret_cast<Ptr>(focus)+0x698); if(kind==5||kind==6||kind==14) return 6; }
    auto state=call<int(*)(void*)>(profile::get_state)(reinterpret_cast<void*>(scene.actor));
    if (state!=5 && state!=7) return 7;
    if (call<bool(*)(void*)>(profile::inhibited)(reinterpret_cast<void*>(at<Ptr>(scene.window+0x118)))) return 7;
    return 0;
}
void publish() {
    stats.enabled=enabled; stats.moving=retained!=nullptr; stats.fault=faulted;
    stats.tick=GetTickCount64();
    InterlockedIncrement(&shared->sequence);
    std::memcpy(reinterpret_cast<char*>(shared)+sizeof(LONG),reinterpret_cast<char*>(&stats)+sizeof(LONG),sizeof(Shared)-sizeof(LONG));
    MemoryBarrier(); InterlockedIncrement(&shared->sequence);
}
void fail() { faulted=true; enabled=false; controls.block(); stats.gate=9; publish(); }
void steer(const Scene& scene,Direction vector) {
    if (!retained) {
        owner=scene;
        call<void**(*)(void**,void*)>(profile::actor_ref)(&retained,reinterpret_cast<void*>(scene.actor));
        if (!current() || !cancel()) throw 1;
    }
    const ULONGLONG now=GetTickCount64();
    const float delta=std::hypot(vector.x-last_direction.x,vector.z-last_direction.z);
    if (last_move && now-last_move<150 && delta<0.04F) return;
    if (!current() || gate(owner)) return;
    Ground target{}; target.point=position(owner.actor);
    target.point.x+=vector.x*10; target.point.z+=vector.z*10;
    // Continuous native movement keeps collision, speed, and server publication.
    call<void**(*)(void*,void**,Ground*,bool,bool,bool,void*,bool)>(profile::move)(retained,&message,&target,true,true,false,nullptr,false);
    if (!current()) { release_message(); release_owner(); controls.block(); return; }
    send_message(); ++stats.moves; last_move=now; last_direction=vector;
}
CameraBasis local_camera(const Scene& scene,CameraBasis basis) {
    if(!scene.parent || !basis.valid) return basis;
    call<void**(*)(void**,void*)>(profile::actor_ref)(&conversion_parent,reinterpret_cast<void*>(scene.parent));
    Scene check;
    if(!capture(check) || !same(check,scene)) {
        call<void**(*)(void**,void*)>(profile::actor_ref)(&conversion_parent,nullptr);return {};
    }
    // Follow the native screen-ray conversion's virtual-base adjustment. This
    // getter returns the parent's composed world transform, including ancestors.
    const Ptr vb=at<Ptr>(scene.parent+8);
    const Ptr iface=scene.parent+8+at<std::int32_t>(vb+0x10);
    const Ptr getter=at<Ptr>(at<Ptr>(iface)+8);
    if(getter<base+0x1000 || getter>=base+0xd71000) throw 1;
    const auto* transform=reinterpret_cast<const ParentTransform*(*)(void*)>(getter)(reinterpret_cast<void*>(iface));
    const ParentTransform copy=*transform;
    call<void**(*)(void**,void*)>(profile::actor_ref)(&conversion_parent,nullptr);
    if(!capture(check) || !same(check,scene)) return {};
    return parent_basis(basis,copy,call<InvertTransform>(profile::invert_transform),call<ApplyTransform>(profile::apply_transform));
}
void tick() {
    ++stats.frames;
    Scene scene;
    if (!capture(scene)) {
        controls.sample(physical_keys(),{},false,false); stats.gate=8; have_scene=false;
        if(retained) { ++stats.scene_changes; release_owner(); }
        publish(); return;
    }
    bool same_scene=have_scene && same_identity(scene,observed) && (!retained || same_identity(scene,owner));
    if(same_scene && retained && scene.parent!=owner.parent) {
        // Retire the previous frame's pending route, then compute a fresh local
        // destination this tick. Held keys remain armed across this same-actor hop.
        if(!refresh_owner(scene) || !cancel()) throw 1;
    }
    observed=scene; have_scene=true;
    stats.keys=physical_keys(); stats.gate=gate(scene);
    const auto eye=global<Vec>(profile::camera_eye);
    const auto basis=camera_basis(global<CameraMatrix>(profile::camera_matrix),{eye.x,eye.y,eye.z});
    stats.yaw=basis.valid ? std::atan2(basis.forward.x,-basis.forward.z):0;
    if(!basis.valid && !stats.gate) stats.gate=10;
    const auto local=local_camera(scene,basis);
    if(basis.valid && !local.valid && !stats.gate) stats.gate=3;
    auto result=controls.sample(stats.keys,local,stats.gate==0,same_scene);
    if (!same_scene && retained) { ++stats.scene_changes; release_owner(); }
    if (result.stop) stop();
    if (result.steer) steer(scene,result.vector);
    if (capture(scene)) {
        auto p=position(scene.actor); stats.x=p.x; stats.y=p.y; stats.z=p.z;
        stats.state=static_cast<DWORD>(call<int(*)(void*)>(profile::get_state)(reinterpret_cast<void*>(scene.actor)));
    }
    publish();
}
void guarded_tick_cxx() { try { tick(); } catch (...) { fail(); } }
void guarded_tick() { __try { guarded_tick_cxx(); } __except(EXCEPTION_EXECUTE_HANDLER) { fail(); } }
void interrupt_cxx() { try { controls.block(); if(retained) stop(); controls.moving=false; } catch(...) { fail(); } }
void interrupt() { __try { interrupt_cxx(); } __except(EXCEPTION_EXECUTE_HANDLER) { fail(); } }
bool can_capture_cxx() { try { Scene scene; return !faulted && controls.armed && capture(scene) && gate(scene)==0; } catch(...) { return false; } }
bool can_capture() { __try { return can_capture_cxx(); } __except(EXCEPTION_EXECUTE_HANDLER) { return false; } }
LRESULT CALLBACK procedure(HWND window,UINT msg,WPARAM wp,LPARAM lp,UINT_PTR,DWORD_PTR) {
    if (GetCurrentThreadId()!=thread) return DefSubclassProc(window,msg,wp,lp);
    if (!executing) {
        executing=true;
        if (msg==command) { if(wp==1 && !faulted) enabled=true; else if(wp==0) enabled=false; interrupt(); publish(); }
        if (msg==WM_KILLFOCUS || msg==WM_CANCELMODE || msg==WM_ACTIVATEAPP && !wp || msg==WM_NCDESTROY
            || msg==WM_LBUTTONDOWN || msg==WM_RBUTTONDOWN || msg==WM_MBUTTONDOWN) interrupt();
        if ((msg==WM_KEYDOWN || msg==WM_SYSKEYDOWN) && wp==VK_F10 && (GetKeyState(VK_CONTROL)&0x8000) && (GetKeyState(VK_MENU)&0x8000) && !(lp&(1LL<<30))) {
            enabled=!enabled&&!faulted; interrupt(); publish(); executing=false; return 0;
        }
        if ((msg==WM_KEYDOWN || msg==WM_SYSKEYDOWN) && (wp==VK_RETURN || wp==VK_ESCAPE || wp==VK_TAB)) interrupt();
        if (msg==WM_KEYDOWN || msg==WM_SYSKEYDOWN) {
            unsigned bit=key_bit(wp);
            if (bit && ((captured&bit) || can_capture())) { captured|=bit; char_keys|=bit; executing=false; return 0; }
        }
        if (msg==WM_CHAR || msg==WM_SYSCHAR) {
            unsigned bit=key_bit(wp>='a'&&wp<='z' ? wp-32:wp);
            if (bit && (char_keys&bit)) { executing=false; return 0; }
        }
        if (msg==WM_KEYUP || msg==WM_SYSKEYUP) {
            unsigned bit=key_bit(wp); char_keys&=~bit;
            if (bit && (captured&bit)) { captured&=~bit; executing=false; return 0; }
        }
        if (msg==WM_NCDESTROY) { RemoveWindowSubclass(window,procedure,1); subclassed=false; enabled=false; }
        executing=false;
    }
    return DefSubclassProc(window,msg,wp,lp);
}
void update(void* self,double dt) {
    if (GetCurrentThreadId()==thread && !executing && !faulted
        && reinterpret_cast<Ptr>(self)==global<Ptr>(profile::window)+8) {
        if (!subclassed) {
            subclassed=SetWindowSubclass(hwnd,procedure,1,0)!=FALSE;
            stats.hooked=subclassed;
            if (!subclassed) fail();
        }
        if (subclassed) { executing=true; guarded_tick(); executing=false; }
    }
    original(self,dt);
}
BOOL CALLBACK find_window(HWND window,LPARAM) {
    DWORD pid{}; auto tid=GetWindowThreadProcessId(window,&pid);
    if(pid==GetCurrentProcessId() && IsWindowVisible(window) && GetWindow(window,GW_OWNER)==nullptr) { hwnd=window; thread=tid; return FALSE; }
    return TRUE;
}
DWORD initialize() {
    if (InterlockedCompareExchange(&initialized,1,0)!=0) return shared && !faulted ? 0:1;
    base=reinterpret_cast<Ptr>(GetModuleHandleW(nullptr));
    if(!verified_loaded_image(base)) return 2;
    EnumWindows(find_window,0); if(!hwnd) return 3;
    command=RegisterWindowMessageW(command_name); if(!command) return 4;
    HANDLE mapping=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(Shared),mapping_name(GetCurrentProcessId()).c_str());
    if(!mapping || GetLastError()==ERROR_ALREADY_EXISTS) { if(mapping) CloseHandle(mapping); return 5; }
    shared=static_cast<Shared*>(MapViewOfFile(mapping,FILE_MAP_WRITE,0,0,sizeof(Shared)));
    if(!shared) { CloseHandle(mapping); return 6; }
    // Mapping handle and module remain pinned until process exit: callbacks must
    // never execute unloaded code, including while the add-on is disabled.
    HMODULE pinned{};
    if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,reinterpret_cast<LPCWSTR>(&initialize),&pinned)) return 7;
    wchar_t module_path[32768]{};
    if(!GetModuleFileNameW(pinned,module_path,32768)) return 10;
    const auto digest=hash(read_file(module_path));
    if(digest.size()!=64) return 11;
    std::memcpy(stats.dll_hash,digest.c_str(),65);
    stats.version=schema; stats.pid=GetCurrentProcessId(); stats.creation=creation_time(GetCurrentProcess());
    stats.gate=1; enabled=false; publish();
    auto* slot=reinterpret_cast<void**>(base+profile::update_slot);
    original=reinterpret_cast<Update>(base+profile::update);
    DWORD protection{};
    if(!VirtualProtect(slot,sizeof(void*),PAGE_READWRITE,&protection)) return 8;
    auto before=InterlockedCompareExchangePointer(slot,reinterpret_cast<void*>(&update),reinterpret_cast<void*>(original));
    DWORD ignored{}; const bool restored=VirtualProtect(slot,sizeof(void*),protection,&ignored)!=FALSE;
    if(before!=reinterpret_cast<void*>(original) || !restored) { fail(); return 9; }
    return 0;
}
}
}
extern "C" __declspec(dllexport) DWORD WINAPI SteamWasdInitialize(void*) {
    try { return steam_wasd::initialize(); } catch(...) { return 10; }
}
BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(module);
    return TRUE;
}
