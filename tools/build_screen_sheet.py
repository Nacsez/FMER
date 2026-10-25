"""Build offline screen sheets from exact production-renderer captures.

No device access. Run fmer_feature_capture first. Screens retain their pixels;
labels sit outside the LCD. Public 734 media and installed help are untouched.
"""
# SPDX-License-Identifier: GPL-3.0-only
import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
import shutil
import zipfile

from build_help_illustrations import png
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
E = html.escape
BG, INK, MUTED, GREEN, PINK = '#070709', '#f5f7fa', '#b6bbc6', '#76ff53', '#ff78d4'
# Each tuple is a capture stem, caption and navigation hint, not a new screen.
GROUPS = [
    ('Play & perform', [
        ('boot', 'FMER', 'POWER ON'), ('home', 'Instrument home', 'HOME / 6V'),
        ('scope', 'Full-screen waveform', 'HOME AGAIN'), ('home-4t', 'Four-track home', 'HOME / 4T'),
        ('scope-4t', 'Four tracks + main mix', 'HOME AGAIN / 4T'), ('presets', 'Instrument banks', 'PRESETS'),
        ('save-instrument', 'Save an instrument', 'SAVE / INSTRUMENT')]),
    ('FM & Virtual Analog', [
        ('fm-edit-0', 'Operator tuning', 'EDIT / TUNE'), ('algorithm', 'Algorithm routing', 'ALGORITHM / FM'),
        ('fm-edit-4', 'Operator rates', 'EDIT / OP RATES'), ('fm-edit-5', 'Operator levels', 'EDIT / OP LEVELS'),
        ('fm-env', 'FM amplitude envelope', 'ENV / FM'), ('va-edit', 'VA oscillator + filter', 'EDIT / VA'),
        ('va-env', 'VA envelope', 'ENV / VA')]),
    ('Movement & expression', [
        ('fm-lfo-0', 'FM modulation', 'LFO / FM MODULATION'), ('fm-lfo-1', 'FM synchronization', 'LFO / FM SYNC'),
        ('va-lfo', 'VA vibrato', 'LFO / VA'), ('mono-glide', 'Mono glide', 'GLO / MONO GLIDE'),
        ('arp-0', 'Arp type + latch', 'ARP / TYPE-LATCH'), ('arp-1', 'Arp timing', 'ARP / TIMING'),
        ('glo-0', 'Playing mode + tempo', 'GLO / VOICE-TEMPO')]),
    ('Effects & routing', [
        ('filter-0', 'Low-pass filter', 'FX / FILTER-SPACE'), ('filter-1', 'High-pass filter', 'FX / ALGORITHM: HP'),
        ('filter-2', 'Band-pass filter', 'FX / ALGORITHM: BP'), ('fx-1', 'Chorus + modulation', 'FX / MODULATION'),
        ('phaser', 'Phaser profiles', 'FX / SELECT PHASER'), ('delay-sync', 'Reverb + synced delay', 'FX / SPACE SETTINGS'),
        ('fx-3', 'Reorder effects', 'FX / SIGNAL CHAIN')]),
    ('Sequence & arrange', [
        ('seq-4', 'Performance mixer', 'SEQ / PERFORM'), ('seq-8', 'Four-lane song', 'SEQ / SONG / 4T'),
        ('single-song', 'Single-instrument song', 'SEQ / SONG / 6V'), ('seq-0', 'Step editing', 'SEQ / STEP EDIT'),
        ('seq-5', 'Recording', 'SEQ / RECORD'), ('seq-6', 'Rests, ties + note moves', 'SEQ / NOTE EDIT'),
        ('seq-7', 'Copy + edit sections', 'SEQ / COPY-EDIT')]),
    ('Connect & preserve', [
        ('seq-1', 'Pattern length + tempo', 'SEQ / PATTERNS'), ('seq-2', 'Pattern chain', 'SEQ / CHAIN MEMBERS'),
        ('song-setup', 'Song playback options', 'SEQ / SONG / SETUP'), ('save-project', 'Save a project', 'SAVE / PROJECT'),
        ('glo-2', 'MIDI input', 'GLO / MIDI INPUT'), ('glo-4', 'MIDI clock', 'GLO / MIDI CLOCK'),
        ('glo-5', 'Direct USB link', 'GLO / USB LINK')]),
]
EXTRA = [
    ('fm-edit-1', 'Operator sensitivity', 'EDIT / SENSITIVITY'), ('fm-edit-2', 'Keyboard scaling', 'EDIT / KEY SCALE'),
    ('fm-edit-3', 'Scaling curves', 'EDIT / CURVE'), ('fm-edit-6', 'Pitch envelope rates', 'EDIT / PITCH RATES'),
    ('fm-edit-7', 'Pitch envelope levels', 'EDIT / PITCH LEVELS'), ('fx-0', 'Filter + space', 'FX / FILTER-SPACE'),
    ('fx-2', 'Millisecond delay', 'FX / SPACE SETTINGS'), ('glo-1', 'Glide disabled', 'GLO / MONO GLIDE'),
    ('glo-3', 'MIDI output', 'GLO / MIDI OUTPUT'), ('glo-6', 'Header icon legend', 'GLO / ICON LEGEND'),
    ('glo-7', 'Panel shortcuts', 'GLO / SHORTCUTS'), ('glo-8', 'System information', 'GLO / INFO'),
    ('glo-9', 'Scoped reset actions', 'GLO / RESET-CLEAR'), ('seq-3', 'Playing mode', 'SEQ / PLAY MODE'),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(x, y, value, size=26, color=INK):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}">{E(value)}</text>'


