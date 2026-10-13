# Social preview images (1200x630) for each page: python tools/og.py   (needs Pillow; fonts from Windows)
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = 'C:/Windows/Fonts/'
BG, INK, INK2, SCAN, SEARCH = '#141412', '#f0efec', '#c3c2b7', '#d95926', '#3987e5'

PAGES = [
    # (output, title lines, slow stat, fast stat)
    ('og.png', ['Developer concepts,', 'with numbers you can reproduce'],
     ('lab', 'runnable code'), ('sources', 'primary docs only')),
    ('indexes/og.png', ['Database indexes,', 'measured'],
     ('64.2 ms', 'find one email, no index'), ('0.0031 ms', 'same query, index on email')),
    ('n-plus-one/og.png', ['The N+1 query problem,', 'measured'],
     ('266 ms', 'N+1: 1,001 queries'), ('29.5 ms', 'one JOIN: 1 query')),
    ('retries/og.png', ['Retries, measured:', 'why backoff needs jitter'],
     ('3.3 s', 'last client served, backoff'), ('0.46 s', 'last client served, with jitter')),
    ('pagination/og.png', ['Pagination, measured:', 'OFFSET vs keyset'],
     ('26.8 ms', 'last page, OFFSET'), ('0.022 ms', 'last page, keyset')),
    ('batching/og.png', ['Batching writes,', 'measured'],
     ('25.2 s', '10,000 inserts, a commit per row'), ('23.6 ms', 'same inserts, one transaction')),
    ('queueing/og.png', ['Queues, measured:', 'why latency explodes'],
     ('554 ms', 'p99 at 90% load'), ('109 ms', 'p99 at 50% load, same server')),
]

def font(name, size):
    return ImageFont.truetype(FONTS + name, size)

for out, title, slow, fast in PAGES:
    img = Image.new('RGB', (1200, 630), BG)
    d = ImageDraw.Draw(img)
    d.text((72, 60), 'MEASURED', font=font('segoeuib.ttf', 30), fill=INK)
    d.text((72 + d.textlength('MEASURED', font=font('segoeuib.ttf', 30)), 60), '.', font=font('segoeuib.ttf', 30), fill=SEARCH)
    y = 140
    for line in title:
        d.text((72, y), line, font=font('segoeuib.ttf', 64), fill=INK)
        y += 80
    for i, ((value, label), color) in enumerate([(slow, SCAN), (fast, SEARCH)]):
        x = 72 + i * 540
        d.rectangle([x, 400, x + 500, 406], fill=color)
        d.text((x, 420), value, font=font('segoeuib.ttf', 56), fill=INK)
        d.text((x, 495), label, font=font('segoeui.ttf', 28), fill=INK2)
    d.text((72, 572), 'tuhuudev.github.io/measured', font=font('consola.ttf', 24), fill=INK2)
    path = os.path.join(ROOT, out)
    img.save(path, optimize=True)
    print(path, os.path.getsize(path))
