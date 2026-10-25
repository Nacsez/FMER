"""Original FMER VA sound collection, candidate 2026-10-22.

SPDX-License-Identifier: GPL-3.0-only

These are independently authored recipes, not translations or edits of an OEM
bank. ``recipes()`` returns fresh plain dictionaries; importing it has no I/O.
They describe the currently implemented single-oscillator instrument: a VA
low-pass, amplitude ADSR, pitch-only sine LFO and the shared effects chain.
There is deliberately no claimed PWM, unison, filter envelope, oscillator
layering, pitch envelope or acoustic-drum emulation. FX belong to the shared
chain, so a four-track mix does not retain a separate FX chain for each patch.

The assembler must mirror controls[144] into VCED[144], set the ten-byte name,
and validate the resulting complete native instrument. All non-sound state is
the assembler's responsibility; no pattern, transport, mixer or playing mode
is encoded here. Stock public defaults and published packages are unchanged.

Conceptual sources only; no parameter recipes copied:
https://moogmusic-help.freshdesk.com/en/support/solutions/articles/69000866774-synthesis-101-an-introduction-to-subtractive-synthesis
https://learningsynths.ableton.com/recipes/plucked-bass
"""

from copy import deepcopy


SOURCES = (
    "https://moogmusic-help.freshdesk.com/en/support/solutions/articles/69000866774-synthesis-101-an-introduction-to-subtractive-synthesis",
    "https://learningsynths.ableton.com/recipes/plucked-bass",
)

WAVES = {"sine": 0, "saw": 1, "square": 2, "triangle": 3, "noise": 4}


def _voice(slug, name, title, category, family, wave, cutoff, resonance, adsr,
           description, *, note=60, transpose=24, lfo=(500, 8, False),
           fx=None, modulation=(0, 0), tags=(), technique=None):
    """Use integer native values, including milliseconds, Hz and percentages."""
    attack, decay, sustain, release = adsr
    rate, depth, enabled = lfo
    controls = {
        144: transpose, 145: 0, 146: 0, 147: int(enabled), 148: 0, 149: 0,
        159: 0, 160: 1, 161: WAVES[wave], 162: 20000, 163: resonance,
        164: attack, 165: decay, 166: sustain, 167: release,
        168: 0, 169: 0, 170: 0, 171: 250, 172: 28, 173: 0, 174: 0,
        175: rate, 176: depth, 177: cutoff, 194: 48,
    }
    controls.update(fx or {})
    if technique is None:
        technique = (
            f"{wave.capitalize()} oscillator; {cutoff} Hz VA low-pass with "
            f"{resonance}% resonance; amplitude ADSR "
            f"{attack}/{decay} ms, {sustain}% sustain, {release} ms release."
        )
        if enabled and wave != "noise":
            technique += f" Pitch sine LFO {rate / 100:g} Hz, +/-{depth} cents."
        if wave == "noise":
            technique += " Noise is unpitched; note number does not retune it."
        if controls[145]:
            technique += (
                f" Shared {'high-pass' if controls[145] == 1 else 'band-pass'} "
                f"at {controls[162]} Hz."
            )
    return dict(
        id="va_" + slug, name=name, title=title, category=category, family=family,
        tags=["original", "va", wave, *tags], description=description,
        technique=technique, audition_note=note, controls=controls,
        modulation_profiles=list(modulation),
    )


