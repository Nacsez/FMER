## Editor save conflicts - 21 October 2026

Refresh saved bank metadata without replacing the working draft. Unrelated slot changes do not prevent saving. A changed destination shows its current name and requires explicit replacement confirmation; Cancel preserves both. A save-time race keeps the draft and gives a retry instruction, never silently retries a write. Opening PC sound banks refreshes its saved view.

## Companion sound sources - 20 October 2026

Library has Included & community sounds: separate64-sound FMER and128-sound OEM imports, plus explicit read-only community capture. Imports require review, preserve PC banks/device data, retain provenance and support one Undo. Complete duplicate pack imports are inert; partial duplicates need confirmation. Captures use existing progress and diagnostic export. No hardware access on page load; unsupported conversion/write scopes are stated.

## 734 visual field guide — 19 October 2026

Manual plates use the actual240×240 production LCD renderer with labeled
illustrative state, or isolated captures of the real Companion UI. Preserve those
pixels; place arrows and labels in a separate SVG layer. Use the existing CADER
palette, a consistent FMER text wordmark, numbered pink pointers and concise
green location labels. Match screen captions to panel-model indices, not visual
menu traversal order. Mark hypothetical data as illustrative; these are not
hardware photographs or audio measurements. Export SVG, PNG and printable PDF,
with the same sheets reachable from offline Help. The shortcuts fit one page.

## 734 section navigation and explicit mode selection ? 18 October 2026

Hold FX/SEQ/EDIT/GLO/LFO800ms to return to the section landing page; long holds do not replay a tap or toggle LFO. SEQ landing is Mixer in4T, single-track Song in1V/4V; page traversal never changes mode or interrupts playback. Mode selector is a bounded1V/4V/4T choice on PLAY MODE K1, GLO K1 and preset-browser SELECT; PRESETS continues browsing instruments. Preserve the single-line header. Battery color means observed USB activity (green) or estimated below10% (pink, priority), never inferred charging current. See DEVELOPMENT_734.md.

## 733.5 selection visibility and beta companion

Mixer editing layers use a complete pink border and dark panel fill for the active control on every track; the selected track header has a separate underline. Focused parameter rows and selected FX-chain stages use full-width outlines. State colors remain distinct from focus geometry. Companion adds explicit original-firmware selection/inspection and optional feedback export. Stock application restore is never labeled a complete factory-settings reset.

## Companion733.3 freshness and lifecycle

Connection detection is distinct from identity verification. Passive3s endpoint checks clear cached instruments/projects after unplug/reconnect; failed operations invalidate verification. Completed operation banners show timestamps so historical results are not presented as live state. Mutating jobs invalidate catalog caches. Last-tab close schedules45s idle shutdown, with active transfers protected. New builds gracefully close older idle instances and report a busy older instance without process killing. Console renderer helpers are hidden.

## Companion733.2 operation feedback - 17 October2026

Device jobs have a persistent sticky progress banner, phase message, exact byte/slot counts when known and elapsed time. Unknown totals remain indeterminate; completion requires the operation result, never elapsed time. Disable device/editor actions and Quit during a transfer; keep status monitoring through browser connection loss. Completed/failed results remain visible with expandable diagnostics. Connection discovery recognizes stock, current FMER and updater independently of library capabilities. The main UI uses product language; qualification evidence belongs in project records and technical disclosures. CADER colors remain unchanged.

## 730 performance and arrangement contract — 15 October 2026

FX routing selection follows the displayed permutation. Both filter focus overlays and lower sliders share LP-left, HP-right and wider BP-center shading. Mixer traversal is Patch, Pattern, Run, Volume, Mute, Solo, FX; reverse traversal is symmetric. Current run/stop glyphs are white, pending launch/retrigger pink and blinking, with shapes as a second cue.

4T HOME uses four real pre-fader/pre-FX instrument traces and a final-mix trace. Knobs1–4 belong to tracks1–4; SEL, SELECT or ALGORITHM cycles Volume/Mute/Solo/FX only. Mini scopes indicate synthesis, not post-mute output; master scope is the audible mix. Scope snapshots remain frozen until all six strips have been sent. Existing single-instrument HOME/full-screen scope remains.

