# SPDX-License-Identifier: GPL-3.0-only
"""Read-only FM6 catalog capture using reviewed Felucca-family editor commands.

Only INFO(1), FM6_LIST(70), FM6_GET(68) are emitted. No preset selection,
WATCH, playback, backup-stop, flash or native restore commands are allowed.
This deliberately does not claim to back up a complete foreign instrument.
"""
import hashlib
import re
import time
from datetime import datetime, timezone

import companion_bank as bank
import companion_dx7 as dx7
import companion_soundpacks as packs
import fm1_stock_catalog as stock
import library

PREFIX=b'\xf0\x7dFL'
ENDPOINT=re.compile(r'(?i)(?:\d+- )?(?:Felucca|SLOOP|JIANT)(?:[ -].*)?(?: \(\d+\))?')


def info(data):
    """Decode the bounded common INFO prefix; family tags remain distinct."""
    if not isinstance(data,bytes) or not 8<=len(data)<=1000 or any(x>127 for x in data):
        raise ValueError('Malformed community INFO response')
    cursor=0
    def string():
        nonlocal cursor
        end=data.find(b'\0',cursor)
        if end<0 or end-cursor>80:raise ValueError('Malformed INFO string')
        raw=data[cursor:end];cursor=end+1
        if any(x<32 for x in raw):raise ValueError('Nonprinting INFO string')
        return raw.decode('ascii')
    version=string()
    if cursor+5>len(data):raise ValueError('Incomplete INFO')
    engines,params,globals_,steps,e0=data[cursor:cursor+5];cursor+=5
    if not 1<=engines<=24 or not 8<=params<=127 or e0!=params-8 or not 1<=steps<=64:
        raise ValueError('Unsupported community parameter layout')
    names=[string() for _ in range(engines)]
    if 'FM6' not in names or cursor>=len(data) or data[cursor]!=4:
        raise ValueError('This firmware does not advertise the reviewed FM6 protocol')
    trailer=data[cursor+1:];upper=version.upper()
    if 'SLOOP' in upper:
        family='SLOOP'
        if not trailer or not 9<=trailer[0]<=12:raise ValueError('Unsupported SLOOP protocol version')
    elif 'JIANT' in upper:
        family='JIANT'
    elif upper.startswith('FELUCCA'):
        family='Felucca'
    else:raise ValueError('Unknown community firmware family; no patch commands were sent')
    if family!='SLOOP' and b'\x46\x01\x08\x00' not in trailer:
        raise ValueError('Expected eight-factory-voice FM6 capability is absent')
    return dict(family=family,version=version,engines=names,trailer=list(trailer))


def listing(data):
    if len(data)<2 or data[0]!=8 or data[1] not in (0,27):
        raise ValueError('Unrecognized FM6 list counts')
    cursor=2;rows=[]
    for i in range(sum(data[:2])):
        if cursor>=len(data) or data[cursor] not in (0,1):raise ValueError('Malformed FM6 list')
        used=data[cursor];cursor+=1;end=data.find(b'\0',cursor)
        if end<0 or end-cursor>10 or any(not 32<=x<=126 for x in data[cursor:end]):
            raise ValueError('Malformed FM6 patch name')
        rows.append(dict(used=bool(used),name=data[cursor:end].decode('ascii')));cursor=end+1
    if cursor!=len(data):raise ValueError('Unexpected FM6 list extension')
    return rows


class Reader:
    def __init__(self,session):self.session=session

    def request(self,command,args=b''):
        if command not in (1,68,70) or (command!=68 and args) or (command==68 and (len(args)!=2 or args[0]>3 or args[1]>31)):
            raise ValueError('Only bounded read-only FM6 requests are permitted')
        self.session._send(PREFIX+bytes([command])+args+b'\xf7','community_fm6_read')
        deadline=time.monotonic()+3
        for _ in range(64):
            frame=self.session.read(max(0,deadline-time.monotonic()))
            if frame is None:break
            if frame.startswith(PREFIX+bytes([command])):
                if not frame.endswith(b'\xf7') or any(x>127 for x in frame[1:-1]):raise ValueError('Malformed community reply')
                payload=frame[5:-1]
                if command==68 and payload[:2]!=args:raise ValueError('FM6 reply belongs to a different slot')
                return payload
            if time.monotonic()>=deadline:break
        raise ValueError('Community FM6 read timed out. No firmware or patch was written.')


