// Exact-image developer probe: no client startup, game process or network I/O.
// Runs real item Use, message constructors, key helpers, inventory tree lookup,
// owned-reference helpers and sender. Only allocation, clock, lock primitives
// and downstream transport are instrumented. Native foreign EH is fail-fast;
// synthetic compiled fixture separately tests exception quarantine/restoration.
#include "combat_item_entry.cpp"
#include <bcrypt.h>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
namespace it=wonderbane::extension::combat::item;
namespace sb=wonderbane::extension::combat::submission;
namespace {
void Require(bool condition, const char* message) {
    if (!condition) { throw std::runtime_error(message); }
}
std::string Digest(const unsigned char* bytes, std::size_t size) {
    BCRYPT_ALG_HANDLE algorithm{};
    BCRYPT_HASH_HANDLE hash{};
    std::array<unsigned char, 32> digest{};
    const bool ok = size <= std::numeric_limits<ULONG>::max()
        && BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0
        && BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) >= 0
        && BCryptHashData(hash, const_cast<unsigned char*>(bytes), static_cast<ULONG>(size), 0) >= 0
        && BCryptFinishHash(hash, digest.data(), static_cast<ULONG>(digest.size()), 0) >= 0;
    if (hash) { BCryptDestroyHash(hash); }
    if (algorithm) { BCryptCloseAlgorithmProvider(algorithm, 0); }
    Require(ok, "SHA256 failed");
    constexpr char hex[] = "0123456789abcdef";
    std::string result;
    for (const auto byte : digest) {
        result += hex[byte >> 4]; result += hex[byte & 15];
    }
    return result;
}

