#include "actor_preparation_motion.h"
#undef NDEBUG
#include <cassert>
#include <cstring>
#include <vector>
namespace ap=wonderbane::extension::actor::preparation;
int main(){
    std::vector<unsigned char> memory(0x1700000);const auto base=reinterpret_cast<std::uintptr_t>(memory.data());
    wonderbane::extension::movement::NativeScene scene{base+0x2000,0,base+0x4000,0,{100,53},1};
    const auto put=[&](std::uintptr_t at,const auto& value){std::memcpy(reinterpret_cast<void*>(at),&value,sizeof(value));};
    bool fail=false,churn=false,unrelated_churn=false;unsigned node_reads=0;
    const auto read=[&](std::uintptr_t at,auto& value)noexcept{
        if(fail||at<base||at>base+memory.size()-sizeof(value)){return false;}
        std::memcpy(&value,reinterpret_cast<void*>(at),sizeof(value));
        if(at==base+0x1200&&++node_reads==1){
            if(churn){put(at+16,std::uint32_t{999});}
            if(unrelated_churn){put(at+12,std::uint32_t{0xdeadbeec});put(scene.world+0xbc,std::uint32_t{8000});}
        }return true;
    };
    const auto reset=[&]{std::fill(memory.begin(),memory.end(),static_cast<unsigned char>(0));node_reads=0;churn=fail=unrelated_churn=false;
        put(scene.actor+0xad0,static_cast<std::uint32_t>(base+0x5000));put(base+0x5010,std::uint32_t{5});
        for(const auto offset:{0xb8U,0xe8U}){const auto sentinel=base+0x1000+offset;
            put(scene.world+offset,static_cast<std::uint32_t>(sentinel));
            put(sentinel+8,static_cast<std::uint32_t>(sentinel));put(sentinel+12,static_cast<std::uint32_t>(sentinel));}
    };
    reset();assert(ap::MotionIdle(base,scene,read));
    put(base+0x16a1c00,std::uint32_t{1});assert(!ap::MotionIdle(base,scene,read));
    reset();put(scene.actor+0xc1c,std::uint16_t{1});assert(!ap::MotionIdle(base,scene,read));
    reset();put(scene.actor+0xc1e,std::uint8_t{1});assert(!ap::MotionIdle(base,scene,read));
    reset();put(base+0x5010,std::uint32_t{7});assert(!ap::MotionIdle(base,scene,read));
    reset();put(scene.actor+0xc10,std::array<std::uint32_t,3>{static_cast<std::uint32_t>(base+0x8000),static_cast<std::uint32_t>(base+0x8010),static_cast<std::uint32_t>(base+0x8100)});
    assert(!ap::MotionIdle(base,scene,read));
    reset();put(scene.actor+0xc18,std::uint32_t{4});assert(!ap::MotionIdle(base,scene,read));
    for(const auto offset:{0xb8U,0xe8U}){
        reset();const auto sentinel=base+0x1000+offset,node=base+0x1200;
        put(scene.world+offset+4,std::uint32_t{1});put(sentinel+4,static_cast<std::uint32_t>(node));
        put(node+4,static_cast<std::uint32_t>(sentinel));put(node+16,std::array<std::uint32_t,2>{101,53});
        assert(ap::MotionIdle(base,scene,read)); // Another actor's movement does not suspend this actor.
        put(node+16,scene.identity);assert(!ap::MotionIdle(base,scene,read));
        put(node+16,std::array<std::uint32_t,2>{101,53});node_reads=0;churn=true;assert(!ap::MotionIdle(base,scene,read));churn=false;
        put(node+8,static_cast<std::uint32_t>(node));assert(!ap::MotionIdle(base,scene,read));
    }
    reset();fail=true;assert(!ap::MotionIdle(base,scene,read));
    reset();put(scene.world+0xbc,std::uint32_t{1048577});assert(!ap::MotionIdle(base,scene,read));
    reset();put(base+0x10bc,static_cast<std::uint32_t>(base+0x10b8));assert(!ap::MotionIdle(base,scene,read));
    // An unvisited subtree may change both its link and the global count.
    // The qualified lookup's local absence proof does not read that subtree.
    reset();const auto sentinel=base+0x10b8,node=base+0x1200,child=base+0x1300;
    put(scene.world+0xbc,std::uint32_t{7000});put(sentinel+4,static_cast<std::uint32_t>(node));
    put(node+4,static_cast<std::uint32_t>(sentinel));put(node+16,std::array<std::uint32_t,2>{101,53});
    unrelated_churn=true;assert(ap::MotionIdle(base,scene,read));assert(node_reads==2);
    // Native ordering compares word1 first: local {100,53} is LEFT of {1,54}.
    unrelated_churn=false;put(node+16,std::array<std::uint32_t,2>{1,54});
    put(node+8,static_cast<std::uint32_t>(child));put(child+4,static_cast<std::uint32_t>(node));
    put(child+16,scene.identity);assert(!ap::MotionIdle(base,scene,read));
    put(child+16,std::array<std::uint32_t,2>{1,55});assert(!ap::MotionIdle(base,scene,read)); // Violates visited upper bound.
    return 0;
}
