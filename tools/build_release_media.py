"""Original FMER manual plates from exact renderer/browser captures. No hardware.

SVGs embed the source image bytes unchanged; arrows and labels are separate
layers. Run feature_capture first. PNG/PDF export is a separate browser step.
"""
from pathlib import Path
import argparse,base64,hashlib,html,json,textwrap
from build_help_illustrations import png
R=Path(__file__).resolve().parents[1];H=R/'host/help';E=html.escape
BG='#070709';PANEL='#101014';INK='#f5f7fa';MUTED='#b6bbc6';GREEN='#76ff53';PINK='#ff78d4';PURPLE='#c9a0ff'

# Exact image names and pixel anchors. Text is maintained alongside its source.
FEATURES=[
 ('playing-modes','Playing modes','performance','One instrument or four independent parts.',
  [('guide-glo-0','GLO / VOICE-TEMPO','K1 selects 1V, 6V or 4T','Voices follows the active allocation'),('guide-mono-glide','GLO / MONO GLIDE','Choose Legato or Always','Set glide time and contour')],
  ['1V: mono instrument with glide. 6V: six voices shared by one instrument.','4T: four mono tracks with separate instrument references.','Use GLO K1 or SEQ / PLAY MODE K1. Entering or leaving 4T stops playback.']),
 ('fm-synthesis','Six-operator FM','fm','Four-voice FM sound design with DX7-style voice exchange.',
  [('guide-fm-edit-0','EDIT / TUNE','SELECT chooses the operator','K1–K4 edit level and frequency'),('guide-fm-edit-4','EDIT / OP RATES','Operator envelope rates','Each knob edits one stage')],
  ['Six operators, 32 algorithms, feedback and detailed rate/level envelopes.','ALGORITHM changes the current FM sound; SAVE retains the edit.','Standard DX7 voice/bank import is available in Companion; exact DX7 emulation is not claimed.']),
 ('fm-envelopes','FM envelopes and scaling','fm','Shape both loudness and harmonic movement.',
  [('guide-fm-env','ENV / CARRIERS','Carrier envelope overview','Four controls edit carrier stages'),('guide-fm-edit-2','EDIT / KEY SCALE','Operator-specific keyboard scaling','Breakpoint, depth and curve')],
  ['ENV edits the carriers together; EDIT provides per-operator envelopes.','EDIT also includes sensitivity, key scaling and pitch-envelope pages.','FM rates and levels are not millisecond ADSR values.']),
 ('algorithms','FM algorithm diagrams','fm','See how the six operators connect.',
  [('panel-algorithm-1','ALGORITHM / 1','Operator routing diagram','The active sound receives the edit'),('panel-algorithm-5','ALGORITHM / 5','Different carrier/modulator structure','Save the instrument to retain it')],
  ['Turn ALGORITHM on an FM instrument to view its routing diagram.','Carriers reach the output; modulators change another operator’s tone.','All 32 routing diagrams are included in the FM handbook.']),
 ('virtual-analog','Virtual Analog','va','A second engine for direct oscillator, filter and envelope work.',
  [('guide-va-edit','EDIT / VA','Waveform and voice filter','Cutoff and resonance are separate'),('guide-va-env','ENV / VA','Envelope shape','Attack, decay, sustain and release')],
  ['Choose sine, saw, square, triangle or noise.','The voice filter is distinct from the reorderable shared FX filter.','Use ENV for amplitude shaping and LFO for stored modulation.']),
 ('instrument-banks','128 onboard instrument slots','banks','64 editable Bank A slots and 64 independent Bank B slots.',
  [('guide-presets','PRESETS','Bank and sound selection','PRESETS crosses all banks'),('guide-save-instrument','SAVE / INSTRUMENT','Choose bank and destination','SEL confirms Save or Load')],
  ['Spectrum contains 36 FM and 28 VA sounds; all 62 survey favorites are included.','Either engine can occupy either bank; Bank B starts with independent default copies.','Reset to FMER Default affects Bank A only. Reset User Bank and Clear User Bank are separate.']),
 ('filter','Filter and resonance','effects','Low-pass, high-pass and band-pass with directional shading.',
  [('guide-filter-0','FX / LOW PASS','Low frequencies pass below cutoff','Frequency and resonance'),('guide-filter-1','FX / HIGH PASS','High frequencies pass above cutoff','The fill direction reverses')],
  ['FX page1: K1 cutoff, K2 resonance; ALGORITHM chooses filter type.','Frequency uses a logarithmic control scale with actual Hz visible.','Resonance emphasizes the region around cutoff; it is not a second frequency.']),
 ('filter-band','Band-pass and HOME controls','effects','The same controls remain in the same order.',
  [('guide-filter-2','FX / BAND PASS','Pass band surrounds cutoff','K3 reverb; K4 delay'),('guide-home','HOME / SINGLE INSTRUMENT','Main mix oscilloscope','Cutoff, resonance, reverb, delay')],
  ['Band-pass shading surrounds the cutoff point.','Single-instrument HOME mirrors the first FX page’s four control positions.','Press FX to reach the remaining effect settings.']),
 ('reverb','Four reverb models','effects','Room, Plate, Hall and Cloud share direct return and decay controls.',
  [('guide-fx-0','FX / FILTER + SPACE','Shared effect activity','K3 changes reverb return'),('guide-fx-2','FX / SPACE SETTINGS','Actual delay time is shown','K3 decay; K4 reverb model')],
  ['Use the return amount to place the instrument in the space.','Select Room, Plate, Hall or Cloud on FX page3.','The six-stage shared effects chain can be reordered.']),
 ('delay','Free-time or tempo-synced delay','effects','Dial milliseconds or choose a musical division.',
  [('guide-fx-2','FX / FREE MS','Actual milliseconds','K1 time; K2 feedback'),('guide-delay-sync','FX / SYNCED','Tempo-derived time','K1 division after ALGORITHM selects sync')],
  ['Divisions: 1/4, dotted 1/8, 1/8, triplet 1/8, 1/16, triplet 1/16 and dotted 1/4.','ALGORITHM switches Free ms / division; FX page1 K4 controls the return.','Delay capacity is 20–1000 ms. MAX indicates the capacity limit.']),
 ('chorus-phaser','Chorus and phaser','effects','Four named characters for each modulation effect.',
  [('guide-fx-1','FX / CHORUS','Chorus character','K1 sets chorus amount'),('guide-phaser','FX / PHASER','Phaser character','K2 sets phaser amount')],
  ['Chorus: Dream, Wide, Shimmer, Rush. Phaser: Drift, Sweep, Pulse, Storm.','Turn the relevant amount knob, then ALGORITHM selects its character.','The implemented effect is Phaser, not Flanger.']),
 ('drive-lfo','Drive and LFO enable','effects','Add saturation or enable the sound’s stored modulation.',
  [('guide-fx-1','FX / MODULATION','Character follows the focused effect','K3 drive; K4 program LFO'),('guide-fm-lfo-0','LFO / FM MODULATION','FM modulation controls','Wave, speed, pitch and amplitude')],
  ['Drive is the distortion stage in the reorderable audio chain.','The LFO toggle retains its settings when disabled.','LFO is a modulation source, not a seventh reorderable audio effect.']),
 ('fx-routing','Reorder the effects chain','effects','Choose the order in which the six stages process audio.',
  [('guide-fx-3','FX / SIGNAL CHAIN','Selected stage and current position','K1 selects; K2 moves the stage')],
  ['Filter, Reverb, Delay, Distortion, Chorus and Phaser can be reordered.','K3 recalls the personal default. Hold SEL, then press FX to save a new default; playback stops.','GLO / RESET restores original routing separately from instrument-bank resets.']),
 ('lfo','Engine-specific modulation','modulation','Stored motion settings for FM and VA instruments.',
  [('guide-fm-lfo-1','LFO / FM SYNC','FM-specific delay and sync fields','SELECT moves between LFO pages'),('guide-va-lfo','LFO / VA','VA rate and depth','Program LFO enable')],
  ['FM includes waveform, speed, pitch/amplitude depth and sensitivity.','VA provides modulation rate and depth. FX page2 K4 gates the stored LFO.','Some DX7 sync behavior differs: inspect the parameter reference for implementation limits.']),
 ('arp','Eleven arpeggiator types','arp','Turn held notes into a timed musical part.',
  [('guide-arp-0','ARP / TYPE + LATCH','Strum is one of eleven types','Type, octaves, latch, triplets'),('guide-arp-1','ARP / TIMING','Timing controls','Division, tempo, gate and swing')],
  ['Up, Down, Exclusive, Played, Inclusive, Random, Repeat, Down Exclusive, Down Inclusive, Outside In, Strum.','1–4 octaves; divisions 1/1 through 1/32, with triplets; gate and 50–75% swing.','Press ARP again to toggle. SELECT switches type and timing pages.']),
 ('recording','Record notes or generated arps','sequencer','A four-beat count-in leads into quantized recording.',
  [('panel-record','SEQ / COUNT-IN','Shared four-beat lead-in','Record mode remains visible'),('guide-seq-5','SEQ / RECORD','Choose the recording method','Step, Overdub or Replace')],
  ['Overdub adds to the current pattern; Replace records a replacement pass.','Live recording captures rests and held notes.','REC from the ARP page records generated arp notes into the selected pattern.']),
 ('patterns','Sixteen patterns per project','sequencer','Build phrases from 1 to 64 steps and switch them in performance.',
  [('guide-seq-1','SEQ / PATTERNS','Pattern bank and playback state','Pattern, tempo, length and chain'),('panel-patterns16','SIXTEEN-PATTERN OVERVIEW','Selection and playback markers','Pattern destinations are 0–15')],
  ['Patterns are shared by the project’s tracks; they are not 16 separate banks per track.','Each pattern can contain up to64 steps.','Four-track parts are mono; single-instrument playback shares its voice pool with live keys and arp.']),
 ('note-edit','Edit notes, rests and ties','pattern-edit','Refine a phrase without recording it again.',
  [('guide-seq-0','SEQ / STEP EDIT','Step cursor and note grid','Pitch/rest/tie, velocity and gate'),('guide-seq-6','SEQ / NOTE EDIT','Logical note selection','Pitch, held length and final gate')],
  ['NOTE EDIT: ALGORITHM moves the logical note in time; SEL deletes it.','Hold SEL while turning pitch down/up to insert Rest/Tie.','STEP EDIT changes individual steps; NOTE EDIT works with held notes.']),
 ('copy-chain','Copy sections and chain patterns','pattern-edit','Reuse musical material and keep it moving.',
  [('guide-seq-7','SEQ / COPY + EDIT','Choose source range and destination','SEL applies the selected action'),('guide-seq-2','SEQ / CHAIN MEMBERS','Pattern membership','Choose the cursor and inclusion')],
  ['Copy, Paste, Cut, Clear and Undo operate on bounded step ranges.','Pattern chaining cycles enabled members; Song mode adds ordered repeats and transpose.','At least one chain member remains enabled.']),
 ('mixer','Four-track performance mixer','performance','One knob per track, with a clearly selected editing layer.',
  [('guide-seq-4','SEQ / MIXER','Four track strips','Volume, mute, solo and FX state'),('guide-home-4t','HOME / FOUR TRACKS','Part traces plus the final mix','Knobs1–4 follow tracks1–4')],
  ['Mixer layers: Patch, Pattern, Run, Volume, Mute, Solo, FX. SELECT / ALGORITHM / SEL cycles the layer.','Run left stops a track; right queues its next-bar launch.','FX toggles each track’s route through the shared chain; it is not four independent FX processors.']),
 ('song','Song arrangements','song','Arrange patterns, transpositions and repeats on a shared timeline.',
  [('guide-seq-8','SEQ / SONG ENTRIES','Repeat blocks align to musical time','Entry, pattern, transpose, repeats'),('guide-song-setup','SEQ / SONG SETUP','Lane and current entry','Live/Song, end behavior, insert/delete')],
  ['32 entries per lane; patterns0–15 or a16-step rest. Repeats1–32; transpose−24..+24 semitones.','ALGORITHM chooses the lane; SEL switches Entries/Setup. End behavior is Stop or Loop.','Single-instrument modes use one active lane; 4T uses four. Save the project to retain the arrangement.']),
 ('scopes','Live visual feedback','shortcuts','Expand the display when the sound is the focus.',
  [('guide-scope','HOME / FULLSCREEN','Final mix waveform','HOME again toggles the view'),('guide-scope-4t','HOME / FOUR-TRACK FULLSCREEN','Four part traces and final mix','Another page button exits fullscreen')],
  ['HOME again hides the ordinary controls in either playing layout.','Part traces monitor sound before track faders and FX; the master trace shows the final mix.','These images use illustrative waveform data through the production renderer.']),
 ('battery','Estimated battery percentage','troubleshooting','A numeric estimate in the compact status header.',
  [('guide-home','HOME / HEADER','Battery percentage at top right','Engine and playing-mode indicators'),('guide-glo-6','GLO / ICON LEGEND','Header symbols and meanings','Color adds status information')],
  ['White: normal. Pink: estimate below10%. Green: active USB data connection.','Green does not measure charger current. Percentage remains a calibrated estimate.','Save before low power; do not treat the percentage as a guaranteed remaining runtime.']),
 ('projects','Onboard projects and saving','projects','Keep a complete working arrangement on the instrument.',
  [('guide-save-project','SAVE / PROJECT','Choose Project scope','Select destination0–15, then SEL'),('guide-save-instrument','SAVE / INSTRUMENT','Instrument bank and slot','Save edited instruments first')],
  ['16 project slots retain patterns, song lanes, mix, working sound and instrument references.','Track references point to bank slots; projects do not embed four independent bank instruments.','Save the instruments, save the project, then capture a complete unit backup.']),
 ('midi','Wired MIDI and clock','midi','Play, synchronize and control FMER from other instruments or a DAW.',
  [('guide-glo-3','GLO / MIDI OUTPUT','Output route and channel','Local audio and Split/Merged'),('guide-glo-4','GLO / MIDI CLOCK','Clock source and transmission','SEL saves global MIDI settings')],
  ['USB MIDI input/output; TRS MIDI input. Bank Select + Program Change select patches.','Split or merge generated track channels; fixed CCs and exact USB SysEx are documented in Help.','TRS output and Bluetooth are unavailable. USB audio is a mixed output, not four separate stems.']),
 ('usb-link','Direct USB instrument link','usb-link','Connect two powered FMER units without a computer.',
  [('guide-glo-5','GLO / USB LINK','Choose PC, Master or Receiver','Master chooses Clock, Notes or Both')],
  ['Unplug PC cables before applying a direct-link role; connect the units with a USB data cable.','SEL applies. Each unit stays independently powered. One direct peer is supported.','Return to PC/NORMAL and press SEL before reconnecting Companion. Link roles reset at power-on.']),
 ('companion-library','Companion library','library','Organize instruments and projects locally on your computer.',
  [('app-library','COMPANION / LIBRARY','Search and organize the catalog','Name shown on the instrument')],
  ['Collections, tags, favorites, rename, duplicate, move and Trash/Undo.','PC library items are separate from the unit’s onboard banks and projects.','Import/export native FMER data and standard DX7 FM voices or32-voice banks.']),
 ('companion-banks','Companion editing and banks','editor','Edit visually, audition locally and choose explicit unit destinations.',
  [('app-editor','COMPANION / EDITOR','FM algorithm and working instrument','Sound, effects and sequencing tabs')],
  ['Sliders, musical selectors and a gesture-level Undo support detailed editing.','64 Bank A and64 Bank B PC slots are separate from hardware storage until transferred.','Opening a unit instrument preserves the editor arrangement; loading a project replaces it.']),
 ('companion-backup','Backup and restore','backups','Keep a recoverable copy before changing an installation.',
  [('app-backups','COMPANION / BACKUPS','Library export and unit backup','Choose the explicit restore scope')],
  ['Complete supported-FMER backups include musical banks, projects, working state, MIDI and personal FX default.','Keep dated archives per named instrument. Manage one connected unit at a time.','Restore is a verified overlay: empty source slots do not silently erase destination slots.']),
 ('companion-install','Offline firmware installation','firmware','Inspect, install and verify from one local Companion window.',
  [('app-firmware','COMPANION / FIRMWARE','Inspect the selected firmware','Install only after compatibility checks')],
  ['Portable Windows10/11 x64 EXE; no Python installation or hosted service required.','Use bundled or local firmware files. The app does not automatically download updates.','Supported layouts are checked; progress and exportable logs remain visible. Unknown layouts are not force-flashed.']),
 ('companion-transfer','Deploy sounds and projects','library','Review every destination before sending your set to the instrument.',
  [('app-transfer','COMPANION / TRANSFER REVIEW','Saved instrument names','Choose explicit unit destinations')],
  ['Send selected Library items, a PC bank or a project with embedded sounds.','A complete unit backup precedes all writes; every written slot is verified.','Playback stops. Working state is restored afterward; a failed batch retains its completed writes.']),
]