// Exact original/prepared .13 primitive hashes; no client bytes embedded.
struct Segment {std::uint32_t rva,size;const char* sha;};
constexpr Segment segments[]{
    {0xae810,0x8e9,"d3081a443dcb6f4cab76fc6ff221695f79a6d3962f5b513f523016940c43293d"},
    {0x374f00,0x7c,"9f5950257a4a4c45b1ad068f4d1853626bf71b6dff233a32bc70dc4994a722da"},
    {0x35a670,0x65,"575d100624f74903c3409da0cbfd0e9bd1418a3c4d118f7b61149cbdac6f88c3"},
    {0x362060,0x97,"d82e83951c7b055da2b978d105c94b0a33040d8050b4da48e514a2e6e7953206"},
    {0x111790,0x10,"9d20fb9737545d0eeb198c79dc5d325beabd6d570a4058d3f1e7f4a887df0403"},
    {0x1117b0,0x16,"66b42201ae2adac5438161fdb2a8dc60eb4bf84b6a9462a2564677c9a809cdd4"},
    {0x1119d0,0x1,"ae3f4619b0413d70d3004b9131c3752153074e45725be13b9a148978895e359e"},
    {0x1125d0,0x23,"98d6dbc6aab36ce528ae6f4d4334b51b427a12518a121738990ef259ee10a0f3"},
    {0xc4b00,0x17,"a515f17d8e6f9f634b776ad473a7fd89bbc84ebcb6b5de67a1a0edc0d3aa39c5"},
    {0x7f4490,0x33,"a9b5138d3ed220c464eb586de242863e18bdf29935df0e97ee870cdc56dad534"},
    {0x7f4da0,0x8e,"a85832da1fbfd197812fcd02e2728ce81bd425e5eb959e9221dfe1bc86dc57c1"},
    {0x4c290,0x142,"e107368e0f2a13250dd0cd8b8fad849566ba50bc33075229516aa22a01bdc025"},
    {0x97200,0x8,"9642a6169167a39c1cee30f6111b9a3a1676eb84eedf7f08c37b6f5bf31ee85c"},
    {0x228620,0x25,"d6d6a5d375e0b9f729598a26e19b49d57455be6e6fd02646843a9bacc13ce3d7"},
    {0x228fa0,0x25,"7864dd494192dd1bc6e2778477a0dd890dfb15a7ae7d2768ed23ce4921dc152d"},
    {0x224340,0x22,"03f1515ad519b257132b7f2a7401f70bc5c5558a46ea911a01f029707f590e90"},
    {0x224210,0xeb,"2114e9c62aea6eb9a363ec87d3f4f77e6d7df9d75d68d4bc59c574f9a5af98b5"},
    {0x22c840,0x55,"e195f5b995395e37794e167b69f35a4351071bbb1969b0323624e380c29ad38e"},
    {0x111bd0,0x38,"1cac94a47954bacd4e92e579a2b34f70970a5f4dbfac00dba056205b3ea6de03"},
    {0x89ba0,0x1c,"efc9ce2249a4cd42996dcde24d7c6f67c714967551a81ebd24784c61479b9c09"},
    {0x89bd0,0x47,"17be9f30f5870706f3b273d0b86cc21d5958159f4c9b19c19e35548ad0f4ee27"},
    {0x131190,0xd,"0d3ed09b1b254a1431ad870bad1528cc3fcde07a728f6cf621d6529201f91de5"},
    {0x1311b0,0x24,"96e124d1f3bf74ce703626356fba6e0cf6b97535fb57b9ca2e8c985aa30ca63b"},
    {0x14c7a0,0x10,"94fdb24b707e0417c827ff428b87b43e35d771a503084dbc90fcaf277ef86309"},
    {0x14c7c0,0x10,"c66f50ad9fce94c26c624d26f5eb503c760095dc99ac2e511abffc6712bd5753"},
    {0x1e19b,0x5,"fb20738ae4d915146c7e48917d080aa94a419792d054b0cbef95eb6bd1f9c5b6"},
    {0xbd25,0x5,"cc68893872dd003dcc6eaa399e64cfb0cc984518e075c63562633e4c29fc9851"},
    {0x4561,0x5,"989155762eb27c88de4daffb6bd050b1b3e435fbcfedce2615f4e0073ef6f5aa"},
    {0x1b8e2,0x5,"62fffacfe55e1b6b932ba1d581a98c42f80d02db3b75b8881a7234c551c484c6"},
    {0x23cb3,0x5,"51437f515e988923edf0497a63088d6a5bb422b277d8b8321a07560ba177575f"},
    {0xb2b7,0x5,"64c03dded86ce9f2b6b89075b5954e449701ee2bb83ac77f4fecf8c2195bf50f"},
    {0x7dab,0x5,"0fde90202b6768789010f75c36699706d8e5cc8937a07090de2d5aca9f683c04"},
    {0x5a65,0x5,"8d3809109e40eff446b1693d197bbd846a1d74aa6aed03ce9f02e93cbb24a4e9"},
    {0xc66c,0x5,"d0b610a91951a0c66515fc2f1524fc66d081be8def913f5b86e7bb5406ad8dbc"},
    {0x25581,0x5,"12016bb9ec4d24cba32a73ce915a9fde09a56d275e51577bd40687da508707cf"},
    {0x4b6f,0x5,"7534ed320efb8ef9b5295a9b512b491469ee2c8e82fd545905724b9342f1af53"},
    {0x124ea,0x5,"eea0eff87e9d8c2aec18cab73f6d4a9055b6c07ecc82eb8029c7fdf377a1ede9"},
    {0x9674,0x5,"430e6f533f35f4ab216d1ae073b6f2c402f067616e0d896dd5c6274cf6f9f12f"},
    {0xcc52,0x5,"8c76f0ee20d3e4bd83199820165b023a7f5fe558e87132c67b5d3f8e263c86dc"},
    {0x1a7f8,0x5,"1b4f12ad941d5c57fd71371e3e734bcc76e74252f24fa7b09cfce5b5a2a2655d"},
    {0x208fb,0x5,"1d25f907fee0b84617d632864c4b9ffb7ff3c2267af8a54646c1cf359f2acc10"},
    {0x1331d,0x5,"9d72232993ed34eaca4b956763998d411dc431f269b00388a3c1d8e857ed234d"},
    {0x1ea65,0x5,"247c5f5d9572c22ba01f1400af141d481695d76743988887b548da1cd0712b69"},
    {0x20720,0x5,"6db22d8bf236bd81bc93abcbe1ff626ddf599eb4850f9364ea1f4e77495a532f"},
    {0x9a5c,0x5,"c8f2b4e0ddb39b36af9c47bb0adaab630be01b88381005e09fc73485137216fe"},
    {0x12a3f,0x5,"22f1ce707ccfeb03ab5559276494c7045f1804b9820eabeec33d00f6b5832b79"},
    {0x1795e,0x5,"94ca8b3be29653a21239620e3d6928d66d781ba94d7176ac9da8d854cdf551af"},
    {0xbdc5,0x5,"9514894e992f15e5297c31adf885f7704fca66bf0fd325d5dcc941f258661f57"},
};
constexpr std::uint32_t relocations[]{0x4c296,0xae816,0xae866,0xae873,0xae8ac,0xae8c7,0xae8f4,0xaeab0,0xaeab7,0xaeada,0xaeb19,0xaeb2d,0xaeb9f,0xaebcc,0xaec9f,0xaecea,0xaed22,0xaed71,0xaedc2,0xaee17,0xaefb7,0xaefde,0xaf033,0xaf043,0x14c7a9,0x14c7c9,0x224216,0x35a676,0x35a6c1,0x362066,0x36208a,0x3620e2,0x374f06,0x374f1a,0x374f61,0x7f4492,0x7f449f,0x7f44a7,0x7f44b1,0x7f44be,0x7f4da6};

