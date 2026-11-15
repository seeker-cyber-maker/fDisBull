/* Authored fDisBull Win16 test fixture. No game assets or external data. */
#include <windows.h>

/* Initialized bytes make the counter's NE data-segment offset discoverable. */
volatile unsigned char oracle_state[] = {
    0x46, 0x44, 0x42, 0x57, 0x31, 7, 0x53, 0x54, 0x41, 0x54, 0x45
};

/* Three harmless, distinctive instructions; the profile locates their bytes. */
static void checkpoint(void) {
    _asm {
        mov ax, 0x1357
        mov ax, 0x2468
        mov ax, 0x369a
    }
}

static LONG FAR PASCAL handler(HWND window, UINT message, WPARAM w, LPARAM l) {
    if (message == WM_KEYUP && w == VK_RIGHT) {
        oracle_state[5]++;
        InvalidateRect(window, NULL, TRUE);
        UpdateWindow(window);
        checkpoint();
        return 0;
    }
    if (message == WM_PAINT) {
        PAINTSTRUCT ps;
        HDC dc;
        RECT area;
        HBRUSH brush;
        dc = BeginPaint(window, &ps);
        SetRect(&area, 0, 0, 320, 200);
        brush = CreateSolidBrush(RGB(24, 40, 64));
        FillRect(dc, &area, brush);
        DeleteObject(brush);
        SetRect(&area, 32, 48, 192, 112);
        brush = CreateSolidBrush(oracle_state[5] > 7 ? RGB(32, 192, 96) : RGB(224, 160, 32));
        FillRect(dc, &area, brush);
        DeleteObject(brush);
        EndPaint(window, &ps);
        return 0;
    }
    if (message == WM_DESTROY) { PostQuitMessage(0); return 0; }
    return DefWindowProc(window, message, w, l);
}

int PASCAL WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show) {
    WNDCLASS cls = {0};
    HWND window;
    RECT area;
    MSG msg;
    (void)previous; (void)command; (void)show;
    cls.lpfnWndProc = handler;
    cls.hInstance = instance;
    cls.lpszClassName = "fdisbull-win16-oracle";
    cls.hCursor = LoadCursor(NULL, IDC_ARROW);
    if (!RegisterClass(&cls)) return 1;
    SetRect(&area, 0, 0, 320, 200);
    AdjustWindowRect(&area, WS_OVERLAPPEDWINDOW, FALSE);
    window = CreateWindow(cls.lpszClassName, "fDisBull Win16 oracle", WS_OVERLAPPEDWINDOW,
        80, 80, area.right-area.left, area.bottom-area.top, NULL, NULL, instance, NULL);
    if (!window) return 2;
    ShowWindow(window, SW_SHOW);
    UpdateWindow(window);
    checkpoint();
    while (GetMessage(&msg, NULL, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }
    return 0;
}
