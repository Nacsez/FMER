"""Build the offline Windows x64 companion preview from pinned inputs.
No device, network, installed Python dependency or owner library is packaged.
"""
from pathlib import Path
import argparse,ast,hashlib,json,shutil,subprocess,zipfile,os,uuid
import companion_bank as bank
import companion_shelf as shelf
import library,release_firmware,companion_soundpacks
ROOT=Path(__file__).resolve().parents[1]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def runtime_modules():
    # Local import closure plus child-process entrypoints and fingerprint inputs.
    wanted={'portable_companion','launch_companion','companion','fm1_session','companion_shelf','companion_archive','companion_jobs','fm1_native_bridge_v25','fm1_native_state_v8','fm1_native_state_v9','fm1_native_state_v10','fm1_native_state_v11'}
    done=set()
    while wanted-done:
        name=sorted(wanted-done)[0];path=ROOT/'tools'/(name+'.py');done.add(name)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            imports=[a.name for a in node.names] if isinstance(node,ast.Import) else ([node.module] if node.module else [a.name for a in node.names]) if isinstance(node,ast.ImportFrom) else []
            for item in imports:
                module=item.split('.')[0]
                if (ROOT/'tools'/(module+'.py')).is_file():wanted.add(module)
    return [ROOT/'tools'/(name+'.py') for name in sorted(done)]

def defaults(out,executable):
    entries=bank.profile(executable)
    state=dict(format='FMER-SOUNDBANK',version=1,profile=bank.PROFILE,capacity=128,revision=0,slots=entries+entries,undo_slots=None)
    folder=out/'Libraries';folder.mkdir()
    (folder/'FMER Default and User Banks.json').write_bytes(library.canonical(bank.BankLibrary._envelope(state)))
    items=[];stamp='2026-10-16T00:00:00+00:00'
    for i,entry in enumerate(entries):
        item=dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL,'fmer-default-726.1-'+str(i))),kind='instrument',title=entry['name'],collection='FMER Defaults',tags=[entry['category']],notes='Original FMER default instrument; independently editable catalog copy.',favorite=False,entry=entry,dependencies={},created=stamp,updated=stamp,trashed=False)
        shelf.Catalog.validate_item(item);items.append(item)
    catalog=dict(format=shelf.FORMAT,version=1,capacity=shelf.CAPACITY,revision=0,slots=items,undo_slots=None)
    (folder/'FMER Default Library.json').write_bytes(library.canonical(shelf.envelope(catalog)))
    oem=companion_soundpacks.prepare('oem-v15',entries,library.PatchCodec(executable,lambda *a,**k:None))
    (folder/'OEM Patches - V15.json').write_bytes(library.canonical(oem['catalog']))
    (folder/'README.txt').write_text('OEM Patches - V15.json contains all 128 original V15 FM voices from the public M-VAVE recovery resource (Apache-2.0). Original data and notices are in third_party/oem_v15. Eleven imports are range-normalized, with changes listed in Notes. This is a separate sound pack, not an FMER bank replacement.\n\nAll 64 original FMER defaults, licensed GPL-3.0-only. These are original FMER instruments, not stock/proprietary banks. Editable source recipes are core/factory_presets.cpp in Corresponding Source.zip; see LICENSE and LICENSING.md. Recording music with FMER does not by itself place your music under GPL. Import the Library file to merge catalog copies. Import the Banks file from Library to merge copies, or use Restore PC banks only when you intend to replace both PC banks. Fresh installations already initialize both banks with these sounds. No unit is modified by importing local files.\n',encoding='utf8')

