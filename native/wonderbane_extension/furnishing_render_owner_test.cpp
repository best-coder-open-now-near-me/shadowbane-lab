#include "furnishing_test_fixture.h"
namespace {
void Normal() {
    Fixture f; auto r=f.Make(); assert(r->Acquire(Selection()) && r->Pose(fixture_pose)); assert(r->Submit(fixture_queue,7) && r->SubmittedCount()==2);
    assert(!r->Clear() && !r->Pose(fixture_pose) && !r->Acquire(Selection()) && !r->Retire(8)); assert(f.releases.empty());
    assert(r->Retire(7)); assert(f.nodes.empty() && f.erase_calls==2 && f.releases.empty());
    assert(r->Clear()); assert(f.releases==std::vector<A>({fixture_copy,fixture_model})); assert(!f.model_refs && !f.clone_refs);
    assert(r->Clear()); assert(f.releases.size()==2);
}
void StopAndStale() {
    for(bool stale:{false,true}) {
        Fixture f; auto r=f.Make(); assert(r->Acquire(Selection()));
        if(stale) { f.stale_at=3; } else { f.close_at=3; }
        assert(r->Submit(fixture_queue,7)); assert(f.releases.empty()); assert(r->Retire(7));
        assert(r->CurrentState()==R::State::empty && !f.model_refs && !f.clone_refs && f.erase_calls==2);
    }
    { Fixture f; auto r=f.Make(); assert(r->Acquire(Selection())); r->Close(); assert(!r->Submit(fixture_queue,7)); assert(r->Clear()); assert(!r->Acquire(Selection())); assert(r->Open()); assert(r->Acquire(Selection())); assert(r->Clear()); }
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
            else { assert(acquired); if(step==3) { assert(!r->Pose(fixture_pose)); } else { assert(r->Pose(fixture_pose)); assert(!r->Clear()); } }
            f.Quarantined(*r);
        }
        Fixture f; auto r=f.Make(); assert(r->Acquire(Selection())); f.fail_at=3; f.fault_after=after;
        assert(!r->Submit(fixture_queue,7)); assert(f.releases.empty()); f.Quarantined(*r);
    }
    { Fixture f; auto r=f.Make(); assert(r->Acquire(Selection()) && r->Submit(fixture_queue,7)); f.fail_erase=true; assert(!r->Retire(7)); assert(f.releases.empty()); f.Quarantined(*r); }
}
void ContextAndReentry() {
    for(unsigned step=1;step<=5;++step) {
        Fixture f; auto r=f.Make(); f.context_at=step;
        if(r->Acquire(Selection())) { if(r->Pose(fixture_pose)) { assert(!r->Clear()); } } f.Quarantined(*r);
    }
    { Fixture f; auto r=f.Make(); assert(r->Acquire(Selection())); f.context_at=3; assert(!r->Submit(fixture_queue,7)); f.Quarantined(*r); }
    { Fixture f; auto r=f.Make(); assert(r->Acquire(Selection()) && r->Submit(fixture_queue,7)); r->InvalidateContext(); assert(f.releases.empty()); f.Quarantined(*r); }
    for(unsigned step=1;step<=6;++step) {
        Fixture f; auto r=f.Make(); f.reenter_at=step; assert(r->Acquire(Selection()) && r->Pose(fixture_pose) && r->Submit(fixture_queue,7) && r->Retire(7) && r->Clear());
    }
}
void Qualification() {
    { Fixture f; auto r=f.Make(); f.source_valid=false; assert(!r->Acquire(Selection()) && !f.step); }
    { Fixture f; auto r=f.Make(); f.clone_null=true; assert(!r->Acquire(Selection()) && !f.clone_refs && !f.model_refs && r->CurrentState()==R::State::empty); }
    { Fixture f; auto r=f.Make(); f.alias=true; assert(!r->Acquire(Selection())); f.Quarantined(*r); }
    { Fixture f; auto r=f.Make(); f.private_valid=false; assert(!r->Acquire(Selection())); assert(f.releases.empty()); f.Quarantined(*r); }
    { Fixture f; auto r=f.Make(); assert(r->Acquire(Selection())); f.private_valid=false; assert(!r->Submit(fixture_queue,7)); f.Quarantined(*r); }
    { Fixture f;auto r=f.Make();assert(r->Acquire(Selection()));f.wrapper_valid=false;assert(!r->Submit(fixture_queue,7));
      assert(f.nodes.empty()&&f.releases.empty()&&f.erase_calls==2&&r->CurrentState()==R::State::owned);assert(r->Clear()); }
    { Fixture f;auto r=f.Make();assert(r->Acquire(Selection()));f.wrapper_valid=false;f.fail_erase=true;
      assert(!r->Submit(fixture_queue,7));f.Quarantined(*r); }
    for(unsigned count:{0U,1U}) {
        Fixture f; auto r=f.Make(); assert(r->Acquire(Selection())); f.submit_count=count; assert(r->Submit(fixture_queue,7)==(count!=0));
        if(count) { assert(r->SubmittedCount()==1 && r->Retire(7)); } assert(r->Clear() && !f.model_refs && !f.clone_refs);
    }
}
}
int main() { Normal(); StopAndStale(); Faults(); ContextAndReentry(); Qualification(); }
