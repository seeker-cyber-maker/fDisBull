/* Win32 presentation and input for an explicitly supplied memory UIL plan.
 * The window owns only OS services; game transitions remain native blocks. */
#define UNICODE
#define _UNICODE
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <windowsx.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "memory-runtime.h"
#include "memory-desktop.h"

/* Set-1 physical scan codes, including the extended-key bit.  WM_CHAR and the
 * current keyboard layout do not change a declared physical-key binding. */
typedef struct { unsigned scan; const char *name; } FdbWinKey;
static const FdbWinKey fdb_win_keys[] = {
    {0x01,"Escape"},{0x02,"Digit1"},{0x03,"Digit2"},{0x04,"Digit3"},
    {0x05,"Digit4"},{0x06,"Digit5"},{0x07,"Digit6"},{0x08,"Digit7"},
    {0x09,"Digit8"},{0x0a,"Digit9"},{0x0b,"Digit0"},{0x0c,"Minus"},
    {0x0d,"Equal"},{0x0e,"Backspace"},{0x0f,"Tab"},
    {0x10,"KeyQ"},{0x11,"KeyW"},{0x12,"KeyE"},{0x13,"KeyR"},
    {0x14,"KeyT"},{0x15,"KeyY"},{0x16,"KeyU"},{0x17,"KeyI"},
    {0x18,"KeyO"},{0x19,"KeyP"},{0x1a,"BracketLeft"},{0x1b,"BracketRight"},
    {0x1c,"Enter"},{0x1e,"KeyA"},{0x1f,"KeyS"},{0x20,"KeyD"},
    {0x21,"KeyF"},{0x22,"KeyG"},{0x23,"KeyH"},{0x24,"KeyJ"},
    {0x25,"KeyK"},{0x26,"KeyL"},{0x27,"Semicolon"},{0x28,"Quote"},
    {0x29,"Backquote"},{0x2b,"Backslash"},{0x2c,"KeyZ"},{0x2d,"KeyX"},
    {0x2e,"KeyC"},{0x2f,"KeyV"},{0x30,"KeyB"},{0x31,"KeyN"},
    {0x32,"KeyM"},{0x33,"Comma"},{0x34,"Period"},{0x35,"Slash"},
    {0x39,"Space"},{0x3b,"F1"},{0x3c,"F2"},{0x3d,"F3"},{0x3e,"F4"},
    {0x3f,"F5"},{0x40,"F6"},{0x41,"F7"},{0x42,"F8"},{0x43,"F9"},
    {0x44,"F10"},{0x57,"F11"},{0x58,"F12"},
    {0x147,"Home"},{0x148,"ArrowUp"},{0x149,"PageUp"},
    {0x14b,"ArrowLeft"},{0x14d,"ArrowRight"},{0x14f,"End"},
    {0x150,"ArrowDown"},{0x151,"PageDown"},{0x152,"Insert"},{0x153,"Delete"}
};
static const char *fdb_win_key_name(LPARAM parameter) {
    unsigned scan=(unsigned)(((uintptr_t)parameter>>16)&0xffu);
    if (((uintptr_t)parameter>>24)&1u) scan|=0x100u;
    for(size_t i=0;i<sizeof(fdb_win_keys)/sizeof(fdb_win_keys[0]);i++)
        if(fdb_win_keys[i].scan==scan) return fdb_win_keys[i].name;
    return NULL;
}
static unsigned fdb_win_key_scan(const char *name) {
    for(size_t i=0;i<sizeof(fdb_win_keys)/sizeof(fdb_win_keys[0]);i++)
        if(name && strcmp(fdb_win_keys[i].name,name)==0) return fdb_win_keys[i].scan;
    return 0;
}

/* The DIB is independent owned storage, in top-to-bottom BGRA byte order.
 * Selecting and deleting its GDI objects follows the same path for live paint
 * and an offscreen diagnostic capture. */
