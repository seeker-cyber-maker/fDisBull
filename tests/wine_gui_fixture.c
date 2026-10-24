/* Authored, redistributable PE64 GUI oracle. No game data. */
#include <windows.h>
__declspec(dllexport) volatile LONG counter=7;
__declspec(dllexport) __attribute__((noinline)) void checkpoint(void) {
    __asm__ volatile("nop\n\tnop\n\tnop\n\tnop" ::: "memory");
}
static LRESULT CALLBACK handler(HWND window,UINT message,WPARAM w,LPARAM l) {
    if(message==WM_LBUTTONUP) {
        if(LOWORD(l)>=32 && LOWORD(l)<192 && HIWORD(l)>=48 && HIWORD(l)<112) {
            InterlockedIncrement(&counter);
            InvalidateRect(window,NULL,TRUE);UpdateWindow(window);checkpoint();
        }return 0;
    }
    if(message==WM_PAINT) {
        PAINTSTRUCT ps;HDC dc=BeginPaint(window,&ps);RECT area={0,0,320,200};
        HBRUSH background=CreateSolidBrush(RGB(24,40,64));FillRect(dc,&area,background);DeleteObject(background);
        area=(RECT){32,48,192,112};HBRUSH button=CreateSolidBrush(counter>7?RGB(32,192,96):RGB(224,160,32));
        FillRect(dc,&area,button);DeleteObject(button);SetBkMode(dc,TRANSPARENT);SetTextColor(dc,RGB(255,255,255));
        TextOutA(dc,40,64,"Click: increment",16);char text[64];wsprintfA(text,"Counter = %ld",counter);TextOutA(dc,32,144,text,lstrlenA(text));
        EndPaint(window,&ps);return 0;
    }
    if(message==WM_DESTROY) {PostQuitMessage(0);return 0;}
    return DefWindowProcA(window,message,w,l);
}
int WINAPI WinMain(HINSTANCE instance,HINSTANCE previous,LPSTR command,int show) {
    (void)previous;(void)command;(void)show;
    WNDCLASSA cls={0};cls.lpfnWndProc=handler;cls.hInstance=instance;cls.lpszClassName="fdisbull-oracle";cls.hCursor=LoadCursor(NULL,IDC_ARROW);
    if(!RegisterClassA(&cls)) return 1;
    RECT r={0,0,320,200};AdjustWindowRect(&r,WS_OVERLAPPEDWINDOW,FALSE);
    HWND window=CreateWindowA(cls.lpszClassName,"fDisBull PE64 oracle",WS_OVERLAPPEDWINDOW,80,80,r.right-r.left,r.bottom-r.top,NULL,NULL,instance,NULL);
    if(!window) return 2;
    ShowWindow(window,SW_SHOW);UpdateWindow(window);checkpoint();
    MSG msg;while(GetMessageA(&msg,NULL,0,0)>0) {TranslateMessage(&msg);DispatchMessageA(&msg);}
    return 0;
}
