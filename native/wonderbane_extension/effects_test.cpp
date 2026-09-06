#include "effects.h"
#include <cstdio>
#include <cmath>
#include <cstring>
#include <limits>
#include <map>
#include <vector>
using namespace wonderbane::extension::effects;
namespace {
int failures=0;
void Check(bool ok,const char* label) { if (!ok) { std::fprintf(stderr,"%s\n",label); ++failures; } }
struct Memory {
    std::map<std::uint32_t,std::vector<unsigned char>> cells;
    template<class T> void Put(std::uint32_t p,T value) { auto& b=cells[p]; b.resize(sizeof(T)); std::memcpy(b.data(),&value,sizeof(T)); }
    static bool Read(void* raw,std::uint32_t p,void* out,std::size_t n) {
        auto& m=*static_cast<Memory*>(raw); const auto it=m.cells.find(p);
        if (it==m.cells.end() || it->second.size()!=n) return false;
        std::memcpy(out,it->second.data(),n); return true;
    }
};
}
int main() {
    {
        SubmissionSchedule schedule; Geometry input{},batch{};
        input.count=4;
        const float depths[]{2,8,5,5};
        for(std::size_t i=0;i<input.count;++i) {
            input.quads[i].depth=depths[i];input.quads[i].alpha=.1F*static_cast<float>(i+1);
        }
        Check(schedule.Begin(input),"schedule accepts bounded geometry");
        input.quads[1].depth=100;input.quads[1].alpha=1;
        Check(schedule.TakeBefore(7,batch) && batch.count==1 && batch.quads[0].depth==8
            && batch.quads[0].alpha==.2F,"snapshot is immutable and drains far geometry before native boundary");
        Check(schedule.TakeBefore(5,batch) && !batch.count,"native submission precedes equal-depth effects");
        Check(schedule.TakeBefore(5,batch) && !batch.count,"equal native boundaries do not duplicate effects");
        Check(schedule.TakeBefore(3,batch) && batch.count==2 && batch.quads[0].alpha<batch.quads[1].alpha,
            "equal-depth effects preserve source order");
        Check(schedule.Finish(batch) && batch.count==1 && batch.quads[0].depth==2,"finish drains only remaining geometry");
        Check(!schedule.Finish(batch) && !batch.count,"duplicate finish never replays");
        Check(schedule.Begin(input) && schedule.TakeBefore(7,batch),"restart after completed scene");
        Check(!schedule.TakeBefore(8,batch) && !batch.count && !schedule.Remaining(),"reversed authority cancels pending geometry");
        Check(schedule.RejectedAfterEmission() && schedule.Emitted()==1 && schedule.State()==ScheduleState::rejected,
            "reversed native order honestly retains partial-emission evidence; no claimed rollback");
        Check(!schedule.Finish(batch),"invalid ordering cannot later flush pending geometry");
        Check(schedule.Begin(input),"begin after rejected authority");schedule.Cancel();
        Check(!schedule.TakeBefore(1,batch) && !batch.count,"scene interruption removes all pending work");
        Check(schedule.Begin(input) && !schedule.Begin(input) && !schedule.Remaining(),"duplicate begin cancels rather than replaying");
        input.count=kQuads+1;Check(!schedule.Begin(input),"over-budget geometry rejected");
        input.count=1;input.quads[0].depth=std::numeric_limits<float>::quiet_NaN();
        Check(!schedule.Begin(input),"nonfinite depth rejected");input.quads[0].depth=1;
        input.quads[0].points[0].x=std::numeric_limits<float>::infinity();
        Check(!schedule.Begin(input),"nonfinite geometry rejected");input.quads[0].points[0].x=0;
        input.quads[0].alpha=2;Check(!schedule.Begin(input),"invalid alpha rejected");
        input.quads[0].alpha=.5F;Check(schedule.Begin(input),"valid snapshot recovers");
        Check(!schedule.TakeBefore(std::numeric_limits<float>::infinity(),batch) && !batch.count,
            "unavailable native depth is never inferred");
        Check(!schedule.RejectedAfterEmission() && !schedule.Emitted(),"rejection before first output has no partial emission");
        input.count=kQuads;
        for(auto& quad:input.quads) { quad={};quad.alpha=.5F;quad.depth=4; }
        Check(schedule.Begin(input) && schedule.Finish(batch) && batch.count==kQuads,"maximum budget stays bounded and lossless");
    }
    Config c{}; Check(Validate(c),"defaults valid");
    c.rate=std::numeric_limits<float>::quiet_NaN(); Check(!Validate(c),"reject nonfinite config"); c={};
    Attachment a{0x10000,1,2,0x20000,0x30000,0x40000,3,4,{100,5,-100},true};
    System s; c.flags=7; c.rate=0; c.burst=1; c.burst_count=10;
    s.Step(c,a,1); Check(s.stats.particles==10,"burst applies once");
    s.Step(c,a,1.1); Check(s.stats.particles==10,"unchanged token not repeated");
    Geometry geometry; s.Build(c,{100,5,-90},{1,0,0},{0,1,0},{0,0,-1},geometry);
    Check(geometry.count==10,"production geometry has particles and no degenerate stationary trail");
    for (int i=2;i<=20;++i) s.Step(c,a,1+static_cast<double>(i)/10);
    Check(s.stats.particles==0,"particles expire");
    a.position.x+=2; s.Step(c,a,3.1); Check(s.stats.samples>1,"moving attachment sampled");
    s.Build(c,{100,5,-90},{1,0,0},{0,1,0},{0,0,-1},geometry);
    for (std::size_t i=0;i<geometry.count;++i) for (const auto& p:geometry.quads[i].points)
        Check(std::isfinite(p.x)&&std::isfinite(p.y)&&std::isfinite(p.z),"finite ribbon geometry");
    a.position.x+=100; s.Step(c,a,3.2); Check(s.stats.samples==1,"teleport starts new ribbon");
    ++a.uuid; ++c.burst; s.Step(c,a,3.3); Check(s.stats.samples==1 && s.stats.particles==10,"UUID reuse resets before fresh burst");
    ++a.zone_uuid; s.Step(c,a,3.4); Check(s.stats.particles==0,"zone change clears particles");
    c.particle_budget=3; c.sample_budget=2; ++c.burst; s.Step(c,a,3.5);
    Check(s.stats.particles==3 && s.stats.dropped>=7,"particle budget bounded with diagnostics");
    a.position.x+=10; s.Step(c,a,3.6); Check(s.stats.samples<=2,"trail budget bounded");
    a.valid=false; s.Step(c,a,3.7); Check(!s.stats.particles&&!s.stats.samples&&s.stats.rejected,"missing attachment clears immediately");
    a.valid=true; s.Step(c,a,3.8); Check(!s.stats.particles,"loss does not replay burst");
    c.flags=0; s.Step(c,a,3.9); Check(!s.stats.samples,"disable clears");
    c.flags=7; s.Step(c,a,4); s.Step(c,a,5); Check(s.stats.samples==1,"long frame gap resets");
    s.Clear(); Check(!s.stats.particles&&!s.stats.samples,"cleanup");
    Memory m; constexpr std::uint32_t base=0x400000;
    m.Put(base+23735704U,a.actor); m.Put(base+23735716U,a.actor);
    m.Put(a.actor,base+18093660U); m.Put(base+18093660U+88U,base+41936U);
    m.Put(a.actor+120U,a.type);m.Put(a.actor+124U,a.uuid);m.Put(a.actor+1200U,a.component);
    m.Put(a.component,a.location);m.Put(a.location+32U,a.position);m.Put(a.actor+3392U,a.zone);
    m.Put(a.zone+120U,a.zone_type);m.Put(a.zone+124U,a.zone_uuid);
    const auto resolved=Resolve(Memory::Read,&m,base,0); Check(SameIdentity(resolved,a),"real layout resolver");
    Check(Resolve(Memory::Read,&m,base,1).valid,"selected actor root resolver");
    m.Put(a.actor+124U,a.uuid+1); Check(!SameIdentity(resolved,Resolve(Memory::Read,&m,base,0)),"reused address has different identity");
    m.Put(base+18093660U+88U,0U); Check(!Resolve(Memory::Read,&m,base,0).valid,"unsupported getter rejected");
    return failures ? 1:0;
}
