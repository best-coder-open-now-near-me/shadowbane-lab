#pragma once
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
constexpr A fixture_model=0x100000, fixture_source=0x110000, fixture_copy=0x120000, fixture_child=0x130000;
constexpr A fixture_queue=0x140000, fixture_head=0x150000, fixture_pool=0x160000, fixture_node=0x170000, fixture_wrapper_type=0x1549d38;
const f::Transform fixture_pose{1,2,3,1,0,0,0,1,1,1};
f::Selection Selection() { f::Selection s{}; s.model=fixture_model; s.render=fixture_source; s.epoch=7; s.floor=2; return s; }
struct Fixture {
    std::map<A,unsigned char> memory;
    std::vector<A> nodes;
    R* renderer=nullptr;
    bool owned=true,current=true,source_valid=true,private_valid=true,clone_null=false,alias=false;
    bool fault_after=false,fail_erase=false,wrapper_valid=true;
    unsigned step=0,fail_at=0,close_at=0,stale_at=0,context_at=0,reenter_at=0;
    unsigned model_refs=0,clone_refs=0,retain_calls=0,clone_calls=0,compose_calls=0,enqueue_calls=0,erase_calls=0;
    unsigned submit_count=2,used=0;
    std::vector<A> releases;
    template<class T> void Put(A at,const T& value) {
        const auto* data=reinterpret_cast<const unsigned char*>(&value);
        for(std::size_t i=0;i<sizeof(T);++i) { memory[at+static_cast<A>(i)]=data[i]; }
    }
    void Tree() {
        Put(fixture_queue,fixture_head); Put(fixture_queue+4,static_cast<A>(nodes.size()));
        Put(fixture_head+4,nodes.empty()?A{0}:nodes.front()); Put(fixture_head+8,nodes.empty()?fixture_head:nodes.front()); Put(fixture_head+12,nodes.empty()?fixture_head:nodes.back());
        for(std::size_t i=0;i<nodes.size();++i) {
            const A n=nodes[i]; Put(n,i?A{0}:A{1}); Put(n+4,i?nodes[0]:fixture_head); Put(n+8,A{0});
            Put(n+12,i+1<nodes.size()?nodes[i+1]:A{0}); Put(n+16,fixture_pool+(n-fixture_node));
        }
    }
    bool Enter() {
        ++step;
        if(step==close_at) { renderer->Close(); }
        if(step==stale_at) { current=false; }
        if(step==context_at) { owned=false; renderer->InvalidateContext(); }
        if(step==reenter_at) {
            assert(!renderer->Acquire(Selection())); assert(!renderer->Clear()); assert(!renderer->Pose(fixture_pose));
            assert(!renderer->Submit(fixture_queue,7)); assert(!renderer->Retire(7)); assert(!renderer->Open());
        }
        return step!=fail_at || fault_after;
    }
    bool Finish() const { return step!=fail_at; }
    static bool Owner(void* c) noexcept { return static_cast<Fixture*>(c)->owned; }
    static bool Current(void* c,const f::Selection& s) noexcept { return static_cast<Fixture*>(c)->current && s.SameIdentity(Selection()); }
    static bool Source(void* c,const f::Selection&) noexcept { return static_cast<Fixture*>(c)->source_valid; }
    static bool Retain(void* c,A value,A* slot) noexcept {
        auto& f=*static_cast<Fixture*>(c); ++f.retain_calls; assert(value==fixture_model && *slot==fixture_model);
        if(!f.Enter()) { return false; } ++f.model_refs; return f.Finish();
    }
    static bool Clone(void* c,A value,A* slot) noexcept {
        auto& f=*static_cast<Fixture*>(c); ++f.clone_calls; assert(value==fixture_source && !*slot && f.model_refs==1);
        if(!f.Enter()) { return false; } if(!f.clone_null) { *slot=f.alias?fixture_source:fixture_copy; ++f.clone_refs; } return f.Finish();
    }
    static bool Release(void* c,A* slot) noexcept {
        auto& f=*static_cast<Fixture*>(c); assert(f.nodes.empty()); f.releases.push_back(*slot);
        if(!f.Enter()) { return false; }
        if(*slot==fixture_copy) { assert(f.clone_refs==1 && f.model_refs==1); --f.clone_refs; }
        else { assert(*slot==fixture_model && f.model_refs==1 && !f.clone_refs); --f.model_refs; }
        *slot=0; return f.Finish();
    }
    static bool Private(void* c,const f::Selection&,A value,A* out,std::size_t capacity,std::size_t* count) noexcept {
        auto& f=*static_cast<Fixture*>(c); assert(value==fixture_copy && f.clone_refs==1 && f.model_refs==1 && capacity>=2);
        out[0]=fixture_copy; out[1]=fixture_child; *count=2; return f.private_valid;
    }
    static bool Compose(void* c,A value,const f::Transform& t) noexcept {
        auto& f=*static_cast<Fixture*>(c); ++f.compose_calls; assert(value==fixture_copy && t==fixture_pose && f.nodes.empty());
        return f.Enter() && f.Finish();
    }
    static bool Enqueue(void* c,A value,A q) noexcept {
        auto& f=*static_cast<Fixture*>(c); ++f.enqueue_calls; assert(value==fixture_copy && q==fixture_queue);
        if(!f.Enter()) { return false; }
        for(unsigned i=0;i<f.submit_count;++i) {
            const A p=fixture_pool+i*32; f.Put(p,fixture_wrapper_type); f.Put(p+0x1c,i?fixture_child:fixture_copy); f.nodes.push_back(fixture_node+i*32);
        }
        f.used=2; f.Tree(); return f.Finish();
    }
    static bool Wrapper(void* c,A,A) noexcept {
        auto& f=*static_cast<Fixture*>(c); assert(!f.releases.size());
        assert(!f.renderer->Retire(7)&&!f.renderer->Clear()); return f.wrapper_valid;
    }
    static bool Pool(void* c,Q::Pool& out) noexcept { out={fixture_pool,16,static_cast<Fixture*>(c)->used}; return true; }
    static bool Read(void* c,A at,void* out,std::size_t size) noexcept {
        auto& f=*static_cast<Fixture*>(c); auto* bytes=static_cast<unsigned char*>(out);
        for(std::size_t i=0;i<size;++i) { auto it=f.memory.find(at+static_cast<A>(i)); if(it==f.memory.end()) { return false; } bytes[i]=it->second; } return true;
    }
    static bool Erase(void* c,A q,A n) noexcept {
        auto& f=*static_cast<Fixture*>(c); ++f.erase_calls; assert(q==fixture_queue && f.clone_refs==1 && f.model_refs==1);
        if(f.fail_erase) { return false; }
        const auto found=std::find(f.nodes.begin(),f.nodes.end(),n); assert(found!=f.nodes.end()); f.nodes.erase(found); f.Tree(); return true;
    }
    std::unique_ptr<R> Make() {
        Tree(); auto r=std::make_unique<R>(R::Operations{this,Owner,Current,Source,Retain,Clone,Release,Private,Compose,Enqueue,Pool,Wrapper},Q::Access{this,Read,Owner,Erase,fixture_wrapper_type});
        renderer=r.get(); return r;
    }
    void Quarantined(R& r) {
        assert(r.CurrentState()==R::State::quarantined); const auto calls=step;
        owned=true; current=true; assert(!r.Open() && !r.Acquire(Selection()) && !r.Clear() && !r.Pose(fixture_pose) && !r.Submit(fixture_queue,8) && !r.Retire(7)); assert(step==calls);
    }
};
}
