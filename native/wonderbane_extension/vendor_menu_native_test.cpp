#include "vendor_menu_native.h"
#undef NDEBUG
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include <initializer_list>
namespace n = wonderbane::extension::vendor_menu;
namespace m = wonderbane::extension::movement;
using V = n::wire::Verb; using O = n::wire::Outcome;
bool live = true;
namespace wonderbane::extension::movement {
bool NativeMovementLifetimeCurrent(const NativeScene& s) noexcept { return live && s.epoch == 1; }
}
std::uint32_t base = 0, data_at = 0, text_at = 0;
m::NativeScene scene{}; n::wire::Command command{};
unsigned calls = 0, selects = 0, activates = 0, scrolls = 0, admissions = 0;
unsigned deny_at = 0, mutate_at = 0;
bool detach_select = false, revoke_select = false, stale_select = false, reenter = false, detach_scroll = false;
O nested = O::invalid;
constexpr std::uint32_t ROOT=0x1000, MANAGER=0x2000, MENU=0x3000, HIRE=0x4000,
 PROD=0x5000, PROW=0x6000, PENTRY=0x7000, RECIPE=0x8000, PAGES=0x9000,
 PANEL=0xa000, BORDER=0xb000, LIST=0xc000, ROW1=0xd000, ROW2=0xe000,
 ENTRY1=0xf000, ENTRY2=0x10000, TEMPLATE1=0x11000, TEMPLATE2=0x12000,
 OPEN=0x13000, VIEW=0x14000, CANCEL=0x15000, MAGIC=0x16000, INVENTORY=0x17000,
 ICANCEL=0x18000, WRAPPER=0x19000, TAB=0x1a000, HEAD=0x1b000, ILIST=0x1c000, ICANCEL2=0x1d000;