SHORTCUTS=[
 ('Hold SEL → press SEQ','Open Song and select four-track mode'),
 ('Hold HOME → press SEQ','Open Mixer and select four-track mode'),
 ('Hold SEL → press HOME','Toggle four-track / four-voice instrument'),
 ('Hold ENV → press HOME','Select mono instrument with legato glide'),
 ('Hold LFO → press HOME','Select four-voice instrument; glide off'),
 ('Hold SEL → press FX','Save current FX order as personal default'),
 ('Hold FX / SEQ / EDIT / GLO / LFO','After0.8s, return to that section’s landing page'),
 ('Press HOME again on HOME','Toggle expanded oscilloscope view'),
 ('Press ARP again / LFO again','Toggle the respective stored function'),
 ('Hold SEL + turn an ordinary parameter knob','Use fine adjustment; context actions take priority'),
 ('Hold SEL + press PLAY','Queue selected track for the next16-step bar'),
 ('Hold SEL + double-press PLAY','Queue all tracks for the next16-step bar'),
 ('NOTE EDIT: ALGORITHM / SEL','Move the logical note in time / delete it'),
 ('NOTE EDIT: hold SEL + turn pitch down/up','Insert Rest / Tie'),
 ('PRESETS / GLO K1','Browse sounds across banks / choose1V,6V,4T'),
 ('SAVE: choose scope, slot, action → SEL','Confirm instrument or project Save/Load'),
]

