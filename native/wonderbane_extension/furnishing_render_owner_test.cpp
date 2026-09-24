#include "furnishing_render_owner.h"
#undef NDEBUG
#include <cassert>
#include <algorithm>
#include <map>
#include <memory>
#include <vector>

namespace f = wonderbane::extension::furnishing;
using A = f::Address; using R = f::RenderOwner; using Q = f::QueueReceipt;
namespace {
constexpr A model=0x100000, source=0x110000, copy=0x120000, child=0x130000;
constexpr A queue=0x140000, head=0x150000, pool=0x160000, node=0x170000, wrapper_type=0x1549d38;
const f::Transform pose{1,2,3,1,0,0,0,1,1,1};
f::Selection Selection() { f::Selection s{}; s.model=model; s.render=source; s.epoch=7; s.floor=2; return s; }
struct Fixture {
    std::map<A,unsigned char> memory;
    std::vector<A> nodes;
    R* renderer=nullptr;
    bool owned=true,current=true,source_valid=true,private_valid=true,clone_null=false,alias=false;
    bool fault_after=false,fail_erase=false;
    unsigned step=0,fail_at=0,close_at=0,stale_at=0,context_at=0,reenter_at=0;
    unsigned model_refs=0,clone_refs=0,retain_calls=0,clone_calls=0,compose_calls=0,enqueue_calls=0,erase_calls=0;
    unsigned submit_count=2,used=0;
    std::vector<A> releases;
    template<class T> void Put(A at,const T& value) {
        const auto* data=reinterpret_cast<const unsigned char*>(&value);
        for(std::size_t i=0;i<sizeof(T);++i) { memory[at+static_cast<A>(i)]=data[i]; }
    }
    void Tree() {
        Put(queue,head); Put(queue+4,static_cast<A>(nodes.size()));
        Put(head+4,nodes.empty()?A{0}:nodes.front()); Put(head+8,nodes.empty()?head:nodes.front()); Put(head+12,nodes.empty()?head:nodes.back());
        for(std::size_t i=0;i<nodes.size();++i) {
            const A n=nodes[i]; Put(n,i?A{0}:A{1}); Put(n+4,i?nodes[0]:head); Put(n+8,A{0});
            Put(n+12,i+1<nodes.size()?nodes[i+1]:A{0}); Put(n+16,pool+(n-node));
        }
    }
    bool Enter() {
        ++step;
        if(step==close_at) { renderer->Close(); }
        if(step==stale_at) { current=false; }
        if(step==context_at) { owned=false; renderer->InvalidateContext(); }
        if(step==reenter_at) {
            assert(!renderer->Acquire(Selection())); assert(!renderer->Clear()); assert(!renderer->Pose(pose));
            assert(!renderer->Submit(queue,7)); assert(!renderer->Retire(7)); assert(!renderer->Open());
        }
        return step!=fail_at || fault_after;
    }
    bool Finish() const { return step!=fail_at; }
    static bool Owner(void* c) noexcept { return static_cast<Fixture*>(c)->owned; }
    static bool Current(void* c,const f::Selection& s) noexcept { return static_cast<Fixture*>(c)->current && s.SameIdentity(Selection()); }
    static bool Source(void* c,const f::Selection&) noexcept { return static_cast<Fixture*>(c)->source_valid; }
    static bool Retain(void* c,A value,A* slot) noexcept {
        auto& f=*static_cast<Fixture*>(c); ++f.retain_calls; assert(value==model && *slot==model);
        if(!f.Enter()) { return false; } ++f.model_refs; return f.Finish();
    }
    static bool Clone(void* c,A value,A* slot) noexcept {
        auto& f=*static_cast<Fixture*>(c); ++f.clone_calls; assert(value==source && !*slot && f.model_refs==1);
        if(!f.Enter()) { return false; } if(!f.clone_null) { *slot=f.alias?source:copy; ++f.clone_refs; } return f.Finish();
    }
    static bool Release(void* c,A* slot) noexcept {
        auto& f=*static_cast<Fixture*>(c); assert(f.nodes.empty()); f.releases.push_back(*slot);
        if(!f.Enter()) { return false; }
        if(*slot==copy) { assert(f.clone_refs==1 && f.model_refs==1); --f.clone_refs; }
        else { assert(*slot==model && f.model_refs==1 && !f.clone_refs); --f.model_refs; }
        *slot=0; return f.Finish();
    }
    static bool Private(void* c,const f::Selection&,A value,A* out,std::size_t capacity,std::size_t* count) noexcept {
        auto& f=*static_cast<Fixture*>(c); assert(value==copy && f.clone_refs==1 && f.model_refs==1 && capacity>=2);
        out[0]=copy; out[1]=child; *count=2; return f.private_valid;
    }
    static bool Compose(void* c,A value,const f::Transform& t) noexcept {
        auto& f=*static_cast<Fixture*>(c); ++f.compose_calls; assert(value==copy && t==pose && f.nodes.empty());
        return f.Enter() && f.Finish();
    }
    static bool Enqueue(void* c,A value,A q) noexcept {
        auto& f=*static_cast<Fixture*>(c); ++f.enqueue_calls; assert(value==copy && q==queue);
        if(!f.Enter()) { return false; }
        for(unsigned i=0;i<f.submit_count;++i) {
            const A p=pool+i*32; f.Put(p,wrapper_type); f.Put(p+0x1c,i?child:copy); f.nodes.push_back(node+i*32);
        }
        f.used=2; f.Tree(); return f.Finish();
    }
    static bool Pool(void* c,Q::Pool& out) noexcept { out={pool,16,static_cast<Fixture*>(c)->used}; return true; }
    static bool Read(void* c,A at,void* out,std::size_t size) noexcept {
        auto& f=*static_cast<Fixture*>(c); auto* bytes=static_cast<unsigned char*>(out);
        for(std::size_t i=0;i<size;++i) { auto it=f.memory.find(at+static_cast<A>(i)); if(it==f.memory.end()) { return false; } bytes[i]=it->second; } return true;
    }
    static bool Erase(void* c,A q,A n) noexcept {
        auto& f=*static_cast<Fixture*>(c); ++f.erase_calls; assert(q==queue && f.clone_refs==1 && f.model_refs==1);
        if(f.fail_erase) { return false; }
        const auto found=std::find(f.nodes.begin(),f.nodes.end(),n); assert(found!=f.nodes.end()); f.nodes.erase(found); f.Tree(); return true;
    }
    std::unique_ptr<R> Make() {
        Tree(); auto r=std::make_unique<R>(R::Operations{this,Owner,Current,Source,Retain,Clone,Release,Private,Compose,Enqueue,Pool},Q::Access{this,Read,Owner,Erase,wrapper_type});
        renderer=r.get(); return r;
    }
    void Quarantined(R& r) {
        assert(r.CurrentState()==R::State::quarantined); const auto calls=step;
        owned=true; current=true; assert(!r.Open() && !r.Acquire(Selection()) && !r.Clear() && !r.Pose(pose) && !r.Submit(queue,8) && !r.Retire(7)); assert(step==calls);
    }
};
void Normal() {
    Fixture f; auto r=f.Make(); assert(r->Acquire(Selection()) && r->Pose(pose)); assert(r->Submit(queue,7) && r->SubmittedCount()==2);
    assert(!r->Clear() && !r->Pose(pose) && !r->Acquire(Selection()) && !r->Retire(8)); assert(f.releases.empty());
    assert(r->Retire(7)); assert(f.nodes.empty() && f.erase_calls==2 && f.releases.empty());
    assert(r->Clear()); assert(f.releases==std::vector<A>({copy,model})); assert(!f.model_refs && !f.clone_refs);
    assert(r->Clear()); assert(f.releases.size()==2);
}
void StopAndStale() {
    for(bool stale:{false,true}) {
        Fixture f; auto r=f.Make(); assert(r->Acquire(Selection()));
        if(stale) { f.stale_at=3; } else { f.close_at=3; }
        assert(r->Submit(queue,7)); assert(f.releases.empty()); assert(r->Retire(7));
        assert(r->CurrentState()==R::State::empty && !f.model_refs && !f.clone_refs && f.erase_calls==2);
    }
    { Fixture f; auto r=f.Make(); assert(r->Acquire(Selection())); r->Close(); assert(!r->Submit(queue,7)); assert(r->Clear()); assert(!r->Acquire(Selection())); assert(r->Open()); assert(r->Acquire(Selection())); assert(r->Clear()); }
    for(unsigned step:{1U,2U}) {
        Fixture f; auto r=f.Make(); f.stale_at=step; assert(!r->Acquire(Selection())); assert(r->CurrentState()==R::State::empty && !f.model_refs && !f.clone_refs);
    }
}
void Faults() {
    for(bool after:{false,true}) {
        for(unsigned step=1;step<=5;++step) {
            Fixture f; auto r=f.Make(); f.fail_at=step; f.fault_after=after;
            const bool acquired=r->Acquire(Selection());
            if(step<=2) { assert(!acquired); }
            else { assert(acquired); if(step==3) { assert(!r->Pose(pose)); } else { assert(r->Pose(pose)); assert(!r->Clear()); } }
            f.Quarantined(*r);
        }
        Fixture f; auto r=f.Make(); assert(r->Acquire(Selection())); f.fail_at=3; f.fault_after=after;
        assert(!r->Submit(queue,7)); assert(f.releases.empty()); f.Quarantined(*r);
    }
    { Fixture f; auto r=f.Make(); assert(r->Acquire(Selection()) && r->Submit(queue,7)); f.fail_erase=true; assert(!r->Retire(7)); assert(f.releases.empty()); f.Quarantined(*r); }
}
void ContextAndReentry() {
    for(unsigned step=1;step<=5;++step) {
        Fixture f; auto r=f.Make(); f.context_at=step;
        if(r->Acquire(Selection())) { if(r->Pose(pose)) { assert(!r->Clear()); } } f.Quarantined(*r);
    }
    { Fixture f; auto r=f.Make(); assert(r->Acquire(Selection())); f.context_at=3; assert(!r->Submit(queue,7)); f.Quarantined(*r); }
    { Fixture f; auto r=f.Make(); assert(r->Acquire(Selection()) && r->Submit(queue,7)); r->InvalidateContext(); assert(f.releases.empty()); f.Quarantined(*r); }
    for(unsigned step=1;step<=6;++step) {
        Fixture f; auto r=f.Make(); f.reenter_at=step; assert(r->Acquire(Selection()) && r->Pose(pose) && r->Submit(queue,7) && r->Retire(7) && r->Clear());
    }
}
void Qualification() {
    { Fixture f; auto r=f.Make(); f.source_valid=false; assert(!r->Acquire(Selection()) && !f.step); }
    { Fixture f; auto r=f.Make(); f.clone_null=true; assert(!r->Acquire(Selection()) && !f.clone_refs && !f.model_refs && r->CurrentState()==R::State::empty); }
    { Fixture f; auto r=f.Make(); f.alias=true; assert(!r->Acquire(Selection())); f.Quarantined(*r); }
    { Fixture f; auto r=f.Make(); f.private_valid=false; assert(!r->Acquire(Selection())); assert(f.releases.empty()); f.Quarantined(*r); }
    { Fixture f; auto r=f.Make(); assert(r->Acquire(Selection())); f.private_valid=false; assert(!r->Submit(queue,7)); f.Quarantined(*r); }
    for(unsigned count:{0U,1U}) {
        Fixture f; auto r=f.Make(); assert(r->Acquire(Selection())); f.submit_count=count; assert(r->Submit(queue,7)==(count!=0));
        if(count) { assert(r->SubmittedCount()==1 && r->Retire(7)); } assert(r->Clear() && !f.model_refs && !f.clone_refs);
    }
}
}
int main() { Normal(); StopAndStale(); Faults(); ContextAndReentry(); Qualification(); }
