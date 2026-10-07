#pragma once
#include <cstdint>
namespace steam_wasd::profile {
inline constexpr char sha256[] = "0e1ba847d03c7f471601d0139c0769cb13f89b0a6a085955a9d09e7545d1e27a";
inline constexpr wchar_t executable[] = L"SBOnlinex64.exe";
inline constexpr std::uintptr_t actor = 0x10504d8, window = 0x104e090, world = 0x104de80;
inline constexpr std::uintptr_t input = 0x104df00, modal = 0x104e118, request = 0x103dd80;
inline constexpr std::uintptr_t update_slot = 0xe29cf0, update = 0xa1e820;
inline constexpr std::uintptr_t window_vtable = 0xe29b60, actor_vtable = 0xd9ec90;
inline constexpr std::uintptr_t move = 0x10dc80, state = 0x10abd0, get_state = 0x10c200;
inline constexpr std::uintptr_t clear_actions = 0x304170, detach = 0x330490, free_node = 0xc975e0;
inline constexpr std::uintptr_t erase_path = 0xd7770, destination = 0x196660, actor_ref = 0x326ac0;
inline constexpr std::uintptr_t connection = 0x5a4a50, send = 0x5a56e0;
inline constexpr std::uintptr_t text_input = 0xdf800, focus = 0x9f1090, inhibited = 0x73c0c0;
inline constexpr std::uintptr_t yaw = 0x105a950;
}
