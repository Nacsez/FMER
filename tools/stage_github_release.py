"""Create a verified local draft-release asset set. Never uploads or publishes."""
from pathlib import Path
import argparse,hashlib,html,json,shutil,zipfile
import release_firmware as release
from export_release_media import prose_html
R=Path(__file__).resolve().parents[1]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,data):p.write_text(json.dumps(data,indent=2)+'\n',encoding='utf8')

def companion_revision(path):
    with zipfile.ZipFile(path) as z:
        roots={n.split('/')[0] for n in z.namelist()}
        if len(roots)!=1:raise ValueError('One portable root required')
        value=json.loads(z.read(next(iter(roots))+'/manifest.json')).get('companion_revision')
        if type(value) is not int or value<1:raise ValueError('Explicit Companion revision required')
        return value

def verify_companion(path,rehearsal):
    proof=json.loads(rehearsal.read_text())
    if proof.get('status')!='passed' or proof.get('zip_sha256')!=sha(path):
        raise ValueError('Passing deployment rehearsal must identify this exact Companion ZIP')
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if any(Path(n).is_absolute() or '..' in Path(n).parts for n in names):raise ValueError('Unsafe ZIP path')
        roots={n.split('/')[0] for n in names}
        if len(roots)!=1:raise ValueError('One portable root required')
        root=next(iter(roots))+'/'
        manifest=json.loads(z.read(root+'manifest.json'))
        expected={root+n for n in manifest['files']}|{root+'manifest.json'}
        if {n for n in names if not n.endswith('/')}!=expected:raise ValueError('Companion manifest closure differs')
        for n,h in manifest['files'].items():
            if hashlib.sha256(z.read(root+n)).hexdigest()!=h:raise ValueError('Companion file changed: '+n)
        catalog=json.loads(z.read(root+release.CATALOG))
        if catalog!=json.loads((R/release.CATALOG).read_text()):raise ValueError('Bundled release catalog differs')
        record=release.catalog()[0];raw=release.bundled(record['id'])
        if z.read(root+'firmware/releases/'+record['filename'])!=raw:raise ValueError('Standalone and bundled firmware differ')
        # Source must describe exactly the runtime code we are distributing.
        import io
        with zipfile.ZipFile(io.BytesIO(z.read(root+'Corresponding Source.zip'))) as source:
            for n in manifest['files']:
                if n.startswith('tools/') or n.startswith('host/'):
                    if source.read(n)!=z.read(root+n):raise ValueError('Runtime/source mismatch: '+n)
            if source.read('FMER SPLASH.png')!=(R/'FMER SPLASH.png').read_bytes():raise ValueError('Artwork source differs')
    return record

