#import <Cocoa/Cocoa.h>
#include "fdisbull_native.h"
#include <stdint.h>
#include <stdlib.h>
#include <time.h>

/* Source-qualified menu leaf is linked separately from the arena core. */
extern uint8_t shadowrun_menu_phase,shadowrun_menu_cursor,shadowrun_menu_archetype,shadowrun_menu_preview,shadowrun_menu_supported;
extern unsigned int shadowrun_menu_pressed;
extern void shadowrun_menu_tick(void);

/* Authored symbolic display of the source-bound shared state, not game art. */
@interface ArenaView : NSView
@property(nonatomic, assign) fdisbull_context *context;
@property(nonatomic, assign) BOOL stopped;
@property(nonatomic, assign) BOOL paused;
@property(nonatomic, assign) BOOL sourceMenu;
@property(nonatomic, copy) NSString *message;
@property(nonatomic, strong) NSData *terrain;
@end

static int64_t value(fdisbull_context *ctx, const char *name, uint32_t index) {
    int64_t out=0;
    if (fdisbull_state_get(ctx,name,index,&out)!=0) return 0;
    return out;
}
static void label(NSString *text, NSPoint point, CGFloat size, NSColor *color) {
    [text drawAtPoint:point withAttributes:@{NSFontAttributeName:[NSFont monospacedSystemFontOfSize:size weight:NSFontWeightRegular], NSForegroundColorAttributeName:color}];
}

