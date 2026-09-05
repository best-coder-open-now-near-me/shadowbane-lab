// Real WGL context exercises the production renderer and runtime. Native scene
// observations are controlled here; the separately tested resolver owns memory bindings.
#include "sky_runtime.cpp"
#include <filesystem>
#include <fstream>
#include <vector>
#include <cstdio>
#include <cmath>
#include <thread>
#include <atomic>
namespace wonderbane::extension::effects {
bool test_actor=false;
Attachment Resolve(Reader,void*,std::uint32_t,std::uint32_t) noexcept {
    Attachment a{};a.valid=test_actor;a.actor=1;a.uuid=2;a.zone=3;return a;
}
bool SameIdentity(const Attachment& a,const Attachment& b) noexcept {return a.valid&&b.valid&&a.actor==b.actor&&a.zone==b.zone;}
}
using namespace wonderbane::extension;
namespace {
int failures=0,native_calls=0;
void Check(bool v,const char* message){if(!v){std::fprintf(stderr,"%s\n",message);++failures;}}
void __fastcall FakeNative(void*,void*) {++native_calls;}
struct State {GLint mode=0,viewport[4]{},depth_func=0,shade=0,draw=0;GLboolean depth=0,mask=0,blend=0,fog=0;float view[16]{},projection[16]{},color[4]{};};
State Snapshot(){State s{};glGetIntegerv(GL_MATRIX_MODE,&s.mode);glGetIntegerv(GL_VIEWPORT,s.viewport);
    glGetIntegerv(GL_DEPTH_FUNC,&s.depth_func);glGetIntegerv(GL_SHADE_MODEL,&s.shade);glGetIntegerv(GL_DRAW_BUFFER,&s.draw);
    s.depth=glIsEnabled(GL_DEPTH_TEST);s.blend=glIsEnabled(GL_BLEND);s.fog=glIsEnabled(GL_FOG);glGetBooleanv(GL_DEPTH_WRITEMASK,&s.mask);
    glGetFloatv(GL_MODELVIEW_MATRIX,s.view);glGetFloatv(GL_PROJECTION_MATRIX,s.projection);glGetFloatv(GL_CURRENT_COLOR,s.color);return s;}
void Same(const State& a,const State& b){Check(a.mode==b.mode&&a.depth_func==b.depth_func&&a.shade==b.shade&&a.draw==b.draw
    &&a.depth==b.depth&&a.mask==b.mask&&a.blend==b.blend&&a.fog==b.fog&&!std::memcmp(a.viewport,b.viewport,sizeof(a.viewport))
    &&!std::memcmp(a.view,b.view,sizeof(a.view))&&!std::memcmp(a.projection,b.projection,sizeof(a.projection))
    &&!std::memcmp(a.color,b.color,sizeof(a.color)),"full fixed-function state restored");}
void Pixel(unsigned char* out){glReadPixels(32,32,1,1,GL_RGBA,GL_UNSIGNED_BYTE,out);}
}
int wmain(int argc,wchar_t** argv){
    WNDCLASSW wc{};wc.style=CS_OWNDC;wc.lpfnWndProc=DefWindowProcW;wc.hInstance=GetModuleHandleW(nullptr);wc.lpszClassName=L"SkyProductionTest";
    if(!RegisterClassW(&wc))return 2;
    HWND window=CreateWindowW(wc.lpszClassName,L"",WS_OVERLAPPEDWINDOW,0,0,160,160,nullptr,nullptr,wc.hInstance,nullptr);if(!window)return 3;
    HDC dc=GetDC(window);PIXELFORMATDESCRIPTOR pf{};pf.nSize=sizeof(pf);pf.nVersion=1;pf.dwFlags=PFD_DRAW_TO_WINDOW|PFD_SUPPORT_OPENGL|PFD_DOUBLEBUFFER;
    pf.iPixelType=PFD_TYPE_RGBA;pf.cColorBits=24;pf.cDepthBits=24;pf.cStencilBits=8;if(!SetPixelFormat(dc,ChoosePixelFormat(dc,&pf),&pf))return 4;
    HGLRC context=wglCreateContext(dc);if(!context||!wglMakeCurrent(dc,context))return 5;
    glViewport(0,0,64,64);glMatrixMode(GL_PROJECTION);glLoadIdentity();glFrustum(-1,1,-1,1,1,1000);
    glMatrixMode(GL_MODELVIEW);glLoadIdentity();
    GraphicsCameraState camera{};glGetFloatv(GL_MODELVIEW_MATRIX,camera.view_matrix);glGetFloatv(GL_PROJECTION_MATRIX,camera.projection_matrix);glGetIntegerv(GL_VIEWPORT,camera.viewport);
    Check(LoadSkyAsset(),"embedded production asset loads");sky::Settings settings{};settings.enabled=1;
    glEnable(GL_DEPTH_TEST);glDepthFunc(GL_GREATER);glEnable(GL_BLEND);glEnable(GL_FOG);glShadeModel(GL_FLAT);glColor4f(.2F,.3F,.4F,.5F);
    glClearColor(0,0,0,1);glClearDepth(.37);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);const auto state=Snapshot();
    float depth_before=0,depth_after=0;glReadPixels(32,32,1,1,GL_DEPTH_COMPONENT,GL_FLOAT,&depth_before);
    Check(sky::Render(sky_asset,settings,camera),"production sky paints background");Same(state,Snapshot());
    glReadPixels(32,32,1,1,GL_DEPTH_COMPONENT,GL_FLOAT,&depth_after);Check(depth_before==depth_after,"world depth preserved exactly");
    unsigned char pixel[4]{};Pixel(pixel);Check(pixel[0]+pixel[1]+pixel[2]>0,"background has visual content");
    // Native world draws run later; translucent pixels blend with sky instead of
    // being overwritten by a late depthless sky fill. UI draws follow the same rule.
    glDisable(GL_FOG);glDisable(GL_DEPTH_TEST);glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
    glMatrixMode(GL_PROJECTION);glLoadIdentity();glMatrixMode(GL_MODELVIEW);glLoadIdentity();
    glColor4f(1,0,0,.5F);glBegin(GL_QUADS);glVertex2f(-1,-1);glVertex2f(1,-1);glVertex2f(1,1);glVertex2f(-1,1);glEnd();
    unsigned char blended[4]{};Pixel(blended);Check(blended[0]>pixel[0]&&blended[1]<=pixel[1],"later translucency blends over background");
    glEnable(GL_ALPHA_TEST);glAlphaFunc(GL_GREATER,.5F);glColor4f(0,1,0,0);glBegin(GL_QUADS);glVertex2f(-1,-1);glVertex2f(1,-1);glVertex2f(1,1);glVertex2f(-1,1);glEnd();
    unsigned char cutout[4]{};Pixel(cutout);Check(!std::memcmp(blended,cutout,4),"alpha-test holes preserve composed background");glDisable(GL_ALPHA_TEST);
    glViewport(0,0,32,32);Check(!sky::Render(sky_asset,settings,camera),"unrelated viewport rejected");glViewport(0,0,64,64);
    glDrawBuffer(GL_FRONT);Check(!sky::Render(sky_asset,settings,camera),"unrelated draw target rejected");glDrawBuffer(GL_BACK);
    settings.enabled=0;Check(!sky::Render(sky_asset,settings,camera),"disable does not paint");settings.enabled=1;
    using Gen=void(APIENTRY*)(GLsizei,GLuint*);using Bind=void(APIENTRY*)(GLenum,GLuint);using Delete=void(APIENTRY*)(GLsizei,const GLuint*);
    const auto gen=reinterpret_cast<Gen>(wglGetProcAddress("glGenFramebuffers"));const auto bind=reinterpret_cast<Bind>(wglGetProcAddress("glBindFramebuffer"));
    const auto del=reinterpret_cast<Delete>(wglGetProcAddress("glDeleteFramebuffers"));
    if(gen&&bind&&del){GLuint fbo=0;gen(1,&fbo);bind(0x8D40,fbo);Check(!sky::Render(sky_asset,settings,camera),"offscreen FBO excluded");bind(0x8D40,0);del(1,&fbo);}
    if(argc==2){
        std::ifstream file(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);if(!file)return 6;
        const auto length=file.tellg();std::vector<unsigned char> bytes(static_cast<std::size_t>(length));file.seekg(0);file.read(reinterpret_cast<char*>(bytes.data()),length);
        const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(bytes.data());const auto* nt=reinterpret_cast<const IMAGE_NT_HEADERS32*>(bytes.data()+dos->e_lfanew);
        auto* image=static_cast<unsigned char*>(VirtualAlloc(nullptr,nt->OptionalHeader.SizeOfImage,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!image)return 7;
        std::memcpy(image,bytes.data(),nt->OptionalHeader.SizeOfHeaders);
        const auto* sections=IMAGE_FIRST_SECTION(nt);
        for(unsigned n=0;n<nt->FileHeader.NumberOfSections;++n)if(sections[n].SizeOfRawData)
            std::memcpy(image+sections[n].VirtualAddress,bytes.data()+sections[n].PointerToRawData,sections[n].SizeOfRawData);
        const auto base=static_cast<std::uint32_t>(reinterpret_cast<std::uintptr_t>(image));
        auto reloc=nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC];std::size_t offset=0;
        while(offset<reloc.Size){auto* block=reinterpret_cast<const IMAGE_BASE_RELOCATION*>(image+reloc.VirtualAddress+offset);if(!block->SizeOfBlock)break;
            auto* entries=reinterpret_cast<const WORD*>(block+1);for(unsigned n=0;n<(block->SizeOfBlock-sizeof(*block))/2;++n)if((entries[n]>>12)==3){
                auto* value=reinterpret_cast<std::uint32_t*>(image+block->VirtualAddress+(entries[n]&0xfff));*value+=base-0x400000U;}
            offset+=block->SizeOfBlock;}
        const auto started=StartSky(image,nt->OptionalHeader.SizeOfImage,kReviewedSceneExecutableHashes[2]);
        if(started){std::fprintf(stderr,"StartSky error %lu base %x size %lu\n",started,base,nt->OptionalHeader.SizeOfImage);return 8;}
        Check(started==ERROR_SUCCESS,"production startup and binding");
        Check(sky_control&&sky_control->ready&&sky_control->asset,"native channel and asset identity exposed");
        Check(StartSky(image,nt->OptionalHeader.SizeOfImage,kReviewedSceneExecutableHashes[2])==ERROR_ALREADY_INITIALIZED,"duplicate start excluded");
        sky_control->settings.enabled=1;InterlockedExchange(&sky_control->desired,2);effects::test_actor=true;
        glMatrixMode(GL_PROJECTION);glLoadMatrixf(camera.projection_matrix);glMatrixMode(GL_MODELVIEW);glLoadMatrixf(camera.view_matrix);
        ObserveSkyCameraUpload(base+0x51b1df,true);BeginSkyBackground(&camera,true);Check(sky_control->painted==1&&sky_control->applied==2,"fresh upload draws through production entry");
        BeginSkyBackground(&camera,true);Check(!sky_control->painted&&sky_control->reason==1,"duplicate stage rejected");
        ObserveSkyCameraUpload(base+0x51b1df,true);EndSkyFrame();BeginSkyBackground(&camera,true);Check(!sky_control->painted,"frame rollover discards camera");
        ObserveSkyCameraUpload(base+0x51b1df,false);BeginSkyBackground(&camera,true);Check(!sky_control->painted,"illegal observation excluded");
        ObserveSkyCameraUpload(base+0x51b1df,true);effects::test_actor=false;BeginSkyBackground(&camera,true);Check(!sky_control->painted,"login/missing actor excluded");effects::test_actor=true;
        sky_control->settings.enabled=2;InterlockedExchange(&sky_control->desired,4);ObserveSkyCameraUpload(base+0x51b1df,true);BeginSkyBackground(&camera,true);Check(!sky_control->painted&&sky_control->error==ERROR_INVALID_DATA,"invalid configuration restores native");
        auto saved=InterlockedExchangePointer(&sky_original,reinterpret_cast<PVOID>(&FakeNative));NativeSkyDraw(nullptr,nullptr);Check(native_calls==1,"unowned calls preserve native fallback");InterlockedExchangePointer(&sky_original,saved);
        StopSky();Check(!sky_control&&!sky_mapping&&!sky_slot,"stop restores slot and releases channel");
        Check(StartSky(image,nt->OptionalHeader.SizeOfImage,kReviewedSceneExecutableHashes[2])==ERROR_SUCCESS,"restart creates disabled generation");Check(!sky_control->settings.enabled,"restart cannot retain enabled configuration");StopSky();
        VirtualFree(image,0,MEM_RELEASE);
    }
    Check(glGetError()==GL_NO_ERROR,"no GL errors");wglMakeCurrent(nullptr,nullptr);wglDeleteContext(context);ReleaseDC(window,dc);DestroyWindow(window);
    return failures?1:0;
}