typedef struct {
    HDC dc;
    HBITMAP bitmap;
    HGDIOBJ previous;
    uint8_t *pixels;
    int width,height;
} FdbWinSurface;
static void fdb_win_surface_dispose(FdbWinSurface *surface) {
    if(surface->dc && surface->previous) SelectObject(surface->dc,surface->previous);
    if(surface->bitmap) DeleteObject(surface->bitmap);
    if(surface->dc) DeleteDC(surface->dc);
    memset(surface,0,sizeof(*surface));
}
static int fdb_win_surface_create(FdbWinSurface *surface,int width,int height) {
    if(width<=0 || height<=0 || width>4096 || height>4096) return 1;
    FdbWinSurface next={0};
    BITMAPINFO info;
    memset(&info,0,sizeof(info));
    info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth=width;info.bmiHeader.biHeight=-height;
    info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
    info.bmiHeader.biCompression=BI_RGB;
    next.dc=CreateCompatibleDC(NULL);
    if(!next.dc) return 1;
    next.bitmap=CreateDIBSection(next.dc,&info,DIB_RGB_COLORS,(void**)&next.pixels,NULL,0);
    if(!next.bitmap || !next.pixels) { fdb_win_surface_dispose(&next);return 1; }
    next.previous=SelectObject(next.dc,next.bitmap);
    if(!next.previous || next.previous==HGDI_ERROR) {
        next.previous=NULL;fdb_win_surface_dispose(&next);return 1;
    }
    next.width=width;next.height=height;
    fdb_win_surface_dispose(surface);*surface=next;return 0;
}
static void fdb_win_surface_set_rgba(FdbWinSurface *surface,const uint8_t *rgba) {
    size_t count=(size_t)surface->width*(size_t)surface->height;
    for(size_t i=0;i<count;i++) {
        surface->pixels[4*i]=rgba[4*i+2];
        surface->pixels[4*i+1]=rgba[4*i+1];
        surface->pixels[4*i+2]=rgba[4*i];
        surface->pixels[4*i+3]=255;
    }
}
static void fdb_win_surface_get_rgba(const FdbWinSurface *surface,uint8_t *rgba) {
    GdiFlush();
    size_t count=(size_t)surface->width*(size_t)surface->height;
    for(size_t i=0;i<count;i++) {
        rgba[4*i]=surface->pixels[4*i+2];
        rgba[4*i+1]=surface->pixels[4*i+1];
        rgba[4*i+2]=surface->pixels[4*i];
        rgba[4*i+3]=255;
    }
}

