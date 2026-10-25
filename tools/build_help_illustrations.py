"""Deterministic handbook figures: actual renderer captures and control maps.
No device, private screenshots, external assets or image-generation service.
"""
from pathlib import Path
import argparse,html,json,struct,zlib,hashlib
R=Path(__file__).resolve().parents[1]
OUT=R/'host/help'

def foundation_map():
    """Original vector diagram: architecture and file formats, not vendor art."""
    boxes=[(24,68,392,'FMER musical system','FM/VA, FX, sequencer, original patches','GPL-3.0-only'),
           (464,68,392,'Companion and native library','Instruments, projects, backups, help','GPL-3.0-only'),
           (24,202,392,'Google MSFA','Six-operator FM synthesis foundation','Apache-2.0'),
           (464,202,392,'DX7 SysEx interchange','FM voice data only; no native projects','Rights belong to the patch author'),
           (24,336,832,'Felucca platform + SLOOP updater','Startup, HAL, panel, audio/display, USB/MIDI and guarded updates','GPL-3.0-only; original notices retained')]
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="880" height="480" viewBox="0 0 880 480" role="img"><rect width="880" height="480" rx="16" fill="#101014"/><g font-family="Segoe UI,Arial,sans-serif" fill="#f5f7fa"><text x="24" y="35" font-size="22">FMER foundations and interchange</text>']
    for x,y,w,title,detail,license_name in boxes:
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="110" rx="10" fill="#1b1b23" stroke="#76ff53"/><text x="{x+16}" y="{y+29}" font-size="19">{html.escape(title)}</text><text x="{x+16}" y="{y+58}" font-size="14">{html.escape(detail)}</text><text x="{x+16}" y="{y+84}" font-size="14" fill="#ff78d4">{html.escape(license_name)}</text>')
    parts.append('</g></svg>');return ''.join(parts)
def png(ppm):
    kind,size,maximum,data=ppm.split(b'\n',3)
    w,h=map(int,size.split())
    if kind!=b'P6' or maximum!=b'255' or len(data)!=w*h*3:raise ValueError('Expected RGB renderer PPM')
    def chunk(tag,data):return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(b'\0'+data[i*w*3:(i+1)*w*3] for i in range(h)),9))+chunk(b'IEND',b'')
def control_map(row,index):
    e=html.escape
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="880" height="270" viewBox="0 0 880 270" role="img"><rect width="880" height="270" rx="16" fill="#101014"/><g font-family="Segoe UI,Arial,sans-serif" fill="#f5f7fa"><text x="24" y="35" font-size="22">'+e(row[0])+'</text>']
    for i,label in enumerate(row[1:5]):
        x=24+i*212
        parts.append(f'<rect x="{x}" y="60" width="196" height="124" rx="12" fill="#1b1b23"/><circle cx="{x+98}" cy="98" r="22" fill="#09090d" stroke="#76ff53" stroke-width="3"/><path d="M{x+98} 98v-17" stroke="#ff78d4" stroke-width="3"/><text x="{x+98}" y="144" text-anchor="middle" font-size="16">K{i+1}</text><text x="{x+98}" y="170" text-anchor="middle" font-size="13">{e(label or "Inactive")}</text>')
    # Wrap instructions; these are maps of physical controls, not fake LCDs.
    words=row[5].split();lines=['']
    for word in words:
        if len(lines[-1])+len(word)>100:lines.append('')
        lines[-1]+=word+' '
    for i,line in enumerate(lines[:3]):parts.append(f'<text x="24" y="{213+i*21}" font-size="15" fill="#b6bbc6">{e(line)}</text>')
    parts.append('</g></svg>');return ''.join(parts)