sb::AppendObserver observer{};
unsigned allocations{},finalizations{},network_calls{},appends{},locks{},unlocks{},depth{},increments_in_lock{};
bool gate=true,append_gate=true,deny_at_network=false;
std::array<std::uint32_t,0x88/4> packet{};
std::array<std::uint32_t,0xf00/4> actor{};
std::array<std::uint32_t,0x800/4> object{};
std::array<std::uint32_t,0x200/4> definition{};
std::array<std::uint32_t,8> head_a{},head_b{},node{};
it::Context binding{};
std::uintptr_t arena_base{};
unsigned cases{};
LONG CALLBACK Diagnostic(EXCEPTION_POINTERS* e) {
    if(e && e->ExceptionRecord && e->ContextRecord && e->ExceptionRecord->ExceptionCode!=EXCEPTION_BREAKPOINT) {
        std::fprintf(stderr,"probe fault code=%08lx rva=%08lx access=%08lx\n",e->ExceptionRecord->ExceptionCode,
            e->ContextRecord->Eip-static_cast<DWORD>(arena_base),
            e->ExceptionRecord->NumberParameters>1?static_cast<DWORD>(e->ExceptionRecord->ExceptionInformation[1]):0);
        std::fflush(stderr);
    }
    return EXCEPTION_CONTINUE_SEARCH;
}
bool Current(void*) noexcept{return gate;}
bool AppendCurrent(void*) noexcept{return append_gate;}
std::uint32_t Ptr(const void* value){return static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(value));}
void Put(std::uintptr_t at,std::uintptr_t value){*reinterpret_cast<std::uintptr_t*>(at)=value;}
void Jump(unsigned char* at,std::uintptr_t target){at[0]=0xe9;const auto rel=static_cast<std::uint32_t>(target-reinterpret_cast<std::uintptr_t>(at)-5);std::memcpy(at+1,&rel,4);}
EXCEPTION_DISPOSITION __cdecl NativeFault(EXCEPTION_RECORD*,void*,CONTEXT*,void*){
    // Native executable EH metadata is intentionally not admitted in this arena.
    std::fprintf(stderr,"native fault\n");std::fflush(stderr);TerminateProcess(GetCurrentProcess(),3);return ExceptionContinueSearch;
}
void* __cdecl Allocate(std::size_t size){

    Require(size==0x88 && packet[1]==0,"unexpected/reentrant message allocation");++allocations;packet={};return packet.data();
}
double __cdecl Clock(){return 123.0;}
void __fastcall Lock(void*,void*){++locks;++depth;}
void __fastcall Unlock(void*,void*){Require(depth>0,"unlock without lock");++unlocks;--depth;}
LONG WINAPI Increment(volatile LONG* value){if(depth){++increments_in_lock;}return InterlockedIncrement(value);}
LONG WINAPI Decrement(volatile LONG* value){return InterlockedDecrement(value);}
void __fastcall Finalize(void* value,void*,unsigned flags){
    Require(value==packet.data() && flags==1,"unexpected object finalization");++finalizations;
}
void* __fastcall Transport(void* holder,void*){return *static_cast<void**>(holder);}
void __fastcall Network(void* writer,void*,void* message){
    Require(writer==reinterpret_cast<void*>(binding.writer),"sender transport binding");++network_calls;
    Require(message==packet.data() && packet[1]==3,"native caller/sender/queue references");
    Require(packet[0]==arena_base+0x1155680 && packet[0x70/4]==2 && packet[0x74/4]==1
        && packet[0x78/4]==binding.item_key[0] && packet[0x7c/4]==binding.item_key[1]
        && packet[0x80/4]==0 && packet[0x84/4]==0,"actual native item message payload");
    if(deny_at_network){append_gate=false;}
    const auto claim=observer.claim(reinterpret_cast<void*>(binding.container),message,0x2c6eb7);
    Require(claim.decision!=sb::AppendDecision::unrelated,"native frame/callsite correlated");
    if(claim.decision==sb::AppendDecision::allow){++appends;observer.complete(claim.owner,sb::AppendResult::queued);}
    else{observer.complete(claim.owner,sb::AppendResult::denied);}
    // Native queue consumer releases exactly its separately retained argument.
    it::Consume(message);
}
void Empty(std::array<std::uint32_t,8>& head){head={};head[2]=head[3]=Ptr(head.data());}
void Membership(unsigned container,bool present){
    Empty(head_a);Empty(head_b);node={};
    if(present){auto& head=container?head_b:head_a;head[1]=head[2]=head[3]=Ptr(node.data());node[1]=Ptr(head.data());
        node[4]=binding.item_key[0];node[5]=binding.item_key[1];node[6]=Ptr(object.data());}
}
void Test(unsigned container,std::uint32_t uuid,bool deny){
    binding.item_key[1]=uuid;object[0x18/4]=binding.item_key[0];object[0x1c/4]=uuid;
    Membership(container,true);gate=append_gate=true;deny_at_network=deny;
    const auto before_alloc=allocations,before_free=finalizations,before_append=appends,before_lock=locks;
    it::State state;it::Receipt receipt;

    const auto result=it::Invoke(binding,state,receipt);

    Require(result.native_entered && result.send_observed && result.append_observed==!deny
        && !result.ownership_quarantined,"native item callthrough result");
    Require(result.result==(deny?it::Result::uncertain:it::Result::queued),"native queue result");
    Require(!state.retained_item&&!state.membership_item&&object[0x7c4/4]==1,
        "native actor inventory output ownership balanced");
    Require(allocations==before_alloc+1&&finalizations==before_free+1&&packet[1]==0,
        "native message references balance after queue and caller release");
    Require(appends==before_append+(deny?0:1)&&locks==unlocks&&depth==0&&locks>before_lock,
        "native container lock boundaries and one append");
    ++cases;
}
int Run(int argc,char** argv){
    try{
        AddVectoredExceptionHandler(0,Diagnostic);
        Require(argc==2,"usage: combat_item_probe <exact original/prepared .13 executable>");
        std::ifstream file(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);
        const auto size=file.tellg();Require(file.good()&&size>0&&size<=64*1024*1024,"invalid executable");
        std::vector<unsigned char> bytes(static_cast<std::size_t>(size));file.seekg(0);
        Require(static_cast<bool>(file.read(reinterpret_cast<char*>(bytes.data()),size)),"short image read");

        const auto hash=Digest(bytes.data(),bytes.size());
        Require((hash=="e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8" || (hash=="e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e" || hash=="381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5"))
            ||(hash=="0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d" || (hash=="78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903" || hash=="e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437")),"unreviewed executable");
        auto* image=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x16c0000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
        Require(image!=nullptr,"arena allocation failed");arena_base=reinterpret_cast<std::uintptr_t>(image);
        // Uncopied code traps. Data pages begin zeroed; no client initialization.
        std::memset(image,0xcc,0x1000000);
        for(const auto& segment:segments){
            Require(segment.rva+segment.size<=bytes.size()
                &&Digest(bytes.data()+segment.rva,segment.size)==segment.sha,"primitive hash mismatch");
            std::memcpy(image+segment.rva,bytes.data()+segment.rva,segment.size);
        }

        for(const auto offset:relocations){std::uint32_t value{};std::memcpy(&value,image+offset,4);
            value+=static_cast<std::uint32_t>(arena_base)-0x400000U;std::memcpy(image+offset,&value,4);}
        // The original switch table is data embedded after AE810's code body.
        for(unsigned offset=0xaf0d0;offset<0xaf0e4;offset+=4){std::uint32_t value{};std::memcpy(&value,image+offset,4);
            value+=static_cast<std::uint32_t>(arena_base)-0x400000U;std::memcpy(image+offset,&value,4);}
        for(const auto offset:{0xae816U,0x374f06U,0x35a676U,0x362066U,0x7f4da6U,0x4c296U,0x224216U}){
            Put(arena_base+offset,reinterpret_cast<std::uintptr_t>(&NativeFault));}
        Jump(image+0x8d88e6,reinterpret_cast<std::uintptr_t>(&Allocate));
        Jump(image+0x46b0,reinterpret_cast<std::uintptr_t>(&Clock));
        Jump(image+0x7bee,reinterpret_cast<std::uintptr_t>(&Lock));Jump(image+0x26eb3,reinterpret_cast<std::uintptr_t>(&Unlock));
        Jump(image+0x7a09,reinterpret_cast<std::uintptr_t>(&Transport));Jump(image+0x14128,reinterpret_cast<std::uintptr_t>(&Network));
        Put(arena_base+0x16b0254,reinterpret_cast<std::uintptr_t>(&Increment));Put(arena_base+0x16b0258,reinterpret_cast<std::uintptr_t>(&Decrement));

        binding={arena_base,reinterpret_cast<std::uintptr_t>(actor.data()),arena_base+0x1600100,arena_base+0x1600000,
            reinterpret_cast<std::uintptr_t>(object.data()),reinterpret_cast<std::uintptr_t>(definition.data()),
            {4050960,53},{5802955,30},{980066,0},8,10,Current,AppendCurrent,nullptr};
        Put(arena_base+0x16a2d98,binding.actor);Put(arena_base+0x16ab88c,binding.writer);
        Put(binding.writer,arena_base+0x116036c);Put(binding.writer+0x44,binding.container);Put(binding.container,arena_base+0x114ce9c);
        image[0x16ab894]=1; // Already initialized native sender holder; no global ctor.
        actor[0]=static_cast<std::uint32_t>(arena_base+0x114165c);actor[2]=static_cast<std::uint32_t>(arena_base+0x11417d4);
        actor[0x18/4]=4050960;actor[0x1c/4]=53;actor[0xea4/4]=static_cast<std::uint32_t>(arena_base+0x1141570);
        actor[0x6cc/4]=Ptr(head_a.data());actor[0x734/4]=Ptr(head_b.data());
        object[0]=static_cast<std::uint32_t>(arena_base+0x1142748);object[2]=static_cast<std::uint32_t>(arena_base+0x1600200);
        Put(arena_base+0x1600204,0x7b8);object[0x7c0/4]=static_cast<std::uint32_t>(arena_base+0x1600210);object[0x7c4/4]=1;
        Put(arena_base+0x1600218,arena_base+0x1311b0);
        object[0x10/4]=980066;object[0x68c/4]=Ptr(definition.data());definition[0]=static_cast<std::uint32_t>(arena_base+0x11428f0);
        definition[0xf4/4]=8;definition[0x11c/4]=10;
        Put(arena_base+0x1155684,reinterpret_cast<std::uintptr_t>(&Finalize));Put(arena_base+0x1155688,arena_base+0x1311b0);

        DWORD prior{};Require(VirtualProtect(image,0x1000000,PAGE_EXECUTE_READ,&prior)!=FALSE,"executable primitive arena");
        FlushInstructionCache(GetCurrentProcess(),image,0x1000000);
        Require(it::StartBound(arena_base,reinterpret_cast<it::Send>(image+0x7f4da0)),"item observer install");

        for(unsigned container:{0U,1U}){for(auto uuid:{30U,40U}){Test(container,uuid,false);Test(container,uuid,true);}}
        for(unsigned container:{0U,1U}){
            Membership(container,false);gate=append_gate=true;deny_at_network=false;
            const auto before=allocations;it::State state;it::Receipt receipt;

    const auto result=it::Invoke(binding,state,receipt);

            Require(!result.native_entered&&!result.append_observed&&!result.ownership_quarantined
                &&allocations==before&&object[0x7c4/4]==1,"missing item does not enter or retain");++cases;
        }
        Require(locks==unlocks&&depth==0&&increments_in_lock>0,"real lookup retains while container lock held");
        std::printf("item native conformance: %u cases passed; 48 exact primitives; no live game\n",cases);return 0;
    }catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}
}
}
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char*) noexcept{return false;}
namespace movement {bool VerifyNativeMovementImage(std::uintptr_t&) noexcept{return false;}}
namespace combat::submission {bool RegisterAppendObserver(AppendObserverKind kind,const AppendObserver& value) noexcept{
    if(kind!=AppendObserverKind::item){return false;}observer=value;return true;}}
}
int main(int argc,char** argv){return Run(argc,argv);}
