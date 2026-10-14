#pragma once
#include "vendor_wire.h"
#include "vendor_production_responses.h"
#include <cstring>
#include <map>
#include <set>

namespace wonderbane::extension::vendor {
// Admission owns one pre-call cursor. A serialized request proves what was sent;
// only decoded -> processing -> returned replies can prove its queue arrivals.
// The raw queue count is deliberately absent from the admission calculation.
class OrderAdmission {
    struct Ticket { vendor_production::Payload payload; std::uint32_t stage, thread; };
    wire::Snapshot before_{};
    vendor_production::Key local_{};
    vendor_production::Cursor cursor_{};
    std::uint64_t bookmark_ = 0;
    std::map<std::uint64_t, Ticket> tickets_;
    std::set<std::uint32_t> arrivals_;
    bool active_ = false, valid_ = false, sent_ = false;
    static bool Contains(const wire::Snapshot& s, std::uint32_t id) noexcept {
        for (std::size_t i = 0; i < s.count; ++i) { if (s.slots[i].item == id) { return true; } }
        return false;
    }
public:
    bool Active() const noexcept { return active_; }
    const vendor_production::Cursor& Cursor() const noexcept { return cursor_; }
    void Invalidate() noexcept { valid_ = false; }
    void Reset() noexcept { active_ = valid_ = sent_ = false; tickets_.clear(); arrivals_.clear(); }
    void Begin(const wire::Snapshot& before, vendor_production::Key local,
        const vendor_production::Cursor& cursor) noexcept {
        Reset(); before_ = before; local_ = local; cursor_ = cursor; bookmark_ = cursor.sequence;
        active_ = valid_ = wire::ValidSnapshot(before) && wire::RandomOrder(before)
            && local[0] && local[1] == 53 && cursor.process_id && cursor.creation;
    }
    bool Receive(const vendor_production::Batch& batch) noexcept {
        if (!active_ || !valid_) { return false; }
        try {
            if (batch.count > vendor_production::kCapacity
                || batch.after.process_id != cursor_.process_id || batch.after.creation != cursor_.creation
                || batch.after.rejected != cursor_.rejected || batch.after.ticket_drops != cursor_.ticket_drops
                || batch.after.sequence != cursor_.sequence + batch.count) { valid_ = false; return false; }
            for (std::size_t i = 0; i < batch.count; ++i) {
                const auto& r = batch.records[i]; const auto& p = r.payload;
                if (static_cast<std::uint64_t>(r.sequence) != ++cursor_.sequence || r.flags & 8) {
                    valid_ = false; return false;
                }
                if (!(r.flags & 1) || p.building != vendor_production::Key{before_.building, 8}
                    || p.vendor != vendor_production::Key{before_.vendor, 42}) { continue; }
                if (r.scene_epoch != before_.scene || r.local != local_ || p.error) { valid_ = false; return false; }
                if (r.stage == 4) {
                    if (r.flags != 3 || r.decode_sequence || p.action != 1 || sent_
                        || p.reference != vendor_production::Key{before_.item_template, 0}
                        || p.quantity != before_.quantity || p.multiple != 1 || p.marker != before_.table
                        || p.prefix || p.suffix || p.references_count) { valid_ = false; return false; }
                    sent_ = true; continue;
                }
                // Old queued decoder callbacks cannot belong to this request.
                if (r.decode_sequence <= bookmark_) { continue; }
                if (!sent_) { valid_ = false; return false; }
                if (r.stage == 1) {
                    if (r.flags != 3 || r.decode_sequence != static_cast<std::uint64_t>(r.sequence)
                        || tickets_.contains(r.decode_sequence) || tickets_.size() >= 64) {
                        valid_ = false; return false;
                    }
                    tickets_.emplace(r.decode_sequence, Ticket{p, 1, r.thread_id}); continue;
                }
                auto ticket = tickets_.find(r.decode_sequence);
                if (r.flags != 7 || ticket == tickets_.end() || (r.stage != 2 && r.stage != 3)
                    || ticket->second.stage != r.stage - 1
                    || std::memcmp(&p, &ticket->second.payload, sizeof(p))
                    || (r.stage == 3 && r.thread_id != ticket->second.thread)) {
                    valid_ = false; return false;
                }
                ticket->second.stage = r.stage; ticket->second.thread = r.thread_id;
                if (r.stage != 3) { continue; }
                tickets_.erase(ticket);
                if (p.action != 8 || !p.item[0] || p.item[1] != 40
                    || p.item_template != before_.item_template || p.template_type
                    || Contains(before_, p.item[0]) || p.queue_ignored) { valid_ = false; return false; }
                arrivals_.insert(p.item[0]);
                std::size_t free = 0;
                for (std::size_t j = 0; j < before_.count; ++j) { free += !before_.slots[j].item; }
                if (arrivals_.size() > free) { valid_ = false; return false; }
            }
            cursor_ = batch.after; return true;
        } catch (...) { valid_ = false; return false; }
    }
    bool Matches(const wire::Snapshot& current) const noexcept {
        if (!valid_ || !sent_ || current.scene != before_.scene || current.root != before_.root
            || current.manager != before_.manager || current.menu != before_.menu
            || current.hireling != before_.hireling || current.building != before_.building
            || current.vendor != before_.vendor || current.count < before_.count
            || current.count > current.slots.size()) { return false; }
        std::size_t free = 0, additions = 0;
        for (std::size_t i = 0; i < before_.count; ++i) {
            if (!before_.slots[i].item) { ++free; }
            else if (!Contains(current, before_.slots[i].item)) { return false; }
        }
        for (std::size_t i = 0; i < current.count; ++i) {
            const auto id = current.slots[i].item;
            if (id && !Contains(before_, id)) {
                if (!arrivals_.contains(id)) { return false; }
                ++additions;
            }
        }
        return free && arrivals_.size() == free && additions == free;
    }
};
}