@implementation ArenaView
- (BOOL)isFlipped { return YES; }
- (BOOL)acceptsFirstResponder { return YES; }
- (BOOL)isAccessibilityElement { return YES; }
- (NSString *)accessibilityRole { return NSAccessibilityGroupRole; }
- (NSString *)accessibilityLabel {
    if (!self.context) return @"Arena unavailable";
    if (self.sourceMenu) return [NSString stringWithFormat:@"Source menu phase %u, selection %u",shadowrun_menu_phase,shadowrun_menu_cursor];
    return [NSString stringWithFormat:@"%@ %@, player %lld %lld, HP %lld, ammo %lld, inventory %@",
        value(self.context,"shadowrun_courtyard_profile",0)?@"Captured courtyard":@"Arena",
        self.stopped?@"stopped":self.paused?@"paused":@"running",
        (long long)value(self.context,"shadowrun_player_x",0),(long long)value(self.context,"shadowrun_player_y",0),
        (long long)value(self.context,"shadowrun_arena_hp",0),(long long)value(self.context,"shadowrun_play_ammo",0),
        value(self.context,"shadowrun_play_menu",0)?@"open":@"closed"];
}
- (void)drawRect:(NSRect)dirty {
    (void)dirty;
    NSRect bounds=self.bounds;
    [[NSColor colorWithCalibratedRed:0.055 green:0.065 blue:0.08 alpha:1] setFill];NSRectFill(bounds);
    fdisbull_context *c=self.context;if (!c) return;
    if (self.sourceMenu) {
        label(@"SHADOWRUN  /  SOURCE MENU",NSMakePoint(36,35),18,[NSColor whiteColor]);
        label(@"Original menu choices · symbolic presentation",NSMakePoint(36,64),12,[NSColor lightGrayColor]);
        if (shadowrun_menu_phase<2) {
            NSArray<NSString *> *items=shadowrun_menu_phase==0?@[@"New Game",@"Load Game"]:@[@"Samurai",@"Decker",@"Gator Shaman"];
            for(NSUInteger i=0;i<items.count;i++) {
                BOOL selected=i==shadowrun_menu_cursor;
                label([NSString stringWithFormat:@"%c  %@",selected?'>':' ',items[i]],NSMakePoint(70,125+i*42),16,selected?[NSColor systemCyanColor]:[NSColor whiteColor]);
            }
            label(@"Up/Down choose · Z or X confirm · Enter is ignored here",NSMakePoint(36,bounds.size.height-48),12,[NSColor lightGrayColor]);
        } else if (shadowrun_menu_phase==2) {
            NSArray<NSString *> *names=@[@"Samurai",@"Decker",@"Gator Shaman"];
            NSString *choice=shadowrun_menu_archetype<names.count?names[shadowrun_menu_archetype]:@"Unknown";
            label([NSString stringWithFormat:@"Selected archetype: %@",choice],NSMakePoint(70,125),16,[NSColor whiteColor]);
            label(@"Original character initialization is not modeled.",NSMakePoint(70,167),14,[NSColor lightGrayColor]);
            label(value(c,"shadowrun_courtyard_profile",0)?@"P enters the separately captured courtyard.":@"P enters the separately prepared assisted arena.",NSMakePoint(70,195),14,[NSColor systemYellowColor]);
            label(@"The menu choice does not change that prepared scene.",NSMakePoint(70,221),12,[NSColor lightGrayColor]);
            label(@"The original opening later drives an automatic arrival walk.",NSMakePoint(70,257),12,[NSColor lightGrayColor]);
            label(@"The full opening is not modeled here.",NSMakePoint(70,279),12,[NSColor lightGrayColor]);
            label(@"R returns to the source menu · Esc quits",NSMakePoint(36,bounds.size.height-48),12,[NSColor lightGrayColor]);
        } else {
            label(@"Original load continuation is not modeled.",NSMakePoint(70,125),16,[NSColor whiteColor]);
            label(@"R returns to the source menu · Esc quits",NSMakePoint(36,bounds.size.height-48),12,[NSColor lightGrayColor]);
        }
        return;
    }
    BOOL menu=value(c,"shadowrun_play_menu",0)!=0;
    int64_t hp=value(c,"shadowrun_arena_hp",0),ammo=value(c,"shadowrun_play_ammo",0);
    int64_t target=value(c,"shadowrun_target_selected",0),status=value(c,"shadowrun_arena_frame_status",0);
    BOOL courtyard=value(c,"shadowrun_courtyard_profile",0)!=0;
    NSString *top=courtyard?[NSString stringWithFormat:@"SHADOWRUN  /  CAPTURED COURTYARD       HP %lld",(long long)hp]:[NSString stringWithFormat:@"SHADOWRUN  /  ASSISTED ARENA       HP %lld   AMMO %lld",(long long)hp,(long long)ammo];
    label(top,NSMakePoint(20,14),15,[NSColor whiteColor]);
    NSString *hint=courtyard?@"Space start/pause   Arrows move   R reset · Fire and inventory unavailable":@"Space start/pause   Arrows move   Z fire/equip   X target/back   Enter inventory   R reset";
    label(hint,NSMakePoint(20,37),11,[NSColor colorWithWhite:0.7 alpha:1]);
    if (menu) {
        label(@"INVENTORY  ·  Captured item identifiers",NSMakePoint(24,78),16,[NSColor whiteColor]);
        int64_t row=value(c,"shadowrun_inventory_row",0),col=value(c,"shadowrun_inventory_column",0);
        for (int i=0;i<8;i++) {
            char name[40];snprintf(name,sizeof(name),"shadowrun_inventory_cell%d",i);
            int64_t item=value(c,name,0);CGFloat x=42+(i%2)*300,y=120+(i/2)*62;
            BOOL selected=(row==i/2 && col==i%2);
            [[selected?[NSColor colorWithCalibratedRed:0.14 green:0.36 blue:0.46 alpha:1]:[NSColor colorWithWhite:0.14 alpha:1] colorUsingColorSpace:NSColorSpace.genericRGBColorSpace] setFill];
            NSRectFill(NSMakeRect(x,y,270,47));
            label([NSString stringWithFormat:@"%c  SLOT %d     ITEM %02llX",selected?'>':' ',i,(unsigned long long)item],NSMakePoint(x+12,y+14),14,[NSColor whiteColor]);
        }
        label([NSString stringWithFormat:@"Weapon %02llX    Armor %lld",(unsigned long long)value(c,"shadowrun_play_weapon_item",0),(long long)value(c,"shadowrun_inventory_equipped_armor",0)],NSMakePoint(42,392),14,[NSColor lightGrayColor]);
    } else {
        if (!self.terrain) {
            NSMutableData *terrain=[NSMutableData dataWithLength:2816];uint8_t *bytes=terrain.mutableBytes;
            for (uint32_t i=0;i<2816;i++) bytes[i]=(uint8_t)value(c,"shadowrun_terrain_map",i);
            self.terrain=terrain;
        }
        const uint8_t *terrain=self.terrain.bytes;
        CGFloat cell=MIN((bounds.size.width-40)/64.0,(bounds.size.height-130)/44.0);
        if (cell<1) cell=1;
        CGFloat ox=(bounds.size.width-cell*64)/2,oy=65;
        NSColor *colors[4]={[NSColor colorWithCalibratedRed:0.15 green:0.18 blue:0.19 alpha:1],
            [NSColor colorWithCalibratedRed:0.43 green:0.46 blue:0.46 alpha:1],
            [NSColor colorWithCalibratedRed:0.24 green:0.27 blue:0.32 alpha:1],
            [NSColor colorWithCalibratedRed:0.33 green:0.24 blue:0.27 alpha:1]};
        for (int y=0;y<44;y++) for (int x=0;x<64;x++) {
            int64_t raw=terrain[y*64+x];
            int category=raw==0?0:raw==127?1:raw<128?2:3;
            [colors[category] setFill];NSRectFill(NSMakeRect(ox+x*cell,oy+y*cell,cell-0.35,cell-0.35));
        }
        for (uint32_t i=0;i<7;i++) {
            if (!(value(c,"shadowrun_target_flags",i)&1)) continue;
            CGFloat x=ox+((CGFloat)value(c,"shadowrun_target_x",i)/512.0)*cell;
            CGFloat y=oy+((CGFloat)value(c,"shadowrun_target_y",i)/512.0)*cell;
            [i==target?[NSColor systemRedColor]:[NSColor systemOrangeColor] setFill];
            [[NSBezierPath bezierPathWithOvalInRect:NSMakeRect(x-4,y-4,8,8)] fill];
        }
        CGFloat px=ox+((CGFloat)value(c,"shadowrun_player_x",0)/512.0)*cell;
        CGFloat py=oy+((CGFloat)value(c,"shadowrun_player_y",0)/512.0)*cell;
        [[NSColor systemCyanColor] setFill];NSRectFill(NSMakeRect(px-4,py-4,8,8));
        NSString *targetText=target<7?[NSString stringWithFormat:@"Target %lld  HP %lld",(long long)target,(long long)value(c,"shadowrun_play_actor_hp",(uint32_t)target)]:@"No target selected";
        label(targetText,NSMakePoint(20,oy+44*cell+12),12,[NSColor whiteColor]);
        label(@"Map colors group raw terrain values; they do not indicate passability.",NSMakePoint(20,oy+44*cell+31),11,[NSColor lightGrayColor]);
    }
    if (self.paused && !self.stopped && status!=3) label(@"PAUSED · press Space to start",NSMakePoint(20,bounds.size.height-24),13,[NSColor systemYellowColor]);
    if (self.message && !self.stopped) label(self.message,NSMakePoint(bounds.size.width/2,bounds.size.height-24),12,[NSColor systemYellowColor]);
    if (self.stopped || status==3) {
        NSString *msg=status==3?@"HP depleted · press R to restart":(self.message?:@"Unsupported state · press R to restart");
        label(msg,NSMakePoint(20,bounds.size.height-24),13,[NSColor systemRedColor]);
    }
}
@end

