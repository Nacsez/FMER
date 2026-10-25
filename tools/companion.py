"""FMER companion: local dual-bank editor and exact-core audition. Explicit734 device sync is opt-in."""
import argparse
import base64
import json
from pathlib import Path
import re
import subprocess
import os
import threading
import time
from companion_lifecycle import BrowserLeases
from companion_http import CompanionHTTPServer, serialize_handlers
from companion_startup import StartupLog
import companion_bank as bank
import library
import sandbox
import companion_device
import companion_shelf
import companion_jobs
import companion_support
import companion_archive
import companion_transfer
import companion_dx7
import companion_soundpacks
import companion_community
import companion_loadouts
import companion_units
from launch_companion import source_fingerprint

def handler_for(executable,root,legacy_root=None):
    store=bank.BankLibrary(root,executable)
    device=companion_device.Device(executable,root)
    catalog=companion_shelf.Catalog(Path(root)/'catalog',executable)
    jobs=companion_jobs.Jobs(device,Path(root)/'operations')
    loadouts=companion_loadouts.Profiles(Path(root)/'loadouts',executable,store.defaults)
    units=companion_units.Units(Path(root)/'units',executable,loadouts)
    jobs.units=units
    source=source_fingerprint()
    startup=StartupLog(root)
    leases=BrowserLeases()
    parent=sandbox.handler_for(executable,Path(root)/'legacy-library' if legacy_root is None else legacy_root)
    class Handler(parent):
        def do_GET(self):
            if self.path=='/api/support':return self.send(200,library.canonical(companion_support.summary(Path(root)/'operations')))
            if not self.local_request():return self.send(403,b'{}')
            if self.path=='/api/startup-report':return self.send(200,library.canonical(startup.report(source)))
            if self.path=='/api/presence':
                try:
                    ports=companion_device.hardware_bridge.WinMM().enumerate()
                    names=lambda key:[x['name'] for x in ports[key] if 'FM-1' in x['name'] or 'FMER' in x['name'] or companion_community.ENDPOINT.fullmatch(x['name'])]
                    return self.send(200,library.canonical(dict(inputs=names('inputs'),outputs=names('outputs'))))
                except Exception as error:return self.send(503,library.canonical({'error':str(error)}))
            if self.path=='/api/algorithms':return self.send(200,(sandbox.ROOT/'host/fm_algorithms.json').read_bytes())
            if self.path=='/api/health':return self.send(200,library.canonical(dict(app='FMER Companion 735',workspace=str(sandbox.ROOT),pid=os.getpid(),data_root=str(Path(root).resolve()),profile=bank.PROFILE,source=source)))
            if self.path=='/':return self.send(200,(sandbox.ROOT/'host/companion_app.html').read_bytes(),'text/html; charset=utf-8')
            if self.path=='/editor':return self.send(200,(sandbox.ROOT/'host/companion.html').read_bytes(),'text/html; charset=utf-8')
            if self.path=='/api/catalog':
                try:return self.send(200,library.canonical(catalog.snapshot()))
                except (ValueError,OSError) as e:return self.send(400,library.canonical({'error':str(e)}))
            if self.path=='/api/sound-packs':return self.send(200,library.canonical(companion_soundpacks.PACKS))
            if self.path=='/api/loadouts':
                try:return self.send(200,library.canonical(loadouts.snapshot()))
                except (ValueError,OSError) as e:return self.send(400,library.canonical({'error':str(e)}))
            if self.path=='/api/units':
                try:return self.send(200,library.canonical(units.snapshot()))
                except (ValueError,OSError) as e:return self.send(400,library.canonical({'error':str(e)}))
            if self.path=='/api/capabilities':return self.send(200,library.canonical(jobs.capabilities()))
            if self.path.startswith('/api/jobs/'):
                try:
                    value=self.path[len('/api/jobs/'):]
                    result=jobs.backup(value[:-7]) if value.endswith('/backup') else jobs.status(value)
                    return self.send(200,library.canonical(result))
                except (ValueError,OSError) as e:return self.send(404,library.canonical({'error':str(e)}))
            if self.path.startswith('/help/'):
                # Exact basename allowlist prevents traversal, encoded separators and local file disclosure.
                name=self.path[len('/help/'):] or 'index.htm'
                if not re.fullmatch(r'[a-z0-9_-]+\.(?:htm|css|js|json|png|svg|txt)',name):return self.send(404,b'{}')
                path=sandbox.ROOT/'host/help'/name
                if not path.is_file():return self.send(404,b'{}')
                mime={'.htm':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript','.json':'application/json','.png':'image/png','.svg':'image/svg+xml','.txt':'text/plain; charset=utf-8'}[path.suffix]
                return self.send(200,path.read_bytes(),mime)
            if self.path in ('/companion_app.js','/companion_loadouts.js','/companion_units.js','/companion_app.css'):
                return self.send(200,(sandbox.ROOT/'host'/self.path[1:]).read_bytes(),'text/javascript' if self.path.endswith('.js') else 'text/css')
            if self.path=='/lab':return self.send(200,(sandbox.ROOT/'host/sandbox.html').read_bytes(),'text/html; charset=utf-8')
            if self.path.startswith('/auditions/'):
                relative=self.path[len('/auditions/'):] or 'index.html'
                if relative not in ('index.html','audit.json') and not re.fullmatch(r'(baseline|current)/preset-([0-9]|[1-5][0-9]|6[0-3])\.wav',relative):return self.send(404,b'{}')
                path=sandbox.ROOT/'artifacts/defaults-719-phaser'/relative
                if not path.is_file():return self.send(404,b'{"error":"Generate the listening comparison first"}')
                mime='audio/wav' if path.suffix=='.wav' else 'text/html; charset=utf-8' if path.suffix=='.html' else 'application/json'
                return self.send(200,path.read_bytes(),mime)
            if self.path=='/api/banks':
                try:return self.send(200,library.canonical(store.dispatch({'action':'snapshot'})))
                except (ValueError,OSError) as e:return self.send(400,library.canonical({'error':str(e)}))
            return super().do_GET()
        def do_POST(self):
            if self.path=='/api/startup':
                if not self.local_request():return self.send(403,b'{}')
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=4096:raise ValueError('Invalid startup diagnostic size')
                    startup.record(library.strict_loads(self.rfile.read(size)))
                    return self.send(200,b'{}')
                except (ValueError,TypeError,OSError):return self.send(400,b'{}')
            if self.path=='/api/browser':
                if not self.local_request():return self.send(403,b'{}')
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=256:raise ValueError('Invalid heartbeat')
                    data=library.strict_loads(self.rfile.read(size));leases.update(data.get('tab'),data.get('closed') is True)
                    return self.send(200,b'{}')
                except (ValueError,TypeError):return self.send(400,b'{}')
            if self.path=='/api/quit':
                if not self.local_request():return self.send(403,b'{}')
                with jobs.guard:
                    if jobs.active:return self.send(409,library.canonical({'error':'Wait for the current device operation before quitting.'}))
                    jobs.closing=True
                    self.server.application_closing=True
                    device.stop_recording()
                    self.send(200,b'{"stopped":true}')
                    threading.Thread(target=self.server.shutdown,daemon=True).start()
                return
            if self.path not in ('/api/banks','/api/work','/api/device','/api/catalog','/api/jobs','/api/firmware','/api/restore-plan','/api/transfer-plan','/api/dx7','/api/sound-packs','/api/community-import','/api/loadouts','/api/loadout-plan','/api/loadout-banks-plan','/api/units'):return super().do_POST()
            if not self.local_request():return self.send(403,b'{}')
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=14*1024*1024:raise ValueError('Request size outside bound')
                data=library.strict_loads(self.rfile.read(size))
                if self.path=='/api/units':result=units.dispatch(data)
                elif self.path=='/api/loadouts':result=loadouts.dispatch(data)
                elif self.path=='/api/loadout-banks-plan':result=companion_loadouts.bank_assignment(data)['plan']
                elif self.path=='/api/loadout-plan':result=companion_loadouts.deployment(data)['plan']
                elif self.path=='/api/catalog':
                    if data.get('action')=='import_banks':
                        library.fields(data,{'action','revision','backup'},'bank import')
                        data={**data,'action':'import','backup':companion_shelf.from_banks(store._unpack(data.get('backup')))}
                    result=catalog.dispatch(data)
                elif self.path=='/api/sound-packs':
                    library.fields(data,{'id'},'sound pack')
                    result=companion_soundpacks.prepare(data.get('id'),store.defaults,store.codec)
                elif self.path=='/api/community-import':
                    library.fields(data,{'archive'},'community capture import')
                    result=companion_community.decode(data.get('archive'),store.defaults,store.codec)
                elif self.path=='/api/dx7':
                    library.fields(data,{'action','raw','entries','collection'},'DX7 exchange')
                    if data.get('action')=='decode':
                        if not isinstance(data.get('raw'),str) or len(data['raw'])>5500:raise ValueError('Choose one DX7 voice or a 32-voice .syx bank')
                        decoded=companion_dx7.decode(base64.b64decode(data['raw'],validate=True),bank.decode_record(store.defaults[0]['native']),store.codec)
                        result={**decoded,'catalog':companion_dx7.make_catalog(decoded,data.get('collection','DX7 imports'))}
                    elif data.get('action')=='export':
                        entries=data.get('entries')
                        if not isinstance(entries,list) or len(entries) not in (1,32):raise ValueError('Select one or exactly 32 FM instruments')
                        for entry in entries:bank.BankLibrary.validate_entry(entry)
                        result=companion_dx7.export([bank.decode_record(entry['native']) for entry in entries],store.codec)
                    else:raise ValueError('Unknown DX7 exchange action')
                elif self.path=='/api/jobs':result=jobs.start(data)
                elif self.path=='/api/firmware':result=jobs.inspect(data)
                elif self.path=='/api/restore-plan':result=companion_archive.plan(data)
                elif self.path=='/api/transfer-plan':
                    library.fields(data,{'rows'},'transfer plan')
                    result=companion_transfer.plan(data.get('rows'))
                elif self.path=='/api/device':result=device.dispatch(data)
                elif self.path=='/api/banks':result=store.dispatch(data)
                else:
                    library.fields(data,{'action','entry','state','raw','scenario','velocity','profile'},'working sound')
                    action=data.get('action')
                    if action=='import':
                        raw=base64.b64decode(data['raw'],validate=True)
                        if len(raw)==784:raw=bank.native.upgrade_v1(raw)
                        state=bank.native.decode_compatible(raw)
                        name=bytes(state['vced'][145:]).decode('ascii').rstrip()
                        if not name:
                            name='UNTITLED';state['vced'][145:]=list(name.ljust(10).encode('ascii'))
                        result=dict(state=state,entry=dict(name=name,category='Custom',favorite=False,audition_note=60,native=bank.pack(state)))
                    elif action=='export_fx':result=dict(profile=bank.export_fx(data['state']))
                    elif action=='import_fx':result=dict(state=bank.import_fx(data['state'],data['profile']))
                    elif action=='decode':
                        bank.BankLibrary.validate_entry(data['entry']);result=dict(state=bank.decode_record(data['entry']['native']))
                    elif action in ('encode','audition'):
                        entry=dict(data['entry']);entry['native']=bank.pack(data['state']);bank.BankLibrary.validate_entry(entry)
                        if action=='encode':result=dict(entry=entry)
                        else:
                            library.choice(data.get('scenario','note'),{'note','chord','sequence','arp','pattern'},'audition phrase')
                            library.integer(data.get('velocity',100),1,127,'velocity')
                            result=sandbox.render_request(bank.render_settings(entry,data.get('scenario','note'),data.get('velocity',100)),executable)
                    else:raise ValueError('Unknown working sound action')
                sandbox.journal('companion_request',path=self.path,action=data.get('action'),revision=result.get('revision'))
                self.send(200,library.canonical(result))
            except (ValueError,KeyError,TypeError,OSError,RuntimeError,subprocess.SubprocessError) as e:
                sandbox.journal('companion_refused',path=self.path,error=str(e))
                self.send(409 if isinstance(e,library.LibraryConflict) else 400,library.canonical({'error':str(e)}))
    Handler.device_owner=device
    Handler.browser_leases=leases
    Handler.jobs=jobs
    return serialize_handlers(Handler)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',type=int,default=8787);p.add_argument('--library-root',type=Path,default=Path(os.environ.get('FMER_DATA_DIR',sandbox.ROOT/'local/companion709')));p.add_argument('--legacy-library-root',type=Path,default=sandbox.LIBRARY);p.add_argument('--config',default='Release',choices=('Debug','Release'));a=p.parse_args()
    executable=sandbox.find_executable(a.config)
    instance=None
    if os.name=='nt':
        import msvcrt
        a.library_root.mkdir(parents=True,exist_ok=True)
        instance=(a.library_root/'companion.instance').open('a+b')
        if instance.tell()==0:instance.write(b'0');instance.flush()
        instance.seek(0)
        try:msvcrt.locking(instance.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise RuntimeError('Another companion owns this Library. Quit it before starting another server.')
    server=CompanionHTTPServer(('127.0.0.1',a.port),handler_for(executable,a.library_root,a.legacy_library_root))
    print(f'FMER companion: http://127.0.0.1:{server.server_port}/ (local workspace; explicit device transfers)',flush=True)
    def watch_tabs():
        while True:
            time.sleep(2)
            with server.RequestHandlerClass.jobs.guard:
                expired=server.RequestHandlerClass.browser_leases.expired(bool(server.RequestHandlerClass.jobs.active))
                if expired:server.RequestHandlerClass.jobs.closing=True
            if expired:server.shutdown();return
    threading.Thread(target=watch_tabs,daemon=True).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        # Finish any current library/render request before releasing the shared
        # data-root lock. Queued connections must not mutate after shutdown.
        with server.RequestHandlerClass.application_guard:
            server.application_closing=True
            server.RequestHandlerClass.device_owner.stop_recording()
            server.server_close()
            if instance:instance.close()
if __name__=='__main__':main()
