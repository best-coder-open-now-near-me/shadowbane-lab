#include "vendor_recycle_native.h"
#include "graphics_status.h"
#include <bcrypt.h>
#include <algorithm>
#include <cstring>

namespace wonderbane::extension::vendor_recycle {
namespace {
struct Reader {
    bool ok = true;
    std::size_t reads = 0, bytes = 0;
    ULONGLONG until = GetTickCount64() + 100;
    bool Read(std::uintptr_t at, void* value, std::size_t size) noexcept {
        if (!ok || at < 0x10000 || at >= 0x80000000 || size > 8192
            || size > 0x80000000 - at || ++reads > 32768 || (bytes += size) > 2*1024*1024
            || GetTickCount64() >= until) { ok = false; return false; }
        __try { std::memcpy(value, reinterpret_cast<const void*>(at), size); return true; }
        __except(EXCEPTION_EXECUTE_HANDLER) { ok = false; return false; }
    }
    std::uint32_t Word(std::uintptr_t at) noexcept {
        std::uint32_t value{}; Read(at, &value, sizeof(value)); return value;
    }
    void Require(std::uintptr_t at, std::uintptr_t value) noexcept {
        ok = Word(at) == value && ok;
    }
    template<std::size_t N> std::size_t Vector(std::uintptr_t at,
        std::array<std::uint32_t, N>& values) noexcept {
        const auto begin = Word(at), end = Word(at+4), cap = Word(at+8);
        if (!begin && !end && !cap) { return 0; }
        if (!ok || begin < 0x10000 || (begin | end | cap) % 4 || begin > end || end > cap
            || cap >= 0x80000000 || end-begin > N*4) { ok = false; return 0; }
        const auto count = (end-begin)/4;
        if (count) { Read(begin, values.data(), count*4); }
        for (std::size_t i=0; i<count; ++i) {
            if (values[i] < 0x10000 || values[i]%4 || values[i]>=0x80000000
                || std::find(values.begin(), values.begin()+i, values[i]) != values.begin()+i) {
                ok = false;
            }
        }
        return count;
    }
};
class Hash {
    BCRYPT_ALG_HANDLE algorithm_{};
    BCRYPT_HASH_HANDLE hash_{};
    bool ok_ = false;
public:
    Hash() noexcept {
        ok_ = BCryptOpenAlgorithmProvider(&algorithm_, BCRYPT_SHA256_ALGORITHM, nullptr, 0)>=0
            && BCryptCreateHash(algorithm_, &hash_, nullptr, 0, nullptr, 0, 0)>=0;
    }
    ~Hash() { if(hash_){BCryptDestroyHash(hash_);} if(algorithm_){BCryptCloseAlgorithmProvider(algorithm_,0);} }
    bool Add(const void* value, std::size_t size) noexcept {
        ok_ = ok_ && size <= UINT32_MAX && BCryptHashData(hash_,
            static_cast<PUCHAR>(const_cast<void*>(value)),static_cast<ULONG>(size),0)>=0;
        return ok_;
    }
    bool Word(std::uint32_t value) noexcept { return Add(&value,sizeof(value)); }
    bool Text(Reader& r, std::uintptr_t string, bool empty) noexcept {
        const auto begin=r.Word(string+4), end=r.Word(string+8), cap=r.Word(string+12);
        if (!r.ok || (begin | end | cap)%2 || begin>end || end>cap || cap>=0x80000000
            || end-begin>8192 || (begin && begin<0x10000) || (!begin && (end || cap))
            || (empty && begin!=end)) { return false; }
        std::array<unsigned char,8192> bytes{};
        return Word(end-begin) && (! (end-begin) || r.Read(begin,bytes.data(),end-begin))
            && Add(bytes.data(),end-begin);
    }
    bool Finish(Digest& digest) noexcept {
        return ok_ && BCryptFinishHash(hash_,digest.data(),static_cast<ULONG>(digest.size()),0)>=0;
    }
};
bool EmptySelection(Reader& r, std::uint32_t manager) noexcept {
    const auto head = r.Word(manager+0x3d8);
    r.Require(manager+0x3dc,0); r.Require(head+4,0); r.Require(head+8,head); r.Require(head+12,head);
    return r.ok;
}
struct SelectionTree {
    Reader& reader;
    const Manifest& manifest;
    std::uint32_t head, limit, used=0, ordered=0, first=0, last=0;
    std::array<std::uint32_t,kItems> visited{};
    bool Walk(std::uint32_t node,std::uint32_t parent,unsigned depth) noexcept {
        if(!node){return true;}
        if(node==head || depth>64 || used>=limit
            || std::find(visited.begin(),visited.begin()+used,node)!=visited.begin()+used){return false;}
        visited[used++]=node;
        reader.Require(node+4,parent);
        if(!reader.ok || !Walk(reader.Word(node+8),node,depth+1) || ordered>=limit){return false;}
        reader.Require(node+16,manifest.items[ordered]); reader.Require(node+20,40);
        reader.Require(node+24,manifest.instances[ordered++]);
        if(!first){first=node;} last=node;
        return reader.ok && Walk(reader.Word(node+12),node,depth+1);
    }
};
bool Selection(Reader& r, const Manifest& m, std::uint32_t count) noexcept {
    if (count>m.count) { return false; }
    if(!count){return EmptySelection(r,m.owner.manager);}
    const auto head=r.Word(m.owner.manager+0x3d8);
    r.Require(m.owner.manager+0x3dc,count);
    SelectionTree tree{r,m,head,count};
    return tree.Walk(r.Word(head+4),head,0) && tree.used==count && tree.ordered==count
        && tree.first==r.Word(head+8) && tree.last==r.Word(head+12) && r.ok;
}
bool CaptureInner(std::uintptr_t image, const movement::NativeScene& scene,
    const vendor::wire::Snapshot& expected, const Items& ids, std::uint32_t count,
    Manifest& out, bool selected) {
    using namespace vendor;
    if (!image || image>UINT32_MAX
        || !Qualified(image)
        || !wire::ValidSnapshot(expected) || !expected.inventory
        || !count || count>kItems || scene.epoch!=expected.scene
        || std::any_of(expected.slots.begin(),expected.slots.end(),[](const auto& slot){return slot.item || slot.state;})) { return false; }
    for (std::size_t i=0;i<ids.size();++i) {
        if (i<count ? !ids[i] || (i && ids[i-1]>=ids[i]) : ids[i]!=0) {return false;}
    }
    bool present=false, top=false; wire::Snapshot current{};
    if (!vendor::Capture(image,scene,current,0,present,top) || !top) {return false;}
    current.revision=expected.revision;
    if (!wire::Equal(current,expected)) {return false;}
    Reader r;
    r.Require(expected.manager+0x48,1); r.Require(expected.manager+0x58,1);
    if (!selected && !EmptySelection(r,expected.manager)) {return false;}
    const auto list=r.Word(expected.inventory+0x3f0);
    r.Require(list,image+0x116acf0); r.Require(list+0x3bc,expected.inventory);
    std::array<std::uint32_t,512> children{}, controls{}, stock{};
    const auto child_count=r.Vector(expected.inventory+0x54,children);
    if (std::find(children.begin(),children.begin()+child_count,list)==children.begin()+child_count) {return false;}
    const auto total=r.Vector(list+0x408,controls);
    Manifest m{}; m.owner=expected; m.items=ids; m.count=count; m.gold=r.Word(expected.manager+0x1cc);
    if(m.gold>INT32_MAX){return false;}
    for (std::size_t i=0;i<total;++i) {
        const auto control=controls[i], entry=r.Word(control+0x44c);
        r.Require(control,image+0x116aebc); r.Require(control+0x3bc,expected.inventory);
        r.Require(control+0x458,list); r.Require(entry,image+0x11696c8);
        const auto id=r.Word(entry+0x10); r.Require(entry+0x14,40);
        if(!id || std::find(stock.begin(),stock.begin()+i,id)!=stock.begin()+i){return false;}
        stock[i]=id;
        const auto found=std::lower_bound(ids.begin(),ids.begin()+count,id);
        if(found==ids.begin()+count || *found!=id){continue;}
        const auto at=static_cast<std::size_t>(found-ids.begin());
        m.entries[at]=entry; m.instances[at]=r.Word(entry+0x20);
    }
    Hash hash;
    constexpr char domain[]="WBRC1";
    if(!hash.Add(domain,sizeof(domain)) || !hash.Word(count)){return false;}
    for(std::size_t i=0;i<count;++i) {
        const auto entry=m.entries[i], instance=m.instances[i], native=r.Word(entry+0x24);
        if(!entry || !instance || !native){return false;}
        r.Require(instance,image+0x114bb68); r.Require(native,image+0x1142748);
        r.Require(instance+0x10,26990); r.Require(instance+0x14,0); r.Require(instance+0x18,ids[i]); r.Require(instance+0x1c,40);
        r.Require(native+0x10,26990); r.Require(native+0x14,0); r.Require(native+0x18,ids[i]); r.Require(native+0x1c,40);
        const auto flags=r.Word(instance+8)&0xffff, value=r.Word(instance+0x70);
        if(flags!=0x101 || !value || value>INT32_MAX || m.refund>INT32_MAX-value){return false;}
        m.refund+=value;
        std::array<std::uint32_t,64> effects{}; const auto effect_count=r.Vector(instance+0xb4,effects);
        const std::uint32_t words[]{ids[i],26990,entry,instance,native,value,
            r.Word(instance+0x74),r.Word(instance+0xf4),flags,static_cast<std::uint32_t>(effect_count)};
        const std::uint32_t durability[]{r.Word(instance+0x60),r.Word(instance+0x64)};
        if(!hash.Add(words,sizeof(words)) || !hash.Add(durability,sizeof(durability))
            || !hash.Text(r,instance+0xd0,true) || !hash.Text(r,native+0xd8,false)){return false;}
        for(std::size_t j=0;j<effect_count;++j) {
            const std::uint32_t effect[]{r.Word(effects[j]),r.Word(effects[j]+4),r.Word(effects[j]+8)};
            if(!effect[0] || effect[1] || effect[2]!=1 || !hash.Add(effect,sizeof(effect))){return false;}
        }
    }
    if (!r.ok || m.gold>INT32_MAX-m.refund || !hash.Finish(m.digest)
        || !movement::NativeMovementLifetimeCurrent(scene)) {return false;}
    if(selected && !Selection(r,m,count)){return false;}
    out=m; return true;
}
bool Select(std::uintptr_t image, const Manifest& m, std::size_t index) noexcept {
    using Getter = void* (__thiscall*)(void*,void**);
    using Add = void (__thiscall*)(void*,const vendor_production::Key*,void*);
    using Release = void (__thiscall*)(void**,void*);
    void* instance=nullptr;
    __try {
        reinterpret_cast<Getter>(image+0x26b70)(reinterpret_cast<void*>(m.entries[index]),&instance);
        if(reinterpret_cast<std::uintptr_t>(instance)!=m.instances[index]) {
            if(instance){reinterpret_cast<Release>(image+0x89bd0)(&instance,nullptr);}
            return false;
        }
        const vendor_production::Key key{m.items[index],40};
        reinterpret_cast<Add>(image+0x6c9a30)(reinterpret_cast<void*>(m.owner.manager),&key,instance);
        return true; // Add consumes the cloned InstanceInfo reference, including on native unwind.
    } __except(EXCEPTION_EXECUTE_HANDLER) {return false;}
}
bool Send(std::uintptr_t image, std::uint32_t manager) noexcept {
    using Sender = void (__thiscall*)(void*);
    __try {reinterpret_cast<Sender>(image+0x6e4180)(reinterpret_cast<void*>(manager));return true;}
    __except(EXCEPTION_EXECUTE_HANDLER) {return false;}
}
}
bool Qualified(std::uintptr_t image) noexcept {
    return image && image<=UINT32_MAX
        && GraphicsExecutableSha256Matches("6bd0e391edc1c773b4c96d8a9801db45f96db9e34202afcfc8d383d4971fe5ad");
}
bool Capture(std::uintptr_t image, const movement::NativeScene& scene,
    const vendor::wire::Snapshot& expected, const Items& ids, std::uint32_t count, Manifest& out) noexcept {
    out={}; try {return CaptureInner(image,scene,expected,ids,count,out,false);} catch(...){return false;}
}
bool Corroborate(std::uintptr_t image,const vendor::wire::Snapshot& s,
    const Items& ids,std::uint32_t count,std::uint32_t gold) noexcept {
    if(!vendor::wire::ValidSnapshot(s) || !s.inventory || !count || count>kItems
        || !vendor::wire::EmptyProduction(s)){return false;}
    Reader r;r.Require(s.manager+0x1cc,gold);
    if(!EmptySelection(r,s.manager)){return false;}
    const auto list=r.Word(s.inventory+0x3f0);
    r.Require(list,image+0x116acf0);r.Require(list+0x3bc,s.inventory);
    std::array<std::uint32_t,512> controls{},seen{};
    const auto total=r.Vector(list+0x408,controls);
    for(std::size_t i=0;i<total;++i) {
        const auto c=controls[i],entry=r.Word(c+0x44c),id=r.Word(entry+0x10);
        r.Require(c,image+0x116aebc);r.Require(c+0x3bc,s.inventory);r.Require(c+0x458,list);
        r.Require(entry,image+0x11696c8);r.Require(entry+0x14,40);
        if(!id || std::find(ids.begin(),ids.begin()+count,id)!=ids.begin()+count
            || std::find(seen.begin(),seen.begin()+i,id)!=seen.begin()+i){return false;}
        seen[i]=id;
    }
    return r.ok;
}
vendor::wire::Outcome Invoke(std::uintptr_t image, const movement::NativeScene& scene,
    const Manifest& expected, Admission admit, void* context) noexcept {
    using O=vendor::wire::Outcome;
    if(!admit || !admit(context)){return O::stale;}
    Manifest fresh{};
    if(!Capture(image,scene,expected.owner,expected.items,expected.count,fresh) || fresh!=expected){return O::stale;}
    for(std::size_t i=0;i<expected.count;++i) {
        if(!admit(context) || !movement::NativeMovementLifetimeCurrent(scene) || !Select(image,expected,i)){return O::uncertain;}
        Reader r; if(!Selection(r,expected,static_cast<std::uint32_t>(i+1))){return O::uncertain;}
    }
    try {
        if(!CaptureInner(image,scene,expected.owner,expected.items,expected.count,fresh,true)
            || fresh!=expected || !admit(context)){return O::uncertain;}
    } catch(...){return O::uncertain;}
    return Send(image,expected.owner.manager)?O::submitted:O::uncertain;
}
}
