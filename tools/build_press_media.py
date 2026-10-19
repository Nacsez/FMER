"""Render first-party release media from exact existing FMER screenshots.

No network, firmware, MIDI or user-library access. Requires the reviewed guide
export and a local Chromium browser. Original image bytes are never edited.
"""
from pathlib import Path
import argparse,base64,hashlib,html,json,shutil
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parents[1]
H=R/'host/help'
M=R/'docs/release/media'

def image(name):
    p=R/'FMER SPLASH.png' if name=='logo' else H/name
    return 'data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode()

def build(kit,chrome):
    M.mkdir(parents=True,exist_ok=True)
    guide=json.loads((R/'docs/help/feature-plates.json').read_text())
    proof=json.loads((kit/'manifest.json').read_text())
    for entry in guide['features']:
        filename=Path(entry['file']).with_suffix('.png').name
        path=kit/'PNG'/filename
        assert hashlib.sha256(path.read_bytes()).hexdigest()==proof['files']['PNG/'+filename]
        assert (kit/'SVG'/entry['file']).read_bytes()==(H/entry['file']).read_bytes()
        shutil.copy2(path,M/filename)
    shutil.copy2(R/'FMER SPLASH.png',M/'fmer-splash.png')
    for source,dest in [('FMER 734 Visual Guide.pdf','FMER-734-Visual-Guide.pdf'),('FMER 734 Shortcuts.pdf','FMER-734-Shortcuts.pdf')]:
        shutil.copy2(kit/source,M/dest)
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
<rect width="1280" height="720" fill="#070709"/>
<image href="{image('logo')}" x="54" y="35" width="170" height="170" style="image-rendering:pixelated"/>
<g font-family="Arial, sans-serif" fill="#f5f7fa">
<text x="260" y="82" fill="#76ff53" font-size="24" letter-spacing="4">FMER / BUILD 734</text>
<text x="260" y="142" font-size="48" font-weight="bold">FM + VIRTUAL ANALOG</text>
<text x="260" y="184" font-size="25">Sound design. Patterns. Four-track performance.</text>
<path d="M54 235 H1226" stroke="#ff78d4" stroke-width="3"/>
<text x="54" y="279" font-size="21" fill="#76ff53">SIX OPERATORS</text>
<text x="464" y="279" font-size="21" fill="#76ff53">FOUR PARTS</text>
<text x="874" y="279" font-size="21" fill="#76ff53">YOUR ARRANGEMENT</text>
<image href="{image('panel-algorithm-5.png')}" x="54" y="300" width="312" height="312" style="image-rendering:pixelated"/>
<image href="{image('guide-home-4t.png')}" x="464" y="300" width="312" height="312" style="image-rendering:pixelated"/>
<image href="{image('guide-seq-8.png')}" x="874" y="300" width="312" height="312" style="image-rendering:pixelated"/>
<text x="54" y="661" font-size="23">Alternative firmware for M-VAVE FM-1 · Offline Windows Companion</text>
<text x="54" y="695" font-size="16" fill="#b6bcc8">Production-rendered screens with illustrative musical state · github.com/Nacsez/FMER</text>
</g></svg>'''
    (M/'fmer-overview.svg').write_text(svg,encoding='utf8')
    paragraphs=[
      ('Two synthesis engines','Six-operator FM, 32 algorithm diagrams and DX7-style interchange. Virtual Analog with sine, saw, square, triangle and noise.'),
      ('Three ways to play','1V glide, 4V polyphony or four mono parts in 4T. Four simultaneous voices total.'),
      ('128 instrument slots','64 editable defaults and 64 independent user sounds. Either engine in either bank; original defaults start with 32 FM and 32 VA.'),
      ('Six reorderable effects','Filter, reverb, delay, chorus, phaser and drive. Four reverb models, beat-synced delay and stored personal routing. LFO modulation stays with the sound.'),
      ('Arpeggios into patterns','11 types including Strum. Latch, octave range, triplets, gate and swing. Record the generated notes into a pattern.'),
      ('A portable arrangement','16 projects; 16 patterns per project, up to 64 steps each. Four song lanes with 32 entries per lane, repeats and transpose. Single-instrument sequencing too.')]
    cards=''.join('<article><h2>'+a+'</h2><p>'+b+'</p></article>' for a,b in paragraphs)
    brochure='''<!doctype html><html lang="en"><meta charset="utf-8"><title>FMER 734 feature overview</title>
