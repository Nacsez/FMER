"""Two independent editable64-slot banks; file-only, complete FMERNAT8 records.

Reuses the existing audited file lock, revision, pre-commit log, previous-file
backup and atomic replacement machinery. No MIDI import or device I/O.
"""
from copy import deepcopy
import base64
import hashlib
from pathlib import Path
import subprocess
import library
import fm1_native_state_v12 as native

PROFILE='FMER Spectrum 735.1'
CONFIRM={'reset_defaults':'Reset to FMER Default','reset_user':'Reset User Bank','clear_user':'Clear User Bank'}
FM_CATEGORIES=['Keys','Bells','Bass','Brass','Organ','Plucks','Winds','Motion',
 'Keys','Keys','Plucks','Percussion','Mallets','Percussion','Bells','Percussion','Bass','Bass','Bass','Bass',
 'Brass','Brass','Brass','Winds','Percussion','Strings','Percussion','Pads','Pads','Bells','Leads','Percussion']
VA_CATEGORIES=['Keys','Leads','Leads','Keys','Bass','Plucks','Pads','Winds','Bass','Bass','Bass','Bass','Bass','Bass',
 'Leads','Leads','Winds','Winds','Leads','Leads','Pads','Strings','Pads','Pads','Plucks','Mallets','Organ','Brass','Keys','Plucks','Arp','Pads']
for _percussion in (10,11,12,13,24,29):VA_CATEGORIES[_percussion]='Percussion'
CATEGORIES=sorted(set(FM_CATEGORIES+VA_CATEGORIES+['Custom']))

def decode_record(text):
    if not isinstance(text,str) or len(text)>5400:raise ValueError('Expected one complete native record')
    raw=base64.b64decode(text,validate=True)
    return native.decode_compatible(raw)

def pack(state):return base64.b64encode(native.encode(state)).decode('ascii')

# Declarative FX profiles, not executable modules. Preserve voice, patterns,
# transport settings and all unlisted fields when applying to a working sound.
LEGACY_FX_IDS=(145,146,147,148,149,162,168,169,170,171,172,173,174,194)
FX_IDS=(*LEGACY_FX_IDS,159)

def export_fx(state):
    native.validate_state(state)
    return dict(format='FMER-FX-PROFILE',version=4,dsp='FMER733',modulation_profiles=list(state['modulation_profiles']),fx_order=state['fx_order'],
                controls={str(i):state['controls'][i] for i in FX_IDS})

def import_fx(state,profile):
    native.validate_state(state)
    if not isinstance(profile,dict) or set(profile)!=({'format','version','dsp','controls','fx_order','modulation_profiles'} if profile.get('version')==4 else {'format','version','dsp','controls','fx_order'} if profile.get('version')==3 else {'format','version','dsp','controls'}):
        raise ValueError('Invalid FX profile fields')
    if profile['format']!='FMER-FX-PROFILE' or type(profile['version']) is not int or (profile['version'],profile['dsp']) not in ((1,'FMER712'),(2,'FMER722'),(3,'FMER728'),(4,'FMER733')):
        raise ValueError('Unsupported FX profile or DSP version')
    values=profile['controls']
    if not isinstance(values,dict) or set(values)!={str(i) for i in (LEGACY_FX_IDS if profile['version']==1 else FX_IDS)}:raise ValueError('Incomplete FX profile')
    result=deepcopy(state)
    for i in (LEGACY_FX_IDS if profile['version']==1 else FX_IDS):result['controls'][i]=values[str(i)]
    result['fx_order']=profile.get('fx_order',0)
    result['modulation_profiles']=deepcopy(profile.get('modulation_profiles',[0,0]))
    if profile['version']==1:result['controls'][159]=0
    native.validate_state(result)
    return result

