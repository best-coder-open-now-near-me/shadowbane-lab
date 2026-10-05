#include "actor_inventory_native.h"
#include "graphics_status.h"
#include "movement_native_image.h"
#include <Windows.h>
#include <cstring>
#include <limits>

namespace wonderbane::extension::combat::inventory {
static_assert(sizeof(void*) == 4, "Reviewed inventory ABI is x86");
namespace {
using Lookup = void*(__thiscall*)(void*, void**, const Key*);
using NativeRelease = void(__thiscall*)(void**, void*);
struct Calls { Lookup lookup; NativeRelease release; };
std::uintptr_t base{};
struct Budget {
    ULONGLONG deadline = GetTickCount64() + 50;
    std::size_t calls{}, bytes{};
    bool Valid() const noexcept { return GetTickCount64() < deadline; }
};
bool Copy(void* out, std::uintptr_t at, std::size_t size, Budget& budget) noexcept {
    if (at < 0x10000 || at > 0x7fff0000 || size > 0x7fff0000-at
        || ++budget.calls > 20000 || (budget.bytes += size) > 512*1024 || !budget.Valid()) { return false; }
    __try { std::memcpy(out, reinterpret_cast<const void*>(at), size); return budget.Valid(); }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
template<class T> bool Read(std::uintptr_t at, T& value, Budget& budget) noexcept {
    return Copy(&value, at, sizeof(value), budget);
}
bool Ptr(std::uintptr_t at) noexcept { return at >= 0x10000 && at < 0x7fff0000 && !(at & 3); }
bool Word(std::uintptr_t at, std::uintptr_t expected, Budget& budget) noexcept {
    std::uintptr_t value{}; return Read(at,value,budget) && value==expected;
}
bool Binding(const Context& c, Budget& budget) noexcept {
    Key key{};
    return c.image==base && Ptr(c.actor) && c.actor_key[0] && c.actor_key[1]==53
        && c.template_key[0] && c.template_key[1]==0 && c.current
        && Word(base+0x16a2d98,c.actor,budget)
        && Word(c.actor,base+0x114165c,budget) && Read(c.actor+0x18,key,budget) && key==c.actor_key
        && Word(c.actor+8,base+0x11417d4,budget) && Word(c.actor+0xea0,0,budget)
        && Word(c.actor+0xea4,base+0x1141570,budget);
}
bool Current(const Context& c, Budget& budget) noexcept {
    return Binding(c,budget) && c.current(c.owner) && Binding(c,budget);
}
bool Less(const Key& a, const Key& b) noexcept { return a[1]<b[1] || (a[1]==b[1] && a[0]<b[0]); }
bool Item(std::uintptr_t image, std::uintptr_t item_address, const Key& key, Facts& f, Budget& budget) noexcept {
    f={}; f.item_address=item_address;
    return Ptr(item_address) && Word(item_address,image+0x1142748,budget)
        && Read(item_address+0x18,f.item_key,budget) && f.item_key==key && key[0] && key[1]
        && Read(item_address+0x10,f.template_key,budget) && f.template_key[0] && !f.template_key[1]
        && Read(item_address+0x68c,f.template_address,budget) && Ptr(f.template_address)
        && Word(f.template_address,image+0x11428f0,budget)
        && Read(f.template_address+0xf4,f.type,budget) && Read(f.template_address+0x11c,f.flags,budget)
        && Read(item_address+0x744,f.quantity,budget);
}
// Exact original/prepared .13 RTTI: these primary tables have a nonvirtual
// ArcItem base at offset zero (PMD 0,-1,0). Common +10 template/+18 instance
// keys may be censused; derived classes are NEVER eligible native-use operands.
struct CensusClass { std::uint32_t table, locator; const char* name; };
constexpr std::array<CensusClass,5> kCensusClasses{{
    {0x1142188,0x118c808,".?AVArcContainerObject@@"},
    {0x1142468,0x118c9a8,".?AVArcDeed@@"},
    {0x1142748,0x118cb58,".?AVArcItem@@"},
    {0x1143278,0x118d8a0,".?AVArcRune@@"},
    {0x1144154,0x118e3c8,".?AVArcKey@@"},
}};
struct Node {
    std::uintptr_t address{};
    std::array<std::uint32_t,6> words{}; // parent,left,right,key[2],item
    std::uintptr_t table{};
    Key key{}, template_key{};
    Facts facts{};
    bool operator==(const Node&) const = default;
};
struct Tree {
    std::uintptr_t head{};
    std::array<std::uint32_t,3> links{}; // root,first,last
    bool operator==(const Tree&) const = default;
};
struct Census {
    std::array<Tree,2> trees{};
    std::array<Node,kMaxNodes> nodes{};
    std::size_t count{};
    bool operator==(const Census&) const = default;
};
bool Walk(const Context& c,Census& census,std::uintptr_t at,std::uintptr_t parent,
    std::uintptr_t head,const Key* low,const Key* high,unsigned level,
    std::uintptr_t& first,std::uintptr_t& last,Budget& budget) noexcept {
    if (!at) { return true; }
    if (!Ptr(at) || at==head || level>64 || census.count==kMaxNodes) { return false; }
    for (std::size_t i=0;i<census.count;++i) { if(census.nodes[i].address==at){return false;} }
    auto& n=census.nodes[census.count]; n.address=at;
    if(!Read(at+4,n.words,budget)) { return false; }
    const Key key{n.words[3],n.words[4]};
    if((parent ? n.words[0]!=parent : (n.words[0]!=0 && n.words[0]!=head))
        || !key[0] || !key[1] || (low && !Less(*low,key)) || (high && !Less(key,*high))) { return false; }
    for(std::size_t i=0;i<census.count;++i) { if(census.nodes[i].key==key){return false;} }
    const auto member_address=n.words[5];
    if(!Ptr(member_address) || !Read(member_address,n.table,budget)){return false;}
    bool qualified=false;
    for(const auto& type:kCensusClasses){if(n.table==c.image+type.table){qualified=true;break;}}
    if(!qualified){return false;}
    if(!Read(member_address+0x18,n.key,budget) || n.key!=key
        || !Read(member_address+0x10,n.template_key,budget) || !n.template_key[0] || n.template_key[1]){return false;}
    // Do not probe unrelated derived/template fields or retain unrelated objects.
    if(n.table==c.image+0x1142748 && n.template_key==c.template_key
        && !Item(c.image,member_address,key,n.facts,budget)){return false;}
    ++census.count;
    if(!Walk(c,census,n.words[1],at,head,low,&key,level+1,first,last,budget)) { return false; }
    if(!first){first=at;} last=at;
    return Walk(c,census,n.words[2],at,head,&key,high,level+1,first,last,budget);
}
bool Capture(const Context& c,Census& result,Budget& budget) noexcept {
    result={};
    constexpr std::array<std::uintptr_t,2> offsets{0x688,0x6f0},tables{0x11415e4,0x11415cc};
    for(std::size_t i=0;i<2;++i){
        auto& t=result.trees[i];
        if(!Word(c.actor+offsets[i],c.image+tables[i],budget)
            || !Read(c.actor+offsets[i]+0x44,t.head,budget) || !Ptr(t.head)
            || !Read(t.head+4,t.links,budget)) { return false; }
        std::uintptr_t first{},last{};
        if(!Walk(c,result,t.links[0],0,t.head,nullptr,nullptr,0,first,last,budget)
            || t.links[1]!=(first ? first : t.head) || t.links[2]!=(last ? last : t.head)) { return false; }
    }
    return true;
}
bool Eligible(const Context& c,const Facts& f) noexcept {
    return f.template_key==c.template_key && f.type==8 && f.flags==0x0a && f.quantity>0;
}
}
struct Access {
    static void Quarantine(State& s) noexcept { s.quarantined_=true; }
    static bool Drop(State& s,void** slot) {
        if(!*slot){return true;}
        reinterpret_cast<NativeRelease>(s.release_)(slot,nullptr);
        if(*slot){Quarantine(s);return false;}
        return true;
    }
    static bool ReleaseInner(State& s) {
        if(s.quarantined_){return false;}
        if(!s.occupied_){return true;}
        if(!s.release_){Quarantine(s);return false;}
        if(!Drop(s,&s.scratch_)){return false;}
        for(auto& owned:s.retained_){if(!Drop(s,&owned)){return false;}}
        s.occupied_=false;s.context_={};s.observation_={};s.release_=0;
        return true;
    }
    static bool ReleaseCxx(State& s) noexcept {
        try{return ReleaseInner(s);}catch(...){Quarantine(s);return false;}
    }
    static bool ReleaseSafe(State& s) noexcept {
        __try {return ReleaseCxx(s);} __except(EXCEPTION_EXECUTE_HANDLER){Quarantine(s);return false;}
    }
    static bool LookupExact(const Context& c,State& s,void** slot,const Facts& expected,
        const Calls& calls,Budget& budget) {
        if(*slot || !budget.Valid()){return false;}
        const auto returned=calls.lookup(reinterpret_cast<void*>(c.actor+0xea4),slot,&expected.item_key);
        if(returned!=slot){Quarantine(s);return false;}
        Facts facts{};
        return *slot && reinterpret_cast<std::uintptr_t>(*slot)==expected.item_address
            && Item(c.image,reinterpret_cast<std::uintptr_t>(*slot),expected.item_key,facts,budget) && facts==expected;
    }
    static Result Run(const Context& c,State& s,Observation& out,const Calls& calls,bool revalidate) {
        Budget budget;
        if(!Ready() || !Current(c,budget)){return Result::unknown;}
        Census first,second;
        if(!Capture(c,first,budget)){return Result::unknown;}
        Observation found{};found.generation=s.generation_;
        for(std::size_t i=0;i<first.count;++i){
            const auto& facts=first.nodes[i].facts;
            if(!Eligible(c,facts)){continue;}
            if(found.count==kMaxItems){return Result::unknown;}
            found.items[found.count++]=facts;
        }
        found.result=found.count?Result::available:Result::no_eligible;
        if(revalidate && found!=s.observation_){return Result::unknown;}
        for(std::size_t i=0;i<found.count;++i){
            if(revalidate){
                if(reinterpret_cast<std::uintptr_t>(s.retained_[i])!=found.items[i].item_address
                    || !LookupExact(c,s,&s.scratch_,found.items[i],calls,budget)){return Result::unknown;}
                if(!Drop(s,&s.scratch_)){return Result::unknown;}
            }else if(!LookupExact(c,s,&s.retained_[i],found.items[i],calls,budget)){return Result::unknown;}
        }
        // No unowned pointer is retained directly. The ordinary getter pins under
        // the native container lock; recapture detects changed discovery/facts.
        // Outermost owner-thread serialization is required; rereads do not claim
        // to defeat arbitrary foreign writes/ABA. Native lock waits cannot be
        // interrupted; an over-budget return simply cannot publish authority.
        if(!Current(c,budget) || !Capture(c,second,budget) || first!=second || !Binding(c,budget)){return Result::unknown;}
        if(!revalidate){s.observation_=found;out=found;}
        return found.result;
    }
    static Result RunCxx(const Context& c,State& s,Observation& out,const Calls& calls,bool again) noexcept {
        try{return Run(c,s,out,calls,again);}catch(...){Quarantine(s);return Result::unknown;}
    }
    static Result RunSafe(const Context& c,State& s,Observation& out,const Calls& calls,bool again) noexcept {
        __try{return RunCxx(c,s,out,calls,again);}
        __except(EXCEPTION_EXECUTE_HANDLER){Quarantine(s);return Result::unknown;}
    }
    static Result ObserveBound(const Context& c,State& s,Observation& out,const Calls& calls) noexcept {
        out={};
        if(s.occupied_ || s.quarantined_ || s.generation_==std::numeric_limits<std::uint64_t>::max()
            || !calls.lookup || !calls.release){return Result::unknown;}
        ++s.generation_;s.occupied_=true;s.context_=c;s.release_=reinterpret_cast<std::uintptr_t>(calls.release);
        const auto result=RunSafe(c,s,out,calls,false);
        if(result!=Result::unknown){return result;}
        ReleaseSafe(s);out={};return Result::unknown;
    }
    static bool RevalidateBound(const Context& c,State& s,const Observation& out,const Calls& calls) noexcept {
        if(!s.occupied_ || s.quarantined_ || c!=s.context_ || out!=s.observation_
            || out.generation!=s.generation_ || out.result==Result::unknown){return false;}
        Observation ignored{};
        const bool ok=RunSafe(c,s,ignored,calls,true)==out.result;
        // Failed revalidation invalidates the publication, but retains references
        // for explicit teardown. No later successful reread can resurrect it.
        if(!ok){s.observation_={};}
        return ok;
    }
};
Result Observe(const Context& c,State& s,Observation& out) noexcept {
    return Access::ObserveBound(c,s,out,{reinterpret_cast<Lookup>(c.image+0x4b6f),
        reinterpret_cast<NativeRelease>(c.image+0x89bd0)});
}
bool Revalidate(const Context& c,State& s,const Observation& out) noexcept {
    return Access::RevalidateBound(c,s,out,{reinterpret_cast<Lookup>(c.image+0x4b6f),
        reinterpret_cast<NativeRelease>(c.image+0x89bd0)});
}
bool Release(State& s) noexcept { return Access::ReleaseSafe(s); }
bool Ready() noexcept { return base!=0; }
bool Start(std::uintptr_t image) noexcept {
    const DWORD error=GetLastError();std::uintptr_t verified{};
    const bool ok=image && (!base || base==image)
        && (GraphicsExecutableSha256Matches("0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d") || GraphicsExecutableSha256Matches("78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903"))
        && movement::VerifyNativeMovementImage(verified) && verified==image;
    if(ok){base=image;}
    SetLastError(error);return ok;
}
}
