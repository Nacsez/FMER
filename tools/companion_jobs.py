"""One durable, inspectable device job at a time. No device work on page load."""
from copy import deepcopy
from datetime import datetime,timezone
import base64
import hashlib
import json
import os
import re
from pathlib import Path
import threading
import traceback
import time
import companion_errors
import companion_stock
import uuid
import companion_archive as archive
import fm1_flash_transport as flash
import fm1_package
import hardware_bridge
import library
import release_firmware
import compatible_firmware


class Jobs:
    def __init__(self,device,root):
        self.device=device;self.root=Path(root);self.guard=threading.RLock();self.jobs={};self.active=None;self.packages={};self.closing=False

    def capabilities(self):
        return dict(platform=os.name,device_transport='Windows WinMM' if os.name=='nt' else 'Not yet packaged for this platform',
                    device_available=os.name=='nt',firmware='FMER734 native 11', firmware_identity='FM-1_734', native_version=11, voice_modes={'synth': '1-4 voices, one sound', 'tracks': '4 mono tracks, one voice each'},
                    individual_device_delete=False,project_names_on_unit=False,
                    flash_scope='Install FMER or a custom application using the reviewed935 updater and protected layout. The connected unit must pass layout/calibration checks; application behavior and library commands remain separate qualifications.',
                    bundled_firmware=release_firmware.available(),
                    library_local=True,help_offline=True)

    def inspect(self,request):
        library.fields(request,{'action','raw','release'},'firmware inspection')
        if request.get('release'):
            if 'raw' in request:raise ValueError('Choose bundled firmware or a file, not both')
            raw=release_firmware.bundled(request['release'])
        else:
            if not isinstance(request.get('raw'),str) or len(request['raw'])>2*1024*1024:raise ValueError('Firmware file is too large')
            raw=base64.b64decode(request['raw'],validate=True)
        official=companion_stock.known_file_info(raw)
        if official is not None:
            # A recognized publisher asset is useful information, not permission
            # to rewrite a different flash layout. No install token is issued.
            return {**official,'limitation':official['reason'],'stock_restore':request.get('action')=='inspect_stock'}
        if request.get('action')=='inspect_stock':
            report=companion_stock.prepare(raw).report
        else:
            report=release_firmware.inspect_bytes(raw)
            if report is None:
                # Unknown files get a readable compatibility result. No legacy
                # private-evidence lookup and no install token on rejection.
                try:report=compatible_firmware.inspect_bytes(raw)
                except ValueError as error:
                    return dict(product='Selected firmware',installable=False,
                        compatibility='Not compatible with this installer',
                        limitation=str(error),package_sha256=hashlib.sha256(raw).hexdigest())
        token=uuid.uuid4().hex;directory=self.root/token;directory.mkdir(parents=True,exist_ok=False)
        path=directory/'package.fwsc';path.write_bytes(raw)
        report.update(inspection=token,installable=bool(report['runtime_preflight_qualified'] and os.name=='nt'),
                      limitation='Restores the supported original application only; device identity and calibration are preserved. This does not restore original user settings.' if report.get('stock_restore') else 'Checks the unit memory layout and calibration before replacing the application. Stock patch export is not supported. Keep power and USB connected.' if report.get('release_profile') else 'An unqualified or mismatched package cannot be installed. Development packages require their complete review evidence.')
        if report.get('compatible_profile'):
            report['limitation']='Custom firmware: updater and memory layout are compatible, but this application has not been tested as an FMER release. Back up all sounds and projects first. The application may interpret saved data differently, and Companion library management requires FMER 733 or 734. Install only firmware from a source you trust.'
        (directory/'inspection.json').write_bytes(library.canonical(report));self.packages[token]=(path,report)
        return report

    def _save(self,job):
        directory=self.root/job['id'];directory.mkdir(parents=True,exist_ok=True)
        destination=directory/'job.json';temp=directory/'job.pending.json'
        with temp.open('wb') as stream:stream.write(library.canonical(job));stream.flush();os.fsync(stream.fileno())
        os.replace(temp,destination)

    def status(self,identifier):
        with self.guard:
            if not re.fullmatch(r'[a-f0-9]{32}',identifier):raise ValueError('Unknown operation')
            if identifier not in self.jobs:
                path=self.root/identifier/'job.json'
                if not path.is_file():raise ValueError('Unknown operation')
                job=library.strict_loads(path.read_bytes())
                if job['state']=='running':
                    job.update(state='interrupted',message='Server stopped during this operation; inspect device state before retrying',error='Operation interrupted; no automatic retry')
                    self._save(job)
                self.jobs[identifier]=job
            return deepcopy(self.jobs[identifier])

    def backup(self,identifier):
        job=self.status(identifier)
        value=job.get('progress',{}).get('backup_path')
        if not isinstance(value,str):raise ValueError('No pre-transfer backup is available for this operation')
        path=Path(value).resolve()
        root=(self.device.root/'device-logs').resolve()
        if not path.is_relative_to(root) or path.name!='unit-backup.fmer-backup.json':
            raise ValueError('Backup is outside the operation archive')
        raw=path.read_bytes()
        if len(raw)>library.MAX_FILE_BYTES:raise ValueError('Backup exceeds size limit')
        value=library.strict_loads(raw);archive.validate(value)
        return value

    def start(self,request):
        library.fields(request,{'action','request','inspection','confirmation'},'operation')
        library.choice(request.get('action'),{'device','install'},'operation')
        if request['action']=='device':
            req=request.get('request')
            if not isinstance(req,dict):raise ValueError('Missing device operation')
            if req.get('action') not in {'probe','backup_all','restore_all','deploy_library','instrument_rename','instrument_copy','instrument_swap','pull','push','load','project_pull','project_push','project_load','project_save','catalog','project_catalog','record','stop_recording','battery_history','midi_read','midi_set','reset_defaults','reset_user','clear_user'}:raise ValueError('Unsupported device operation')
            if req['action']=='restore_all':archive.validate(req.get('backup'))
        else:
            selected=self.packages.get(request.get('inspection'))
            if not selected or not selected[1]['installable']:raise ValueError('Select a qualified firmware package first')
            if request.get('confirmation')!='Install '+selected[1]['product']:raise ValueError('Confirm the exact firmware target')
        with self.guard:
            if self.closing:raise library.LibraryConflict('Companion is closing. Reopen it to continue.')
            if self.active is not None:raise library.LibraryConflict('A device operation is already running')
            identifier=uuid.uuid4().hex
            job=dict(id=identifier,action=request['action'],state='running',message='Preparing operation',operation=request.get('request',{}).get('action',request['action']),progress={},created=datetime.now(timezone.utc).isoformat(),result=None,error=None)
            self.jobs[identifier]=job;self.active=identifier;self._save(job)
            threading.Thread(target=self._run,args=(identifier,deepcopy(request)),daemon=True).start()
            return deepcopy(job)

    def _run(self,identifier,request):
        def progress(message,**details):
            with self.guard:
                self.jobs[identifier].update(message=message,progress=details)
                if details.get('identity'):self.jobs[identifier]['identity']=details['identity']
                self._save(self.jobs[identifier])
        try:
            if request['action']=='device':result=self.device.dispatch(request['request'],progress)
            else:
                path,report=self.packages[request['inspection']]
                package=companion_stock.prepare(path.read_bytes()) if report.get('stock_restore') else flash.qualify_package(path,report['package_sha256'],report['loader_sha256'])
                if not report.get('stock_restore'):flash.require_write_qualification(package) # Recheck all pins immediately before port access.
                if os.name!='nt':raise ValueError('Firmware transport is currently qualified on Windows only')
                with self.device.lock._lock():
                    self.device.stop_recording()
                    progress('Preparing firmware installation')
                    last_progress=[0.0]
                    def update_progress(event,**values):
                        if event=='identity':progress('Connected to '+values['identity'],identity=values['identity'])
                        elif event=='compatibility_metadata':progress('Device compatibility details collected',metadata=values['metadata'])
                        elif event=='metadata_page':
                            with self.guard:self.jobs[identifier].setdefault('diagnostics',{}).setdefault('metadata_pages',[]).append(values)
                            progress('Reading compatibility details',done=values['page']+1,total=20,unit='pages')
                        elif event=='update_phase':progress(values['phase'],phase=values['phase'])
                        elif event=='accepted_request' and (time.monotonic()-last_progress[0]>.2 or values.get('terminal')):
                            last_progress[0]=time.monotonic()
                            progress('Preparing updater' if values['stage']==1 else 'Transferring firmware',
                                     done=values['covered_required_bytes'],total=values['required_bytes'],unit='bytes',stage=values['stage'])
                    journal=flash.Journal(self.root/identifier/'flash',progress=update_progress)
                    try:
                        if report.get('stock_restore'):companion_stock.perform(hardware_bridge.WinMM(),path.read_bytes(),journal)
                        else:flash.perform_update(hardware_bridge.WinMM(),package,journal)
                        result=dict(success=True,firmware=report['product'],package_sha256=report['package_sha256'],journal=str(journal.directory))
                    finally:journal.close()
            with self.guard:self.jobs[identifier].update(state='complete',message='Operation complete',result=result)
        except Exception as e:
            with self.guard:self.jobs[identifier].update(state='failed',message='Operation stopped. Your diagnostic record has been saved.',error=(str(e)+' The instrument stopped responding while preparing the updater. Close other MIDI apps, power the unit off and on, reconnect it, then Check connection before retrying. If it repeats, export this operation record; changing cables is unlikely to help.' if 'Stage 1 timed out' in str(e) else str(e)),traceback=traceback.format_exc())
        finally:
            with self.guard:
                job=self.jobs[identifier]
                if job['state']=='failed':job['outcome']=companion_errors.explain(job.get('error',''),bool(job.get('progress',{}).get('metadata')))
                self.jobs[identifier]['finished']=datetime.now(timezone.utc).isoformat();self.active=None;self._save(self.jobs[identifier])