WORKFLOWS=[
 ('sound-to-song','From sound to arrangement',[
 ('01 / CHOOSE','Select1V,6V or4T in GLO. Browse with PRESETS.'),('02 / DESIGN','EDIT, ENV, LFO and FX shape the working instrument.'),('03 / SAVE SOUND','SAVE / Instrument. Choose bank and slot; confirm SEL.'),
 ('04 / RECORD','Choose pattern and length. REC uses Step, Overdub or Replace.'),('05 / ARRANGE','Assign track sounds and patterns. Add Song repeats and transpose.'),('06 / PRESERVE','Save Project. Back up the unit in Companion.')], 'Tracks reference saved instrument slots. Save edited sounds before the project.'),
 ('data-map','What is saved where?',[
 ('INSTRUMENT BANKS','64 Bank A +64 Bank B. Each slot can hold FM or VA.'),('PATTERN SET','16 patterns in each project; each holds1–64 steps.'),('SONG LANES','32 entries per lane refer to the project’s patterns.'),
 ('PROJECT','Working sound, patterns, lanes, mix and bank references.'),('PC LIBRARY','Named instruments/projects, collections and independent copies.'),('UNIT BACKUP','All populated banks/projects plus working/global settings.')], 'A project references track instruments. Moving a bank instrument can change projects that reference its slot.'),
 ('mode-workflow','Choose the right playing mode',[
 ('1V / MONO','One instrument and glide for connected lead or bass lines.'),('6V / POLY','One instrument; keys, arp and one sequence share six voices.'),('4T / PARTS','Four independent mono tracks, each with an instrument reference.'),
 ('DIRECT ACCESS','GLO K1 or SEQ / PLAY MODE K1 changes allocation explicitly.'),('PERFORM','4T opens Mixer. Single-instrument modes open one-lane Song.'),('RETURN','Hold SEQ0.8s to return. Use HOME for scopes; FX for effects.')], 'Entering/leaving4T stops playback. Ordinary page navigation and preset browsing do not change mode.'),
 ('paired-usb','Two-unit USB performance',[
 ('01 / PREPARE','Keep both units powered. Disconnect their computer cables.'),('02 / CHOOSE ROLES','GLO / USB LINK: Master on one, Receiver on the other.'),('03 / APPLY + CONNECT','SEL applies. Join the two USB-C ports with a data cable.'),
 ('04 / SET TRAFFIC','Master: Clock, Notes or Both. Avoid unintended note doubling.'),('05 / PERFORM','Leader transport controls the shared time; each keeps its own sounds.'),('06 / RETURN TO PC','Choose PC/NORMAL and press SEL before Companion use.')], 'One direct peer. No direct USB audio between units, USB hub mode or Bluetooth group support.'),
 ('safe-install','Companion installation workflow',[
 ('01 / CONNECT','One unit. Close other applications holding its MIDI ports.'),('02 / BACK UP','Capture supported-FMER banks/projects; name the archive by unit/date.'),('03 / INSPECT','Select bundled or local firmware. Review compatibility and scope.'),
 ('04 / INSTALL','Confirm. Keep power and USB connected while progress is active.'),('05 / VERIFY','Wait for completion and the new firmware identity.'),('06 / REVIEW','Check sounds/projects. On failure, export the operation log.')], 'Stock firmware cannot provide FMER musical backups. Unknown layouts require diagnosis, not a forced write.'),
]

