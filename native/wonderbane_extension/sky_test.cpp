#include "sky.h"
#include "sky_binding.h"
#include "sky_asset_identity.h"
#include <cstdio>
#include <cmath>
#include <limits>
using namespace wonderbane::extension;
namespace {int failures=0;void Check(bool v,const char* message){if(!v){std::fprintf(stderr,"%s\n",message);++failures;}}
bool Near(sky::Vec a,sky::Vec b){return std::abs(a.x-b.x)+std::abs(a.y-b.y)+std::abs(a.z-b.z)<0.0001F;}}
int main(){
    sky::Settings settings;Check(sky::Valid(settings),"default settings valid");
    settings.intensity=std::numeric_limits<float>::quiet_NaN();Check(!sky::Valid(settings),"NaN rejected");settings={};
    settings.enabled=2;Check(!sky::Valid(settings),"unknown flags rejected");settings={};
    HMODULE module=GetModuleHandleW(nullptr);HRSRC r=FindResourceW(module,MAKEINTRESOURCEW(201),RT_RCDATA);
    Check(r&&SizeofResource(module,r)==sizeof(sky::Asset),"packaged resource size");if(!r)return 1;
    const auto* a=static_cast<const sky::Asset*>(LockResource(LoadResource(module,r)));
    Check(a&&sky::ValidAsset(*a)&&sky::Hash(a,sizeof(*a),sky::kAssetHash),"packaged resource identity");if(!a)return 1;
    auto bad=*a;bad.clouds[0].width=0;Check(!sky::ValidAsset(bad),"malformed cloud rejected");
    GraphicsCameraState camera{};camera.view_matrix[0]=camera.view_matrix[5]=camera.view_matrix[10]=camera.view_matrix[15]=1;
    camera.projection_matrix[0]=1;camera.projection_matrix[5]=1.5F;
    const auto ray=sky::Ray(camera,0.3F,0.2F,0);
    camera.view_matrix[12]=10000;camera.view_matrix[13]=-42;camera.view_matrix[14]=12000;
    Check(Near(ray,sky::Ray(camera,0.3F,0.2F,0)),"translation cannot move infinite sky");
    Check(!Near(ray,sky::Ray(camera,0.3F,0.2F,90)),"orientation rotates sky");
    camera.view_matrix[0]=0;camera.view_matrix[2]=-1;camera.view_matrix[8]=1;camera.view_matrix[10]=0;
    Check(!Near(ray,sky::Ray(camera,0.3F,0.2F,0)),"camera yaw rotates sky");
    const sky::Vec fog{.2F,.3F,.4F};
    Check(Near(sky::Shade(*a,settings,{0,0,-1},fog,true),fog),"horizon exactly joins active fog color");
    settings.intensity=0;Check(Near(sky::Shade(*a,settings,{0,0,-1},fog,true),fog),"intensity preserves fog seam");
    sky::Authority auth;auth.Upload(camera.view_matrix,1,2);
    Check(!auth.Consume(&camera,1,2,false),"unverified scenes excluded");
    Check(!auth.Consume(&camera,1,2,true),"refusal consumes camera");
    auth.Upload(camera.view_matrix,1,2);Check(!auth.Consume(&camera,2,2,true),"context changes excluded");
    auth.Upload(camera.view_matrix,1,2);Check(!auth.Consume(&camera,1,3,true),"stale lifecycle generation excluded");
    auth.Upload(camera.view_matrix,1,2);camera.view_matrix[12]+=1;Check(!auth.Consume(&camera,1,2,true),"changed current-frame view excluded");
    auth.Upload(camera.view_matrix,1,2);Check(auth.Consume(&camera,1,2,true),"exact fresh current-frame camera admitted");
    Check(!auth.Consume(&camera,1,2,true),"duplicate clear cannot reuse camera");
    auth.Upload(camera.view_matrix,1,2);auth.Reset();Check(!auth.Consume(&camera,1,2,true),"present/reset discards previous-frame camera");
    return failures?1:0;
}
