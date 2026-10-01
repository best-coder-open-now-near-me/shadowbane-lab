// Reuses the exact-image isolated inventory lookup/refcount arena; no game.
#define main ItemEntryConformanceMain
#include "combat_item_probe.cpp"
#undef main
#include "actor_inventory_native.cpp"
namespace iv=wonderbane::extension::combat::inventory;
int main(int argc,char** argv){
    if(ItemEntryConformanceMain(argc,argv)){return 1;}
    try{
        iv::base=arena_base;
        actor[0x688/4]=static_cast<std::uint32_t>(arena_base+0x11415e4);
        actor[0x6f0/4]=static_cast<std::uint32_t>(arena_base+0x11415cc);
        object[0x744/4]=3;
        const iv::Context c{arena_base,binding.actor,binding.actor_key,binding.template_key,Current,nullptr};
        unsigned inventory_cases{};
        for(unsigned tree:{0U,1U}){for(auto uuid:{30U,40U}){
            binding.item_key[1]=uuid;object[0x18/4]=binding.item_key[0];object[0x1c/4]=uuid;
            Membership(tree,true);gate=true;iv::State state;iv::Observation observation;
            const auto before_alloc=allocations,before_network=network_calls,before_lock=locks;
            Require(iv::Observe(c,state,observation)&&observation.count==1
                && observation.items[0].item_address==binding.item_address
                && observation.items[0].template_address==binding.template_address
                && observation.items[0].item_key==binding.item_key&&object[0x7c4/4]==2,"actual retained observation");
            Require(iv::Revalidate(c,state,observation)&&object[0x7c4/4]==2,"actual native membership revalidation");
            const auto old=observation;
            Require(iv::Release(state)&&object[0x7c4/4]==1,"actual native observation release");
            Require(iv::Observe(c,state,observation)&&observation.generation!=old.generation
                && !iv::Revalidate(c,state,old),"old generation cannot borrow reused native refs");
            Membership(tree,false);
            Require(!iv::Revalidate(c,state,observation)&&object[0x7c4/4]==2,"unregistered retained object unavailable");
            Require(iv::Release(state)&&object[0x7c4/4]==1,"unregistered native ref balances");
            Require(allocations==before_alloc&&network_calls==before_network&&locks>before_lock
                &&locks==unlocks&&!depth,"observation calls locks/refcounts only, no action transport");
            ++inventory_cases;
        }}
        Require(increments_in_lock>0,"native lookup retained while locked");
        std::printf("inventory native conformance: %u cases passed; qualified48-primitives reused; no live game\n",inventory_cases);
        return 0;
    }catch(const std::exception& e){std::fprintf(stderr,"%s\n",e.what());return 1;}
}