def press_pack(out):
    folder=out/'press';folder.mkdir()
    for name in ('Logo','Screenshots','Infographics/PNG','Infographics/SVG','PDF','Copy'):(folder/name).mkdir(parents=True)
    media=R/'docs/release/media'
    for name in ('fmer-splash.png','fmer-overview.png','fmer-overview.svg'):shutil.copy2(media/name,folder/'Logo'/name)
    guide=json.loads((R/'docs/help/feature-plates.json').read_text())
    for name,h in guide['source_images'].items():
        p=R/'host/help'/name
        if sha(p)!=h:raise ValueError('Screenshot changed: '+name)
        shutil.copy2(p,folder/'Screenshots'/name)
    dump(folder/'Screenshots/captions.json',dict(scope=guide['capture_scope'],features=guide['features']))
    for e in guide['features']:
        shutil.copy2(R/'host/help'/e['file'],folder/'Infographics/SVG'/e['file'])
        name=Path(e['file']).with_suffix('.png').name
        shutil.copy2(media/name,folder/'Infographics/PNG'/name)
    for p in media.glob('*.pdf'):shutil.copy2(p,folder/'PDF'/p.name)
    for name in ('MARKETING_COPY.md','VIDEO_SCRIPTS.md','ARTWORK.md','INSTALLATION.md','RELEASE_NOTES_734.md','COMPANION_R3.md','COMPANION_R4.md','COMPANION_R5_QA.md'):
        p=R/'docs/release'/name;shutil.copy2(p,folder/'Copy'/name)
        (folder/'Copy'/(p.stem+'.html')).write_text(prose_html(p.read_text(encoding='utf8')),encoding='utf8')
    for name in ('LICENSE','LICENSING.md','NOTICE'):shutil.copy2(R/name,folder/name)
    gallery=''.join('<article><h2>'+html.escape(e['title'])+'</h2><a href="Infographics/SVG/'+e['file']+'"><img loading="lazy" alt="'+html.escape(e['title'])+'" src="Infographics/PNG/'+Path(e['file']).with_suffix('.png').name+'"></a><p>'+html.escape(e['summary'])+'</p></article>' for e in guide['features'])
    links=''.join('<li><a href="PDF/'+p.name+'">'+p.stem+'</a></li>' for p in sorted((folder/'PDF').glob('*.pdf')))
    links+=''.join('<li><a href="Copy/'+p.name+'">'+p.stem.replace('_',' ')+'</a></li>' for p in sorted((folder/'Copy').glob('*.html')))
    (folder/'START HERE.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>FMER 734 press pack</title><style>body{margin:30px;background:#070709;color:#f5f7fa;font:18px/1.5 system-ui}main{max-width:1400px;margin:auto}h1,h2,a{color:#76ff53}.hero{max-width:100%}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:24px}article{padding:18px;background:#101014;border:1px solid #727684}article img{width:100%}</style><main><h1>FMER / 734 press pack</h1><img class="hero" src="Logo/fmer-overview.png" alt="FMER overview"><p>Original logo, exact software captures, annotated feature sheets, workflows and writing. All content opens locally. The screenshot fixtures are illustrative, not physical LCD photographs or audio measurements.</p><ul>'+links+'</ul><section>'+gallery+'</section></main></html>',encoding='utf8')
    (folder/'README.txt').write_text('Open START HERE.html. Logo contains the unchanged owner-approved PNG and overview SVG/PNG. Screenshots contains original software captures; captions.json describes their scope. Infographics contains editable SVGs and PNG exports; PDF contains the overview, complete visual manual and shortcuts. Copy contains release copy and video scripts. Original FMER artwork/text: GPL-3.0-only; retain notices. Full code/generators are in the matching FMER-734-Source.zip release asset. No private unit photos, recordings or vendor patch banks are included.\n',encoding='utf8')
    dump(folder/'manifest.json',dict(firmware=734,files={p.relative_to(folder).as_posix():sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}))
    with zipfile.ZipFile(out/'FMER-734-Press-Pack.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file():z.write(p,'FMER-734-Press-Pack/'+p.relative_to(folder).as_posix())

def stage(out,companion,source,rehearsal):
    record=verify_companion(companion,rehearsal)
    revision=companion_revision(companion)
    with zipfile.ZipFile(source) as z:
        manifest=json.loads(z.read('SOURCE_MANIFEST.json'))
        if set(z.namelist())!=set(manifest['files'])|{'SOURCE_MANIFEST.json'}:
            raise ValueError('Source archive closure differs')
        for n,h in manifest['files'].items():
            if hashlib.sha256(z.read(n)).hexdigest()!=h:raise ValueError('Source manifest differs: '+n)
        with zipfile.ZipFile(companion) as app:
            root=app.namelist()[0].split('/')[0]+'/'
            files=json.loads(app.read(root+'manifest.json'))['files']
            for n in files:
                if n.startswith(('tools/','host/','third_party/oem_v15/')) and z.read(n)!=app.read(root+n):
                    raise ValueError('Release source/runtime mismatch: '+n)
    out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(companion,out/'FMER-Companion-734-Windows-x64.zip')
    with zipfile.ZipFile(companion) as z:
        root=z.namelist()[0].split('/')[0]+'/'
        sounds=z.read(root+'Libraries/FMER Default Library.json')
        from companion_shelf import Catalog
        catalog=Catalog.__new__(Catalog)._unpack(json.loads(sounds))
        if len(catalog['slots'])!=64 or any(i['kind']!='instrument' for i in catalog['slots']):
            raise ValueError('Default sound download must contain the same 64 included instruments')
        (out/'FMER-734-Default-Sounds.fmer-catalog.json').write_bytes(sounds)
    shutil.copy2(source,out/'FMER-734-Source.zip')
    shutil.copy2(R/'firmware/releases'/record['filename'],out/record['filename'])
    shutil.copy2(R/'docs/release/INSTALLATION.md',out/'INSTALLATION.md')
    for p in (R/'docs/release/media').glob('*.pdf'):shutil.copy2(p,out/p.name)
    press_pack(out)
    files={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(out.iterdir()) if p.is_file()}
    dump(out/'release-manifest.json',dict(firmware=734,companion_revision=revision,tag='build-734-r'+str(revision),repository='Nacsez/FMER',draft=True,
        publication_authorized=False,runtime_license_basis='Included Newlib/LLVM source and notices; external compiler; see RUNTIME_REVIEW_734.md',
        source_manifest_sha256=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),
        firmware_package_sha256=record['package_sha256'],deployment_rehearsal_sha256=sha(rehearsal),
        files=files,limitations='See INSTALLATION.md and docs/release/RELEASE_READINESS.md; private draft only.'))
    (out/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in sorted(out.iterdir()) if p.is_file()),encoding='ascii')
    print(json.dumps(dict(output=str(out),assets=len(files)+2,firmware=record['package_sha256'],network_access=False)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--companion',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--rehearsal',type=Path,required=True)
    a=p.parse_args();stage(a.out,a.companion,a.source,a.rehearsal)
