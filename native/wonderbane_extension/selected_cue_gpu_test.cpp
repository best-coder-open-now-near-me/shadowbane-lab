#include "selected_cue_gpu.h"
#include <gl/GL.h>
#include <array>
#include <cstdio>
#include <cstring>
using namespace wonderbane::extension;
namespace {
int failures=0;
void Check(bool ok,const char* label){if(!ok){std::fprintf(stderr,"%s\n",label);++failures;}}
struct State {
    GLint program{},active{},fbo{},draw{},read{},matrix{},viewport[4]{},textures[3]{};
    GLboolean depth{},blend{},mask{}; GLfloat clear[4]{};
};
using Active=void(APIENTRY*)(GLenum);
State Snapshot(){
    State s{}; auto active=reinterpret_cast<Active>(wglGetProcAddress("glActiveTexture"));
    glGetIntegerv(0x8B8D,&s.program);glGetIntegerv(0x84E0,&s.active);glGetIntegerv(0x8CA6,&s.fbo);
    glGetIntegerv(GL_DRAW_BUFFER,&s.draw);glGetIntegerv(GL_READ_BUFFER,&s.read);
    glGetIntegerv(GL_MATRIX_MODE,&s.matrix);glGetIntegerv(GL_VIEWPORT,s.viewport);
    s.depth=glIsEnabled(GL_DEPTH_TEST);s.blend=glIsEnabled(GL_BLEND);
    glGetBooleanv(GL_DEPTH_WRITEMASK,&s.mask);glGetFloatv(GL_COLOR_CLEAR_VALUE,s.clear);
    for(unsigned n=0;n<3;++n){active(0x84C0+n);glGetIntegerv(GL_TEXTURE_BINDING_2D,&s.textures[n]);}
    active(static_cast<GLenum>(s.active));return s;
}
void Same(const State& a,const State& b){
    Check(a.program==b.program && a.active==b.active && a.fbo==b.fbo
        && a.draw==b.draw && a.read==b.read && a.matrix==b.matrix
        && a.depth==b.depth && a.blend==b.blend && a.mask==b.mask
        && std::memcmp(a.viewport,b.viewport,sizeof(a.viewport))==0
        && std::memcmp(a.textures,b.textures,sizeof(a.textures))==0
        && std::memcmp(a.clear,b.clear,sizeof(a.clear))==0,"graphics state restored");
}
void Rect(float x0,float x1,float y0,float y1,float z){
    glBegin(GL_QUADS);glVertex3f(x0,y0,z);glVertex3f(x1,y0,z);
    glVertex3f(x1,y1,z);glVertex3f(x0,y1,z);glEnd();
}
unsigned Pixel(int x,int y){std::array<unsigned char,4> p{};glReadPixels(x,y,1,1,GL_RGBA,GL_UNSIGNED_BYTE,p.data());return p[0]+p[1]+p[2];}
}
int main(){
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
    auto initial=Snapshot();Check(cue::BeginMask(),"mask resource creation");Same(initial,Snapshot());
    Check(cue::BeforeOwnedDraw(),"before capture");Same(initial,Snapshot());
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
    cue::ReleaseMask();Check(glGetError()==GL_NO_ERROR,"no GL errors after cleanup");
    Check(cue::BeginMask(),"resources recreate after cleanup");cue::ReleaseMask();
    wglMakeCurrent(nullptr,nullptr);wglDeleteContext(context);ReleaseDC(window,dc);DestroyWindow(window);
    return failures ? 1:0;
}
