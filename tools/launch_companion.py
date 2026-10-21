"""Double-click companion launcher. Loopback only; no MIDI or machine setup."""
from pathlib import Path
import argparse,hashlib,json,os,socket,subprocess,sys,time,urllib.request,webbrowser

ROOT=Path(__file__).resolve().parents[1]
APP='FMER Companion 734'
def source_fingerprint():
    digest=hashlib.sha256()
    for name in ('tools/release_firmware.py','tools/fm1_flash_transport.py','firmware/releases/catalog.json'):
        path=ROOT/name
        if path.is_file():digest.update(name.encode());digest.update(path.read_bytes())
    for path in ('tools/launch_companion.py','tools/companion_lifecycle.py','tools/companion.py','tools/companion_device.py','tools/companion_bank.py','tools/fm1_native_bridge_v26.py','tools/fm1_native_state_v11.py','tools/fm1_native_bridge_v25.py','tools/fm1_native_state_v10.py','tools/fm1_native_state_v9.py','tools/fm1_native_state_v8.py','tools/fm1_session.py','host/companion.html','host/fm_algorithms.json','tools/companion_shelf.py','tools/companion_archive.py','tools/companion_jobs.py','host/companion_app.html','host/companion_app.css','host/companion_app.js'):
        digest.update(path.encode());digest.update((ROOT/path).read_bytes())
    for path in sorted((ROOT/'host/help').glob('*')):
        if path.is_file():digest.update(path.name.encode());digest.update(path.read_bytes())
    for name in ('tools/companion_community.py','tools/companion_soundpacks.py','host/firmware_compatibility.json','third_party/oem_v15/voices.json'):
        path=ROOT/name
        digest.update(name.encode());digest.update(path.read_bytes())
    return digest.hexdigest()

def health(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=.4) as response:
            value=json.load(response)
            return value if value.get('app')==APP and (value.get('data_root')==str(Path(os.environ['FMER_DATA_DIR']).resolve()) if 'FMER_DATA_DIR' in os.environ else value.get('workspace')==str(ROOT)) and value.get('source')==source_fingerprint() else None
    except (OSError,ValueError):return None

def launch(open_browser=True):
    folder=Path(os.environ['FMER_DATA_DIR'])/'logs/launcher' if 'FMER_DATA_DIR' in os.environ else ROOT/'artifacts/companion-launch';folder.mkdir(parents=True,exist_ok=True)
    for port in range(8787,8797):
        if health(port):
            url=f'http://127.0.0.1:{port}/'
            if open_browser:webbrowser.open(url)
            return dict(url=url,reused=True)
    if 'FMER_DATA_DIR' in os.environ:
        for port in range(8787,8797):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=.4) as response:value=json.load(response)
                if value.get('data_root')==str(Path(os.environ['FMER_DATA_DIR']).resolve()):
                    if value.get('app')!=APP:raise RuntimeError('Another application owns this library.')
                    request=urllib.request.Request(f'http://127.0.0.1:{port}/api/quit',data=b'{}',headers={'Content-Type':'application/json'})
                    try:
                        with urllib.request.urlopen(request,timeout=12) as reply:json.load(reply)
                    except Exception as error:raise RuntimeError('The previous companion is busy. Finish its operation and use Quit companion, then reopen this version.') from error
                    for _ in range(100):
                        try:
                            with socket.create_connection(('127.0.0.1',port),timeout=.2):pass
                        except OSError:break
                        time.sleep(.1)
                    else:raise RuntimeError('The previous companion is still closing. Please try again shortly.')
            except (OSError,ValueError):pass
    for port in range(8787,8797):
        with socket.socket() as probe:
            try:probe.bind(('127.0.0.1',port))
            except OSError:continue
        stamp=time.strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid())
        out=folder/(stamp+'.stdout.log');err=folder/(stamp+'.stderr.log')
        options={}
        if os.name=='nt':options['creationflags']=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP
        with out.open('ab') as stdout,err.open('ab') as stderr:
            process=subprocess.Popen([sys.executable,'-B',str(ROOT/'tools/companion.py'),'--port',str(port)],
                cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,**options)
        for _ in range(100):
            if health(port):
                result=dict(url=f'http://127.0.0.1:{port}/',pid=process.pid,reused=False,stdout=str(out),stderr=str(err))
                (folder/'latest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
                if open_browser:webbrowser.open(result['url'])
                return result
            if process.poll() is not None:raise RuntimeError('Companion exited. Read '+str(err))
            time.sleep(.1)
        raise RuntimeError('Companion startup timed out. Read '+str(err))
    raise RuntimeError('No available loopback port8787..8796. Close an older companion window/server and try again.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--no-browser',action='store_true');a=p.parse_args()
    try:print(json.dumps(launch(not a.no_browser)));sys.exit(0)
    except Exception as error:print('FMER could not start: '+str(error),file=sys.stderr);sys.exit(1)
