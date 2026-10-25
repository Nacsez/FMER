"""Ordered, self-contained instrument profiles. Local persistence; no MIDI on import."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import uuid
import library
import companion_bank as bank
from companion_shelf import text
import companion_transfer as transfer

FORMAT = 'FMER-LOADOUT'
CAPACITY = 12
ROOT = Path(__file__).resolve().parents[1]

def sound(entry, title=None, notes=''):
    return dict(entry=deepcopy(entry), title=title or entry['name'], notes=notes)

def validate_sound(value):
    if not isinstance(value,dict) or set(value)!={'entry','title','notes'}:raise ValueError('Incomplete loadout instrument')
    bank.BankLibrary.validate_entry(value['entry'])
    text(value['title'],80,'Instrument title');text(value['notes'],1000,'Instrument notes',True)

def validate(profile):
    if not isinstance(profile,dict) or set(profile)!={'id','title','description','slots'}:raise ValueError('Incomplete loadout profile')
    text(profile['id'],80,'Profile identity');text(profile['title'],80,'Profile title')
    text(profile['description'],1000,'Profile description',True)
    if not isinstance(profile['slots'],list) or len(profile['slots'])!=64:raise ValueError('A loadout contains exactly 64 instruments; fill every slot')
    for value in profile['slots']:validate_sound(value)
    return profile

def seal(profile):
    validate(profile)
    return dict(format=FORMAT,version=1,payload=deepcopy(profile),sha256=hashlib.sha256(library.canonical(profile)).hexdigest())

def unpack(value):
    if not isinstance(value,dict) or set(value)!={'format','version','payload','sha256'} or value['format']!=FORMAT or type(value['version']) is not int or value['version']!=1:raise ValueError('Choose an FMER loadout profile file')
    if hashlib.sha256(library.canonical(value['payload'])).hexdigest()!=value['sha256']:raise ValueError('Loadout checksum mismatch')
    return deepcopy(validate(value['payload']))

def deployment(request):
    library.fields(request,{'profile','bank','confirmation'},'loadout deployment')
    profile=unpack(request.get('profile'))
    destination=request.get('bank');library.choice(destination,{'default','user','both'},'loadout destination')
    starts=[64] if destination=='default' else [0] if destination=='user' else [64,0]
    rows=[dict(kind='instrument',slot=start+i,entry=deepcopy(s['entry'])) for start in starts for i,s in enumerate(profile['slots'])]
    plan=transfer.plan(rows)
    return dict(profile=profile,rows=rows,plan=plan)

def bank_assignment(request):
    """Two independent 64-sound blocks; None means preserve that bank."""
    library.fields(request,{'default','user','confirmation'},'bank assignments')
    rows=[];titles=[]
    for name in ('default','user'):
        if request.get(name) is not None:
            checked=deployment(dict(profile=request[name],bank=name))
            rows.extend(checked['rows']);titles.append(('Bank A' if name=='default' else 'Bank B')+': '+checked['profile']['title'])
    if not rows:raise ValueError('Choose a profile for at least one bank')
    return dict(title='; '.join(titles),rows=rows,plan=transfer.plan(rows))

def included(defaults):
    value=json.loads((ROOT/'host/loadout_profiles.json').read_text(encoding='utf8'))
    if value.get('format')!='FMER-INCLUDED-LOADOUTS' or value.get('version')!=1:raise ValueError('Unsupported included loadouts')
    sounds=value['sounds']
    for item in sounds.values():validate_sound(item)
    profiles=[dict(id=p['id'],title=p['title'],description=p['description'],slots=[deepcopy(sounds[i]) for i in p['sound_ids']]) for p in value['profiles']]
    defaults=json.loads((ROOT/'host/classic_loadout.json').read_text(encoding='utf8'))
    profiles.append(dict(id='classic',title='FMER Classic',description='The 64 legacy instruments from firmware734. GPL-3.0-only.',slots=[sound(e,notes='Original FMER default; GPL-3.0-only.') for e in defaults]))
    for p in profiles:validate(p)
    return profiles,list(sounds.values())

class Profiles(library.PatchLibrary):
    def __init__(self,root,executable,defaults):
        super().__init__(root,executable)
        self.included,self.sounds=included(defaults)

    def _empty(self):return dict(format='FMER-LOADOUTS',version=1,capacity=CAPACITY,revision=0,slots=[],undo_slots=None)

    def _validate_state(self,state):
        if not isinstance(state,dict) or set(state)!=set(self._empty()) or state['format']!='FMER-LOADOUTS' or state['version']!=1 or state['capacity']!=CAPACITY:raise ValueError('Unsupported profile library')
        library.integer(state['revision'],0,2**53-1,'revision')
        for field in ('slots','undo_slots'):
            items=state[field]
            if items is None and field=='undo_slots':continue
            if not isinstance(items,list) or len(items)>CAPACITY:raise ValueError('12 saved profiles available; export a profile before deleting it to make room')
            for p in items:
                validate(p)
                if str(uuid.UUID(p['id']))!=p['id']:raise ValueError('Invalid saved profile identity')
            if len({p['id'] for p in items})!=len(items):raise ValueError('Duplicate profile identity')

    def snapshot(self):return {**super().snapshot(),'included':deepcopy(self.included),'sounds':deepcopy(self.sounds)}

    def get(self,identifier):
        found=[p for p in self._read()['slots']+self.included if p['id']==identifier]
        if len(found)!=1:raise ValueError('Profile missing; refresh the list')
        return deepcopy(found[0])

    def dispatch(self,request):
        library.fields(request,{'action','revision','id','profile','file','title','confirmation'},'loadout request')
        action=request.get('action')
        if action=='export':return seal(self.get(request.get('id')))
        library.choice(action,{'save','copy','import','delete','undo'},'loadout action')
        def change(state):
            items=deepcopy(state['slots'])
            if action=='undo':
                if state['undo_slots'] is None:raise ValueError('Nothing to undo')
                return deepcopy(state['undo_slots'])
            if action=='delete':
                if request.get('confirmation')!='Delete profile':raise ValueError('Confirm deleting this local profile')
                if not any(p['id']==request.get('id') for p in items):raise ValueError('Saved profile missing')
                return [p for p in items if p['id']!=request['id']]
            if action=='copy':
                p=self.get(request.get('id'));p['title']=text(request.get('title'),80,'Profile title')
            elif action=='import':p=unpack(request.get('file'))
            else:p=deepcopy(validate(request.get('profile')))
            existing=next((i for i,x in enumerate(items) if x['id']==p['id']),None) if action=='save' else None
            if existing is not None:items[existing]=p
            else:
                if action=='save' and p['id']!='new':raise ValueError('Copy an included profile before editing; missing saved profiles cannot be overwritten')
                p['id']=str(uuid.uuid4());items.append(p)
            return items
        self._mutate(request.get('revision'),action,change)
        return self.snapshot()