# Pixel coordinates in the original 240x240 frame, reviewed against captures.
# Keeping these separate from labels makes annotation mistakes visible in review.
ANCHORS={
 'playing-modes': [[(160,156),(165,204)],[(155,156),(145,191)]],
 'fm-synthesis': [[(70,36),(150,177)],[(130,58),(150,181)]],
 'fm-envelopes': [[(150,85),(155,183)],[(85,36),(160,178)]],
 'algorithms': [[(140,105),(140,165)],[(140,105),(140,165)]],
 'virtual-analog': [[(130,66),(165,183)],[(145,83),(165,183)]],
 'instrument-banks': [[(110,74),(110,113)],[(115,155),(120,128)]],
 'filter': [[(130,164),(125,178)],[(190,164),(130,164)]],
 'filter-band': [[(135,164),(150,210)],[(150,80),(165,185)]],
 'reverb': [[(80,122),(150,202)],[(143,138),(155,211)]],
 'delay': [[(136,138),(150,165)],[(155,138),(155,155)]],
 'chorus-phaser': [[(125,138),(145,156)],[(130,138),(145,180)]],
 'drive-lfo': [[(125,138),(155,213)],[(145,60),(155,183)]],
 'fx-routing': [[(147,60),(135,203)]],
 'lfo': [[(155,183),(105,36)],[(140,60),(120,228)]],
 'arp': [[(120,60),(153,183)],[(135,60),(153,183)]],
 'recording': [[(140,85),(155,158)],[(130,85),(130,155)]],
 'patterns': [[(145,96),(153,182)],[(140,91),(140,160)]],
 'note-edit': [[(122,110),(153,182)],[(120,110),(155,183)]],
 'copy-chain': [[(130,184),(120,132)],[(130,97),(160,169)]],
 'mixer': [[(190,91),(200,167)],[(140,92),(167,228)]],
 'song': [[(132,85),(160,183)],[(136,36),(153,199)]],
 'scopes': [[(150,90),(150,170)],[(150,78),(160,195)]],
 'battery': [[(216,12),(117,12)],[(132,83),(132,164)]],
 'projects': [[(150,228),(120,156)],[(110,156),(120,128)]],
 'midi': [[(146,167),(153,216)],[(160,183),(140,60)]],
 'usb-link': [[(155,168),(145,191)]],
 'companion-library': [[(112,39),(201,113)]],
 'companion-banks': [[(170,185),(170,108)]],
 'companion-backup': [[(160,73),(75,145)]],
 'companion-install': [[(71,72),(65,155)]],
 'companion-transfer': [[(58,109),(150,112)]],
}

