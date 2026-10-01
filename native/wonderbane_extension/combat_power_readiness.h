#pragma once
#include <array>
#include <cmath>
#include <cstdint>

namespace wonderbane::extension::combat::power {
enum class Availability { unknown, ready, global_recovery, reuse_blocked };
namespace readiness {
// Exact .13 PreparePower4E339/4E3D9: recovery clock, then reuse-list
// membership unless ADMIN_ISADMIN. Predicted node deadlines NEVER admit a power.
// Owner thread, retained exact actor; bounded observation is not retained ownership.
constexpr std::size_t maximum_nodes = 1024, maximum_slots = 4096;
inline bool Address(std::uintptr_t at, std::size_t size) noexcept {
    return at >= 0x10000 && at % 4 == 0 && size <= 0x7fff0000
        && at <= 0x7fff0000 - size;
}
struct Node {
    std::uint32_t next{}, previous{}, id{}, deadline_bits{};
    bool operator==(const Node&) const = default;
};
struct Snapshot {
    std::uint32_t container{}, sentinel{}, first{}, last{}, count{};
    std::array<std::uint32_t, maximum_nodes> addresses{};
    std::array<Node, maximum_nodes> nodes{};
    std::uint32_t table{}, bits{}, polynomial{}, descriptor_table{}, descriptor_key{}, descriptor_name{};
    std::uint8_t default_value{}, bypass{};
    // Preserve all slots to reject map mutation, including duplicate relevant keys.
    std::array<std::array<std::uint32_t, 2>, maximum_slots> slots{};
    float recovery{};
    double now{};
};
template<class Read>
bool Capture(std::uintptr_t image, std::uintptr_t actor, Read read, Snapshot& out) noexcept {
    out = {};
    if (!Address(actor,0x680) || !Address(image,0x1389574)
        || !read(image+0x16a2d70,out.now) || !std::isfinite(out.now)
        || !read(actor+0x67c,out.recovery) || !std::isfinite(out.recovery)
        || !read(actor+0x5c8,out.container)) { return false; }
    if (out.container) {
        if (!Address(out.container,4) || !read(out.container,out.sentinel)
            || !Address(out.sentinel,16) || !read(out.sentinel,out.first)
            || !read(out.sentinel+4,out.last)) { return false; }
        auto at=out.first, previous=out.sentinel;
        while(at!=out.sentinel) {
            if (out.count==maximum_nodes || !Address(at,sizeof(Node))) { return false; }
            for(std::size_t i=0;i<out.count;++i) { if(out.addresses[i]==at) { return false; } }
            Node node{};
            if(!read(at,node) || node.previous!=previous || !node.id || !node.next) { return false; }
            out.addresses[out.count]=at; out.nodes[out.count++]=node;
            previous=at; at=node.next;
        }
        if(previous!=out.last || (out.count==0 && out.last!=out.sentinel)) { return false; }
    }
    // The exact descriptor's default getter only returns +10 low byte.
    const auto descriptor=image+0x1389560;
    if(!read(descriptor,out.descriptor_table) || out.descriptor_table!=image+0x1141a24
        || !read(descriptor+4,out.descriptor_key) || !out.descriptor_key || out.descriptor_key==UINT32_MAX
        || !read(descriptor+8,out.descriptor_name) || out.descriptor_name!=image+0x12e86b4
        || !read(descriptor+0x10,out.default_value) || out.default_value!=0
        || !read(actor+0x34,out.table) || !read(actor+0x38,out.bits)) { return false; }
    out.bypass=out.default_value;
    if(out.table) {
        if(out.bits>12) { return false; }
        const auto count=std::size_t{1}<<out.bits;
        if(!Address(out.table,count*8) || !read(image+0x114133c+out.bits*4,out.polynomial)) { return false; }
        bool found=false;
        for(std::size_t i=0;i<count;++i) {
            auto& slot=out.slots[i];
            if(!read(out.table+i*8,slot)) { return false; }
            if(slot[0]==out.descriptor_key) {
                if(found) { return false; }
                found=true; out.bypass=static_cast<std::uint8_t>(slot[1]);
            }
        }
        // 86DA0: native keyed lookup stops at its first empty bucket. A matching
        // key elsewhere in malformed storage must never manufacture a bypass.
        const auto mask=static_cast<std::uint32_t>(count-1);
        const auto initial=(~out.descriptor_key)&mask;
        auto index=initial, step=((out.descriptor_key>>3)^out.descriptor_key)&mask;
        if(!step) { step=mask; }
        bool resolved=false, native_found=false;
        std::uint8_t native_value=out.default_value;
        for(std::size_t attempt=0;attempt<count;++attempt) {
            const auto& slot=out.slots[index];
            if(!slot[0]) { resolved=true; break; }
            if(slot[0]==out.descriptor_key) {
                native_found=true; native_value=static_cast<std::uint8_t>(slot[1]); resolved=true; break;
            }
            index=(initial+step)&mask;
            step<<=1;
            if(step>mask) { step^=out.polynomial; }
        }
        if(!resolved || native_found!=found || native_value!=out.bypass) { return false; }
    }
    return true;
}
inline bool Stable(const Snapshot& a,const Snapshot& b) noexcept {
    return a.container==b.container && a.sentinel==b.sentinel && a.first==b.first && a.last==b.last
        && a.count==b.count && a.addresses==b.addresses && a.nodes==b.nodes
        && a.table==b.table && a.bits==b.bits && a.polynomial==b.polynomial && a.descriptor_table==b.descriptor_table
        && a.descriptor_key==b.descriptor_key && a.descriptor_name==b.descriptor_name
        && a.default_value==b.default_value && a.bypass==b.bypass && a.slots==b.slots
        && a.recovery==b.recovery && b.now>=a.now;
}
template<class Read>
Availability Observe(std::uintptr_t image,std::uintptr_t actor,std::uint32_t power,Read read) noexcept {
    if(!power) { return Availability::unknown; }
    Snapshot first{},last{};
    if(!Capture(image,actor,read,first) || !Capture(image,actor,read,last) || !Stable(first,last)) {
        return Availability::unknown;
    }
    // Keep precedence identical to PreparePower. No local-clock prediction erases membership.
    if(last.now<last.recovery) { return Availability::global_recovery; }
    for(std::size_t i=0;i<last.count;++i) {
        if(last.nodes[i].id==power && !last.bypass) { return Availability::reuse_blocked; }
    }
    return Availability::ready;
}
}
}
