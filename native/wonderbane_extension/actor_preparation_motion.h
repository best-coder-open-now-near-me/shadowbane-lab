#pragma once
#include "movement_lifetime.h"
#include <array>
#include <cstring>
namespace wonderbane::extension::actor::preparation {
// Passive counterparts of the exact-image movement cancellation operands.
// Never cancel them: any local path/follow/queued move makes preparation defer.
// The qualified 21b7b0 lookup compares unsigned key[1], then key[0]. Inspect
// only the local search path; activity in unrelated subtrees is not a veto.
template<class Read>
bool MotionIdle(std::uintptr_t base,const movement::NativeScene& scene,Read read) noexcept {
    struct Map { std::uint32_t sentinel,size; bool operator==(const Map&) const=default; };
    struct Node { std::uint32_t color,parent,left,right;std::array<std::uint32_t,2> key;
        bool operator==(const Node&) const=default; };
    static_assert(sizeof(Node)==24);
    const auto less=[](const auto& a,const auto& b){return a[1]<b[1]||(a[1]==b[1]&&a[0]<b[0]);};
    const auto address=[](std::uint32_t at){return at>=0x10000&&at<0x7fff0000&&!(at&3);};
    std::uint32_t request{},state{},status{};std::uint16_t follow{};std::uint8_t continuation{};std::array<std::uint32_t,3> path{};
    if(!read(base+0x16a1c00,request)||request||!read(scene.actor+0xad0,state)||!address(state)
        ||!read(state+0x10,status)||status!=5||!read(scene.actor+0xc10,path)
        ||!read(scene.actor+0xc1c,follow)||follow||!read(scene.actor+0xc1e,continuation)||continuation
        ||(!path[0]&&(path[1]||path[2]))||path[0]!=path[1]||path[2]<path[1]||path[2]-path[0]>1048576
        ||(path[0]&&(!address(path[0])||!address(path[2])))) { return false; }
    for(const auto offset:{0xb8U,0xe8U}) {
        Map map{},after{};std::uint32_t root{},final_root{};
        if(!read(scene.world+offset,map)||!address(map.sentinel)||map.size>1048576
            ||!read(map.sentinel+4,root)||static_cast<bool>(root)!=static_cast<bool>(map.size)) { return false; }
        // A valid red-black tree with <=2^20 entries needs at most 40 levels.
        // The 64-level bound also rejects cycles without scanning the world.
        std::array<std::uint32_t,64> addresses{};
        std::array<Node,64> nodes{};std::size_t count=0;
        std::array<std::uint32_t,2> lower{},upper{};bool have_lower=false,have_upper=false;
        auto at=root,parent=map.sentinel;
        while(at) {
            if(!address(at)||count==nodes.size()) { return false; }
            for(std::size_t i=0;i<count;++i) { if(addresses[i]==at) { return false; } }
            Node node{};if(!read(at,node)||node.color>1||node.parent!=parent||node.key==scene.identity
                ||(have_lower&&!less(lower,node.key))||(have_upper&&!less(node.key,upper))) { return false; }
            addresses[count]=at;nodes[count]=node;++count;
            parent=at;
            if(less(scene.identity,node.key)) {
                upper=node.key;have_upper=true;at=node.left;
            }else {
                lower=node.key;have_lower=true;at=node.right;
            }
        }
        for(std::size_t i=0;i<count;++i) {
            Node current{};const auto& before=nodes[i];
            if(!read(addresses[i],current)||current.parent!=before.parent||current.key!=before.key
                ||(less(scene.identity,before.key)?current.left!=before.left:current.right!=before.right)) { return false; }
        }
        if(!read(scene.world+offset,after)||after.sentinel!=map.sentinel||after.size>1048576
            ||!read(map.sentinel+4,final_root)||root!=final_root) { return false; }
    }
    std::uint32_t final_request{},final_state{},final_status{};std::uint16_t final_follow{};std::uint8_t final_continuation{};std::array<std::uint32_t,3> final_path{};
    return read(base+0x16a1c00,final_request)&&!final_request
        &&read(scene.actor+0xad0,final_state)&&final_state==state
        &&read(state+0x10,final_status)&&final_status==status
        &&read(scene.actor+0xc10,final_path)&&final_path==path
        &&read(scene.actor+0xc1c,final_follow)&&!final_follow
        &&read(scene.actor+0xc1e,final_continuation)&&!final_continuation;
}
}
