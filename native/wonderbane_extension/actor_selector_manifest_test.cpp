#include "actor_selector_manifest.h"
#include <cstdio>
#include <fstream>
#include <string>
namespace s=wonderbane::extension::actor::selectors;
namespace {
unsigned failures{};
void Check(bool ok,const char* label){if(!ok){++failures;std::fprintf(stderr,"%s\n",label);}}
int Hex(char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:-1;}
std::string Text(const s::Digest& d){constexpr char digits[]="0123456789abcdef";std::string out;for(auto c:d){out+=digits[c>>4];out+=digits[c&15];}return out;}
}
int main(int argc,char** argv){
    if(argc!=2){return 2;}
    std::ifstream stream(argv[1]);std::string text;stream>>text;
    if(text.size()!=2304){return 2;}
    s::Manifest manifest{};auto* bytes=reinterpret_cast<unsigned char*>(&manifest);
    for(std::size_t i=0;i<sizeof(manifest);++i){const int a=Hex(text[i*2]),b=Hex(text[i*2+1]);if(a<0||b<0){return 2;}bytes[i]=static_cast<unsigned char>((a<<4)|b);}
    s::Digest digest{};Check(s::Hash(manifest,digest)&&Text(digest)=="fabb21784a9d719a3c6658149a6c24bdd3277821509b767c8d6b890cfa42ecb4","cross-language complete manifest hash");
    Check(s::GroupDigest(manifest,0,digest)&&Text(digest)=="079d7fb5ad226a5c5e7d41f7926bf63ad19eb9bf1a22a5ab6c634ad0825c3023","cross-language stable semantic group hash");
    auto reordered=manifest;std::swap(reordered.records[1],reordered.records[2]);reordered.records[1].index=1;reordered.records[2].index=2;
    s::Digest before{},after{};Check(s::GroupDigest(manifest,1,before)&&s::GroupDigest(reordered,1,after)&&before==after,"alternative ordering does not reset pending history");
    auto corrupt=manifest;corrupt.records[3].power=1;Check(!s::Valid(corrupt),"unused record rejected");
    corrupt=manifest;corrupt.records[0].template_zero=1;Check(!s::Valid(corrupt),"template namespace rejected");
    corrupt=manifest;corrupt.records[2]=corrupt.records[1];corrupt.records[2].index=2;Check(!s::Valid(corrupt),"duplicate semantic action rejected");
    std::printf("selector manifest: %u failures\n",failures);return failures?1:0;
}
