"""Compare authored rendering fixtures with a hash-pinned upstream draw routine.

The upstream file is supplied separately; it is never downloaded or bundled by
this test. Its lockFocus transport is replaced with an explicit bitmap context
so 1x/2x/3x comparisons use equal backing scales. Drawing expressions, layout,
theme lookup and font selection stay untouched. No menu app is launched.
"""
from pathlib import Path
import argparse
import hashlib
import json
import plistlib
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_SHA = 'aef57f386d664e392b5cfab683b5dbf28dfdbfb124ae19d03c3ea17fbb391a10'

SWIFT = r'''
import AppKit

final class Cpuinfo {
    var values: [Double] = []
    var overall: Double = 0
    func getCoreCount() -> UInt { UInt(values.count) }
    func getCoreUsageAt(_ index: UInt) -> Double { values[Int(index)] }
    func getHostUsage() -> Double { overall }
}

@main struct OracleComparison {
    @MainActor static func main() throws {
        NSApplication.shared.setActivationPolicy(.prohibited)
        var comparisons = [[String: Any]]()
        let values: [Double] = [0,0.1,0.5,0.7499,0.75,0.8999,0.9,1,0.2,0.6]
        let sampler = Cpuinfo(); sampler.values = values
        func pixels(_ bitmap: NSBitmapImageRep) -> [UInt8] {
            let bytes = bitmap.bitmapData!
            return (0..<bitmap.pixelsHigh).flatMap { row in
                Array(UnsafeBufferPointer(start: bytes + row * bitmap.bytesPerRow,
                                          count: bitmap.pixelsWide * 4))
            }
        }
        for scale in [1.0,2,3] {
            for dark in [false,true] {
                for theme in ["Default","B/W"] {
                    for mode in ["cores","image","text","image-text"] {
                        for usage in [0.0,0.1234,0.7499,0.75,0.8999,0.9,1] {
                            sampler.overall = usage
                            let reference = CpuinfoImage()
                            reference.setCpuinfo(sampler)
                            reference.oracleScale = scale
                            reference.darkMode = dark; reference.theme = theme
                            reference.imageEnabled = mode == "image" || mode == "image-text"
                            reference.textEnabled = mode == "text" || mode == "image-text"
                            reference.multiCoreEnabled = mode == "cores"
                            reference.update()
                            var options = DisplayOptions()
                            options.showCoresIndividually = mode == "cores"
                            options.showImage = reference.imageEnabled
                            options.showText = reference.textEnabled
                            options.theme = theme
                            let sample = CPUSample(capturedAt: "authored", overall: usage,
                                cores: values.map { Optional($0) }, error: nil)
                            let candidate = MeterRenderer.image(sample: sample, options: options,
                                                                dark: dark, scale: scale)
                            let original = reference.representations[0] as! NSBitmapImageRep
                            let replica = candidate.representations[0] as! NSBitmapImageRep
                            let left = pixels(original); let right = pixels(replica)
                            let sameSize = reference.size == candidate.size &&
                                original.pixelsWide == replica.pixelsWide && original.pixelsHigh == replica.pixelsHigh
                            let mismatch = left.count == right.count ? zip(left,right).filter { $0 != $1 }.count : -1
                            comparisons.append(["scale":scale, "dark":dark, "theme":theme,
                                "mode":mode,"usage":usage,"logical_width":reference.size.width,
                                "same_size":sameSize,"differing_channels":mismatch])
                        }
                    }
                }
            }
        }
        let font = NSFont.menuBarFont(ofSize: NSFont.systemFontSize)
        let palette = [MeterColor.green,.orange,.red].map { value -> [String:Any] in
            let color = MeterRenderer.color(value,dark:true).usingColorSpace(.deviceRGB)!
            return ["name":value.rawValue,"rgba":[color.redComponent,color.greenComponent,color.blueComponent,color.alphaComponent]]
        }
        let result: [String:Any] = ["comparisons":comparisons,"device_palette":palette,
            "font":["name":font.fontName,"family":font.familyName ?? "", "size":font.pointSize,
                    "ascender":font.ascender,"descender":font.descender,"leading":font.leading],
            "menu_created":false,"preferences_accessed":false,
            "scope":"authored static frames; upstream bitmap-context instrumentation; no original process pixels"]
        print(String(data:try JSONSerialization.data(withJSONObject:result,options:[.sortedKeys]),encoding:.utf8)!)
    }
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', required=True, type=Path, help='pinned CpuinfoImage.swift')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    source = args.upstream.read_bytes()
    assert hashlib.sha256(source).hexdigest() == UPSTREAM_SHA, 'unexpected upstream source'
    text = source.decode('utf-8')
    assert text.count('    lockFocus()') == 1 and text.count('    unlockFocus()') == 1
    text = text.replace('  var darkMode = false', '  var oracleScale: Double = 1\n  var darkMode = false')
    text = text.replace('    lockFocus()', '''    let oracleBitmap = NSBitmapImageRep(bitmapDataPlanes: nil,
      pixelsWide: Int(ceil(size.width * oracleScale)), pixelsHigh: Int(ceil(size.height * oracleScale)),
      bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
      colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    oracleBitmap.size = size
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: oracleBitmap)!''')
    text = text.replace('    unlockFocus()', '''    NSGraphicsContext.restoreGraphicsState()
    for representation in representations { removeRepresentation(representation) }
    addRepresentation(oracleBitmap)''')
    tracked = ['Sources/CPUCore.swift','Sources/MeterRenderer.swift']
    before = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in tracked}
    with tempfile.TemporaryDirectory(prefix='cpuinfo-upstream-render-') as temporary:
        work = Path(temporary)
        app = work/'Renderer Oracle.app'/'Contents'
        binary = app/'MacOS'/'oracle'
        binary.parent.mkdir(parents=True)
        themes = []
        for name in ['Default','B/W']:
            theme = {'name':name}
            for appearance in ['dark','light']:
                monochrome = 'FFFFFFFF' if appearance == 'dark' else '000000FF'
                theme[appearance] = {'BAR_WIDTH':24,
                    'BAR_NORMALCOLOR':'00FF00FF' if name == 'Default' else monochrome,
                    'BAR_MEDIUMCOLOR':'FF8C00FF' if name == 'Default' else monochrome,
                    'BAR_HIGHCOLOR':'FF0000FF' if name == 'Default' else monochrome,
                    'TEXT_NORMALCOLOR':monochrome,'TEXT_MEDIUMCOLOR':monochrome,'TEXT_HIGHCOLOR':monochrome}
            themes.append(theme)
        (app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable':'oracle','theme':themes}))
        (work/'Reference.swift').write_text(text)
        (work/'Comparison.swift').write_text(SWIFT)
        subprocess.run(['/usr/bin/xcrun','swiftc','-parse-as-library','-target',
            subprocess.check_output(['uname','-m'],text=True).strip()+'-apple-macosx14.0',
            str(ROOT/'Sources/CPUCore.swift'),str(ROOT/'Sources/MeterRenderer.swift'),
            str(work/'Reference.swift'),str(work/'Comparison.swift'),'-framework','AppKit','-o',str(binary)],check=True)
        result = subprocess.run([str(binary)],capture_output=True,text=True,check=True,timeout=45)
        report = json.loads(result.stdout)
    after = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in tracked}
    assert before == after, 'candidate changed during comparison'
    report.update(upstream_sha256=UPSTREAM_SHA,
        upstream_revision='d7f9e846909f9775e1d6d03214796dbaff4d5492',candidate_sources=before)
    failures = [row for row in report['comparisons'] if not row['same_size'] or row['differing_channels']]
    report['passed'] = not failures
    report['comparison_count'] = len(report['comparisons'])
    with args.output.open('x') as output:
        json.dump(report,output,indent=2);output.write('\n')
    print(json.dumps({'comparisons':len(report['comparisons']),'mismatches':len(failures),'font':report['font']}))
    if failures:
        print(json.dumps(failures[:12],indent=2))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
