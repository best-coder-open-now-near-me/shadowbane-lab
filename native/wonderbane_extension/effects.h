#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace wonderbane::extension::effects {
constexpr std::size_t kParticles = 1024, kSamples = 256, kQuads = kParticles + kSamples;
struct Vec { float x{}, y{}, z{}; };
struct Config {
    std::uint32_t flags = 0; // enabled=1, emitter=2, ribbon=4, additive=8
    std::uint32_t attachment = 0; // 0 local actor root; 1 selected actor root
    std::uint32_t burst = 0; // monotonically changing button token
    std::uint32_t burst_count = 48;
    std::uint32_t particle_budget = 512, sample_budget = 128;
    float rate = 40, lifetime = 1.5F, speed = 2, size = 0.25F;
    float trail_lifetime = 2, sample_seconds = 0.025F, sample_distance = 0.2F;
    float width = 0.35F, teleport_distance = 30;
    float red = 0.25F, green = 0.8F, blue = 1, opacity = 0.7F;
    float height = 0, gravity = -1;
};
static_assert(sizeof(Config) == 84);
bool Validate(const Config&) noexcept;
struct Attachment {
    std::uint32_t actor{}, type{}, uuid{}, component{}, location{}, zone{}, zone_type{}, zone_uuid{};
    Vec position{};
    bool valid = false;
};
bool SameIdentity(const Attachment&, const Attachment&) noexcept;
struct Stats { std::uint32_t particles{}, samples{}, dropped{}, rejected{}, resets{}, degenerate{}, quads{}, render_rejected{}; };
struct Quad { Vec points[4]{}; float alpha{}, depth{}; };
struct Geometry { std::array<Quad, kQuads> quads{}; std::size_t count{}; };
class System {
public:
    void Clear() noexcept;
    void Step(const Config&, const Attachment&, double now) noexcept;
    void Build(const Config&, Vec eye, Vec right, Vec up, Vec forward, Geometry&) noexcept;
    Stats stats{};
private:
    struct Particle { Vec position{}, velocity{}; double born{}; };
    struct Sample { Vec position{}; double born{}; };
    std::array<Particle, kParticles> particles_{};
    std::array<Sample, kSamples> samples_{};
    std::size_t particle_count_{}, sample_count_{};
    Attachment previous_{};
    double time_{}, sample_time_{};
    float emission_{};
    std::uint32_t burst_{}, seed_ = 1;
    bool active_ = false;
};
// Production resolver and test seam: bounded reads, never calls game methods.
using Reader = bool(*)(void*, std::uint32_t, void*, std::size_t);
Attachment Resolve(Reader, void*, std::uint32_t base, std::uint32_t selection) noexcept;
} // namespace wonderbane::extension::effects
