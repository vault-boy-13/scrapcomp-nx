/* Optional, process-local capture through the installed RenderDoc application API. */
#include "renderdoc_capture.h"
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#ifdef SCRAP_HOST_RENDERDOC
#include <renderdoc_app.h>
static RENDERDOC_API_1_6_0 *api;
static ULONGLONG started;
static unsigned delay_seconds;
static int triggered,reported;
#endif

int scrap_host_renderdoc_install(void)
{
    const char *dll=getenv("RECOMP_RENDERDOC_DLL"),*at=getenv("RECOMP_RENDERDOC_AT");
    if(!dll && !at) return 1;
#ifdef SCRAP_HOST_RENDERDOC
    wchar_t path[32768];char *tail;
    if(!dll || !at || !MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,dll,-1,path,32768)) return 0;
    unsigned long value=strtoul(at,&tail,10);
    if(*tail || !*at || value>300) return 0;
    HMODULE module=LoadLibraryExW(path,NULL,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    pRENDERDOC_GetAPI get=module?(pRENDERDOC_GetAPI)GetProcAddress(module,"RENDERDOC_GetAPI"):NULL;
    if(!get || !get(eRENDERDOC_API_Version_1_6_0,(void **)&api)) {
        fprintf(stderr,"[RENDERDOC] application API unavailable, error=%lu\n",GetLastError());return 0;
    }
    api->SetCaptureKeys(NULL,0);api->MaskOverlayBits(0,0);
    api->SetCaptureFilePathTemplate("gpu-frame");
    delay_seconds=(unsigned)value;started=GetTickCount64();
    fprintf(stderr,"[RENDERDOC] process-local capture armed at %u seconds\n",delay_seconds);
    return 1;
#else
    fprintf(stderr,"[RENDERDOC] requested capture, but application API header was not configured\n");
    return 0;
#endif
}

void scrap_host_renderdoc_presented(int is_3d)
{
#ifdef SCRAP_HOST_RENDERDOC
    if(!api || !is_3d || reported) return;
    if(!triggered && GetTickCount64()-started>=(ULONGLONG)delay_seconds*1000) {
        api->TriggerCapture();triggered=1;
        fprintf(stderr,"[RENDERDOC] next GL frame requested\n");
    }
    if(triggered && api->GetNumCaptures()) {
        uint32_t length=0;
        api->GetCapture(0,NULL,&length,NULL);
        if(length>0 && length<32768) {
            char *path=malloc(length+1);
            if(path) {
                path[length]=0;
                if(api->GetCapture(0,path,&length,NULL)) fprintf(stderr,"[RENDERDOC] captured %s\n",path);
                free(path);
            }
        }
        reported=1;
    }
#else
    (void)is_3d;
#endif
}
