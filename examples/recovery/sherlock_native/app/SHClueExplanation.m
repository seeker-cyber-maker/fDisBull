#import "SHClueExplanation.h"

static void SHExplanationText(NSString *text, NSRect rect, CGFloat size,
                              NSFontWeight weight, BOOL centered,
                              NSColor *color) {
    NSMutableParagraphStyle *paragraph = [[NSMutableParagraphStyle alloc] init];
    paragraph.alignment = centered ? NSTextAlignmentCenter : NSTextAlignmentLeft;
    paragraph.lineBreakMode = NSLineBreakByWordWrapping;
    [text drawInRect:rect withAttributes:@{
        NSFontAttributeName:[NSFont systemFontOfSize:size weight:weight],
        NSForegroundColorAttributeName:color,
        NSParagraphStyleAttributeName:paragraph
    }];
}

BOOL SHDrawClueExplanation(const SherlockPuzzle *puzzle, unsigned clueIndex,
                           NSArray<NSImage *> *fullTiles, NSPoint origin) {
    SHClueExplanation explanation;
    if (sh_explain_clue(puzzle, clueIndex, &explanation) != 0) return NO;

    [NSGraphicsContext saveGraphicsState];
    NSRect panel = NSMakeRect(origin.x, origin.y,
                              SH_CLUE_EXPLANATION_WIDTH, SH_CLUE_EXPLANATION_HEIGHT);
    NSRectClip(panel);
    [NSColor.windowBackgroundColor setFill]; NSRectFill(panel);
    [NSColor.labelColor setStroke];
    NSBezierPath *border = [NSBezierPath bezierPathWithRect:NSInsetRect(panel, .5, .5)];
    border.lineWidth = 1; [border stroke];
    NSGraphicsContext.currentContext.imageInterpolation = NSImageInterpolationNone;

    SHExplanationText([NSString stringWithUTF8String:explanation.title],
        NSMakeRect(origin.x + 12, origin.y + 10, 266, 19), 13,
        NSFontWeightSemibold, YES, NSColor.labelColor);
    [NSColor.separatorColor setFill];
    NSRectFill(NSMakeRect(origin.x + 12, origin.y + 35, 266, 1));

    CGFloat stride = 266.0 / explanation.arity;
    for (unsigned i = 0; i < explanation.arity; ++i) {
        unsigned object = explanation.objects[i];
        CGFloat center = origin.x + 12 + stride * (i + .5);
        SHExplanationText([NSString stringWithFormat:@"%c", 'A' + (int)i],
            NSMakeRect(center - 20, origin.y + 42, 40, 15), 11,
            NSFontWeightSemibold, YES, NSColor.labelColor);
        NSRect tile = NSMakeRect(center - 16, origin.y + 62, 32, 32);
        NSImage *image = object < fullTiles.count ? fullTiles[object] : nil;
        if ([image isKindOfClass:NSImage.class]) {
            [image drawInRect:tile fromRect:NSZeroRect
                operation:NSCompositingOperationCopy fraction:1
                respectFlipped:YES hints:nil];
        } else {
            [NSColor.controlBackgroundColor setFill]; NSRectFill(tile);
            SHExplanationText([NSString stringWithFormat:@"%u", object],
                NSInsetRect(tile, 1, 8), 11, NSFontWeightRegular,
                YES, NSColor.labelColor);
        }
        SHExplanationText([NSString stringWithFormat:@"Row %u · Item %u",
                            object / SHERLOCK_COLUMNS + 1,
                            object % SHERLOCK_COLUMNS + 1],
            NSMakeRect(center - stride / 2, origin.y + 98, stride, 13), 8,
            NSFontWeightRegular, YES, NSColor.secondaryLabelColor);
    }

    SHExplanationText([NSString stringWithUTF8String:explanation.rule],
        NSMakeRect(origin.x + 12, origin.y + 120, 266, 65), 11,
        NSFontWeightRegular, NO, NSColor.labelColor);
    [NSColor.separatorColor setFill];
    NSRectFill(NSMakeRect(origin.x + 12, origin.y + 189, 266, 1));
    SHExplanationText(@"No hint penalty. The clock keeps running.",
        NSMakeRect(origin.x + 12, origin.y + 195, 266, 13), 8.5,
        NSFontWeightRegular, YES, NSColor.secondaryLabelColor);
    SHExplanationText(@"Click to close",
        NSMakeRect(origin.x + 12, origin.y + 213, 266, 13), 9,
        NSFontWeightSemibold, YES, NSColor.labelColor);
    [NSGraphicsContext restoreGraphicsState];
    return YES;
}