def classic_profile(executable):
    result=subprocess.run([str(executable),'--factory'],creationflags=(subprocess.CREATE_NO_WINDOW if __import__('os').name=='nt' else 0), capture_output=True,timeout=10,check=True)
    catalog=library.strict_loads(result.stdout)
    if catalog['profile']!='FMER Default 726.1' or len(catalog['sounds'])!=64:raise ValueError('Build the current FMER Default profile first')
    slots=[]
    for expected_id,sound in enumerate(catalog['sounds']):
        if sound['id']!=expected_id or sound['engine']!=(0 if expected_id<8 or 16<=expected_id<40 else 1):
            raise ValueError('Profile program IDs or engines do not match the stable catalog')
        idx=sound['id'];engine=sound['engine'];v=sound['va'];controls=sound['vced'][:145]+[0]*15+[0]*38
        controls[147]=sound['lfo_enabled']
        controls[160:178]=[engine,int(v[0]),20000,round(v[2]*100),round(v[3]),round(v[4]),round(v[5]*100),round(v[6]),0,0,0,250,35,0,0,round(v[7]*100),round(v[8]),round(v[1])]
        controls[178:198]=[120,0,0,16,1,75,0,50,16,0,128,100,75,4,0,0,50,0,0,1]
        state=dict(schema=native.SCHEMA,version=native.VERSION,source_generation=0,preset_id=idx,controls=controls,
                   vced=sound['vced'],patterns=[dict(length=16,steps=[[128,100,75] for _ in range(64)]) for _ in range(native.PATTERN_COUNT)])
        native.initialize_tracks(state)
        bank_index=idx if idx<8 else idx-8 if idx<40 else idx-32
        category=(FM_CATEGORIES if engine==0 else VA_CATEGORIES)[bank_index]
        slots.append(dict(name=sound['name'],category=category,favorite=False,
                          audition_note=43 if category=='Bass' else 67 if category in ('Bells','Mallets') else 60,
                          native=pack(state)))
    return slots

def profile(executable):
    import json
    value=json.loads((Path(__file__).resolve().parents[1]/'host/loadout_profiles.json').read_text(encoding='utf8'))
    selected=next(p for p in value['profiles'] if p['id']=='A')
    result=[]
    for index,key in enumerate(selected['sound_ids']):
        item=deepcopy(value['sounds'][key]['entry']);state=decode_record(item['native'])
        state['preset_id']=index;state['controls'][191]=6;item['native']=pack(state);result.append(item)
    if len(result)!=64:raise ValueError('Spectrum needs64 instruments')
    return result


