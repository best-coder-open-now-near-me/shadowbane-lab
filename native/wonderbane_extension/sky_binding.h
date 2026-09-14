#pragma once
#include "reviewed_scene_boundary.h"
#include <vector>
namespace wonderbane::extension::sky {
inline bool Hash(const void* bytes,std::size_t size,const char* expected) noexcept {
    if(!bytes||size>0xffffffffU)return false;
    BCRYPT_ALG_HANDLE algorithm=nullptr;BCRYPT_HASH_HANDLE hash=nullptr;
    unsigned char digest[32]{};bool valid=false;
    if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0
        &&BCryptCreateHash(algorithm,&hash,nullptr,0,nullptr,0,0)>=0
        &&BCryptHashData(hash,static_cast<PUCHAR>(const_cast<void*>(bytes)),static_cast<ULONG>(size),0)>=0
        &&BCryptFinishHash(hash,digest,32,0)>=0){
        constexpr char hex[]="0123456789abcdef";valid=true;
        for(unsigned n=0;n<32;++n)valid=valid&&expected[n*2]==hex[digest[n]>>4]&&expected[n*2+1]==hex[digest[n]&15];
    }
    if(hash)BCryptDestroyHash(hash);if(algorithm)BCryptCloseAlgorithmProvider(algorithm,0);return valid;
}
inline bool Code(const std::uint8_t* image,std::size_t size,std::uint32_t base,
    std::uint32_t rva,std::size_t length,const unsigned* reloc,std::size_t count,const char* expected) noexcept {
    if(!image||!base||rva>size||length>size-rva||length>2421)return false;
    std::array<std::uint8_t,2421> copy{};std::memcpy(copy.data(),image+rva,length);
    for(std::size_t n=0;n<count;++n){if(reloc[n]+4>length)return false;
        std::uint32_t value=0;std::memcpy(&value,copy.data()+reloc[n],4);value-=base-0x400000U;
        std::memcpy(copy.data()+reloc[n],&value,4);}
    return Hash(copy.data(),length,expected);
}
inline bool ReviewedBackground(const std::uint8_t* image,std::size_t size,std::uint32_t base) noexcept {
    constexpr unsigned r0[]={0x6,0x76,0x83,0x93,0x9d,0xae,0xb7,0xd3,0xe4,0xf9,0x143,0x153,0x169,0x172,0x1d0,0x22e,0x24f,0x25a,0x293,0x2aa,0x2e2,0x2f3,0x304,0x35a,0x365,0x375,0x406,0x42d,0x47e,0x48c,0x4bb,0x4f9,0x51b,0x527,0x533,0x608,0x634,0x67c,0x6a2,0x6ce,0x712,0x738,0x764,0x78e,0x799,0x79f,0x7b3,0x7c1,0x7d1,0x7e1,0x7f4,0x7fb,0x821,0x82c,0x83e,0x84a,0x855};
    if(!Code(image,size,base,0x51a9e0,2192,r0,57,"1009d840470101181b365bfac672b656e1814618bc0f0ca304805e586ae57290"))return false;
    constexpr unsigned r1[]={0x6,0x2a,0x91,0xab,0xbb,0xc5,0xd6,0xdf,0xfb,0x10c,0x121,0x16b,0x17b,0x191,0x19a,0x1b9,0x1c1,0x1cb,0x1d5,0x1de,0x1ed,0x1f6,0x20d,0x24d,0x2a8,0x2b9,0x2ca,0x308,0x316,0x326,0x3b1,0x3c3,0x408,0x417,0x425,0x48c,0x4ca,0x533,0x571,0x597,0x5c3,0x60b,0x63a,0x666,0x6aa,0x6b9,0x6cb,0x6f4,0x707,0x70e,0x734,0x73f,0x751,0x75d,0x768};
    if(!Code(image,size,base,0x51b4a0,1968,r1,55,"0727e075ba57c7fffe24ab51ce7537f637bb1f2bfc2899ee64956f949f9fea87"))return false;
    constexpr unsigned r2[]={0x26};
    if(!Code(image,size,base,0x5524a0,65,r2,1,"5aa6a17a43fc790fd1aaf7041a6290a1bcdd2be07f9e94f551ce02fdb166d021"))return false;
    constexpr unsigned r3[]={0x42,0x48,0x9e};
    if(!Code(image,size,base,0x4f6010,275,r3,3,"2263926cb08eecc5b30192ed1d8575c8ad719ea75785caa6d115fcd1c6175298"))return false;
    constexpr unsigned r4[]={0xa,0xc3};
    if(!Code(image,size,base,0x79c730,205,r4,2,"9c13da05cd9aa105fb0bd4bc51537cd6b463540e41e7d13bbc028ab0af9b4696"))return false;
    if(size<0x11641e8)return false;
    std::uint32_t shader=0,wrapper=0;std::int32_t ds=0,dw=0;
    std::memcpy(&shader,image+0x1162b40,4);std::memcpy(&wrapper,image+0x11641dc,4);
    std::memcpy(&ds,image+0xa214,4);std::memcpy(&dw,image+0x22328,4);
    return shader==base+0xa213&&image[0xa213]==0xe9&&0xa218+ds==0x4f6010
        &&wrapper==base+0x22327&&image[0x22327]==0xe9&&0x2232c+dw==0x5524a0;
}
}
