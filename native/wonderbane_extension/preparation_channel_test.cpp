// Real producer ring, fences, publication, Controller and Runtime. The included
// fixture explicitly substitutes NativeActor gameplay, scene/manual admission,
// image verification and trace output. It does not execute a client image.
#define main PreparationRuntimeUnitFixture
#include "actor_action_runtime_test.cpp"
#undef main
#include "command_channel.h"
#include <iostream>

int main() {
    using namespace wonderbane::extension;
    const ProcessIdentity identity{GetCurrentProcessId(),f::Creation(GetCurrentProcess())};
    Check(outer::Start(identity),"production actor service registers");
    Tick();Check(outer::Ready(),"synthetic scene is bound");
    Check(StartClientActionCommandChannel(identity)==ERROR_SUCCESS,"real command mapping starts");
    command_channel_detail::RefreshCombatCapability(*command_channel_detail::g_runtime.storage);
    std::cout<<identity.process_id<<" "<<identity.creation_filetime_utc<<std::endl;
    bool done=false;
    const auto deadline=GetTickCount64()+30000;
    while(GetTickCount64()<deadline) {
        Tick();
        DWORD available{};
        if(PeekNamedPipe(GetStdHandle(STD_INPUT_HANDLE),nullptr,0,nullptr,&available,nullptr)&&available) {
            std::string line;std::getline(std::cin,line);
            if(line=="manual") { preparation_idle=false;++preparation_epoch;native_activity=true; }
            else if(line=="idle") { preparation_idle=true;++preparation_epoch; }
            else if(line=="settle") { poll_settled=true; }
            else if(line=="done") { done=true;break; }
            else { return 3; }
            Tick();std::cout<<"ack "<<line<<std::endl;
        }
        Sleep(1);
    }
    StopClientActionCommandChannel();
    std::cout<<calls<<" "<<begins<<" "<<pauses<<" "<<child_stops<<" "
             <<native_activity<<" "<<a::runtime.active<<std::endl;
    // A preparation parent must never acquire/pause movement or stop a child.
    return done&&calls==1&&begins==0&&pauses==0&&child_stops==0
        &&native_activity&&!a::runtime.active ? 0 : 2;
}