Global modifier shortcuts consume both releases: SEL+SEQ Song/4T, HOME+SEQ Mixer/4T, SEL+HOME4T/4V, ENV+HOME mono glide, LFO+HOME4V with glide off. HOME/ENV/LFO ordinary navigation occurs on release so a chord cannot trigger an unintended intermediate page. GLO legend now has an adjacent HOTKEYS page; INFO and RESET remain last. Song model and exact controls: SONG_MODE_DESIGN.md.

## 729 routing and control contract - 2026-10-14

SEL+FX saves the current chain as personal default, opens FX routing and consumes modifier release without paging. K3 reset uses the personal default. GLO's last RESET page separately restores ORIGINAL FX ROUTE, with confirmation and no bank erasure. Saved projects retain their own explicit order. Keep the routing footer within18 scale2 characters and show saving/success/failure. Existing CADER palette, compact header and exact values remain.

MIDI bank/program scope is visible in Help: DEFAULT/User, transport/channel isolation and zero-based wire numbers. Unsupported selections are inert, not placeholder functionality. Song/peer UI remains a draft and must not appear as functioning controls. [729 report](DEVELOPMENT_729.md).

## 727 owner-directed refinement - 2026-10-14

Named choices on hardware show musical names without wire enum codes. Numeric musical values and units remain visible; diagnostic/native values unchanged. HOME mirrors FX page1; VOICES is visibly locked in4TRK. SEL+HOME explicitly toggles mode, preserving the compact header. See DEVELOPMENT_727.md. This supersedes earlier hardware enum-number requirements.

## 726 release polish - 2026-10-13

Owner approved FMER separated from right-aligned FM/VA,1V..4V or4T, transport, USB/stream, clock and close-fitting percentage battery on one line.4px icon gaps; minimum8px brand separation at100%. HOME retains96px scope. No invented cable/headphone/Bluetooth detection. Global K1 exposes mode; INFO/RESET last. Companion CADER palette unchanged. [Details](DEVELOPMENT_726.md).

## 725 mode and companion contract - 2026-10-13

GLO/VOICE-TEMPO K1 is SINGLE0/4TRK1, K2 tempo, K3 voices and K4 transpose. The four-track total is explicitly one voice per track. A deliberate VOICES edit exits four-track allocation; clockwise at4 reaches four-note polyphony. Existing patterns/mix are retained; mode change stops playback. HOME SELECT remains FM/VA. Companion Sound repeats the same mode/value relationship and Undo boundary.

Embedded editing keeps one central FM-1 transfer workflow; diagnostics and bank resets sit in labeled disclosures. Exact values and CADER palette are unchanged. Portable app data stays outside the installation folder; Quit refuses active transfers and releases capture/server ownership. No hosted service or automatic device access is required.

## 724 live-key repair ? 2026-10-12

Selected muted track explained silent physical keys while another sequencer track remained audible. Implement stopped-transport audition without changing stored mute/solo, level, FX routing or Local Off; retain normal mixer behavior during playback/recording. Move estimated battery readout to top right. Exact diagnosis, contracts and qualification plan: [724 review](DEVELOPMENT_724.md). Target installation, preservation and timing are pending.

## 723 interaction refinement ? 2026-10-12

Mixer LEVEL is2% per slow detent, accelerating to4/6 during a sustained turn, with SEL fixed at1%. Reversal, track, mode or timeout breaks the speed run. Other layers stay discrete. GLO MIDI Output uses SEND / KEY CH / HEAR FMER / CH MODE; Clock uses TEMPO / SEND CLOCK / MIDI START / SEND KNOBS. Context explains the active routing; GLO pages and SEL saves. Every choice is checked against the224-pixel readable area. Header E64% explicitly means estimate; GLO Info spells this out. ARP gate pulse survives current-page selection; REC distinguishes count-in from capture; dim FX/LFO show enabled state; SAVE distinguishes navigation, edits, activity and result. No decorative key overlay obscures actual note pitches. See [723 review](DEVELOPMENT_723.md).