def clean(value):
    # Normal prose spacing; never alter captured software pixels or source IDs.
    import re
    value=re.sub(r'(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])', ' ', value)
    for original in ('4T','6V','1V','K1','K2','K3','K4','DX7','x64'):
        value=value.replace(re.sub(r'(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])',' ',original),original)
    return value

def text(x,y,value,size=24,color=INK,weight=400):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}">{E(clean(value))}</text>'
def lines(x,y,value,width=54,size=24,color=MUTED):
    return ''.join(text(x,y+i*int(size*1.35),v,size,color) for i,v in enumerate(textwrap.wrap(value,width=width)))
def shell(title,subtitle,height=1200):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="{height}" viewBox="0 0 1800 {height}" role="img"><title>{E(title)}</title><desc>{E(subtitle)}</desc><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8" fill="{PINK}"/></marker></defs><rect width="1800" height="{height}" fill="{BG}"/><g font-family="Segoe UI,Arial,sans-serif">',text(64,62,'FMER',42,GREEN,800),text(1736,55,'735 / FIELD GUIDE',18,MUTED).replace('x="1736"','x="1736" text-anchor="end"'),f'<path d="M64 86H1736" stroke="{PURPLE}"/>',text(64,143,title,40,INK,650),text(64,183,subtitle,24,MUTED)]
def finish(parts,height=1200,caption='Actual735 renderer / illustrative state / annotations outside the software'):
    parts += [f'<path d="M64 {height-66}H1736" stroke="#4b4e5a"/>',text(64,height-30,caption,18,MUTED),'</g></svg>'];return ''.join(parts)