def source_archive(out):
    paths=[]
    for name in ('core','host','tools','tests','ui','hal','firmware/fm1','third_party/msfa','third_party/runtime','third_party/fm1_resources','packaging','docs/help','docs/release'):
        paths += [p for p in (ROOT/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix.lower() in ('.c','.cc','.cpp','.h','.hpp','.s','.ld','.inc','.in','.py','.html','.htm','.css','.js','.json','.cmake','.patch','.cs','.md','.txt') and not p.name.endswith('QUALIFICATION.json') and 'qualifications' not in p.parts]
    paths += [ROOT/name for name in ('CMakeLists.txt','LICENSE','LICENSING.md','NOTICE','CONTRIBUTING.md','DEPENDENCIES.md','docs/SOURCE_BUILD.md','docs/DESIGN.md','docs/COMPANION_PRODUCT.md','docs/COMPANION_RELEASE_733.md','evidence/target-toolchain.json','evidence/msfa-source.json','evidence/python-portable-runtime.json')]
    paths += [ROOT/name for name in ('docs/research/2026-10-18-community-interoperability.md','evidence/community-20261018.json')]
    paths += [ROOT/'evidence/companion-community-20261020.json']
    paths += [ROOT/'evidence/companion-qa-20261021.json']
    paths += [ROOT/'third_party/runtime/newlib/COPYING.NEWLIB']
    paths += [p for p in (ROOT/'third_party/oem_v15').iterdir() if p.is_file()]
    paths += [ROOT/'packaging/PUBLIC.gitignore',ROOT/'packaging/PUBLIC.gitattributes']
    # Explicit owner GPL-3.0-only grant, 2026-10-19; see docs/release/ARTWORK.md.
    # Include the original raster source, not only its generated firmware header.
    paths += [ROOT/'FMER SPLASH.png']
    # Reviewed first-party press images and printable documentation.
    paths += [p for p in (ROOT/'docs/release/media').glob('*') if p.is_file() and p.suffix.lower() in ('.png','.svg','.pdf')]
    for folder in ('core','host','firmware/fm1','firmware/fm1/loader','firmware/fm1/loader/tests','third_party/msfa'):
        for name in ('CMakeLists.txt','COPYING','LICENSE','README.md'):
            if (ROOT/folder/name).is_file():paths.append(ROOT/folder/name)
    # Keep the illustrated help usable from the source tree too. These are the
    # same reviewed FMER figures distributed beside the executable, not images
    # from the research corpus or imported patch libraries.
    paths += [p for p in (ROOT/'host/help').iterdir() if p.is_file() and p.suffix.lower() in ('.png','.svg')]
    # Ship the reviewed incorporated platform, not unrelated upstream engines,
    # samples or assets. The tree metadata is required by verify_upstream.
    import build_fm1_candidate as target
    upstream=ROOT/'third_party/acquired/fm1-target-review/community/felucca/source'
    paths += [upstream/item['path'] for item in target.verify_upstream(upstream)]
    paths += [upstream/'LICENSE',upstream/'README.md',upstream.parent/'tree.json']
    with zipfile.ZipFile(out/'Corresponding Source.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(set(paths)):
            if p.is_file():archive.write(p,p.relative_to(ROOT).as_posix())

def build(out):
    out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    pin=json.loads((ROOT/'evidence/python-portable-runtime.json').read_text())
    acquired=ROOT/'third_party/acquired/python-3.13.16-embed-amd64'
    runtime=out/'runtime';runtime.mkdir()
    for item in pin['files']:
        path=acquired/item['path']
        if sha(path)!=item['sha256']:raise ValueError('Python runtime changed: '+item['path'])
        shutil.copy2(path,runtime/item['path'])
    (runtime/'python313._pth').write_text('python313.zip\n.\n../tools\n',encoding='ascii')
    (out/'tools').mkdir()
    for p in runtime_modules():shutil.copy2(p,out/'tools'/p.name)
    (out/'host').mkdir()
    for p in (ROOT/'host').iterdir():
        if p.is_file() and p.suffix in ('.html','.js','.css','.json'):shutil.copy2(p,out/'host'/p.name)
    shutil.copytree(ROOT/'host/help',out/'host/help')
    shutil.copytree(ROOT/'third_party/oem_v15',out/'third_party/oem_v15')
    (out/'Help.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=host/help/index.htm"><title>FMER Handbook</title><a href="host/help/index.htm">Open the offline handbook</a>',encoding='utf8')
    (out/'bin').mkdir();host=ROOT/'artifacts/build/host/host/Release/fmer_host.exe';shutil.copy2(host,out/'bin/fmer_host.exe')
    defaults(out,host)
    firmware=out/'firmware/releases';firmware.mkdir(parents=True)
    shutil.copy2(ROOT/release_firmware.CATALOG,firmware/'catalog.json')
    for record in release_firmware.catalog():
        raw=release_firmware.bundled(record['id']);release_firmware.inspect_bytes(raw)
        (firmware/record['filename']).write_bytes(raw)
    notices=out/'notices';notices.mkdir()
    shutil.copy2(acquired/'LICENSE.txt',notices/'Python-LICENSE.txt')
    shutil.copy2(ROOT/'evidence/python-portable-runtime.json',notices/'Python-runtime-provenance.json')
    shutil.copy2(ROOT/'third_party/msfa/COPYING',notices/'MSFA-Apache-2.0.txt')
    shutil.copy2(ROOT/'third_party/msfa/README.md',notices/'MSFA-provenance.md')
    shutil.copy2(ROOT/'third_party/runtime/newlib/COPYING.NEWLIB',notices/'Newlib-LICENSE.txt')
    shutil.copy2(ROOT/'third_party/runtime/compiler-rt/LICENSE.TXT',notices/'LLVM-runtime-LICENSE.txt')
    shutil.copy2(ROOT/'third_party/runtime/compiler-rt/CREDITS.TXT',notices/'LLVM-runtime-CREDITS.txt')
    shutil.copy2(ROOT/'third_party/runtime/PROVENANCE.json',notices/'Firmware-runtime-provenance.json')
    shutil.copy2(ROOT/'third_party/fm1_resources/UPSTREAM-NOTICES.md',notices/'Configuration-UPSTREAM-NOTICES.md')
    shutil.copy2(ROOT/'third_party/fm1_resources/LICENSE-APACHE-2.0.txt',notices/'Configuration-Apache-2.0.txt')
    shutil.copy2(ROOT/'third_party/fm1_resources/README.md',notices/'Configuration-provenance.md')
    shutil.copy2(ROOT/'firmware/fm1/loader/LICENSE',notices/'GPL-3.0.txt')
    for name in ('LICENSE','LICENSING.md','NOTICE'):
        shutil.copy2(ROOT/name,out/name)
    shutil.copy2(ROOT/'NOTICE',notices/'FMER-NOTICE.txt')
    shutil.copy2(ROOT/'LICENSING.md',notices/'FMER-LICENSING.md')
    shutil.copy2(ROOT/'docs/SOURCE_BUILD.md',notices/'SOURCE_BUILD.md')
    shutil.copy2(ROOT/'DEPENDENCIES.md',notices/'DEPENDENCIES.md')
    (notices/'Runtime changes.txt').write_text('Python 3.13.16 Windows x64 embeddable distribution, verified against the official manifest. Binaries are unmodified. Only python313._pth is changed to add the application tools directory; site-package discovery remains disabled. No pip or machine Python installation is used. Microsoft runtime DLLs shipped in that official distribution are retained. See Python-LICENSE.txt for bundled component notices.\n',encoding='utf8')
    source_archive(out)
    csc=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(csc),'/nologo','/target:winexe','/reference:System.Windows.Forms.dll','/out:'+str(out/'FMER Companion.exe'),str(ROOT/'packaging/Launcher.cs')],check=True)
    (out/'READ ME FIRST.txt').write_text('FMER Companion 734 - Windows x64\n\nExtract ALL files, then double-click FMER Companion.exe. Keep this folder together. No separate Python install, account or internet connection is needed. The application opens in your browser on this computer.\n\nConnect one powered-on FM-1. Use Check connection at the top right. Stock firmware is detected, but its instrument backup commands are unavailable; open Firmware to install FMER. Back up existing FMER instruments/projects before reinstalling. The installer checks compatible hardware, memory layout and calibration rather than requiring identical application code. Different layouts remain unsupported. Keep USB and power connected and controls untouched while the progress banner is active. A failed transfer is not completion; read its message and export diagnostics.\n\nThe new updater can resume the included firmware when its record and compatibility remain verifiable. Other update modes or a damaged bootloader need a separate recovery procedure. Custom applications require the exact reviewed935 updater and protected layout; other packages need the publisher installer.\n\nHelp.html opens the offline handbook. Libraries contains 64 original FMER instruments, 128 OEM V15 voices and PC-bank backups. Your library and logs live separately under %LOCALAPPDATA%/FMER/Companion. OEM Patches includes 128 voices from the licensed public V15 resource; private unit dumps are not included.\n\nWindows10/11 x64, Intel/AMD. Unsigned application; Windows may show a reputation warning. Original FMER firmware, Companion and default instruments are GPL-3.0-only. Keep LICENSE, LICENSING.md, NOTICE, included dependency notices and source archive.\n',encoding='utf8')
    manifest=dict(product='FMER Companion 734',companion_revision=5,scope='Windows x64 portable companion',python=pin['version'],firmware_included=True,source_archive=True,files={p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    zip_path=out.parent/(out.name+'.zip')
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for p in sorted(out.rglob('*')):
            if p.is_file():archive.write(p,out.name+'/'+p.relative_to(out).as_posix())
    report=dict(path=str(out),zip=str(zip_path),files=len(manifest['files']),bytes=zip_path.stat().st_size,sha256=sha(zip_path))
    zip_path.with_suffix('.sha256.txt').write_text(report['sha256']+'  '+zip_path.name+'\n',encoding='ascii')
    print(json.dumps(report,indent=2));return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);build(p.parse_args().out)