@interface ArenaController : NSObject <NSApplicationDelegate,NSWindowDelegate>
@property(nonatomic, assign) fdisbull_context *context;
@property(nonatomic, strong) NSWindow *window;
@property(nonatomic, strong) ArenaView *view;
@property(nonatomic, strong) NSTimer *timer;
@property(nonatomic, assign) uint8_t pad;
@property(nonatomic, assign) uint8_t latched;
@property(nonatomic, assign) BOOL running;
@end

@interface ArenaWindow : NSWindow
@property(nonatomic, weak) ArenaController *controller;
@end
@implementation ArenaWindow
- (void)keyDown:(NSEvent *)e {
    ArenaController *c=self.controller;uint8_t b=0;
    if (c.view.sourceMenu) {
        if(e.isARepeat) return;
        if(e.keyCode==53) {[NSApp terminate:nil];return;}
        if(e.keyCode==15) {shadowrun_menu_phase=0;shadowrun_menu_cursor=0;shadowrun_menu_preview=0;shadowrun_menu_archetype=0;[c.view setNeedsDisplay:YES];return;}
        if(shadowrun_menu_phase==2U && e.keyCode==35) {c.view.sourceMenu=NO;c.view.paused=YES;c.running=NO;c.pad=0;c.latched=0;[c.view setNeedsDisplay:YES];return;}
        if(shadowrun_menu_phase>1U) return;
        shadowrun_menu_pressed=0;
        if(e.keyCode==126) shadowrun_menu_pressed=0x0100U;
        else if(e.keyCode==125) shadowrun_menu_pressed=0x0200U;
        else if(e.keyCode==6) shadowrun_menu_pressed=0x4000U;
        else if(e.keyCode==7) shadowrun_menu_pressed=0x1000U;
        if(shadowrun_menu_pressed) {shadowrun_menu_tick();[c.view setNeedsDisplay:YES];}
        return;
    }
    if (value(c.context,"shadowrun_courtyard_profile",0) && (e.keyCode==6 || e.keyCode==7 || e.keyCode==36)) {
        c.view.message=@"Action unavailable in captured courtyard";[c.view setNeedsDisplay:YES];return;
    }
    switch(e.keyCode) {case 126:b=1;break;case 125:b=2;break;case 123:b=4;break;case 124:b=8;break;
        case 7:b=16;break;case 6:b=64;break;case 36:b=128;break;
        case 49: if(!e.isARepeat && !c.view.stopped){c.running=!c.running;c.view.paused=!c.running;[c.view setNeedsDisplay:YES];}return;
        case 15: if(!e.isARepeat && fdisbull_reset(c.context)==0){c.pad=0;c.latched=0;c.running=NO;c.view.paused=YES;c.view.stopped=NO;c.view.message=nil;[c.view setNeedsDisplay:YES];}return;
        case 53:[NSApp terminate:nil];return;default:return;}
    c.pad|=b;if (!e.isARepeat && (b&0xd0U)) c.latched|=b;
}
- (void)keyUp:(NSEvent *)e {
    uint8_t b=0;switch(e.keyCode) {case 126:b=1;break;case 125:b=2;break;case 123:b=4;break;case 124:b=8;break;case 7:b=16;break;case 6:b=64;break;case 36:b=128;break;default:return;}
    self.controller.pad &= (uint8_t)~b;
}
- (BOOL)canBecomeKeyWindow { return YES; }
@end