def embedded(name,x,y,w,h):
    data=base64.b64encode((H/(name+'.png')).read_bytes()).decode()
    return f'<image x="{x}" y="{y}" width="{w}" height="{h}" style="image-rendering:pixelated" href="data:image/png;base64,{data}"/>'
def plate(item):
    slug,title,topic,summary,frames,bullets=item;app=frames[0][0].startswith('app-');height=1380 if app else 1200
    out=shell(title,summary,height)
    for i,(name,label,a,b) in enumerate(frames):
        if app:
            raw=(H/(name+'.png')).read_bytes();import struct
            iw,ih=struct.unpack('>II',raw[16:24]);x,y,w=76,250,1080;h=min(790,w*ih/iw);w=h*iw/ih;notes_x=1220
        else:x,y,w,h=76+i*860,270,480,480;notes_x=x+515
        out += [text(x,235,label,23,GREEN,650),f'<rect x="{x-8}" y="{y-8}" width="{w+16}" height="{h+16}" rx="8" fill="{PANEL}" stroke="#4b4e5a"/>',embedded(name,x,y,w,h)]
        for n,label in enumerate((a,b)):
            ax,ay=ANCHORS[slug][i][n]
            ly=y+80+n*225;endx=x+w*ax/240;endy=y+h*ay/240
            out += [f'<path d="M{notes_x-10} {ly-8}L{endx} {endy}" stroke="{PINK}" stroke-width="3" fill="none" marker-end="url(#arrow)"/>',text(notes_x,ly,str(n+1).zfill(2),22,PINK,700),lines(notes_x,ly+34,label,19,23,INK)]
    by=1075 if app else 845
    for i,b in enumerate(bullets):out += [text(76,by+i*74,str(i+1).zfill(2),23,PINK,700),lines(128,by+i*74,b,113,24,INK)]
    return finish(out,height,'Actual Companion browser capture / example library / no unit connected' if app else 'Actual735 renderer / illustrative state / annotations outside the software')
