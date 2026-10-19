"""Checksummed unit snapshots and explicit, journaled restore overlays.

Blank destinations are represented but are never silently erased: firmware721
has bank-wide clears, not individual tombstones. No automatic retries on writes.
"""
import base64
import hashlib
from datetime import datetime, timezone
import companion_bank as bank
import library


def encode(raw):return base64.b64encode(raw).decode('ascii')
def decode(value):return bank.native.encode(bank.decode_record(value))
def seal(payload):
    return dict(format='FMER-UNIT-BACKUP',version=1,payload=payload,sha256=hashlib.sha256(library.canonical(payload)).hexdigest())


def validate(value):
    if not isinstance(value,dict) or set(value)!={'format','version','payload','sha256'} or value['format']!='FMER-UNIT-BACKUP' or type(value['version']) is not int or value['version']!=1:raise ValueError('Unsupported unit backup')
    p=value['payload'];raw=library.canonical(p)
    if len(raw)>library.MAX_FILE_BYTES or hashlib.sha256(raw).hexdigest()!=value['sha256']:raise ValueError('Unit backup checksum mismatch')
    if not isinstance(p,dict) or set(p) not in ({'identity','created','instruments','projects','live','midi'},{'identity','created','instruments','projects','live','midi','fx_default'}) or p['identity'] not in ('FM-1_721','FM-1_722','FM-1_723','FM-1_724','FM-1_725','FM-1_726','FM-1_727','FM-1_728','FM-1_729','FM-1_730','FM-1_731','FM-1_733','FM-1_734'):raise ValueError('Backup requires FMER721-734')
    if 'fx_default' in p and (type(p['fx_default']) is not int or not 0<=p['fx_default']<720):raise ValueError('Invalid personal FX default')
    datetime.fromisoformat(p['created'])
    for key,size in (('instruments',128),('projects',16)):
        if not isinstance(p[key],list) or len(p[key])!=size:raise ValueError('Incomplete unit backup')
        for record in p[key]:
            if record is not None:decode(record)
    if any(x is None for x in p['instruments'][64:]):raise ValueError('DEFAULT device slots must remain populated')
    decode(p['live'])
    import fm1_native_bridge_v18 as bridge
    bridge.midi_settings_request(p['midi'],0)
    return p


def capture(client, progress=lambda *args,**kwargs:None):
    before=client.store_status();client._idle_store(before)
    live,state=client.snapshot();midi=client.midi_status()
    identity=client.session.verified_identity
    if not isinstance(identity,str):raise ValueError('Unit identity was not verified before backup')
    payload=dict(identity=identity,created=datetime.now(timezone.utc).isoformat(),instruments=[],projects=[],live=encode(live),midi=midi['settings'])
    payload['fx_default']=before.get('fx_default',0)
    for key,count,catalog,read in (('instruments',128,client.slot_catalog,client.read_slot),('projects',16,client.project_catalog,client.read_project)):
        for i in range(count):
            progress(f'Reading {key} {i+1}/{count}',done=i+(128 if key=='projects' else 0),total=144,unit='slots')
            payload[key].append(encode(read(i)[0]) if catalog(i)['present'] else None)
    after=client.store_status();client._idle_store(after)
    if (before['generation'],before['job'])!=(after['generation'],after['job']) or state['live_generation']!=client.status()['live_generation'] or midi['settings']!=client.midi_status()['settings']:raise RuntimeError('Unit changed during backup; nothing may be restored from this incomplete capture')
    result=seal(payload);validate(result);return result


def plan(value):
    p=validate(value)
    return dict(instruments=sum(x is not None for x in p['instruments']),projects=sum(x is not None for x in p['projects']),
                empty_instruments=sum(x is None for x in p['instruments']),empty_projects=sum(x is None for x in p['projects']),
                scope='Restore populated slots, working state, persistent MIDI and personal FX default (when present). Older backups leave the default unchanged. Empty source slots leave destination contents unchanged. This is an overlay, not an erase or factory reset.',sha256=value['sha256'])


def restore(client,value,directory,progress=lambda *args,**kwargs:None):
    p=validate(value);completed=[]
    # The caller commits a complete destination backup before entering here.
    for key,write in (('instruments',client.push_slot),('projects',client.push_project)):
        for slot,record in enumerate(p[key]):
            if record is None:continue
            progress(f'Restoring {key} {slot}',completed=completed,done=len(completed),total=sum(x is not None for k in ('instruments','projects') for x in p[k]),unit='slots')
            write(decode(record),slot,directory)
            completed.append(dict(kind=key,slot=slot))
            progress(f'Verified {key} {slot}',completed=list(completed))
    progress('Restoring working state and MIDI',completed=completed)
    if 'fx_default' in p:client.save_fx_default(p['fx_default'],directory)
    client.restore(decode(p['live']),directory)
    client.midi_configure(p['midi'],persist=True,backup_directory=directory)
    return dict(completed=completed,empty_slots_preserved=True,working_state_restored=True,midi_restored=True)