@implementation ArenaController
- (void)applicationDidFinishLaunching:(NSNotification *)note {
    (void)note;ArenaWindow *w=[[ArenaWindow alloc] initWithContentRect:NSMakeRect(0,0,960,760)
        styleMask:(NSWindowStyleMaskTitled|NSWindowStyleMaskClosable|NSWindowStyleMaskResizable) backing:NSBackingStoreBuffered defer:NO];
    self.window=w;w.controller=self;w.delegate=self;w.title=@"Shadowrun · Assisted Arena";w.minSize=NSMakeSize(640,520);
    self.view=[[ArenaView alloc] initWithFrame:w.contentView.bounds];self.view.autoresizingMask=NSViewWidthSizable|NSViewHeightSizable;self.view.context=self.context;self.view.paused=YES;self.view.sourceMenu=YES;
    w.contentView=self.view;[w center];[w makeKeyAndOrderFront:nil];[NSApp activateIgnoringOtherApps:YES];
    self.timer=[NSTimer scheduledTimerWithTimeInterval:(1.0/60.0) target:self selector:@selector(tick:) userInfo:nil repeats:YES];
}
- (void)tick:(NSTimer *)timer {
    (void)timer;if(self.view.sourceMenu || !self.running || self.view.stopped || value(self.context,"shadowrun_arena_frame_status",0)==3) return;
    uint8_t input=self.pad|self.latched;self.latched=0;
    int rc=fdisbull_step(self.context,input);
    if(rc) {self.view.stopped=YES;self.view.message=rc==1?@"Unsupported action or state · press R to restart":@"Runtime fault · press R to restart";}
    [self.view setNeedsDisplay:YES];
}
- (void)windowDidResignKey:(NSNotification *)note { (void)note;self.pad=0;self.latched=0;self.running=NO;self.view.paused=YES;[self.view setNeedsDisplay:YES]; }
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)app { (void)app;return YES; }
@end

