#ifdef GROUP_UPDATE_TEST
#include "group_updates.cpp"
namespace tr=wonderbane::extension::group_updates;
#else
#include "group_messages.cpp"
namespace tr=wonderbane::extension::group_messages;
#endif
#include <iostream>
#include <fstream>
namespace {
unsigned errors=0,decoded=0,processed=0;std::uint64_t epoch=7;
bool change_scene=false,mutate_sender=false,change_group=false;
std::array<std::uint32_t,48> native_window{},manager{},entry{},actor{};
std::array<std::uint32_t,3> sentinel{},node{};
std::uint32_t world=1;
alignas(4) std::array<char16_t,5> member_name{u'A',u'l',u'i',u'c',u'e'};
void Check(bool ok,const char* label){if(!ok){++errors;std::cerr<<label<<'\n';}}
void __fastcall DecodeOriginal(void*,void*,void*){++decoded;SetLastError(12);}
std::uint32_t __fastcall ProcessOriginal(void* message,void*){
 ++processed;if(change_scene)++epoch;if(change_group)entry[0x14/4]++;
 if(mutate_sender)reinterpret_cast<std::uint32_t*>(message)[0x74/4+2]=reinterpret_cast<std::uint32_t*>(message)[0x74/4+1];
 SetLastError(13);return 99;
}
void* __fastcall DestroyOriginal(void* p,void*,unsigned){return p;}
const tr::Record& Last(){return tr::storage->records[(tr::storage->sequence-1)%tr::kCapacity];}
}
namespace wonderbane::extension {
bool GraphicsExecutableSha256Matches(const char*) noexcept{return false;}
namespace movement {
bool VerifyNativeMovementImage(std::uintptr_t&) noexcept{return false;}
bool ReadNativeMovementLifetime(NativeScene& s) noexcept{s={};s.epoch=epoch;s.identity={42,53};
 s.window=reinterpret_cast<std::uintptr_t>(native_window.data());s.actor=reinterpret_cast<std::uintptr_t>(actor.data());
 s.world=reinterpret_cast<std::uintptr_t>(&world);return true;}
bool NativeMovementLifetimeCurrent(const NativeScene& s) noexcept{return s.epoch&&s.epoch==epoch;}
}
DWORD ReplaceImportAddressSlot(std::uint32_t* p,std::uint32_t old,std::uint32_t value) noexcept{
 return static_cast<std::uint32_t>(InterlockedCompareExchange(reinterpret_cast<LONG*>(p),static_cast<LONG>(value),static_cast<LONG>(old)))==old?ERROR_SUCCESS:ERROR_INVALID_DATA;
}
}
int main(int argc,char** argv){
 auto* image=static_cast<unsigned char*>(VirtualAlloc(nullptr,0x1800000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!image)return 2;
 auto base=reinterpret_cast<std::uintptr_t>(image);
 std::array<std::uint32_t*,3> slots{};std::array<std::uint32_t,3> targets{reinterpret_cast<std::uint32_t>(&DestroyOriginal),reinterpret_cast<std::uint32_t>(&ProcessOriginal),reinterpret_cast<std::uint32_t>(&DecodeOriginal)};
 for(std::size_t i=0;i<3;++i){slots[i]=reinterpret_cast<std::uint32_t*>(base+tr::kTable+tr::kSlots[i]);*slots[i]=targets[i];}
 constexpr unsigned char code[]{0x55,0x8b,0xec,0x8b,0x4d,0x08,0x8b,0x01,0xff,0x75,0x0c,0xff,0x50,0x1c,0x5d,0xc2,0x08,0x00};
 auto* thunk=image+tr::kDecoderReturn-14;std::memcpy(thunk,code,sizeof(code));DWORD old=0;
 if(!VirtualProtect(thunk,sizeof(code),PAGE_EXECUTE_READ,&old)||!FlushInstructionCache(GetCurrentProcess(),thunk,sizeof(code)))return 3;
 using Decoder=void(__stdcall*)(void*,void*);auto decode=reinterpret_cast<Decoder>(thunk);
 Check(tr::StartBound({GetCurrentProcessId(),123456789},base,slots,targets)==ERROR_SUCCESS,"start");
 auto ptr=[](const void* p){return reinterpret_cast<std::uint32_t>(p);};
 *reinterpret_cast<std::uint32_t*>(base+0x16a7bfc)=ptr(native_window.data());
 *reinterpret_cast<std::uint32_t*>(base+0x16a2d98)=ptr(actor.data());
 *reinterpret_cast<std::uint32_t*>(base+0x1389028)=ptr(&world);
 actor[0x18/4]=42;actor[0x1c/4]=53;
 native_window[0x98/4]=ptr(manager.data());manager[0x9c/4]=ptr(sentinel.data());
 sentinel[0]=sentinel[1]=ptr(node.data());node[0]=node[1]=ptr(sentinel.data());node[2]=ptr(entry.data());
 entry[0x10/4]=123;entry[0x14/4]=53;entry[0x74/4]=0x15;
 entry[0x28/4+1]=ptr(member_name.data());entry[0x28/4+2]=entry[0x28/4+3]=ptr(member_name.data())+10;
 std::array<std::uint32_t,48> message{};std::array<std::uint32_t,8> socket{};
 message[0]=static_cast<std::uint32_t>(base+tr::kTable);socket[0]=static_cast<std::uint32_t>(base+0x116019c);
#ifdef GROUP_UPDATE_TEST
 std::array<std::uint32_t,2> key{123,53};std::array<float,3> xyz{70000,100,-50000};
 std::memcpy(entry.data()+0x68/4,xyz.data(),12);
 message[0x68/4]=5;message[0x74/4]=1;message[0x70/4]=1;message[0x90/4]=ptr(key.data());message[0x8c/4]=ptr(xyz.data());
#else
 alignas(4) std::array<char16_t,5> sender{u'A',u'l',u'i',u'c',u'e'};
 alignas(4) std::array<char16_t,5> text{u'/',u'c',u'o',u'm',u'e'};
 message[0x70/4]=14;
 message[0x74/4+1]=ptr(sender.data());message[0x74/4+2]=message[0x74/4+3]=ptr(sender.data())+10;
 message[0x8c/4+1]=ptr(text.data());message[0x8c/4+2]=message[0x8c/4+3]=ptr(text.data())+10;
#endif
 decode(message.data(),socket.data());Check(GetLastError()==12,"decode native LastError");
 Check(tr::ProcessHook(message.data(),nullptr)==99&&GetLastError()==13,"native Process result and LastError");
 Check(tr::storage->sequence==3&&Last().flags==15&&Last().decode_sequence==1&&Last().processing_generation==2,"exact receive lineage");
 if(argc==2){std::ofstream out(argv[1],std::ios::binary);out.write(reinterpret_cast<const char*>(tr::storage),sizeof(tr::Storage));Check(bool(out),"ABI frame export");}
#ifdef GROUP_UPDATE_TEST
 Check(Last().payload.rows[0].object==key&&Last().payload.rows[0].xyz==xyz,"copied key and coordinates");
 xyz[0]+=1;Check(Last().payload.rows[0].xyz[0]!=xyz[0],"immutable copied position");xyz[0]-=1;
#else
 Check(Last().payload.sender_units==5&&Last().payload.text_units==5,"copied sender and body");
 decode(message.data(),socket.data());mutate_sender=true;tr::ProcessHook(message.data(),nullptr);mutate_sender=false;
 Check(Last().flags==15&&Last().payload.sender_units==5,"Process native sender mutation cannot rewrite decoded attribution");
 message[0x74/4+2]=ptr(sender.data())+10;
#endif
 decode(message.data(),socket.data());tr::ProcessHook(message.data(),nullptr);
 Check(Last().flags==15&&Last().processing_generation>2,"identical messages have distinct generation");
#ifdef GROUP_UPDATE_TEST
 xyz[0]+=10;decode(message.data(),socket.data());tr::ProcessHook(message.data(),nullptr);
 Check(Last().flags==7,"native no-op or unapplied coordinate update cannot stamp position freshness");xyz[0]-=10;
#else
 decode(message.data(),socket.data());change_group=true;tr::ProcessHook(message.data(),nullptr);change_group=false;entry[0x14/4]--;
 Check(Last().flags==7&&Last().payload.sender_key==tr::Key{},"group change across Process invalidates command authority");
 member_name[0]=u'B';decode(message.data(),socket.data());tr::ProcessHook(message.data(),nullptr);member_name[0]=u'A';
 Check(Last().flags==7,"channel text from a nonmember is never authority");
#endif
 decode(message.data(),socket.data());++epoch;tr::ProcessHook(message.data(),nullptr);Check(Last().flags==3,"old scene decode not attributed");
 decode(message.data(),socket.data());change_scene=true;tr::ProcessHook(message.data(),nullptr);change_scene=false;Check(Last().flags==1,"Process scene change invalidates attribution");
 decode(message.data(),socket.data());tr::DestroyHook(message.data(),nullptr,0);tr::ProcessHook(message.data(),nullptr);Check(!(Last().flags&4),"destroyed ticket cannot replay");
 const auto seq=tr::storage->sequence;socket[7]=1;decode(message.data(),socket.data());socket[7]=0;Check(tr::storage->sequence==seq,"inactive socket ignored");
#ifdef GROUP_UPDATE_TEST
 message[0x70/4]=11;tr::Payload payload{};Check(!tr::Snapshot(message.data(),payload),"partial oversized roster not published");
#else
 message[0x70/4]=1;auto before=processed;tr::ProcessHook(message.data(),nullptr);Check(processed==before+1&&tr::storage->sequence==seq,"other channels call through without command evidence");
 message[0x70/4]=14;message[0x74/4+2]=message[0x74/4+1];tr::Payload payload{};Check(!tr::Snapshot(message.data(),payload),"empty sender never adopts local Process fallback");
#endif
 tr::Stop();for(std::size_t i=0;i<3;++i)Check(*slots[i]==targets[i],"original callbacks restored");
 VirtualFree(image,0,MEM_RELEASE);return static_cast<int>(errors);
}
