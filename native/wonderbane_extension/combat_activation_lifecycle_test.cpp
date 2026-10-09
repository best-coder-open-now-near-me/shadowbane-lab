#include "combat_activation_lifecycle.h"
#undef NDEBUG
#include <cassert>
#include <cstdio>
namespace i=wonderbane::extension::combat::activation;
namespace {
const i::ActivationIdentity actor{0x20000000,{4050960,53},3};
constexpr std::uint32_t power=429021400;
i::ActivationHistory::Transition Start(i::ActivationHistory& history) {
    const auto start=history.BeginStart(actor,power,0x30000000,0x31000000,0x32000000,7);
    assert(start&&history.StateReturned(start,true));
    const auto append=history.BeginAppend(actor,power,0x30000000,0x31000000,0x32000000,7);
    assert(append&&history.AppendReturned(append,true)&&history.StartProcessReturned(append,true));return append;
}
void Interrupt(i::ActivationHistory& history) {
    const auto move=history.BeginMovement(actor);assert(move&&history.MovementReturned(move,true));
}
}
int main(){
    // Retained duplicates belong to native bookkeeping. Every independently
    // observed setter+append generation can retire once; old tickets cannot.
    i::ActivationHistory history;std::uint64_t prior{};
    for(unsigned generation=0;generation<4;++generation){
        const auto ticket=history.Arm(0,actor,power);assert(ticket&&ticket!=prior);
        assert(!history.Interrupted(0,ticket,actor));history.QueueResult(0,ticket,true);
        Start(history);Interrupt(history);assert(history.Interrupted(0,ticket,actor));
        assert(!history.Interrupted(0,prior,actor));prior=ticket;
    }
    // Terminal local evidence survives later manual work, but never transfers
    // to a newer reserved item command or replaced scene/actor.
    history.OtherActivity(actor.actor);history.ForeignItemSend(actor.actor);
    assert(history.Interrupted(0,prior,actor));
    auto other=actor;++other.scene;assert(!history.Interrupted(0,prior,other));
    other=actor;++other.key[0];assert(!history.Interrupted(0,prior,other));
    assert(!history.Arm(1,other,power));other=actor;++other.scene;assert(!history.Arm(1,other,power));
    const auto newer=history.Arm(0,actor,power);assert(!history.Interrupted(0,newer,actor));
    // A manual item send before or after start cannot resolve the owned queue.
    for(bool active:{false,true}){
        i::ActivationHistory h;const auto ticket=h.Arm(0,actor,power);h.QueueResult(0,ticket,true);
        if(active){Start(h);}h.ForeignItemSend(actor.actor);
        assert(!h.BeginStart(actor,power,1,2,3,7)&&!h.BeginMovement(actor)&&!h.Interrupted(0,ticket,actor));
    }
    // Neither queue failure nor an abnormal/changed native call grants proof.
    for(unsigned failure=0;failure<4;++failure){
        i::ActivationHistory h;const auto ticket=h.Arm(0,actor,power);h.QueueResult(0,ticket,true);
        auto state=h.BeginStart(actor,power,1,2,3,7);assert(state);
        if(failure==0){assert(!h.StateReturned(state,false));}
        else {assert(h.StateReturned(state,true));
            auto append=h.BeginAppend(actor,power,1,2,3,7);assert(append);
            if(failure==1){assert(!h.AppendReturned(append,false));}
            else {assert(h.AppendReturned(append,true)&&h.StartProcessReturned(append,true));auto move=h.BeginMovement(actor);assert(move);
                if(failure==2){assert(!h.MovementReturned(move,false));}
                if(failure==3){h.OtherActivity(actor.actor);assert(!h.MovementReturned(move,true));}
            }
        }
        assert(!h.Interrupted(0,ticket,actor));
    }
    // Nested same-ID starts invalidate the outer process even if the captured
    // message/vector bytes are restored before its append.
    for(unsigned changed=0;changed<5;++changed){
        i::ActivationHistory h;const auto ticket=h.Arm(0,actor,power);h.QueueResult(0,ticket,true);
        auto state=h.BeginStart(actor,power,1,2,3,7);assert(state&&h.StateReturned(state,true));
        if(changed==0){assert(!h.BeginStart(actor,power,1,2,3,7));}
        const auto append=h.BeginAppend(actor,power,changed==1?9:1,changed==2?9:2,changed==3?9:3,changed==4?9:7);
        assert(!append&&!h.Interrupted(0,ticket,actor));
    }
    // Unrelated actors cannot poison the local mutation generation.
    {
        i::ActivationHistory h;const auto ticket=h.Arm(0,actor,power);h.QueueResult(0,ticket,true);
        auto state=h.BeginStart(actor,power,1,2,3,7);assert(state);
        h.OtherActivity(actor.actor+4);h.ForeignItemSend(actor.actor+4);
        assert(h.StateReturned(state,true));auto append=h.BeginAppend(actor,power,1,2,3,7);
        assert(append&&h.AppendReturned(append,true)&&h.StartProcessReturned(append,true));Interrupt(h);assert(h.Interrupted(0,ticket,actor));
    }
    // Two unresolved semantic candidates for one power have no unique journal
    // association. Neither is cleared by a later single activation.
    {
        i::ActivationHistory h;const auto a=h.Arm(0,actor,power),b=h.Arm(1,actor,power),c=h.Arm(2,actor,power);
        h.QueueResult(0,a,true);h.QueueResult(1,b,true);h.QueueResult(2,c,true);
        assert(!h.BeginStart(actor,power,1,2,3,7));
        assert(!h.BeginStart(actor,power,1,2,3,7)); // No leftover candidate survives ambiguity.
        assert(!h.Interrupted(0,a,actor)&&!h.Interrupted(1,b,actor)&&!h.Interrupted(2,c,actor));
    }
    // The shared semantic generation also covers an owned self-power, but
    // never converts entered-uncertain without normal followup into local proof.
    for(bool followup:{false,true}){
        i::ActivationHistory h;const auto ticket=h.Arm(0,actor,power,i::ActivationOrigin::self_power);
        h.QueueResult(0,ticket,true);h.OwnedFollowup(0,ticket,followup);Start(h);Interrupt(h);
        assert(h.Interrupted(0,ticket,actor)&&h.LocalInterrupted(0,ticket,actor)==followup);
        h.OtherActivity(actor.actor);assert(h.LocalInterrupted(0,ticket,actor)==followup);
    }
    // A start before actual queued-send proof cannot be adopted retroactively.
    {
        i::ActivationHistory h;const auto ticket=h.Arm(0,actor,power);
        assert(!h.BeginStart(actor,power,1,2,3,7));
        h.ForeignPowerUse(actor.actor);h.QueueResult(0,ticket,true);
        assert(!h.BeginStart(actor,power,1,2,3,7));
    }
    // Qualified owned followup can directly establish state6 before any
    // incoming message. Its incoming acknowledgement continues the same ticket;
    // a later movement need not wait for that acknowledgement.
    for(bool incoming:{false,true}){
        i::ActivationHistory h;const auto ticket=h.Arm(0,actor,power,i::ActivationOrigin::self_power);
        h.QueueResult(0,ticket,true);const auto followup=h.BeginOwnedFollowup(0,ticket);
        assert(followup&&h.OwnedFollowupReturned(followup,true,true));
        if(incoming){Start(h);}
        Interrupt(h);assert(h.LocalTerminal(0,ticket,actor));
    }
    {
        i::ActivationHistory h;const auto ticket=h.Arm(0,actor,power,i::ActivationOrigin::self_power);
        h.QueueResult(0,ticket,true);const auto followup=h.BeginOwnedFollowup(0,ticket);assert(followup);
        h.ForeignPowerUse(actor.actor);assert(!h.OwnedFollowupReturned(followup,true,true));
        assert(!h.BeginMovement(actor)&&!h.LocalTerminal(0,ticket,actor));
    }
    // Exact completion needs both qualified remover sites of the same incoming
    // frame. Nested/manual activity, including restored same-ID bytes, prevents
    // terminal attribution. Vector emptiness is deliberately not a model input.
    for(unsigned mutation=0;mutation<5;++mutation){
        i::ActivationHistory h;const auto ticket=h.Arm(0,actor,power,i::ActivationOrigin::self_power);
        h.QueueResult(0,ticket,true);h.OwnedFollowup(0,ticket,true);Start(h);
        auto end=h.BeginCompletion(actor,power,4,5,6,7);assert(end);
        if(mutation==1){h.ForeignPowerUse(actor.actor);}
        if(mutation==1){assert(!h.CompletionStateReturned(end,true));}
        else{
            assert(h.CompletionStateReturned(end,true));
            auto first=h.BeginRemoval(actor,power,4,5,6,7,false);assert(first);
            assert(h.RemovalReturned(first,false,true));
            assert(!h.LocalTerminal(0,ticket,actor));
            if(mutation==2){h.OtherActivity(actor.actor);}
            if(mutation==3){assert(!h.BeginStart(actor,power,4,5,6,7));}
            auto tail=h.BeginRemoval(actor,power,4,mutation==4?99:5,6,7,true);
            if(mutation){assert(!tail);}
            else{assert(tail&&h.RemovalReturned(tail,true,true));
                assert(!h.LocalTerminal(0,ticket,actor));assert(h.CompletionProcessReturned(tail,true));}
        }
        assert(h.LocalTerminal(0,ticket,actor)==(mutation==0));
        assert(!h.Interrupted(0,ticket,actor));
        if(!mutation){
            h.ForeignPowerUse(actor.actor);h.QueueResult(0,ticket,false);assert(h.LocalTerminal(0,ticket,actor));
            auto replaced=actor;++replaced.scene;assert(!h.ResetExactLifetime(replaced));
            assert(h.ResetExactLifetime(actor)&&!h.LocalTerminal(0,ticket,actor));
            const auto next=h.Arm(0,replaced,power);assert(next>ticket);
        }
    }
    // Positive newer manual activation relinquishes only old bot control,
    // never the old application's interpretation. Sending/attempt alone is
    // insufficient; nested mutation, fault and a later reservation cannot borrow
    // the old manual-start candidate.
    for(unsigned mutation=0;mutation<5;++mutation){
        i::ActivationHistory h;const auto ticket=h.Arm(0,actor,power,i::ActivationOrigin::self_power);
        h.QueueResult(0,ticket,true);h.OwnedFollowup(0,ticket,true);Start(h);
        h.ManualSend(actor.actor,power+1);assert(!h.LocalTerminal(0,ticket,actor));
        auto start=h.BeginManualStart(actor,power+1,11,12,13,7);assert(start);
        if(mutation==1){h.OtherActivity(actor.actor);}
        if(mutation==1){assert(!h.ManualStateReturned(start,true));}
        else{
            assert(h.ManualStateReturned(start,true));
            auto append=h.BeginManualAppend(actor,power+1,11,12,13,7);assert(append&&h.ManualAppendReturned(append,true));
            if(mutation==2){h.ForeignItemSend(actor.actor);}
            if(mutation==3){const auto replacement_ticket=h.Arm(1,actor,power,i::ActivationOrigin::self_power);h.QueueResult(1,replacement_ticket,true);}
            assert(h.ManualProcessReturned(append,mutation!=4)==(mutation==0));
        }
        assert(h.LocalTerminal(0,ticket,actor)==(mutation==0));
        assert(!h.Interrupted(0,ticket,actor));
        assert(h.Read(0).phase==i::ActivationPhase::unknown&&h.Read(0).queued);
    }
    for(bool observed:{false,true}){
        i::ActivationHistory h;const auto ticket=h.Arm(0,actor,power,i::ActivationOrigin::self_power);
        h.QueueResult(0,ticket,true);h.OwnedFollowup(0,ticket,true);Start(h);
        h.ManualSend(actor.actor,power+1);
        assert(h.ManualDirectReturned(actor,power+1,observed)==observed);
        assert(h.LocalTerminal(0,ticket,actor)==observed&&!h.Interrupted(0,ticket,actor));
    }
    std::puts("activation lifecycle generations passed");return 0;
}
