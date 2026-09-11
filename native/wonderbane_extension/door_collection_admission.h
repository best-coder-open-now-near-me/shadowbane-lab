#pragma once
#include <Windows.h>
#include <cstdint>

namespace wonderbane::extension::movement {
// Shared by verified collection writers and bounded pointer acquisition only.
// The reader region may copy native fields and increment verified native atomic
// references. It MUST NOT release references or invoke other native callbacks.
// Mutation call-through runs after BeginMutation returns, with no SRW lock held.
// This is collection lifetime exclusion, never movement/operation authority.
class DoorCollectionAdmission {
public:
    DoorCollectionAdmission() = default;
    DoorCollectionAdmission(const DoorCollectionAdmission&) = delete;
    DoorCollectionAdmission& operator=(const DoorCollectionAdmission&) = delete;
    DoorCollectionAdmission(DoorCollectionAdmission&&) = delete;
    DoorCollectionAdmission& operator=(DoorCollectionAdmission&&) = delete;
    struct ReadLease {
        DoorCollectionAdmission* admission = nullptr;
        std::uint64_t generation = 0;
        ReadLease() = default;
        ReadLease(const ReadLease&) = delete;
        ReadLease& operator=(const ReadLease&) = delete;
        ~ReadLease() { Reset(); }
        void Reset() noexcept {
            if (admission) { auto* owner = admission; admission = nullptr; owner->EndRead(); }
            generation = 0;
        }
    };
    bool TryRead(ReadLease& lease) noexcept {
        if (lease.admission) { return false; }
        AcquireSRWLockExclusive(&lock_);
        const bool accepted = !terminal_ && !writers_ && readers_ != UINT32_MAX;
        if (accepted) { ++readers_; lease.admission = this; lease.generation = generation_; }
        ReleaseSRWLockExclusive(&lock_);
        return accepted;
    }
    // Original mutation is never suppressed, even after terminal retirement.
    // Announce before waiting so no new reader can overtake a pending writer.
    void BeginMutation() noexcept {
        AcquireSRWLockExclusive(&lock_);
        ++writers_;
        Advance();
        while (readers_) { SleepConditionVariableSRW(&readers_drained_, &lock_, INFINITE, 0); }
        ReleaseSRWLockExclusive(&lock_);
    }
    void EndMutation() noexcept {
        AcquireSRWLockExclusive(&lock_);
        --writers_;
        ReleaseSRWLockExclusive(&lock_);
    }
    // Snapshot only: a writer can enter immediately after this returns. Never
    // use this as a lease authorizing native selection or an interaction.
    bool Current(std::uint64_t generation) noexcept {
        AcquireSRWLockShared(&lock_);
        const bool current = !terminal_ && !writers_ && generation && generation == generation_;
        ReleaseSRWLockShared(&lock_);
        return current;
    }
    void Retire() noexcept {
        AcquireSRWLockExclusive(&lock_);
        terminal_ = true; Advance();
        ReleaseSRWLockExclusive(&lock_);
    }
private:
    void EndRead() noexcept {
        AcquireSRWLockExclusive(&lock_);
        --readers_;
        if (!readers_) { WakeAllConditionVariable(&readers_drained_); }
        ReleaseSRWLockExclusive(&lock_);
    }
    void Advance() noexcept {
        if (generation_ == UINT64_MAX) { terminal_ = true; }
        else { ++generation_; }
    }
    SRWLOCK lock_ = SRWLOCK_INIT;
    CONDITION_VARIABLE readers_drained_ = CONDITION_VARIABLE_INIT;
    std::uint64_t generation_ = 1, writers_ = 0;
    std::uint32_t readers_ = 0;
    bool terminal_ = false;
};
}
