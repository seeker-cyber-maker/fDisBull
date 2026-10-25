/* Capture/input companion only: it never attaches as a debugger. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wincrypt.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static PROCESS_INFORMATION pi;
static void fatal(const char *op) {printf("{\"error\":\"%s\"}\n",op);fflush(stdout);ExitProcess(2);}
static void b64(const BYTE *data,DWORD n) {
    DWORD size=0;
    if(!CryptBinaryToStringA(data,n,CRYPT_STRING_BASE64|CRYPT_STRING_NOCRLF,NULL,&size)) fatal("encode-size");
    char *encoded=malloc(size);if(!encoded) fatal("allocation");
    if(!CryptBinaryToStringA(data,n,CRYPT_STRING_BASE64|CRYPT_STRING_NOCRLF,encoded,&size)) fatal("encode");
    printf("\"%s\"",encoded);free(encoded);
}
static HWND window;static LONG best_area;
static BOOL CALLBACK findwindow(HWND h,LPARAM unused) {
    DWORD pid;RECT r;(void)unused;GetWindowThreadProcessId(h,&pid);
    if(pid==pi.dwProcessId && IsWindowVisible(h) && GetClientRect(h,&r) && r.right*r.bottom>best_area) {
        best_area=r.right*r.bottom;window=h;
    }return TRUE;
}
static int frame(RECT *r,POINT *p) {
    window=NULL;best_area=0;EnumWindows(findwindow,0);
    if(!window || !GetClientRect(window,r) || r->right<1 || r->bottom<1 || r->right>1920 || r->bottom>1080) return 0;
    p->x=p->y=0;return ClientToScreen(window,p);
}
int main(int argc,char **argv) {
    if(argc!=2) return 64;
    pi.dwProcessId=(DWORD)strtoul(argv[1],NULL,10);
    setvbuf(stdout,NULL,_IONBF,0);
    static char line[4096];
    while(fgets(line,sizeof(line),stdin)) {
        char op[32]={0},arg[32]={0};unsigned long long addr=0;unsigned n=0;
        if(sscanf(line,"%31s",op)!=1) continue;
        if(!strcmp(op,"screenshot")) {
            RECT r;POINT p;
            if(!frame(&r,&p)) {puts("{\"error\":\"no-visible-client-window\"}");continue;}
            HDC screen=GetDC(NULL),dc=CreateCompatibleDC(screen);HBITMAP bitmap=CreateCompatibleBitmap(screen,r.right,r.bottom);
            HGDIOBJ old=SelectObject(dc,bitmap);BITMAPINFO info={0};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
            info.bmiHeader.biWidth=r.right;info.bmiHeader.biHeight=-r.bottom;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
            DWORD size=r.right*r.bottom*4;BYTE *pixels=malloc(size);
            int ok=pixels && BitBlt(dc,0,0,r.right,r.bottom,screen,p.x,p.y,SRCCOPY|CAPTUREBLT);
            SelectObject(dc,old);if(ok) ok=GetDIBits(dc,bitmap,0,r.bottom,pixels,&info,DIB_RGB_COLORS)==r.bottom;
            if(ok) {printf("{\"width\":%ld,\"height\":%ld,\"window\":\"0x%llx\",\"bgra_base64\":",r.right,r.bottom,(unsigned long long)(uintptr_t)window);b64(pixels,size);puts("}");}
            else puts("{\"error\":\"capture-failed\"}");
            free(pixels);DeleteObject(bitmap);DeleteDC(dc);ReleaseDC(NULL,screen);
        } else if(!strcmp(op,"click") && sscanf(line,"%*s %llx %u %31s",&addr,&n,arg)==3) {
            RECT r;POINT p;
            if(!frame(&r,&p) || addr>=(unsigned)r.right || n>=(unsigned)r.bottom) {puts("{\"error\":\"click-outside-client\"}");continue;}
            DWORD down=0,up=0;
            if(!strcmp(arg,"left")) {down=MOUSEEVENTF_LEFTDOWN;up=MOUSEEVENTF_LEFTUP;}
            if(!strcmp(arg,"right")) {down=MOUSEEVENTF_RIGHTDOWN;up=MOUSEEVENTF_RIGHTUP;}
            if(!strcmp(arg,"middle")) {down=MOUSEEVENTF_MIDDLEDOWN;up=MOUSEEVENTF_MIDDLEUP;}
            INPUT input[3];memset(input,0,sizeof(input));for(int i=0;i<3;i++) input[i].type=INPUT_MOUSE;
            input[0].mi.dwFlags=MOUSEEVENTF_MOVE|MOUSEEVENTF_ABSOLUTE;
            input[0].mi.dx=(p.x+(LONG)addr)*65535/(GetSystemMetrics(SM_CXSCREEN)-1);
            input[0].mi.dy=(p.y+(LONG)n)*65535/(GetSystemMetrics(SM_CYSCREEN)-1);
            input[1].mi.dwFlags=down;input[2].mi.dwFlags=up;
            if(!down || SendInput(3,input,sizeof(INPUT))!=3) puts("{\"error\":\"send-input-failed\"}");
            else printf("{\"queued\":true,\"window\":\"0x%llx\"}\n",(unsigned long long)(uintptr_t)window);
        } else puts("{\"error\":\"unsupported-ui-command\"}");
    }
    return 0;
}
