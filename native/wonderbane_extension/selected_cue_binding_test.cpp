#include "selected_cue_binding.h"
#include <filesystem>
#include <fstream>
#include <vector>
#include <cstdio>
int wmain(int argc,wchar_t** argv){
    using namespace wonderbane::extension::cue;
    std::array<unsigned char,404> empty{};
    if(ReviewedBinding(nullptr,0,0x400000) || ReviewedBinding(empty.data(),empty.size(),0x400000))return 1;
    if(argc==1){std::puts("Frozen client verification unavailable without an explicit private executable path.");return 77;}
    if(argc!=2)return 2;
    std::ifstream file(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);
    if(!file)return 3;
    const auto length=file.tellg();if(length<0x1149ed8 || length>0x4000000)return 4;
    std::vector<unsigned char> image(static_cast<std::size_t>(length));
    file.seekg(0);file.read(reinterpret_cast<char*>(image.data()),static_cast<std::streamsize>(image.size()));
    // This exact reviewed PE has matching raw/RVA offsets for the inspected sections.
    if(!file || !ReviewedBinding(image.data(),image.size(),0x400000))return 5;
    struct Span{std::uint32_t rva,size;std::vector<unsigned> reloc;};
    const Span spans[]{ {0x78ae0,404,{7,38,155,223,265,279,367}},
        {0x1cb100,173,{28,64,69,78,91}}, {0x1c8a90,68,{33}}, {0x79c730,205,{10,195}},
        {0x5645b3,66,{1,8,13,20,25,34,41,46,53,61}}, {0x5655c0,33,{25}}, {0x1a07f0,168,{55,138}} };
    for(auto base:{0x100000U,0x10000000U}){
        auto relocated=image;
        for(const auto& span:spans)for(auto offset:span.reloc){
            std::uint32_t value=0;std::memcpy(&value,relocated.data()+span.rva+offset,4);
            value+=base-0x400000U;std::memcpy(relocated.data()+span.rva+offset,&value,4);
        }
        auto method=base+0x26d91U;std::memcpy(relocated.data()+0x1149ed4,&method,4);
        if(!ReviewedBinding(relocated.data(),relocated.size(),base))return 6;
        for(const auto& span:spans)for(unsigned n=0;n<span.size;++n){
            relocated[span.rva+n]^=1;
            bool accepted=ReviewedBinding(relocated.data(),relocated.size(),base);
            relocated[span.rva+n]^=1;if(accepted)return 7;
        }
    }
    std::puts("Actor-to-wrapper ownership: exact code, both relocations, and every-byte drift rejection passed.");
    return 0;
}
