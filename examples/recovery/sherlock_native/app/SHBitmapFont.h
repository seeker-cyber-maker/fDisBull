#import <Cocoa/Cocoa.h>

/* Small canvas text uses the owner's recovered pixel font. Native controls,
 * large headings, Unicode names and a source checkout without the private
 * resource retain an ordinary AppKit font. */
BOOL SHBitmapFontIsAvailable(void);
void SHDrawBitmapText(NSString *text, NSRect rect, CGFloat size,
                       NSColor *color, BOOL centered, NSColor *shadow);
