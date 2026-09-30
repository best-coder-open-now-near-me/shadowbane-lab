#include "combat_target_policy.h"
#undef NDEBUG
#include <cassert>
#include <limits>
namespace policy = wonderbane::extension::combat::policy;
namespace movement = wonderbane::extension::movement;
namespace {
std::uintptr_t image{};
HWND window{};
movement::NativeScene scene{};
unsigned checks{}, mutate_at{};
bool live = true;
void (*mutation)() = nullptr;
template<class T> void Put(std::uintptr_t at, T value) { std::memcpy(reinterpret_cast<void*>(at), &value, sizeof(value)); }
constexpr std::array<std::uintptr_t, 6> descriptors{0x1373238, 0x13732a8, 0x1373098, 0x1373080, 0x13730b0, 0x1373148};
void Reset() {
    std::memset(reinterpret_cast<void*>(image), 0, 0x10000);
    scene = {}; scene.actor = image + 0x2000; scene.window = image + 0x1000;
    scene.world = image + 0x3000; scene.epoch = 1; scene.identity = {100,53};
    Put(image + 0x16a2d98, scene.actor); Put(image + 0x16a7bfc, scene.window);
    Put(image + 0x1389028, scene.world); Put(scene.actor, image + 0x114165c);
    Put(scene.actor + 0x18, scene.identity);
    Put(scene.window + 0x98, image + 0x4000); Put(image + 0x409c, image + 0x4100);
    Put(image + 0x4100, image + 0x4100); Put(image + 0x4104, image + 0x4100);
    Put(image + 0x6000, image + 0x114165c); Put(image + 0x6018, policy::Key{200,37});
    Put(image + 0x65cc, 80.0f); Put(image + 0x65d0, 100.0f);
    Put(image + 0x6034, image + 0x7000); Put(image + 0x6038, std::uint32_t{3});
    for (std::size_t i = 0; i < descriptors.size(); ++i) {
        Put(image + descriptors[i] + 4, static_cast<std::uint32_t>(1000+i));
    }
    live = true; checks = mutate_at = 0; mutation = nullptr;
}
policy::Outcome Capture(policy::Snapshot& output) {
    return policy::Capture(window, image, scene, reinterpret_cast<void*>(image + 0x6000), {200,37}, output);
}
void Role(std::size_t i, bool value) {
    Put(image + 0x7000, static_cast<std::uint32_t>(1000+i));
    Put(image + 0x7004, image + 0x8000);
    if (i == 5) { Put(image + 0x8000, policy::Key{300,53}); }
    else { Put(image + 0x8004, image + 0x8100); Put(image + 0x8100, static_cast<std::uint8_t>(value)); }
}
void ChangeHealth() { Put(image + 0x65cc, 50.0f); }
void ChangeKey() { Put(image + 0x6018, policy::Key{201,37}); }
void ChangeRole() { Role(1, true); }
void ChangeDescriptor() { Put(image + descriptors[0] + 4, std::uint32_t{1999}); }
}
namespace wonderbane::extension::movement {
bool NativeMovementLifetimeCurrent(const NativeScene&) noexcept {
    ++checks; if (mutation && checks == mutate_at) { mutation(); } return live;
}
}
int main() {
    image = reinterpret_cast<std::uintptr_t>(VirtualAlloc(nullptr, 0x1800000, MEM_RESERVE|MEM_COMMIT, PAGE_READWRITE));
    assert(image);
    window = CreateWindowExW(0,L"STATIC",L"policy",0,0,0,1,1,HWND_MESSAGE,nullptr,GetModuleHandleW(nullptr),nullptr);
    assert(window); policy::Snapshot output{};
    Reset(); assert(Capture(output) == policy::Outcome::eligible); const auto total_checks = checks;
    assert(output.object.address == image + 0x6000 && output.object.key == (policy::Key{200,37}));
    for (std::size_t i = 0; i < descriptors.size(); ++i) {
        Reset(); Role(i,true); assert(Capture(output) == policy::Outcome::protected_target);
        Reset(); Role(i,false); assert(Capture(output) == ((i==0 || i==5) ? policy::Outcome::protected_target : policy::Outcome::eligible));
        Put(image+0x7008, static_cast<std::uint32_t>(1000+i));
        Put(image+0x700c, image+0x8000); assert(Capture(output) == policy::Outcome::invalid);
    }
    Reset(); Put(image+0x65cc,0.0f); assert(Capture(output)==policy::Outcome::protected_target);
    for (auto value : {std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN(),101.0f}) {
        Reset(); Put(image+0x65cc,value); assert(Capture(output)==policy::Outcome::invalid);
    }
    Reset(); Put(image+0x65d0,0.0f); assert(Capture(output)==policy::Outcome::invalid);
    Reset(); Put(image+0x6000,image+0x1141650); assert(Capture(output)==policy::Outcome::invalid);
    Reset(); Put(image+0x601c,std::uint32_t{53}); assert(Capture(output)==policy::Outcome::invalid);
    Reset(); Put(image+0x6038,std::uint32_t{17}); assert(Capture(output)==policy::Outcome::invalid);
    Reset(); Put(image+0x6034,std::uintptr_t{1}); assert(Capture(output)==policy::Outcome::invalid);
    Reset(); Put(image+descriptors[1]+4,std::uint32_t{1000}); assert(Capture(output)==policy::Outcome::invalid);
    Reset(); Role(1,true); Put(image+0x8100,std::uint8_t{2}); assert(Capture(output)==policy::Outcome::invalid);
    Reset(); Role(1,true); Put(image+0x8004,std::uintptr_t{1}); assert(Capture(output)==policy::Outcome::invalid);
    Reset(); Role(5,true); Put(image+0x8000,policy::Key{200,37}); assert(Capture(output)==policy::Outcome::invalid);
    Reset(); Role(5,true); Put(image+0x8000,policy::Key{}); assert(Capture(output)==policy::Outcome::invalid);
    Reset(); Put(image+0x6034,std::uintptr_t{0}); assert(Capture(output)==policy::Outcome::eligible);
    Reset();
    // Full calibrated capacity is streamed, including the last bucket; duplicate
    // detection cannot be approximated by a keyed first match or prefix scan.
    Put(image+0x6034,image+0x90000); Put(image+0x6038,std::uint32_t{16});
    std::memset(reinterpret_cast<void*>(image+0x90000),0,65536*8);
    Put(image+0x90000+(65536-1)*8,std::uint32_t{1000});
    assert(Capture(output)==policy::Outcome::protected_target);
    Put(image+0x90000,std::uint32_t{1000}); assert(Capture(output)==policy::Outcome::invalid);
    Reset(); Put(image+0x7000,UINT32_MAX); Put(image+0x7004,std::uint32_t{1});
    assert(Capture(output)==policy::Outcome::eligible); // Tombstones have no role payload.
    Reset(); Role(1,true); Put(image+0x8004,image+0x20000);
    DWORD old{}; assert(VirtualProtect(reinterpret_cast<void*>(image+0x20000),4096,PAGE_NOACCESS,&old));
    assert(Capture(output)==policy::Outcome::invalid);
    DWORD ignored{}; assert(VirtualProtect(reinterpret_cast<void*>(image+0x20000),4096,old,&ignored));
    Reset(); live=false; assert(Capture(output)==policy::Outcome::invalid);
    Reset(); Put(image+0x4100,image+0x4200); Put(image+0x4104,image+0x4200);
    Put(image+0x4200,image+0x4100); Put(image+0x4204,image+0x4100); Put(image+0x4208,image+0x4300);
    Put(image+0x4310,policy::Key{200,37}); Put(image+0x4374,std::uint32_t{0x15});
    assert(Capture(output)==policy::Outcome::protected_target);
    for (auto change : {ChangeHealth,ChangeKey,ChangeRole,ChangeDescriptor}) {
        bool rejected_between_passes = false;
        for (unsigned position=1; position<=total_checks; ++position) {
            Reset(); mutation=change; mutate_at=position;
            rejected_between_passes |= Capture(output)==policy::Outcome::invalid;
        }
        assert(rejected_between_passes);
    }
    Reset();
    assert(policy::Capture(nullptr,image,scene,reinterpret_cast<void*>(image+0x6000),{200,37},output)==policy::Outcome::invalid);
    assert(DestroyWindow(window)); assert(VirtualFree(reinterpret_cast<void*>(image),0,MEM_RELEASE));
}
