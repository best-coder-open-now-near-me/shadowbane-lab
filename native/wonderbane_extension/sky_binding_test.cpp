#include "sky_binding.h"
#include <filesystem>
#include <fstream>
#include <vector>
#include <cstdio>
int wmain(int argc,wchar_t** argv){
    using namespace wonderbane::extension::sky;
    std::array<unsigned char,404> empty{};
    if(ReviewedBackground(nullptr,0,0x400000) || ReviewedBackground(empty.data(),empty.size(),0x400000))return 1;
    if(argc==1){std::puts("Frozen client verification unavailable without an explicit private executable path.");return 77;}
    if(argc!=2)return 2;
    std::ifstream file(std::filesystem::path(argv[1]),std::ios::binary|std::ios::ate);
    if(!file)return 3;
    const auto length=file.tellg();if(length<0x11641e8 || length>0x4000000)return 4;
    std::vector<unsigned char> image(static_cast<std::size_t>(length));
    file.seekg(0);file.read(reinterpret_cast<char*>(image.data()),static_cast<std::streamsize>(image.size()));
    // This exact reviewed PE has matching raw/RVA offsets for the inspected sections.
    if(!file || !ReviewedBackground(image.data(),image.size(),0x400000))return 5;
    struct Span{std::uint32_t rva,size;std::vector<unsigned> reloc;};
    const Span spans[]={{0x51a9e0,2192,{0x6,0x76,0x83,0x93,0x9d,0xae,0xb7,0xd3,0xe4,0xf9,0x143,0x153,0x169,0x172,0x1d0,0x22e,0x24f,0x25a,0x293,0x2aa,0x2e2,0x2f3,0x304,0x35a,0x365,0x375,0x406,0x42d,0x47e,0x48c,0x4bb,0x4f9,0x51b,0x527,0x533,0x608,0x634,0x67c,0x6a2,0x6ce,0x712,0x738,0x764,0x78e,0x799,0x79f,0x7b3,0x7c1,0x7d1,0x7e1,0x7f4,0x7fb,0x821,0x82c,0x83e,0x84a,0x855}},{0x51b4a0,1968,{0x6,0x2a,0x91,0xab,0xbb,0xc5,0xd6,0xdf,0xfb,0x10c,0x121,0x16b,0x17b,0x191,0x19a,0x1b9,0x1c1,0x1cb,0x1d5,0x1de,0x1ed,0x1f6,0x20d,0x24d,0x2a8,0x2b9,0x2ca,0x308,0x316,0x326,0x3b1,0x3c3,0x408,0x417,0x425,0x48c,0x4ca,0x533,0x571,0x597,0x5c3,0x60b,0x63a,0x666,0x6aa,0x6b9,0x6cb,0x6f4,0x707,0x70e,0x734,0x73f,0x751,0x75d,0x768}},{0x5524a0,65,{0x26}},{0x4f6010,275,{0x42,0x48,0x9e}},{0x79c730,205,{0xa,0xc3}}};
    for(auto base:{0x100000U,0x10000000U}){
        auto relocated=image;
        for(const auto& span:spans)for(auto offset:span.reloc){
            std::uint32_t value=0;std::memcpy(&value,relocated.data()+span.rva+offset,4);
            value+=base-0x400000U;std::memcpy(relocated.data()+span.rva+offset,&value,4);
        }
        auto method=base+0xa213U;std::memcpy(relocated.data()+0x1162b40,&method,4);
        method=base+0x22327U;std::memcpy(relocated.data()+0x11641dc,&method,4);
        if(!ReviewedBackground(relocated.data(),relocated.size(),base))return 6;
        for(const auto& span:spans)for(unsigned n=0;n<span.size;++n){
            relocated[span.rva+n]^=1;
            bool accepted=ReviewedBackground(relocated.data(),relocated.size(),base);
            relocated[span.rva+n]^=1;if(accepted)return 7;
        }
    }
    std::puts("Background camera and native sky ownership: exact code, both relocations, and every-byte drift rejection passed.");
    return 0;
}