## 722 development checkpoint ? 2026-10-12 UTC

722 interaction: three FX pages retained. FX3 ALGORITHM chooses Free ms0 or seven musical divisions; K1 follows mode, free time is retained, actual milliseconds/MAX remain visible. PERFORM gains RUN (left stop/right next-bar launch); last touched strip is the selected track. SEL+PLAY resolves after300ms to selected-track next-bar launch; double within that window launches all. Recording refuses launches. ARP REC captures generated notes, count-in/Overdub/Replace retained. ARP/FX show mixer track/M/S/FX flags; page navigation preserves routing. GLO pages with GLO, never SEL. CADER palette and exact numeric controls remain.

## Companion product interface ? 2026-10-11

Six top-level destinations: Library, Sound banks, Editor, FM-1, Backups, Firmware. CADER dark palette retained. Library uses metadata, multiselection, Trash and Undo; Editor retains visual controls/exact values and one-gesture Undo. Separate PC banks from hardware destinations. Background operations expose progress and retained downloadable diagnostics. Help opens an offline-capable HTM index in a new tab. No MIDI access on load; exact write scopes and partial-write limitations shown before confirmation. See [design scope](COMPANION_PRODUCT.md).

## 721 final evidence -- 2026-10-11

Installed721 implements direct four-track PERFORM layers and NOTE/COPY editing. Full guide and actual raster preview are in artifacts/development-721. Physical readability and click/display alignment remain owner acceptance. See [721 review](../artifacts/development-721/review.html).

## 721 song workflow candidate -- 2026-10-11

721 candidate: dedicated four-strip PERFORM mixer, fixed track-to-knob mapping, labeled layer selector and explicit M/S/F states; no nested track selection for performance controls. FX and SEQ preserve playback. NOTE EDIT and COPY/EDIT extend the existing grid with logical held-note edits, bounded range operations and guarded undo. Four silent count-in beats precede one shared track downbeat. See artifacts/development-721/interface-guide.txt for the full mapping. Physical readability and optical/audio alignment remain unqualified until owner feedback.

# FMER interaction and appearance contract

<!-- FMER720-HANDOFF-BEGIN -->
## 720 release6 installed test prototype - 2026-10-11 UTC

The 720 workflow below is now installed on Test01 as release6. [Final connected evidence](../artifacts/development-720/report.json) supplements the separately scoped host panel, raster and companion checks. Connected workflow checks passed; physical display, count-in feel, listening and cold power-cycle acceptance remain open.

Complete native/project loading uses a guarded stopped-DMA main-loop transaction, retaining explicit STOP semantics and separately reporting intentional quiet time. This does not change immediate preset browsing. Keep project/pattern IDs zero-based and the SAVE scope value distinct from the destination; Project 0 is the restored owner arrangement.

[720 review and controls](../artifacts/development-720/review.html) | [Source-pinned evidence](../artifacts/development-720/report.json). Earlier dated entries retain their historical scope.

<!-- FMER720-HANDOFF-END -->

## 720 workflow refinement - 2026-10-11

PRESETS moves through one circular list: 32 FM sounds, 32 VA sounds, then 64
USER slots. Reverse travel follows the same list backward. Existing slot IDs
remain unchanged. K1 still jumps banks directly. Sound names and bank/slot
identity remain visible; browsing auditions immediately. Algorithm changes
belong to the current working FM sound, with the routing overlay identifying
that scope; SAVE makes the edited sound persistent.

Distinguish the SELECT rotary encoder from the SEL button in instructions.
PRESETS and SELECT both browse inside the sound browser; SEL returns HOME
without a second recall. Empty USER slots remain visibly empty and leave the
previous sound playing. The stable DEFAULT slot IDs are FM 0–7/16–39 and
VA 8–15/40–63; USER retains 0–63. Sequential browsing must cross those IDs and
bank boundaries without introducing a hidden load gesture.