typedef struct {
    FdbHost host;
    const FdbHostConfig *config;
    HWND window,view,help;
    HWND *selectors;
    HWND selector_labels[16];
    FdbWinSurface surface;
    int diagnostic,controlled,clock_override,result,failed;
    uint32_t controlled_clock,controlled_modifiers;
} FdbWin;
static const wchar_t fdb_window_class[]=L"FdisbullMemoryHost1";
static const wchar_t fdb_view_class[]=L"FdisbullMemoryView1";
static uint32_t fdb_win_clock(const FdbWin *app) {
    if(app->clock_override) return app->controlled_clock;
    return (uint32_t)(((uint64_t)((double)GetTickCount64()/app->config->tick_ms))&65535u);
}
static uint32_t fdb_win_modifiers(const FdbWin *app) {
    if(app->controlled) return app->controlled_modifiers;
    uint32_t flags=0;
    if((GetKeyState(VK_LWIN)|GetKeyState(VK_RWIN))&0x8000) flags|=FDB_MOD_COMMAND;
    if(GetKeyState(VK_CONTROL)&0x8000) flags|=FDB_MOD_CONTROL;
    if(GetKeyState(VK_MENU)&0x8000) flags|=FDB_MOD_OPTION;
    if(GetKeyState(VK_SHIFT)&0x8000) flags|=FDB_MOD_SHIFT;
    if(GetKeyState(VK_CAPITAL)&1) flags|=FDB_MOD_CAPS;
    return flags;
}
static wchar_t *fdb_win_wide(const char *text) {
    if(!text) text="";
    int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,-1,NULL,0);
    if(n<=0 || n>65536) return NULL;
    wchar_t *result=(wchar_t*)malloc((size_t)n*sizeof(wchar_t));
    if(!result) return NULL;
    if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,-1,result,n)) {
        free(result);return NULL;
    }
    return result;
}
static int fdb_win_paint(FdbWin *app,HDC dc) {
    int width=app->host.view_width,height=app->host.view_height;
    if(width<=0 || height<=0 || width>4096 || height>4096) return 1;
    if(app->surface.width!=width || app->surface.height!=height)
        if(fdb_win_surface_create(&app->surface,width,height)) return 1;
    uint8_t *rgba=(uint8_t*)malloc((size_t)width*(size_t)height*4u);
    if(!rgba) return 1;
    int failed=fdb_host_render(&app->host,rgba,(uint32_t)width,(uint32_t)height);
    if(!failed) fdb_win_surface_set_rgba(&app->surface,rgba);
    free(rgba);
    if(failed) return 1;
    return BitBlt(dc,0,0,width,height,app->surface.dc,0,0,SRCCOPY)?0:1;
}
static void fdb_win_changed(FdbWin *app,int result) {
    app->result=result;
    if(app->view) InvalidateRect(app->view,NULL,FALSE);
    if(app->host.closed && app->view && GetCapture()==app->view) ReleaseCapture();
    if(app->host.closed && !app->diagnostic && app->window)
        PostMessageW(app->window,WM_CLOSE,0,0);
}
static void fdb_win_release(FdbWin *app,int focused) {
    if(app->host.closed) return;
    if(app->host.buttons) {
        app->result=fdb_host_focus(&app->host,0,fdb_win_clock(app));
        if(focused && !app->result)
            app->result=fdb_host_focus(&app->host,1,fdb_win_clock(app));
    }
}
static LRESULT CALLBACK fdb_win_view_proc(HWND window,UINT message,WPARAM wparam,LPARAM lparam) {
    FdbWin *app=(FdbWin*)GetWindowLongPtrW(window,GWLP_USERDATA);
    if(message==WM_NCCREATE) {
        CREATESTRUCTW *create=(CREATESTRUCTW*)lparam;
        app=(FdbWin*)create->lpCreateParams;
        SetWindowLongPtrW(window,GWLP_USERDATA,(LONG_PTR)app);
    }
    if(!app) return DefWindowProcW(window,message,wparam,lparam);
    switch(message) {
    case WM_ERASEBKGND:return 1;
    case WM_PAINT: {
        PAINTSTRUCT paint;HDC dc=BeginPaint(window,&paint);
        if(fdb_win_paint(app,dc)) app->failed=1;
        EndPaint(window,&paint);return 0;
    }
    case WM_PRINTCLIENT:
        app->result=fdb_win_paint(app,(HDC)wparam);return 0;
    case WM_SIZE: {
        RECT area;
        if(GetClientRect(window,&area) && area.right>0 && area.bottom>0)
            fdb_win_changed(app,fdb_host_resize(&app->host,area.right,area.bottom));
        return 0;
    }
    case WM_SETFOCUS:
        if(!app->host.closed) fdb_win_changed(app,fdb_host_focus(&app->host,1,fdb_win_clock(app)));
        return 0;
    case WM_KILLFOCUS:
        if(!app->host.closed) fdb_win_changed(app,fdb_host_focus(&app->host,0,fdb_win_clock(app)));
        if(GetCapture()==window) ReleaseCapture();
        return 0;
    case WM_CAPTURECHANGED:
        if(GetCapture()!=window) fdb_win_release(app,GetFocus()==window);
        return 0;
    case WM_KEYDOWN:case WM_SYSKEYDOWN: {
        const char *name=fdb_win_key_name(lparam);
        app->host.accepted=0;app->host.committed=0;app->result=0;
        if(!name) return message==WM_SYSKEYDOWN?DefWindowProcW(window,message,wparam,lparam):0;
        uint32_t modifiers=fdb_win_modifiers(app);
        for(uint32_t i=0;i<app->config->key_count;i++)
            if(strcmp(name,app->config->keys[i].name)==0) {
                fdb_win_changed(app,fdb_host_key(&app->host,i,modifiers,
                                                GetFocus()==window,fdb_win_clock(app)));
                if(modifiers&(FDB_MOD_COMMAND|FDB_MOD_CONTROL|FDB_MOD_OPTION))
                    return DefWindowProcW(window,message,wparam,lparam);
                return 0;
            }
        return message==WM_SYSKEYDOWN?DefWindowProcW(window,message,wparam,lparam):0;
    }
    case WM_LBUTTONDOWN:case WM_RBUTTONDOWN:case WM_MBUTTONDOWN:
    case WM_LBUTTONUP:case WM_RBUTTONUP:case WM_MBUTTONUP:case WM_MOUSEMOVE: {
        uint32_t phase=app->host.buttons?FDB_POINTER_DRAG:FDB_POINTER_MOVE,button=0;
        if(message==WM_LBUTTONDOWN || message==WM_RBUTTONDOWN || message==WM_MBUTTONDOWN)
            phase=FDB_POINTER_DOWN;
        if(message==WM_LBUTTONUP || message==WM_RBUTTONUP || message==WM_MBUTTONUP)
            phase=FDB_POINTER_UP;
        if(message==WM_RBUTTONDOWN || message==WM_RBUTTONUP) button=1;
        if(message==WM_MBUTTONDOWN || message==WM_MBUTTONUP) button=2;
        if(phase==FDB_POINTER_DOWN) SetFocus(window);
        fdb_win_changed(app,fdb_host_pointer(&app->host,phase,button,
                     GET_X_LPARAM(lparam),GET_Y_LPARAM(lparam),fdb_win_clock(app)));
        if(phase==FDB_POINTER_DOWN && !app->host.closed && app->host.accepted && app->host.buttons && GetCapture()!=window)
            SetCapture(window);
        if(phase==FDB_POINTER_UP && !app->host.buttons && GetCapture()==window)
            ReleaseCapture();
        return 0;
    }
    default:return DefWindowProcW(window,message,wparam,lparam);
    }
}
static int fdb_win_controls_height(const FdbWin *app) {
    return 70+(int)app->config->region_count*32;
}
static void fdb_win_layout(FdbWin *app,int width,int height) {
    int controls_height=fdb_win_controls_height(app);
    if(width<=32 || height<=controls_height+16) return;
    int game_width=width-32;
    int game_height=height-controls_height-16;
    if(game_width>4096) game_width=4096;
    if(game_height>4096) game_height=4096;
    if(app->help) MoveWindow(app->help,16,8,game_width,46,TRUE);
    for(uint32_t slot=0;slot<app->config->region_count;slot++) {
        MoveWindow(app->selector_labels[slot],16,61+(int)slot*32,160,24,TRUE);
        MoveWindow(app->selectors[slot],186,58+(int)slot*32,game_width-170,200,TRUE);
    }
    if(app->view) MoveWindow(app->view,16,controls_height,game_width,game_height,TRUE);
}
static LRESULT CALLBACK fdb_win_window_proc(HWND window,UINT message,WPARAM wparam,LPARAM lparam) {
    FdbWin *app=(FdbWin*)GetWindowLongPtrW(window,GWLP_USERDATA);
    if(message==WM_NCCREATE) {
        app=(FdbWin*)((CREATESTRUCTW*)lparam)->lpCreateParams;
        SetWindowLongPtrW(window,GWLP_USERDATA,(LONG_PTR)app);
    }
    if(!app) return DefWindowProcW(window,message,wparam,lparam);
    switch(message) {
    case WM_SIZE: {
        if(wparam==SIZE_MINIMIZED) return 0;
        RECT area;if(GetClientRect(window,&area)) fdb_win_layout(app,area.right,area.bottom);
        return 0;
    }
    case WM_TIMER:
        if(wparam==1 && !app->host.closed)
            fdb_win_changed(app,fdb_host_tick(&app->host,fdb_win_clock(app)));
        return 0;
    case WM_COMMAND: {
        unsigned id=LOWORD(wparam);
        if(HIWORD(wparam)==CBN_SELCHANGE && id>=1000 && id-1000<app->config->region_count) {
            uint32_t slot=id-1000;
            HWND combo=app->selectors[slot];
            LRESULT selected=SendMessageW(combo,CB_GETCURSEL,0,0);
            int before=fdb_selected_region(slot);
            fdb_win_changed(app,selected<0?1:fdb_host_select(&app->host,slot,(uint32_t)selected));
            if(app->result && before>=0) SendMessageW(combo,CB_SETCURSEL,(WPARAM)before,0);
            int selected_result=app->result,accepted=app->host.accepted,committed=app->host.committed;
            SetFocus(app->view);
            app->result=selected_result;app->host.accepted=accepted;app->host.committed=committed;
            return 0;
        }
        break;
    }
    case WM_CLOSE:
        fdb_host_finish(&app->host);
        DestroyWindow(window);return 0;
    case WM_DESTROY:
        if(!app->diagnostic) PostQuitMessage(0);
        return 0;
    case WM_GETMINMAXINFO: {
        MINMAXINFO *info=(MINMAXINFO*)lparam;
        int controls_height=fdb_win_controls_height(app);
        DWORD style=(DWORD)GetWindowLongPtrW(window,GWL_STYLE);
        DWORD extended=(DWORD)GetWindowLongPtrW(window,GWL_EXSTYLE);
        RECT limit={0,0,4096+32,4096+controls_height+16};
        int max_width=4096,max_height=4096;
        if(AdjustWindowRectEx(&limit,style,GetMenu(window)!=NULL,extended)) {
            max_width=limit.right-limit.left;max_height=limit.bottom-limit.top;
        }
        info->ptMinTrackSize.x=420;info->ptMinTrackSize.y=controls_height+100>350?controls_height+100:350;
        info->ptMaxTrackSize.x=max_width;info->ptMaxTrackSize.y=max_height;
        if(info->ptMaxSize.x<=0 || info->ptMaxSize.x>max_width) info->ptMaxSize.x=max_width;
        if(info->ptMaxSize.y<=0 || info->ptMaxSize.y>max_height) info->ptMaxSize.y=max_height;
        return 0;
    }
    default:break;
    }
    return DefWindowProcW(window,message,wparam,lparam);
}
static int fdb_win_create(FdbWin *app) {
    HINSTANCE instance=GetModuleHandleW(NULL);
    WNDCLASSW type;memset(&type,0,sizeof(type));
    type.lpfnWndProc=fdb_win_window_proc;type.hInstance=instance;
    type.lpszClassName=fdb_window_class;type.hCursor=LoadCursorW(NULL,IDC_ARROW);
    type.hbrBackground=(HBRUSH)(COLOR_WINDOW+1);
    if(!RegisterClassW(&type) && GetLastError()!=ERROR_CLASS_ALREADY_EXISTS) return 1;
    type.lpfnWndProc=fdb_win_view_proc;type.lpszClassName=fdb_view_class;
    type.hbrBackground=(HBRUSH)GetStockObject(BLACK_BRUSH);
    if(!RegisterClassW(&type) && GetLastError()!=ERROR_CLASS_ALREADY_EXISTS) return 1;
    wchar_t *title=fdb_win_wide(app->config->title),*help=fdb_win_wide(app->config->help);
    if(!title || !help) { free(title);free(help);return 1; }
    app->window=CreateWindowExW(0,fdb_window_class,title,WS_OVERLAPPEDWINDOW|WS_CLIPCHILDREN,
                              CW_USEDEFAULT,CW_USEDEFAULT,900,650,NULL,NULL,instance,app);
    free(title);
    if(!app->window) { free(help);return 1; }
    app->help=CreateWindowExW(0,L"STATIC",help,WS_CHILD|WS_VISIBLE|SS_LEFT,
                             16,8,868,46,app->window,NULL,instance,NULL);free(help);
    if(!app->help) return 1;
    app->view=CreateWindowExW(0,fdb_view_class,L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP,
                             16,fdb_win_controls_height(app),868,450,app->window,NULL,instance,app);
    if(!app->view) return 1;
    for(uint32_t slot=0;slot<app->config->region_count;slot++) {
        const FdbHostRegion *region=&app->config->regions[slot];
        wchar_t *region_label=fdb_win_wide(region->label);
        if(!region_label) return 1;
        app->selector_labels[slot]=CreateWindowExW(0,L"STATIC",region_label,WS_CHILD|WS_VISIBLE|SS_LEFT,
                                 16,61+(int)slot*32,160,24,app->window,NULL,instance,NULL);
        free(region_label);
        if(!app->selector_labels[slot]) return 1;
        app->selectors[slot]=CreateWindowExW(0,L"COMBOBOX",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|CBS_DROPDOWNLIST|WS_VSCROLL,
                                 186,58+(int)slot*32,698,200,app->window,
                                 (HMENU)(uintptr_t)(1000u+slot),instance,NULL);
        HWND combo=app->selectors[slot];if(!combo) return 1;
        for(uint32_t variant=0;variant<region->count;variant++) {
            wchar_t *label=fdb_win_wide(region->labels[variant]);if(!label) return 1;
            LRESULT added=SendMessageW(combo,CB_ADDSTRING,0,(LPARAM)label);free(label);
            if(added==CB_ERR || added==CB_ERRSPACE) return 1;
        }
        if(SendMessageW(combo,CB_SETCURSEL,(WPARAM)fdb_selected_region(slot),0)==CB_ERR) return 1;
    }
    RECT client;if(!GetClientRect(app->window,&client)) return 1;
    fdb_win_layout(app,client.right,client.bottom);
    ShowWindow(app->window,app->diagnostic?SW_SHOWNOACTIVATE:SW_SHOW);
    SetFocus(app->view);
    if(!app->diagnostic && !SetTimer(app->window,1,(UINT)(app->config->tick_ms+0.5),NULL)) return 1;
    return 0;
}
static int fdb_win_command(void *context,const FdbHostCommand *command,const uint32_t *payload) {
    (void)payload;
    FdbWin *app=(FdbWin*)context;
    if(app->host.closed && command->kind!=FDB_CMD_RESIZE) return 1;
    app->result=0;app->controlled=1;app->clock_override=1;
    app->controlled_clock=command->clock;app->controlled_modifiers=0;
    switch(command->kind) {
    case FDB_CMD_KEY: {
        if(command->a>=app->config->key_count || command->c>1u) { app->result=1;break; }
        unsigned scan=fdb_win_key_scan(app->config->keys[command->a].name);
        if(!scan) { app->result=1;break; }
        app->controlled_modifiers=command->b;
        SetFocus(command->c?app->view:app->window);
        UINT native_scan=(scan&0xffu)|((scan&0x100u)?0xe000u:0u);
        WPARAM native_key=MapVirtualKeyW(native_scan,MAPVK_VSC_TO_VK_EX);
        LPARAM parameter=(LPARAM)(1u|((scan&0xffu)<<16)|((scan&0x100u)?1u<<24:0u));
        SendMessageW(app->view,WM_KEYDOWN,native_key,parameter);break;
    }
    case FDB_CMD_POINTER: {
        int x=(int32_t)command->c,y=(int32_t)command->d;
        if(command->a>FDB_POINTER_DRAG || command->b>2u || x<-32768 || x>32767 || y<-32768 || y>32767) { app->result=1;break; }
        UINT message=WM_MOUSEMOVE;
        if(command->a==FDB_POINTER_DOWN)
            message=command->b==0?WM_LBUTTONDOWN:command->b==1?WM_RBUTTONDOWN:WM_MBUTTONDOWN;
        else if(command->a==FDB_POINTER_UP)
            message=command->b==0?WM_LBUTTONUP:command->b==1?WM_RBUTTONUP:WM_MBUTTONUP;
        WPARAM buttons=0;
        if(app->host.buttons&1u) buttons|=MK_LBUTTON;
        if(app->host.buttons&2u) buttons|=MK_RBUTTON;
        if(app->host.buttons&4u) buttons|=MK_MBUTTON;
        SendMessageW(app->view,message,buttons,MAKELPARAM((WORD)x,(WORD)y));break;
    }
    case FDB_CMD_CLOCK:
        SendMessageW(app->window,WM_TIMER,1,0);break;
    case FDB_CMD_SELECT:
        if(command->a>=app->config->region_count || command->b>=app->config->regions[command->a].count) { app->result=1;break; }
        if(SendMessageW(app->selectors[command->a],CB_SETCURSEL,command->b,0)==CB_ERR) { app->result=1;break; }
        SendMessageW(app->window,WM_COMMAND,MAKEWPARAM(1000u+command->a,CBN_SELCHANGE),(LPARAM)app->selectors[command->a]);break;
    case FDB_CMD_RESIZE:
        if(!command->a || !command->b || command->a>4096 || command->b>4096) { app->result=1;break; }
        { FdbHost candidate=app->host;
          if(fdb_host_resize(&candidate,(int)command->a,(int)command->b)) { app->result=1;break; }
        }
        if(!SetWindowPos(app->view,NULL,16,fdb_win_controls_height(app),(int)command->a,(int)command->b,SWP_NOACTIVATE|SWP_NOZORDER)) app->result=1;
        break;
    case FDB_CMD_FOCUS:
        if(command->a>1u) { app->result=1;break; }
        { HWND desired=command->a?app->view:app->window;
          HWND before=GetFocus();SetFocus(desired);
          if(GetFocus()!=desired) { app->result=1;break; }
          if(before==desired)
              SendMessageW(app->view,command->a?WM_SETFOCUS:WM_KILLFOCUS,(WPARAM)app->window,0);
        }
        break;
    default:app->result=1;break;
    }
    app->controlled=0;app->clock_override=0;
    return app->result;
}
static int fdb_win_capture(void *context,uint8_t *rgba,uint32_t width,uint32_t height) {
    FdbWin *app=(FdbWin*)context;
    if((int)width!=app->host.view_width || (int)height!=app->host.view_height) return 1;
    FdbWinSurface capture={0};
    if(fdb_win_surface_create(&capture,(int)width,(int)height)) return 1;
    app->result=0;
    SendMessageW(app->view,WM_PRINTCLIENT,(WPARAM)capture.dc,PRF_CLIENT);
    int failed=app->result;
    if(!failed) fdb_win_surface_get_rgba(&capture,rgba);
    fdb_win_surface_dispose(&capture);return failed;
}
int main(int argc,char **argv) {
    FdbWin app;memset(&app,0,sizeof(app));app.config=fdb_host_config();
    app.diagnostic=argc==4 && strcmp(argv[1],"--adapter-test")==0;
    if(argc!=1 && !app.diagnostic) {
        fprintf(stderr,"Usage: program [--adapter-test INPUT.bin OUTPUT.bin]\n");return 2;
    }
    if(!app.config || !app.config->tick_ms || app.config->region_count>16u) return 2;
    for(uint32_t i=0;i<app.config->key_count;i++)
        if(!fdb_win_key_scan(app.config->keys[i].name)) {
            fprintf(stderr,"Unsupported native physical key: %s\n",app.config->keys[i].name);return 2;
        }
    app.selectors=(HWND*)calloc(app.config->region_count?app.config->region_count:1u,sizeof(HWND));
    if(!app.selectors) return 2;
    SetProcessDPIAware();
    int result=fdb_host_open(&app.host,fdb_win_clock(&app));
    if(!result) result=fdb_win_create(&app);
    if(!result && app.diagnostic) {
        FdbHostPlatform platform={fdb_win_command,fdb_win_capture};
        result=fdb_host_study(&app.host,argv[2],argv[3],&platform,&app);
    } else if(!result) {
        MSG message;
        int got;
        while((got=GetMessageW(&message,NULL,0,0))>0) {
            TranslateMessage(&message);DispatchMessageW(&message);
            if(app.failed) { result=1;break; }
        }
        if(got<0) result=1;
    }
    if(app.window && IsWindow(app.window)) {
        KillTimer(app.window,1);DestroyWindow(app.window);
    }
    fdb_win_surface_dispose(&app.surface);fdb_host_destroy(&app.host);free(app.selectors);
    if(result) fprintf(stderr,"Native Win32 adapter refused: %s\n",fdb_last_error());
    return result?2:0;
}
