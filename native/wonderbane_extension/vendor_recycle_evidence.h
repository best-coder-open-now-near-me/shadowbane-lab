#pragma once
#include "vendor_recycle_native.h"
#include <map>

namespace wonderbane::extension::vendor_recycle {
class Evidence {
    struct Ticket { vendor_production::Payload payload{}; unsigned stage=0, thread=0; };
    Manifest manifest_{};
    vendor_production::Key local_{};
    vendor_production::Cursor cursor_{};
    std::map<std::uint64_t,Ticket> tickets_;
    std::uint64_t floor_=0, sent_=0, completion_=0;
    bool valid_=false;
    bool References(const vendor_production::Payload& p) const noexcept {
        if(p.references_count!=manifest_.count || p.references_reserved){return false;}
        std::array<bool,kItems> found{};
        for(std::size_t i=0;i<p.references.size();++i) {
            const auto& key=p.references[i];
            if(i>=p.references_count){if(key!=vendor_production::Key{}){return false;}continue;}
            if(!key[0] || key[1]!=40){return false;}
            const auto at=std::lower_bound(manifest_.items.begin(),manifest_.items.begin()+manifest_.count,key[0]);
            if(at==manifest_.items.begin()+manifest_.count || *at!=key[0]){return false;}
            const auto index=static_cast<std::size_t>(at-manifest_.items.begin());
            if(found[index]){return false;}found[index]=true;
        }
        return true;
    }
    bool Body(const vendor_production::Payload& p,bool send) const noexcept {
        auto expected=p;
        expected.action=send?3U:7U;expected.error=0;expected.fields=send?0U:4U;
        expected.building={manifest_.owner.building,8};expected.vendor={manifest_.owner.vendor,42};
        expected.reference={};expected.quantity=1;expected.marker=expected.prefix=expected.suffix=0;
        expected.item={};expected.item_template=expected.queue_count_raw=expected.value=expected.seconds=0;
        expected.duration=expected.queue_ignored=expected.complete=0;expected.deposited_item={};expected.deposited_template={};
        expected.strongbox_gold=send?0:manifest_.gold+manifest_.refund;
        expected.multiple=expected.template_type=expected.queue_flags_raw=expected.rejection=expected.reserved=0;
        return !std::memcmp(&p,&expected,sizeof(p)) && References(p);
    }
public:
    void Begin(const Manifest& manifest,vendor_production::Key local,const vendor_production::Cursor& cursor) noexcept {
        manifest_=manifest;local_=local;cursor_=cursor;floor_=cursor.sequence;sent_=completion_=0;tickets_.clear();
        valid_=manifest.count && manifest.count<=kItems && local[0] && local[1]==53
            && cursor.process_id && cursor.creation && cursor.sequence<INT64_MAX;
    }
    bool Healthy() const noexcept {return valid_;}
    bool Verified() const noexcept {return valid_ && completion_ && tickets_.empty();}
    std::uint64_t Floor() const noexcept {return floor_;}
    std::uint64_t Completion() const noexcept {return Verified()?completion_:0;}
    const vendor_production::Cursor& Cursor() const noexcept {return cursor_;}
    void Invalidate() noexcept {valid_=false;}
    bool Receive(const vendor_production::Batch& batch) noexcept {
        if(!valid_){return false;}
        try {
            if(batch.count>vendor_production::kCapacity || batch.after.process_id!=cursor_.process_id
                || batch.after.creation!=cursor_.creation || batch.after.rejected!=cursor_.rejected
                || batch.after.ticket_drops!=cursor_.ticket_drops || batch.after.sequence>INT64_MAX
                || batch.after.sequence!=cursor_.sequence+batch.count || batch.after.sequence-floor_>4096){valid_=false;return false;}
            for(std::size_t i=0;i<batch.count;++i) {
                const auto& record=batch.records[i];const auto& p=record.payload;
                if(record.sequence!=static_cast<LONG64>(++cursor_.sequence) || (record.flags!=3 && record.flags!=7)
                    || record.scene_epoch!=manifest_.owner.scene || record.local!=local_ || !record.thread_id
                    || p.building!=vendor_production::Key{manifest_.owner.building,8}
                    || p.vendor!=vendor_production::Key{manifest_.owner.vendor,42} || p.error || p.rejection){valid_=false;return false;}
                if(record.stage==4) {
                    if(sent_ || record.flags!=3 || record.decode_sequence || !Body(p,true)){valid_=false;return false;}
                    sent_=cursor_.sequence;continue;
                }
                if(!sent_ || record.decode_sequence<=sent_ || p.action!=7){valid_=false;return false;}
                if(record.stage==1) {
                    if(record.flags!=3 || record.decode_sequence!=cursor_.sequence || tickets_.size()>=64
                        || tickets_.contains(record.decode_sequence)){valid_=false;return false;}
                    tickets_.emplace(record.decode_sequence,Ticket{p,1,record.thread_id});continue;
                }
                const auto it=tickets_.find(record.decode_sequence);
                if(record.flags!=7 || it==tickets_.end() || (record.stage!=2 && record.stage!=3)
                    || it->second.stage!=record.stage-1 || std::memcmp(&p,&it->second.payload,sizeof(p))
                    || (record.stage==3 && record.thread_id!=it->second.thread)){valid_=false;return false;}
                it->second.stage=record.stage;it->second.thread=record.thread_id;
                if(record.stage!=3){continue;}
                tickets_.erase(it);
                if(p.references_count) {
                    if(completion_ || !Body(p,false)){valid_=false;return false;}
                    completion_=cursor_.sequence;
                } else if(p.fields!=4 || p.strongbox_gold!=manifest_.gold) {valid_=false;return false;}
            }
            cursor_=batch.after;return true;
        } catch(...){valid_=false;return false;}
    }
};
}