GLO pages run in this order: Voice/Tempo, Mono Glide, MIDI Input, MIDI Output,
MIDI Clock, Info, Reset/Clear. Each heading names its purpose. Information and
destructive actions are last. Existing knob positions within musical groups
remain fixed. HOME shows the sound name and musical voice/algorithm status,
without engineering gain statistics in the performance overview.

Sixteen shared patterns use two rows of eight readable tiles. Pink outline is
the edit cursor, green top marker is the playing pattern, purple bottom marker
is queued, and green numbers denote enabled chain members. Both rows use actual
zero-based pattern IDs 0 through 15. The chain mask retains all sixteen bits.
REC offers Step entry (0), Live Overdub (1), and Live Replace (2). Overdub loops
until REC or STOP; Replace makes one pass. The four-beat lead-in replaces the
visual area on every sequencer page while leaving controls in their fixed
positions. Beat numbers and lit boxes use the audio owner's count and click
pulse. Armed external-clock wait must not invent the first audible beat.

SAVE has K1 Slot, K2 Bank (sounds only), K3 Save/Load, and K4 Sound/Project.
The destination scope and slot freeze on SEL confirmation. Sounds use two
independent 64-slot banks; projects use 16 separate destinations and retain the
working sound, sixteen patterns, track instrument references, mix and effects.
Track sound references require edited instruments to be saved to their assigned
slots. Clear Projects is separate from either sound-bank reset.

Show project and pattern destinations as their exact zero-based IDs 0–15 on
both interfaces: onboard PROJECT 0 equals companion Project 00. K4's
PROJECT 1 denotes scope 1, never a one-based project index. Track lanes may
use T1–T4 while the exact track control retains values 0–3. SAVE and explicit
Load stop playback; immediate preset browsing remains its separate live path.
New projects use Overdub; loading a saved project retains its recording mode.

The companion labels unit instruments and unit projects separately. Its PC
slots retain complete editable bundles for compatibility; project files can be
exported independently. Opening a unit instrument preserves the editor's
arrangement. Opening a project explicitly replaces that arrangement. Sending
the editor project and saving the current unit project are distinct actions,
with destination-specific confirmation. Selected-pattern audio preview remains
one pattern with the working sound, not four-track arrangement rendering.

Full-screen scope frames begin at the top and keep one accepted PCM generation
until complete. Pending full-screen rows use transport readiness without the
normal two-millisecond inter-row software delay. Each service still submits
at most one bounded rectangle and never rewrites an in-flight DMA buffer.
No new display buffer or guessed tearing-effect pin is introduced. These are
host-tested transfer properties; optical smoothness remains a device test.

## 719 workstation interaction contract - 2026-10-11 UTC

PRESETS rotation immediately auditions sound; K1 selects FM0/VA1/USER2 and SELECT/HOME returns without another recall. Audition preserves shared FX and arrangement state. Persistent Save and explicit full sound-plus-pattern restore still require a named destination and SELECT confirmation. No silent empty-USER substitution.

SEQ retains grid/pattern/chain pages1..3, then TRACKS4, MIXER5 and RECORD6. Track selection stays on K2 across TRACKS/MIXER; actual playing/queued patterns, bank references, step, level and mute drive lane visuals. Rest128 and Tie129 are distinct. Record feedback uses the audio-owner count-in, not a UI timer. GLO7 groups glide mode, time, contour and voice budget; exact values stay visible and time uses proportional adjustment. ARP says TYPE without changing its numeric meaning. [Exact knob map](../artifacts/development-719/interface-guide.txt).

MODE stays on K4 on both TRACKS and MIXER. SINGLE explicitly labels the mixer inactive, locks its K1 level/K2 track/K3 mute controls and replaces dormant lane activity with activation instructions. Viewing a page is passive. An explicit switch to 4TRK stops playback and opens the selected track's actual saved pattern; PLAY starts all four tracks. This follows the owner's719 mixer test: controls must not appear to change the sound while bypassed by another mode.

