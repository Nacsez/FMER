"""Original six-operator FMER instruments for the 2026-10 sound collection.

SPDX-License-Identifier: GPL-3.0-only

These are authored operator recipes, not mutations of OEM/imported presets.
No file, hardware or library access occurs on import. Algorithms are numbered
1..32 in the recipe tables and converted to canonical VCED 0..31 here. Operators
are always OP6..OP1. Keep the published firmware's factory bank immutable.

Design references (concepts only; no downloaded preset data):
https://yamahasynth.com/learn/synth-programming/basics-of-fm-synthesis-lesson-2/
https://yamahasynth.com/learn/montage-series-synthesizers/mannys-fm-xplorations-article-2/

MSFA implements single-operator feedback; algorithms 4/6 have a multi-operator
feedback loop and are deliberately not relied upon in these recipes. See the
pinned Apache-2.0 third_party/msfa/src/fm_core.cc for routing provenance.
"""
from copy import deepcopy
import math
import re


# Output-bus carrier masks, derived from the included MSFA routing table.
CARRIERS = (0x28,0x28,0x24,0x24,0x2a,0x2a,0x28,0x28,
            0x28,0x24,0x24,0x28,0x28,0x28,0x28,0x20,
            0x20,0x20,0x26,0x34,0x36,0x2e,0x36,0x3e,
            0x3e,0x34,0x34,0x29,0x3a,0x39,0x3e,0x3f)

# R1,R2,R3,R4,L1,L2,L3,L4: high rates are fast; levels are logarithmic.
# Nonzero L3 is a held plateau, not a percentage of the output level.
ENVELOPES = {
    'body': (99,53,42,79,99,94,89,0),
    'soft': (79,45,34,68,99,96,93,0),
    'blow': (88,54,40,74,99,96,92,0),
    'splat': (98,66,40,78,99,84,93,0),
    'reed': (85,48,35,70,99,94,91,0),
    'organ': (99,99,99,86,99,99,99,0),
    'pluck': (99,55,43,79,99,87,0,0),
    # Hold the modulation index while the audible carrier falls away. Using
    # the carrier's fast falling envelope here made unlike plucks converge on
    # near-sine tails in the first bank-wide spectral comparison.
    'brightpluck': (99,48,44,79,99,97,0,0),
    'brightstrike': (99,64,52,84,99,95,0,0),
    'hammer': (99,65,51,82,99,81,0,0),
    'click': (99,87,78,96,99,62,0,0),
    'chiff': (99,74,62,86,99,79,0,0),
    'snare': (99,68,59,90,99,84,0,0),
    'hat': (99,83,73,97,99,70,0,0),
    'short': (99,72,62,91,99,80,0,0),
    'kick': (99,61,52,86,99,90,0,0),
    'boom': (99,49,44,79,99,92,0,0),
    'ring': (99,38,31,54,99,92,0,0),
    'tine': (99,45,34,65,99,91,0,0),
    'wood': (99,58,48,81,99,86,0,0),
    'wah': (99,43,33,77,99,82,73,0),
    'bow': (43,37,29,56,99,97,94,0),
    'swell': (32,33,25,49,99,97,95,0),
    'bloom': (49,29,25,54,99,83,97,0),
    'moving': (52,29,24,51,99,96,81,0),
    'air': (63,42,32,61,99,94,89,0),
    'drone': (35,22,23,46,99,87,98,0),
    'shimmer': (55,31,27,53,99,82,95,0),
}


def fixed(hz):
    """A fixed-frequency component, encoded by the actual DX7/MSFA law."""
    return ('fixed', hz)


