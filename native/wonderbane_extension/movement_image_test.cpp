#include <Windows.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <vector>
#include <cstring>
#include <cmath>
#include "movement_controls.h"
#include "door_lifetime_bindings.h"
#include "world_map_client_layout.h"
#include "import_hook.h"
namespace {
std::wstring tested_path;
void* tested_image=nullptr;
DWORD WINAPI TestModulePath(HMODULE,wchar_t* out,DWORD capacity){
 if(tested_path.size()>=capacity)return capacity;
 std::memcpy(out,tested_path.c_str(),(tested_path.size()+1)*sizeof(wchar_t));
 return static_cast<DWORD>(tested_path.size());
}
HMODULE WINAPI TestModuleHandle(LPCWSTR){return static_cast<HMODULE>(tested_image);}
}
#include "terrain_mask_refresh.cpp"
#define GetModuleFileNameW TestModulePath
#define GetModuleHandleW TestModuleHandle
#include "movement_native_image.cpp"
#include "movement_boundary_trace.cpp"
#undef GetModuleFileNameW
#undef GetModuleHandleW
namespace wm=wonderbane::extension::movement;
namespace we=wonderbane::extension;
namespace {
int failures=0;
void Check(bool ok,const char* message){if(!ok){++failures;std::cerr<<message<<'\n';}}
std::vector<unsigned char> Read(const wchar_t* path){
 std::ifstream f(std::filesystem::path(path),std::ios::binary|std::ios::ate);
 if(!f)return {};
 const auto size=f.tellg();if(size<=0 || size>64*1024*1024)return {};
 std::vector<unsigned char> b(static_cast<std::size_t>(size));f.seekg(0);
 if(!f.read(reinterpret_cast<char*>(b.data()),size))return {};return b;
}
// Execute the reviewed leaf intersection in this owned fixture only. No entry
// point, imports, client thread, world, window or network subsystem is started.
void NativeDoorCollectionBindings() {
 const auto base=reinterpret_cast<std::uintptr_t>(tested_image);
 for(const auto& group : {wm::kDoorAppendBindings,wm::kDoorResetBindings,wm::kDoorLoadBindings}) {
  for(const auto binding : group) {
   std::uint32_t original=0;
   std::memcpy(&original,reinterpret_cast<const void*>(base+binding.slot),sizeof(original));
   Check(original==base+binding.original,"reviewed door collection slot and original match relocated native image");
  }
 }
}
void NativeDoorTriangleContract() {
 using Point=wm::GroundPoint;
 using Intersect=int (__cdecl*)(const Point*,const Point*,const Point*,const Point*,const Point*,float*,float*,float*);
 auto* code=static_cast<unsigned char*>(tested_image)+0x120e10;
 DWORD protection=0;
 if(!VirtualProtect(code,0x1a4,PAGE_EXECUTE_READ,&protection)) {
  Check(false,"native triangle executable page protection");return;
 }
 FlushInstructionCache(GetCurrentProcess(),code,0x1a4);
 const auto intersect=reinterpret_cast<Intersect>(code);
 const Point origin{0,1,0}, direction{0,0,-1};
 const Point a{-2,-1,-2}, b{2,-1,-2}, c{0,3,-2};
 float distance=0,u=0,v=0;
 Check(intersect(&origin,&direction,&a,&b,&c,&distance,&u,&v)!=0
  && std::abs(distance-2)<.00001F && u>=0 && v>=0 && u+v<=1,
  "reviewed triangle returns ray distance and scalar barycentrics");
 const Point reversed{0,0,1};
 Check(intersect(&origin,&reversed,&a,&b,&c,&distance,&u,&v)!=0 && distance<0,
  "leaf triangle can return a negative hit; caller must enforce forward near threshold");
 const Point outside{1.8F,1,0};
 Check(intersect(&outside,&direction,&a,&b,&c,&distance,&u,&v)==0,
  "triangle miss inside its bounding box is rejected");
 const Point parallel{1,0,0};
 Check(intersect(&origin,&parallel,&a,&b,&c,&distance,&u,&v)==0,
  "parallel ray rejected by actual native leaf");
 const Point shifted_origin{100,11,-200}, shifted_a{98,9,-202},
  shifted_b{102,9,-202}, shifted_c{100,13,-202};
 Check(intersect(&shifted_origin,&direction,&shifted_a,&shifted_b,&shifted_c,&distance,&u,&v)!=0
  && std::abs(distance-2)<.00001F,"native leaf distance preserves common-frame translation");
 Check(VirtualProtect(code,0x1a4,protection,&protection)!=0,"restore native triangle page protection");
}
void NativeDispatcherContract() {
 // Execute the actual .22/.23 default branch and reconstructed original stack
 // frame, replacing only its legacy handler continuation in this owned arena.
 // No client imports, world, UI, network or message handlers are invoked.
 auto* base=static_cast<unsigned char*>(tested_image);
 auto* continuation=base+0x7ca9c6;
 std::array<unsigned char,6> original{};
 std::memcpy(original.data(),continuation,original.size());
 const std::array<unsigned char,6> returned{0xb0,0x01,0x8b,0xe5,0x5d,0xc3};
 std::memcpy(continuation,returned.data(),returned.size());
 DWORD text_protection=0,patch_protection=0,discard=0;
 const bool text=VirtualProtect(continuation,returned.size(),PAGE_EXECUTE_READ,&text_protection)!=0;
 const bool patch=VirtualProtect(base+0x1790000,0x1000,PAGE_EXECUTE_READ,&patch_protection)!=0;
 Check(text&&patch,"owned dispatcher executable protections");
 if(text&&patch){
  FlushInstructionCache(GetCurrentProcess(),continuation,returned.size());
  FlushInstructionCache(GetCurrentProcess(),base+0x1790000,0x1000);
  using Dispatch=bool (__cdecl*)(const void*,void*);
  const auto dispatch=reinterpret_cast<Dispatch>(base+0x7ca9c0);
  // .23 reserves 0x12f2..0x1311 for title commands; execute both ordinary
  // neighbors while leaving that real UI/network path uninvoked.
  for(const auto action:{0U,0xeaU,0x334U,0x1000U,0x12c9U,0x12d5U,0x12f1U,0x1312U,0xffffffffU}){
   const std::array<std::uint32_t,9> message{action};
   Check(dispatch(message.data(),base),"actual dispatcher retains ordinary cdecl action frame");
  }
 }
 if(text){Check(VirtualProtect(continuation,returned.size(),text_protection,&discard)!=0,
                "restore dispatcher continuation protection");}
 if(patch){Check(VirtualProtect(base+0x1790000,0x1000,patch_protection,&discard)!=0,
                 "restore added dispatcher protection");}
 std::memcpy(continuation,original.data(),original.size());
}
void Mapped(const std::vector<unsigned char>& bytes){
 const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(bytes.data());
 const auto* nt=reinterpret_cast<const IMAGE_NT_HEADERS32*>(bytes.data()+dos->e_lfanew);
 tested_image=VirtualAlloc(nullptr,nt->OptionalHeader.SizeOfImage,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
 Check(tested_image!=nullptr,"mapped image allocation");if(!tested_image)return;
 auto* base=static_cast<unsigned char*>(tested_image);
 std::memcpy(base,bytes.data(),nt->OptionalHeader.SizeOfHeaders);
 const auto* sections=IMAGE_FIRST_SECTION(nt);
 for(unsigned i=0;i<nt->FileHeader.NumberOfSections;++i)
  if(sections[i].SizeOfRawData)std::memcpy(base+sections[i].VirtualAddress,bytes.data()+sections[i].PointerToRawData,sections[i].SizeOfRawData);
 const auto dir=nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC];
 const auto delta=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(base)-nt->OptionalHeader.ImageBase);
 for(std::size_t at=dir.VirtualAddress;at<dir.VirtualAddress+dir.Size;){
  const auto* block=reinterpret_cast<const IMAGE_BASE_RELOCATION*>(base+at);
  for(std::size_t e=at+8;e<at+block->SizeOfBlock;e+=2){
   std::uint16_t entry{};std::memcpy(&entry,base+e,2);
   if((entry>>12)==IMAGE_REL_BASED_HIGHLOW){
    auto* p=base+block->VirtualAddress+(entry&0xfff);std::uint32_t value{};
    std::memcpy(&value,p,4);value+=delta;std::memcpy(p,&value,4);
   }
  }
  at+=block->SizeOfBlock;
 }
}
}
int wmain(int argc,wchar_t** argv){
 if(argc==1){std::cerr<<"reviewed private original/prepared executable paths required\n";return 77;}
 if(argc!=3){std::cerr<<"requires original and prepared reviewed executable paths\n";return 2;}
 FILETIME c{},e{},k{},u{};GetProcessTimes(GetCurrentProcess(),&c,&e,&k,&u);
 const we::ProcessIdentity identity{GetCurrentProcessId(),(std::uint64_t{c.dwHighDateTime}<<32)|c.dwLowDateTime};
 for(int n=1;n<=2;++n){
  const auto bytes=Read(argv[n]);Check(!bytes.empty() && wm::ReviewedImage(bytes),"original/prepared whole-file contract accepted");
  if(bytes.empty() || !wm::ReviewedImage(bytes))return 1;
  Check(wm::ReviewedDigest(bytes)==(n==1),"argument identifies original versus exact prepared transformation");
  tested_path=argv[n];Mapped(bytes);if(!tested_image)return 1;
  std::uintptr_t base=0;
  const bool authenticated=wm::VerifyNativeMovementImage(base)
   && base==reinterpret_cast<std::uintptr_t>(tested_image);
  Check(authenticated,"production disk and relocated loaded-text verifier accepts");
  if(!authenticated) {
   VirtualFree(tested_image,0,MEM_RELEASE);tested_image=nullptr;return 1;
  }
  wm::NativeMovementImageLayout layout{};
  Check(wm::VerifyNativeMovementImageLayout(base,layout),"production verifier publishes authenticated image layout");
  auto* mapped=static_cast<unsigned char*>(tested_image);
  const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(mapped);
  auto* nt=reinterpret_cast<IMAGE_NT_HEADERS32*>(mapped+dos->e_lfanew);
  Check(layout.image_size==nt->OptionalHeader.SizeOfImage
   && layout.section_count==nt->FileHeader.NumberOfSections,"published layout matches mapped exact image");
  Check(we::ReviewedWorldMapLayout(*nt,IMAGE_FIRST_SECTION(nt)+6,&layout),
   "production world map startup layout accepts authenticated original/prepared image");
  const auto free_slot=we::FindImportAddressSlot(mapped,layout.image_size,"MSVCRT.dll","free");
  Check(reinterpret_cast<std::uintptr_t>(free_slot)==base+0x16b0504,
   "lifetime import binding uses authenticated size for the real image");
  if(layout.image_size!=0x1766000U){
   Check(we::FindImportAddressSlot(mapped,0x1766000U,"MSVCRT.dll","free")==nullptr,
    "former hardcoded lifetime bound is rejected on expanded image");
   Check(!we::ReviewedWorldMapLayout(*nt,IMAGE_FIRST_SECTION(nt)+6,nullptr),
    "expanded world map layout requires authenticated file identity");
  }
  const auto image_size=nt->OptionalHeader.SizeOfImage;
  nt->OptionalHeader.SizeOfImage^=0x1000U;
  wm::NativeMovementImageLayout refused{123,9};std::uintptr_t refused_base=123;
  Check(!wm::VerifyNativeMovementImageLayout(refused_base,refused)
   && !refused_base && !refused.image_size && !refused.section_count,
   "changed loaded header revokes the entire layout proof");
  nt->OptionalHeader.SizeOfImage=image_size;
  if(layout.section_count==9){
   bool title_menu_patch=false;
   Check(wm::ReviewedImage(bytes,&title_menu_patch),"exact file selects its mutable-data profile");
   Check(layout.added_patch_sections_verified,".22 publishes sealed loaded patch sections");
   for(const auto rva:{0x178f010U,0x1790180U,0x1790140U,0x1790154U,0x179080cU}){
    mapped[rva]^=1;
    Check(!wm::VerifyNativeMovementImage(base),"added code/constants/padding mutations rejected");
    mapped[rva]^=1;
   }
   for(const auto rva:{0x179010aU,0x179010bU,0x1790122U,0x1790123U,0x1790150U,0x1790153U,
                       0x1790800U,0x179080bU}){
    mapped[rva]^=1;
    Check(wm::VerifyNativeMovementImage(base),"reviewed mutable patch data remains usable");
    mapped[rva]^=1;
   }
   for(const auto rva:{0x1790c20U,0x1790c21U,0x1790c22U,0x1790c23U}){
    mapped[rva]^=1;
    Check(wm::VerifyNativeMovementImage(base)==title_menu_patch,
     "title row counter is mutable only for the exact .23 original/prepared pair");
    mapped[rva]^=1;
   }
   for(const auto rva:{0x1790c1fU,0x1790c24U,0x1790e40U,0x1790e82U}){
    mapped[rva]^=1;
    Check(!wm::VerifyNativeMovementImage(base),"title counter neighbors and dispatcher code remain sealed");
    mapped[rva]^=1;
   }
   auto* section=IMAGE_FIRST_SECTION(nt)+8;
   section->Characteristics^=IMAGE_SCN_MEM_WRITE;
   Check(!wm::VerifyNativeMovementImage(base),"added loaded section header drift rejected");
   section->Characteristics^=IMAGE_SCN_MEM_WRITE;
   NativeDispatcherContract();
   Check(wm::VerifyNativeMovementImage(base),"owned dispatcher fixture restores exact loaded code");
  }
  NativeDoorCollectionBindings();
  NativeDoorTriangleContract();
  we::image_base=0;Check(we::VerifyBinding(identity)==ERROR_SUCCESS,"production update gate accepts reviewed prepared bootstrap");
  auto* terrain_image=static_cast<std::uint8_t*>(tested_image);
  we::StartTerrainMaskRefresh(terrain_image,0x1766000U,"feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff");
#if !defined(WONDERBANE_EXTENSION_DIAGNOSTICS_ONLY)
  Check(std::strstr(we::TerrainMaskRefreshStatusJson(),"active")!=nullptr,"actual shared terrain repair installed before movement");
  Check(wm::VerifyNativeMovementImage(base) && we::VerifyBinding(identity)==ERROR_SUCCESS,"movement accepts actual fully owned terrain repair");
  for(const auto& patch:we::terrain_mask_review::kPatches){
   terrain_image[patch.rva]=patch.original;
   Check(!wm::VerifyNativeMovementImage(base),"partial owned terrain repair rejected");
   terrain_image[patch.rva]=static_cast<std::uint8_t>(patch.replacement^0xffU);
   Check(!wm::VerifyNativeMovementImage(base),"changed owned terrain repair byte rejected");
   terrain_image[patch.rva]=patch.replacement;
  }
  terrain_image[0x2000]^=1;Check(!wm::VerifyNativeMovementImage(base),"unrelated mutation rejected while terrain repair owned");terrain_image[0x2000]^=1;
#else
  Check(std::strstr(we::TerrainMaskRefreshStatusJson(),"disabled")!=nullptr,"diagnostics terrain repair stays disabled");
  Check(wm::VerifyNativeMovementImage(base),"diagnostics stock code accepted");
#endif
  we::StopTerrainMaskRefresh();
  Check(wm::VerifyNativeMovementImage(base),"restored original terrain code accepted");
  for(const auto& patch:we::terrain_mask_review::kPatches)terrain_image[patch.rva]=patch.replacement;
  Check(!wm::VerifyNativeMovementImage(base),"unowned matching terrain patch set rejected");
  for(const auto& patch:we::terrain_mask_review::kPatches)terrain_image[patch.rva]=patch.original;
  auto changed=bytes;changed[0x2000]^=1;Check(!wm::ReviewedImage(changed),"unrelated code patch rejected");
  changed=bytes;changed.back()^=1;Check(!wm::ReviewedImage(changed),"unrelated file data patch rejected");
  changed=bytes;changed.resize(1024);Check(!wm::ReviewedImage(changed),"truncated image rejected");
  if(n==2)for(const auto& patch:wm::bootstrap_patches){
   changed=bytes;changed[patch.offset]^=1;Check(!wm::ReviewedImage(changed),"modified bootstrap span rejected");
   changed=bytes;std::memcpy(changed.data()+patch.offset,patch.original.data(),patch.original.size());
   Check(!wm::ReviewedImage(changed),"partially applied bootstrap rejected");
  }
  auto* loaded=static_cast<unsigned char*>(tested_image);loaded[0x2000]^=1;
  Check(!wm::VerifyNativeMovementImage(base),"loaded text mutation rejected despite valid disk");
  Check(we::VerifyBinding(identity)!=ERROR_SUCCESS,"update gate rejects loaded text mutation");
  loaded[0x2000]^=1;loaded[0x79ab40]^=1;
  Check(!we::VerifyUpdate(),"reviewed update function digest still enforced");
  VirtualFree(tested_image,0,MEM_RELEASE);tested_image=nullptr;we::image_base=0;
 }
 if(!failures)std::cout<<"Executed original/prepared disk authentication, relocated loaded-text and update gate; actual terrain startup ownership and restoration; rejected partial/bootstrap/code/data/truncation/loaded/unowned mutations.\n";
 return failures?1:0;
}