class BankLibrary(library.PatchLibrary):
    def __init__(self,root,executable,*,defaults=None):
        super().__init__(root,executable)
        self.defaults=deepcopy(profile(executable) if defaults is None else defaults)
        if len(self.defaults)!=64:raise ValueError('Profile must contain64 instruments')
        for p in self.defaults:self.validate_entry(p)

    @staticmethod
    def validate_entry(entry):
        if not isinstance(entry,dict) or set(entry)!={'name','category','favorite','audition_note','native'}:raise ValueError('Invalid sound entry fields')
        name=entry['name']
        if not isinstance(name,str) or not 1<=len(name)<=10 or not all(32<=ord(c)<=126 for c in name):raise ValueError('Use1..10 printable ASCII characters for the device name')
        library.choice(entry['category'],set(CATEGORIES),'category');library.boolean(entry['favorite'],'favorite')
        library.integer(entry['audition_note'],0,127,'audition note')
        state=decode_record(entry['native'])
        if bytes(state['vced'][145:]).decode('ascii').rstrip()!=name.rstrip():raise ValueError('Display name and saved instrument name differ')

    def _empty(self):
        return dict(format='FMER-SOUNDBANK',version=1,profile=PROFILE,capacity=128,revision=0,
                    slots=deepcopy(self.defaults)+deepcopy(self.defaults),undo_slots=None)

    @staticmethod
    def _envelope(state):
        return dict(format='FMER-SOUNDBANK-FILE',version=1,sha256=hashlib.sha256(library.canonical(state)).hexdigest(),payload=state)

    def _validate_state(self,state):
        if not isinstance(state,dict) or set(state)!={'format','version','profile','capacity','revision','slots','undo_slots'}:raise ValueError('Invalid bank fields')
        if state['profile'] not in (PROFILE,'FMER Default 726.1','FMER Default 719.1','FMER Default 718.1','FMER Default 717.1','FMER Default 716.1','FMER Default 715.1','FMER Default 709.1','FMER Default 710.1'):raise ValueError('Bank profile differs; explicit profile migration required')
        if state['format']!='FMER-SOUNDBANK' or type(state['version']) is not int or state['version']!=1 or state['capacity']!=128:raise ValueError('Unsupported bank format')
        library.integer(state['revision'],0,2**53-1,'revision')
        for key in ('slots','undo_slots'):
            bank=state[key]
            if key=='undo_slots' and bank is None:continue
            if not isinstance(bank,list) or len(bank)!=128:raise ValueError('Exactly two64-slot banks required')
            for idx,entry in enumerate(bank):
                if entry is None:
                    if idx<64:raise ValueError('Default bank cannot contain empty slots')
                else:self.validate_entry(entry)

    def _unpack(self,envelope):
        if not isinstance(envelope,dict) or set(envelope)!={'format','version','sha256','payload'} or envelope['format']!='FMER-SOUNDBANK-FILE' or type(envelope['version']) is not int or envelope['version']!=1:raise ValueError('Unsupported bank backup')
        state=envelope['payload'];raw=library.canonical(state)
        if len(raw)>library.MAX_FILE_BYTES or hashlib.sha256(raw).hexdigest()!=envelope['sha256']:raise ValueError('Bank checksum/size mismatch')
        self._validate_state(state);return state

    def dispatch(self,request):
        library.fields(request,{'action','revision','slot','entry','confirmation','backup','bank','destination','name'},'sound bank request')
        action=request.get('action')
        if action=='snapshot':return self.snapshot()|dict(profile=PROFILE,categories=CATEGORIES,hardware_access=False)
        if action=='backup':return dict(backup=self._envelope(self._read()))
        if action=='deployment':
            # Data only. Export never synchronizes either device bank.
            # Use the explicit711 guarded slot controls after reconciliation.
            bank=request.get('bank');library.choice(bank,{'defaults','user'},'bank')
            slots=self._read()['slots'][0:64] if bank=='defaults' else self._read()['slots'][64:128]
            return dict(format='FMER-DEVICE-BANK-PLAN',version=1,profile=PROFILE,bank=bank,
                        requires_reconciliation=True,device_writes=False,slots=deepcopy(slots),
                        firmware_requirement='Use the FMER727 companion device controls for explicit guarded slot sync; both banks use complete FMERNAT8 records.')
        if action not in ('save','undo','restore','reset_defaults','reset_user','clear_user','rename','copy','move','swap','delete'):raise ValueError('Unknown bank action')
        if action in CONFIRM and request.get('confirmation')!=CONFIRM[action]:raise ValueError('Explicit named reset confirmation required')
        def change(state):
            slots=deepcopy(state['slots'])
            if action=='save':
                idx=library.integer(request.get('slot'),0,127,'slot');self.validate_entry(request.get('entry'));slots[idx]=deepcopy(request['entry'])
            elif action=='undo':
                if state['undo_slots'] is None:raise ValueError('Nothing to undo')
                slots=deepcopy(state['undo_slots'])
            elif action=='restore':slots=deepcopy(self._unpack(request.get('backup'))['slots'])
            elif action=='reset_defaults':slots[:64]=deepcopy(self.defaults)
            elif action=='reset_user':slots[64:]=deepcopy(self.defaults)
            elif action=='clear_user':slots[64:]=[None]*64
            elif action in ('rename','copy','move','swap','delete'):
                idx=library.integer(request.get('slot'),0,127,'slot')
                if slots[idx] is None:raise ValueError('Source slot is empty')
                if action=='rename':
                    name=request.get('name');state=decode_record(slots[idx]['native'])
                    if not isinstance(name,str) or not 1<=len(name)<=10 or not name.strip() or any(not 32<=ord(c)<=126 for c in name):raise ValueError('Use1..10 printable ASCII characters')
                    state['vced'][145:]=list(name.ljust(10).encode('ascii'));slots[idx]['name']=name;slots[idx]['native']=pack(state)
                elif action=='delete':
                    if idx<64:raise ValueError('Bank A slots stay populated; replace or reset this sound')
                    slots[idx]=None
                else:
                    dest=library.integer(request.get('destination'),0,127,'destination')
                    if dest==idx:raise ValueError('Choose another destination')
                    if action=='copy':slots[dest]=deepcopy(slots[idx])
                    elif action=='move':
                        if idx<64:raise ValueError('Bank A slots stay populated; use Copy or Swap')
                        if slots[dest] is not None:raise ValueError('Move needs an empty destination; use Swap to retain both sounds')
                        slots[dest],slots[idx]=slots[idx],None
                    else:
                        if idx<64 and slots[dest] is None:raise ValueError('Bank A slots cannot be empty')
                        slots[dest],slots[idx]=slots[idx],slots[dest]
            return slots
        return self._mutate(request.get('revision'),action,change)