def _frequency(value):
    if isinstance(value, tuple):
        centidecades = round(100 * math.log10(value[1]))
        if not 0 <= centidecades <= 399:
            raise ValueError('Fixed frequency must be 1..9772 Hz')
        return (1, centidecades // 100, centidecades % 100)
    value = float(value)
    coarse = 0 if value < 1 else min(31, int(value))
    base = .5 if not coarse else coarse
    fine = round((value / base - 1) * 100)
    if not 0 <= fine <= 99:
        raise ValueError('Ratio cannot be represented without an octave error')
    return 0, coarse, fine


def _row(name, title, family, algorithm, feedback, ratios, levels, shapes,
         description, *, note=60, category=None, detune=None, velocity=None,
         scaling=2, pitch=None, lfo=None, controls=None, tags=(), profiles=(0,0)):
    assert len(name) <= 10 and name.isascii()
    assert len(ratios) == len(levels) == 6
    shapes = shapes.split()
    assert len(shapes) == 6
    mask = CARRIERS[algorithm-1]
    p = [0] * 155
    for i in range(6):
        carrier = bool(mask & (1 << i))
        envelope = ENVELOPES[shapes[i]]
        mode, coarse, fine = _frequency(ratios[i])
        # High-key brightness damping; bass fundamental remains intact.
        depth = 0 if carrier else (12 if family not in ('Percussion','Experimental') else 5)
        vel = velocity[i] if velocity else (2 if carrier else 4)
        dt = detune[i] if detune else 7
        p[i*21:i*21+21] = [*envelope,45,0,depth,0,1,
                           0 if mode else scaling,1 if carrier else 2,vel,
                           levels[i],mode,coarse,fine,dt]
    p[126:134] = [99,78,70,84,50,50,50,50]
    if pitch:
        p[126:134] = list(pitch)
    p[134:145] = [algorithm-1,feedback,1,29,40,2,4,1,0,2,24]
    if lfo:
        # Rate, delay, pitch depth, amplitude depth, waveform, pitch sensitivity.
        p[137:141] = list(lfo[:4])
        p[142:144] = list(lfo[4:])
    p[145:] = list(name.ljust(10).encode('ascii'))
    controls = {145:0,146:0,147:0,148:0,149:0,159:0,
                162:20000,168:0,169:0,170:0,171:300,172:32,
                173:0,174:0,194:50,**(controls or {})}
    category = category or {'Percussion':'Percussion','Bass':'Bass','Keys':'Keys',
        'Winds':'Winds','Leads':'Leads','Pads':'Pads','Experimental':'Motion'}[family]
    texture = 'ratio and fixed-frequency components' if any(isinstance(r,tuple) for r in ratios) else 'ratio-tuned operators'
    return dict(id='fm_'+re.sub('[^a-z0-9]+','_',name.lower()).strip('_'),
        name=name,title=title,category=category,family=family,
        group={'Percussion':'percussion','Bass':'bass','Keys':'keys','Winds':'winds',
               'Leads':'leads','Pads':'pads','Experimental':'textures'}[family],
        tags=['FM',family.lower(),*tags],description=description,
        technique=f'Algorithm {algorithm}; {texture}; independent '+
                  ', '.join(dict.fromkeys(shapes))+' envelopes. '+
                  'Velocity shapes brightness independently of the main body. '+
                  ('Prepared LFO is active.' if controls[147] else 'Prepared LFO can be enabled for motion.'),
        audition_note=note,vced=p,controls=controls,modulation_profiles=list(profiles))


def _percussion():
    """32 distinct drum functions, with separately designed strike/body/tail."""
    r=[]
    def add(*a,**k): r.append(_row(*a,family='Percussion',category='Percussion',**k))
    add('MARROW','Marrow deep kick',algorithm=5,feedback=0,
        ratios=[1,1,3,1,.5,.5],levels=[29,82,63,55,12,84],
        shapes='click kick click click boom boom',note=36,
        pitch=[99,90,80,90,71,50,50,50],description='Deep rounded kick with a soft beater and octave-low tail; play C2-F2.',tags=['kick','deep'])
    add('PUNCH','Punch club kick',algorithm=19,feedback=4,
        ratios=[1,1,.5,7,1,1],levels=[65,79,78,61,83,72],
        shapes='chiff kick boom click short kick',note=36,
        pitch=[99,95,80,90,76,50,50,50],description='Firm pitched punch with a compact feedback beater; suited to short sequencer gates.',tags=['kick','punch'])
    add('CARDBOARD','Cardboard acoustic kick',algorithm=3,feedback=5,
        ratios=[3.17,1,1,2.37,2,1],levels=[78,78,84,59,63,61],
        shapes='click short kick click click short',note=38,
        pitch=[99,92,82,90,62,50,50,50],description='Dry skin knock and small-box resonance rather than a long sub; emphasize the middle velocities.',tags=['kick','acoustic'])
    add('SUBDROP','Subdrop long kick',algorithm=29,feedback=0,
        ratios=[3,1,1,1,.5,.5],levels=[66,49,31,70,72,76],
        shapes='click click click kick boom boom',note=36,
        pitch=[99,83,70,90,73,50,50,50],description='Long low drum with a fast initial dive and minimal high-mid energy; leave room between hits.',tags=['kick','sub'])
    add('RUBBERK','Rubber membrane kick',algorithm=16,feedback=3,
        ratios=[2,1,3,1,1,1],levels=[71,67,65,75,80,88],
        shapes='click short chiff short kick kick',note=36,
        pitch=[99,88,74,89,68,50,50,50],description='Elastic descending membrane with a rubbery upper tap and restrained sustain.',tags=['kick','rubber'])
    add('INDUSTRYK','Industry hard kick',algorithm=7,feedback=6,
        ratios=[1,1,1.41,1,3.21,1],levels=[86,76,73,80,83,64],
        shapes='click short short kick click short',note=36,
        pitch=[99,96,85,94,80,50,50,50],controls={168:8},description='Hard mechanical kick with a brief complex attack; lower velocities soften the metallic click.',tags=['kick','industrial'])
    add('SNAPWIRE','Snapwire snare',algorithm=13,feedback=7,
        ratios=[fixed(3260),fixed(1790),2.83,1,2,1],levels=[95,81,79,77,59,75],
        shapes='snare snare short snare click short',note=50,
        description='Broad scratchy wire burst over a small tuned shell; the attack is intentionally noise-like.',tags=['snare','wire'])
    add('DUSTSNARE','Dust brushed snare',algorithm=11,feedback=7,
        ratios=[fixed(4130),1.43,fixed(940),2.19,1,1],levels=[95,83,74,57,64,68],
        shapes='snare short snare click short short',note=48,
        description='Soft granular snare with a diffuse tail; brush-like at light velocity, crusty at accents.',tags=['snare','dust'])
    add('RIMSNARE','Rimshot snare',algorithm=10,feedback=7,
        ratios=[fixed(2210),3.79,1,fixed(5140),2.17,1],levels=[91,75,80,94,69,68],
        shapes='click short short snare snare snare',note=52,
        description='Sharp rim strike over a short wire bed; centered in the midrange for busy arrangements.',tags=['snare','rim'])
    add('CANNON','Cannon gated snare',algorithm=12,feedback=7,
        ratios=[2.63,fixed(1570),1.73,1,fixed(4870),1],levels=[84,79,82,80,96,73],
        shapes='short snare short snare snare snare',note=47,
        pitch=[99,94,80,90,56,50,50,50],description='Large synthetic shell and a dense gated wire tail; deliberately larger than the dry snare.',tags=['snare','electronic'])
    add('CLAPPAPER','Paper handclap',algorithm=21,feedback=7,
        ratios=[fixed(3790),fixed(820),fixed(1230),fixed(5230),fixed(970),fixed(1810)],levels=[96,70,69,92,68,67],
        shapes='short short snare snare short snare',note=60,
        description='Layered band-limited crack with unequal decays; a compact synthetic clap, not a sample.',tags=['clap','dry'])
    add('CLAPROOM','Room handclap',algorithm=22,feedback=7,
        ratios=[fixed(4610),fixed(690),fixed(1120),fixed(1730),7.31,1],levels=[96,68,71,65,87,56],
        shapes='snare snare short snare short short',note=60,controls={173:9,148:0,194:35},
        description='Longer scattered clap with a restrained room around the tail; useful on slower backbeats.',tags=['clap','room'])
    add('TICKHAT','Tick closed hat',algorithm=1,feedback=7,
        ratios=[fixed(7910),fixed(3790),fixed(2390),fixed(4330),fixed(5710),fixed(3110)],levels=[96,83,77,69,89,62],
        shapes='hat hat hat hat hat hat',note=60,controls={145:1,162:2100},
        description='Tiny bright hi-hat with inharmonic fixed partials and a high-pass floor.',tags=['hat','closed'])
    add('OPENFOIL','Open foil hat',algorithm=11,feedback=7,
        ratios=[fixed(6910),fixed(2830),fixed(3890),fixed(5210),fixed(1570),fixed(3310)],levels=[96,79,68,88,79,66],
        shapes='snare short snare short snare snare',note=60,controls={145:1,162:1900},
        description='Airy open hi-hat with a rough foil edge; let longer gates expose the full tail.',tags=['hat','open'])
    add('SANDSHAKE','Sand shaker',algorithm=17,feedback=7,
        ratios=[fixed(3310),fixed(710),fixed(6170),fixed(2290),fixed(4870),fixed(1390)],levels=[86,71,80,91,95,78],
        shapes='short short snare short snare snare',note=60,controls={145:1,162:1300},
        description='Dry sand-like sweep with strong velocity contrast; a softer alternative to hi-hats.',tags=['shaker','noise'])
    add('TAMBFIZZ','Tambourine fizz',algorithm=19,feedback=7,
        ratios=[fixed(4870),fixed(2630),fixed(3710),7.27,3.13,2.79],levels=[94,70,67,89,81,63],
        shapes='snare snare short click short snare',note=60,controls={145:1,162:900},
        description='Bright jingles over a brief hand strike; accents bring out the metallic splash.',tags=['tambourine','metal'])
    add('RIDESHARD','Shard ride cymbal',algorithm=8,feedback=7,
        ratios=[fixed(4310),fixed(1510),fixed(7430),fixed(2270),3.57,2.11],levels=[84,76,95,71,86,64],
        shapes='chiff ring ring ring click ring',note=60,controls={145:1,162:1700},
        description='Defined ride ping and a long dense metallic skirt; quieter hits keep the ping forward.',tags=['ride','cymbal'])
    add('CRASHGLASS','Glass crash',algorithm=14,feedback=7,
        ratios=[fixed(6190),fixed(2110),fixed(4010),fixed(3370),7.43,3.17],levels=[96,84,79,70,92,68],
        shapes='ring snare ring ring snare ring',note=60,controls={145:1,162:1500},
        description='Spreading glassy crash with a ragged decay; use as an accent rather than a constant wash.',tags=['crash','cymbal'])
    add('CHINATRASH','China trash cymbal',algorithm=16,feedback=7,
        ratios=[fixed(3130),fixed(1790),fixed(4910),fixed(2710),fixed(8110),fixed(2270)],levels=[95,82,81,77,80,78],
        shapes='ring snare snare ring snare ring',note=60,controls={145:1,162:1000},
        description='Low trashy gong-like crash with a rough inharmonic bloom.',tags=['cymbal','trash'])
    add('COWBITE','Cowbell bite',algorithm=27,feedback=3,
        ratios=[1.37,2,1,3,1,1.49],levels=[79,87,71,81,76,68],
        shapes='hammer hammer wood short wood wood',note=60,
        description='Hollow two-tone cowbell with a hard leading edge; pitched and useful across an octave.',tags=['cowbell','metal'])
    add('LOWTOM','Floor skin tom',algorithm=3,feedback=2,
        ratios=[2.13,1,1,3.71,2,1],levels=[64,75,84,70,65,68],
        shapes='click wood boom click short wood',note=43,
        pitch=[99,88,77,89,61,50,50,50],description='Low membrane thump with a soft pitch fall and short shell tap.',tags=['tom','low'])
    add('HIGHTOM','Rack skin tom',algorithm=9,feedback=3,
        ratios=[2.79,1,1.41,1,2.17,1],levels=[70,71,64,84,76,63],
        shapes='click wood short wood click short',note=55,
        pitch=[99,91,80,90,58,50,50,50],description='Tight melodic rack tom with a firm wooden attack; follows keyboard pitch.',tags=['tom','high'])
    add('SYNTHOM','Laser synth tom',algorithm=18,feedback=4,
        ratios=[1,2,1,3,1,1],levels=[64,75,70,75,73,87],
        shapes='short wood short short wood wood',note=48,
        pitch=[99,73,72,89,78,50,50,50],description='Pronounced descending electronic tom with a long pitch sweep and hollow body.',tags=['tom','laser'])
    add('CONGAPALM','Palm conga',algorithm=20,feedback=2,
        ratios=[2.61,1.41,1,3,1.49,1],levels=[74,69,79,69,61,72],
        shapes='click short wood click short wood',note=57,
        pitch=[99,93,80,90,55,50,50,50],description='Rounded hand-drum body with a dry palm contact; softer notes lose the slap.',tags=['conga','hand'])
    add('BONGOWOOD','Bongo wood',algorithm=26,feedback=3,
        ratios=[3.17,2.41,1,4,1.49,2],levels=[76,71,79,73,65,55],
        shapes='click short short click wood short',note=64,
        description='Small high hand-drum with woody membrane modes and a short release.',tags=['bongo','hand'])
    add('TAIKOHIDE','Hide taiko',algorithm=7,feedback=4,
        ratios=[1.43,2,2.71,1,3.13,1],levels=[79,76,75,83,88,67],
        shapes='click wood wood boom click wood',note=38,
        pitch=[99,86,73,85,58,50,50,50],description='Broad low drum with a stick crack and a loose hide resonance.',tags=['taiko','cinematic'])
    add('LOGKNOCK','Log knock',algorithm=5,feedback=1,
        ratios=[2.71,1,3.37,2,1.41,1],levels=[82,78,76,63,51,73],
        shapes='short wood click short click wood',note=60,
        description='Hollow wooden slit-drum with two staggered resonances; excellent for pitched counter-rhythms.',tags=['wood','log'])
    add('CLAVETAP','Clave tap',algorithm=31,feedback=3,
        ratios=[2.17,1,1.49,2.37,3.71,5.13],levels=[73,72,61,52,42,32],
        shapes='click short short click click click',note=72,
        description='Tiny hardwood click with a sharply focused fundamental and a few short overtones.',tags=['clave','wood'])
    add('TRIANGLE','Triangle ring',algorithm=25,feedback=1,
        ratios=[7.19,1,2.17,3.53,5.41,7.79],levels=[81,65,58,57,49,44],
        shapes='click ring ring ring ring ring',note=79,
        description='Fine struck-metal triangle with separated noninteger partials and a long natural tail.',tags=['triangle','metal'])
    add('AGOGOBELL','Agogo bell',algorithm=28,feedback=3,
        ratios=[1.41,3.17,1.49,1,4.71,2],levels=[65,74,75,75,72,64],
        shapes='wood click short wood click wood',note=67,
        description='Rounded two-band metal bell with a strong pitched center and short clang.',tags=['agogo','bell'])
    add('FRAMEHIT','Frame drum hit',algorithm=15,feedback=5,
        ratios=[1.73,2.41,1,1,4.17,1.49],levels=[75,71,69,82,88,61],
        shapes='click wood short kick short short',note=45,
        pitch=[99,91,75,90,56,50,50,50],description='Wide frame resonance and a brief noisy skin contact; voiced below the congas.',tags=['frame','hand'])
    add('ZAPSPRING','Spring zap',algorithm=17,feedback=6,
        ratios=[3.17,1.41,5.29,2.13,1.73,1],levels=[80,74,77,79,83,83],
        shapes='click short wood short wood wood',note=55,
        pitch=[99,69,62,84,83,48,50,50],description='Cartoon spring strike with a long downward sweep and irregular metallic sidebands.',tags=['zap','effect'])
    return r


def _bass():
    r=[]
    def add(*a,**k): r.append(_row(*a,family='Bass',category='Bass',**k))
    add('ARCADEPOP','Arcade pop bass',algorithm=1,feedback=5,
        ratios=[3,1,1,1,7.13,1],levels=[77,83,92,84,92,68],
        shapes='hammer wah body body click hammer',note=40,velocity=[5,3,4,2,6,2],
        pitch=[99,93,80,90,54,50,50,50],description='A hard fret pop gives way to a chewy four-operator bass body; velocity changes the bite.',tags=['arcade','slap'])
    add('SLAPCOIL','Coil slap bass',algorithm=7,feedback=4,
        ratios=[5,1,2,1,4.31,1],levels=[76,88,79,85,90,67],
        shapes='chiff wah body body click hammer',note=43,
        description='Bright string snap above a rounded low body; short accents and held notes have different colors.',tags=['slap','bright'])
    add('FINGERWOOD','Wood finger bass',algorithm=3,feedback=2,
        ratios=[2,1,1,3.11,1,1],levels=[65,86,84,74,75,72],
        shapes='hammer body body chiff wah body',note=43,
        detune=[7,7,7,7,7,8],description='Woody finger onset, stable low fundamental and a smaller drifting string layer.',tags=['finger','warm'])
    add('PICKSTEEL','Steel pick bass',algorithm=11,feedback=3,
        ratios=[4,1,1,7.07,2,1],levels=[83,80,84,76,85,74],
        shapes='hammer wah body click wah body',note=40,
        description='Picked metallic attack and tight midrange growl; avoids a continuous fizzy sustain.',tags=['pick','steel'])
    add('RUBBERB','Rubber squeeze bass',algorithm=18,feedback=5,
        ratios=[2,1,1,3,2,1],levels=[71,79,86,76,82,87],
        shapes='chiff wah body wah wah body',note=40,
        description='Elastic index sweep through a branched stack; accented notes open into a hollow squelch.',tags=['rubber','squelch'])
    add('DUBROOT','Dub root bass',algorithm=29,feedback=1,
        ratios=[1,1,2,1,.5,1],levels=[61,75,35,61,77,58],
        shapes='hammer body chiff body body body',note=36,
        controls={162:1900},description='Dense but restrained low fundamental and octave underpinning, with the pick noise tucked away.',tags=['dub','deep'])
    add('REZZBASS','Resonant FM bass',algorithm=16,feedback=4,
        ratios=[2,1,3,1,2,1],levels=[78,79,88,80,83,88],
        shapes='chiff wah hammer wah wah body',note=40,
        description='Resonant vowel-like sweep produced by the modulation network rather than filter resonance.',tags=['resonant','squelch'])
    add('SUBFELT','Felt sub bass',algorithm=30,feedback=0,
        ratios=[1,2,1,1,.5,2],levels=[69,53,64,76,74,48],
        shapes='body chiff soft body body soft',note=36,
        description='Pure low weight with a little tactile onset and no noisy tail; useful under complex drums.',tags=['sub','soft'])
    add('BRASSBASS','Brass punch bass',algorithm=19,feedback=5,
        ratios=[1,1,2,3,1,1],levels=[91,75,58,70,86,77],
        shapes='splat body hammer chiff body body',note=40,
        description='Brassy upper lip and steady bass core; held notes become rounder after the initial bark.',tags=['brass','punch'])
    add('REEDBASS','Reedbox bass',algorithm=12,feedback=3,
        ratios=[2,4,6,1,2,1],levels=[85,67,58,85,77,67],
        shapes='wah hammer chiff body wah body',note=43,
        description='Odd-harmonic reed color with a narrow woody body; good for nimble octave patterns.',tags=['reed','hollow'])
    add('TALKLOW','Talking low bass',algorithm=5,feedback=2,
        ratios=[1,fixed(510),1,fixed(1180),1,1],levels=[86,68,88,61,82,79],
        shapes='wah body moving body wah body',note=43,
        description='Two stationary formant bands float above a keyboard-tracking fundamental; a synthetic vowel bass.',tags=['vowel','formant'])
    add('FRETLESS','Fretless bloom',algorithm=10,feedback=2,
        ratios=[1,2,1,3,1,1],levels=[80,67,83,61,79,72],
        shapes='soft wah soft chiff soft soft',note=43,
        pitch=[82,78,70,84,49,50,50,50],lfo=[29,55,2,0,0,2],
        description='Smooth singing bass with a modest pitch settling and gently blooming upper mids.',tags=['fretless','singing'])
    add('GRITROOT','Grit root bass',algorithm=13,feedback=6,
        ratios=[1,2,3,1,1,1],levels=[86,75,64,83,73,76],
        shapes='wah hammer chiff body body body',note=38,
        controls={168:5},description='A coarse transient-rich branch over a clean second root; grit yields to a stable note.',tags=['gritty','bass'])
    add('PULSEBASS','Pulsebox bass',algorithm=22,feedback=4,
        ratios=[2,1,1,2,2,1],levels=[87,68,65,48,82,75],
        shapes='wah body body hammer hammer body',note=40,
        detune=[7,6,8,7,7,7],description='Three closely voiced carriers share a hollow pulse spectrum with a separate hard attack.',tags=['pulse','detuned'])
    add('PLUCKROOT','Plucked root bass',algorithm=27,feedback=2,
        ratios=[3,2,1,4,1,.5],levels=[76,79,79,70,71,66],
        shapes='chiff hammer pluck click pluck pluck',note=43,
        description='Short plucked root with low reinforcement and bright string contact; leaves space for dense rhythm.',tags=['pluck','tight'])
    add('SQUISHLOW','Squish low bass',algorithm=17,feedback=5,
        ratios=[1,3,1,1,2,1],levels=[75,72,81,77,88,87],
        shapes='wah hammer wah body wah body',note=38,
        pitch=[99,86,76,88,55,50,50,50],description='Bendy rubber onset and a compressed-sounding hollow sustain generated entirely in FM.',tags=['squish','rubber'])
    return r


def _keys():
    r=[]
    def add(*a,**k): r.append(_row(*a,family='Keys',**k))
    add('TINEGLOW','Glow electric tine',algorithm=5,feedback=1,
        ratios=[14,1,3,1,1,1],levels=[78,72,80,72,66,80],
        shapes='hammer tine hammer tine pluck tine',note=64,
        velocity=[6,2,4,2,3,2],detune=[7,6,7,8,7,7],
        description='Soft tine at light touch, bell-like bite on accents and a long woody body.',tags=['electric-piano','tine'])
    add('REEDSUIT','Suitcase reed keys',algorithm=19,feedback=3,
        ratios=[1,1,2,3,1,1],levels=[86,77,58,70,79,75],
        shapes='hammer tine tine click hammer tine',note=60,
        detune=[7,6,8,7,7,7],description='Warm barking electric keys with unequal fundamental and octave decays.',tags=['electric-piano','reed'])
    add('WOODGRAND','Wood and wire piano',algorithm=7,feedback=2,
        ratios=[4,1,3,1,14,1],levels=[73,78,75,81,75,68],
        shapes='click hammer hammer tine chiff pluck',note=60,
        scaling=3,description='Percussive wooden keyboard with a brief wire sheen; a stylized FM piano rather than a sampled grand.',tags=['piano','wood'])
    add('CLAVSNAP','Snap clavinet',algorithm=3,feedback=4,
        ratios=[5,1,1,3,2,1],levels=[78,92,79,81,86,74],
        shapes='click hammer pluck chiff hammer pluck',note=60,
        description='Clipped string snap and short nasal body; strong velocity accents make rhythm parts speak.',tags=['clav','funk'])
    add('HARPSILK','Silk harpsichord',algorithm=12,feedback=1,
        ratios=[2,4,7,1,3,1],levels=[91,80,75,80,85,73],
        shapes='brightpluck brightstrike brightstrike pluck brightpluck tine',note=67,
        description='Fine bright pluck followed by a clean ringing root, with little low-mid bark.',tags=['harpsichord','pluck'])
    add('CELESTIA','Celestial celesta',algorithm=29,feedback=0,
        ratios=[3.47,1,7.11,2,1,4],levels=[81,73,74,59,70,39],
        shapes='tine ring hammer tine ring tine',note=72,category='Bells',
        description='Small luminous struck bell with a soft fundamental and shimmering upper pair.',tags=['celesta','bell'])
    add('VIBESVEL','Velvet vibraphone',algorithm=21,feedback=0,
        ratios=[4,1,2,3,1,2],levels=[60,75,55,59,74,53],
        shapes='hammer ring tine hammer ring tine',note=67,category='Mallets',
        lfo=[30,30,0,18,0,0],controls={147:1,173:6},
        description='Rounded mallet metal with light tremolo and a clean two-octave spectrum.',tags=['vibes','tremolo'])
    add('MARIMBA','Rosewood marimba',algorithm=10,feedback=1,
        ratios=[4,7,1,3.91,1,1],levels=[68,54,82,64,65,69],
        shapes='click hammer wood click wood wood',note=60,category='Mallets',
        description='Soft woody low mode and a fast higher bar resonance; register scaling tightens the top.',tags=['marimba','wood'])
    add('XYLOPEARL','Pearl xylophone',algorithm=23,feedback=1,
        ratios=[3.97,1,4,3.11,2,1],levels=[79,76,49,68,60,62],
        shapes='click wood short hammer wood wood',note=72,category='Mallets',
        description='Hard compact wood-bar attack with a little pearly high register.',tags=['xylophone','bright'])
    add('STEELPAN','Sunlit steel pan',algorithm=28,feedback=1,
        ratios=[1,2.17,1.49,1,3.43,2],levels=[62,76,80,74,72,62],
        shapes='wood click hammer tine hammer tine',note=67,category='Mallets',
        pitch=[99,91,80,87,52,50,50,50],description='Rounded struck-pan center with irregular metallic overtones and a short pitch settling.',tags=['steelpan','metal'])
    add('KALIMBA','Thumbwood kalimba',algorithm=26,feedback=2,
        ratios=[7.09,2,1,3.13,1,2],levels=[91,81,79,82,69,60],
        shapes='brightstrike brightstrike pluck brightstrike tine pluck',note=67,category='Plucks',
        description='Thumb-tine contact, hollow body and a slightly metallic upper strike.',tags=['kalimba','pluck'])
    add('HARPDEW','Dewdrop harp',algorithm=2,feedback=1,
        ratios=[7,3,1,1,4,1],levels=[48,64,73,79,68,69],
        shapes='click hammer pluck tine hammer tine',note=67,category='Plucks',
        description='Clear plucked string with a cascading high-frequency decay; keeps arpeggios transparent.',tags=['harp','delicate'])
    add('JINGLESTAR','Star jingle bells',algorithm=5,feedback=2,
        ratios=[9.37,2.17,6.43,1.53,4.71,1],levels=[85,66,84,66,79,71],
        shapes='hammer ring tine ring hammer ring',note=72,category='Bells',
        description='Bright clustered holiday-like bells with irregular beating partials and lively accents.',tags=['jingle','bells'])
    add('TUBEBELL','Bronze tubular bell',algorithm=3,feedback=1,
        ratios=[3.53,2.71,1,7.13,1.41,2],levels=[70,85,77,78,77,63],
        shapes='hammer ring ring click tine ring',note=60,category='Bells',
        description='Tall bronze strike with a strong low note and a complex slowly decaying crown.',tags=['tubular','bell'])
    add('GLOCKICE','Ice glockenspiel',algorithm=24,feedback=0,
        ratios=[5.41,1,2.79,4.13,1,7.37],levels=[82,72,54,49,63,44],
        shapes='hammer ring tine tine ring tine',note=79,category='Bells',
        description='Icy small bell with distinct partials and a clean high note; soft velocity stays gentle.',tags=['glockenspiel','ice'])
    add('MUSICBOX','Copper music box',algorithm=25,feedback=0,
        ratios=[6.71,1,2.13,3.37,5.11,8.17],levels=[76,72,49,52,40,34],
        shapes='click tine hammer tine hammer tine',note=76,category='Bells',
        description='Mechanical pin-pluck and a delicate upper-register comb; restrained enough for repeating figures.',tags=['music-box','delicate'])
    return r


def _winds():
    r=[]
    def add(*a,**k): r.append(_row(*a,family='Winds',**k))
    add('SPLATTRUMP','Splat trumpet',algorithm=16,feedback=3,
        ratios=[fixed(57),1,3.43,1,1,1],levels=[67,91,82,72,89,86],
        shapes='chiff blow chiff chiff splat blow',note=64,category='Brass',
        velocity=[5,4,6,3,4,2],pitch=[99,86,78,88,53,50,50,50],
        lfo=[32,58,3,1,0,3],controls={147:1},
        description='Lip flutter and brief inharmonic spit resolve into a strong brassy note; hard accents exaggerate the front.',tags=['trumpet','splat'])
    add('BRONZEBONE','Bronze trombone',algorithm=18,feedback=4,
        ratios=[fixed(43),2,1,1.37,1,1],levels=[62,74,88,75,88,87],
        shapes='chiff splat blow chiff blow soft',note=48,category='Brass',
        pitch=[83,78,74,86,48,50,50,50],lfo=[26,57,2,0,0,3],controls={147:1},
        description='Low squawking brass with a rounded center and a slightly scooped attack; play the lower middle register.',tags=['trombone','squawk'])
    add('HORNGOLD','Golden horn',algorithm=9,feedback=3,
        ratios=[2,1,3,1,1,1],levels=[70,82,64,82,81,68],
        shapes='chiff soft reed soft blow soft',note=55,category='Brass',
        detune=[7,7,7,6,7,8],description='Softer rounded brass with a singing body and small attack bloom; suited to harmonies.',tags=['horn','warm'])
    add('SECTBRASS','Section brass',algorithm=19,feedback=4,
        ratios=[1,1,1,3,1,1],levels=[91,70,70,72,84,75],
        shapes='splat blow blow chiff blow blow',note=60,category='Brass',
        detune=[7,5,9,7,7,7],pitch=[99,82,74,86,52,50,50,50],
        description='Three broad brass components with unequal articulation and mild detune; chord-friendly and assertive.',tags=['brass','ensemble'])
    add('STABCHROME','Chrome brass stab',algorithm=22,feedback=5,
        ratios=[1,1,1,2,2,1],levels=[92,68,69,53,85,75],
        shapes='hammer pluck pluck hammer hammer pluck',note=60,category='Brass',
        detune=[7,6,8,7,7,7],description='Short metallic brass stab with an octave punch; programmed to decay even under a held key.',tags=['brass','stab'])
    add('MUTEHORN','Cup-muted horn',algorithm=12,feedback=4,
        ratios=[2,3,5,1,2,1],levels=[88,72,64,81,81,65],
        shapes='splat chiff reed blow reed soft',note=64,category='Brass',
        description='Narrow pinched brass spectrum with a little nasal edge; complements the open trumpet.',tags=['muted','brass'])
    add('PANBREATH','Breathing pan flute',algorithm=1,feedback=7,
        ratios=[fixed(3170),fixed(1090),1.37,1,2,1],levels=[94,63,58,56,58,84],
        shapes='chiff chiff chiff chiff soft soft',note=72,
        velocity=[3,5,5,2,3,2],pitch=[88,78,70,85,48,50,50,50],
        lfo=[28,55,2,1,0,2],controls={147:1},
        description='Breathy short attack over a near-pure pipe; the noisy branch falls away while the blown note sustains.',tags=['pan-flute','breathy'])
    add('JAZZFLUTE','Air jazz flute',algorithm=3,feedback=7,
        ratios=[fixed(4870),fixed(1510),1,3,2,1],levels=[95,65,59,44,70,83],
        shapes='air air soft chiff reed soft',note=72,
        velocity=[3,4,2,5,3,2],lfo=[33,46,3,1,0,3],controls={147:1},
        description='Sustained quiet air layer, clearer upper partial and delayed vibrato; designed for the flute register.',tags=['flute','air'])
    add('BAMBOOAIR','Bamboo air pipe',algorithm=10,feedback=6,
        ratios=[fixed(2690),2.47,1,3,2,1],levels=[88,61,59,53,62,82],
        shapes='chiff chiff soft chiff soft soft',note=67,
        pitch=[84,75,67,85,47,50,50,50],lfo=[24,52,2,2,0,2],
        description='Hollow bamboo-like pipe with a little breath and a slight unsettled onset; less vibrato than the jazz flute.',tags=['bamboo','pipe'])
    add('CLARIVOX','Clarinet wood',algorithm=7,feedback=2,
        ratios=[2,2,4,1,2,1],levels=[65,84,66,83,79,67],
        shapes='chiff reed reed soft reed soft',note=60,
        lfo=[30,58,2,1,0,2],description='Odd-harmonic low reed with a softer top pair and a woody attack.',tags=['clarinet','reed'])
    add('OBOEEDGE','Oboe edge',algorithm=14,feedback=3,
        ratios=[3,2,2,1,5,1],levels=[76,75,86,82,74,64],
        shapes='chiff reed blow blow chiff soft',note=67,
        lfo=[34,50,3,2,0,3],description='Narrow nasal reed with a firm upper-mid edge and a light secondary root.',tags=['oboe','nasal'])
    add('REEDBARK','Baritone reed bark',algorithm=2,feedback=4,
        ratios=[3,2,2,1,2,1],levels=[69,72,88,84,86,68],
        shapes='chiff splat reed blow splat soft',note=50,
        pitch=[90,80,74,85,49,50,50,50],description='Low raspy reed that barks at accents and softens into a hollow sustained note.',tags=['baritone','reed'])
    add('HARMONICA','Harmonica draw',algorithm=20,feedback=3,
        ratios=[2,2,1,2,1,2],levels=[84,72,79,79,73,56],
        shapes='reed blow blow reed soft soft',note=64,
        detune=[7,7,6,7,8,7],pitch=[86,76,72,84,49,50,50,50],
        description='Compact reedy draw-note with close beating and a breathy pitch settling.',tags=['harmonica','reed'])
    add('DRAWORGAN','Drawbar organ',algorithm=32,feedback=0,
        ratios=[8,6,4,3,2,1],levels=[48,51,61,58,67,79],
        shapes='organ organ organ organ organ organ',note=60,category='Organ',scaling=0,
        velocity=[0,0,0,0,0,0],description='Six sustained harmonic drawbars with immediate key-on and no velocity filtering; a solid clean organ.',tags=['organ','drawbar'])
    add('PIPECHAPEL','Chapel pipe organ',algorithm=31,feedback=1,
        ratios=[2,1,.5,2,4,8],levels=[51,67,73,58,49,37],
        shapes='air soft soft soft soft soft',note=60,category='Organ',scaling=0,
        velocity=[0,0,0,0,0,0],controls={173:12,148:2,194:65},
        description='Soft-speaking pipe registers with a low octave and a modest hall tail; useful for slow harmony.',tags=['organ','pipe'])
    add('REEDCOMBO','Reed combo organ',algorithm=24,feedback=4,
        ratios=[2,1,2,4,3,1],levels=[86,69,56,45,50,65],
        shapes='organ organ organ organ organ organ',note=60,category='Organ',scaling=0,
        velocity=[0,0,0,0,0,0],controls={169:8},
        description='Bright transistor-like reed organ with an additive top and a small chorus halo.',tags=['organ','combo'])
    return r


def _leads():
    r=[]
    def add(*a,**k): r.append(_row(*a,family='Leads',**k))
    add('ACIDPEARL','Pearl acid lead',algorithm=16,feedback=4,
        ratios=[2,1,3,1,2,1],levels=[83,81,77,81,88,86],
        shapes='hammer wah chiff wah wah body',note=60,
        description='Snappy resonant index sweep and a firm center; accents expose a squealing high-mid peak.',tags=['acid','squelchy'])
    add('SQUEALBOX','Squealbox lead',algorithm=17,feedback=6,
        ratios=[3,1,2,1,1,1],levels=[85,78,82,83,91,86],
        shapes='chiff wah body wah splat body',note=64,
        description='A feedback-rich branched lead that moves from soft hollow notes to sharp screaming accents.',tags=['squeal','lead'])
    add('VELVETSOLO','Velvet solo',algorithm=28,feedback=2,
        ratios=[1,3,1,1,2,1],levels=[64,65,78,75,70,71],
        shapes='soft chiff soft soft reed soft',note=67,
        detune=[7,7,7,6,7,8],lfo=[30,46,3,0,0,3],controls={147:1},
        description='Rounded lyrical lead with a soft direct fundamental and delayed vibrato.',tags=['solo','smooth'])
    add('SAWTOOTHFM','Sawtooth FM lead',algorithm=19,feedback=4,
        ratios=[1,1,1,2,1,1],levels=[89,72,70,70,83,76],
        shapes='body body body chiff body body',note=64,
        detune=[7,5,9,7,7,7],description='Broad harmonic lead with three gently differing carriers and a strong held spectrum.',tags=['sawlike','broad'])
    add('SQUAREBIRD','Squarebird lead',algorithm=21,feedback=2,
        ratios=[2,1,2,2,1,1],levels=[85,74,48,82,70,68],
        shapes='body body body reed body body',note=72,
        detune=[7,7,7,7,6,8],description='Hollow odd-harmonic lead with an octave overtone and a small singing detune.',tags=['squarelike','hollow'])
    add('VOXSCREAM','Vox scream',algorithm=5,feedback=3,
        ratios=[1,fixed(620),1,fixed(1470),2,1],levels=[89,67,91,62,82,77],
        shapes='wah body splat body wah body',note=60,
        description='Stationary vocal resonances over a playable root; pitch and velocity reshape the vowel-like edge.',tags=['vowel','squeal'])
    add('RAZORPLUK','Razor pluck',algorithm=11,feedback=4,
        ratios=[3,1,1,7,2,1],levels=[89,80,80,77,84,70],
        shapes='brightpluck brightpluck pluck brightstrike brightpluck pluck',note=64,category='Plucks',
        description='Knife-edged attack followed by a compact hollow decay; leaves space in rapid patterns.',tags=['pluck','razor'])
    add('GLASSARP','Glass arp',algorithm=3,feedback=1,
        ratios=[5.13,2,1,7.23,1.41,2],levels=[73,83,77,70,76,64],
        shapes='click hammer pluck click hammer pluck',note=67,category='Arp',
        description='High-detail glass pluck with contrasting metallic stacks; fast patterns stay separated.',tags=['arp','glass'])
    add('BUBBLESTEP','Bubble step',algorithm=18,feedback=3,
        ratios=[1,2,1,3,2,1],levels=[68,81,77,74,85,85],
        shapes='click wah hammer hammer wah pluck',note=60,category='Arp',
        pitch=[99,89,76,86,57,50,50,50],description='Rubbery per-note bubble with a small pitch fall and a dry stop.',tags=['arp','bubble'])
    add('WIRESEQ','Wire sequence',algorithm=13,feedback=5,
        ratios=[5,3,2,1,7.17,1],levels=[90,85,80,81,88,64],
        shapes='brightstrike brightpluck brightstrike pluck brightstrike pluck',note=64,category='Arp',
        description='Taut wire attack and a thin focused body; articulate in crowded sequencer parts.',tags=['arp','wire'])
    add('DIGIBRASS','Digital brass lead',algorithm=8,feedback=4,
        ratios=[3,1,1,1,2,1],levels=[75,83,89,82,83,69],
        shapes='chiff blow splat blow blow soft',note=64,
        description='Bright brassy lead with a punchy shared modulation branch and a cleaner supporting pair.',tags=['brass','digital'])
    add('RINGPLUCK','Ring pluck',algorithm=23,feedback=2,
        ratios=[3.19,1,2.47,5.13,1,1.49],levels=[87,72,59,79,68,57],
        shapes='hammer pluck pluck click pluck wood',note=67,category='Plucks',
        description='An inharmonic pluck with a recognizable low center and irregular high ringing.',tags=['pluck','inharmonic'])
    add('PIXELPIPE','Pixel pipe',algorithm=30,feedback=1,
        ratios=[1,2,2,1,2,4],levels=[66,64,74,75,44,33],
        shapes='body chiff reed body body body',note=72,
        description='Small hollow game-like lead with a soft sustained fundamental and an octave sparkle.',tags=['pixel','pipe'])
    add('HARDREED','Hard reed lead',algorithm=14,feedback=5,
        ratios=[2,2,1,1,3,1],levels=[78,83,88,84,78,65],
        shapes='chiff wah body body hammer body',note=60,
        description='Hard nasal midrange lead with a short edge on each note; clear enough for unison riffs.',tags=['reed','hard'])
    add('PLASTIK','Plastic pluck',algorithm=26,feedback=3,
        ratios=[2.37,3,1,2,1,2],levels=[90,82,78,85,69,51],
        shapes='brightstrike brightpluck pluck brightstrike wood wood',note=64,category='Plucks',
        description='Hollow plastic knock with a rounded decay and light octave body.',tags=['plastic','pluck'])
    add('ZIGZAG','Zigzag mod lead',algorithm=15,feedback=4,
        ratios=[3,2,1,1,1,1],levels=[76,81,84,82,87,66],
        shapes='chiff wah body body moving body',note=64,
        lfo=[42,20,3,14,4,2],controls={147:1},description='A lively stepped brightness tremor over a biting lead; held notes expose the active modulation.',tags=['lead','moving'])
    return r


def _pads():
    r=[]
    def add(*a,**k): r.append(_row(*a,family='Pads',**k))
    add('DRIFTWOOL','Wool drift pad',algorithm=21,feedback=2,
        ratios=[1,1,1,2,1,1],levels=[80,66,65,70,69,68],
        shapes='bloom swell swell moving swell swell',note=60,
        detune=[7,5,9,7,6,8],lfo=[19,38,2,8,0,2],controls={147:1,173:11,148:2},
        description='Warm four-carrier pad with slow opposing brightness envelopes; steady chords reveal the inner motion.',tags=['warm','floaty'])
    add('BOWEDROOM','Bowed room strings',algorithm=19,feedback=3,
        ratios=[1,1,1,3,1,1],levels=[87,69,68,64,82,71],
        shapes='bow bow bow chiff bow bow',note=60,category='Strings',
        detune=[7,5,9,7,7,8],lfo=[24,47,2,4,0,2],controls={147:1,169:7},
        description='Slightly grainy bowed entrance and softly detuned ensemble body; released notes taper rather than stop.',tags=['strings','bowed'])
    add('GLACIER','Glacier glass pad',algorithm=5,feedback=0,
        ratios=[7.19,1,5.13,2,3.37,1],levels=[85,66,82,62,73,73],
        shapes='shimmer swell bloom swell moving swell',note=64,
        detune=[7,6,7,8,7,7],lfo=[17,30,1,10,0,1],controls={147:1,173:14,148:3,194:67},
        description='Cold glass bands bloom at different speeds over a lower warm floor; bright rather than harsh.',tags=['glass','ambient'])
    add('CHOIRAAH','Open vowel choir',algorithm=5,feedback=1,
        ratios=[1,fixed(720),1,fixed(1280),1,1],levels=[83,67,87,60,69,74],
        shapes='air bow bloom bow soft bow',note=60,
        lfo=[21,52,2,7,0,2],controls={147:1,173:10,148:2},
        description='Two fixed vocal bands and a pitched root create an open synthetic choir; strongest around C3-C5.',tags=['choir','vowel'])
    add('CHOIROOH','Rounded vowel choir',algorithm=10,feedback=1,
        ratios=[1,2,fixed(430),1,1,1],levels=[81,65,71,45,70,76],
        shapes='air moving bow chiff soft bow',note=60,
        lfo=[18,54,2,5,0,2],controls={147:1,173:11,148:2,162:6800},
        description='Rounded closed vowel with a restrained upper air component and slow breath-like onset.',tags=['choir','round'])
    add('AURORAVEIL','Aurora veil',algorithm=28,feedback=2,
        ratios=[2,5.11,1,1,3.07,1],levels=[47,72,78,69,74,70],
        shapes='shimmer bloom moving swell shimmer swell',note=64,
        detune=[8,7,7,5,7,9],lfo=[13,25,2,13,0,2],controls={147:1,169:9,173:12,148:3},
        description='A high veil drifts above two differently evolving bodies; long chords reveal the color changes.',tags=['evolving','veil'])
    add('SOFTBRASS','Soft brass cloud',algorithm=22,feedback=3,
        ratios=[1,1,1,2,1,1],levels=[87,64,64,47,78,73],
        shapes='bloom bow bow bow moving bow',note=60,
        detune=[7,5,9,7,7,7],controls={173:10,148:2},
        description='Broad brass color softened into a pad, retaining some inner bite at high velocity.',tags=['brass','cloud'])
    add('SILKSTRNG','Silk strings',algorithm=20,feedback=2,
        ratios=[1,2,1,1,1,2],levels=[81,64,72,81,71,48],
        shapes='bow moving bow air bow bow',note=64,category='Strings',
        detune=[7,6,5,7,9,8],lfo=[27,49,2,3,0,2],controls={147:1,169:10},
        description='Smooth string-like pad with light octave sheen and moderate tremulous movement.',tags=['strings','silk'])
    add('HARMONIUM','Bellows harmonium',algorithm=25,feedback=3,
        ratios=[2,1,2,3,4,1],levels=[83,65,54,49,43,70],
        shapes='air air air air air air',note=60,category='Organ',
        lfo=[12,30,0,10,0,0],controls={147:1},description='Slow breathy reed-register swell with a gently pulsing bellows envelope.',tags=['harmonium','reed'])
    add('NIGHTBLOOM','Night bloom',algorithm=12,feedback=3,
        ratios=[1,2,5,1,3,1],levels=[77,74,66,78,73,69],
        shapes='moving bloom shimmer swell bloom swell',note=60,
        lfo=[10,20,1,13,0,2],controls={147:1,173:14,148:3,194:67},
        description='A dark pad slowly opens a brighter middle and upper layer, then relaxes under sustained notes.',tags=['dark','bloom'])
    add('FROSTHALO','Frost halo',algorithm=23,feedback=1,
        ratios=[5.17,1,2.13,7.29,1,1],levels=[79,65,53,75,64,68],
        shapes='shimmer swell bloom bloom swell swell',note=67,
        detune=[7,6,7,7,8,7],controls={169:9,173:13,148:3},
        description='Thin icy metallic halo and softer root, with a clearly delayed high layer.',tags=['ice','halo'])
    add('ANALOGMIST','Analog mist',algorithm=29,feedback=3,
        ratios=[1,1,1,1,1,2],levels=[82,67,78,68,62,39],
        shapes='moving swell bloom swell swell swell',note=60,
        detune=[7,5,7,9,6,8],lfo=[16,37,2,3,0,2],controls={147:1,169:10,162:8300},
        description='Soft saw-like FM pairs and additive support with mild ensemble beating.',tags=['warm','ensemble'])
    add('WATERCHOIR','Water choir',algorithm=26,feedback=2,
        ratios=[1,2,fixed(810),3,1,1],levels=[78,75,64,69,73,60],
        shapes='bloom moving swell shimmer swell swell',note=60,
        lfo=[18,20,2,12,0,2],controls={147:1,173:13,148:3,174:5},
        description='Soft shifting vowel with a clear root; quiet phasing adds a watery moving edge.',tags=['vowel','water'])
    add('BRONZESKY','Bronze sky',algorithm=3,feedback=2,
        ratios=[3.17,2.13,1,5.11,1.41,1],levels=[68,80,75,71,77,69],
        shapes='shimmer bloom swell moving bloom swell',note=60,
        controls={173:14,148:2,194:62},description='Slow metallic cloud with a bronze low band and a contrasting higher drifting stack.',tags=['metal','sky'])
    add('LOWCELLO','Low cello shade',algorithm=14,feedback=3,
        ratios=[2,1,1,1,3,1],levels=[72,77,85,82,66,61],
        shapes='chiff bow reed bow chiff bow',note=48,category='Strings',
        lfo=[26,54,2,3,0,2],controls={147:1,162:9500},
        description='Low bowed character with a coarse front and focused sustained body; solo rather than a huge ensemble.',tags=['cello','bowed'])
    add('AIRWINDOW','Air window',algorithm=30,feedback=6,
        ratios=[1,fixed(4970),fixed(1510),1,2,3],levels=[71,92,63,49,45,32],
        shapes='swell air air air swell swell',note=67,
        lfo=[15,40,0,12,0,1],controls={147:1,173:12,148:3},
        description='A breathy high layer floats over a small additive pipe chord; light and sparse in a mix.',tags=['air','floaty'])
    return r


def _textures():
    r=[]
    def add(*a,**k): r.append(_row(*a,family='Experimental',category='Motion',**k))
    add('MERCURY','Mercury liquid',algorithm=17,feedback=4,
        ratios=[2.17,1,3.43,1.41,2,1],levels=[76,78,81,75,83,85],
        shapes='moving bloom shimmer moving bloom soft',note=60,
        lfo=[17,18,3,16,0,2],controls={147:1,173:9,148:3},
        description='Liquid branching sidebands that swell and fold back into a playable low center.',tags=['liquid','evolving'])
    add('QUICKSILVR','Quicksilver squish',algorithm=16,feedback=5,
        ratios=[1.37,2,5.17,1,2.41,1],levels=[77,81,74,78,86,85],
        shapes='chiff wah moving wah bloom body',note=55,
        pitch=[99,82,67,85,58,50,49,50],description='Fast rubber onset followed by a slow changing growl; note length changes the result.',tags=['squishy','growl'])
    add('GLASSRAIN','Glass rain',algorithm=5,feedback=1,
        ratios=[9.19,1,7.31,2,5.17,1],levels=[86,65,83,63,81,69],
        shapes='hammer ring shimmer ring bloom ring',note=72,
        lfo=[29,20,0,19,5,0],controls={147:1,170:10,171:281,173:10,148:3},
        description='Different metallic decays and sample-and-hold brightness flicker create sparse rain-like activity.',tags=['rain','random'])
    add('ALIENREED','Alien reed',algorithm=18,feedback=4,
        ratios=[3.11,1.43,2,1.73,2,1],levels=[77,74,83,79,84,85],
        shapes='chiff reed moving bloom reed body',note=60,
        lfo=[23,31,3,9,0,3],controls={147:1},description='A reed-like center surrounded by shifting noninteger sidebands; odd but still playable.',tags=['alien','reed'])
    add('ROBOTVOX','Robot vowel',algorithm=5,feedback=4,
        ratios=[1,fixed(570),2,fixed(1690),1,1],levels=[89,65,84,60,77,76],
        shapes='moving body bloom body wah body',note=55,
        lfo=[33,10,0,20,4,0],controls={147:1,174:7},description='Fixed formant bands plus stepped amplitude changes make a deliberately synthetic voice.',tags=['robot','vowel'])
    add('DEEPORBIT','Deep orbit',algorithm=15,feedback=3,
        ratios=[.5,1,1,1,3.17,1],levels=[73,76,84,81,78,64],
        shapes='moving drone bloom drone shimmer drone',note=43,
        lfo=[9,10,5,10,0,3],controls={147:1,173:14,148:3,194:69},
        description='Low evolving drone with slow pitch orbit and a small metallic distant layer.',tags=['drone','orbit'])
    add('RADIOSTARS','Radio stars',algorithm=28,feedback=6,
        ratios=[2,fixed(4310),fixed(1190),1,7.13,1],levels=[43,93,65,56,84,72],
        shapes='shimmer moving bloom swell shimmer swell',note=67,
        lfo=[37,5,1,23,5,1],controls={147:1,170:9,171:427,173:12,148:3},
        description='Grainy fixed-frequency air and glass-toned melody flicker around each other.',tags=['radio','space'])
    add('GEARTEETH','Gear teeth',algorithm=11,feedback=6,
        ratios=[1.31,3.17,1,5.29,2.41,1],levels=[88,78,79,83,81,68],
        shapes='hammer short wood click hammer wood',note=55,
        description='A mechanical pluck with dense inharmonic gear chatter that quickly leaves a tuned tail.',tags=['mechanical','pluck'])
    add('WETGONG','Wet gong',algorithm=1,feedback=5,
        ratios=[1.41,2.17,1.73,1,7.13,2.41],levels=[77,79,86,80,85,65],
        shapes='hammer moving ring ring chiff ring',note=43,
        pitch=[99,65,48,80,56,49,50,50],controls={173:14,148:2},
        description='Broad bowed-metal bloom after the strike, with a slowly settling pitch and long wet tail.',tags=['gong','metal'])
    add('NEONBLOBS','Neon blobs',algorithm=8,feedback=5,
        ratios=[2.13,1,3.17,1,1.41,1],levels=[76,81,89,81,81,66],
        shapes='click wah moving pluck wah pluck',note=60,
        pitch=[99,79,65,83,65,48,50,50],description='Squashy pitched blobs with a quick bright impact and a descending elastic body.',tags=['bubble','squishy'])
    add('SQUEAKTOY','Squeak toy',algorithm=12,feedback=5,
        ratios=[2,3.17,5,1,1.41,1],levels=[86,78,75,82,85,63],
        shapes='wah short chiff pluck wah pluck',note=72,
        pitch=[87,72,66,90,61,48,50,50],description='Short high rubber squeak that bends down and clears quickly; a character percussion lead.',tags=['squeak','toy'])
    add('CRYSTALCAV','Crystal cavern',algorithm=23,feedback=2,
        ratios=[7.43,1,2.13,5.17,1,3.31],levels=[85,67,54,78,65,49],
        shapes='bloom swell shimmer moving swell shimmer',note=64,
        controls={173:16,148:3,194:70,170:8,171:613},description='Sparse glass resonances float into a long cloud; use slow intervals rather than dense chord clusters.',tags=['crystal','cavern'])
    add('PULSEMOSS','Pulse moss',algorithm=20,feedback=3,
        ratios=[2,4,1,1,1,2],levels=[83,61,75,82,71,45],
        shapes='moving bloom drone shimmer drone drone',note=55,
        lfo=[28,8,0,26,4,0],controls={147:1,169:8,173:9},
        description='Soft pulse-shaped modulation opens and closes a woody held chord without changing the note.',tags=['pulse','organic'])
    add('WHALEGLASS','Whale glass',algorithm=3,feedback=2,
        ratios=[1.37,.5,1,5.13,1.43,1],levels=[68,83,81,73,78,67],
        shapes='bloom moving swell shimmer bloom swell',note=48,
        pitch=[51,32,25,57,53,48,51,50],lfo=[11,25,4,10,0,3],controls={147:1,173:14,148:3},
        description='A low long-form pitch gesture under a glassy upper stack; intentionally less conventionally stable.',tags=['whale','evolving'])
    add('DUSTBELL','Dust bell',algorithm=10,feedback=7,
        ratios=[fixed(5710),7.17,1,5.13,2.41,1],levels=[94,75,70,71,78,72],
        shapes='chiff hammer ring click tine ring',note=67,
        controls={173:10,148:1},description='A dusty noise-like strike and irregular bright partials over a clear bell center.',tags=['dust','bell'])
    add('FOLDINGSEA','Folding sea',algorithm=13,feedback=4,
        ratios=[1,2.17,4.31,1,3.13,1],levels=[82,78,68,78,81,70],
        shapes='moving shimmer bloom drone bloom swell',note=55,
        lfo=[8,16,2,16,0,2],controls={147:1,174:9,173:15,148:3,194:68},
        description='Slow evolving modulation branches cross in brightness while a quiet phase wash expands the tail.',tags=['sea','evolving'])
    return r


# An explicit, source-controlled voicing pass after the first 192-instrument
# render matrix (2026-10-22). Only output carriers are level-trimmed: increasing
# a modulator instead would change the intended harmonic character. These are
# not render-time normalization values and do not depend on machine audio gain.
# Quiet hats remain quieter than pads; synth-mode four-note headroom is retained.
_CARRIER_TRIM_BY_GROUP = dict(percussion=3,bass=3,keys=4,winds=3,
                              leads=4,pads=5,textures=4)
_CARRIER_TRIM_BY_NAME = {
    'MARROW':0, 'PUNCH':2, 'SUBDROP':2, 'RUBBERK':2, 'INDUSTRYK':5,
    'CLAVETAP':6, 'TICKHAT':6, 'OPENFOIL':5, 'RIDESHARD':5,
    'TRIANGLE':5, 'TAMBFIZZ':4, 'CLAPROOM':4,
    'AIRWINDOW':8, 'HARMONIUM':7, 'ANALOGMIST':6,
    'REEDCOMBO':8, 'PIPECHAPEL':7, 'DRAWORGAN':5,
    'MUSICBOX':6, 'STEELPAN':5, 'GLOCKICE':5,
    'RADIOSTARS':7, 'CRYSTALCAV':6, 'GLASSRAIN':5,
    'PIXELPIPE':5, 'RINGPLUCK':5, 'GLASSARP':5,
}


def recipes():
    """Return independent mutable dictionaries for all 128 original voices."""
    result = _percussion()+_bass()+_keys()+_winds()+_leads()+_pads()+_textures()
    if len(result) != 128:
        raise AssertionError('The authored FM collection must contain 128 voices')
    if len({x['id'] for x in result}) != 128 or len({x['name'] for x in result}) != 128:
        raise AssertionError('Every authored voice needs a unique identity and name')
    for row in result:
        trim = _CARRIER_TRIM_BY_NAME.get(row['name'],_CARRIER_TRIM_BY_GROUP[row['group']])
        for i in range(6):
            if CARRIERS[row['vced'][134]] & (1 << i):
                row['vced'][21*i+16] = min(99,row['vced'][21*i+16]+trim)
    return deepcopy(result)
