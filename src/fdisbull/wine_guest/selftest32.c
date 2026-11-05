/* Authored I386 GUI program for original-process, keyboard and scene tests. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
__declspec(dllexport) volatile LONG counter=7;
__declspec(dllexport) volatile LONG keys=0;
__declspec(dllexport) volatile LONG clicks=0;
__declspec(dllexport) volatile LONG last_key=0;
__declspec(dllexport) __attribute__((noinline)) void checkpoint(void) {
    __asm__ volatile("nop\n\tnop\n\tnop\n\tnop" ::: "memory");
}
__declspec(dllexport) __attribute__((noinline)) LONG increment(LONG amount) {
    counter+=amount;return counter;
}
static void changed(HWND window) {
    InvalidateRect(window,NULL,TRUE);UpdateWindow(window);checkpoint();
}
static LRESULT CALLBACK handler(HWND window,UINT message,WPARAM w,LPARAM l) {
    if(message==WM_KEYUP) {
        last_key=(LONG)w;keys++;
        if(w==VK_RIGHT || w=='A')increment(1);
        if(w==VK_LEFT)increment(-1);
        changed(window);return 0;
    }
    if(message==WM_LBUTTONUP) {
        if(LOWORD(l)>=32 && LOWORD(l)<192 && HIWORD(l)>=48 && HIWORD(l)<112) {
            clicks++;increment(1);changed(window);
        }return 0;
    }
    if(message==WM_PAINT) {
        PAINTSTRUCT ps;HDC dc=BeginPaint(window,&ps);RECT area={0,0,320,200};
        HBRUSH brush=CreateSolidBrush(RGB(24,40,64));FillRect(dc,&area,brush);DeleteObject(brush);
        area.left=32;area.top=48;area.right=192;area.bottom=112;
        brush=CreateSolidBrush(counter>7?RGB(32,192,96):RGB(224,160,32));
        FillRect(dc,&area,brush);DeleteObject(brush);SetBkMode(dc,TRANSPARENT);
        SetTextColor(dc,RGB(255,255,255));TextOutA(dc,40,64,"Click or press Right",20);
        char text[96];wsprintfA(text,"Counter %ld, keys %ld, clicks %ld",counter,keys,clicks);
        TextOutA(dc,24,144,text,lstrlenA(text));EndPaint(window,&ps);return 0;
    }
    if(message==WM_DESTROY) {PostQuitMessage(0);return 0;}
    return DefWindowProcA(window,message,w,l);
}
int WINAPI WinMain(HINSTANCE instance,HINSTANCE previous,LPSTR command,int show) {
    (void)previous;(void)command;(void)show;
    WNDCLASSA cls={0};cls.lpfnWndProc=handler;cls.hInstance=instance;
    cls.lpszClassName="fdisbull-pe32-oracle";cls.hCursor=LoadCursor(NULL,IDC_ARROW);
    if(!RegisterClassA(&cls))return 1;
    RECT area={0,0,320,200};AdjustWindowRect(&area,WS_OVERLAPPEDWINDOW,FALSE);
    HWND window=CreateWindowA(cls.lpszClassName,"fDisBull PE32 native oracle",WS_OVERLAPPEDWINDOW,
        80,80,area.right-area.left,area.bottom-area.top,NULL,NULL,instance,NULL);
    if(!window)return 2;
    ShowWindow(window,SW_SHOW);UpdateWindow(window);checkpoint();
    MSG msg;while(GetMessageA(&msg,NULL,0,0)>0) {TranslateMessage(&msg);DispatchMessageA(&msg);}
    return 0;
}