def _percussion():
    return [
        _voice("sub_thump", "SUB THUMP", "Sub Thump", "Percussion", "kick", "sine", 1200, 0,
               (1, 440, 0, 110), "Deep, clean bass-drum body with a rounded front. A sub thump, without a pitch-drop transient.",
               transpose=0, tags=("deep", "kick", "dry")),
        _voice("dub_knock", "DUB KNOCK", "Dub Knock", "Percussion", "kick", "triangle", 520, 31,
               (0, 270, 0, 70), "Compact low knock with a woody edge and restrained saturation.",
               transpose=0, fx={168: 16}, tags=("punch", "kick", "woody")),
        _voice("rubber_kick", "RUBBER KIK", "Rubber Kick", "Percussion", "kick", "sine", 1800, 12,
               (0, 580, 0, 150), "Long, rubbery tuned kick body with a small pitch wobble. No one-shot pitch envelope is implied.",
               transpose=0, lfo=(480, 63, True), fx={168: 8}, tags=("rubbery", "kick", "tuned")),
        _voice("paper_snap", "PAPER SNAP", "Paper Snap", "Percussion", "snare", "noise", 11000, 15,
               (0, 105, 0, 32), "Dry papery snap that leaves space for a bass line; the band-pass picks out the crack.",
               fx={145: 2, 146: 48, 162: 1850, 168: 9}, tags=("snappy", "dry", "snare")),
        _voice("wire_snare", "WIRE SNARE", "Wire Snare", "Percussion", "snare", "noise", 6800, 28,
               (0, 195, 0, 65), "Brisk wire-like noise snare with a crisp upper edge and a short room reflection.",
               fx={145: 1, 146: 11, 162: 620, 173: 8}, tags=("scratchy", "snare", "bright")),
        _voice("body_snare", "BODY SNARE", "Body Snare", "Percussion", "snare", "noise", 1950, 78,
               (0, 225, 0, 75), "Lower, chunky noise snare: the resonant body supplies weight rather than an added oscillator.",
               fx={168: 13, 173: 5}, tags=("chunky", "snare", "resonant")),
        _voice("dry_clap", "DRY CLAP", "Dry Clap", "Percussion", "clap", "noise", 9300, 8,
               (0, 112, 0, 32), "Compact synthetic clap-like burst, focused in the midrange; intentionally a single burst.",
               fx={145: 2, 146: 37, 162: 1550, 173: 10}, tags=("clap", "tight", "midrange")),
        _voice("room_clap", "ROOM CLAP", "Room Clap", "Percussion", "clap", "noise", 7500, 22,
               (0, 155, 0, 45), "Wider clap-like accent with a 28 ms reflection and a short room around it.",
               fx={145: 2, 146: 31, 162: 2050, 170: 24, 171: 28, 172: 12, 173: 18, 194: 29},
               tags=("clap", "room", "slapback")),
        _voice("chip_hat", "CHIP HAT", "Chip Hat", "Percussion", "hat", "noise", 17500, 4,
               (0, 39, 0, 15), "Tiny bright closed-hat tick with the low frequencies removed.",
               fx={145: 1, 146: 8, 162: 5600}, tags=("hat", "closed", "bright")),
        _voice("open_air", "OPEN AIR", "Open Air Hat", "Percussion", "hat", "noise", 15500, 10,
               (0, 370, 0, 160), "Open noise hat with a longer airy tail; a different articulation from the closed hat.",
               fx={145: 1, 146: 13, 162: 4300, 173: 6}, tags=("hat", "open", "airy")),
        _voice("tin_rattle", "TIN RATTLE", "Tin Rattle", "Percussion", "metal", "noise", 10600, 48,
               (0, 285, 0, 90), "Noisy rattling percussion with moving comb-like colour from chorus and phaser.",
               fx={145: 1, 146: 24, 162: 2700, 169: 18, 174: 29}, modulation=(2, 2),
               tags=("metal", "rattle", "moving")),
        _voice("dust_shake", "DUST SHAKE", "Dust Shaker", "Percussion", "shaker", "noise", 18000, 3,
               (5, 76, 0, 28), "Soft-fronted high-mid shaker grain for quieter subdivisions and velocity accents.",
               fx={145: 2, 146: 35, 162: 6900}, tags=("shaker", "soft", "grain")),
        _voice("low_tom", "LOW TOM", "Low Tom", "Percussion", "tom", "triangle", 1250, 36,
               (0, 325, 0, 95), "Low, tuned membrane-like knock with audible harmonics and a compact tail.",
               note=57, transpose=12, fx={168: 7, 173: 7}, tags=("tom", "tuned", "low")),
        _voice("bongo_pop", "BONGO POP", "Bongo Pop", "Percussion", "hand drum", "sine", 3100, 37,
               (0, 145, 0, 45), "Small tuned hand-drum pop with a nearly immediate front and a little room.",
               note=65, transpose=12, fx={168: 11, 173: 9}, tags=("bongo", "tuned", "pop")),
        _voice("wood_rim", "WOOD RIM", "Wood Rim", "Percussion", "rim", "square", 3400, 28,
               (0, 34, 0, 15), "Short pitched rim tick with a hollow midrange bite, useful against deep kicks.",
               note=78, fx={145: 2, 146: 55, 162: 1900, 168: 13}, tags=("rim", "woody", "tick")),
        _voice("trash_cym", "TRASH CYM", "Trash Cymbal", "Percussion", "cymbal", "noise", 15000, 34,
               (1, 1650, 0, 580), "Long, rough crash texture with slow phaser movement and a modest room tail.",
               fx={145: 1, 146: 12, 162: 2100, 168: 11, 174: 27, 173: 17, 194: 57},
               modulation=(0, 1), tags=("cymbal", "trash", "long")),
    ]


