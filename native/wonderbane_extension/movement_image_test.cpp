#include <Windows.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <vector>
#include <cstring>
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
  std::uintptr_t base=0;Check(wm::VerifyNativeMovementImage(base) && base==reinterpret_cast<std::uintptr_t>(tested_image),"production disk and relocated loaded-text verifier accepts");
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
