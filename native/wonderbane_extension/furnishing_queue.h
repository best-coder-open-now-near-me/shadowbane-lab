#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace wonderbane::extension::furnishing {
// Queue receipts own no native references. The renderer retains its private tree
// until ReleaseAllowed(), AND until its matching outer drain/shader use is over.
// Calls are serialized on the verified native owner. No client code is patched.
class QueueReceipt {
public:
    static constexpr std::size_t kMaxNodes = 8192, kMaxRenders = 64;
    using Address = std::uint32_t;
    struct Pool { Address begin = 0; std::uint32_t capacity = 0, used = 0; };
    struct Access {
        void* context = nullptr;
        bool (*read)(void*, Address, void*, std::size_t) noexcept = nullptr;
        bool (*admit)(void*) noexcept = nullptr;
        // False includes an uncertain native entry; never retry that erase.
        bool (*erase)(void*, Address queue, Address node) noexcept = nullptr;
        Address wrapper_type = 0;
    };
    enum class State { idle, prepared, entering, submitted, quarantined };
    explicit QueueReceipt(Access access) noexcept : access_(access) {}
    QueueReceipt(const QueueReceipt&) = delete;
    QueueReceipt& operator=(const QueueReceipt&) = delete;
    bool Prepare(Address queue, Pool, const Address* renders, std::size_t count,
                 std::uint64_t ticket) noexcept;
    bool Enter() noexcept;
    bool Complete(Pool) noexcept;
    // Caller proves matching outer drain completion (or no drain has begun).
    // The opaque ticket must still match the owner/context/frame generation.
    bool Retire(std::uint64_t ticket) noexcept;
    void CancelPrepared() noexcept;
    void Quarantine() noexcept { state_ = State::quarantined; }
    State CurrentState() const noexcept { return state_; }
    bool ReleaseAllowed() const noexcept { return state_ == State::idle; }
    std::size_t SubmittedCount() const noexcept { return receipt_count_; }
private:
    struct RawNode { Address color, parent, left, right, payload; };
    static_assert(sizeof(RawNode) == 20);
    struct Node { Address address = 0; RawNode raw{}; std::uint32_t black_height = 0;
                  std::size_t left = kMaxNodes, right = kMaxNodes; };
    struct Snapshot {
        Address head = 0, root = 0, first = 0, last = 0;
        std::uint32_t count = 0;
        std::array<Node, kMaxNodes> nodes{};
        std::array<std::size_t, kMaxNodes> order{};
    };
    struct Entry { Address node = 0, wrapper = 0, render = 0; bool removed = false; };
    bool Admitted() const noexcept;
    bool Read(Address, void*, std::size_t) const noexcept;
    template<class T> bool Read(Address at, T& out) const noexcept {
        return Read(at, &out, sizeof(out));
    }
    bool Capture(Snapshot&) noexcept;
    bool PoolValid(Pool) const noexcept;
    bool Private(Address) const noexcept;
    bool Wrapper(Address, Address&) const noexcept;
    bool SameRemainder(const Snapshot&) const noexcept;
    bool CurrentEntries(const Snapshot&) const noexcept;
    void Reset() noexcept;
    Access access_{};
    State state_ = State::idle;
    Address queue_ = 0;
    Pool before_pool_{};
    std::uint64_t ticket_ = 0;
    std::array<Address, kMaxRenders> renders_{};
    std::size_t render_count_ = 0, receipt_count_ = 0;
    std::array<Entry, kMaxRenders> receipt_{};
    // Persisted scratch avoids large owner-thread stacks and per-frame allocation.
    Snapshot before_{}, current_{};
};
}