def _bass():
    return [
        _voice("foundation", "FOUNDATION", "Foundation Sub", "Bass", "sub", "sine", 340, 0,
               (4, 330, 88, 95), "Clean, steady low end; pressure comes from the fundamental rather than bright effects.",
               note=36, tags=("sub", "solid", "dry")),
        _voice("square_low", "SQUARE LOW", "Square Low", "Bass", "square bass", "square", 490, 23,
               (2, 290, 69, 80), "Thick square-wave bass with a rounded top that keeps the odd harmonics close to the body.",
               note=38, fx={168: 7}, tags=("round", "thick", "steady")),
        _voice("saw_palm", "SAW PALM", "Palm Bass", "Bass", "plucked bass", "saw", 880, 57,
               (1, 205, 15, 65), "Short, muted saw bass with a strong resonant edge and a small held body.",
               note=40, fx={168: 9}, tags=("plucked", "tight", "muted")),
        _voice("acid_bite", "ACID BITE", "Acid Bite", "Bass", "resonant bass", "saw", 1320, 85,
               (1, 240, 22, 75), "Sharp static-resonance bass for manual cutoff performance; the envelope shapes loudness, not cutoff.",
               note=40, fx={168: 16}, tags=("squelchy", "resonant", "manual sweep")),
        _voice("square_peg", "SQUARE PEG", "Square Peg", "Bass", "plucked bass", "square", 2450, 41,
               (0, 128, 0, 46), "Hard-edged little bass peg that stops cleanly between busy sequencer steps.",
               note=41, fx={168: 11}, tags=("staccato", "plucked", "arcade")),
        _voice("fuzz_root", "FUZZ ROOT", "Fuzz Root", "Bass", "driven bass", "saw", 1950, 24,
               (3, 420, 73, 120), "Grainy sustained bass with restrained low-pass filtering after its rich oscillator.",
               note=38, fx={162: 1450, 146: 19, 168: 38}, tags=("fuzz", "grit", "sustain")),
        _voice("rubber_low", "RUBBER LOW", "Rubber Low", "Bass", "moving bass", "triangle", 1100, 36,
               (3, 360, 54, 105), "Rounded triangle bass with an obvious but shallow pitch wobble.",
               note=40, lfo=(230, 31, True), fx={168: 14}, tags=("rubbery", "wobble", "soft")),
        _voice("dub_chord", "DUB CHORD", "Dub Chord Bass", "Bass", "dub bass", "square", 710, 35,
               (4, 420, 18, 200), "Dark plucked chord-bass with dotted echoes; short gates keep the rhythm clean.",
               note=43, fx={169: 9, 170: 23, 171: 375, 172: 35, 159: 2, 173: 7},
               modulation=(0, 0), tags=("dub", "echo", "dark")),
        _voice("talk_box", "TALK BOX", "Talking Box", "Bass", "band-pass bass", "saw", 6500, 28,
               (3, 310, 59, 130), "Nasal band-passed bass with a slow phaser that changes its vowel-like colour.",
               note=43, fx={145: 2, 146: 55, 162: 820, 168: 12, 174: 39},
               modulation=(0, 0), tags=("nasal", "moving", "vowel-like")),
        _voice("grit_step", "GRIT STEP", "Grit Step", "Bass", "driven bass", "saw", 5300, 48,
               (0, 175, 32, 60), "Bright, wiry bass stab with drive and enough upper harmonics to cut through a drum loop.",
               note=40, fx={145: 1, 146: 8, 162: 35, 168: 29}, tags=("gritty", "bright", "step")),
        _voice("hollow_low", "HOLLOW LOW", "Hollow Low", "Bass", "hollow bass", "square", 1750, 14,
               (8, 470, 58, 170), "Hollow square bass shaded by a gentle moving notch and restrained chorus.",
               note=41, fx={169: 14, 174: 21}, modulation=(0, 1), tags=("hollow", "rounded", "moving")),
        _voice("soft_anchor", "SOFTANCHOR", "Soft Anchor", "Bass", "soft bass", "triangle", 650, 15,
               (85, 520, 83, 550), "Slow-fronted soft bass for ambient harmony; long enough to connect notes without a forced glide mode.",
               note=36, tags=("soft", "ambient", "warm")),
    ]