def shell(title, subtitle, width, height):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img"><title>{E(title)}</title><desc>{E(subtitle)}</desc><rect width="100%" height="100%" fill="{BG}"/><g font-family="Arial,sans-serif">',
            text(48, 70, 'FMER / ' + title, 46, GREEN), text(48, 116, subtitle, 25, MUTED),
            f'<path d="M48 142H{width-48}" stroke="{PINK}" stroke-width="2"/>']


def card(entry, x, y, size, images):
    name, title, route = entry
    data = base64.b64encode(images[name]).decode('ascii')
    return [f'<rect x="{x-1}" y="{y-1}" width="{size+2}" height="{size+2}" fill="none" stroke="#4b4e5a"/>',
            f'<image x="{x}" y="{y}" width="{size}" height="{size}" style="image-rendering:pixelated" href="data:image/png;base64,{data}"/>',
            text(x, y+size+32, title, 26), text(x, y+size+61, route, 20, GREEN)]


def finish(parts, height, width):
    parts += [f'<path d="M48 {height-68}H{width-48}" stroke="#4b4e5a"/>',
              text(48, height-30, '735 development preview / actual renderer / illustrative state', 22, MUTED), '</g></svg>']
    return ''.join(parts)


def build(captures, out, chrome):
    out = out.resolve(); out.mkdir(parents=True, exist_ok=False)
    entries = [e for _, group in GROUPS for e in group] + EXTRA
    assert len(entries) == len({e[0] for e in entries}) == 56
    available = {p.stem.removeprefix('guide-') for p in captures.glob('guide-*.ppm')}
    assert available == {e[0] for e in entries}, (available.symmetric_difference(e[0] for e in entries))
    (out/'Screens').mkdir(); images = {}
    for name, _, _ in entries:
        source = captures/f'guide-{name}.ppm'
        assert source.read_bytes().split(b'\n', 3)[1] == b'240 240'
        images[name] = png(source.read_bytes())
        (out/'Screens'/f'{name}.png').write_bytes(images[name])
    # Integer 2x LCD pixels in the poster and social cards, without retouching.
    width, height = 3600, 4000
    parts = shell('Screen atlas', 'FM + Virtual Analog / six voices / four tracks / hands-on sound design', width, height)
    for row, (title, group) in enumerate(GROUPS):
        top = 192 + row*620
        parts.append(text(48, top, f'{row+1:02d} / {title.upper()}', 28, PINK))
        for col, entry in enumerate(group):
            parts += card(entry, 48+col*504, top+22, 480, images)
    sheets = [('FMER 735 Screen Sheet', finish(parts, height, width), width, height)]
    # Four-screen 4:5 cards keep text readable in a feed. Full atlas has 42 views.
    picks = [(1, 2, 3, 4), (0, 1, 4, 5), (3, 4, 5, 6), (0, 3, 5, 6), (0, 1, 5, 6), (0, 3, 5, 6)]
    for index, ((title, group), selected) in enumerate(zip(GROUPS, picks), 1):
        parts = shell(title, '735 / FM-1 firmware / development preview', 1080, 1350)
        for n, pick in enumerate(selected):
            parts += card(group[pick], 48+(n%2)*504, 172+(n//2)*552, 480, images)
        # Social captions occupy less vertical space than poster captions.
        svg = finish(parts, 1350, 1080)
        sheets.append((f'{index:02d} {title.replace("&", "and")}', svg, 1080, 1350))
    errors = []; layout = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chrome, headless=True)
        page = browser.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        for name, svg, w, h in sheets:
            file = out/(name+'.svg'); file.write_text(svg, encoding='utf8')
            page.set_viewport_size({'width': w, 'height': h}); page.goto(file.as_uri())
            page.evaluate('document.fonts.ready')
            overflow = page.evaluate('''() => [...document.querySelectorAll('text')].filter(t => {
              const b=t.getBBox(),s=document.documentElement.viewBox.baseVal;
              return b.x<0||b.y<0||b.x+b.width>s.width||b.y+b.height>s.height;
            }).map(t=>t.textContent)''')
            layout.extend({'sheet': name, 'text': t} for t in overflow)
            page.locator('svg').screenshot(path=str(out/(name+'.png')))
        printfile = out/'print.html'
        printfile.write_text('<!doctype html><meta charset="utf-8"><style>@page{size:A3 portrait;margin:8mm}body{margin:0}img{width:100%}</style><img src="FMER 735 Screen Sheet.svg">', encoding='utf8')
        page.goto(printfile.as_uri()); page.wait_for_function('Array.from(document.images).every(i=>i.complete && i.naturalWidth>0)')
        page.pdf(path=str(out/'FMER 735 Screen Sheet.pdf'), prefer_css_page_size=True, print_background=True)
        printfile.unlink(); browser.close()
    assert not errors and not layout, (errors, layout)
    cards = ''.join(f'<article><a href="Screens/{E(n)}.png"><img src="Screens/{E(n)}.png" alt="{E(t)}"></a><h2>{E(t)}</h2><p>{E(r)}</p></article>' for n,t,r in entries)
    (out/'START HERE.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FMER735 screen atlas</title><style>body{background:#070709;color:#f5f7fa;font:18px/1.5 system-ui;margin:32px}h1,a{color:#76ff53}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:24px}img{width:240px;image-rendering:pixelated}h2{font-size:20px}article{padding:16px;border:1px solid #4b4e5a}p{color:#b6bbc6}</style><h1>FMER / Screen atlas</h1><p>Build735 development preview. These56 views use the production240×240 renderer with illustrative state. No screens were painted or redesigned for the poster. Navigation labels identify the section and named page; repeated presses depend on the current page and playing mode.</p><p><a href="FMER 735 Screen Sheet.png">42-screen overview</a> · <a href="FMER 735 Screen Sheet.pdf">A3 PDF</a></p><main>'+cards+'</main></html>', encoding='utf8')
    (out/'README.txt').write_text('FMER735 screen sheets — local development preview\n\nOpen START HERE.html for all56 exact240x240 captures. The poster contains42 representative views. Six1080x1350 PNG/SVG cards provide smaller social posts. The PDF is A3; poster text will be small on ordinary office paper. SVG files embed all images and work offline. Captures use illustrative musical state, not hardware photographs. Numeric settings are examples, not prescribed defaults. Group rows are thematic, not the panel page order. No Bluetooth capability is represented. Refresh captures and verify navigation before the next release.\n\nRebuild using tools/feature_capture.cpp and tools/build_screen_sheet.py. GPL-3.0-only; see LICENSE. No third-party reference image is redistributed.\n', encoding='utf8')
    shutil.copy2(ROOT/'LICENSE', out/'LICENSE')
    manifest = dict(build=735, channel='local-development', views=len(entries), overview_views=42,
                    screenshots='production renderer with illustrative state', browser_errors=errors, overflow=layout,
                    sources={p:sha(ROOT/p) for p in ['firmware/fm1/ui.h','firmware/fm1/panel_model.h','tools/feature_capture.cpp','tools/build_screen_sheet.py']},
                    files={p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf8')
    with zipfile.ZipFile(out.with_suffix('.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file(): z.write(p, p.relative_to(out.parent))
    print(json.dumps(dict(output=str(out), views=len(entries), sheets=len(sheets), overflow=layout)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--captures', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--chrome', default='C:/Program Files/Google/Chrome/Application/chrome.exe')
    args = parser.parse_args(); build(args.captures, args.out, args.chrome)
