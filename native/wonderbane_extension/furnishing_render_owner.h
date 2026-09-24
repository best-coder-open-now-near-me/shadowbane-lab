#pragma once
#include "furnishing_queue.h"
#include "furnishing_selection.h"
#include <atomic>

namespace wonderbane::extension::furnishing {
// All methods except Close() are owner-thread only.
// One process-persistent owner. Destruction deliberately does not call native
// release: only the proven owner/context and retired receipt authorize that.
class RenderOwner {
public:
    struct Operations {
        void* context = nullptr;
        // Owner includes exact HWND thread and the acquisition graphics context.
        bool (*owner)(void*) noexcept = nullptr;
        bool (*current)(void*, const Selection&) noexcept = nullptr;
        bool (*source)(void*, const Selection&) noexcept = nullptr;
        // Native adapters guard C++/SEH faults. False after entry is uncertain;
        // reference slots remain persisted, and are never retried or overwritten.
        bool (*retain)(void*, Address model, Address* slot) noexcept = nullptr;
        bool (*clone)(void*, Address source_render, Address* slot) noexcept = nullptr;
        bool (*release)(void*, Address* slot) noexcept = nullptr;
        // Confirms an independent private tree and the exact qualified resource,
        // reference, callback, metadata and shader families before exposing it.
        bool (*private_tree)(void*, const Selection&, Address clone, Address* renders,
                             std::size_t capacity, std::size_t* count) noexcept = nullptr;
        bool (*compose)(void*, Address clone, const Transform&) noexcept = nullptr;
        bool (*enqueue)(void*, Address clone, Address queue) noexcept = nullptr;
        bool (*pool)(void*, QueueReceipt::Pool&) noexcept = nullptr;
    };
    enum class State { empty, acquiring, owned, submitting, submitted, retiring, releasing, quarantined };
    RenderOwner(Operations operations, QueueReceipt::Access access) noexcept : operations_(operations), receipt_(access) {}
    RenderOwner(const RenderOwner&) = delete;
    RenderOwner& operator=(const RenderOwner&) = delete;
    bool Acquire(const Selection&) noexcept;
    bool Pose(const Transform& parent) noexcept;
    bool Submit(Address queue, std::uint64_t ticket) noexcept;
    // Only a matching outer drain after shader shutdown (or a proven pre-drain
    // rejection) may call this. Closing admission never removes this callback.
    bool Retire(std::uint64_t ticket) noexcept;
    bool Clear() noexcept;
    void Close() noexcept { admission_.store(false, std::memory_order_release); }
    // Owner-only restart after successful cleanup. Never replaces quarantined data.
    bool Open() noexcept;
    void InvalidateContext() noexcept;
    State CurrentState() const noexcept { return state_; }
    std::size_t SubmittedCount() const noexcept { return receipt_.SubmittedCount(); }
    const Selection& Identity() const noexcept { return selection_; }
private:
    bool Owner() const noexcept;
    bool Current() const noexcept;
    bool PrivateTree(bool initial) noexcept;
    bool ClearOwned() noexcept;
    void Quarantine() noexcept { state_ = State::quarantined; receipt_.Quarantine(); }
    Operations operations_{};
    QueueReceipt receipt_;
    std::atomic<bool> admission_{true};
    State state_ = State::empty;
    bool busy_ = false;
    Selection selection_{};
    Address model_ = 0, clone_ = 0;
    std::array<Address, QueueReceipt::kMaxRenders> renders_{};
    std::size_t count_ = 0;
    std::uint64_t ticket_ = 0;
};
}
