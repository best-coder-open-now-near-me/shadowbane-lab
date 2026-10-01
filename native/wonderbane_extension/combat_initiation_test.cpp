#include "combat_initiation.h"
#undef NDEBUG
#include <cassert>
#include <cstring>
namespace i = wonderbane::extension::combat::initiation;
int main() {
    constexpr std::uintptr_t actor=0x10000,state=0x11000,data=0x12000;
    std::array<unsigned char,0x3000> memory{};
    auto put=[&](std::uintptr_t at,const auto& value) { std::memcpy(memory.data()+at-actor,&value,sizeof(value)); };
    unsigned reads{}, mutate_on{}; bool fail=false;
    auto read=[&](std::uintptr_t at,auto& value) noexcept {
        ++reads;
        if(fail || at<actor || at+sizeof(value)>actor+memory.size()) { return false; }
        if(reads==mutate_on) { put(data,std::uint32_t{9}); }
        std::memcpy(&value,memory.data()+at-actor,sizeof(value)); return true;
    };
    auto reset=[&] { memory={}; reads=mutate_on=0; fail=false; put(state+0x10,std::uint32_t{5}); };
    auto header=[&](std::uint32_t begin,std::uint32_t end,std::uint32_t capacity) {
        put(actor+0x65c,std::array<std::uint32_t,3>{begin,end,capacity});
    };
    i::Snapshot out{}; assert(!out.Clear());
    out.state=8; assert(!out.Clear()); out={};
    reset(); assert(i::Capture(actor,state,out,read) && out.Clear());
    header(data,data,data+1024); assert(i::Capture(actor,state,out,read) && out.Clear());
    put(state+0x10,std::uint32_t{6}); assert(i::Capture(actor,state,out,read) && !out.Clear());
    put(data,std::uint32_t{7}); header(data,data+4,data+1024);
    assert(i::Capture(actor,state,out,read) && out.Only(7) && !out.Clear());
    put(data+4,std::uint32_t{7}); header(data,data+8,data+1024);
    assert(i::Capture(actor,state,out,read) && out.Only(7));
    put(data+8,std::uint32_t{7}); header(data,data+12,data+1024);
    assert(i::Capture(actor,state,out,read) && !out.Only(7));
    put(data+4,std::uint32_t{8}); header(data,data+8,data+1024);
    assert(i::Capture(actor,state,out,read) && !out.Only(7));
    for(const auto h: {std::array<std::uint32_t,3>{0,4,4},{data,data-4,data},
        {data,data+8,data+4},{data+1,data+1,data+1},{data,data,data+1028},
        {data,data,0x80000000}}) {
        reset(); put(actor+0x65c,h); assert(!i::Capture(actor,state,out,read));
    }
    for(auto unknown:{0U,8U,0xffffffffU}) {
        reset();put(state+0x10,unknown);assert(!i::Capture(actor,state,out,read));
    }
    reset();header(data,data+4,data+4);assert(!i::Capture(actor,state,out,read)); // zero ID
    reset();fail=true;assert(!i::Capture(actor,state,out,read));
    reset();header(data,data+4,data+4);put(data,std::uint32_t{7});mutate_on=5;
    assert(!i::Capture(actor,state,out,read)); // data changed between full captures
}
