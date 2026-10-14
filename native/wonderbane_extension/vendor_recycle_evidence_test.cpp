#include "vendor_recycle_evidence.h"
#include "vendor_controller.h"
#include <fstream>
#include <iostream>
#include <memory>
#include <string>
#undef NDEBUG
#include <cassert>
namespace r=wonderbane::extension::vendor_recycle;
namespace p=wonderbane::extension::vendor_production;
namespace v=wonderbane::extension::vendor;
namespace w=v::wire;
r::Manifest Manifest() {
    r::Manifest m{};m.owner.scene=m.owner.revision=1;m.owner.root=100;m.owner.manager=200;
    m.owner.menu=300;m.owner.inventory=400;m.owner.hireling=500;m.owner.building=2229645;m.owner.vendor=2517204;
    m.owner.count=2;m.owner.slots[0].entry=600;m.owner.slots[1].entry=700;
    m.count=7;m.gold=205328;m.refund=1057;m.digest.fill(1);
    for(unsigned i=0;i<m.count;++i){m.items[i]=4294904956U+i;}return m;
}
p::Payload Body(const r::Manifest& m,bool send=false,bool empty=false) {
    p::Payload body{};body.action=send?3U:7U;body.fields=send?0U:4U;
    body.building={m.owner.building,8};body.vendor={m.owner.vendor,42};body.quantity=1;
    body.strongbox_gold=send?0:empty?m.gold:m.gold+m.refund;
    if(!empty){body.references_count=m.count;for(unsigned i=0;i<m.count;++i){body.references[i]={m.items[send?i:m.count-i-1],40};}}
    return body;
}
std::unique_ptr<p::Batch> Batch(const r::Manifest& m) {
    auto batch=std::make_unique<p::Batch>();batch->after={6936,134364730542458483ULL,682,0,0};batch->count=25;
    auto& send=batch->records[0];send.sequence=658;send.stage=4;send.thread_id=10;send.flags=3;
    send.scene_epoch=1;send.local={123,53};send.payload=Body(m,true);
    for(unsigned j=0;j<8;++j) {
        for(unsigned i=0;i<3;++i) {
            const auto at=1+j*3+i;auto& record=batch->records[at];record.sequence=658+at;
            record.stage=i+1;record.decode_sequence=659+j*3;record.thread_id=i?10:20;
            record.flags=i?7:3;record.scene_epoch=1;record.local={123,53};record.payload=Body(m,false,j<7);
        }
    }return batch;
}
struct Fake:v::Invoker {
    unsigned calls=0;w::Outcome result=w::Outcome::submitted;
    w::Outcome Invoke(w::Verb,const w::Snapshot&,std::uint32_t) noexcept override {++calls;return result;}
};
w::Command Command(const w::Snapshot& owner,unsigned key=1) {
    w::Command c{};c.host={1,1,1};c.window=1000;c.request[0]=static_cast<std::uint8_t>(key);c.expected=owner;c.item=7;
    w::RecycleBatch data{};data.digest.fill(1);data.gold=205328;data.refund=1057;
    for(unsigned i=0;i<c.item;++i){data.items[i]=4294904956U+i;}
    std::memcpy(c.reserved,&data,sizeof(data));return c;
}
int main(int argc,char** argv) {
    auto manifest=Manifest();
    if(argc==4) {
        std::ifstream stream(argv[1],std::ios::binary|std::ios::ate);assert(stream);
        const auto size=stream.tellg();assert(size>0 && size%sizeof(p::Record)==0 && size<=256*sizeof(p::Record));
        auto batch=std::make_unique<p::Batch>();batch->count=static_cast<unsigned>(size/sizeof(p::Record));
        stream.seekg(0);stream.read(reinterpret_cast<char*>(batch->records.data()),size);assert(stream);
        const auto& first=batch->records[0];manifest.owner.scene=first.scene_epoch;
        manifest.owner.building=first.payload.building[0];manifest.owner.vendor=first.payload.vendor[0];
        manifest.count=first.payload.references_count;assert(manifest.count && manifest.count<=r::kItems);
        for(unsigned i=0;i<manifest.count;++i){manifest.items[i]=first.payload.references[i][0];}
        std::sort(manifest.items.begin(),manifest.items.begin()+manifest.count);
        manifest.gold=static_cast<unsigned>(std::stoul(argv[2]));manifest.refund=static_cast<unsigned>(std::stoul(argv[3]));
        const auto floor=static_cast<std::uint64_t>(first.sequence)-1;
        batch->after={6936,134364730542458483ULL,floor+batch->count,0,0};
        r::Evidence proof;proof.Begin(manifest,first.local,{6936,134364730542458483ULL,floor,0,0});
        assert(proof.Receive(*batch) && proof.Verified());
        std::cout<<"manual native evidence verified sequence="<<proof.Completion()<<" commands=0\n";return 0;
    }
    r::Evidence proof;proof.Begin(manifest,{123,53},{6936,134364730542458483ULL,657,0,0});
    auto batch=Batch(manifest);assert(proof.Receive(*batch) && proof.Verified() && proof.Completion()==682);
    for(unsigned mutation=0;mutation<15;++mutation) {
        proof.Begin(manifest,{123,53},{6936,134364730542458483ULL,657,0,0});batch=Batch(manifest);
        if(mutation==0){batch->after.rejected=1;}
        if(mutation==1){batch->after.ticket_drops=1;}
        if(mutation==2){batch->after.creation++;}
        if(mutation==3){batch->records[2].sequence++;}
        if(mutation==4){batch->records[0].payload.references[0]=batch->records[0].payload.references[1];}
        if(mutation==5){batch->records[0].payload.action=7;}
        if(mutation==6){batch->records[24].payload.strongbox_gold++;}
        if(mutation==7){batch->records[24].thread_id++;}
        if(mutation==8){batch->records[24].decode_sequence++;}
        if(mutation==9){batch->records[23].payload.references[0][1]=0;}
        if(mutation==10){batch->records[22].payload.references[0][0]=1;}
        if(mutation==11){batch->records[24].local[0]++;}
        if(mutation==12){batch->records[24].scene_epoch++;}
        if(mutation==13){batch->records[24].payload.error=1;}
        if(mutation==14){batch->records[24].stage=2;}
        assert(!proof.Receive(*batch) && !proof.Verified());assert(!proof.Receive(*Batch(manifest)));
    }
    // Native command identity is never replayed, and only an exact positive
    // callback with a qualified post-state releases the pending operation.
    v::Controller controller;controller.Observe(manifest.owner,true,false,100);Fake invoker;
    auto command=Command(controller.Current());assert(w::Valid(w::Verb::recycle,command));
    auto result=controller.Execute(w::Verb::recycle,command,true,true,invoker,100);
    assert(result.signature==w::recycle_magic && result.outcome==1 && invoker.calls==1);
    controller.Observe(manifest.owner,true,false,101);assert(controller.PendingRecycle());
    assert(controller.Execute(w::Verb::recycle,command,true,true,invoker,102).outcome==1 && invoker.calls==1);
    auto changed=command;changed.reserved[0]^=1;assert(controller.Execute(w::Verb::recycle,changed,true,true,invoker,103).outcome==4);
    controller.Observe(manifest.owner,true,false,104,{},v::OrderProof::waiting,v::OrderProof::verified,{657,682,1057,206385});
    assert(!controller.Busy());auto inspect=Command({},9);inspect.item=0;std::memset(inspect.reserved,0,sizeof(inspect.reserved));
    result=controller.Execute(w::Verb::inspect_recycle,inspect,true,true,invoker,105);
    assert(result.signature==w::recycle_magic && result.transition_request==command.request && result.transition_item==7);
    w::RecycleCompletion completion{};std::memcpy(&completion,result.reserved,sizeof(completion));assert(completion.sequence==682 && completion.gold==206385);
    for(bool timeout:{false,true}) {
        v::Controller uncertain;uncertain.Observe(manifest.owner,true,false,100);Fake fake;
        auto c=Command(uncertain.Current());assert(uncertain.Execute(w::Verb::recycle,c,true,true,fake,100).outcome==1);
        uncertain.Observe(manifest.owner,true,false,timeout?5101:101,{},v::OrderProof::waiting,timeout?v::OrderProof::waiting:v::OrderProof::invalid);
        assert(uncertain.Busy() && uncertain.Execute(w::Verb::inspect_recycle,inspect,true,true,fake,5102).flags&w::unresolved);
        assert(uncertain.Execute(w::Verb::recycle,Command(uncertain.Current(),10),true,true,fake,5103).outcome==6 && fake.calls==1);
    }
    command=Command(manifest.owner);command.item=0;assert(!w::Valid(w::Verb::recycle,command));
    command=Command(manifest.owner);command.item=49;assert(!w::Valid(w::Verb::recycle,command));
    command=Command(manifest.owner);command.expected.slots[0].item=1;command.expected.slots[0].state=1;assert(!w::Valid(w::Verb::recycle,command));
    command=Command(manifest.owner);command.reserved[243]=1;assert(!w::Valid(w::Verb::recycle,command));
    std::cout<<"recycle evidence and controller checks passed\n";return 0;
}
