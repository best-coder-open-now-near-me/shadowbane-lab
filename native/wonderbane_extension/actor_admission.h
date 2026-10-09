#pragma once
#include <cstdint>
namespace wonderbane::extension::actor::admission {
// Local entry blockers only. Remote application history is deliberately absent.
enum Block : std::uint32_t { initiation=1, native_use=2, local_action=4, foreign_target=8, child_cleanup=16, manual_activity=32 };
constexpr std::uint32_t known=63;
}
