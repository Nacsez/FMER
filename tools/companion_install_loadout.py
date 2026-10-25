"""One guarded install + loadout operation using existing updater/native transports."""
from pathlib import Path
import os
import time
import companion_archive as archive
import companion_device
import companion_loadouts
import companion_transfer
import fm1_flash_transport as flash
import unit_endpoints
import library

def preserved_rows(before, after, requested):
    """Materialize inherited sounds that a firmware-default change would replace."""
    if before is None:return []
    import companion_bank as bank
    destinations={r['slot'] for r in requested if r['kind']=='instrument'}
    result=[]
    for slot,(old,new) in enumerate(zip(before['payload']['instruments'],after['payload']['instruments'])):
        if slot in destinations or old is None:continue
        state=bank.decode_record(old)
        if new is not None:
            old_sound=bank.native.canonical_sound(state)
            new_sound=bank.native.canonical_sound(bank.decode_record(new))
            old_sound['source_generation']=new_sound['source_generation']
            if old_sound==new_sound:continue
        name=''.join(chr(c) for c in state['vced'][145:]);name=name.rstrip() or name
        entry=dict(name=name,category='Custom',favorite=False,audition_note=60,native=bank.pack(state))
        bank.BankLibrary.validate_entry(entry)
        result.append(dict(kind='instrument',slot=slot,entry=entry))
    return result

def run(api,package,journal,request,directory,progress,checkpoint):
    checked=companion_loadouts.bank_assignment(request) if request is not None else dict(rows=[],title='Keep existing instruments')
    if request is not None and request.get('confirmation')!=checked['plan']['confirmation']:raise ValueError('Review and confirm the exact loadout destinations')
    # Bind this multi-stage job to one physical port before backup or updater entry.
    rows=unit_endpoints.annotate(api,api.enumerate())
    candidates=[x for x in rows['inputs'] if flash.PORT_NAME.fullmatch(x['name'])]
    if len(candidates)!=1:raise ValueError('Connect only the intended FM-1 for installation with a loadout')
    locations=[p for p in candidates[0].get('location_paths',[]) if p.startswith('PCIROOT(')]
    if not locations:raise ValueError('Cannot establish the instrument USB location; no firmware was written')
    api.target_location=max(locations,key=len)
    unit_endpoints.filter_location(rows,api.target_location)
    result=dict(firmware_installed=False,loadout_complete=False,profile_title=checked['title'],completed=[])
    directory=Path(directory);before=None
    def capture(client,name):
        value=archive.capture(client,progress)
        path=directory/name/'unit-backup.fmer-backup.json';path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(library.canonical(value));stream.flush();os.fsync(stream.fileno())
        return value,str(path)
    session=flash.find_session(api,None,journal,wait=8,retry_identity_timeout=True)
    try:
        identity=session.verified_identity
        if identity=='FM-1_735' and package.report['product'] in ('FM-1_733','FM-1_734'):
            raise ValueError('This instrument has native12 saved data. Export a complete backup and keep firmware735 or newer; an older-firmware storage migration is not yet supported. No firmware was written.')
        if identity in companion_device.BRIDGES:
            progress('Backing up instruments and projects before installation')
            before,path=capture(companion_device.BRIDGES[identity].NativeBridge(session,journal),'before-install')
            result.update(backup_path=path);checkpoint(result)
        else:
            result['pre_install_backup_unavailable']='Native backup unavailable for '+identity
            checkpoint(result)
    finally:
        if session.close():raise RuntimeError('Could not close backup connection; installation stopped')
    flash.perform_update(api,package,journal)
    result['firmware_installed']=True;checkpoint(result)
    session=flash.find_session(api,package.report['product'],journal,wait=15,retry_identity_timeout=True)
    try:
        client=companion_device.native_client(session.verified_identity,session,journal)
        # A first installation may still be initializing its writable banks
        # after USB identity returns. Do not mistake that for transfer readiness.
        for attempt in range(240):
            status=client.store_status()
            if status.get('ready') == 1 and not status.get('busy'):break
            progress('Waiting for instrument banks to finish initializing')
            time.sleep(.25)
        else:raise TimeoutError('Firmware installed, but instrument banks did not become ready; no loadout slots were written')
        progress('Backing up installed banks before applying '+checked['title'])
        after,path=capture(client,'before-loadout')
        result['post_install_backup_path']=path
        result.setdefault('backup_path',path);checkpoint(result)
        # Preserve pre-install working state when available; all destination
        # records are captured again after reboot before the first slot write.
        result['backup']=before or after
        try:
            preserved=preserved_rows(before,after,checked['rows'])
            result['preserved_inherited_slots']=[r['slot'] for r in preserved]
            rows=preserved+checked['rows']
            if rows:companion_transfer.deploy(client,rows,directory/'slot-backups',progress,journal,result)
            elif before:
                import base64
                result['working_restore']=client.restore(base64.b64decode(before['payload']['live']),directory/'slot-backups')
            result['loadout_complete']=True
        finally:
            result.pop('backup',None);checkpoint(result)
    finally:
        if session.close():raise RuntimeError('Instrument connection cleanup failed; inspect the operation record')
    return result
