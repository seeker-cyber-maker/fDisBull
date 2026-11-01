/* Win16 OS services for a supplied memory UIL plan.  Game transitions and
 * storage belong to the generated blocks and the segmented shared host. */
#include <windows.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "M16HOST.H"

#define FDB16_PAINT (WM_USER + 11)
#define FDB16_CHUNK_BYTES 32760U
#define FDB16_MAX_VIEW 4096
#define FDB16_WINDOW_EXTRA 0

typedef struct { FdbU16 scan; const char *name; } Fdb16WinKey;
static const Fdb16WinKey fdb16_win_keys[] = {
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

typedef struct {
    HDC dc;
    HBITMAP bitmap;
    HGDIOBJ previous;
    int width,height;
} Fdb16WinSurface;
typedef struct {
    Fdb16Host host;
    const Fdb16Config *config;
    HINSTANCE instance;
    HWND window,view,help,selectors[16];
    Fdb16WinSurface surface;
    FARPROC window_thunk,view_thunk;
    char window_class[32],view_class[32];
    int window_registered,view_registered;
    int diagnostic,controlled,clock_override,result,failed,capture_owned;
    FdbU32 controlled_clock,controlled_modifiers;
} Fdb16Win;
typedef char Fdb16_pointer_must_fit_LONG[(sizeof(Fdb16Win*)==sizeof(LONG))?1:-1];

static const char *fdb16_win_key_name(LPARAM parameter) {
    FdbU16 scan,i;
    scan=(FdbU16)(((FdbU32)parameter >> 16) & 255UL);
    if ((FdbU32)parameter & 16777216UL) scan|=0x100U;
    for(i=0;i<sizeof(fdb16_win_keys)/sizeof(fdb16_win_keys[0]);i++)
        if(fdb16_win_keys[i].scan==scan) return fdb16_win_keys[i].name;
    return NULL;
}
static FdbU16 fdb16_win_key_scan(const char *name) {
    FdbU16 i;
    for(i=0;i<sizeof(fdb16_win_keys)/sizeof(fdb16_win_keys[0]);i++)
        if(name && strcmp(fdb16_win_keys[i].name,name)==0)
            return fdb16_win_keys[i].scan;
    return 0;
}
static FdbU32 fdb16_win_clock(const Fdb16Win *app) {
    if(app->clock_override) return app->controlled_clock;
    return ((FdbU32)GetTickCount() / (FdbU32)app->config->tick_ms)&65535UL;
}
static FdbU32 fdb16_win_modifiers(const Fdb16Win *app) {
    FdbU32 flags;
    if(app->controlled) return app->controlled_modifiers;
    flags=0UL;
    /* Win3.x has no Windows-key convention.  The controlled adapter still
     * carries the abstract command bit so its refusal is tested unchanged. */
    if(GetKeyState(VK_CONTROL)&0x8000U) flags|=FDB_MOD_CONTROL;
    if(GetKeyState(VK_MENU)&0x8000U) flags|=FDB_MOD_OPTION;
    if(GetKeyState(VK_SHIFT)&0x8000U) flags|=FDB_MOD_SHIFT;
    if(GetKeyState(VK_CAPITAL)&1) flags|=FDB_MOD_CAPS;
    return flags;
}
static void fdb16_win_surface_dispose(Fdb16WinSurface *surface) {
    if(surface->dc && surface->previous)
        SelectObject(surface->dc,surface->previous);
    if(surface->bitmap) DeleteObject((HGDIOBJ)surface->bitmap);
    if(surface->dc) DeleteDC(surface->dc);
    memset(surface,0,sizeof(*surface));
}
static int fdb16_win_surface_create(Fdb16WinSurface *surface,HWND owner,
                                    int width,int height) {
    Fdb16WinSurface next;
    HDC reference;
    if(width<=0 || height<=0 || width>FDB16_MAX_VIEW || height>FDB16_MAX_VIEW)
        return 1;
    memset(&next,0,sizeof(next));
    reference=GetDC(owner);
    if(!reference) return 1;
    next.dc=CreateCompatibleDC(reference);
    if(next.dc) next.bitmap=CreateCompatibleBitmap(reference,width,height);
    ReleaseDC(owner,reference);
    if(!next.dc || !next.bitmap) { fdb16_win_surface_dispose(&next);return 1; }
    next.previous=SelectObject(next.dc,(HGDIOBJ)next.bitmap);
    if(!next.previous || next.previous==(HGDIOBJ)-1) {
        next.previous=NULL;fdb16_win_surface_dispose(&next);return 1;
    }
    next.width=width;next.height=height;
    fdb16_win_surface_dispose(surface);*surface=next;
    return 0;
}
static void fdb16_win_dib(BITMAPINFO *info,FdbU16 width,FdbU16 height) {
    memset(info,0,sizeof(*info));
    info->bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
    info->bmiHeader.biWidth=(LONG)width;
    info->bmiHeader.biHeight=(LONG)height;
    info->bmiHeader.biPlanes=1;
    info->bmiHeader.biBitCount=24;
    info->bmiHeader.biCompression=BI_RGB;
    info->bmiHeader.biSizeImage=(((FdbU32)width*3UL+3UL)&~3UL)*(FdbU32)height;
}
static int fdb16_win_paint(Fdb16Win *app,HDC destination) {
    int width,height,failed;
    FdbU16 top,rows,capacity;
    FdbU32 stride;
    unsigned char *chunk;
    BITMAPINFO info;
    width=app->host.view_width;height=app->host.view_height;
    if(width<=0 || height<=0 || width>FDB16_MAX_VIEW || height>FDB16_MAX_VIEW)
        return 1;
    if(app->surface.width!=width || app->surface.height!=height)
        if(fdb16_win_surface_create(&app->surface,app->window,width,height)) return 1;
    stride=((FdbU32)width*3UL+3UL)&~3UL;
    capacity=(FdbU16)((FdbU32)FDB16_CHUNK_BYTES/stride);
    if(!capacity) return 1;
    chunk=(unsigned char*)malloc(FDB16_CHUNK_BYTES);
    if(!chunk) return 1;
    failed=0;
    for(top=0;top<(FdbU16)height;top=(FdbU16)(top+rows)) {
        rows=(FdbU16)(height-top);
        if(rows>capacity) rows=capacity;
        if(fdb16_host_bgr(&app->host,chunk,(FdbU16)width,(FdbU16)height,top,rows)) {
            failed=1;break;
        }
        fdb16_win_dib(&info,(FdbU16)width,rows);
        if(StretchDIBits(app->surface.dc,0,(int)top,width,(int)rows,
                        0,0,width,(int)rows,chunk,&info,DIB_RGB_COLORS,SRCCOPY)<=0) {
            failed=1;break;
        }
    }
    free(chunk);
    if(failed) return 1;
    return BitBlt(destination,0,0,width,height,app->surface.dc,0,0,SRCCOPY)?0:1;
}
static void fdb16_win_changed(Fdb16Win *app,int result) {
    app->result=result;
    if(app->view) InvalidateRect(app->view,NULL,FALSE);
    if(app->host.closed && app->view) {
        if(GetCapture()==app->view) ReleaseCapture();
        app->capture_owned=0;
    }
    if(app->host.closed && !app->diagnostic && app->window)
        PostMessage(app->window,WM_CLOSE,0,0L);
}
static void fdb16_win_release(Fdb16Win *app,int focused) {
    if(app->host.closed) return;
    if(app->host.buttons) {
        app->result=fdb16_host_focus(&app->host,0,fdb16_win_clock(app));
        if(focused && !app->result)
            app->result=fdb16_host_focus(&app->host,1,fdb16_win_clock(app));
    }
}

LRESULT __export FAR PASCAL fdb16_win_view_proc(HWND window,UINT message,
                                               WPARAM wparam,LPARAM lparam) {
    Fdb16Win *app;
    LPCREATESTRUCT create;
    PAINTSTRUCT paint;
    HDC dc;
    RECT area;
    const char *name;
    FdbU32 modifiers,phase;
    FdbU16 i,button;
    app=(Fdb16Win*)GetWindowLong(window,FDB16_WINDOW_EXTRA);
    if(message==WM_NCCREATE) {
        create=(LPCREATESTRUCT)lparam;
        app=(Fdb16Win*)create->lpCreateParams;
        SetWindowLong(window,FDB16_WINDOW_EXTRA,(LONG)app);
    }
    if(!app) return DefWindowProc(window,message,wparam,lparam);
    switch(message) {
    case WM_ERASEBKGND:return 1;
    case WM_PAINT:
        dc=BeginPaint(window,&paint);
        if(fdb16_win_paint(app,dc)) app->failed=1;
        EndPaint(window,&paint);return 0;
    case FDB16_PAINT:
        app->result=fdb16_win_paint(app,(HDC)wparam);return 0;
    case WM_SIZE:
        memset(&area,0,sizeof(area));GetClientRect(window,&area);
        if(area.right>0 && area.bottom>0)
            fdb16_win_changed(app,fdb16_host_resize(&app->host,area.right,area.bottom));
        return 0;
    case WM_SETFOCUS:
        if(!app->host.closed)
            fdb16_win_changed(app,fdb16_host_focus(&app->host,1,fdb16_win_clock(app)));
        return 0;
    case WM_KILLFOCUS:
        if(!app->host.closed)
            fdb16_win_changed(app,fdb16_host_focus(&app->host,0,fdb16_win_clock(app)));
        if(GetCapture()==window) ReleaseCapture();
        app->capture_owned=0;
        return 0;
    case WM_CANCELMODE:
        fdb16_win_release(app,GetFocus()==window);
        if(GetCapture()==window) ReleaseCapture();
        app->capture_owned=0;
        return 0;
    case WM_KEYDOWN:case WM_SYSKEYDOWN:
        name=fdb16_win_key_name(lparam);
        app->host.accepted=0;app->host.committed=0;app->result=0;
        if(!name) return message==WM_SYSKEYDOWN?
            DefWindowProc(window,message,wparam,lparam):0;
        modifiers=fdb16_win_modifiers(app);
        for(i=0;i<app->config->key_count;i++)
            if(strcmp(name,app->config->keys[i].name)==0) {
                fdb16_win_changed(app,fdb16_host_key(&app->host,i,modifiers,
                    GetFocus()==window,fdb16_win_clock(app)));
                if(modifiers&(FDB_MOD_COMMAND|FDB_MOD_CONTROL|FDB_MOD_OPTION))
                    return DefWindowProc(window,message,wparam,lparam);
                return 0;
            }
        return message==WM_SYSKEYDOWN?DefWindowProc(window,message,wparam,lparam):0;
    case WM_LBUTTONDOWN:case WM_RBUTTONDOWN:case WM_MBUTTONDOWN:
    case WM_LBUTTONUP:case WM_RBUTTONUP:case WM_MBUTTONUP:case WM_MOUSEMOVE:
        phase=app->host.buttons?FDB_POINTER_DRAG:FDB_POINTER_MOVE;button=0;
        if(message==WM_LBUTTONDOWN || message==WM_RBUTTONDOWN || message==WM_MBUTTONDOWN)
            phase=FDB_POINTER_DOWN;
        if(message==WM_LBUTTONUP || message==WM_RBUTTONUP || message==WM_MBUTTONUP)
            phase=FDB_POINTER_UP;
        if(message==WM_RBUTTONDOWN || message==WM_RBUTTONUP) button=1;
        if(message==WM_MBUTTONDOWN || message==WM_MBUTTONUP) button=2;
        if(phase==FDB_POINTER_DOWN) SetFocus(window);
        fdb16_win_changed(app,fdb16_host_pointer(&app->host,(FdbU16)phase,button,
            (int)(short)LOWORD(lparam),(int)(short)HIWORD(lparam),fdb16_win_clock(app)));
        if(phase==FDB_POINTER_DOWN && !app->host.closed && app->host.accepted &&
           app->host.buttons && GetCapture()!=window) {
            SetCapture(window);app->capture_owned=GetCapture()==window;
        }
        if(phase==FDB_POINTER_UP && !app->host.buttons) {
            if(GetCapture()==window) ReleaseCapture();
            app->capture_owned=0;
        }
        return 0;
    default:return DefWindowProc(window,message,wparam,lparam);
    }
}
static void fdb16_win_layout(Fdb16Win *app,int width,int height) {
    int controls_height,game_width,game_height;
    FdbU16 slot;
    controls_height=app->config->region_count?102:70;
    if(width<=32 || height<=controls_height+16) return;
    game_width=width-32;game_height=height-controls_height-16;
    if(game_width>FDB16_MAX_VIEW) game_width=FDB16_MAX_VIEW;
    if(game_height>FDB16_MAX_VIEW) game_height=FDB16_MAX_VIEW;
    if(app->help) MoveWindow(app->help,16,8,game_width,46,TRUE);
    for(slot=0;slot<app->config->region_count;slot++)
        if(app->selectors[slot])
            MoveWindow(app->selectors[slot],16+(int)slot*260,58,250,200,TRUE);
    if(app->view) MoveWindow(app->view,16,controls_height,game_width,game_height,TRUE);
}
LRESULT __export FAR PASCAL fdb16_win_window_proc(HWND window,UINT message,
                                                 WPARAM wparam,LPARAM lparam) {
    Fdb16Win *app;
    LPCREATESTRUCT create;
    RECT area,limit;
    MINMAXINFO FAR *limits;
    FdbU16 id,slot;
    HWND combo;
    LRESULT selected;
    int before,saved_result,accepted,committed,controls_height,max_width,max_height;
    app=(Fdb16Win*)GetWindowLong(window,FDB16_WINDOW_EXTRA);
    if(message==WM_NCCREATE) {
        create=(LPCREATESTRUCT)lparam;
        app=(Fdb16Win*)create->lpCreateParams;
        SetWindowLong(window,FDB16_WINDOW_EXTRA,(LONG)app);
    }
    if(!app) return DefWindowProc(window,message,wparam,lparam);
    switch(message) {
    case WM_SIZE:
        if(wparam==SIZE_MINIMIZED) return 0;
        memset(&area,0,sizeof(area));GetClientRect(window,&area);
        fdb16_win_layout(app,area.right,area.bottom);return 0;
    case WM_TIMER:
        if(wparam==1 && !app->host.closed) {
            if(app->capture_owned && GetCapture()!=app->view) {
                fdb16_win_release(app,GetFocus()==app->view);
                app->capture_owned=0;
            }
            fdb16_win_changed(app,fdb16_host_tick(&app->host,fdb16_win_clock(app)));
        }
        return 0;
    case WM_ACTIVATEAPP:
        if(!wparam) {
            fdb16_win_release(app,0);
            if(GetCapture()==app->view) ReleaseCapture();
            app->capture_owned=0;
        }
        return 0;
    case WM_COMMAND:
        /* Win16 control id is wParam; notification is HIWORD(lParam). */
        id=(FdbU16)wparam;
        if(HIWORD(lparam)==CBN_SELCHANGE && id>=1000 &&
           id-1000<app->config->region_count) {
            slot=(FdbU16)(id-1000);combo=app->selectors[slot];
            if((HWND)LOWORD(lparam)!=combo) return 0;
            selected=SendMessage(combo,CB_GETCURSEL,0,0L);
            before=fdb16_core_selected(slot);
            fdb16_win_changed(app,selected<0?1:
                fdb16_host_select(&app->host,slot,(FdbU16)selected));
            if(app->result && before>=0)
                SendMessage(combo,CB_SETCURSEL,(WPARAM)before,0L);
            saved_result=app->result;
            accepted=app->host.accepted;committed=app->host.committed;
            SetFocus(app->view);
            app->result=saved_result;
            app->host.accepted=accepted;app->host.committed=committed;
            return 0;
        }
        break;
    case WM_CLOSE:
        fdb16_host_finish(&app->host);DestroyWindow(window);return 0;
    case WM_DESTROY:
        if(!app->diagnostic) PostQuitMessage(0);
        return 0;
    case WM_GETMINMAXINFO:
        limits=(MINMAXINFO FAR *)lparam;
        controls_height=app->config->region_count?102:70;
        limit.left=0;limit.top=0;limit.right=FDB16_MAX_VIEW+32;
        limit.bottom=FDB16_MAX_VIEW+controls_height+16;
        AdjustWindowRect(&limit,(DWORD)GetWindowLong(window,GWL_STYLE),GetMenu(window)!=NULL);
        max_width=limit.right-limit.left;max_height=limit.bottom-limit.top;
        limits->ptMinTrackSize.x=420;limits->ptMinTrackSize.y=350;
        limits->ptMaxTrackSize.x=max_width;limits->ptMaxTrackSize.y=max_height;
        if(limits->ptMaxSize.x<=0 || limits->ptMaxSize.x>max_width)
            limits->ptMaxSize.x=max_width;
        if(limits->ptMaxSize.y<=0 || limits->ptMaxSize.y>max_height)
            limits->ptMaxSize.y=max_height;
        return 0;
    default:break;
    }
    return DefWindowProc(window,message,wparam,lparam);
}
static int fdb16_win_create(Fdb16Win *app,int show) {
    WNDCLASS type;
    RECT client;
    FdbU16 slot,variant;
    const Fdb16Region *region;
    HWND combo;
    LRESULT added;
    memset(&type,0,sizeof(type));
    app->window_thunk=MakeProcInstance((FARPROC)fdb16_win_window_proc,app->instance);
    app->view_thunk=MakeProcInstance((FARPROC)fdb16_win_view_proc,app->instance);
    if(!app->window_thunk || !app->view_thunk) return 1;
    /* Each instance owns its DS-binding thunks and class registrations. */
    sprintf(app->window_class,"Fdb16Window%04x",(unsigned)app->instance);
    sprintf(app->view_class,"Fdb16View%04x",(unsigned)app->instance);
    type.lpfnWndProc=(WNDPROC)app->window_thunk;type.hInstance=app->instance;
    type.cbWndExtra=sizeof(Fdb16Win*);
    type.lpszClassName=app->window_class;type.hCursor=LoadCursor(NULL,IDC_ARROW);
    type.hbrBackground=(HBRUSH)(COLOR_WINDOW+1);
    if(!RegisterClass(&type)) return 1;
    app->window_registered=1;
    type.lpfnWndProc=(WNDPROC)app->view_thunk;type.lpszClassName=app->view_class;
    type.hbrBackground=(HBRUSH)GetStockObject(BLACK_BRUSH);
    if(!RegisterClass(&type)) return 1;
    app->view_registered=1;
    app->window=CreateWindow(app->window_class,app->config->title,
        WS_OVERLAPPEDWINDOW|WS_CLIPCHILDREN,CW_USEDEFAULT,CW_USEDEFAULT,
        900,650,NULL,NULL,app->instance,app);
    if(!app->window) return 1;
    app->help=CreateWindow("STATIC",app->config->help,WS_CHILD|WS_VISIBLE|SS_LEFT,
        16,8,868,46,app->window,NULL,app->instance,NULL);
    if(!app->help) return 1;
    app->view=CreateWindow(app->view_class,"",WS_CHILD|WS_VISIBLE|WS_TABSTOP,
        16,102,868,450,app->window,NULL,app->instance,app);
    if(!app->view) return 1;
    for(slot=0;slot<app->config->region_count;slot++) {
        region=&app->config->regions[slot];
        combo=CreateWindow("COMBOBOX","",
            WS_CHILD|WS_VISIBLE|WS_TABSTOP|CBS_DROPDOWNLIST|WS_VSCROLL,
            16+(int)slot*260,58,250,200,app->window,
            (HMENU)(1000+slot),app->instance,NULL);
        app->selectors[slot]=combo;
        if(!combo) return 1;
        for(variant=0;variant<region->count;variant++) {
            added=SendMessage(combo,CB_ADDSTRING,0,(LPARAM)region->labels[variant]);
            if(added==CB_ERR || added==CB_ERRSPACE) return 1;
        }
        if(SendMessage(combo,CB_SETCURSEL,(WPARAM)fdb16_core_selected(slot),0L)==CB_ERR)
            return 1;
    }
    memset(&client,0,sizeof(client));GetClientRect(app->window,&client);
    fdb16_win_layout(app,client.right,client.bottom);
    ShowWindow(app->window,app->diagnostic?SW_SHOWNOACTIVATE:show);
    SetFocus(app->view);
    if(!app->diagnostic && !SetTimer(app->window,1,app->config->tick_ms,NULL)) return 1;
    return 0;
}
static int fdb16_win_coordinate(FdbU32 value,int *coordinate) {
    if(value<=32767UL) *coordinate=(int)value;
    else if(value>=4294934528UL) *coordinate=-1-(int)(4294967295UL-value);
    else return 1;
    return 0;
}
static int fdb16_win_command(void *context,const Fdb16Command *command,
                           const Fdb16Arena *payload) {
    Fdb16Win *app;
    FdbU16 scan;
    HWND desired,before;
    UINT message;
    WPARAM buttons,native_key;
    LPARAM parameter;
    int x,y;
    (void)payload;
    app=(Fdb16Win*)context;
    if(app->host.closed && command->kind!=FDB_CMD_RESIZE) return 1;
    app->result=0;app->controlled=1;app->clock_override=1;
    app->controlled_clock=command->clock;app->controlled_modifiers=0UL;
    switch(command->kind) {
    case FDB_CMD_KEY:
        if(command->a>=app->config->key_count || command->c>1UL) { app->result=1;break; }
        scan=fdb16_win_key_scan(app->config->keys[(FdbU16)command->a].name);
        if(!scan) { app->result=1;break; }
        app->controlled_modifiers=command->b;
        SetFocus(command->c?app->view:app->window);
        native_key=(WPARAM)MapVirtualKey(scan&255U,1);
        parameter=(LPARAM)(1UL|((FdbU32)(scan&255U)<<16)|
                            ((scan&0x100U)?16777216UL:0UL));
        SendMessage(app->view,WM_KEYDOWN,native_key,parameter);break;
    case FDB_CMD_POINTER:
        if(command->a>FDB_POINTER_DRAG || command->b>2UL ||
           fdb16_win_coordinate(command->c,&x) || fdb16_win_coordinate(command->d,&y)) {
            app->result=1;break;
        }
        message=WM_MOUSEMOVE;
        if(command->a==FDB_POINTER_DOWN)
            message=command->b==0UL?WM_LBUTTONDOWN:
                    command->b==1UL?WM_RBUTTONDOWN:WM_MBUTTONDOWN;
        else if(command->a==FDB_POINTER_UP)
            message=command->b==0UL?WM_LBUTTONUP:
                    command->b==1UL?WM_RBUTTONUP:WM_MBUTTONUP;
        buttons=0;
        if(app->host.buttons&1UL) buttons|=MK_LBUTTON;
        if(app->host.buttons&2UL) buttons|=MK_RBUTTON;
        if(app->host.buttons&4UL) buttons|=MK_MBUTTON;
        SendMessage(app->view,message,buttons,MAKELONG((WORD)x,(WORD)y));break;
    case FDB_CMD_CLOCK:
        SendMessage(app->window,WM_TIMER,1,0L);break;
    case FDB_CMD_SELECT:
        if(command->a>=app->config->region_count ||
           command->b>=app->config->regions[(FdbU16)command->a].count) {
            app->result=1;break;
        }
        desired=app->selectors[(FdbU16)command->a];
        if(SendMessage(desired,CB_SETCURSEL,(WPARAM)command->b,0L)==CB_ERR) {
            app->result=1;break;
        }
        SendMessage(app->window,WM_COMMAND,(WPARAM)(1000UL+command->a),
                    MAKELONG((WORD)desired,CBN_SELCHANGE));break;
    case FDB_CMD_RESIZE:
        if(!command->a || !command->b || command->a>FDB16_MAX_VIEW ||
           command->b>FDB16_MAX_VIEW) { app->result=1;break; }
        if(!SetWindowPos(app->view,NULL,16,102,(int)command->a,(int)command->b,
                        SWP_NOACTIVATE|SWP_NOZORDER)) app->result=1;
        break;
    case FDB_CMD_FOCUS:
        if(command->a>1UL) { app->result=1;break; }
        desired=command->a?app->view:app->window;
        before=GetFocus();SetFocus(desired);
        if(GetFocus()!=desired) { app->result=1;break; }
        if(before==desired)
            SendMessage(app->view,command->a?WM_SETFOCUS:WM_KILLFOCUS,
                        (WPARAM)app->window,0L);
        break;
    default:app->result=1;break;
    }
    app->controlled=0;app->clock_override=0;
    return app->result;
}
static int fdb16_win_capture(void *context,Fdb16File *output,FdbU16 width,FdbU16 height) {
    Fdb16Win *app;
    Fdb16WinSurface capture;
    BITMAPINFO info;
    unsigned char *chunk,*rgba,*source;
    FdbU32 stride;
    FdbU16 top,rows,capacity,row,x;
    HDC reference;
    int failed;
    app=(Fdb16Win*)context;
    if(!output || width!=(FdbU16)app->host.view_width ||
       height!=(FdbU16)app->host.view_height) return 1;
    memset(&capture,0,sizeof(capture));
    if(fdb16_win_surface_create(&capture,app->window,width,height)) return 1;
    chunk=(unsigned char*)malloc(FDB16_CHUNK_BYTES);
    rgba=(unsigned char*)malloc((unsigned)(width*4U));
    if(!chunk || !rgba) {
        free(chunk);free(rgba);fdb16_win_surface_dispose(&capture);return 1;
    }
    app->result=0;
    SendMessage(app->view,FDB16_PAINT,(WPARAM)capture.dc,0L);
    failed=app->result;
    /* GetDIBits reads our bitmap, after deselecting it, never a screen DC.
     * The owner DC here supplies only the requested native color format. */
    SelectObject(capture.dc,capture.previous);capture.previous=NULL;
    reference=GetDC(app->window);
    if(!reference) failed=1;
    fdb16_win_dib(&info,width,height);
    stride=((FdbU32)width*3UL+3UL)&~3UL;
    capacity=(FdbU16)((FdbU32)FDB16_CHUNK_BYTES/stride);
    top=0;
    while(!failed && top<height) {
        rows=(FdbU16)(height-top);if(rows>capacity) rows=capacity;
        if(GetDIBits(reference,capture.bitmap,(UINT)(height-top-rows),(UINT)rows,
                     chunk,&info,DIB_RGB_COLORS)!=(int)rows) { failed=1;break; }
        for(row=0;row<rows;row++) {
            source=chunk+(unsigned)((FdbU32)(rows-1U-row)*stride);
            for(x=0;x<width;x++) {
                rgba[x*4U]=source[x*3U+2U];rgba[x*4U+1U]=source[x*3U+1U];
                rgba[x*4U+2U]=source[x*3U];rgba[x*4U+3U]=255;
            }
            if(fdb16_write_bytes(output,rgba,(FdbU32)width*4UL)) { failed=1;break; }
        }
        top=(FdbU16)(top+rows);
    }
    if(reference) ReleaseDC(app->window,reference);
    free(chunk);free(rgba);fdb16_win_surface_dispose(&capture);
    return failed;
}
static void fdb16_win_dispose(Fdb16Win *app) {
    if(app->window && IsWindow(app->window)) {
        KillTimer(app->window,1);DestroyWindow(app->window);
    }
    fdb16_win_surface_dispose(&app->surface);
    if(app->view_registered) UnregisterClass(app->view_class,app->instance);
    if(app->window_registered) UnregisterClass(app->window_class,app->instance);
    if(app->view_thunk) FreeProcInstance(app->view_thunk);
    if(app->window_thunk) FreeProcInstance(app->window_thunk);
    fdb16_host_destroy(&app->host);
}
int PASCAL WinMain(HINSTANCE instance,HINSTANCE previous,LPSTR command,int show) {
    Fdb16Win app;
    Fdb16Platform platform;
    MSG message;
    char initial[256],input[256],output[256];
    FdbU16 i;
    int mode,result,got;
    (void)previous;
    memset(&app,0,sizeof(app));app.instance=instance;app.config=fdb16_config();
    mode=fdb16_arguments(command,input,output);
    if(mode<0 || !app.config || !app.config->tick_ms || app.config->region_count>16U)
        return 2;
    app.diagnostic=mode;
    for(i=0;i<app.config->key_count;i++)
        if(!fdb16_win_key_scan(app.config->keys[i].name)) return 2;
    if(fdb16_initial_path(instance,initial)) return 2;
    result=fdb16_host_open(&app.host,initial,fdb16_win_clock(&app));
    if(!result) result=fdb16_win_create(&app,show);
    if(!result && app.diagnostic) {
        platform.command=fdb16_win_command;platform.capture_view=fdb16_win_capture;
        result=fdb16_host_study(&app.host,input,output,&platform,&app);
    } else if(!result) {
        got=0;
        while((got=GetMessage(&message,NULL,0,0))>0) {
            TranslateMessage(&message);DispatchMessage(&message);
            if(app.failed) { result=1;break; }
        }
        if(got<0) result=1;
    }
    fdb16_win_dispose(&app);
    return result?2:0;
}
