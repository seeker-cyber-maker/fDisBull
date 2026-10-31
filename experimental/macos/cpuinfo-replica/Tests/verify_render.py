"""Check authored pixels and Mach observation without creating a status item."""
from pathlib import Path
import json
import subprocess
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'build/Cpuinfo Replica.app/Contents/MacOS/CpuinfoReplica'
checks = 0

def check(condition, label):
    global checks
    assert condition, label
    checks += 1

with tempfile.TemporaryDirectory(prefix='cpuinfo-replica-render-') as temporary:
    for scale in (1, 2, 3):
        path = Path(temporary) / f'bars-{scale}.png'
        result = subprocess.run([str(APP), '--fixture', str(ROOT / 'Tests/bars.fixture.json'),
                                 '--output', str(path), '--scale', str(scale)],
                                capture_output=True, text=True, check=True, timeout=15)
        report = json.loads(result.stdout)
        check(report['menu_created'] is False and report['preferences_accessed'] is False,
              'fixture must bypass app lifecycle')
        image = Image.open(path).convert('RGBA')
        check(image.size == (52 * scale, 24 * scale), 'logical size/backing pixels')
        check(image.getbbox() == (2 * scale, 5 * scale, 50 * scale, 19 * scale), 'track geometry including negative-space edges')
        check(image.getpixel((3 * scale, 17 * scale))[:3] == (0, 255, 0), 'zero minimum nub remains green')
        check(image.getpixel((23 * scale, 16 * scale))[:3] == (255, 140, 0), '75 percent orange')
        check(image.getpixel((33 * scale, 16 * scale))[:3] == (255, 0, 0), '90 percent red')
        unknown = image.getpixel((43 * scale, 16 * scale))
        check(unknown[3] < 80 and unknown[:3] == (255, 255, 255), 'unknown has only a neutral track')

result = subprocess.run([str(APP), '--diagnostic', '--sample-count', '2', '--interval-ms', '100'],
                        capture_output=True, text=True, check=True, timeout=15)
samples = json.loads(result.stdout)
check(len(samples) == 2 and len(samples[0]['cores']) > 0, 'native Mach samples')
check(all(value is None for value in samples[0]['cores']), 'initial baseline unknown')
check(samples[0]['overall'] is None, 'overall initial baseline unknown')
check(len(samples[1]['cores']) == len(samples[0]['cores']), 'stable topology')
check(all(value is not None and 0 <= value <= 1 for value in samples[1]['cores']), 'finite native interval ratios')
print(f'{checks} render/native checks passed; no status item, preferences, login or external app actions')