def build(captures):
    OUT.mkdir(exist_ok=True)
    (OUT/'fmer-foundations.svg').write_text(foundation_map(),encoding='utf8')
    for path in sorted(captures.glob('panel-*.ppm')):(OUT/(path.stem+'.png')).write_bytes(png(path.read_bytes()))
    panel=json.loads((R/'docs/help/panel.json').read_text(encoding='utf8'))
    for i,row in enumerate(panel):(OUT/f'controls-{i:02}.svg').write_text(control_map(row,i),encoding='utf8')
    maps={
      'index':['panel-home','panel-home-four-tracks','panel-splash'],
      'getting-started':['app-banks','app-editor'], 'connection':['app-unit','panel-usb-link'],
      'library':['app-library'], 'banks':['app-banks','panel-presets','panel-user-presets'],
      'loadouts':['app-loadouts','app-install-loadouts','panel-presets','panel-user-presets'],
      'community':['app-sound-sources','app-library'],
      'units':['app-units','app-loadouts'],
      'editor':['app-editor','panel-focus'], 'fm':['panel-algorithm-1','panel-algorithm-5','panel-fm-envelope'],
      'va':['panel-va-envelope','app-editor-va'],
      'effects':['panel-effects-clean','panel-fx-chain','panel-home-filter-0','panel-home-filter-1','panel-home-filter-2'],
      'modulation':['panel-glide','panel-fm-envelope','panel-va-envelope'],
      'arp':['panel-arp','panel-arp-exclusive','panel-arp-capacity'],
      'sequencer':['panel-sequence','panel-record','panel-tracks-single'],
      'pattern-edit':['panel-sequence-bank4','panel-patterns16','panel-chain'],
      'performance':['panel-mixer','panel-home-four-tracks','panel-four-track-fullscreen'],
      'projects':['panel-project-save','app-library'], 'midi':['panel-midi-output','panel-midi-clock'],
      'backups':['app-backups','panel-restore'], 'firmware':['app-firmware'],
      'workflows':['panel-record','panel-song','app-banks'],
      'troubleshooting':['panel-global-mode','panel-estimated-battery','panel-legend'],
      'glossary':['panel-algorithm-5','panel-song','panel-mixer'],
      'limits':['panel-tracks','panel-estimated-battery'],
      'song':['panel-song','panel-song-setup'], 'shortcuts':['panel-shortcuts','panel-scope-only'],
      'usb-link':['panel-usb-link','panel-midi-clock'],
      'reference':['app-editor','panel-fm-envelope','panel-va-envelope']}
    captions={ 'app-loadouts':'Instrument loadouts: independent Bank A and Bank B profiles, reusable 64-slot collections and reviewed deployment.',
      'app-library':'Companion Library: titles, collections, tags, selection and Trash. Example catalog; no unit connected.',
      'app-banks':'Sound banks: choose, audition, edit and organize the 64 Bank A and 64 Bank B slots on the PC.',
      'app-editor':'Companion Editor: canonical values, musical selectors, sliders and local sound audition.',
      'app-editor-va':'Companion VA Editor: oscillator, filter and envelope controls.',
      'app-unit':'Your FM-1: explicit reads, destinations and verified transfers. Offline view.',
      'app-backups':'Backups: separate local Library export and complete unit musical-data snapshots.',
      'app-firmware':'Firmware: inspect the bundled installer before confirming a device write.',
      'panel-home-filter-0':'Low-pass fill extends left of cutoff.', 'panel-home-filter-1':'High-pass fill extends right of cutoff.',
      'panel-home-filter-2':'Band-pass fill surrounds cutoff.', 'panel-song':'Song: four lanes on a shared timeline, with repeat blocks and transposition.',
      'panel-song-setup':'Song lane setup: LIVE/SONG, end behavior and entry insertion/deletion.',
      'panel-record':'Recording: four-beat count-in, quantization and Overdub/Replace.',
      'panel-fx-chain':'Signal chain: selected stage and its position in the processing order.'}
    result={}
    for topic,names in maps.items():
        result[topic]=[dict(file=name+'.png',alt=captions.get(name,name.removeprefix('panel-').replace('-',' ').capitalize()+' view'),caption=captions.get(name,name.removeprefix('panel-').replace('-',' ').capitalize()+' view')+(' Firmware 735 renderer capture; illustrative state, not a device photograph.' if name.startswith('panel-') else ' Actual browser capture.')) for name in names]
    result['troubleshooting'].append(dict(file='app-feedback.png',alt='Beta feedback form',caption='Optional beta feedback and local diagnostic summary.'))
    result['licensing']=[dict(file='fmer-foundations.svg',alt='FMER software foundations and DX7 interchange boundaries',caption='Original architecture diagram: hardware support, musical engines and file interchange have distinct responsibilities and licenses.')]
    result['fm'] += [dict(file=f'panel-algorithm-{i}.png',alt=f'FM algorithm {i}',caption=f'Algorithm {i}: actual operator routing drawn by firmware 735.') for i in range(1,33) if i not in (1,5)]
    result['panel']=[dict(file=f'controls-{i:02}.svg',alt=row[0]+' physical control map',caption=row[0]+': knob positions and page actions. Diagram from the audited panel map.') for i,row in enumerate(panel)]
    # Add each relevant menu map to its explanatory topic as well.
    families={'fm':['FM EDIT'],'va':['VA EDIT'],'effects':['FX'],'modulation':['ENV','LFO'],'arp':['ARP'],'sequencer':['SEQ'],'midi':['GLO / MIDI'],'banks':['PRESETS','SAVE']}
    for topic,prefixes in families.items():
        for i,row in enumerate(panel):
            if any(row[0].startswith(p) for p in prefixes):result[topic].append(result['panel'][i])
    (R/'docs/help/figures.json').write_text(json.dumps(result,indent=2,ensure_ascii=True)+'\n',encoding='utf8')
    print(f'{len(result)} illustrated topics; {len(panel)} physical menu diagrams; {len(list(captures.glob("*.ppm")))} renderer captures')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--captures',type=Path,required=True);build(p.parse_args().captures)
