#include "furnishing_selection.h"
#undef NDEBUG
#include <cassert>
#include <cmath>
#include <cstring>
#include <limits>
#include <map>
#include <memory>
#include <vector>

namespace f = wonderbane::extension::furnishing;
using A = f::Address; using Capture = f::SelectionCapture;
namespace {
constexpr A base = 0x400000, root = 0x100000, actor = 0x110000, building = 0x120000;
constexpr A hud = 0x130000, manager = 0x140000, list = 0x150000, layout = 0x160000;
constexpr A row = 0x170000, entry = 0x180000, deed = 0x190000, model = 0x200000, render = 0x210000;
constexpr A head = 0x220000, node = 0x230000, actor_component = 0x240000, actor_pose = 0x250000;
constexpr A building_component = 0x260000, building_pose = 0x270000;
constexpr A children = 0x280000, rows = 0x290000, name = 0x300000, floors = 0x310000;
const Capture::Owner owner{root, actor, building, 7};
const f::Transform transform{79292.7421875f,65.60722351074219f,-52861.19140625f,1,0,0,0,1,1,1};
struct Memory {
    std::map<A, unsigned char> bytes;
    std::map<A, unsigned> reads;
    A change = 0; unsigned change_on = 2, admissions = 0, reject_on = 0;
    bool admitted = true, reenter = false, reenter_admit = false;
    Capture* capture = nullptr;
    template<class T> void Put(A at, const T& value) {
        const auto* data = reinterpret_cast<const unsigned char*>(&value);
        for (std::size_t i = 0; i < sizeof(T); ++i) { bytes[at + static_cast<A>(i)] = data[i]; }
    }
    void Words(A at, std::initializer_list<A> values) { for (A v : values) { Put(at, v); at += 4; } }
    void Type(A at, A rva) { Put(at, base + rva); }
    Memory() {
        Put(base + 0x16a7bfc, root); Put(base + 0x16a2d98, actor);
        Type(root, 0x1174884); Put(root + 0x64, A{2}); Put(root + 0x20, head); Put(root + 0xa4, manager);
        Words(head, {node,node}); Words(node, {head,head,hud}); Type(hud,0x1167c68);
        Type(actor,0x114165c); Put(actor+0x4b0,actor_component); Put(actor_component,actor_pose); Put(actor_pose+8,building);
        Type(building,0x1177c0c); Words(building+0x18,{4761372,8});
        Put(building+0x4b0,building_component); Put(building_component,building_pose); Put(building_pose+0x20,transform);
        Words(building+0x734,{floors,floors+4});
        Type(manager,0x1171adc); Put(manager+0xa8,hud); Put(hud+0x104,manager); Put(hud+0x64c,building);
        Put(hud+0x524,list); Put(hud+0x648,layout); Put(hud+0x660,entry);
        Words(hud+0x54,{children,children+8,children+8}); Words(children,{list,layout});
        Type(list,0x116acf0); Put(list+0x3bc,hud); Put(layout+0x3bc,hud);
        Words(layout+0x168,{name,name+26,name+28}); const char16_t label[] = u"BTNPROPLAYOUT"; Put(name,label);
        Words(list+0x408,{rows,rows+4,rows+4}); Put(rows,row); Put(list+0x404,row);
        Type(row,0x116aebc); Put(row+0x3bc,hud); Put(row+0x458,list); Put(row+0x44c,entry);
        Type(entry,0x1169908); Put(entry+8,A{0x25}); Words(entry+0x10,{5017277,30});
        Put(entry+0x20,deed); Put(entry+0x24,model); Type(deed,0x1142468); Words(deed+0x7b8,{622657,0});
        Type(model,0x1143540); Type(model+0x44,0x114350c); Put(model+0xc0,render);
        Type(render,0x1149dbc); Type(render+0x30,0x1149d94);
        Put(hud+0x628,A{0}); Words(hud+0x630,{400,400}); Put(hud+0x638,std::array<float,2>{64,54}); Put(hud+0x37c,1.0f);
    }
    static bool Read(void* ctx, A at, void* out, std::size_t n) noexcept {
        auto& m = *static_cast<Memory*>(ctx); const auto count = ++m.reads[at];
        auto* dest = static_cast<unsigned char*>(out);
        for (std::size_t i = 0; i < n; ++i) {
            auto found = m.bytes.find(at+static_cast<A>(i)); if (found == m.bytes.end()) { return false; } dest[i] = found->second;
        }
        if (at == m.change && count == m.change_on) { dest[0] ^= 4; }
        if (m.reenter) { m.reenter = false; f::Selection s{}; assert(!m.capture->Capture(owner,s)); }
        return true;
    }
    static bool Current(void* ctx, const Capture::Owner& o) noexcept {
        auto& m = *static_cast<Memory*>(ctx); ++m.admissions;
        if (m.reenter_admit) { m.reenter_admit = false; f::Selection s{}; assert(!m.capture->Capture(owner,s)); }
        return m.admitted && m.admissions != m.reject_on && o.root == root && o.actor == actor && o.parent == building && o.epoch == 7;
    }
    std::unique_ptr<Capture> Make() {
        auto out = std::make_unique<Capture>(Capture::Access{this,&Read,&Current,base}); capture = out.get(); return out;
    }
};
void Reject(Memory& m) { auto c=m.Make(); f::Selection s{}; s.epoch=99; assert(!c->Capture(owner,s)); assert(!s.epoch && !s.model); }
}
int main() {
    { Memory m; auto c=m.Make(); f::Selection s{}; assert(c->Capture(owner,s)); assert(s.structure==building && s.building==f::Key({4761372,8}));
      assert(s.row==row && s.entry==entry && s.model==model && s.render==render && s.asset==f::Key({622657,0}));
      assert(s.building_world==transform && s.floor==0); auto same=s; same.zoom=2; assert(s.SameIdentity(same));
      same.floor=1; assert(!s.SameIdentity(same)); same=s; ++same.epoch; assert(!s.SameIdentity(same)); }
    // An old matching HUD cannot authorize a building after occupancy changes.
    for (auto field : {actor_pose+8,hud+0x64c,base+0x16a2d98,base+0x16a7bfc}) { Memory m; m.Put(field,A{building+4}); Reject(m); }
    for (auto field : {root,hud,manager,actor,building,list,row,entry,deed,model,render}) { Memory m; m.Put(field,base+0x1000); Reject(m); }
    for (auto field : {hud+0x104,manager+0xa8,list+0x3bc,layout+0x3bc,row+0x3bc,row+0x458,row+0x44c,hud+0x660,list+0x404}) {
        Memory m; m.Put(field,A{0x320000}); Reject(m);
    }
    for (auto field : {hud+0x628,building+0x18,entry+0x10,deed+0x7b8}) { Memory m; m.Put(field,A{0xffffffff}); Reject(m); }
    for (auto field : {hud+0x37c,hud+0x638,building_pose+0x20,building_pose+0x2c}) { Memory m; m.Put(field,std::numeric_limits<float>::quiet_NaN()); Reject(m); }
    { Memory m; m.Put(hud+0x37c,0.0f); Reject(m); }
    { Memory m; m.Put(hud+0x630,A{0}); Reject(m); }
    { Memory m; m.Put(building_pose+0x2c,2.0f); Reject(m); }
    { Memory m; m.Put(building_pose+0x3c,0.0f); Reject(m); }
    { Memory m; m.Put(name,A{0}); Reject(m); }
    { Memory m; m.Put(layout+0x170,name+25); Reject(m); }
    { Memory m; m.Put(children+4,list); Reject(m); }
    { Memory m; m.Put(node,node); Reject(m); }
    { Memory m; m.Put(head+4,head); Reject(m); }
    { Memory m; m.Put(node+4,A{0}); Reject(m); }
    { Memory m; m.Words(list+0x408,{rows,rows+8,rows+8}); m.Put(rows+4,row); Reject(m); }
    { Memory m; m.Words(list+0x408,{rows,rows+129*4,rows+129*4}); Reject(m); }
    { Memory m; m.Words(hud+0x54,{children,children+513*4,children+513*4}); Reject(m); }
    // Every consumed byte, including layout and occupancy, participates in the final recheck.
    std::vector<A> addresses;
    { Memory m; auto c=m.Make(); f::Selection s{}; assert(c->Capture(owner,s)); for (auto [at,count] : m.reads) { assert(count>=2); addresses.push_back(at); } }
    for (A at : addresses) { Memory m; m.change=at; Reject(m); }
    { Memory m; m.admitted=false; Reject(m); assert(m.reads.empty()); }
    { Memory m; m.reject_on=2; Reject(m); }
    { Memory m; auto c=m.Make(); m.reenter=true; f::Selection s{}; assert(c->Capture(owner,s)); }
    { Memory m; auto c=m.Make(); m.reenter_admit=true; f::Selection s{}; assert(c->Capture(owner,s)); }
    // Exercise every supported collection bound together, including reverse verification.
    { Memory m;
      for (A i=1;i<128;++i) {
          const A current=node+i*16, prev=current-16, next=i==127?head:current+16, window=0x500000+i*16;
          m.Words(current,{next,prev,window}); m.Type(window,0x1160000);
      }
      m.Put(node,node+16); m.Put(head+4,node+127*16);
      for (A i=2;i<512;++i) { m.Put(children+i*4,A{0x600000+i*16}); }
      m.Words(hud+0x54,{children,children+512*4,children+512*4});
      for (A i=1;i<128;++i) {
          const A control=0x700000+i*0x1000, payload=control+0x800;
          m.Put(rows+i*4,control); m.Type(control,0x116aebc); m.Put(control+0x3bc,hud);
          m.Put(control+0x458,list); m.Put(control+0x44c,payload); m.Type(payload,0x1169908); m.Put(payload+8,A{0x25});
      }
      m.Words(list+0x408,{rows,rows+128*4,rows+128*4});
      auto c=m.Make(); f::Selection s{}; assert(c->Capture(owner,s)); assert(s.entry==entry);
      m.Put(0x701800,base+0x1169908); m.Put(0x701000+0x44c,entry); assert(!c->Capture(owner,s));
    }
    // A neutral list focus is allowed; the owned HUD entry still defines selection.
    { Memory m; m.Put(list+0x404,A{0}); auto c=m.Make(); f::Selection s{}; assert(c->Capture(owner,s)); }
    return 0;
}