Use CADER colors and real sliders/selectors in the companion. Sound editing adds mono glide; pattern editing exposes four references/mixer settings over eight shared patterns. A gesture remains one Undo. Importing FX preserves all track/glide/pattern state. Label selected-pattern audition accurately rather than implying full arrangement playback. Keep the battery status B-- while percent is uncalibrated. Scope changed-pixel transfers preserve snapshot coherence; optical smoothness is a separate physical acceptance gate.

## 718 tiny-screen controls — 2026-10-10 UTC

Retain CADER colors, exact numeric values and four horizontal sliders below the live visual. FX uses rows2..4 for final-output scope, row5 for actual stage activity, rows6..9 for controls; edit focus never replaces the graph. ENV uses rows2..4 for a schematic shape, row5 for units/group context and rows6..9 for knobs. FM: native carrier attack rate, decay rate, sustain level, release rate;99is fastest for rates. VA: ADSR time/level. FM EDIT contains operator rates/levels and pitch rates/levels. Full-screen HOME remains a reversible repeated-HOME gesture; snapshot generation stays fixed until every visible row finishes.


## 717 reactive visual contract — 2026-10-10 UTC

HOME normally keeps the four canonical knob values readable under a96px scope (small bottom status overlay). HOME again hides text and controls for a240px-high scope; HOME or another panel button restores normal rendering and carries out that button's usual action. Encoder movement also returns to controls. Musical keys continue to play without leaving scope view. Fault status overrides the visualizer.

FX row shows FL/RV/DL/DR/CH/PH activity dots from actual stage signal differences, including delay/reverb tails. Disabled stages clear; dots decay when quiet. Log-compressed approximate peak display is explanatory, not a numeric feedback meter. Keep existing palette, parameter positions and exact displayed values. Preview: `../artifacts/development-717/ui/review.png`. Four-track concept is explicitly separate from implemented UI.


## 715 branding and sound feedback - 2026-10-09 UTC

Use the owner-provided native v240x240 splash for boot and original segmented FMER wordmark for the header. Keep parameter text readable. Algorithm changes show routing with human 1..32 and exact raw 0..31, green carriers, purple modulators and pink effective feedback. The companion uses the same generated routing. Known missing feedback is marked. Preserve CADER dark palette and visual controls with real numeric values. [715 review and listening links](../artifacts/development-715/review.html).

## Companion bank workflow, 2026-10-07

The companion implements two visually distinct editable banks with the same CADER palette. The destination bank and slot stay visible while editing. Search, engine/category filters and Favorites organize the catalog. User slots are engine-neutral. Separate **Reset to FMER Default**, **Reset User Bank** and **Clear User Bank** actions name their affected bank before confirmation; no reset crosses into the other bank. Bank Undo, explicit Save and a retained previous file provide recovery from ordinary catalog edits.

Expose canonical values beside sliders/selectors. Frequency travel is logarithmic; zero-inclusive VA envelope time travel is quadratic. A gesture is one Undo action, including exact native identity restoration. Metadata-only edits do not mark sound bytes as a custom patch. Separate Sound, FM operators, Pitch & LFO, Effects, Arp & performance and Patterns views keep the home editor manageable. The eight-bank pattern view distinguishes the edit cursor, active length and retained hidden steps. Save/import/render actions temporarily disable the editor so a late response cannot discard a newer gesture.

Working and saved auditions are explicit comparisons, labeled with the captured instrument name. The preview uses current native values; its plot is a peak envelope. Host-only limitations and device reconciliation are visible in the appropriate workflow. The app adds catalog capacity and backup convenience while the next device storage iteration must retain independent on-unit Save/reset operations. [Exact contract and remaining firmware work](COMPANION_BANKS.md).

Adopted: 2026-10-05. The owner requested visual controls in place of mandatory
number typing, with the real numeric values always visible, and CADER's dark
theme. This is the design contract for the web companion and later instrument
pages. The [test report](../TEST_REPORT.md) records which implementations have
actually passed; requirements below do not imply hardware qualification.