def workflow(item):
    slug,title,nodes,note=item;out=shell(title,'WORKFLOW / follow the numbered steps or read each storage layer in order')
    for i,(label,body) in enumerate(nodes):
        x=64+(i%3)*570;y=255+(i//3)*330
        out += [f'<rect x="{x}" y="{y}" width="530" height="250" rx="12" fill="{PANEL}" stroke="{GREEN}" stroke-width="2"/>',text(x+28,y+48,label,26,GREEN,650),lines(x+28,y+95,body,32,25,INK)]
        if i%3<2:out.append(f'<path d="M{x+532} {y+125}h34" stroke="{PINK}" stroke-width="4" marker-end="url(#arrow)"/>')
    out+= [lines(76,1005,note,115,25,INK)];return finish(out,caption='FMER735 / workflow reference / arrows indicate reading order, not automatic file transfer')
def cheatsheet():
    out=shell('Shortcuts / one-sheet reference','Hold the modifier first. SELECT is the rotary encoder; SEL is the button.',1400)
    for i,(gesture,result) in enumerate(SHORTCUTS):
        y=238+i*62
        if i%2==0:out.append(f'<rect x="64" y="{y-27}" width="1672" height="60" fill="{PANEL}"/>')
        out += [text(84,y+7,gesture,24,GREEN,600),text(900,y+7,result,23,INK)]
    out += [lines(76,1274,'Mode changes involving4T, SAVE/LOAD and saving a personal FX default stop playback. Track launch shortcuts are unavailable during recording.',126,21,INK)]
    return finish(out,1400,'FMER735 / GLO contains the on-device icon legend and shortcut page')

def build(captures):
    for path in captures.glob('guide-*.ppm'):(H/(path.stem+'.png')).write_bytes(png(path.read_bytes()))
    entries=[]
    for f in FEATURES:
        name='feature-'+f[0]+'.svg';(H/name).write_text(plate(f),encoding='utf8');entries.append(dict(slug=f[0],title=f[1],topic=f[2],file=name,summary=f[3],frames=[v[0]+'.png' for v in f[4]]))
    for f in WORKFLOWS:
        name='workflow-'+f[0]+'.svg';(H/name).write_text(workflow(f),encoding='utf8');entries.append(dict(slug=f[0],title=f[1],topic='workflows',file=name,summary=f[3],frames=[]))
    (H/'feature-shortcuts.svg').write_text(cheatsheet(),encoding='utf8');entries.append(dict(slug='shortcuts-sheet',title='Shortcuts / one sheet',topic='shortcuts',file='feature-shortcuts.svg',summary='Modifier gestures, navigation and performance commands.',frames=[]))
    manifest=dict(firmware='FM-1_735',date='2026-10-24',capture_scope='Actual production renderer with illustrative fixtures; actual isolated Companion browser captures; no physical display photographs',features=entries,
       inputs={p:hashlib.sha256((R/p).read_bytes()).hexdigest() for p in ('firmware/fm1/ui.h','firmware/fm1/panel_model.h','tools/feature_capture.cpp','tools/build_release_media.py')},
       source_images={f:hashlib.sha256((H/f).read_bytes()).hexdigest() for e in entries for f in e['frames']})
    (R/'docs/help/feature-plates.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    figures=json.loads((R/'docs/help/figures.json').read_text(encoding='utf8'))
    for group in figures.values():group[:]=[x for x in group if not x['file'].startswith(('feature-','workflow-'))]
    for e in entries:figures[e['topic']].insert(0,dict(file=e['file'],alt=e['title']+': annotated screen reference',caption=e['summary']+' Open for full-size view.'))
    (R/'docs/help/figures.json').write_text(json.dumps(figures,indent=2,ensure_ascii=True)+'\n',encoding='utf8')
    (H/'visual-guide.htm').write_text(gallery(entries),encoding='utf8')
    print(json.dumps(dict(plates=len(entries),firmware=735,hardware_access=False)))

def gallery(entries):
    cards=''.join(f'<section class="plate" data-text="{E(e["title"].lower())}"><h2>{E(e["title"])}</h2><a href="{e["file"]}"><img src="{e["file"]}" alt="{E(e["title"])}"></a><p>{E(e["summary"])}</p></section>' for e in entries)
    page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FMER735 / Visual field guide</title><style>body{margin:0;background:'+BG+';color:'+INK+';font:18px/1.5 system-ui}main{max-width:1500px;margin:auto;padding:36px}h1{font-size:42px;color:'+GREEN+'}a{color:'+GREEN+'}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:28px}.plate{min-width:0;background:'+PANEL+';padding:20px;border:1px solid #4b4e5a;border-radius:8px}img{width:100%;height:auto}input{padding:14px;font:inherit;width:min(500px,90%);margin-bottom:24px;background:#1b1b23;color:white;border:1px solid '+PINK+'}@media(max-width:500px){main{padding:16px}.grid{display:block}.plate{margin-bottom:20px}}@media print{input,header{display:none}.grid{display:block}.plate{break-after:page;padding:0;border:0}.plate h2,.plate p{display:none}main{padding:0}img{max-height:185mm;object-fit:contain}body{background:white}}</style><main><header><h1>FMER / visual field guide</h1><p>Build735 · Annotated screens, workflows and shortcuts. Click a sheet to open it at full size.</p><p><a href="index.htm">Full handbook</a> · <a href="feature-shortcuts.svg">Shortcut sheet</a></p><input aria-label="Find a guide" placeholder="Find a feature or workflow" oninput="document.querySelectorAll(\'.plate\').forEach(p=>p.hidden=!p.dataset.text.includes(this.value.toLowerCase()))"></header><div class="grid">'+cards+'</div></main></html>'
    return page
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--captures',type=Path,required=True);build(p.parse_args().captures)
