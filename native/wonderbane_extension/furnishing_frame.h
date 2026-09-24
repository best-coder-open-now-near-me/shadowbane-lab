#pragma once
#include <cstdint>
namespace wonderbane::extension::furnishing {
// Owner/context serialized, independent of renderer Stop. One main clear grants
// at most one outer drain. Nested drains never acquire or retire its receipt.
class FrameGate {
public:
    void Clear(bool main) noexcept {
        if(depth_) { broken_=true; }
        ready_=main&&!broken_; ticket_=0;
    }
    std::uint64_t Enter() noexcept {
        if(depth_==UINT32_MAX) { broken_=true; return 0; }
        if(++depth_!=1 || broken_ || !ready_) { return 0; }
        ready_=false;
        if(sequence_==UINT64_MAX) { broken_=true; return 0; }
        ticket_=++sequence_; return ticket_;
    }
    std::uint64_t Leave(bool shader_clear) noexcept {
        if(!depth_) { broken_=true; return 0; }
        if(--depth_) { return 0; }
        const auto ticket=ticket_; ticket_=0;
        if(!shader_clear) { broken_=true; }
        return broken_?0:ticket;
    }
    void Invalidate() noexcept { ready_=false; if(depth_) { broken_=true; } }
    bool Broken() const noexcept { return broken_; }
    bool Draining() const noexcept { return depth_!=0; }
private:
    std::uint64_t sequence_=0,ticket_=0;
    std::uint32_t depth_=0;
    bool ready_=false,broken_=false;
};
}
