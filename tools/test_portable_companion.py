"""Extracted deployment rehearsal: minimal PATH, isolated user data, no MIDI.
This is not a clean VM or a physical Amethyst installation qualification.
"""
from pathlib import Path
import argparse,hashlib,json,os,socket,subprocess,time,urllib.request,zipfile
R=Path(__file__).resolve().parents[1]
def test(archive,out):
    out=out.resolve();archive=archive.resolve()
    out.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(archive) as z:z.extractall(out/'Extracted app with spaces')
    app=next(p for p in (out/'Extracted app with spaces').iterdir() if p.is_dir())
    data=out/'Isolated User Data'
    env=dict(os.environ,FMER_DATA_DIR=str(data.resolve()),PATH=os.environ['WINDIR']+';'+os.environ['WINDIR']+'/System32',PYTHONPATH='',PYTHONHOME='')
    # Do not inherit heartbeats from an owner's existing tab on8787..8796.
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0));env['FMER_PORT']=str(reservation.getsockname()[1])
    checks=[];url=None
    def passed(label):checks.append(label);print(label,flush=True)
    def api(path,body=None):
        req=urllib.request.Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
    def launch():
        child=subprocess.Popen([str(app/'FMER Companion.exe'),'--no-browser'],env=env,cwd=app)
        for _ in range(300):
            if (data/'launch.json').is_file():
                record=json.loads((data/'launch.json').read_text());return child,record['url'].rstrip('/')
            if child.poll() is not None and child.returncode:raise RuntimeError('Launcher failed')
            time.sleep(.1)
        child.terminate();raise RuntimeError('Launcher timed out')
    try:
        manifest=json.loads((app/'manifest.json').read_text())
        for name,digest in manifest['files'].items():
            if hashlib.sha256((app/name).read_bytes()).hexdigest()!=digest:raise ValueError('Manifest mismatch: '+name)
        passed('All extracted manifest files match SHA-256')
        result=subprocess.run([str(app/'runtime/python.exe'),'-c','import ctypes,ssl,socket,json; import companion; import release_firmware; print(ssl.OPENSSL_VERSION)'],env=env,cwd=app,capture_output=True,text=True,timeout=20)
        if result.returncode:raise RuntimeError(result.stderr)
        passed('Bundled Python imports ctypes, SSL, sockets, companion and transport without installed Python')
        child,url=launch();child.wait(timeout=20)
        assert api('/api/health')['app']==manifest['product']
        assert api('/api/health')['data_root']==str(data.resolve())
        assert api('/api/catalog')['slots']==[]
        banks=api('/api/banks');assert len(banks['slots'])==128
        assert banks['slots'][:64]==banks['slots'][64:]
        passed('One-click EXE starts with minimal PATH; fresh original DEFAULT and USER banks, empty private catalog')
        from companion_startup_smoke import check_browser_startup
        check_browser_startup(url,out/'browser')
        api('/api/browser',dict(tab='portable-rehearsal'))
        passed('Extracted EXE serves working Edge controls, lazy editor, and recoverable startup errors')
        oem=api('/api/sound-packs',dict(id='oem-v15'))
        assert oem['count']==128 and len(oem['normalized_slots'])==11
        assert api('/api/banks')==banks and api('/api/catalog')['slots']==[]
        assert (app/'Libraries/OEM Patches - V15.json').is_file()
        for name in ('voices.json','UPSTREAM-NOTICES.md','LICENSE-APACHE-2.0.txt'):
            assert (app/'third_party/oem_v15'/name).is_file()
        passed('All 128 OEM V15 voices prepare offline with bundled codec and notices; review leaves banks and catalog unchanged')
        caps=api('/api/capabilities');release=next(x for x in caps['bundled_firmware'] if x['available'])
        report=api('/api/firmware',dict(action='inspect',release=release['id']))
        assert report['installable'] and not report['hardware_qualified']
        if manifest['product']=='FMER Companion 735' or manifest.get('companion_revision',0)>=6:
            assert release['id']==('fm1-compatible-to-735-r9' if manifest['product']=='FMER Companion 735' else 'fm1-compatible-to-734-r3')
            formats=set()
            for item in caps['bundled_firmware']:
                assert item['available']
                inspected=api('/api/firmware',dict(action='inspect',release=item['id']))
                assert inspected['installable'] and not inspected['head_written']
                assert inspected['app_write_range']==[0x4000,0x93000]
                formats.add(inspected['package_format'])
            assert formats=={'application-only-v1','self-describing-v1'}
        passed('Bundled first-install inspection succeeds without private dumps, SDK or old development packages')
        if manifest['product']=='FMER Companion 735' or manifest.get('companion_revision',0)>=7:
            loadouts=api('/api/loadouts')
            assert len(loadouts['included'])==5 and len(loadouts['sounds'])==192 and loadouts['slots']==[]
            a=api('/api/loadouts',dict(action='export',id='A'));b=api('/api/loadouts',dict(action='export',id='B'))
            plan=api('/api/loadout-banks-plan',dict(default=a,user=b))
            assert plan['count']==128 and [r['slot'] for r in plan['rows']]==list(range(64,128))+list(range(64))
            copied=api('/api/loadouts',dict(action='copy',revision=loadouts['revision'],id='A',title='Portable set'))
            assert copied['slots'][0]['title']=='Portable set'
            passed('Included 192 sounds, five profiles, independent bank plans and personal profile saves work offline')
        if manifest['product']=='FMER Companion 735':
            units=api('/api/units');assert units['slots']==[] and units['capacity']==16
            units=api('/api/units',dict(action='save',revision=units['revision'],profile=dict(id='new',name='Portable Malachite',notes='',collection='Malachite sounds',default=copied['slots'][0]['id'],user='B')))
            first=units['slots'][0]
            units=api('/api/units',dict(action='save',revision=units['revision'],profile=dict(id='new',name='Portable Citrine',notes='',collection='Citrine sounds',default='C',user='D')))
            assert units['slots'][0]==first and units['slots'][1]['default']=='C'
            passed('Named instrument setups retain independent A/B assignments and collections with bundled runtime')
        coverage=json.loads((app/'host/help/coverage.json').read_text())
        for slug,items in coverage['figures'].items():
            for name in [slug+'.htm']+[x['file'] for x in items]:
                with urllib.request.urlopen(url+'/help/'+name,timeout=10) as r:assert r.status==200 and len(r.read())>100
        passed('Every illustrated help page and figure serves locally from the extracted package')
        for name,original in (('license.txt','LICENSE'),('notice.txt','NOTICE')):
            with urllib.request.urlopen(url+'/help/'+name,timeout=10) as r:
                assert r.status==200 and r.read().decode('utf8').replace('\r\n','\n')==(app/original).read_text(encoding='utf8')
        with zipfile.ZipFile(app/'Corresponding Source.zip') as source:
            for name in ('LICENSE','LICENSING.md','NOTICE','tools/companion_dx7.py','tools/fm1_flash_transport.py'):
                assert source.read(name)==(app/name).read_bytes()
        passed('Offline Help serves exact GPL license and attribution; matching source includes DX7 and installer code')
        lib=json.loads((app/'Libraries/FMER Default Library.json').read_text())
        imported=api('/api/catalog',dict(action='import',revision=api('/api/catalog')['revision'],backup=lib))
        assert len(imported['slots'])==64
        entry=banks['slots'][0];state=api('/api/work',dict(action='decode',entry=entry))['state']
        audition=api('/api/work',dict(action='audition',entry=entry,state=state,scenario='note',velocity=100))
        assert audition['peak']>0
        passed('Default catalog imports all 64 sounds; bundled host renders audible PCM')
        api('/api/quit',{});time.sleep(.5)
        (data/'launch.json').unlink()
        child,url=launch();child.wait(timeout=20)
        assert len(api('/api/catalog')['slots'])==64
        if manifest['product']=='FMER Companion 735' or manifest.get('companion_revision',0)>=7:assert api('/api/loadouts')['slots'][0]['title']=='Portable set'
        if manifest['product']=='FMER Companion 735':assert api('/api/units')['slots']==units['slots']
        passed('Quit and relaunch preserve the per-user Library independently of the program folder')
        # An idle old build must be replaced gracefully, without Task Manager.
        old_pid=api('/api/health')['pid']
        fingerprinted=app/'tools/companion.py'
        fingerprinted.write_bytes(fingerprinted.read_bytes()+b'\n# simulated newer build for lifecycle rehearsal\n')
        (data/'launch.json').unlink()
        child,url=launch();child.wait(timeout=20)
        assert api('/api/health')['pid']!=old_pid
        assert len(api('/api/catalog')['slots'])==64
        passed('New build gracefully replaces idle old server and retains the library')
        api('/api/browser',dict(tab='rehearsal-tab'))
        api('/api/browser',dict(tab='rehearsal-tab',closed=True))
        deadline=time.monotonic()+55
        while time.monotonic()<deadline:
            try:api('/api/health')
            except OSError:break
            time.sleep(.5)
        else:raise RuntimeError('Server survived closing its last browser tab')
        url=None
        passed('Last browser tab close releases the server without terminating Python manually')

        if url:api('/api/quit',{});url=None
        result=dict(status='passed',checks=checks,hardware_access=False,clean_machine=False,zip=str(archive),zip_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    except Exception as e:
        result=dict(status='failed',checks=checks,error=repr(e));raise
    finally:
        if url:
            try:api('/api/quit',{})
            except Exception:pass
        (out/'report.json').write_text(json.dumps(result,indent=2),encoding='utf8')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--zip',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();test(a.zip,a.out)