int main(int argc,const char **argv) {
    @autoreleasepool {
        NSString *rom=nil,*snapshot=nil,*pads=nil,*menuEdges=nil;long steps=0,renders=1;BOOL enterPrepared=NO;
        for(int i=1;i<argc;i++) {
            NSString *arg=[NSString stringWithUTF8String:argv[i]];
            if (([arg isEqual:@"--rom"] || [arg isEqual:@"--snapshot"] || [arg isEqual:@"--steps"] || [arg isEqual:@"--pads"] || [arg isEqual:@"--render-benchmark"] || [arg isEqual:@"--menu-edges"]) && i+1>=argc) {fprintf(stderr,"missing argument\n");return 2;}
            if ([arg isEqual:@"--rom"]) rom=[NSString stringWithUTF8String:argv[++i]];
            else if ([arg isEqual:@"--snapshot"]) snapshot=[NSString stringWithUTF8String:argv[++i]];
            else if ([arg isEqual:@"--pads"]) pads=[NSString stringWithUTF8String:argv[++i]];
            else if ([arg isEqual:@"--menu-edges"]) menuEdges=[NSString stringWithUTF8String:argv[++i]];
            else if ([arg isEqual:@"--enter-prepared"]) enterPrepared=YES;
            else if ([arg isEqual:@"--steps"]) {char *end=NULL;steps=strtol(argv[++i],&end,10);if(!end || *end || steps<0 || steps>100000) return 2;}
            else if ([arg isEqual:@"--render-benchmark"]) {char *end=NULL;renders=strtol(argv[++i],&end,10);if(!end || *end || renders<1 || renders>10000) return 2;}
            else {fprintf(stderr,"unknown option\n");return 2;}
        }
        if (!snapshot && (steps || pads || menuEdges || enterPrepared || renders!=1)) {fprintf(stderr,"headless options require --snapshot\n");return 2;}
        if (enterPrepared && !menuEdges) {fprintf(stderr,"prepared entry requires menu evidence\n");return 2;}
        if (snapshot && [[NSFileManager defaultManager] fileExistsAtPath:snapshot]) {fprintf(stderr,"snapshot already exists\n");return 2;}
        if (!rom) rom=[[NSBundle mainBundle] objectForInfoDictionaryKey:@"FDisBullSourceROM"];
        if (!rom) {fprintf(stderr,"source ROM path required\n");return 2;}
        fdisbull_context *ctx=NULL;int rc=fdisbull_create(rom.fileSystemRepresentation,&ctx);
        if(rc || !ctx) {fprintf(stderr,"cannot open verified source ROM (%d)\n",rc);return 1;}
        [NSApplication sharedApplication];
        if (snapshot) {
            BOOL menuMode=menuEdges!=nil;
            if(menuEdges.length) for(NSString *entry in [menuEdges componentsSeparatedByString:@","]) {
                NSScanner *scanner=[NSScanner scannerWithString:entry];NSInteger v;
                if(![scanner scanInteger:&v] || !scanner.isAtEnd || v<0 || v>65535){fdisbull_destroy(ctx);return 2;}
                shadowrun_menu_pressed=(unsigned int)v;shadowrun_menu_tick();
                if(!shadowrun_menu_supported){fdisbull_destroy(ctx);return 1;}
            }
            if(enterPrepared && shadowrun_menu_phase!=2U) {fprintf(stderr,"menu has not reached the initializer boundary\n");fdisbull_destroy(ctx);return 2;}
            if(menuMode && !enterPrepared && (steps || pads.length)) {fprintf(stderr,"arena input requires explicit prepared entry\n");fdisbull_destroy(ctx);return 2;}
            NSMutableArray<NSNumber *> *inputs=[NSMutableArray array];
            if(pads.length) for(NSString *entry in [pads componentsSeparatedByString:@","]) {
                NSScanner *scanner=[NSScanner scannerWithString:entry];NSInteger v;
                if(![scanner scanInteger:&v] || !scanner.isAtEnd || v<0 || v>255){fdisbull_destroy(ctx);return 2;}
                [inputs addObject:@(v)];
            }
            for(long i=0;i<steps;i++) [inputs addObject:@0];
            BOOL stopped=NO;NSUInteger completed=0;for(NSNumber *v in inputs) {if(fdisbull_step(ctx,(uint8_t)v.unsignedIntValue)){stopped=YES;break;}completed++;}
            ArenaView *view=[[ArenaView alloc] initWithFrame:NSMakeRect(0,0,960,760)];view.context=ctx;view.stopped=stopped;view.sourceMenu=menuMode&&!enterPrepared;
            NSBitmapImageRep *rep=[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:960 pixelsHigh:760 bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO colorSpaceName:NSCalibratedRGBColorSpace bytesPerRow:0 bitsPerPixel:0];
            NSGraphicsContext *bitmap=[NSGraphicsContext graphicsContextWithBitmapImageRep:rep];
            NSGraphicsContext *flipped=[NSGraphicsContext graphicsContextWithCGContext:bitmap.CGContext flipped:YES];
            [NSGraphicsContext saveGraphicsState];[NSGraphicsContext setCurrentContext:flipped];
            NSAffineTransform *transform=[NSAffineTransform transform];[transform translateXBy:0 yBy:760];[transform scaleXBy:1 yBy:-1];[transform concat];
            /* Warm the renderer before measuring the unchanged-state draws. */
            [view drawRect:view.bounds];struct timespec start,end;clock_gettime(CLOCK_MONOTONIC,&start);
            for(long i=0;i<renders;i++) { @autoreleasepool { [view drawRect:view.bounds]; } }
            clock_gettime(CLOCK_MONOTONIC,&end);[NSGraphicsContext restoreGraphicsState];
            uint64_t elapsed=(uint64_t)((int64_t)(end.tv_sec-start.tv_sec)*1000000000LL+(int64_t)(end.tv_nsec-start.tv_nsec));
            NSData *png=[rep representationUsingType:NSBitmapImageFileTypePNG properties:@{}];BOOL ok=[png writeToFile:snapshot atomically:YES];
            printf("{\"stopped\":%s,\"hp\":%lld,\"player_x\":%lld,\"player_y\":%lld,\"menu_phase\":%u,\"menu_cursor\":%u,\"arena_entered\":%s,\"arena_ticks\":%lu,\"render_iterations\":%ld,\"render_ns\":%llu}\n",stopped?"true":"false",(long long)value(ctx,"shadowrun_arena_hp",0),(long long)value(ctx,"shadowrun_player_x",0),(long long)value(ctx,"shadowrun_player_y",0),shadowrun_menu_phase,shadowrun_menu_cursor,(!menuMode||enterPrepared)?"true":"false",(unsigned long)completed,renders,(unsigned long long)elapsed);
            fdisbull_destroy(ctx);return ok?0:1;
        }
        ArenaController *controller=[ArenaController new];controller.context=ctx;NSApp.delegate=controller;
        [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];[NSApp run];fdisbull_destroy(ctx);return 0;
    }
}
