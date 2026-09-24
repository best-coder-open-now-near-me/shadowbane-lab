#include "furnishing_native_calls.h"
#undef NDEBUG
#include <cassert>
#include <cstring>
#include <memory>
#include <thread>

namespace f = wonderbane::extension::furnishing;
using A = f::Address;
namespace {
A image=0,model=0,render=0,clone=0;
bool digest_ok=true,seal_ok=true,reference_ok=true;
unsigned seals=0,kind=0,mode=0,calls=0;
HGLRC context=reinterpret_cast<HGLRC>(1);
HDC dc=nullptr;
A receiver_seen=0,argument_seen=0;
const f::Transform pose{1,2,3,1,0,0,0,1,1,1};
template<class T> void Put(A at,const T& v) { std::memcpy(reinterpret_cast<void*>(at),&v,sizeof(v)); }
void Fault() {
    ++calls;
    if(mode==1) { throw 7; }
    if(mode==2) { RaiseException(EXCEPTION_ACCESS_VIOLATION,0,0,nullptr); }
}
HGLRC WINAPI Context() { return context; }
HDC WINAPI Dc() { return dc; }
void __fastcall Retain(void* receiver,void*,A* slot) { kind=1; receiver_seen=reinterpret_cast<A>(receiver); assert(*slot==model); Fault(); }
void __fastcall Clone(void* receiver,void*,A* slot,bool recursive) { kind=2; receiver_seen=reinterpret_cast<A>(receiver); assert(recursive && !*slot); *slot=clone; Fault(); }
void __fastcall Release(A* slot,void*,void* adopted) { kind=3; assert(!adopted); argument_seen=*slot; *slot=0; Fault(); }
void __fastcall Compose(void* receiver,void*,const f::Transform* t) { kind=4; receiver_seen=reinterpret_cast<A>(receiver); assert(*t==pose); Fault(); }
void __fastcall Enqueue(void* receiver,void*,void* q) { kind=5; receiver_seen=reinterpret_cast<A>(receiver); argument_seen=reinterpret_cast<A>(q); Fault(); }
bool __fastcall Floor(void* receiver,void*,int x,int y,std::array<float,3>* point) {
    kind=7; receiver_seen=reinterpret_cast<A>(receiver); assert(x==123 && y==456); *point={2,3,4}; Fault(); return mode!=3;
}
void __fastcall Erase(void* q,void*,void* n) { kind=6; receiver_seen=reinterpret_cast<A>(q); argument_seen=reinterpret_cast<A>(n); Fault(); }
}
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char* digest) noexcept {
    return digest_ok && std::strcmp(digest,"7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f")==0;
}
namespace movement {
bool VerifyNativeMovementImage(std::uintptr_t& base) noexcept { ++seals; base=image; return seal_ok; }
bool NativeMovementReferenceInterface(void* object,std::uintptr_t& out) noexcept {
    out=reference_ok?reinterpret_cast<std::uintptr_t>(object)+0x718:0; return reference_ok;
}
}
namespace furnishing {
struct NativeCallsTestAccess {
    static void Install(NativeCalls& n) {
        n.calls_.retain=reinterpret_cast<decltype(n.calls_.retain)>(&Retain);
        n.calls_.clone=reinterpret_cast<decltype(n.calls_.clone)>(&::Clone);
        n.calls_.release=reinterpret_cast<decltype(n.calls_.release)>(&::Release);
        n.calls_.compose=reinterpret_cast<decltype(n.calls_.compose)>(&::Compose);
        n.calls_.enqueue=reinterpret_cast<decltype(n.calls_.enqueue)>(&::Enqueue);
        n.calls_.erase=reinterpret_cast<decltype(n.calls_.erase)>(&::Erase);
        n.calls_.floor=reinterpret_cast<decltype(n.calls_.floor)>(&::Floor);
        n.calls_.context=&Context; n.calls_.dc=&Dc;
    }
};
}
}
int main() {
    image=reinterpret_cast<A>(VirtualAlloc(nullptr,0x1700000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE)); assert(image);
    alignas(4) std::array<unsigned char,0x740> m{};
    alignas(4) std::array<unsigned char,0x168> r{},c{};
    model=reinterpret_cast<A>(m.data()); render=reinterpret_cast<A>(r.data()); clone=reinterpret_cast<A>(c.data());
    Put(image+0x114369c+4,A{0x710}); Put(image+0x1149e04+4,A{0x14c});
    Put(image+0x11434cc+8,image+0x26f49); Put(image+0x1149d70+8,image+0x26f49); Put(image+0x1149d70+4,image+0x127ab);
    Put(model,image+0x1143540); Put(model+8,image+0x114369c); Put(model+0x718,image+0x11434cc); Put(model+0x71c,A{1});
    for(A object:{render,clone}) {
        Put(object,image+0x1149dbc); Put(object+8,image+0x1149e04); Put(object+0x154,image+0x1149d70); Put(object+0x158,A{1});
    }
    f::NativeCalls n;
    digest_ok=false; assert(!n.Configure() && !seals); digest_ok=true; seal_ok=false; assert(!n.Configure());
    seal_ok=true; assert(n.Configure() && !n.Configure()); f::NativeCallsTestAccess::Install(n);
    HWND window=CreateWindowExW(0,L"STATIC",L"furnishing ABI test",0,0,0,100,100,nullptr,nullptr,GetModuleHandleW(nullptr),nullptr); assert(window);
    dc=GetDC(window); assert(dc && WindowFromDC(dc)==window);
    assert(n.Bind(window) && !n.Bind(window) && n.Owner());
    A slot=model; assert(n.RetainModel(model,&slot) && receiver_seen==model+0x718 && kind==1);
    slot=0; assert(n.Clone(render,&slot) && slot==clone && receiver_seen==render && kind==2);
    assert(n.Compose(clone,pose) && receiver_seen==clone && kind==4);
    constexpr A queue=0x220000,node=0x230000;
    assert(n.Enqueue(clone,queue) && receiver_seen==clone+0x30 && argument_seen==queue && kind==5);
    assert(n.Erase(queue,node) && receiver_seen==queue && argument_seen==node && kind==6);
    assert(n.Release(&slot) && !slot && argument_seen==clone && kind==3); slot=model; assert(n.Release(&slot) && !slot);
    Put(image+0x1388bf4,A{0x240000}); Put(image+0x12d6de8,A{16}); Put(image+0x1388c08,A{2});
    f::QueueReceipt::Pool pool{}; assert(n.Pool(pool) && pool.begin==0x240000 && pool.capacity==16 && pool.used==2);
    alignas(4) std::array<unsigned char,0x680> h{};
    f::Selection selection{}; selection.hud=reinterpret_cast<A>(h.data()); selection.structure=0x250000; selection.floor=0;
    Put(selection.hud,image+0x1167c68); Put(selection.hud+0x64c,selection.structure); Put(selection.hud+0x628,selection.floor);
    std::array<float,3> point{};
    assert((n.Floor(selection,123,456,point)==f::NativeCalls::FloorResult::hit && point==std::array<float,3>({2,3,4})));
    assert(receiver_seen==selection.hud && kind==7);
    mode=3; assert((n.Floor(selection,123,456,point)==f::NativeCalls::FloorResult::miss && point==std::array<float,3>{})); mode=0;
    const auto prior=calls;
    reference_ok=false; slot=model; assert(!n.RetainModel(model,&slot)); reference_ok=true;
    Put(image+0x1149d70+4,image+0x127ac); slot=0; assert(!n.Clone(render,&slot)); Put(image+0x1149d70+4,image+0x127ab);
    Put(image+0x1149e04+4,A{0x150}); assert(!n.Clone(render,&slot)); Put(image+0x1149e04+4,A{0x14c});
    Put(render+0x158,A{0}); assert(!n.Clone(render,&slot)); Put(render+0x158,A{1});
    assert(!n.Clone(0xffffffff,&slot) && !n.Clone(render,nullptr));
    auto invalid=pose; invalid[3]=0; assert(!n.Compose(clone,invalid));
    context=reinterpret_cast<HGLRC>(2); assert(!n.Owner() && !n.Compose(clone,pose)); context=reinterpret_cast<HGLRC>(1);
    std::thread foreign([&] { assert(!n.Owner() && !n.Compose(clone,pose)); }); foreign.join(); assert(calls==prior);
    for(mode=1;mode<=2;++mode) {
        assert((n.Floor(selection,123,456,point)==f::NativeCalls::FloorResult::fault && point==std::array<float,3>{}));
        slot=model; assert(!n.RetainModel(model,&slot) && slot==model);
        slot=0; assert(!n.Clone(render,&slot) && slot==clone); // publication survives a native fault
        assert(!n.Compose(clone,pose) && !n.Enqueue(clone,queue) && !n.Erase(queue,node));
        assert(!n.Release(&slot) && slot==0); // consumed before fault; callers must not retry
    }
    mode=0; ReleaseDC(window,dc); DestroyWindow(window); assert(!n.Owner());
    VirtualFree(reinterpret_cast<void*>(image),0,MEM_RELEASE); return 0;
}
