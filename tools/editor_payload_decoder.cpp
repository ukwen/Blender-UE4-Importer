// External development helper. Link against separately acquired pyooz (GPL-3.0-or-later)
// and BLAKE3 portable C sources; do not bundle their binaries in the addon.
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include <algorithm>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
#include "ooz.h"
#include "blake3.h"
static uint64_t be(const unsigned char* p, int n) { uint64_t v=0; while(n--) v=(v<<8)|*p++; return v; }
static uint32_t crc32(const unsigned char* p, size_t n) {
    uint32_t crc=0xffffffffu;
    while(n--) { crc^=*p++; for(int i=0;i<8;i++) crc=(crc>>1)^((0u-(crc&1u))&0xedb88320u); }
    return ~crc;
}
int main() {
#ifdef _WIN32
    // Windows CRT defaults to text mode; binary compressed bytes must not be translated.
    if (_setmode(_fileno(stdin), _O_BINARY)==-1 || _setmode(_fileno(stdout), _O_BINARY)==-1) return 13;
#endif
    constexpr size_t cap=256*1024*1024;
    std::vector<unsigned char> in; unsigned char tmp[65536]; size_t n;
    while ((n=fread(tmp,1,sizeof(tmp),stdin))) {
        if (n>cap-in.size()) return 2;
        in.insert(in.end(),tmp,tmp+n);
    }
    if (ferror(stdin)||in.size()<64||be(in.data(),4)!=0xb7756362) return 3;
    const auto* p=in.data(); uint64_t raw64=be(p+16,8), compressed=be(p+24,8); size_t count=be(p+12,4);
    if (!raw64||raw64>cap||compressed!=in.size()) return 4;
    size_t raw=static_cast<size_t>(raw64), header_size=64;
    if (p[8]==3) {
        if (count>(in.size()-64)/4) return 6;
        header_size+=4*count;
    }
    if (crc32(p+8,header_size-8)!=be(p+4,4)) return 14;
    std::vector<unsigned char> out(raw+OOZ_SAFE_SPACE);
    if (p[8]==0) {
        if (p[9]||p[10]||p[11]||count!=1||in.size()!=64+raw) return 5;
        memcpy(out.data(),p+64,raw);
    } else if (p[8]==3) {
        if (p[9]!=3||p[10]!=3||p[11]!=18||count!=(raw+262143)/262144||count>(in.size()-64)/4) return 6;
        size_t at=64+4*count, written=0;
        for(size_t i=0;i<count;i++) {
            size_t sz=be(p+64+i*4,4), expected=std::min(size_t(262144),raw-written);
            if (!sz||sz>expected||sz>in.size()-at) return 7;
            if(sz==expected) memcpy(out.data()+written,p+at,sz);
            else {
                // Padding is needed by this experimental decoder. Isolate it in a separate process.
                std::vector<unsigned char> block(sz+64); memcpy(block.data(),p+at,sz);
                if(Kraken_Decompress(block.data(),sz,out.data()+written,expected)!=(int)expected) return 8;
            }
            at+=sz; written+=expected;
        }
        if(at!=in.size()||written!=raw) return 9;
    } else return 10;
    blake3_hasher h; blake3_hasher_init(&h); blake3_hasher_update(&h,out.data(),raw); unsigned char hash[32]; blake3_hasher_finalize(&h,hash,32);
    if(memcmp(hash,p+32,32)) return 11;
    return fwrite(out.data(),1,raw,stdout)==raw && fflush(stdout)==0 ? 0 : 12;
}