def _leads():
    return [
        _voice("sunblade", "SUNBLADE", "Sunblade", "Leads", "saw lead", "saw", 10500, 19,
               (3, 165, 87, 145), "Bright singing saw lead with a narrow vibrato and a short supportive echo.",
               note=69, lfo=(620, 10, True), fx={170: 13, 171: 230, 173: 9}, tags=("bright", "singing", "saw")),
        _voice("reed_ribbon", "REEDRIBBON", "Reed Ribbon", "Leads", "reed lead", "square", 3500, 51,
               (19, 260, 78, 190), "Reedy sustained lead with a small onset swell and expressive pitch vibrato.",
               note=67, lfo=(580, 15, True), fx={174: 10, 173: 12}, tags=("reed", "vibrato", "warm")),
        _voice("whistle", "WHISTLE", "Clean Whistle", "Leads", "whistle", "sine", 12000, 0,
               (16, 210, 92, 130), "Clear whistle tone with a narrow vibrato; intentionally pure rather than breathy flute emulation.",
               note=79, lfo=(670, 21, True), fx={170: 10, 171: 190, 173: 14}, tags=("whistle", "pure", "high")),
        _voice("chip_race", "CHIP RACE", "Chip Race", "Leads", "chip lead", "square", 16000, 5,
               (1, 110, 81, 48), "Immediate square-wave melody with short release and little ambience, made for fast lines.",
               note=72, fx={170: 10, 171: 125, 172: 17}, tags=("arcade", "chip", "fast")),
        _voice("acid_tooth", "ACID TOOTH", "Acid Tooth", "Leads", "resonant lead", "saw", 2450, 88,
               (1, 190, 29, 80), "Pointed resonant lead that invites cutoff-knob gestures. Static filter position keeps the rhythm predictable.",
               note=60, fx={168: 18, 170: 13, 171: 167, 172: 24}, tags=("squelchy", "resonant", "manual sweep")),
        _voice("pin_needle", "PIN NEEDLE", "Pin Needle", "Arp", "arp pluck", "square", 7200, 32,
               (0, 77, 0, 30), "Needle-sharp pluck that leaves clear gaps in high-speed arpeggios.",
               note=72, fx={170: 14, 171: 250, 172: 24, 159: 3}, tags=("arp", "staccato", "bright")),
        _voice("saw_bead", "SAW BEAD", "Saw Bead", "Arp", "arp pluck", "saw", 4700, 62,
               (1, 145, 0, 58), "Round-edged resonant beads with just enough dotted delay to connect an arp.",
               note=64, fx={170: 18, 171: 375, 172: 27, 159: 2, 173: 5}, tags=("arp", "plucked", "resonant")),
        _voice("bubble_tongue", "BUBBLETONG", "Bubble Tongue", "Arp", "character pluck", "triangle", 5300, 24,
               (1, 235, 0, 90), "Squishy little pitch-wobbling pluck with its middle frequencies brought forward.",
               note=67, lfo=(870, 84, True), fx={145: 2, 146: 55, 162: 1100, 173: 9},
               tags=("squishy", "bubbly", "wobble")),
        _voice("kite_lead", "KITE LEAD", "Kite Lead", "Leads", "chorused lead", "saw", 8200, 15,
               (8, 270, 85, 290), "Floating saw lead carried by chorus, with enough definition to remain melodic.",
               note=72, lfo=(710, 6, True), fx={169: 32, 173: 18, 170: 9, 171: 310},
               modulation=(1, 0), tags=("floaty", "chorused", "singing")),
        _voice("folded_edge", "FOLDEDGE", "Folded Edge", "Leads", "driven lead", "square", 12000, 10,
               (2, 240, 63, 105), "Compressed, driven square lead with a focused top. This uses saturation, not a wavefolder engine.",
               note=65, fx={162: 4900, 146: 12, 168: 30, 173: 7}, tags=("driven", "hard", "square")),
        _voice("robot_trill", "ROBOTTRILL", "Robot Trill", "Leads", "character lead", "saw", 5900, 55,
               (1, 330, 73, 185), "Fast, wide pitch vibrato makes an intentionally artificial squealing melody.",
               note=67, lfo=(970, 94, True), fx={174: 15, 170: 12, 171: 145},
               modulation=(0, 2), tags=("squeaky", "robot", "fast vibrato")),
        _voice("nasal_pipe", "NASAL PIPE", "Nasal Pipe", "Leads", "band-pass lead", "square", 9500, 24,
               (11, 280, 79, 195), "Narrow, pipe-like lead shaded by a gently moving phaser; useful above a dense bass part.",
               note=72, lfo=(420, 8, True), fx={145: 2, 146: 35, 162: 2850, 174: 23, 173: 14},
               modulation=(0, 0), tags=("nasal", "pipe", "focused")),
    ]


