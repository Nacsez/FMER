"""Explicit734 companion operations; serialized device access, backups and logs."""
import base64
from datetime import datetime,timezone
import json,os,subprocess,sys,time,uuid
from pathlib import Path
import companion_bank as bank
import fm1_native_bridge_v27 as bridge
import fm1_native_bridge_v26 as previous_bridge
BRIDGES={bridge.IDENTITY:bridge,previous_bridge.IDENTITY:previous_bridge}
import hardware_bridge
import library
import companion_archive as archive
import companion_transfer as transfer
import companion_community as community

ROOT=Path(__file__).resolve().parents[1]
CONFIRM={'reset_defaults':('Reset to FMER Default',3),'reset_user':('Reset User Bank',4),'clear_user':('Clear User Bank',5)}

class Device:
    def __init__(self,executable,root):
        self.executable=executable;self.root=Path(root);self.recorder=None;self.stop_file=None;self.capture=None
        self.capture_battery=False
        self.lock=library.PatchLibrary(self.root/'device-access',executable)

    def stop_recording(self):
        if self.recorder is None:return
        self.stop_file.write_text('Explicit companion operation\n',encoding='utf8')
        try:self.recorder.wait(timeout=8)
        except subprocess.TimeoutExpired:raise RuntimeError('Session recorder is still closing; device operation refused')
        self.recorder=None

    def start_recording(self):
        if self.recorder is not None and self.recorder.poll() is None:return dict(recording=True,path=str(self.capture))
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'-'+uuid.uuid4().hex[:8]
        self.capture=self.root/'session-logs'/('companion734-'+stamp)
        self.stop_file=self.root/'device-access'/('stop-'+stamp)
        self.stop_file.parent.mkdir(parents=True,exist_ok=True)
        flags=dict(creationflags=subprocess.CREATE_NO_WINDOW) if os.name=='nt' else {}
        log=self.stop_file.with_suffix('.log')
        with log.open('wb') as output:
            self.recorder=subprocess.Popen([sys.executable,'-B',str(ROOT/'tools/fm1_session.py'),
                '--firmware',getattr(self,'record_identity',bridge.IDENTITY)[-3:],'--duration','0','--stop-file',str(self.stop_file),'--output',str(self.capture),
                '--native-backup-directory',str(self.root/'device-backups')]+(['--battery-telemetry'] if self.capture_battery else []),cwd=ROOT,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,**flags)
        for _ in range(60):
            try:status=json.loads((self.capture/'status.json').read_text(encoding='utf8'))
            except (OSError,ValueError):status={}
            if status.get('phase')=='capturing':return dict(recording=True,path=str(self.capture),pid=self.recorder.pid)
            if self.recorder.poll() is not None:break
            time.sleep(.1)
        self.stop_recording()
        raise RuntimeError('Recorder did not reach a verified capture session; inspect '+str(log))

    def dispatch(self,request,progress=lambda *args,**kwargs:None):
        library.fields(request,{'action','slot','raw','confirmation','settings','persist','battery_telemetry','backup','destination','name','rows'},'device request')
        action=request.get('action')
        library.choice(action,{'community_capture','probe','catalog','pull','push','load','record','stop_recording','battery_history','midi_read','midi_set',
            'project_catalog','project_pull','project_push','project_load','project_save','backup_all','restore_all','deploy_library','instrument_rename','instrument_copy','instrument_swap',*CONFIRM},'device action')
        if action=='deploy_library':
            plan=transfer.plan(request.get('rows'))
            if request.get('confirmation')!=plan['confirmation']:
                raise ValueError('Review and confirm these exact transfer destinations')
        if action=='restore_all':
            archive.validate(request.get('backup'))
            if request.get('confirmation')!='Restore populated unit slots':raise ValueError('Confirm Restore populated unit slots')
        if action in ('instrument_rename','instrument_copy','instrument_swap'):
            bridge.slot_number(request.get('slot'))
            if action=='instrument_rename':
                name=request.get('name')
                if not isinstance(name,str) or not 1<=len(name)<=10 or not name.strip() or any(not 32<=ord(c)<=126 for c in name):raise ValueError('Use1..10 printable ASCII characters')
            else:
                bridge.slot_number(request.get('destination'))
                if request['slot']==request['destination']:raise ValueError('Choose another destination')
            if request.get('confirmation')!='Apply unit instrument change':raise ValueError('Confirm Apply unit instrument change')
        if 'battery_telemetry' in request:
            library.boolean(request['battery_telemetry'],'battery_telemetry')
            if action!='record':raise ValueError('battery_telemetry only applies to record')
        if action=='midi_set':
            bridge.midi_settings_request(request.get('settings'),0)
            library.boolean(request.get('persist',False),'persist')
        if action in ('pull','push','load'):bridge.slot_number(request.get('slot'))
        if action in ('project_pull','project_push','project_load','project_save'):
            bridge.native._integer(request.get('slot'),0,15,'Project slot')
        raw=None
        if action in ('push','project_push'):
            # Upgrade old host records before opening MIDI. The original PC
            # entry stays unchanged, and only strict native11 bytes reach733/734.
            raw=base64.b64decode(request['raw'],validate=True)
            raw=bridge.native.encode(bridge.native.decode_compatible(raw))
            expected=('Replace device project ' if action=='project_push' else 'Replace device slot ')+str(request['slot'])
            if request.get('confirmation')!=expected:raise ValueError('Confirm the exact device destination')
        if action=='project_save' and request.get('confirmation')!='Save device project '+str(request['slot']):
            raise ValueError('Confirm the exact project destination')
        if action in CONFIRM and request.get('confirmation')!=CONFIRM[action][0]:raise ValueError('Confirm the named device reset')
        with self.lock._lock():
            resume=self.recorder is not None and self.recorder.poll() is None
            self.stop_recording()
            if action=='community_capture':resume=False
            if action=='record':self.capture_battery=request.get('battery_telemetry',False)
            if action=='stop_recording':return dict(recording=False,path=str(self.capture) if self.capture else None)
            stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'-'+uuid.uuid4().hex[:8]
            journal=bridge.transport.Journal(self.root/'device-logs'/stamp)
            session=None;result=dict(success=False,action=action,identity=bridge.IDENTITY)
            try:
                progress('Connecting to FM-1',phase='connect')
                if action=='community_capture':
                    result.update(community.perform(hardware_bridge.WinMM(),journal,self.executable,progress))
                    return result
                if action=='probe':
                    api=hardware_bridge.WinMM();ports=api.enumerate()
                    if any(community.ENDPOINT.fullmatch(row['name']) for row in ports['inputs']):
                        if any(bridge.transport.PORT_NAME.fullmatch(row['name']) for row in ports['inputs']):
                            raise ValueError('Connect only the unit you want to manage; FMER and community units are both present')
                        result.update(community.probe(api,journal));return result
                session=bridge.transport.find_session(hardware_bridge.WinMM(),None,journal,wait=8,retry_identity_timeout=True)
                identity=session.verified_identity
                result['identity']=identity
                progress('Connected to '+identity,identity=identity,phase='connected')
                if action=='probe':
                    result.update(success=True,can_manage=identity in BRIDGES)
                    return result
                if identity not in BRIDGES:
                    raise ValueError('FM-1 is connected with '+identity+'. Install FMER to use instrument backups and library transfers. Stock firmware does not provide these commands.')
                progress('Preparing '+action.replace('_',' '),identity=identity,phase='prepare')
                self.record_identity=identity
                client=BRIDGES[identity].NativeBridge(session,journal);backups=self.root/'device-backups'
                if action in ('backup_all','restore_all','deploy_library'):
                    progress('Backing up the complete unit')
                    before=archive.capture(client,progress)
                    backup_path=journal.directory/'unit-backup.fmer-backup.json'
                    with backup_path.open('xb') as stream:
                        stream.write(library.canonical(before));stream.flush();os.fsync(stream.fileno())
                    result.update(backup=before,backup_path=str(backup_path))
                    if action=='restore_all':result['restore']=archive.restore(client,request['backup'],backups,progress)
                    elif action=='deploy_library':transfer.deploy(client,request['rows'],backups,progress,journal,result)
                elif action in ('instrument_rename','instrument_copy','instrument_swap'):
                    source,_=client.read_slot(request['slot'])
                    bridge.native.save_backup(source,backups,device_identity=identity,source='Before companion organize instrument source')
                    original,_=client.snapshot();original_backup=bridge.native.save_backup(original,backups,device_identity=identity,source='Working state before unit organization')
                    result['working_backup']=original_backup;result['completed']=[]
                    dest=request.get('destination',request['slot']);other=None
                    if action=='instrument_swap':
                        other,_=client.read_slot(dest)
                        bridge.native.save_backup(other,backups,device_identity=identity,source='Before companion swap destination')
                    if action=='instrument_rename':
                        state=bridge.native.decode(source);state['vced'][145:]=list(request['name'].ljust(10).encode('ascii'));source=bridge.native.encode(state)
                    try:
                        progress(f'Writing instrument slot {dest}')
                        client.push_slot(source,dest,backups);result['completed'].append(dest)
                        journal.record('organize_slot_verified',slot=dest)
                        if other:
                            progress(f'Writing instrument slot {request["slot"]}')
                            client.push_slot(other,request['slot'],backups);result['completed'].append(request['slot'])
                            journal.record('organize_slot_verified',slot=request['slot'])
                    finally:result['working_restore']=client.restore(original,backups)
                    result['project_references_remapped']=False
                elif action=='battery_history':result['battery_history']=client.battery_history()
                elif action=='midi_read':result['midi']=client.midi_status()
                elif action=='midi_set':result['midi']=client.midi_configure(request['settings'],persist=request.get('persist',False),backup_directory=backups)
                elif action in ('catalog','record'):result.update(client.list_slots())
                elif action=='project_catalog':result.update(client.list_projects())
                elif action=='project_pull':
                    saved=client.export_project(request['slot'],backups);wire=Path(saved['backup']['path']).read_bytes()
                    result.update(raw=base64.b64encode(wire).decode('ascii'),backup=saved)
                elif action=='project_push':result.update(client.push_project(raw,request['slot'],backups))
                elif action=='project_load':result.update(client.load_project(request['slot'],backups))
                elif action=='project_save':result.update(client.save_project(request['slot'],backups))
                elif action=='pull':
                    saved=client.export_slot(request['slot'],backups);wire=Path(saved['backup']['path']).read_bytes()
                    result.update(raw=base64.b64encode(wire).decode('ascii'),backup=saved)
                elif action=='push':result.update(client.push_slot(raw,request['slot'],backups))
                elif action=='load':result.update(client.load_slot(request['slot'],backups))
                else:
                    originals=[base64.b64decode(p['native']) for p in bank.profile(self.executable)]
                    result.update(client.reset_bank(CONFIRM[action][1],backups,originals))
                result['success']=True
            except Exception as error:
                result['error']=repr(error);raise
            finally:
                if session is not None:
                    try:failures=session.close()
                    except Exception as error:failures=[repr(error)]
                    if failures:result.update(success=False,cleanup_errors=failures)
                result['artifacts']=str(journal.directory)
                journal.record('companion_device_result',**result)
                (journal.directory/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');journal.close()
                if not result.get('cleanup_errors') and (resume or (action=='record' and result['success'])):
                    try:result['capture']=self.start_recording()
                    except Exception as error:
                        if action=='record':raise
                        result['capture_warning']=str(error)
            if not result['success']:raise RuntimeError('Device cleanup failed; see '+result['artifacts'])
            return result