def capture(reader,identity,progress=lambda *a,**k:None):
    if identity not in ('FM-1_916','FM-1_900'):
        raise ValueError('Readback currently supports Felucca 1.6.1, SLOOP 2.7.1 and the reviewed JIANT family. For FMER use its normal backup; for stock V15 use OEM Patches.')
    header=reader.request(1);details=info(header)
    if (identity=='FM-1_916')!=(details['family']=='Felucca'):
        raise ValueError('Device identity and editor family disagree')
    first=reader.request(70);listed=listing(first)
    family=details['family'];bank_count=first[1]
    if (family=='SLOOP' and bank_count!=27) or (family!='SLOOP' and bank_count!=0):
        raise ValueError('FM6 bank count disagrees with the selected family')
    targets=[(2,i) for i in range(8) if listed[i]['used']]
    targets += [(1,i) for i in range(bank_count) if listed[8+i]['used']]
    targets += [(0,i) for i in range(3 if family=='SLOOP' else 4)]
    if family!='SLOOP' and b'\x50\x01\x03' in bytes(details['trailer']):targets += [(3,i) for i in range(32)]
    rows=[];empty=[]
    for n,(target,index) in enumerate(targets):
        progress('Reading '+family+' FM voices',done=n,total=len(targets),unit='slots')
        args=bytes([target,index]);reply=reader.request(68,args)
        if len(reply)<3 or reply[:2]!=args:raise ValueError('Wrong FM6 reply slot')
        if reply[2]==2 and len(reply)==3:
            if target in (1,2):raise ValueError('Listed voice disappeared; retry with controls untouched')
            empty.append([target,index]);continue
        if len(reply)!=131 or reply[2]!=0:raise ValueError('FM6 read refused or incomplete')
        packed=reply[3:];voice=stock.unpack_voice(packed)
        if stock.normalize(voice)[1]:raise ValueError('Community voice exceeds DX7 ranges; raw operation log retained')
        if reader.request(68,args)!=reply:raise ValueError('Voice changed during capture; retry with controls untouched')
        rows.append(dict(target=target,index=index,packed=list(packed),sha256=hashlib.sha256(packed).hexdigest()))
    if reader.request(1)!=header or reader.request(70)!=first:
        raise ValueError('Firmware/catalog changed during capture; no library import was made')
    body=dict(format='FMER-COMMUNITY-FM6',version=1,identity=identity,source=details,
              captured=datetime.now(timezone.utc).isoformat(),voices=rows,empty=empty,
              scope='FM6 voices only; not a full native backup. No device writes. Felucca/JIANT separate 32-voice cartridge is not included.')
    progress('FM voice capture complete',done=len(targets),total=len(targets),unit='slots')
    return dict(payload=body,sha256=hashlib.sha256(library.canonical(body)).hexdigest())


def decode(archive,defaults,codec):
    if not isinstance(archive,dict) or set(archive)!={'payload','sha256'}:raise ValueError('Invalid community archive')
    body=archive['payload']
    if hashlib.sha256(library.canonical(body)).hexdigest()!=archive['sha256']:raise ValueError('Community archive checksum mismatch')
    if body.get('format')!='FMER-COMMUNITY-FM6' or body.get('version')!=1 or not isinstance(body.get('voices'),list) or not 1<=len(body['voices'])<=128:
        raise ValueError('Unsupported community capture')
    family=body.get('source',{}).get('family')
    if family not in ('Felucca','SLOOP','JIANT'):raise ValueError('Unknown archive source')
    entries=[];notes=[];seen=set()
    for row in body['voices']:
        if type(row.get('target')) is not int or type(row.get('index')) is not int or not 0<=row['target']<=3 or not 0<=row['index']<=31:raise ValueError('Invalid source slot')
        slot=(row['target'],row['index'])
        if slot in seen:raise ValueError('Duplicate source slot')
        seen.add(slot);raw=bytes(row['packed'])
        if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Voice checksum mismatch')
        voice=stock.unpack_voice(raw)
        if stock.normalize(voice)[1]:raise ValueError('Invalid community voice range')
        entries.extend(dx7.decode(codec.encode([voice]),bank.decode_record(defaults[0]['native']),codec)['entries'])
        notes.append(f'{family} FM6 capture. Target {slot[0]}, index {slot[1]}; source archive SHA-256 {archive["sha256"]}. FM voice only; source engine/FX/project not converted. Imported instruments retain their authors\' rights.')
    return dict(catalog=packs.catalog(entries,family+' FM6',archive['sha256'],[family,'FM6'],notes),count=len(entries),losses=list(dx7.LOSSES))


def open_session(api,journal):
    import fm1_flash_transport as transport
    import unit_endpoints
    endpoints=unit_endpoints.annotate(api,api.enumerate())
    selected={d:[r for r in endpoints[d] if ENDPOINT.fullmatch(r['name'])] for d in ('inputs','outputs')}
    if any(len(selected[d])!=1 for d in selected):
        raise ValueError('Connect one Felucca, SLOOP or JIANT unit for community FM capture. FMER uses its normal backup; OEM V15 voices are available in Included sounds.')
    pair=(selected['inputs'][0],selected['outputs'][0])
    if not pair[0].get('interface_sha256') or pair[0]['interface_sha256']!=pair[1].get('interface_sha256'):
        raise ValueError('Cannot verify a matching physical input/output pair')
    session=transport.FlashSession(api,pair,journal)
    session.__enter__()
    return session


def probe(api,journal):
    session=open_session(api,journal)
    try:
        identity=session.identify()
        if identity not in ('FM-1_916','FM-1_900'):raise ValueError('Unsupported community identity')
        details=info(Reader(session).request(1))
        if (identity=='FM-1_916')!=(details['family']=='Felucca'):raise ValueError('Device identity and editor family disagree')
        return dict(success=True,identity=identity,can_manage=False,community_capture=True,community=details)
    finally:
        if session.close():raise RuntimeError('Community MIDI cleanup failed')


def perform(api,journal,executable,progress):
    session=open_session(api,journal)
    try:
        identity=session.identify()
        archive=capture(Reader(session),identity,progress)
        path=journal.directory/'community-fm6.json'
        # Preserve original wire voices before conversion; caller reviews import.
        path.write_bytes(library.canonical(archive))
        defaults=bank.profile(executable)
        result=decode(archive,defaults,library.PatchCodec(executable,lambda *a,**k:None))
        return dict(result,archive=archive,archive_path=str(path),identity=identity,success=True)
    finally:
        if session.close():raise RuntimeError('Community MIDI cleanup failed; export operation record')
