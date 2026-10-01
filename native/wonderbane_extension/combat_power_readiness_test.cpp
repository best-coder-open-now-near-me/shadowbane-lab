#include "combat_power_readiness.h"
#include <cstdio>
#include <cstring>
#include <map>
#include <limits>
namespace r = wonderbane::extension::combat::power::readiness;
using A = wonderbane::extension::combat::power::Availability;
namespace {
constexpr std::uintptr_t image=0x400000,actor=0x20000000,container=0x21000000,sentinel=0x21000100,node_address=0x21000200,table=0x22000000;
std::map<std::uintptr_t,std::uint8_t> bytes;
int failures{};unsigned calls{},mutate_at{};
void Check(bool value,const char* label) { if(!value) { ++failures;std::fprintf(stderr,"%s\n",label); } }
template<class T> void Put(std::uintptr_t at,const T& v) {
    const auto* p=reinterpret_cast<const std::uint8_t*>(&v);
    for(std::size_t i=0;i<sizeof(T);++i) { bytes[at+i]=p[i]; }
}
bool Read(std::uintptr_t at,auto& v) noexcept {
    ++calls;
    if(mutate_at && calls==mutate_at) { Put(actor+0x5c8,std::uint32_t{0}); }
    auto* p=reinterpret_cast<std::uint8_t*>(&v);
    for(std::size_t i=0;i<sizeof(v);++i) {
        const auto it=bytes.find(at+i); if(it==bytes.end()) { return false; } p[i]=it->second;
    }
    return true;
}
void Reset() {
    bytes.clear();calls=mutate_at=0;
    Put(image+0x16a2d70,100.0);Put(actor+0x67c,99.0f);Put(actor+0x5c8,std::uint32_t{0});
    Put(image+0x1389560,std::uint32_t{image+0x1141a24});Put(image+0x1389564,std::uint32_t{5});
    Put(image+0x1389568,std::uint32_t{image+0x12e86b4});Put(image+0x1389570,std::uint8_t{0});
    Put(actor+0x34,std::uint32_t{0});Put(actor+0x38,std::uint32_t{0});
}
void List(std::uint32_t id=123,float deadline=90) {
    Put(actor+0x5c8,std::uint32_t{container});Put(container,std::uint32_t{sentinel});
    Put(sentinel,std::uint32_t{node_address});Put(sentinel+4,std::uint32_t{node_address});
    r::Node n{node_address==sentinel?0U:static_cast<std::uint32_t>(sentinel),static_cast<std::uint32_t>(sentinel),id,0};
    std::memcpy(&n.deadline_bits,&deadline,4);Put(node_address,n);
}
void Map() {
    Put(actor+0x34,std::uint32_t{table});Put(actor+0x38,std::uint32_t{2});
    Put(image+0x114133c+8,std::uint32_t{7});
    for(unsigned i=0;i<4;++i) { Put(table+i*8,std::array<std::uint32_t,2>{}); }
}
A Observe() { return r::Observe(image,actor,123,[](std::uintptr_t at,auto& v) noexcept { return Read(at,v); }); }
}
int main() {
    Reset();Check(Observe()==A::ready,"null list/default false ready");
    List();Check(Observe()==A::reuse_blocked,"expired prediction does not grant reuse");
    Put(actor+0x67c,101.0f);Check(Observe()==A::global_recovery,"global recovery precedence");
    Put(actor+0x67c,100.0f);Check(Observe()==A::reuse_blocked,"equal recovery permits reuse predicate");
    Reset();List(456);Check(Observe()==A::ready,"different power does not block");
    Reset();List();Map();
    Put(table+2*8,std::array<std::uint32_t,2>{5,1});Check(Observe()==A::ready,"actual bypass true");
    Put(table+2*8,std::array<std::uint32_t,2>{5,256});Check(Observe()==A::reuse_blocked,"only low byte is bypass");
    Put(table+2*8,std::array<std::uint32_t,2>{});Put(table,std::array<std::uint32_t,2>{5,1});
    Check(Observe()==A::unknown,"misplaced relevant key beyond native empty rejected");
    Put(table+2*8,std::array<std::uint32_t,2>{UINT32_MAX,0});Put(table+3*8,std::array<std::uint32_t,2>{5,1});
    Put(table,std::array<std::uint32_t,2>{});
    Check(Observe()==A::ready,"native tombstone collision path preserved");
    Put(table,std::array<std::uint32_t,2>{5,0});Check(Observe()==A::unknown,"duplicate relevant property rejected");
    Reset();List();Put(node_address,r::Node{static_cast<std::uint32_t>(node_address),static_cast<std::uint32_t>(sentinel),123,0});
    Check(Observe()==A::unknown,"cyclic list rejected");
    Reset();List();Put(node_address+4,std::uint32_t{0});Check(Observe()==A::unknown,"broken reverse link rejected");
    Reset();List();Put(sentinel+4,std::uint32_t{sentinel});Check(Observe()==A::unknown,"wrong tail rejected");
    Reset();List();Put(node_address+8,std::uint32_t{0});Check(Observe()==A::unknown,"invalid power ID rejected");
    Reset();List();Put(node_address+8,std::uint32_t{123});
    Put(node_address,r::Node{static_cast<std::uint32_t>(node_address+0x100),static_cast<std::uint32_t>(sentinel),123,0});
    Put(node_address+0x100,r::Node{static_cast<std::uint32_t>(sentinel),static_cast<std::uint32_t>(node_address),123,0});
    Put(sentinel+4,std::uint32_t{node_address+0x100});Check(Observe()==A::reuse_blocked,"duplicate reuse IDs retain native membership");
    Reset();Put(actor+0x5c8,std::uint32_t{container});Put(container,std::uint32_t{sentinel});
    Put(sentinel,std::uint32_t{sentinel});Put(sentinel+4,std::uint32_t{sentinel});Check(Observe()==A::ready,"empty sentinel list");
    Reset();Put(image+0x1389570,std::uint8_t{1});Check(Observe()==A::unknown,"unexpected descriptor default rejected");
    Reset();Put(image+0x1389560,std::uint32_t{0});Check(Observe()==A::unknown,"unqualified descriptor rejected");
    Reset();Map();Put(actor+0x38,std::uint32_t{13});Check(Observe()==A::unknown,"bounded map rejects oversize");
    Reset();Put(image+0x16a2d70,std::numeric_limits<double>::quiet_NaN());Check(Observe()==A::unknown,"invalid clock rejected");
    Reset();Put(actor+0x67c,std::numeric_limits<float>::infinity());Check(Observe()==A::unknown,"invalid recovery rejected");
    Reset();List();r::Snapshot capture{};Check(r::Capture(image,actor,[](std::uintptr_t at,auto& v) noexcept { return Read(at,v); },capture),"capture fixture");
    const auto first_calls=calls;calls=0;mutate_at=first_calls+1;
    Check(Observe()==A::unknown,"list mutation between complete passes rejected");
    Reset();List();bytes.erase(node_address+9);Check(Observe()==A::unknown,"unreadable member is unknown");
    Reset();List();Put(node_address,r::Node{static_cast<std::uint32_t>(sentinel),static_cast<std::uint32_t>(sentinel),123,0});
    // A long valid list is bounded; no partial membership result escapes.
    for(std::uint32_t i=0;i<=r::maximum_nodes;++i) {
        const auto at=static_cast<std::uint32_t>(node_address+i*0x20);
        Put(at,r::Node{static_cast<std::uint32_t>(i==r::maximum_nodes?sentinel:at+0x20),
            static_cast<std::uint32_t>(i?at-0x20:sentinel),123,0});
    }
    Put(sentinel+4,std::uint32_t{node_address+r::maximum_nodes*0x20});
    Check(Observe()==A::unknown,"list bound never returns partial authority");
    if(failures) { return 1; } std::puts("power readiness: 24 cases passed"); return 0;
}
