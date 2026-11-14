#import <Cocoa/Cocoa.h>

/* The DOS sequencer had one PC-speaker voice: a new cue replaced the old one.
 * The PCM assets retain recovered PIT-divisor/tick sequences. Native device
 * mixing and first-tick phase are explicit adaptations; see audio-recovery. */
void SHPlaySound(NSString *name, BOOL enabled) {
    static NSMutableDictionary<NSString *, NSSound *> *sounds;
    static NSSound *current;
    if (!enabled) { [current stop]; current = nil; return; }
    if (!name.length) return;
    if (!sounds) sounds = [NSMutableDictionary dictionary];
    NSSound *sound = sounds[name];
    if (!sound) {
        NSURL *url = [NSBundle.mainBundle URLForResource:name
                                         withExtension:@"wav" subdirectory:@"Sounds"];
        if (url) sound = [[NSSound alloc] initWithContentsOfURL:url byReference:YES];
        if (!sound) return;
        sounds[name] = sound;
    }
    [current stop];
    current = sound;
    [current play];
}
