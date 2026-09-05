#include "selected_cue_gpu.h"
#include <gl/GL.h>
#include <array>
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <chrono>
#include <cstdlib>
using namespace wonderbane::extension;
namespace {
int failures=0;
void Check(bool ok,const char* label){if(!ok){std::fprintf(stderr,"%s\n",label);++failures;}}
struct State {
    GLint program{},active{},fbo{},draw{},read{},matrix{},viewport[4]{},textures[3]{};
    GLint depth_func{},blend_src{},blend_dst{},equation{};
    GLboolean alpha_test{};GLfloat alpha_ref{};
    GLboolean depth{},blend{},mask{}; GLfloat clear[4]{};
};
using Active=void(APIENTRY*)(GLenum);
State Snapshot(){
    State s{}; auto active=reinterpret_cast<Active>(wglGetProcAddress("glActiveTexture"));
    glGetIntegerv(0x8B8D,&s.program);glGetIntegerv(0x84E0,&s.active);glGetIntegerv(0x8CA6,&s.fbo);
    glGetIntegerv(GL_DRAW_BUFFER,&s.draw);glGetIntegerv(GL_READ_BUFFER,&s.read);
    glGetIntegerv(GL_MATRIX_MODE,&s.matrix);glGetIntegerv(GL_VIEWPORT,s.viewport);
    s.depth=glIsEnabled(GL_DEPTH_TEST);s.blend=glIsEnabled(GL_BLEND);
    glGetIntegerv(GL_DEPTH_FUNC,&s.depth_func);glGetIntegerv(GL_BLEND_SRC,&s.blend_src);
    glGetIntegerv(GL_BLEND_DST,&s.blend_dst);glGetIntegerv(0x8009,&s.equation);
    s.alpha_test=glIsEnabled(GL_ALPHA_TEST);glGetFloatv(GL_ALPHA_TEST_REF,&s.alpha_ref);
    glGetBooleanv(GL_DEPTH_WRITEMASK,&s.mask);glGetFloatv(GL_COLOR_CLEAR_VALUE,s.clear);
    for(unsigned n=0;n<3;++n){active(0x84C0+n);glGetIntegerv(GL_TEXTURE_BINDING_2D,&s.textures[n]);}
    active(static_cast<GLenum>(s.active));return s;
}
void Same(const State& a,const State& b){
    Check(a.program==b.program && a.active==b.active && a.fbo==b.fbo
        && a.draw==b.draw && a.read==b.read && a.matrix==b.matrix
        && a.depth_func==b.depth_func && a.blend_src==b.blend_src && a.blend_dst==b.blend_dst
        && a.equation==b.equation && a.alpha_test==b.alpha_test && a.alpha_ref==b.alpha_ref
        && a.depth==b.depth && a.blend==b.blend && a.mask==b.mask
        && std::memcmp(a.viewport,b.viewport,sizeof(a.viewport))==0
        && std::memcmp(a.textures,b.textures,sizeof(a.textures))==0
        && std::memcmp(a.clear,b.clear,sizeof(a.clear))==0,"graphics state restored");
}
void Rect(float x0,float x1,float y0,float y1,float z){
    glBegin(GL_QUADS);glVertex3f(x0,y0,z);glVertex3f(x1,y0,z);
    glVertex3f(x1,y1,z);glVertex3f(x0,y1,z);glEnd();
}
std::array<unsigned char,4> NativeTransparency(bool late_composite,bool depth_write,bool foreground){
    glDepthMask(GL_TRUE);glDisable(GL_BLEND);glColor4f(0,0,0,1);
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"native foreground selected mesh begin");
    auto mesh=[](void*) noexcept {Rect(-.4F,.4F,-.5F,.5F,0);};
    Check(cue::CaptureGeometry(mesh,nullptr),"native foreground selected mesh capture");mesh(nullptr);
    Check(cue::AfterOwnedDraw(),"native foreground selected mesh end");
    cue::Settings settings{};settings.enabled=1;
    if(!late_composite)Check(cue::CompositeMask(settings,{}),"reference cue before native foreground");
    glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
    glDepthMask(depth_write?GL_TRUE:GL_FALSE);glColor4f(1,0,0,.5F);
    Rect(-.6F,.6F,-.6F,.6F,foreground?-.5F:.5F);
    if(late_composite)Check(cue::CompositeMask(settings,{}),"candidate cue after native foreground");
    std::array<unsigned char,4> pixel{};glReadPixels(foreground?230:190,240,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel.data());
    glDepthMask(GL_TRUE);glDisable(GL_BLEND);return pixel;
}
unsigned Pixel(int x,int y){std::array<unsigned char,4> p{};glReadPixels(x,y,1,1,GL_RGBA,GL_UNSIGNED_BYTE,p.data());return p[0]+p[1]+p[2];}
}
int main(int argc,char** argv){
    if(argc>2 || (argc==2 && std::strcmp(argv[1],"--cost")!=0
        && std::strcmp(argv[1],"--native-transparency")!=0)){
        std::fprintf(stderr,"usage: selected_cue_gpu_test [--cost|--native-transparency]\n");return 2;
    }
    WNDCLASSW wc{};wc.style=CS_OWNDC;wc.lpfnWndProc=DefWindowProcW;
    wc.hInstance=GetModuleHandleW(nullptr);wc.lpszClassName=L"SelectedCueGpuTest";
    if(!RegisterClassW(&wc))return 2;
    HWND window=CreateWindowW(wc.lpszClassName,L"",WS_OVERLAPPEDWINDOW,0,0,680,540,nullptr,nullptr,wc.hInstance,nullptr);
    if(!window)return 3;
    HDC dc=GetDC(window);PIXELFORMATDESCRIPTOR pf{};pf.nSize=sizeof(pf);pf.nVersion=1;
    pf.dwFlags=PFD_DRAW_TO_WINDOW|PFD_SUPPORT_OPENGL|PFD_DOUBLEBUFFER;
    pf.iPixelType=PFD_TYPE_RGBA;pf.cColorBits=24;pf.cDepthBits=24;pf.cStencilBits=8;
    if(!SetPixelFormat(dc,ChoosePixelFormat(dc,&pf),&pf))return 4;
    HGLRC context=wglCreateContext(dc);if(!context || !wglMakeCurrent(dc,context))return 5;
    if(!wglGetProcAddress("glGenFramebuffers")) {
        std::fprintf(stderr,"SKIP: context lacks framebuffer objects\n");return 77;
    }
    glViewport(0,0,640,480);glMatrixMode(GL_PROJECTION);glLoadIdentity();
    glMatrixMode(GL_MODELVIEW);glLoadIdentity();glEnable(GL_DEPTH_TEST);glDepthFunc(GL_LESS);
    glClearColor(0,0,0,0);glClearDepth(1);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    if(argc==2 && std::strcmp(argv[1],"--native-transparency")==0){
        const auto equal=[](const auto& x,const auto& y){
            for(int n=0;n<3;++n)if(std::abs(int(x[n])-int(y[n]))>1)return false;
            return true;
        };
        for(bool foreground:{true,false})for(bool depth_write:{false,true}){
            // Foreground must blend over the glow; background must remain below
            // its halo. Sample the halo for background, outside native mesh depth.
            const auto expected=NativeTransparency(!foreground,depth_write,foreground);
            const auto actual=NativeTransparency(true,depth_write,foreground);
            const bool correct=equal(expected,actual);
            std::printf("native alpha=.5 foreground=%d depth_write=%d expected_rgb=%u,%u,%u actual_rgb=%u,%u,%u\n",
                int(foreground),int(depth_write),unsigned(expected[0]),unsigned(expected[1]),unsigned(expected[2]),unsigned(actual[0]),unsigned(actual[1]),unsigned(actual[2]));
            Check(correct,"cue must preserve native transparency on both sides of its depth");
            if(!foreground){
                const auto early=NativeTransparency(false,depth_write,foreground);
                Check(!equal(expected,early),"background halo case must reject wholesale early composition");
                std::printf("wholesale-early-counterexample depth_write=%d early_rgb=%u,%u,%u\n",
                    int(depth_write),unsigned(early[0]),unsigned(early[1]),unsigned(early[2]));
            }
        }
        cue::ReleaseMask();wglMakeCurrent(nullptr,nullptr);wglDeleteContext(context);ReleaseDC(window,dc);DestroyWindow(window);
        return failures?1:0;
    }
    auto initial=Snapshot();Check(cue::BeginMask(),"mask resource creation");Same(initial,Snapshot());
    Check(cue::AllocatedMaskBytes()==640ULL*480*8,"normal mesh uses only two depth textures");
    Check(cue::BeforeOwnedDraw() && cue::BeforeLegacyGeometry(),"before legacy capture");
    Check(cue::AllocatedMaskBytes()>640ULL*480*8 && cue::AllocatedMaskBytes()<=640ULL*480*28,"legacy storage allocated only on demand");Same(initial,Snapshot());
    glColor3f(0,0,0);Rect(-0.4F,0.4F,-0.5F,0.5F,0);
    Check(cue::AfterOwnedDraw(),"after capture");Same(initial,Snapshot());
    // A later nearer obstacle hides half of the selected silhouette.
    Rect(0,0.6F,-0.6F,0.6F,-0.5F);
    cue::Settings s{};s.enabled=1;s.radius=8;
    Check(cue::CompositeMask(s,{}),"mask composite");Same(initial,Snapshot());
    Check(Pixel(230,240)>0,"selected visible silhouette is tinted");
    Check(Pixel(380,240)==0,"later obstacle hides selected coverage");
    Check(Pixel(189,240)>0,"glow extends beyond true silhouette");
    Check(Pixel(170,240)==0,"glow has bounded radius");
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    Check(cue::BeginMask(),"fresh scene clears previous mask");
    Check(cue::CompositeMask(s,{}),"empty scene composite");
    Check(Pixel(230,240)==0,"no stale carryover");
    cue::Direction d{true,true,-1,-1};
    Check(cue::CompositeMask(s,d),"offscreen direction draw");Same(initial,Snapshot());
    Check(Pixel(44,394)>0,"indicator is in the client viewport");
    Check(cue::BeginMask(),"begin before viewport transition");
    glViewport(0,0,600,400);
    Check(!cue::CompositeMask(s,{}),"viewport change rejects stale capture");
    Check(cue::BeginMask(),"resize recreates matching resources");
    Check(cue::CompositeMask(s,{}),"resized scene composite");
    glViewport(0,0,640,480);
    // Real non-depth-writing mesh: same client arrays/material, private depth
    // capture, original native color submission, then normal cue composite.
    const GLfloat vertices[]{-.4F,-.5F,0,.4F,-.5F,0,.4F,.5F,0,-.4F,.5F,0};
    const GLfloat texcoords[]{0,0,1,0,1,1,0,1};
    glEnableClientState(GL_VERTEX_ARRAY);glVertexPointer(3,GL_FLOAT,0,vertices);
    auto mesh=[](void*) noexcept {glDrawArrays(GL_QUADS,0,4);};
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"begin translucent mesh");
    glDepthMask(GL_FALSE);glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
    glColor4f(0,0,0,.5F);auto material=Snapshot();
    Check(cue::CaptureGeometry(mesh,nullptr),"capture native translucent mesh");Same(material,Snapshot());
    mesh(nullptr);Check(cue::AfterOwnedDraw(),"finish translucent mesh");
    glDepthMask(GL_TRUE);glDisable(GL_BLEND);glColor4f(0,0,0,1);
    Rect(0,.6F,-.6F,.6F,-.5F); // nearer opaque foreground
    Rect(-.6F,0,-.6F,.6F,.5F); // farther opaque background
    Check(cue::CompositeMask(s,{}),"translucent silhouette composite");
    Check(Pixel(230,240)>0,"translucent mesh glows in front of farther background");
    Check(Pixel(380,240)==0,"nearer opaque foreground occludes translucent mesh");
    for(GLenum destination:{GL_ONE_MINUS_SRC_ALPHA,GL_ONE}){
        glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
        Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"begin zero-alpha mesh");
        glDepthMask(GL_FALSE);glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,destination);
        glColor4f(1,1,1,0);material=Snapshot();
        Check(cue::CaptureGeometry(mesh,nullptr),"capture zero-alpha mesh");Same(material,Snapshot());
        mesh(nullptr);Check(cue::AfterOwnedDraw(),"finish zero-alpha mesh");
        glDepthMask(GL_TRUE);glDisable(GL_BLEND);
        Check(cue::CompositeMask(s,{}),"zero-alpha composite");
        Check(Pixel(230,240)==0,"zero-alpha source-over/additive material has no silhouette");
    }
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"begin RGB additive mesh");
    glDepthMask(GL_FALSE);glEnable(GL_BLEND);glBlendFunc(GL_ONE,GL_ONE);
    glColor4f(.2F,.2F,.2F,0);material=Snapshot();
    Check(cue::CaptureGeometry(mesh,nullptr),"RGB additive source does not depend on alpha");Same(material,Snapshot());
    mesh(nullptr);Check(cue::AfterOwnedDraw(),"finish RGB additive mesh");
    Check(cue::CompositeMask(s,{}),"RGB additive composite");
    Check(Pixel(189,240)>0,"RGB additive alpha-zero material retains visible silhouette");
    glDepthMask(GL_TRUE);glDisable(GL_BLEND);
    GLuint texture=0;glGenTextures(1,&texture);glBindTexture(GL_TEXTURE_2D,texture);
    const GLubyte texels[]{255,255,255,0,255,255,255,255};
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,2,1,0,GL_RGBA,GL_UNSIGNED_BYTE,texels);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    glEnable(GL_TEXTURE_2D);glEnableClientState(GL_TEXTURE_COORD_ARRAY);
    glTexCoordPointer(2,GL_FLOAT,0,texcoords);glEnable(GL_ALPHA_TEST);glAlphaFunc(GL_GREATER,.25F);
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"begin textured alpha cutout");
    glDepthMask(GL_FALSE);glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
    glColor4f(1,1,1,.5F);material=Snapshot();
    Check(cue::CaptureGeometry(mesh,nullptr),"capture original alpha-test texture");Same(material,Snapshot());
    mesh(nullptr);const auto native_pixel=Pixel(400,240);
    Check(cue::AfterOwnedDraw(),"finish textured alpha cutout");
    Check(cue::CompositeMask(s,{}),"textured alpha cutout composite");
    Check(Pixel(230,240)==0,"native texture alpha hole is preserved");
    Check(Pixel(400,240)>native_pixel,"visible textured alpha coverage glows");
    glDepthMask(GL_TRUE);glDisable(GL_BLEND);glDisable(GL_ALPHA_TEST);glDisable(GL_TEXTURE_2D);
    glDisableClientState(GL_TEXTURE_COORD_ARRAY);glDisableClientState(GL_VERTEX_ARRAY);glDeleteTextures(1,&texture);
    glEnableClientState(GL_VERTEX_ARRAY);glVertexPointer(3,GL_FLOAT,0,vertices);
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"begin native depth prepass");
    glColorMask(GL_FALSE,GL_FALSE,GL_FALSE,GL_FALSE);
    Check(cue::CaptureGeometry(mesh,nullptr),"capture color-disabled native depth prepass");
    mesh(nullptr);Check(cue::AfterOwnedDraw(),"finish native depth prepass");
    glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);glDepthMask(GL_FALSE);glDepthFunc(GL_EQUAL);
    Check(cue::BeforeOwnedDraw(),"begin native equal-depth material pass");
    Check(cue::CaptureGeometry(mesh,nullptr),"capture native equal-depth material pass");
    glColor4f(0,0,0,1);mesh(nullptr);Check(cue::AfterOwnedDraw(),"finish equal-depth material pass");
    Check(cue::CompositeMask(s,{}),"depth-prepass character composite");
    Check(Pixel(230,240)>0,"depth prepass plus equal color pass retains character coverage");
    glDepthMask(GL_TRUE);glDepthFunc(GL_LESS);glDisableClientState(GL_VERTEX_ARRAY);
    // Whole-character union stays correct when raw and legacy nodes interleave.
    const GLfloat left_vertices[]{-.8F,-.5F,0,-.2F,-.5F,0,-.2F,.5F,0,-.8F,.5F,0};
    glEnableClientState(GL_VERTEX_ARRAY);glVertexPointer(3,GL_FLOAT,0,left_vertices);
    glColor4f(0,0,0,1);
    for(bool raw_first:{false,true}){
        glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);Check(cue::BeginMask(),"mixed mask begin");
        for(int part=0;part<2;++part){
            Check(cue::BeforeOwnedDraw(),"mixed owned begin");
            if((part==0)==raw_first){Check(cue::CaptureGeometry(mesh,nullptr),"mixed raw");mesh(nullptr);}
            else{Check(cue::BeforeLegacyGeometry(),"mixed legacy");Rect(.2F,.8F,-.5F,.5F,0);}
            Check(cue::AfterOwnedDraw(),"mixed owned end");
        }
        Check(cue::CompositeMask(s,{}),"mixed whole-character composite");
        Check(Pixel(160,240)>0 && Pixel(480,240)>0,"both native submission paths remain in silhouette");
        Check(Pixel(320,240)==0,"empty space between character pieces remains empty");
    }
    glDisableClientState(GL_VERTEX_ARRAY);
    Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"begin stencil safety case");
    glDepthMask(GL_FALSE);glEnable(GL_STENCIL_TEST);material=Snapshot();
    Check(!cue::CaptureGeometry(mesh,nullptr),"active native stencil is not replayed");Same(material,Snapshot());
    Check(glIsEnabled(GL_STENCIL_TEST)==GL_TRUE,"stencil enable remains native");
    glDisable(GL_STENCIL_TEST);cue::DiscardMask();
    using Queries=void(APIENTRY*)(GLsizei,GLuint*);
    using DeleteQueries=void(APIENTRY*)(GLsizei,const GLuint*);
    using BeginQuery=void(APIENTRY*)(GLenum,GLuint);
    using EndQuery=void(APIENTRY*)(GLenum);
    using QueryResult=void(APIENTRY*)(GLuint,GLenum,GLuint*);
    auto gen_query=reinterpret_cast<Queries>(wglGetProcAddress("glGenQueries"));
    auto delete_query=reinterpret_cast<DeleteQueries>(wglGetProcAddress("glDeleteQueries"));
    auto begin_query=reinterpret_cast<BeginQuery>(wglGetProcAddress("glBeginQuery"));
    auto end_query=reinterpret_cast<EndQuery>(wglGetProcAddress("glEndQuery"));
    auto query_result=reinterpret_cast<QueryResult>(wglGetProcAddress("glGetQueryObjectuiv"));
    Check(gen_query && delete_query && begin_query && end_query && query_result,"native query test APIs");
    if(gen_query && delete_query && begin_query && end_query && query_result){
        GLuint query=0,result=1;gen_query(1,&query);
        Check(cue::BeginMask() && cue::BeforeOwnedDraw(),"begin query safety case");
        begin_query(0x8914,query);material=Snapshot();
        Check(!cue::CaptureGeometry(mesh,nullptr),"active native query is not replayed");Same(material,Snapshot());
        end_query(0x8914);query_result(query,0x8866,&result);
        Check(result==0,"capture cannot add native query samples");delete_query(1,&query);cue::DiscardMask();
    }
    glDepthMask(GL_TRUE);
    cue::ReleaseMask();Check(glGetError()==GL_NO_ERROR,"no GL errors after cleanup");
    Check(cue::AllocatedMaskBytes()==0,"cleanup releases tracked mask storage");
    Check(cue::BeginMask(),"resources recreate after cleanup");
    Check(cue::AllocatedMaskBytes()==640ULL*480*8,"recreation starts without legacy allocations");cue::ReleaseMask();
    if(argc==2 && std::strcmp(argv[1],"--cost")==0){
        glEnableClientState(GL_VERTEX_ARRAY);glVertexPointer(3,GL_FLOAT,0,vertices);
        for(int width:{640,1920}){
            const int height=width==640?480:1080;
            RECT rect{0,0,width,height};AdjustWindowRect(&rect,WS_OVERLAPPEDWINDOW,FALSE);
            SetWindowPos(window,nullptr,0,0,rect.right-rect.left,rect.bottom-rect.top,SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE);
            glViewport(0,0,width,height);glFinish();
            const auto frame=[&](bool capture){
                glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
                if(capture)Check(cue::BeginMask(),"cost mask begin");
                for(int node=0;node<46;++node){
                    if(capture){
                        Check(cue::BeforeOwnedDraw(),"cost owned begin");
                        Check(cue::CaptureGeometry(mesh,nullptr),"cost mesh capture");
                    }
                    mesh(nullptr);
                    if(capture)Check(cue::AfterOwnedDraw(),"cost owned end");
                }
                if(capture)Check(cue::CompositeMask(s,{}),"cost composite");
                glFinish();
            };
            const auto timed=[&](bool capture){
                const auto start=std::chrono::steady_clock::now();frame(capture);
                return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
            };
            const double cold=timed(true);
            for(int warmup=0;warmup<3;++warmup){frame(false);frame(true);}
            std::array<double,16> native{},enabled{};
            for(std::size_t sample=0;sample<native.size();++sample){
                // Alternate order to reduce systematic warm-cache/order bias.
                if(sample%2){enabled[sample]=timed(true);native[sample]=timed(false);}
                else{native[sample]=timed(false);enabled[sample]=timed(true);}
            }
            std::sort(native.begin(),native.end());std::sort(enabled.begin(),enabled.end());
            const double native_median=(native[7]+native[8])/2,enabled_median=(enabled[7]+enabled[8])/2;
            std::printf("production-mask-cost viewport=%dx%d owned_nodes=46 samples=16 cold_ms=%.3f native_median_ms=%.3f enabled_median_ms=%.3f enabled_min_ms=%.3f enabled_max_ms=%.3f median_difference_ms=%.3f nominal_mib=%.3f (host test context, synthetic mesh, synchronized CPU/GPU frame time; not a live-client budget)\n",
                width,height,cold,native_median,enabled_median,enabled.front(),enabled.back(),enabled_median-native_median,
                static_cast<double>(cue::AllocatedMaskBytes())/(1024*1024));
            cue::ReleaseMask();
        }
        glDisableClientState(GL_VERTEX_ARRAY);
    }
    wglMakeCurrent(nullptr,nullptr);wglDeleteContext(context);ReleaseDC(window,dc);DestroyWindow(window);
    return failures ? 1:0;
}