## Manipulate the sound visually; retain the exact value

A musical parameter should be understandable and adjustable without typing a
number. Its label, current value and unit remain visible together. A numeric
entry remains available for precision, but is not the only way to adjust an
ordinary sound or performance setting. Saved values and renderer requests use
the validated canonical values, never a rounded display string.

| Parameter kind | Preferred control | Value presentation |
| --- | --- | --- |
| Level, mix, depth, velocity, gate, swing and other bounded amounts | Slider with a visible extent and thumb | Exact value and its actual unit; show a percentage only when the underlying parameter is a percentage |
| Cutoff frequency across a wide positive range | Logarithmic slider | Exact Hz beside the control; logarithmic position is presentation only |
| Tempo, duration, pattern length and bounded counts | Stepped slider with optional exact entry | BPM, seconds or count, with the valid range discoverable |
| Enable, sync, latch and other binary state | Labeled switch or checkbox | State word and numeric value when the data represents the setting as 0/1 |
| Oscillator mode, waveform, scaling curve, arp order/rate and other small enumerations | Labeled choices or a select | Meaningful name and the stored numeric code when one exists |
| Note or pitch | Labeled keys, note selector or pitch slider | Note name plus MIDI number; explicitly retain the numeric octave convention |
| Algorithm | Discrete selector now; algorithm diagram when backed by the same routing definition as DSP | Algorithm name/index and exact stored code if its numbering differs |
| Pattern steps and chords | Step grid and note toggles/keys, with per-note velocity controls | Each retained pitch/velocity remains inspectable; rests and ties have distinct labels/shapes |
| Slot, bank and destination | Named selection with a visible destination | Slot/bank number is retained as identity, not disguised as a continuous sound parameter |

Sliders are the first web implementation. A knob is useful only if it provides
equally clear bounds, direction, keyboard operation, touch handling and value
readout. Decorative knobs do not justify making editing less accessible.

For a frequency range `[minimum, maximum]`, normalized slider position `p`
maps to `minimum * (maximum / minimum)^p`. Clamp and quantize the result to the
parameter's actual supported step, then display and persist that value. Loading
an exact existing value must not quantize it simply to position the slider.
Test the bounds, monotonic movement, useful low-frequency resolution and
round-trip preservation. Do not apply logarithmic scaling to a range containing
zero or negative values without an explicit parameter-specific mapping.

One parameter has one canonical value. Its visual control, exact entry,
imported patch, preset/session restoration, Undo and A/B must agree immediately.
Changing display units or the theme must not change the sound or persisted
bytes. A UI must identify unsupported/inactive settings rather than appearing
to change an engine that ignores them. The [codec registry](CODEC.md) remains
the source of FM parameter IDs and bounds.

## Input, reversibility and diagnostics

- Native keyboard semantics remain available: Tab reaches the control, arrows
  adjust a slider, Home/End reach its bounds, and Space changes a toggle.
  Labels and accessible value text identify units and named enum states.
- Pointer and touch controls have a usable hit region. A larger touch target
  may surround a compact visual thumb; do not force precise thumb aiming.
- Wheel scrolling does not silently change a value or selected option. Keep
  normal page scrolling available instead of intercepting every wheel event.
- One continuous pointer gesture creates one Undo boundary. Live value updates
  within the gesture remain visible. Releasing/canceling it or moving focus
  cannot leave a transaction open. Discrete key changes have explicit Undo
  boundaries; keyboard auto-repeat must not corrupt the starting state.
- Exact-entry errors show the allowed range and preserve prior valid state.
  Do not silently accept `NaN`, an invalid enum, or a truncated import. Save
  continues to identify its destination and preserve existing data on refusal.
- Diagnostics should retain committed parameter ID/value changes, source of
  the action, refusals and request correlation. Avoid thousands of drag-event
  log rows; summarize a gesture outside the audio path. Logs supplement
  immediate visible feedback and must not turn a completed Save into a failure.