def _keys():
    return [
        _voice("velvet_key", "VELVET KEY", "Velvet Key", "Keys", "soft keys", "triangle", 3100, 13,
               (4, 1300, 16, 430), "Soft electric-keyboard impression with a rounded attack and a playable sustaining body.",
               fx={169: 16, 173: 13}, modulation=(0, 0), tags=("velvet", "soft", "keys")),
        _voice("square_clav", "SQUARECLAV", "Square Clav", "Plucks", "clav pluck", "square", 4300, 34,
               (0, 165, 0, 50), "Clipped, hollow pluck with a dry keyed-string character and a small amount of drive.",
               note=60, fx={168: 13}, tags=("clav-like", "plucked", "dry")),
        _voice("tiny_mallet", "TINYMALLET", "Tiny Mallet", "Mallets", "soft mallet", "sine", 13000, 0,
               (2, 660, 0, 220), "Small rounded sine mallet with a delicate room tail; especially useful in the upper register.",
               note=76, fx={173: 16, 148: 1, 194: 43}, tags=("mallet", "pure", "delicate")),
        _voice("bark_key", "BARK KEY", "Bark Key", "Keys", "resonant keys", "saw", 1850, 76,
               (1, 650, 9, 180), "A woody, resonant keyboard bark whose loudness fades into a small held body.",
               note=60, fx={168: 10, 173: 8}, tags=("bark", "woody", "resonant")),
        _voice("damp_string", "DAMPSTRING", "Damped String", "Plucks", "long pluck", "triangle", 9500, 21,
               (1, 1820, 0, 380), "Soft long pluck with a clean harmonic outline; finger release damps it before the full decay.",
               note=65, fx={169: 12, 173: 14}, modulation=(0, 0), tags=("string-like", "plucked", "long")),
        _voice("droplet", "DROPLET", "Droplet", "Mallets", "echo mallet", "sine", 15000, 0,
               (0, 310, 0, 95), "Clear little droplet followed by a short repeat; compact enough for a sequenced counterline.",
               note=79, fx={170: 25, 171: 170, 172: 31, 173: 15, 148: 1}, tags=("water", "mallet", "echo")),
        _voice("piped_key", "PIPED KEY", "Piped Key", "Organ", "square organ", "square", 5200, 9,
               (3, 70, 94, 65), "Compact square-wave organ tone with a firm hold and a deliberately clean stop.",
               note=60, fx={169: 14, 173: 10}, modulation=(1, 0), tags=("organ", "hollow", "steady")),
        _voice("tack_key", "TACK KEY", "Tack Key", "Keys", "bright keys", "saw", 6700, 18,
               (2, 1050, 7, 260), "Bright saw keyboard strike with enough dry edge for rhythmic chord parts.",
               note=60, fx={168: 7, 173: 11, 148: 1}, tags=("bright", "struck", "keys")),
    ]


