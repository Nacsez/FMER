"""Export reviewed, local FMER SVG plates to PNG/PDF; no network or hardware."""
from pathlib import Path
import argparse, hashlib, html, json, re, shutil, zipfile
from playwright.sync_api import sync_playwright

R = Path(__file__).resolve().parents[1]
H = R / 'host/help'


def prose_html(source):
    """Small local reading view; Markdown remains the editable original."""
    def inline(s):
        s=html.escape(s)
        return re.sub(r'`([^`]+)`',r'<code>\1</code>',re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',s))
    blocks=[]
    for block in source.split('\n\n'):
        rows=block.strip().splitlines()
        if not rows:continue
        if rows[0].startswith('#'):
            n=min(6,len(rows[0])-len(rows[0].lstrip('#')))
            blocks.append(f'<h{n}>'+inline(rows[0][n:].strip())+f'</h{n}>')
        elif rows[0].startswith('|'):
            cells=[]
            for row in rows:
                if re.fullmatch(r'[|:\- ]+',row):continue
                cells.append('<tr>'+''.join('<td>'+inline(x.strip())+'</td>' for x in row.strip('|').split('|'))+'</tr>')
            blocks.append('<div class="table"><table>'+''.join(cells)+'</table></div>')
        else:blocks.append('<p>'+inline('\n'.join(rows))+'</p>')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FMER / release writing</title><style>body{background:#070709;color:#f5f7fa;font:18px/1.6 system-ui;max-width:1100px;margin:32px auto;padding:20px}h1,h2,a{color:#76ff53}p{white-space:pre-line}code{color:#ff78d4}td{padding:12px;border:1px solid #727684;vertical-align:top}table{border-collapse:collapse;width:100%}.table{overflow:auto}tr:first-child{color:#76ff53}a{display:inline-block;margin-bottom:24px}</style><a href="../START HERE.html">FMER release kit</a>'+''.join(blocks)+'</html>'


def export(out, chrome):
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((R / 'docs/help/feature-plates.json').read_text())
    for folder in ('SVG', 'PNG', 'Copy'):
        (out / folder).mkdir()
    errors, layout_errors = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chrome, headless=True)
        page = browser.new_page(viewport={'width': 1800, 'height': 1400}, device_scale_factor=1)
        page.on('pageerror', lambda e: errors.append(str(e)))
        for entry in manifest['features']:
            source = H / entry['file']
            shutil.copy2(source, out / 'SVG' / source.name)
            page.goto(source.as_uri())
            page.evaluate('document.fonts.ready')
            # SVG text must remain inside its canvas, including long shortcuts.
            layout_errors.extend(page.evaluate('''() => {
                const s=document.documentElement.viewBox.baseVal;
                return [...document.querySelectorAll('text')].flatMap(t=>{
                  const b=t.getBBox();return b.x < 0 || b.y < 0 || b.x+b.width>s.width || b.y+b.height>s.height ? [t.textContent] : [];
                });
            }'''))
            page.locator('svg').screenshot(path=str(out / 'PNG' / (source.stem + '.png')))
        images = ''.join('<section><img src="'+(out/'SVG'/e['file']).as_uri()+'"></section>' for e in manifest['features'])
        style = '<style>@page{size:A4 landscape;margin:0}body{margin:0}section{height:209mm;width:297mm;break-after:page;display:flex;align-items:center;justify-content:center;background:#070709}section:last-child{break-after:auto}img{max-width:100%;max-height:100%}</style>'
        printfile = out / 'print.html'
        printfile.write_text('<!doctype html><meta charset="utf-8">'+style+images, encoding='utf8')
        page.goto(printfile.as_uri())
        page.wait_for_function('Array.from(document.images).every(i=>i.complete && i.naturalWidth>0)')
        page.pdf(path=str(out/'FMER 734 Visual Guide.pdf'), prefer_css_page_size=True, print_background=True)
        page.pdf(path=str(out/'FMER 734 Shortcuts.pdf'), prefer_css_page_size=True, print_background=True, page_ranges=str(len(manifest['features'])))
        printfile.unlink()
        browser.close()
    if errors or layout_errors:
        raise ValueError({'browser_errors': errors, 'overflow': layout_errors})
    for path in (R/'docs/release').glob('*.md'):
        shutil.copy2(path, out/'Copy'/path.name)
        (out/'Copy'/(path.stem+'.html')).write_text(prose_html(path.read_text(encoding='utf8')),encoding='utf8')
    cards=''.join('<article><h2>'+html.escape(e['title'])+'</h2><a href="SVG/'+e['file']+'"><img loading="lazy" src="PNG/'+Path(e['file']).stem+'.png" alt="'+html.escape(e['title'])+'"></a><p>'+html.escape(e['summary'])+'</p></article>' for e in manifest['features'])
    links=''.join('<li><a href="Copy/'+p.stem+'.html">'+html.escape(p.stem.replace('_', ' '))+'</a> · <a href="Copy/'+p.name+'">editable text</a></li>' for p in sorted((out/'Copy').glob('*.md')))
    (out/'START HERE.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FMER 734 / Release kit</title><style>body{background:#070709;color:#f5f7fa;font:18px/1.6 system-ui;margin:32px}main{max-width:1400px;margin:auto}h1,a{color:#76ff53}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:24px}article{padding:18px;background:#101014;border:1px solid #444}img{width:100%}</style><main><h1>FMER / 734 release kit</h1><p>Annotated production screens, workflows, writing drafts and shortcuts. Click any sheet for its full-size SVG. PNG copies are in the PNG folder.</p><p><a href="FMER 734 Visual Guide.pdf">Printable visual guide</a> · <a href="FMER 734 Shortcuts.pdf">One-page shortcut sheet</a></p><ul>'+links+'</ul><section>'+cards+'</section></main></html>',encoding='utf8')
    (out/'README.txt').write_text('FMER 734 visual release kit\n\nOpen START HERE.html. All files work offline. SVG embeds the exact captured image bytes; PNG and PDF exports use those same sheets. Hardware frames use the production renderer with illustrative data; Companion frames use an isolated library. They are not hardware photographs or new audio/transport qualification. Source and provenance: tools/feature_capture.cpp, tools/build_release_media.py, docs/help/feature-plates.json. Copy is a draft for owner review. No public upload has occurred. No new firmware build is represented by this kit.\n',encoding='utf8')
    shutil.copy2(R/'LICENSE', out/'LICENSE')
    manifest.update(files={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}, browser_errors=errors, layout_errors=layout_errors)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(out.with_suffix('.zip'),'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(out.parent))
    print(json.dumps({'out':str(out),'plates':len(manifest['features']),'errors':errors,'layout_errors':layout_errors}))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--chrome',default='C:/Program Files/Google/Chrome/Application/chrome.exe')
    args=p.parse_args();export(args.out,args.chrome)
