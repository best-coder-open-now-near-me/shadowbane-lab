#include "effects.h"
#include <algorithm>
#include <cmath>

namespace wonderbane::extension::effects {
namespace {
Vec Add(Vec a, Vec b) { return {a.x+b.x,a.y+b.y,a.z+b.z}; }
Vec Sub(Vec a, Vec b) { return {a.x-b.x,a.y-b.y,a.z-b.z}; }
Vec Mul(Vec a, float s) { return {a.x*s,a.y*s,a.z*s}; }
float Dot(Vec a, Vec b) { return a.x*b.x+a.y*b.y+a.z*b.z; }
Vec Cross(Vec a, Vec b) { return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x}; }
bool Unit(Vec& a) { const float n = Dot(a,a); if (!std::isfinite(n) || n < 1e-10F) return false; a=Mul(a,1/std::sqrt(n)); return true; }
bool Range(float x, float a, float b) { return std::isfinite(x) && x>=a && x<=b; }
bool Finite(Vec p) { return Range(p.x,-200000,200000) && Range(p.y,-20000,20000) && Range(p.z,-200000,200000); }
}
bool Validate(const Config& c) noexcept {
    return !(c.flags & ~15U) && c.attachment <= 1 && c.burst_count <= 256
        && c.particle_budget >= 1 && c.particle_budget <= kParticles
        && c.sample_budget >= 2 && c.sample_budget <= kSamples
        && Range(c.rate,0,500) && Range(c.lifetime,0.05F,10) && Range(c.speed,0,30)
        && Range(c.size,0.01F,5) && Range(c.trail_lifetime,0.05F,10)
        && Range(c.sample_seconds,0.005F,0.5F) && Range(c.sample_distance,0.01F,10)
        && Range(c.width,0.01F,5) && Range(c.teleport_distance,1,100)
        && Range(c.red,0,1) && Range(c.green,0,1) && Range(c.blue,0,1)
        && Range(c.opacity,0,1) && Range(c.height,-5,10) && Range(c.gravity,-30,30);
}
void System::Clear() noexcept {
    particle_count_=sample_count_=0; emission_=0; active_=false; previous_={};
    stats.particles=stats.samples=stats.quads=0;
}
void System::Step(const Config& c, const Attachment& a, double now) noexcept {
    if (!Validate(c) || !(c.flags&1U) || !a.valid || !Finite(a.position) || !std::isfinite(now)) {
        if ((c.flags&1U) && !a.valid) ++stats.rejected;
        if (active_) ++stats.resets;
        Clear(); burst_=c.burst; return;
    }
    double dt = active_ ? now-time_ : 0;
    const Vec travel = Sub(a.position,previous_.position);
    if (active_ && (!SameIdentity(a,previous_) || dt<0 || dt>0.25
        || Dot(travel,travel)>c.teleport_distance*c.teleport_distance)) {
        ++stats.resets; Clear(); dt=0;
    }
    const Vec origin=Add(a.position,{0,c.height,0});
    if (!active_) { active_=true; sample_time_=now; }
    for (std::size_t i=0;i<particle_count_;) {
        auto& p=particles_[i];
        if (now-p.born>=c.lifetime || i>=c.particle_budget) { p=particles_[--particle_count_]; continue; }
        p.position=Add(p.position,Mul(p.velocity,static_cast<float>(dt)));
        p.velocity.y+=c.gravity*static_cast<float>(dt); ++i;
    }
    std::size_t keep=0;
    for (std::size_t i=0;i<sample_count_;++i) if (now-samples_[i].born<c.trail_lifetime) samples_[keep++]=samples_[i];
    sample_count_=keep;
    while (sample_count_>c.sample_budget) {
        std::move(samples_.begin()+1,samples_.begin()+sample_count_,samples_.begin()); --sample_count_;
    }
    const auto sample=[&](Vec point, double born) {
        if (sample_count_==c.sample_budget) {
            std::move(samples_.begin()+1,samples_.begin()+sample_count_,samples_.begin()); --sample_count_; ++stats.dropped;
        }
        samples_[sample_count_++]={point,born}; sample_time_=born;
    };
    if (c.flags&4U) {
        if (!sample_count_) sample(origin,now);
        else {
            const Vec from=samples_[sample_count_-1].position;
            const Vec delta=Sub(origin,from); const float distance=std::sqrt(Dot(delta,delta));
            if (distance>=c.sample_distance || (now-sample_time_>=c.sample_seconds && distance>0.0001F)) {
                const std::size_t wanted=static_cast<std::size_t>(std::ceil(distance/c.sample_distance));
                const std::size_t steps=(std::min)(wanted,static_cast<std::size_t>(c.sample_budget));
                if (wanted>steps) stats.dropped+=static_cast<std::uint32_t>(wanted-steps);
                const double start=sample_time_;
                for (std::size_t i=1;i<=steps;++i) {
                    const float t=static_cast<float>(i)/static_cast<float>(steps);
                    sample(Add(from,Mul(delta,t)),start+(now-start)*t);
                }
            }
        }
    } else sample_count_=0;
    emission_+=(c.flags&2U) ? c.rate*static_cast<float>(dt) : 0;
    auto emit=static_cast<std::uint32_t>(emission_); emission_-=static_cast<float>(emit);
    if (c.burst!=burst_) { emit+=c.burst_count; burst_=c.burst; }
    const auto capacity=static_cast<std::uint32_t>(c.particle_budget-particle_count_);
    if (emit>capacity) { stats.dropped+=emit-capacity; emit=capacity; }
    const auto random=[&]() { seed_=1664525U*seed_+1013904223U; return static_cast<float>(seed_>>8U)/16777215.0F*2-1; };
    for (std::uint32_t i=0;i<emit;++i) {
        Vec v{random(),random(),random()}; if (!Unit(v)) v={0,1,0};
        particles_[particle_count_++]={origin,Mul(v,c.speed),now};
    }
    time_=now; previous_=a;
    stats.particles=static_cast<std::uint32_t>(particle_count_); stats.samples=static_cast<std::uint32_t>(sample_count_);
}
void System::Build(const Config& c, Vec eye, Vec right, Vec up, Vec forward, Geometry& out) noexcept {
    out.count=0;
    if (!active_ || !Validate(c) || !Unit(right) || !Unit(up) || !Unit(forward)) return;
    const auto quad=[&](Vec a,Vec b,Vec d,Vec e,float alpha,Vec center) {
        if (out.count<out.quads.size()) out.quads[out.count++]={{a,b,d,e},alpha,Dot(Sub(center,eye),forward)};
    };
    for (std::size_t i=0;i<particle_count_;++i) {
        const auto& p=particles_[i]; const Vec r=Mul(right,c.size/2),u=Mul(up,c.size/2);
        quad(Sub(Sub(p.position,r),u),Add(Sub(p.position,u),r),Add(Add(p.position,r),u),Add(Sub(p.position,r),u),
            c.opacity*(1-static_cast<float>((time_-p.born)/c.lifetime)),p.position);
    }
    std::array<Vec,kSamples> sides{};
    for (std::size_t i=0;i<sample_count_;++i) {
        const auto before=i ? i-1:i;
        const auto after=(std::min)(i+1,sample_count_-1);
        Vec tangent=Sub(samples_[after].position,samples_[before].position);
        if (!Unit(tangent)) { ++stats.degenerate; sides[i]=Mul(right,c.width/2); continue; }
        Vec side=Cross(tangent,Sub(eye,samples_[i].position));
        if (!Unit(side)) { side=Cross(tangent,up); if (!Unit(side)) side=right; }
        // Adjacent segments share endpoint offsets, so turns cannot open cracks.
        if (i && Dot(side,sides[i-1])<0) side=Mul(side,-1);
        sides[i]=Mul(side,c.width/2);
    }
    for (std::size_t i=1;i<sample_count_;++i) {
        const auto& a=samples_[i-1]; const auto& b=samples_[i];
        const Vec delta=Sub(b.position,a.position);
        if (Dot(delta,delta)<1e-10F) { ++stats.degenerate; continue; }
        quad(Sub(a.position,sides[i-1]),Add(a.position,sides[i-1]),
            Add(b.position,sides[i]),Sub(b.position,sides[i]),
            c.opacity*(1-static_cast<float>((time_-a.born)/c.trail_lifetime)),
            Mul(Add(a.position,b.position),0.5F));
    }
    std::sort(out.quads.begin(),out.quads.begin()+out.count,[](const Quad& a,const Quad& b){return a.depth>b.depth;});
    stats.quads=static_cast<std::uint32_t>(out.count);
}
} // namespace wonderbane::extension::effects
