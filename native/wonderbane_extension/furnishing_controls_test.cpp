#include "furnishing_controls.h"
#include "furnishing_pose.h"
#undef NDEBUG
#include <cassert>
#include <array>
namespace f=wonderbane::extension::furnishing;
namespace {
unsigned downs=0,ups=0,keys=0; WPARAM moved=0;
std::array<unsigned,5> actions{}; bool current=true;
void Action(void*,f::PreviewControls::Action a) noexcept { ++actions[static_cast<unsigned>(a)]; }
bool Current(void*,const f::Selection&) noexcept { return current; }
bool Contains(void*,const f::Selection& s,int x,int y) noexcept { return f::LayoutContains(s,x/2,y/2); }
LRESULT CALLBACK Base(HWND hwnd,UINT m,WPARAM w,LPARAM l) {
    if(m==WM_LBUTTONDOWN) { ++downs; } if(m==WM_LBUTTONUP) { ++ups; }
    if(m==WM_MOUSEMOVE) { moved=w; } if(m==WM_KEYDOWN || m==WM_KEYUP) { ++keys; }
    return DefWindowProcW(hwnd,m,w,l);
}
}
int main() {
    WNDCLASSW cls{}; cls.lpfnWndProc=&Base; cls.hInstance=GetModuleHandleW(nullptr); cls.lpszClassName=L"PreviewControlsFixture";
    assert(RegisterClassW(&cls));
    HWND window=CreateWindowW(cls.lpszClassName,L"",WS_OVERLAPPEDWINDOW,0,0,1000,800,nullptr,nullptr,cls.hInstance,nullptr); assert(window);
    f::PreviewControls controls({nullptr,&Action,&Current,&Contains}); assert(controls.Bind(window));
    f::Selection s{}; s.rectangle={0,0,400,400}; s.dimensions={100,100}; s.offset={50,50}; s.zoom=1; s.layout_scale=1;
    controls.Show(&s,true,L"Preview only");
    // Physical 200,200 maps to native 100,100. Placement never receives this pair.
    SendMessageW(window,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(200,200)); assert(!downs);
    SendMessageW(window,WM_MOUSEMOVE,MK_LBUTTON,MAKELPARAM(202,202)); assert(!(moved&MK_LBUTTON));
    SendMessageW(window,WM_LBUTTONUP,0,MAKELPARAM(200,200)); assert(!ups && actions[4]==1);
    SendMessageW(window,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(800,200));
    SendMessageW(window,WM_LBUTTONUP,0,MAKELPARAM(800,200)); assert(downs==1 && ups==1);
    SendMessageW(window,WM_KEYDOWN,VK_ESCAPE,0); SendMessageW(window,WM_KEYUP,VK_ESCAPE,0); assert(!keys && actions[3]);
    controls.Show(&s,true,L"Preview only");
    SendMessageW(window,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(200,200)); controls.Hide();
    SendMessageW(window,WM_LBUTTONUP,0,MAKELPARAM(200,200)); assert(ups==1);
    controls.Show(&s,false,L"Ready");
    HWND panel=FindWindowExW(window,nullptr,L"WonderBaneFurnishingPreview",nullptr); assert(panel);
    SendMessageW(panel,WM_LBUTTONUP,0,MAKELPARAM(30,20)); assert(!actions[0]);
    SendMessageW(panel,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(30,20));
    SendMessageW(panel,WM_LBUTTONUP,0,MAKELPARAM(30,20)); assert(actions[0]==1);
    // The mode blocks placement immediately, even before the next native update.
    SendMessageW(window,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(200,200)); assert(downs==1);
    current=false; SendMessageW(window,WM_LBUTTONUP,0,MAKELPARAM(200,200));
    SendMessageW(window,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(200,200)); assert(downs==1 && actions[3]>=2);
    SendMessageW(window,WM_LBUTTONUP,0,MAKELPARAM(200,200));
    controls.Retire(); assert(!IsWindow(panel));
    SendMessageW(window,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(200,200)); assert(downs==2);
    DestroyWindow(window);
}