The browser companion remains the primary development interface. It edits the
same musical data used by the shared core; it is not a separate synth or an
implied FM-1 transport. See [the library format](LIBRARY.md) and
[sandbox behavior](SANDBOX.md) for current persistence and rendering scope.

## CADER dark palette and visual language

The authoritative reference is the owner's local CADER workspace, inspected
read-only on 2026-10-05. The private machine path is omitted from distributable
documentation. CADER was located through CyberPacker's retained
`docs/reviews/ribbon-identity-2026-09-06/cader-source.json` provenance record;
its palette snapshot hash matches the live source. No CADER scripts, artwork
or fonts are copied or required at runtime.

| CADER token | Value | FMER use |
| --- | --- | --- |
| `background` | `#070709` | Application canvas and solid shell |
| `panel` | `#101014` | Main working sections |
| `panel_alt` | `#1b1b23` | Secondary surfaces and controls |
| `field` | `#09090d` | Exact entry, logs and recessed fields |
| `hover` | `#30313a` | Pointer hover surface |
| `border` | `#727684` | Meaningful control outline |
| `axis` | `#4b4e5a` | Decorative dividers, not essential control outlines |
| `grid` | `#202127` | Subdued contextual grid |
| `text` | `#f5f7fa` | Main labels and values |
| `muted` | `#b6bbc6` | Secondary explanatory text |
| `disabled` | `#9398a5` | Explicitly disabled state |
| `accent` | `#76ff53` | Primary action and active musical state |
| `accent_text` | `#070709` | Text on green fill |
| `construction` | `#c9a0ff` | Reference/comparison information |
| `dimension` / `preview` | `#ff78d4` | Distinct keyboard focus and edit annotation |
| `selection` | `#ffffff` | A selected cue where separate from active state |

Use solid near-black surfaces, compact rectangular groups and clearly marked
edges. Controls and panels use CADER's 3 px corners; selected/menu details may
use its 2 px treatment. Avoid decorative gradients, glass blur and oversized
rounded cards. CADER's main theme uses 14 px default text, 8 px group spacing,
14/12 px horizontal/vertical outer margins and 8/6 px inner control padding.
The web adaptation uses local system sans-serif text and tabular numeric
readouts; no particular proprietary font is a dependency. These dimensions
are layout starting points, not reasons to clip text at a different scale.

Green denotes action/active state, purple reference state and pink focus.
An active control also has a marked edge, label or shape, so color is not its
only signal. Pressed primary buttons use green fill with near-black text.
Focus remains a separate pink outline. Warning/error hues, if needed, are
explicit FMER extensions with words/symbols, not borrowed meanings for purple.

CADER's design targets are at least 4.5:1 for readable text and 3:1 for essential
graphical cues against adjacent backgrounds, calculated before rounding.
Verify actual FMER pairings and interaction states; copying tokens alone does
not establish contrast or complete accessibility. Preserve focus and control
boundaries under forced colors and reduced motion. Review narrow layouts and
zoom without document-wide horizontal overflow or obscured primary actions.

### Inspected source identity

Paths below are relative to the CADER workspace. They are provenance references,
not FMER build dependencies or live links required by the documentation checks.

| Source | Inspected content | SHA-256 |
| --- | --- | --- |
| `prototype/scripts/ui/cad_palette.gd` | Lines 5-13: exact light/dark palette; lines 1-4: contrast intent | `429650d3689acadf5797f827ae982ae07cd9bc290e5c407ce4b8d1e2c99ddb9f` |
| `prototype/scripts/ui/main.gd` | Lines 140-203: font size, state colors, corner radii, active edge, focus and spacing; lines 253-264: inner padding and border width | `0e6bd51f8105ec656eef564595624ed66ef84ece16be27426ee216f775c02c90` |
| `docs/VISIBILITY_AND_PRODUCTIVITY_V0.2.md` | Lines 14-56: semantic palette, shape cues, solid backing and contrast targets | `36f3c8efe0d45c0ef0b8c064c796a3ff372ceda42cd89f2cfdf10a5ef5909793` |
| `docs/ICON_UI_V0.3.2.md` | Lines 7-13: compact labeled controls, contrasting pressed state, pink focus, marked active edge and scale qualifications | `3f34e9bc4e4d32b6fd234a7b845012905c8af1096edcda92cf9f8ef3bb29a1af` |

