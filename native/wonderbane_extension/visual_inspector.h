#pragma once
#include "effects.h"
#include <array>
#include <cstdint>
namespace wonderbane::extension::visual {
constexpr unsigned kNodes=128;
struct Node { std::uint32_t address{},parent{},resource{},reserved{}; };
struct Snapshot {
    std::uint32_t status=1,type=0,uuid=0,count=0;
    std::array<Node,kNodes> nodes{};
};
// status: 0 captured, 1 unavailable, 2 unsupported tree, 3 changed during capture.
Snapshot Capture(effects::Reader,void*,std::uint32_t base,std::uint32_t selection) noexcept;
void Start(std::uint32_t base) noexcept;
void Stop() noexcept;
void Poll(bool scene_available) noexcept;
}