<style>@page{size:A4;margin:0}*{box-sizing:border-box}body{margin:0;background:#070709;color:#f5f7fa;font:12pt/1.45 Arial,sans-serif}section{padding:12mm 15mm;height:297mm;overflow:hidden;break-after:page}section:last-child{break-after:auto}h1{font-size:24pt;color:#76ff53;margin:0 0 6mm}h2{font-size:14pt;color:#76ff53;margin:0 0 2mm}p{margin:0 0 4mm}.hero{width:180mm;display:block;margin:0 0 6mm}.grid{display:grid;grid-template-columns:1fr 1fr;gap:5mm}article{border-top:1mm solid #ff78d4;padding:3mm 0 0}small{font-size:9pt;color:#b6bcc8}.app{width:180mm;max-height:105mm;object-fit:contain;margin:3mm 0 6mm}ol{padding-left:6mm}li{margin-bottom:2mm}.foot{margin-top:6mm;border-top:1px solid #727684;padding-top:4mm}</style>
<section><img class="hero" src="fmer-overview.png" alt="FMER and three actual software screens"><div class="grid">'''+cards+'''</div><p class="foot"><strong>Hands-on performance:</strong> per-track level, mute, solo, FX routing, patch, pattern and run state. Next-bar launches, live waveform views and panel shortcuts.</p><small>Build 734 · pre-1.0 · github.com/Nacsez/FMER<br>Screens use the production renderer with illustrative data, not physical LCD photography.</small></section>
<section><h1>Your sounds. Your instrument.</h1><p>FMER Companion organizes instruments, projects and backups on your own computer. The portable Windows package includes the runtime, installer, firmware, default library and illustrated offline handbook.</p><img class="app" src="../../../host/help/app-library.png" alt="Actual FMER Companion library"><div class="grid"><article><h2>Local from the start</h2><ol><li>Extract the complete Windows ZIP.</li><li>Launch FMER Companion.exe.</li><li>Connect one FM-1 and check connection.</li><li>Back up, then inspect and install firmware.</li></ol></article><article><h2>Wired into your setup</h2><p>USB MIDI notes, clock and documented controls. Split or merge outgoing track channels. Direct USB links pair two powered FMER units. TRS MIDI accepts input.</p></article></div><p class="foot"><strong>Scope:</strong> Windows 10/11 x64. Shared effects; combined USB audio, no separate stems. Battery percentage is estimated. Bluetooth and macOS/Linux binaries are deferred. Compatibility checks protect supported layouts; unknown layouts cannot be forced.</p><p>Original FMER code, defaults and splash: GPL-3.0-only. Board support: Felucca. FM foundation: MSFA. Updater foundation: SLOOP. See the included notices.</p><small>Read the release notes and handbook limits before installing. Report your experience through GitHub issues; diagnostic sharing is optional. Outside code contributions require maintainer permission.</small></section></html>'''
    (M/'feature-overview.html').write_text(brochure,encoding='utf8')
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=chrome,headless=True)
        page=browser.new_page(viewport={'width':1280,'height':720},device_scale_factor=1)
        page.goto((M/'fmer-overview.svg').as_uri());page.locator('svg').screenshot(path=str(M/'fmer-overview.png'))
        page.goto((M/'feature-overview.html').as_uri());page.wait_for_function('Array.from(document.images).every(i=>i.complete && i.naturalWidth>0)')
        overflow=page.evaluate('Array.from(document.querySelectorAll("section")).map(e=>e.scrollHeight-e.clientHeight)')
        assert all(x<=1 for x in overflow),overflow
        page.pdf(path=str(M/'FMER-734-Feature-Overview.pdf'),prefer_css_page_size=True,print_background=True)
        browser.close()
    features=['# FMER 734: feature tour\n','Production-rendered firmware screens and isolated Companion captures. Musical states and waveforms are illustrative. Pink pointers identify controls; the underlying screens are unchanged. Download the PDFs or open the offline handbook for workflows and the complete parameter reference.\n']
    for e in guide['features']:
        features += ['## '+e['title']+'\n',e['summary']+'\n','!['+e['title']+'](media/'+Path(e['file']).with_suffix('.png').name+')\n']
    (R/'docs/release/FEATURES.md').write_text('\n'.join(features),encoding='utf8')
    manifest=dict(firmware=734,scope=guide['capture_scope'],logo_source_sha256=hashlib.sha256((R/'FMER SPLASH.png').read_bytes()).hexdigest(),
      generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(M.iterdir()) if p.is_file() and p.name!='manifest.json'})
    (M/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(files=len(manifest['files']),sections=2,overflow=overflow)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--guide-kit',type=Path,required=True);p.add_argument('--chrome',default='C:/Program Files/Google/Chrome/Application/chrome.exe');a=p.parse_args();build(a.guide_kit,a.chrome)
