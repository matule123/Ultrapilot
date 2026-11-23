// Diagnostic candidate only. Pin the exact file before touching Prism objects.
#pragma once
#include <Windows.h>
#include <wincrypt.h>
#include <cstring>
#include <cstdint>
#include <cstddef>
#pragma comment(lib,"advapi32.lib")

namespace up161 {
inline bool image_matches() {
    wchar_t path[32768]{};
    if(!GetModuleFileNameW(nullptr,path,32768))return false;
    HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE)return false;
    HCRYPTPROV provider=0;HCRYPTHASH hash=0;bool ok=false;
    if(CryptAcquireContextW(&provider,nullptr,nullptr,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)
       &&CryptCreateHash(provider,CALG_SHA_256,0,0,&hash)) {
        unsigned char block[65536];DWORD count=0;bool complete=true;
        for(;;) {
            if(!ReadFile(file,block,sizeof(block),&count,nullptr)){complete=false;break;}
            if(!count)break;
            if(!CryptHashData(hash,block,count,0)){complete=false;break;}
        }
        unsigned char actual[32]{};DWORD length=sizeof(actual);
        constexpr unsigned char expected[]={0xb7,0x0c,0x23,0x57,0xcc,0x56,0xeb,0x58,
            0x34,0xee,0x47,0xfe,0xa3,0xc6,0x0b,0x2f,0x2d,0x45,0x91,0x38,0x3f,0xf2,0xac,0x47,
            0x9c,0xfd,0x3c,0xd2,0x54,0x30,0x1b,0x8c};
        ok=complete&&CryptGetHashParam(hash,HP_HASHVAL,actual,&length,0)
            &&length==sizeof(expected)&&std::memcmp(actual,expected,sizeof(expected))==0;
    }
    if(hash)CryptDestroyHash(hash);if(provider)CryptReleaseContext(provider,0);CloseHandle(file);return ok;
}
inline uintptr_t base(){return reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));}
inline bool readable(const void* value,size_t bytes) {
    uintptr_t at=reinterpret_cast<uintptr_t>(value);
    if(!at||bytes==0||at+bytes<at)return false;
    MEMORY_BASIC_INFORMATION page{};
    if(!VirtualQuery(value,&page,sizeof(page))||page.State!=MEM_COMMIT
        ||page.Protect&(PAGE_GUARD|PAGE_NOACCESS))return false;
    return at+bytes<=reinterpret_cast<uintptr_t>(page.BaseAddress)+page.RegionSize;
}
template<class Array> bool bounded(const Array& array,uint64_t max) {
    if(array.size>array.capacity||array.size>max)return false;
    return array.size==0 || readable(array.value,size_t(array.size)*sizeof(*array.value));
}
}
