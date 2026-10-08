#include "status.h"
#include <tlhelp32.h>
#include <shellapi.h>
#include <iostream>
#include <cstring>
namespace sw=steam_wasd;
struct Handle {
    HANDLE value{};
    explicit Handle(HANDLE v=nullptr):value(v){}
    ~Handle(){if(value && value!=INVALID_HANDLE_VALUE) CloseHandle(value);}
    Handle(const Handle&)=delete;
    explicit operator bool() const { return value && value!=INVALID_HANDLE_VALUE; }
};
std::vector<MODULEENTRY32W> modules(DWORD pid) {
    Handle snapshot(CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid));
    std::vector<MODULEENTRY32W> result;
    MODULEENTRY32W entry{}; entry.dwSize=sizeof(entry);
    if(snapshot && Module32FirstW(snapshot.value,&entry)) do { result.push_back(entry); } while(Module32NextW(snapshot.value,&entry));
    return result;
}
std::vector<DWORD> clients() {
    Handle snapshot(CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0));
    PROCESSENTRY32W entry{}; entry.dwSize=sizeof(entry); std::vector<DWORD> pids;
    if(snapshot && Process32FirstW(snapshot.value,&entry)) do {
        if(!_wcsicmp(entry.szExeFile,sw::profile::executable)) pids.push_back(entry.th32ProcessID);
    } while(Process32NextW(snapshot.value,&entry));
    return pids;
}
bool snapshot(DWORD pid,sw::Shared& out) {
    Handle mapping(OpenFileMappingW(FILE_MAP_READ,FALSE,sw::mapping_name(pid).c_str()));
    if(!mapping) return false;
    auto* view=static_cast<sw::Shared*>(MapViewOfFile(mapping.value,FILE_MAP_READ,0,0,sizeof(sw::Shared)));
    if(!view) return false;
    bool ok=false;
    for(int i=0;i<100;++i) {
        const LONG before=view->sequence; MemoryBarrier();
        if(!(before&1)) {
            std::memcpy(&out,view,sizeof(out)); MemoryBarrier();
            if(view->sequence==before) { ok=true; break; }
        }
        Sleep(1);
    }
    UnmapViewOfFile(view);
    Handle process(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid));
    return ok && process && out.version==sw::schema && out.pid==pid && out.creation==sw::creation_time(process.value);
}
bool matching_package(const sw::Shared& s) {
    wchar_t path[32768]{};
    if(!GetModuleFileNameW(nullptr,path,32768)) return false;
    auto dll=std::filesystem::path(path).parent_path()/L"steam_wasd.dll";
    const auto digest=sw::hash(sw::read_file(dll));
    return digest.size()==64 && s.dll_hash[64]==0 && digest==s.dll_hash;
}
void print(const sw::Shared& s) {
    std::cout<<"pid="<<s.pid<<" creation="<<s.creation<<" hooked="<<s.hooked<<" enabled="<<s.enabled<<" fault="<<s.fault
        <<" gate="<<s.gate<<" keys="<<s.keys<<" moving="<<s.moving<<" state="<<s.state<<" frames="<<s.frames
        <<" moves="<<s.moves<<" stops="<<s.stops<<" messages="<<s.messages<<" scenes="<<s.scene_changes
        <<" dll_sha256="<<s.dll_hash<<" position="<<s.x<<","<<s.y<<","<<s.z<<" yaw="<<s.yaw<<" age_ms="<<(GetTickCount64()-s.tick)<<"\n";
}
struct WindowSearch {DWORD pid; HWND window{};};
BOOL CALLBACK find_window(HWND hwnd,LPARAM value) {
    auto* search=reinterpret_cast<WindowSearch*>(value); DWORD pid{}; GetWindowThreadProcessId(hwnd,&pid);
    if(pid==search->pid && IsWindowVisible(hwnd) && !GetWindow(hwnd,GW_OWNER)) { search->window=hwnd; return FALSE; }
    return TRUE;
}
bool set_enabled(DWORD pid,bool enabled) {
    sw::Shared state{}; if(!snapshot(pid,state) || !state.hooked || state.fault || (enabled && !matching_package(state))) return false;
    WindowSearch window{pid}; EnumWindows(find_window,reinterpret_cast<LPARAM>(&window));
    if(!window.window || !PostMessageW(window.window,RegisterWindowMessageW(sw::command_name),enabled ? 1:0,0)) return false;
    for(int i=0;i<50;++i) {
        Sleep(100);
        if(snapshot(pid,state) && state.enabled==DWORD(enabled) && !state.fault) {print(state); return true;}
    }
    return false;
}
bool remote_call(HANDLE process,void* function,void* argument,DWORD& code) {
    Handle thread(CreateRemoteThread(process,nullptr,0,reinterpret_cast<LPTHREAD_START_ROUTINE>(function),argument,0,nullptr));
    if(!thread) { std::cerr<<"Remote call creation failed: "<<GetLastError()<<"\n"; return false; }
    if(WaitForSingleObject(thread.value,15000)!=WAIT_OBJECT_0) {
        std::cerr<<"Remote call has not completed; no retry or unload was attempted. Restart the game before retrying.\n"; return false;
    }
    return GetExitCodeThread(thread.value,&code)!=FALSE;
}
bool attach(DWORD pid) {
    sw::Shared state{};
    if(snapshot(pid,state)) { print(state); return state.hooked && !state.fault && matching_package(state); }
    Handle process(OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ|PROCESS_VM_WRITE|PROCESS_VM_OPERATION|PROCESS_CREATE_THREAD|SYNCHRONIZE,FALSE,pid));
    if(!process) {std::cerr<<"OpenProcess failed: "<<GetLastError()<<"\n";return false;}
    const auto list=modules(pid);
    if(list.empty() || _wcsicmp(list.front().szModule,sw::profile::executable)) return false;
    auto file=sw::read_file(list.front().szExePath);
    if(!sw::verified_file(file)) {std::cerr<<"Unsupported Steam executable. Exact build required; no hook installed.\n";return false;}
    const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(file.data());
    const auto* nt=reinterpret_cast<const IMAGE_NT_HEADERS64*>(file.data()+dos->e_lfanew);
    const auto* sections=IMAGE_FIRST_SECTION(nt);
    for(unsigned i=0;i<nt->FileHeader.NumberOfSections;++i) if(sections[i].Characteristics&IMAGE_SCN_MEM_EXECUTE) {
        const auto& s=sections[i]; std::vector<unsigned char> live(s.SizeOfRawData); SIZE_T read{};
        if(!ReadProcessMemory(process.value,list.front().modBaseAddr+s.VirtualAddress,live.data(),live.size(),&read)
            || read!=live.size() || std::memcmp(live.data(),file.data()+s.PointerToRawData,live.size())) {
            std::cerr<<"Loaded executable differs from the supported Steam image.\n"; return false;
        }
    }
    wchar_t own_path[32768]{}; if(!GetModuleFileNameW(nullptr,own_path,32768)) return false;
    auto dll=std::filesystem::canonical(std::filesystem::path(own_path).parent_path()/L"steam_wasd.dll");
    for(const auto& m:list) if(!_wcsicmp(m.szModule,L"steam_wasd.dll")) {
        std::cerr<<"An uninitialized or different WASD DLL is already loaded. Restart the game before retrying.\n";return false;
    }
    HMODULE local=LoadLibraryExW(dll.c_str(),nullptr,DONT_RESOLVE_DLL_REFERENCES);
    if(!local) return false;
    auto initializer=GetProcAddress(local,"SteamWasdInitialize");
    auto offset=reinterpret_cast<std::uintptr_t>(initializer)-reinterpret_cast<std::uintptr_t>(local);
    FreeLibrary(local); if(!initializer) return false;
    auto load=GetProcAddress(GetModuleHandleW(L"kernel32.dll"),"LoadLibraryW"); HMODULE containing{};
    if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,reinterpret_cast<LPCWSTR>(load),&containing)) return false;
    wchar_t system_path[32768]{}; GetModuleFileNameW(containing,system_path,32768);
    void* remote_load{};
    for(const auto& m:list) if(!_wcsicmp(m.szExePath,system_path))
        remote_load=m.modBaseAddr+(reinterpret_cast<std::uintptr_t>(load)-reinterpret_cast<std::uintptr_t>(containing));
    if(!remote_load) return false;
    const size_t length=(dll.native().size()+1)*sizeof(wchar_t);
    void* path=VirtualAllocEx(process.value,nullptr,length,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    if(!path) return false;
    SIZE_T written{};
    if(!WriteProcessMemory(process.value,path,dll.c_str(),length,&written) || written!=length) {
        VirtualFreeEx(process.value,path,0,MEM_RELEASE);return false;
    }
    DWORD code{};
    if(!remote_call(process.value,remote_load,path,code)) return false;
    VirtualFreeEx(process.value,path,0,MEM_RELEASE);
    void* remote_init{};
    for(const auto& m:modules(pid)) if(!_wcsicmp(m.szExePath,dll.c_str())) remote_init=m.modBaseAddr+offset;
    if(!remote_init) {std::cerr<<"The game did not load the WASD DLL.\n";return false;}
    if(!remote_call(process.value,remote_init,nullptr,code) || code) {std::cerr<<"Initialization failed, code "<<code<<". Restart the game before retrying.\n";return false;}
    for(int i=0;i<100;++i) { Sleep(100); if(snapshot(pid,state) && state.hooked) {print(state);return !state.fault;} }
    std::cerr<<"Hook installed but game-thread startup was not observed. Leave movement disabled.\n"; return false;
}
int wmain(int argc,wchar_t** argv) {
    try {
        std::wstring mode=argc>1?argv[1]:L"--launch";
        if(mode!=L"--launch" && mode!=L"--attach" && mode!=L"--status" && mode!=L"--enable" && mode!=L"--disable") {
            std::cerr<<"Usage: steam_wasd_launcher [--launch|--attach|--status|--enable|--disable] [PID]\n";return 2;
        }
        DWORD pid{};
        if(argc>2) { wchar_t* end{}; auto parsed=wcstoul(argv[2],&end,10); if(!parsed || *end) return 2; pid=parsed; }
        else {
            auto found=clients();
            if(found.empty() && mode==L"--launch") {
                ShellExecuteW(nullptr,L"open",L"steam://rungameid/4371680",nullptr,nullptr,SW_SHOWNORMAL);
                std::cout<<"Waiting for Steam Shadowbane...\n";
                for(int i=0;i<120 && found.empty();++i) {Sleep(500);found=clients();}
            }
            if(found.size()!=1) {std::cerr<<"Expected one Steam Shadowbane process; specify its PID if several are open.\n";return 2;}
            pid=found.front();
        }
        if(mode==L"--status") {sw::Shared state{};if(!snapshot(pid,state)) return 1;print(state);return state.fault?1:0;}
        if(mode==L"--enable" || mode==L"--disable") return set_enabled(pid,mode==L"--enable")?0:1;
        if(!attach(pid)) return 1;
        if(mode==L"--launch") {
            if(!set_enabled(pid,true)) return 1;
            std::cout<<"WASD enabled. Release all movement keys first. Ctrl+Alt+F10 toggles WASD.\n";
        }
        return 0;
    } catch(const std::exception& e) {std::cerr<<e.what()<<"\n";return 1;}
}
