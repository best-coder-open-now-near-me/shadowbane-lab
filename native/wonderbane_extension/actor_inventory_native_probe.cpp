// Reuses the exact-image isolated inventory lookup/refcount arena; no game.
#define main ItemEntryConformanceMain
#include "combat_item_probe.cpp"
#undef main
#include "actor_inventory_native.cpp"
namespace iv=wonderbane::extension::combat::inventory;
void ClassProof(const char* path){
    std::ifstream file(std::filesystem::path(path),std::ios::binary|std::ios::ate);
    const auto size=file.tellg();Require(file.good()&&size>0&&size<=64*1024*1024,"RTTI image bounds");
    std::vector<unsigned char> bytes(static_cast<std::size_t>(size));file.seekg(0);
    Require(static_cast<bool>(file.read(reinterpret_cast<char*>(bytes.data()),size)),"RTTI image read");
    auto word=[&](std::uint32_t at){Require(at<=bytes.size()-4,"RTTI word range");std::uint32_t v{};std::memcpy(&v,bytes.data()+at,4);return v;};
    auto rva=[&](std::uint32_t va){Require(va>=0x400000&&va-0x400000<bytes.size(),"RTTI pointer range");return va-0x400000;};
    auto name=[&](std::uint32_t va){const auto at=rva(va)+8;Require(at+128<=bytes.size(),"RTTI name range");
        const auto* text=reinterpret_cast<const char*>(bytes.data()+at);const auto end=std::find(text,text+128,'\0');
        Require(end!=text+128,"RTTI name bound");return std::string(text,end);};
    for(const auto& type:iv::kCensusClasses){
        const auto col=rva(word(type.table-4));
        Require(col==type.locator&&!word(col)&&!word(col+4)&&!word(col+8)
            &&name(word(col+12))==type.name,"exact primary table/class locator identity");
        const auto hierarchy=rva(word(col+16)),count=word(hierarchy+8),array=rva(word(hierarchy+12));
        Require(count&&count<=64,"RTTI base count");bool common=false;
        for(std::uint32_t i=0;i<count;++i){const auto entry=rva(word(array+i*4));
            if(name(word(entry))==".?AVArcItem@@"){
                Require(!word(entry+8)&&word(entry+12)==0xffffffffU&&!word(entry+16),"nonvirtual zero-offset ArcItem common base");common=true;}}
        Require(common,"qualified ArcItem base exists");
    }
}
int main(int argc,char** argv){
    if(ItemEntryConformanceMain(argc,argv)){return 1;}
    try{
        ClassProof(argv[1]);
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
            Require(iv::Observe(c,state,observation)==iv::Result::available&&observation.count==1
                && observation.items[0].item_address==binding.item_address
                && observation.items[0].template_address==binding.template_address
                && observation.items[0].item_key==binding.item_key&&object[0x7c4/4]==2,"actual retained observation");
            Require(iv::Revalidate(c,state,observation)&&object[0x7c4/4]==2,"actual native membership revalidation");
            const auto old=observation;
            Require(iv::Release(state)&&object[0x7c4/4]==1,"actual native observation release");
            Require(iv::Observe(c,state,observation)==iv::Result::available&&observation.generation!=old.generation
                && !iv::Revalidate(c,state,old),"old generation cannot borrow reused native refs");
            Membership(tree,false);
            Require(!iv::Revalidate(c,state,observation)&&object[0x7c4/4]==2,"unregistered retained object unavailable");
            Require(iv::Release(state)&&object[0x7c4/4]==1,"unregistered native ref balances");
            Require(allocations==before_alloc&&network_calls==before_network&&locks>before_lock
                &&locks==unlocks&&!depth,"observation calls locks/refcounts only, no action transport");
            ++inventory_cases;
        }}
        for(const auto& type:iv::kCensusClasses){
            binding.item_key[1]=30;object[0x1c/4]=30;Membership(0,true);gate=true;
            std::array<std::uint32_t,8> peer_node{};std::array<std::uint32_t,8> peer{};
            peer[0]=static_cast<std::uint32_t>(arena_base+type.table);peer[4]=111;
            peer[6]=binding.item_key[0]+1;peer[7]=30;
            peer_node[1]=Ptr(node.data());peer_node[4]=peer[6];peer_node[5]=30;peer_node[6]=Ptr(peer.data());
            node[3]=Ptr(peer_node.data());head_a[3]=Ptr(peer_node.data());
            iv::State owner;iv::Observation result;
            Require(iv::Observe(c,owner,result)==iv::Result::available&&result.count==1
                &&result.items[0].item_key==binding.item_key,"actual locked getter with unrelated qualified subclass");
            Require(iv::Revalidate(c,owner,result)&&iv::Release(owner),"mixed inventory native ref closure");
            peer[4]=980066;
            if(type.table!=0x1142748){
                Require(iv::Observe(c,owner,result)==iv::Result::available&&result.count==1,
                    "derived matching-template object never admitted as potion");Require(iv::Release(owner),"derived reference exclusion");}
            ++inventory_cases;
        }
        Membership(0,false);{iv::State owner;iv::Observation result;
            Require(iv::Observe(c,owner,result)==iv::Result::no_eligible&&iv::Revalidate(c,owner,result),"actual complete empty census revalidates");
            Membership(0,true);Require(!iv::Revalidate(c,owner,result)&&iv::Release(owner),"new eligible native member invalidates absence");++inventory_cases;}
        Require(increments_in_lock>0,"native lookup retained while locked");
        std::printf("inventory native conformance: %u cases passed; qualified48-primitives reused; 5 primary ArcItem classes verified; no live game\n",inventory_cases);
        return 0;
    }catch(const std::exception& e){std::fprintf(stderr,"%s\n",e.what());return 1;}
}