def _textures():
    return [
        _voice("velvet_air", "VELVET AIR", "Velvet Air", "Pads", "warm pad", "saw", 1490, 11,
               (820, 1900, 75, 2550), "Low, soft cloud of saw harmonics with slow chorus and a rounded hall tail.",
               lfo=(210, 5, True), fx={169: 32, 173: 31, 148: 2, 194: 64},
               modulation=(0, 0), tags=("warm", "floaty", "pad")),
        _voice("glass_tide", "GLASS TIDE", "Glass Tide", "Pads", "sine pad", "sine", 16000, 0,
               (740, 2100, 79, 3200), "Pure tone carried through a slow pitch tide and a long cloud reverb; intentionally sparse harmonically.",
               note=67, lfo=(34, 74, True), fx={169: 18, 173: 41, 148: 3, 194: 73},
               modulation=(0, 0), tags=("glass", "slow", "drifting")),
        _voice("bronze_sky", "BRONZE SKY", "Bronze Sky", "Pads", "hollow pad", "square", 2600, 24,
               (380, 1250, 72, 1900), "Hollow square pad with a bronzed moving notch and a wide chorus halo.",
               lfo=(330, 7, True), fx={169: 27, 174: 34, 173: 24, 148: 2, 194: 58},
               modulation=(1, 0), tags=("hollow", "moving", "bronze")),
        _voice("soft_fire", "SOFT FIRE", "Soft Fire", "Pads", "bright swell", "saw", 5900, 17,
               (1600, 2000, 74, 2900), "A bright slow swell with a long rounded release; a warm harmonic bed behind a lead.",
               lfo=(180, 5, True), fx={169: 24, 173: 30, 148: 2, 194: 66},
               modulation=(0, 0), tags=("swell", "bright", "slow")),
        _voice("silk_string", "SILKSTRING", "Silk String", "Strings", "string pad", "saw", 7100, 10,
               (240, 900, 81, 1250), "A gentle string-like saw ensemble impression using chorus rather than oscillator unison.",
               lfo=(560, 8, True), fx={169: 34, 173: 24, 148: 2, 194: 56},
               modulation=(1, 0), tags=("string-like", "silky", "chorused")),
        _voice("breath_wall", "BREATHWALL", "Breath Wall", "Pads", "noise pad", "noise", 2400, 23,
               (950, 2200, 63, 2150), "A continuous, unpitched wall of warm breath with its middle band brought forward.",
               fx={145: 2, 146: 22, 162: 920, 173: 28, 148: 2, 194: 61}, tags=("breath", "noise", "warm")),
        _voice("frozen_dust", "FROZENDUST", "Frozen Dust", "Pads", "noise pad", "noise", 14500, 16,
               (1450, 2800, 45, 3450), "A thin upper-air noise cloud, designed as a texture rather than a pitched chord instrument.",
               fx={145: 1, 146: 11, 162: 4700, 169: 16, 173: 39, 148: 2, 194: 69},
               modulation=(2, 0), tags=("ice", "airy", "noise")),
        _voice("whale_song", "WHALE SONG", "Whale Song", "Motion", "slow pitch texture", "sine", 2200, 9,
               (2100, 2400, 85, 3650), "Very slow, wide pitch drift with long echoes; hold notes to let the contour develop.",
               note=55, lfo=(16, 96, True), fx={169: 12, 170: 25, 171: 830, 172: 39, 173: 33, 148: 3, 194: 71},
               modulation=(0, 0), tags=("whale", "slow", "drifting")),
        _voice("warp_tape", "WARP TAPE", "Warp Tape", "Pads", "tape-like pad", "triangle", 4900, 17,
               (90, 1650, 77, 1850), "Rounded pad with audible slow wow, subdued chorus and irregular-feeling fixed-time echoes.",
               lfo=(67, 43, True), fx={169: 17, 170: 23, 171: 410, 172: 36, 173: 26, 148: 1, 194: 59},
               modulation=(0, 0), tags=("tape-like", "wow", "warm")),
        _voice("swamp_wave", "SWAMP WAVE", "Swamp Wave", "Motion", "resonant texture", "saw", 620, 89,
               (460, 1250, 68, 1580), "A low resonant growl with slow moving notches and gentle pitch undulation.",
               note=48, lfo=(122, 33, True), fx={168: 12, 174: 43, 173: 23, 148: 3, 194: 60},
               modulation=(0, 1), tags=("swamp", "squelchy", "low")),
        _voice("magnet_fog", "MAGNET FOG", "Magnet Fog", "Motion", "phased pad", "square", 2400, 54,
               (1150, 1900, 67, 3250), "Dense hollow pad with a pronounced slow phaser sweep and a quiet chorus halo.",
               lfo=(31, 14, True), fx={169: 12, 174: 54, 173: 28, 148: 2, 194: 67},
               modulation=(0, 0), tags=("magnetic", "phased", "evolving")),
        _voice("radio_ghost", "RADIOGHOST", "Radio Ghost", "Motion", "noise texture", "noise", 9400, 22,
               (250, 2250, 45, 1850), "Narrow noisy whistle-like colour drifting through chorus and phaser; no stable musical pitch is promised.",
               fx={145: 2, 146: 66, 162: 2350, 169: 24, 174: 45, 173: 25, 148: 3, 194: 61},
               modulation=(2, 1), tags=("radio", "noise", "weird")),
        _voice("crystal_mist", "CRYSTLMIST", "Crystal Mist", "Pads", "vibrating pad", "triangle", 14500, 12,
               (690, 1500, 62, 2950), "Bright upper-register pad with a quick wide vibrato and a shimmering chorus texture.",
               note=72, lfo=(730, 40, True), fx={169: 44, 173: 35, 148: 3, 194: 67},
               modulation=(2, 0), tags=("crystal", "shimmer", "floaty")),
        _voice("sonar_loop", "SONAR LOOP", "Sonar Loop", "Motion", "echo pluck", "sine", 4000, 0,
               (0, 510, 0, 190), "A pure short sonar ping repeated in eighth-note echoes; notes and rhythm remain easy to hear.",
               note=79, fx={170: 42, 171: 250, 172: 51, 159: 3, 173: 22, 148: 2, 194: 53},
               tags=("sonar", "echo", "pulse")),
        _voice("orbit_beacon", "ORBITBEACN", "Orbit Beacon", "Motion", "siren texture", "square", 5100, 36,
               (85, 680, 34, 950), "A narrow musical siren with fast pitch movement and phaser-coloured reflections.",
               note=72, lfo=(240, 100, True), fx={170: 20, 171: 290, 172: 37, 174: 29, 173: 19},
               modulation=(0, 2), tags=("siren", "space", "weird")),
        _voice("rust_bloom", "RUST BLOOM", "Rust Bloom", "Motion", "noise swell", "noise", 11000, 49,
               (2350, 1650, 0, 1250), "A slow noisy bloom that fades even while held, with grit and moving spectral notches.",
               fx={145: 1, 146: 24, 162: 1450, 168: 16, 174: 39, 173: 29, 148: 3, 194: 64},
               modulation=(0, 1), tags=("rust", "swell", "evolving")),
    ]


def recipes():
    """Return 64 distinct originals; callers may safely edit their own copy."""
    result = []
    for group, voices in (("percussion", _percussion()), ("bass", _bass()),
                          ("leads", _leads()), ("keys", _keys()),
                          ("pads", _textures())):
        for voice in voices:
            voice["group"] = group
            result.append(voice)
    return deepcopy(result)
