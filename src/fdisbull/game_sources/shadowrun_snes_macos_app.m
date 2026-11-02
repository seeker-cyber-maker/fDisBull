#import <Cocoa/Cocoa.h>
#include "fdisbull_native.h"

static int64_t state(fdisbull_context *c,const char *name) {
    int64_t result=0;
    if(fdisbull_state_get(c,name,0,&result)) {fprintf(stderr,"missing source state: %s\n",name);exit(2);}
    return result;
}
static void text(NSString *s,CGFloat x,CGFloat y,CGFloat size,NSColor *color) {
    [s drawAtPoint:NSMakePoint(x,y) withAttributes:@{NSFontAttributeName:[NSFont monospacedSystemFontOfSize:size weight:NSFontWeightRegular],NSForegroundColorAttributeName:color}];
}
@interface StudyView : NSView
@property(nonatomic,assign) fdisbull_context *context;
@property(nonatomic,assign) int64_t originX,originY;
@property(nonatomic,assign) BOOL paused,stopped;
@property(nonatomic,assign) NSUInteger ticks;
@end
@implementation StudyView
- (void)drawRect:(NSRect)dirty {
    (void)dirty;NSRect r=self.bounds;
    [[NSColor colorWithCalibratedRed:.055 green:.075 blue:.10 alpha:1] setFill];NSRectFill(r);
    CGFloat cx=r.size.width/2,cy=r.size.height/2;
    [NSGraphicsContext saveGraphicsState];
    NSRectClip(NSMakeRect(25,70,r.size.width-50,r.size.height-180));
    NSBezierPath *grid=[NSBezierPath bezierPath];
    for(NSInteger i=-12;i<=12;i++) {
        [grid moveToPoint:NSMakePoint(cx+i*32,70)];[grid lineToPoint:NSMakePoint(cx+i*32,r.size.height-110)];
        [grid moveToPoint:NSMakePoint(25,cy+i*32)];[grid lineToPoint:NSMakePoint(r.size.width-25,cy+i*32)];
    }
    [[NSColor colorWithCalibratedWhite:.18 alpha:1] setStroke];grid.lineWidth=1;[grid stroke];
    int64_t x=state(self.context,"shadowrun_snes_player_x"),y=state(self.context,"shadowrun_snes_player_y");
    CGFloat px=cx+(x-self.originX),py=cy-(y-self.originY);
    [[NSColor colorWithCalibratedRed:.25 green:.85 blue:.72 alpha:1] setFill];
    [[NSBezierPath bezierPathWithOvalInRect:NSMakeRect(px-7,py-7,14,14)] fill];
    [NSGraphicsContext restoreGraphicsState];
    NSColor *white=[NSColor colorWithCalibratedWhite:.88 alpha:1];
    text(@"Shadowrun SNES · Opening movement study",25,r.size.height-37,20,white);
    text(@"World-coordinate view · source camera and artwork not reproduced",25,r.size.height-62,12,white);
    text([NSString stringWithFormat:@"Player: x=%lld  y=%lld  z=%lld   updates=%lu",(long long)x,(long long)y,(long long)state(self.context,"shadowrun_snes_player_z"),(unsigned long)self.ticks],25,r.size.height-86,13,white);
    text(self.stopped?@"Unqualified action or state · R resets":(self.paused?@"Paused · Space starts movement":@"Running · Space pauses"),25,43,14,white);
    text(@"Arrows move · R resets · Esc closes · captured static scene",25,21,12,white);
}
@end
@interface StudyController : NSObject <NSApplicationDelegate,NSWindowDelegate>
@property(nonatomic,assign) fdisbull_context *context;
@property(nonatomic,strong) NSWindow *window;
@property(nonatomic,strong) StudyView *view;
@property(nonatomic,strong) NSTimer *timer;
@property(nonatomic,assign) uint8_t pad;
@end
@interface StudyWindow : NSWindow
@property(nonatomic,weak) StudyController *controller;
@end
@implementation StudyWindow
- (BOOL)canBecomeKeyWindow {return YES;}
- (void)keyDown:(NSEvent *)event {
    StudyController *c=self.controller;
    switch(event.keyCode) {
        case 126:c.pad|=1;break;case 125:c.pad|=2;break;case 123:c.pad|=4;break;case 124:c.pad|=8;break;
        case 49:if(!event.isARepeat && !c.view.stopped)c.view.paused=!c.view.paused;break;
        case 15:if(!event.isARepeat && !fdisbull_reset(c.context)) {c.pad=0;c.view.ticks=0;c.view.paused=YES;c.view.stopped=NO;}break;
        case 53:[NSApp terminate:nil];return;default:return;
    }
    [c.view setNeedsDisplay:YES];
}
- (void)keyUp:(NSEvent *)event {
    switch(event.keyCode) {case 126:self.controller.pad&=(uint8_t)~1;break;case 125:self.controller.pad&=(uint8_t)~2;break;case 123:self.controller.pad&=(uint8_t)~4;break;case 124:self.controller.pad&=(uint8_t)~8;break;default:break;}
}
@end
@implementation StudyController
- (void)applicationDidFinishLaunching:(NSNotification *)note {
    (void)note;StudyWindow *window=[[StudyWindow alloc] initWithContentRect:NSMakeRect(0,0,900,680) styleMask:(NSWindowStyleMaskTitled|NSWindowStyleMaskClosable|NSWindowStyleMaskResizable) backing:NSBackingStoreBuffered defer:NO];
    self.window=window;window.controller=self;window.delegate=self;window.title=@"Shadowrun SNES · Movement Study";
    self.view=[[StudyView alloc] initWithFrame:window.contentView.bounds];self.view.context=self.context;self.view.paused=YES;
    self.view.originX=state(self.context,"shadowrun_snes_player_x");self.view.originY=state(self.context,"shadowrun_snes_player_y");
    self.view.autoresizingMask=NSViewWidthSizable|NSViewHeightSizable;window.contentView=self.view;
    [window center];[window makeKeyAndOrderFront:nil];[NSApp activateIgnoringOtherApps:YES];
    self.timer=[NSTimer scheduledTimerWithTimeInterval:1.0/60.0 target:self selector:@selector(tick:) userInfo:nil repeats:YES];
}
- (void)tick:(NSTimer *)timer {
    (void)timer;if(self.view.paused || self.view.stopped)return;
    int result=fdisbull_step(self.context,self.pad);
    if(result)self.view.stopped=YES;else self.view.ticks++;
    [self.view setNeedsDisplay:YES];
}
- (void)windowDidResignKey:(NSNotification *)note {(void)note;self.pad=0;self.view.paused=YES;[self.view setNeedsDisplay:YES];}
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)app {(void)app;return YES;}
@end