std::uint32_t P(std::uint32_t off) { return base + off; }
void Put(std::uint32_t off, std::uint32_t value) { std::memcpy(reinterpret_cast<void*>(P(off)), &value, 4); }
std::uint32_t Word(std::uint32_t off) { std::uint32_t v; std::memcpy(&v, reinterpret_cast<void*>(P(off)), 4); return v; }
void Vector(std::uint32_t off, std::initializer_list<std::uint32_t> values) {
    Put(off,P(data_at)); unsigned n=0;
    for(auto v:values) { Put(data_at+n*4,P(v)); ++n; }
    Put(off+4,P(data_at+n*4)); Put(off+8,P(data_at+n*4)); data_at+=0x100;
}
void Name(std::uint32_t off,const wchar_t* name) {
    const auto bytes=static_cast<std::uint32_t>(std::wcslen(name)*2);
    std::memcpy(reinterpret_cast<void*>(P(text_at)),name,bytes);
    Put(off+0x168,P(text_at)); Put(off+0x16c,P(text_at+bytes)); Put(off+0x170,P(text_at+bytes)); text_at+=0x100;
}
void Control(std::uint32_t off,std::uint32_t cls,std::uint32_t owner,const wchar_t* name=L"") {
    Put(off,P(cls)); Put(off+0x3bc,P(owner)); Name(off,name);
}
void Huds(std::initializer_list<std::uint32_t> huds) {
    auto at=HEAD+0x100,prev=HEAD; Put(HEAD,huds.size()?P(at):P(HEAD));
    for(auto hud:huds) { Put(prev,P(at)); Put(at+4,P(prev)); Put(at+8,P(hud)); prev=at; at+=0x100; }
    Put(prev,P(HEAD)); Put(HEAD+4,P(prev));
}
bool Admit(void*) noexcept {
    ++admissions;
    if(mutate_at==admissions) Put(OPEN+0x3bc,0);
    return live && (!deny_at || deny_at!=admissions);
}
void __fastcall Select(void* self,void*,void* row) {
    assert(reinterpret_cast<std::uint32_t>(self)==P(LIST)); ++selects;
    Put(LIST+0x404,reinterpret_cast<std::uint32_t>(row));
    if(detach_select) Put(ROW2+0xe8,0);
    if(revoke_select) live=false;
    if(stale_select) Put(RECIPE+0x47c,77);
}
bool __fastcall Activate(void* self,void*,std::uint32_t event) {
    assert(reinterpret_cast<std::uint32_t>(self)==P(ROW2) && event==0); ++activates;
    Put(RECIPE+0x45c,P(ENTRY2)); Put(RECIPE+0x408,P(TEMPLATE2)); Put(RECIPE+0x47c,16);
    return true;
}
void __fastcall Scroll(void* self,void*,std::uint32_t index) {
    assert(reinterpret_cast<std::uint32_t>(self)==P(LIST) && index==1); ++scrolls;
    Put(LIST+0x418,1); Put(ROW2+0x304,0);
    if(detach_scroll) Put(ROW2+0x3bc,0);
}
bool __fastcall Button(void* self,void*,std::uint32_t event,std::uint32_t flag) {
    assert(event==0 && flag==1); ++calls;
    if(reenter) nested=n::Invoke(base,scene,V::open_recipe,command,&Admit,nullptr);
    const auto p=reinterpret_cast<std::uint32_t>(self);
    if(p==P(OPEN)) Huds({RECIPE,MENU});
    else if(p==P(VIEW)) { Put(MANAGER+0x7c,P(INVENTORY)); Put(MANAGER+0x58,1); Huds({INVENTORY,MENU}); }
    else if(p==P(CANCEL)||p==P(ICANCEL)) Huds({MENU});
    else { assert(p==P(MAGIC)); Put(RECIPE+0x404,1); Put(RECIPE+0x40c,3362971591U); Put(RECIPE+0x434,3362971591U); }
    return false; // Generic handler return is not action completion.
}
void Jump(std::uint32_t off,std::uintptr_t target) {
    auto* p=reinterpret_cast<unsigned char*>(P(off)); p[0]=0xb8; Put(off+1,static_cast<std::uint32_t>(target)); p[5]=0xff; p[6]=0xe0;
    assert(FlushInstructionCache(GetCurrentProcess(),p,7));
}
void Reset(bool recipe=true) {
    std::memset(reinterpret_cast<void*>(P(0x1000)),0,0x50000);
    data_at=0x30000; text_at=0x40000; live=true; calls=selects=activates=scrolls=admissions=0;
    deny_at=mutate_at=0; detach_select=revoke_select=stale_select=reenter=detach_scroll=false; nested=O::invalid;
    Put(0x16a7bfc,P(ROOT)); Put(ROOT,P(0x1174884)); Put(ROOT+0x64,2); Put(ROOT+0xa4,P(MANAGER)); Put(ROOT+0x20,P(HEAD));
    Put(MANAGER,P(0x1171adc)); Put(MANAGER+0x78,P(MENU)); Put(MANAGER+0xf0,123); Put(MANAGER+0xf4,8); Put(MANAGER+0xf8,123); Put(MANAGER+0xfc,8); Put(MANAGER+0x384,P(HIRE));
    Put(HIRE,P(0x1169518)); Put(HIRE+0x10,777); Put(HIRE+0x14,42);
    Put(MENU,P(0x116a058)); Put(MENU+0x104,P(MANAGER));
    Control(PROD,0x116acf0,MENU); Control(PROW,0x116aebc,MENU); Put(PROW+0x458,P(PROD)); Put(PROW+0x44c,P(PENTRY)); Put(PENTRY,P(0x1169560));
    Vector(MENU+0x54,{PROD,OPEN,VIEW}); Vector(PROD+0x408,{PROW});
    Control(OPEN,0x1169ec0,MENU,L"BTNCREATEITEM"); Put(OPEN+0x1d0,0x5a1);
    Control(VIEW,0x1169ec0,MENU,L"BTNVIEW"); Put(VIEW+0x1d0,0x58c);
    Put(RECIPE,P(0x116bf7c)); Put(RECIPE+0x104,P(MANAGER)); Put(RECIPE+0x3b8,P(MANAGER)); Put(RECIPE+0x3c0,777); Put(RECIPE+0x3c4,42);
    Put(RECIPE+0x400,3362971591U); Put(RECIPE+0x408,P(TEMPLATE1)); Put(RECIPE+0x45c,P(ENTRY1)); Put(RECIPE+0x47c,12); Put(RECIPE+0x4d4,1);
    Put(RECIPE+0x518,P(PAGES)); Put(RECIPE+0x520,P(LIST));
    Vector(RECIPE+0x54,{PAGES,CANCEL}); Control(CANCEL,0x1169ec0,RECIPE,L"CANCEL"); Put(CANCEL+0x1d0,50);
    Control(PAGES,0x116b510,RECIPE,L"ItemCreationPages"); Vector(PAGES+0x400,{TAB}); Put(TAB+4,P(PANEL)); Put(TAB+0x50,P(WRAPPER));
    Put(WRAPPER,P(0x116c2c0)); Put(WRAPPER+4,P(RECIPE)); Put(WRAPPER+8,P(0x238ad));
    Control(PANEL,0x1169ec0,RECIPE); Control(BORDER,0x11657c8,RECIPE);
    Put(PANEL+0xe8,P(PAGES)); Put(BORDER+0xe8,P(PANEL)); Vector(PANEL+0x40,{BORDER}); Vector(BORDER+0x40,{LIST,MAGIC});
    Control(MAGIC,0x1169ec0,RECIPE,L"MAGIC"); Put(MAGIC+0xe8,P(BORDER)); Put(MAGIC+0x1d0,0x71d);
    Control(LIST,0x116acf0,RECIPE,L"ITEMLIST"); Put(LIST+0xe8,P(BORDER)); Put(LIST+0x404,P(ROW1)); Vector(LIST+0x408,{ROW1,ROW2});
    Put(LIST+0x414,1); Put(LIST+0x41c,1); Put(LIST+0x420,20);
    for(auto row:{ROW1,ROW2}) { Control(row,0x116aebc,RECIPE); Put(row+0x458,P(LIST)); Put(row+0xe8,P(LIST)); }
    Put(ROW1+0x44c,P(ENTRY1)); Put(ROW2+0x44c,P(ENTRY2)); Put(ROW2+0x420,1);
    Put(ENTRY1,P(0x116c2d0)); Put(ENTRY1+0x10,26990); Put(ENTRY2,P(0x116c2d0)); Put(ENTRY2+0x10,5051080);
    Put(TEMPLATE1,P(0x1142748)); Put(TEMPLATE1+0x10,26990); Put(TEMPLATE2,P(0x1142748)); Put(TEMPLATE2+0x10,5051080);
    Put(INVENTORY,P(0x116c64c)); Put(INVENTORY+0x104,P(MANAGER)); Put(INVENTORY+0x3f4,P(MANAGER));
    Vector(INVENTORY+0x54,{ICANCEL,ILIST}); Control(ICANCEL,0x1169ec0,INVENTORY); Put(ICANCEL+0x1d0,50);
    Control(ILIST,0x116acf0,INVENTORY); Put(INVENTORY+0x3f0,P(ILIST));
    if(recipe) Huds({RECIPE,MENU}); else Huds({MENU});
    scene={}; scene.epoch=1; scene.window=P(ROOT);
}
void Prepare(std::uint32_t wanted=0) {
    command={}; command.host={1,1,1}; command.window=1; command.request[0]=1; command.item_template=wanted;
    assert(n::Capture(base,scene,command.expected)); command.expected.revision=1;
}
O Invoke(V verb) { return n::Invoke(base,scene,verb,command,&Admit,nullptr); }
int main() {
    auto* memory=VirtualAlloc(nullptr,0x1800000,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE);
    assert(memory); base=reinterpret_cast<std::uint32_t>(memory);
    Jump(0x5f5440,reinterpret_cast<std::uintptr_t>(&Button)); Jump(0x613520,reinterpret_cast<std::uintptr_t>(&Select));
    Jump(0x61c7f0,reinterpret_cast<std::uintptr_t>(&Activate)); Jump(0x612660,reinterpret_cast<std::uintptr_t>(&Scroll));
    Reset(false); Prepare(); assert(!command.expected.recipe && !command.expected.item_template && !command.expected.recipe_list);
    assert(Invoke(V::open_recipe)==O::submitted && calls==1); Prepare(); assert(Invoke(V::open_recipe)==O::observed && calls==1);
    Reset(false); Prepare(); reenter=true; assert(Invoke(V::open_recipe)==O::submitted && nested==O::unavailable && calls==1);
    Reset(false); Prepare(); deny_at=2; assert(Invoke(V::open_recipe)==O::stale && !calls);
    Reset(false); Prepare(); mutate_at=2; assert(Invoke(V::open_recipe)==O::stale && !calls);
    for(auto off:{OPEN+0x1a8,OPEN+0x304,OPEN+0xe8,OPEN+0x1d4}) {
        Reset(false); Prepare(); Put(off,off==OPEN+0x304?0x100U:1U); assert(Invoke(V::open_recipe)!=O::submitted && !calls);
    }
    Reset(false); Prepare(); Put(OPEN+0x1d0,0x5a2); assert(Invoke(V::open_recipe)==O::unavailable && !calls);
    Reset(); Prepare(5051080); assert(Invoke(V::select_recipe)==O::submitted && selects==1 && activates==1);
    Prepare(5051080); assert(Invoke(V::select_recipe)==O::observed && selects==1);
    Reset(); Put(ROW2+0x304,0x100); Prepare(5051080); assert(Invoke(V::select_recipe)==O::submitted && scrolls==1 && activates==1);
    Reset(); Put(ROW2+0x304,0x100); Prepare(5051080); detach_scroll=true; assert(Invoke(V::select_recipe)==O::uncertain && scrolls==1 && !selects && !activates);
    for(unsigned mode=0;mode<3;++mode) {
        Reset(); Prepare(5051080); detach_select=mode==0; revoke_select=mode==1; stale_select=mode==2;
        assert(Invoke(V::select_recipe)==O::uncertain && selects==1 && !activates);
    }
    for(auto off:{ROW2+0xe8,ROW2+0x1a8,ROW2+0x1d0,ROW2+0x458,ROW2+0x3bc}) {
        Reset(); Prepare(5051080); Put(off,1); assert(Invoke(V::select_recipe)!=O::submitted && !selects && !activates);
    }
    Reset(); Prepare(5051080); Put(BORDER+0xe8,P(BORDER)); assert(Invoke(V::select_recipe)==O::stale && !selects);
    Reset(); Prepare(5051080); Put(PAGES+0x40c,1); assert(Invoke(V::select_recipe)==O::stale && !selects);
    Reset(); Prepare(5051080); Put(RECIPE+0x408,P(TEMPLATE2)); assert(Invoke(V::select_recipe)==O::stale && !selects);
    Reset(); Prepare(5051080); Put(ROW2+0x1e0,P(0x45000)); Put(ROW2+0x1e4,P(0x45002)); Put(ROW2+0x1e8,P(0x45002)); assert(Invoke(V::select_recipe)==O::stale && !selects);
    Reset(); Prepare(); assert(Invoke(V::random_mode)==O::submitted && calls==1); Prepare(); assert(Invoke(V::random_mode)==O::observed && calls==1);
    Reset(); Prepare(); Put(MAGIC+0xe8,0); assert(Invoke(V::random_mode)==O::unavailable && !calls);
    for(auto ancestor:{BORDER,PANEL,PAGES,LIST}) {
        for(auto field:{0x1a8U,0x304U}) {
            Reset(); Prepare(5051080); Put(ancestor+field,field==0x304?0x100U:1U);
            assert(Invoke(V::select_recipe)!=O::submitted && !selects && !activates && !scrolls);
            if(ancestor!=LIST) {
                Reset(); Prepare(); Put(ancestor+field,field==0x304?0x100U:1U);
                assert(Invoke(V::random_mode)!=O::submitted && !calls);
            }
        }
    }
    Reset(); Prepare(); assert(Invoke(V::close_recipe)==O::submitted); Prepare(); assert(!command.expected.recipe && Invoke(V::close_recipe)==O::observed);
    Reset(false); Prepare(); assert(Invoke(V::open_inventory)==O::submitted); Prepare(); assert(command.expected.inventory && Invoke(V::close_inventory)==O::submitted);
    Reset(false); Put(MANAGER+0x7c,P(INVENTORY)); Put(MANAGER+0x58,1); Huds({INVENTORY,MENU}); Prepare(); Put(ICANCEL+0x1d0,0x50); assert(Invoke(V::close_inventory)==O::unavailable && !calls);
    for(unsigned fault=0;fault<10;++fault) {
        Reset(false); Put(MANAGER+0x7c,P(INVENTORY)); Put(MANAGER+0x58,1); Huds({INVENTORY,MENU}); Prepare();
        switch(fault) {
        case 0: Name(ICANCEL,L"CANCEL"); break; // Not this client's observed Inventory binding.
        case 1: Control(ICANCEL2,0x1169ec0,INVENTORY); Put(ICANCEL2+0x1d0,50); Vector(INVENTORY+0x54,{ICANCEL,ILIST,ICANCEL2}); break;
        case 2: Put(ICANCEL+0xe8,P(PANEL)); break;
        case 3: Put(ICANCEL+0x1a8,1); break;
        case 4: Put(ICANCEL+0x304,0x100); break;
        case 5: Put(ICANCEL+0x1d4,1); break;
        case 6: Put(ICANCEL+0x1ec,1); break;
        case 7: Put(ICANCEL+0x1f0,1); break;
        case 8: Put(MANAGER+0x58,0); break;
        case 9: Put(ICANCEL+0x1e0,P(0x45000)); Put(ICANCEL+0x1e4,P(0x45002)); Put(ICANCEL+0x1e8,P(0x45002)); break;
        }
        assert(Invoke(V::close_inventory)==O::unavailable && !calls);
    }
    Reset(false); Put(MANAGER+0x7c,P(INVENTORY)); Put(MANAGER+0x58,1); Huds({INVENTORY,MENU});
    // Match the retained allocated-but-empty ArcString, including its capacity.
    Put(ICANCEL+0x1dc,P(0x46000)); Put(ICANCEL+0x1e0,P(0x45000)); Put(ICANCEL+0x1e4,P(0x45000)); Put(ICANCEL+0x1e8,P(0x45010));
    Prepare(); assert(Invoke(V::close_inventory)==O::submitted && calls==1);
    Reset(); Prepare(); Name(CANCEL,L""); assert(Invoke(V::close_recipe)==O::unavailable && !calls);
    for(unsigned fault=0;fault<4;++fault) {
        Reset(false); Put(MANAGER+0x7c,P(INVENTORY)); Put(MANAGER+0x58,1); Huds({INVENTORY,MENU}); Prepare();
        if(fault==0) Put(INVENTORY+0x3f0,0);
        if(fault==1) Vector(INVENTORY+0x54,{ICANCEL});
        if(fault==2) Put(ILIST,P(0x1169ec0));
        if(fault==3) Put(ILIST+0x3bc,P(RECIPE));
        n::wire::Snapshot invalid{}; assert(!n::Capture(base,scene,invalid));
        assert(Invoke(V::close_inventory)==O::stale && !calls);
    }
    Reset(); Prepare(); ++command.expected.vendor; assert(Invoke(V::random_mode)==O::stale && !calls);
    Reset(); Prepare(); command.reserved[0]=1; assert(Invoke(V::random_mode)==O::invalid && !calls);
    Reset(); Prepare(); live=false; assert(Invoke(V::random_mode)==O::stale && !calls);
    assert(VirtualFree(memory,0,MEM_RELEASE)); std::puts("vendor menu native ownership, routing, cancellation, reentrancy and ordinary-call tests passed");
}