def render_settings(entry,scenario='note',velocity=100):
    BankLibrary.validate_entry(entry);s=decode_record(entry['native']);c=s['controls']
    settings=dict(scenario='sequence' if scenario=='pattern' else scenario,note=entry['audition_note'],velocity=velocity,duration=3,tail=4,budget=1 if c[150] and not c[153] else c[191],bpm=c[178],
                mono=c[191]==1 or bool(c[150] and not c[153]),glide=dict(mode=c[150],time_ms=c[151],curve=c[152]),
                engine='va' if c[160] else 'fm',wave=['sine','saw','square','triangle','noise'][c[161]],cutoff=c[177],vced=s['vced'],
                va=dict(resonance=c[163]/100,attack_ms=c[164],decay_ms=c[165],sustain=c[166]/100,release_ms=c[167],lfo_rate_hz=c[175]/100,lfo_depth_cents=c[176]),
                lfo_enabled=bool(c[147]),effects=dict(filter_mode=c[145],resonance=c[146]/100,reverb_model=c[148],delay_model=c[149],cutoff_hz=c[162],drive=c[168]/100,chorus=c[169]/100,delay=c[170]/100,delay_ms=(c[171] if not c[159] else max(20,min(1000,round(60000/c[178]*[0,1,.75,.5,1/3,.25,1/6,1.5][c[159]])))),feedback=c[172]/100,reverb=c[173]/100,phaser=c[174]/100,reverb_decay=c[194]/100))
    ch,ph=s['modulation_profiles']
    settings['effects'].update(chorus_rate_hz=[.12,.28,.65,1.][ch],chorus_depth=[.35,.70,.85,1.][ch],phaser_rate_hz=[.5,1.1,2.6,5.2][ph],phaser_depth=[.55,.80,.90,1.][ph])
    settings['effects']['order']=[['filter','reverb','delay','drive','chorus','phaser'][i] for i in native.effect_order(s['fx_order'])]
    if scenario=='arp':
        settings['arp']=dict(order=['up','down','exclusive','played','inclusive','random','repeat','down_exclusive','down_inclusive','outside_in','strum'][c[180]],
                             octaves=c[182],gate=c[183],rate=c[181],latch=bool(c[184]),swing=c[185],triplet=bool(c[192]))
    if scenario=='pattern':
        p=s['patterns'][c[195]]
        settings['pattern']=dict(length=p['length'],channel=0,steps=[dict(notes=[] if pitch>=128 else [dict(pitch=pitch,velocity=vel)],gate=gate,tie=pitch==129) for pitch,vel,gate in p['steps']])
        # Audition up to one cycle (bounded20s); long patterns are an excerpt.
        settings['duration']=min(20,max(3,(p['length']*15+c[178]-1)//c[178]))
    return settings