int main(int argc,const char **argv) {
    @autoreleasepool {
        NSString *rom=nil,*snapshot=nil,*pads=nil;
        for(int i=1;i<argc;i++) {
            NSString *arg=@(argv[i]);
            if(i+1>=argc) {fprintf(stderr,"missing argument\n");return 2;}
            if([arg isEqual:@"--rom"])rom=@(argv[++i]);
            else if([arg isEqual:@"--snapshot"])snapshot=@(argv[++i]);
            else if([arg isEqual:@"--pads"])pads=@(argv[++i]);
            else {fprintf(stderr,"unknown argument\n");return 2;}
        }
        if(pads && !snapshot) {fprintf(stderr,"headless input requires --snapshot\n");return 2;}
        if(snapshot && [[NSFileManager defaultManager] fileExistsAtPath:snapshot]) {fprintf(stderr,"snapshot exists\n");return 2;}
        if(!rom)rom=[[NSBundle mainBundle] objectForInfoDictionaryKey:@"FDisBullSourceROM"];
        fdisbull_context *c=NULL;
        if(!rom || fdisbull_create(rom.fileSystemRepresentation,&c)) {fprintf(stderr,"verified source ROM required\n");return 1;}
        [NSApplication sharedApplication];
        if(snapshot) {
            StudyView *view=[[StudyView alloc] initWithFrame:NSMakeRect(0,0,900,680)];view.context=c;view.paused=YES;
            view.originX=state(c,"shadowrun_snes_player_x");view.originY=state(c,"shadowrun_snes_player_y");
            if(pads) {
                NSArray *inputs=[pads componentsSeparatedByString:@","];
                if(inputs.count>100000) {fdisbull_destroy(c);return 2;}
                for(NSString *input in inputs) {
                    NSScanner *scanner=[NSScanner scannerWithString:input];NSInteger value;
                    if(![scanner scanInteger:&value] || !scanner.isAtEnd || value<0 || value>255) {fdisbull_destroy(c);return 2;}
                    if(fdisbull_step(c,(uint8_t)value)) {view.stopped=YES;break;}view.ticks++;
                }
            }
            NSBitmapImageRep *image=[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:900 pixelsHigh:680 bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:3600 bitsPerPixel:32];
            [NSGraphicsContext saveGraphicsState];[NSGraphicsContext setCurrentContext:[NSGraphicsContext graphicsContextWithBitmapImageRep:image]];
            [view drawRect:view.bounds];[NSGraphicsContext restoreGraphicsState];
            NSData *png=[image representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
            if(![png writeToFile:snapshot options:NSDataWritingWithoutOverwriting error:NULL]) {fdisbull_destroy(c);return 1;}
            printf("{\"completed_updates\":%lu,\"stopped\":%s,\"player_x\":%lld,\"player_y\":%lld,\"player_z\":%lld}\n",(unsigned long)view.ticks,view.stopped?"true":"false",(long long)state(c,"shadowrun_snes_player_x"),(long long)state(c,"shadowrun_snes_player_y"),(long long)state(c,"shadowrun_snes_player_z"));
            fdisbull_destroy(c);return 0;
        }
        StudyController *controller=[StudyController new];controller.context=c;
        [NSApp setDelegate:controller];[NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];[NSApp run];
        fdisbull_destroy(c);return 0;
    }
}