## Tiny-screen and hardware adaptation

2026-10-06 refinement: the owner confirmed that 702 stopped flickering but
its text was too small or crowded. Firmware 703 therefore gives an edited
control its own page. Primary names and values use 21-pixel-tall glyphs;
supporting text uses 14-pixel glyphs with one line in each 24-pixel strip.
Turning a control opens its value and range bar. HOME returns to the sound
overview; engineering counters live on the diagnostics page. No tiny secondary
text is permitted in the normal interface. The CADER palette and canonical
numeric values remain the same. Host fit/DMA tests support this design;
physical readability still needs the owner's evaluation.

The future FM-1 skin uses these semantic roles and the shared parameter model,
not a scaled-down browser page. Keep parameter ID, label, units, range, exact
value, availability and edit transactions independent of the browser widgets.
A hardware encoder can edit the same parameter that a web slider edits.

Design device pages around the measured screen/controller and actual encoder
navigation. Show the selected parameter/value, focused operator or step, edit
state and an unambiguous return/Stop gesture. A compact meter or arc may convey
range while the number remains legible. Do not assume an unverified framebuffer,
touch panel, display driver, memory budget or firmware transfer capability.
The [architecture](ARCHITECTURE.md) and [recovery gate](RECOVERY.md) govern target
implementation independently of appearance work.

## Verification contract

Regression coverage should prove visual input changes the real request value,
not just its label. Check slider/entry synchronization, logarithmic frequency,
discrete choices, toggle codes, exact imported values, one-gesture Undo,
restore/A-B state, wheel protection, keyboard editing, and viewport reachability.
Retain source/build identity, browser errors, screenshots, action logs and the
request/render artifacts. Include a real render after editing, with tests using
an isolated companion library. Existing user slots must remain untouched.

Screenshot inspection and automated contrast/layout checks complement the
behavior checks. Physical touch, screen-reader use, device display readability
and hardware encoder feel retain their own qualification; a host browser pass
cannot certify those conditions.


## 706 panel lighting contract

Keep CADER's dark screen and the canonical numeric values; physical emitters
use their actual hardware colors and on/dim drive. Every light communicates a
current condition. The active page stays visible; disabled ARP is dim when
selected, enabled ARP indicates gate activity when another page is selected.
Octave buttons show the sign of the current offset, with its exact value on
screen. Keys acknowledge contact and actual MIDI/generated voice ownership:
gates bright, release tails dim, finished/stolen voices absent. Arp chord holds
stay dim so generated gates stand out. Off-screen pitches are not folded onto
incorrect keys. Keys keep note meanings on SEQ; there is no hidden step overlay.

Green PLAY communicates running sequence/quarter beat, and REC communicates
armed step entry. SEL lights while fine adjustment is held. SAVE has dim press
feedback only, since native persistence is unavailable. Panic clears sounding
activity; still-held physical contacts remain honest contact indicators.
Ordinary PLAY can signal protective pause/failure. No decorative idle heartbeat
or blanket backlight is added. Main-loop readback and logging preserve commanded
states; optical brightness/color remain a separate owner acceptance question.


## 709 standalone bank controls — 2026-10-08 UTC

SAVE has K1 slot and K2 USER/DEFAULT bank with named destination and deliberate SEL confirmation. GLO/BANK RESET separates Reset to FMER Default, Reset User Bank and Clear User Bank, using arm/confirm with navigation cancel. Default recall includes its stored sound effects while retaining performance and patterns. Companion device actions are grouped separately from PC library actions; each shows destination, confirmation, result and logs. No automatic bank replacement occurs on connection. CADER colors, exact numeric values and visual controls remain unchanged.

[709 guide](FM1_709.md) contains current scope and evidence.
