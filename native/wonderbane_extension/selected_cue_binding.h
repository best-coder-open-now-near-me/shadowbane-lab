#pragma once
#include <Windows.h>
#include <bcrypt.h>
#include <array>
#include <cstdint>
#include <cstring>

namespace wonderbane::extension::cue {
inline bool CodeHash(const std::uint8_t* image,std::size_t size,std::uint32_t base,
                     std::uint32_t rva,std::size_t length,const unsigned* reloc,std::size_t count,
                     const char* expected) noexcept {
    if(!image || !base || rva>size || length>size-rva || length>404)return false;
    std::array<unsigned char,404> code{};std::memcpy(code.data(),image+rva,length);
    for(std::size_t n=0;n<count;++n){
        if(reloc[n]+4>length)return false;
        std::uint32_t v=0;std::memcpy(&v,code.data()+reloc[n],4);v-=base-0x400000U;
        std::memcpy(code.data()+reloc[n],&v,4);
    }
    BCRYPT_ALG_HANDLE algorithm=nullptr;BCRYPT_HASH_HANDLE hash=nullptr;
    std::array<unsigned char,32> digest{};bool ok=false;
    if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0
        && BCryptCreateHash(algorithm,&hash,nullptr,0,nullptr,0,0)>=0
        && BCryptHashData(hash,code.data(),static_cast<ULONG>(length),0)>=0
        && BCryptFinishHash(hash,digest.data(),32,0)>=0){
        constexpr char hex[]="0123456789abcdef";ok=true;
        for(std::size_t n=0;n<32;++n)ok=ok && expected[n*2]==hex[digest[n]>>4] && expected[n*2+1]==hex[digest[n]&15];
    }
    if(hash)BCryptDestroyHash(hash);if(algorithm)BCryptCloseAlgorithmProvider(algorithm,0);return ok;
}
inline bool ReviewedBinding(const std::uint8_t* image,std::size_t size,std::uint32_t base) noexcept {
    constexpr unsigned actor[]{7,38,155,223,265,279,367},queue[]{28,64,69,78,91};
    constexpr unsigned wrapper[]{33},drain[]{10,195};
    if(!CodeHash(image,size,base,0x78ae0,404,actor,7,"af75513bbb6f6f7866df0976fb8e4f8d8cd8affb50c60c363b074213a18cc3df")
        || !CodeHash(image,size,base,0x1cb100,173,queue,5,"2fc3a0a6b270f8b07740e96c1c3a2b367dc206e9fb2116934a0a4f75a203891a")
        || !CodeHash(image,size,base,0x1c8a90,68,wrapper,1,"6b7726e9f2da88bcc37eb0e9e2a9f64321518a68290d79d217f0f58ec97f47a5")
        || !CodeHash(image,size,base,0x79c730,205,drain,2,"9c13da05cd9aa105fb0bd4bc51537cd6b463540e41e7d13bbc028ab0af9b4696"))return false;
    if(size<0x1149ed8)return false;
    std::uint32_t method=0;std::memcpy(&method,image+0x1149ed4,4);
    std::int32_t displacement=0;std::memcpy(&displacement,image+0x26d92,4);
    return method==base+0x26d91 && image[0x26d91]==0xE9
        && 0x26d96+displacement==0x1c8a90;
}
}
