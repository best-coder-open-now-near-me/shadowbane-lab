#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

namespace wonderbane::extension::actor_effects {
using Key = std::array<std::uint32_t, 2>;
inline constexpr std::size_t kMaxEffects = 256;
enum class Unknown : std::uint32_t {
    none, unavailable, mutation_active, identity, read_fault, geometry,
    unsupported, changed, exhausted
};
enum class ActionClass : std::uint32_t { apply, apply_many, transform, invisible, over_time, deferred, spire };
struct Effect {
    std::uint32_t descriptor_id{}, action_id{}, rank{}, native_class{}, source_tag{};
    std::array<std::uint32_t, 3> source_words{};
    ActionClass action_class{};
    std::uint8_t local_add_suppression{};
    bool operator==(const Effect&) const = default;
};
// Internal borrowed context. The caller retains the canonical actor throughout
// capture/revalidation. current proves the outermost owner-service, process,
// scene, actor registry lifetime and thread; it must never initiate native work.
struct Context {
    std::uintptr_t image{}, actor{};
    Key actor_key{};
    std::uint64_t scene{};
    bool (*current)(void*) noexcept = nullptr;
    void* owner{};
};
struct Snapshot {
    Unknown unknown = Unknown::unavailable;
    Key actor_key{};
    std::uint64_t scene{}, epoch{};
    std::uint32_t count{};
    std::array<Effect, kMaxEffects> effects{};
    bool Complete() const noexcept { return unknown == Unknown::none && epoch != 0 && scene != 0; }
private:
    // Internal seal only; never serialize these addresses. They prevent context
    // substitution and are not a replacement for the retained lifetime proof.
    std::uintptr_t image_identity_{}, actor_identity_{};
    void* owner_identity_{};
    bool (*current_identity_)(void*) noexcept = nullptr;
    friend Unknown Capture(const Context&, Snapshot&) noexcept;
    friend bool Revalidate(const Context&, const Snapshot&) noexcept;
};
// actual_initializer_return must be captured directly inside the exported
// initializer, before forwarding here. Late installation is never supported.
bool StartAtBootstrap(std::uintptr_t image, std::uintptr_t actual_initializer_return) noexcept;
bool Ready() noexcept;
Unknown Capture(const Context&, Snapshot&) noexcept;
bool Revalidate(const Context&, const Snapshot&) noexcept;
// Normalize only this process's immutable owned CALL bytes. The shared image
// verifier must invoke this alongside existing observer normalizers.
bool NormalizeOwnedCode(std::uintptr_t image, std::uint32_t text_rva,
    std::span<std::uint8_t> code, std::span<const std::uint8_t> disk) noexcept;
}
