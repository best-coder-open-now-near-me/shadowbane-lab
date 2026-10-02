#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace wonderbane::extension::combat::inventory {
using Key = std::array<std::uint32_t, 2>;
inline constexpr std::size_t kMaxNodes = 512;
inline constexpr std::size_t kMaxItems = 16;
struct Context {
    std::uintptr_t image{}, actor{};
    Key actor_key{}, template_key{};
    // Retained canonical actor, verified outermost owner thread/scene/Grant.
    // Must not initiate native work or pump messages.
    bool (*current)(void*) noexcept = nullptr;
    void* owner{};
    bool operator==(const Context&) const = default;
};
struct Facts {
    Key item_key{}, template_key{};
    std::uintptr_t item_address{}, template_address{};
    std::uint32_t quantity{}, type{}, flags{};
    bool operator==(const Facts&) const = default;
};
enum class Result : std::uint32_t { unknown, available, no_eligible };
struct Observation {
    Result result = Result::unknown;
    std::array<Facts, kMaxItems> items{};
    std::uint32_t count{};
    std::uint64_t generation{};
    bool operator==(const Observation&) const = default;
};
struct Access;
// Caller-owned, noncopyable, persistent across native faults. References are not
// serialized into publications. Explicit Release is required before reuse.
// Quarantine is irreversible: uncertain native retain/release is never retried.
class State {
public:
    State() noexcept = default;
    State(const State&) = delete;
    State& operator=(const State&) = delete;
    bool Quarantined() const noexcept { return quarantined_; }
private:
    std::array<void*, kMaxItems> retained_{};
    void* scratch_{};
    Context context_{};
    Observation observation_{};
    std::uintptr_t release_{};
    std::uint64_t generation_{};
    bool occupied_{}, quarantined_{};
    friend struct Access;
};
// Exact prepared .13 image qualification; no hooks, startup or native actions.
bool Start(std::uintptr_t image) noexcept;
bool Ready() noexcept;
// Owner-thread only. Bounded complete discovery in both actor-owned trees,
// native locked owned lookup, complete recapture, final actor/fence checks.
// Unknown is not absence. No-eligible requires complete stable discovery in both
// containers and remains revalidatable; it says nothing about unloaded/server
// inventory or effect absence. Only exact ArcItem type8/flags0xA positive-quantity
// candidates for the configured template are retained and published.
Result Observe(const Context&, State&, Observation&) noexcept;
bool Revalidate(const Context&, State&, const Observation&) noexcept;
// Uses only saved native release and owned slots, so stale context can teardown.
// A true result proves local references released, not item/effect completion.
bool Release(State&) noexcept;
}
