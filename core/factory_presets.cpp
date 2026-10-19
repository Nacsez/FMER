#include "factory_presets.hpp"

namespace fmer {
namespace {
constexpr const char* names[factory_preset_count] = {
    "FM KEYS", "FM BELL", "FM BASS", "FM BRASS",
    "FM ORGAN", "FM PLUCK", "FM REED", "FM MOTION",
    "VA ROUND", "VA SAW", "VA PULSE", "VA TRI",
    "VA BASS", "VA PLUCK", "VA SOFT", "VA VIBRA",
    "FM TINE", "FM REEDKEY", "FM CLAV", "FM KICK",
    "FM VIBES", "FM SNARE", "FM JINGLE", "FM HAT",
    "FM ARCADE", "FM PICKBS", "FM SUBBASS", "FM SLAP",
    "FM TRUMPET", "FM SQUELCH", "FM BRSTAB", "FM FLUTE",
    "FM LOGDRUM", "FM STRINGS", "FM TOM", "FM CHOIR",
    "FM WARMPAD", "FM GLASS", "FM LEAD", "FM PERC",
    "VA SUB", "VA ACID", "VA KICK", "VA SNARE",
    "VA HAT", "VA TOM", "VA LEAD", "VA HOLLOW",
    "VA REED", "VA FLUTE", "VA BRIGHT", "VA SING",
    "VA WARM", "VA STRINGS", "VA SWELL", "VA SHIMMER",
    "VA CLAP", "VA MALLET", "VA ORGAN", "VA BRASS",
    "VA SOFTKEY", "VA CYMBAL", "VA ARP", "VA LONG"
};

struct FmRecipe {
    unsigned char algorithm, feedback;
    unsigned char levels[6], ratios[6]; // VCED order OP6..OP1
    unsigned char attack, decay, sustain, release;
};

// 709.1 articulation: independent brightness envelopes, velocity-to-timbre,
// and high-key damping. All recipes are authored here; no vendor patch data.
// Values are DX7 rates (larger = faster), not milliseconds.
struct Articulation { unsigned char decay, body, velocity, damping, fine; };
constexpr Articulation articulation[32] = {
    {58,62,4,22,0}, {51, 0,4,30,41}, {73,55,5,18,0}, {66,75,5,18,0},
    {99,99,0,10,0}, {78, 0,5,32,0}, {72,64,5,18,0}, {40,82,3,18,0},
    {70,26,6,30,7}, {58,54,5,22,0}, {84, 0,6,35,0}, {69, 0,5,32,18},
    {55, 0,4,26,1}, {82, 0,5,38,0}, {47, 0,4,35,37}, {65, 0,5,32,21},
    {66,45,4,20,0}, {78,34,5,27,0}, {71,65,3,12,0}, {88,15,6,32,0},
    {75,74,6,21,0}, {63,66,5,23,0}, {71,72,5,20,0}, {64,52,5,27,0},
    {73,64,5,20,0}, {52,81,4,20,0}, {63,73,5,21,0}, {52,70,4,22,0},
    {37,83,3,24,0}, {50,56,4,30,12}, {76,64,6,18,0}, {94, 0,6,38,27}
};

// Carrier masks for the algorithms used below, in VCED OP6..OP1 order.
// Derived from the pinned MSFA routing table's output-bus-add flags.
constexpr unsigned carrier_mask(unsigned algorithm) noexcept {
    constexpr unsigned char masks[32]={
        0x28,0x28,0x24,0x24,0x2a,0x2a,0x28,0x28,
        0x28,0x24,0x24,0x28,0x28,0x28,0x28,0x20,
        0x20,0x20,0x26,0x34,0x36,0x2e,0x36,0x3e,
        0x3e,0x34,0x34,0x29,0x3a,0x39,0x3e,0x3f};
    return masks[algorithm & 31];
}

// Hand-authored sound-design starting points. In particular, the first sound
// uses three audible modulator/carrier pairs, so an algorithm edit has useful
// audible material to reroute. FMER INIT remains the codec's neutral sine test.
constexpr FmRecipe fm_recipes[factory_fm_preset_count] = {
    {4, 0, {74,78,63,76,48,81}, {3,1,2,1,1,1}, 99,45,60,64},
    {4, 0, {77,75,67,72,60,80}, {7,1,3,2,2,1}, 99,34, 0,46},
    {0, 2, {45,54,60,74,64,88}, {3,1,1,1,1,1}, 99,60,64,82},
    {6, 4, {62,63,63,80,72,86}, {2,1,3,1,1,1}, 92,55,84,72},
    {31,0, {57,61,66,69,73,80}, {8,6,4,3,2,1}, 99,99,99,82},
    {2, 1, {62,67,82,56,63,83}, {4,2,1,3,1,1}, 99,66, 0,85},
    {11,3, {49,51,64,76,63,85}, {5,3,2,1,2,1}, 94,59,78,72},
    {20,1, {64,72,76,65,76,79}, {3,1,2,2,1,1}, 67,40,86,56},
    // Keys: bright tine, warm reed, short clav and small metallic keyboard.
    {4, 0, {73,80,60,75,40,82}, {14,1,3,1,1,1}, 99,42,51,65},
    {4, 1, {59,78,58,74,36,82}, {2,1,1,1,1,1}, 98,42,64,67},
    {0, 3, {50,62,66,76,73,86}, {5,3,1,1,2,1}, 99,71, 0,89},
    {4, 0, {56,42,66,70,20,93}, {1,1,1,1,1,1}, 99,66, 0,84},
    // Tuned percussion: longer mallets through bright inharmonic chimes.
    {4, 0, {48,79,51,76,36,83}, {4,1,3,1,2,1}, 99,34, 0,50},
    {4, 7, {87,78,54,74,42,69}, {1,1,1,1,1,1}, 99,72, 0,87},
    {4, 1, {76,75,75,76,72,73}, {11,2,7,1,5,3}, 99,34, 0,46},
    {4, 7, {81,69,76,68,80,67}, {1,1,1,1,1,1}, 99,84, 0,95},
    // Basses: mellow finger, bright pick, sine-rich sub and percussive slap.
    {0, 3, {46,62,72,80,71,90}, {4,2,1,1,1,1}, 99,66,49,86},
    {0, 3, {45,56,63,77,64,88}, {4,2,1,1,1,1}, 99,63,57,87},
    {4, 0, {14,67,10,69,12,89}, {1,1,1,1,1,1}, 96,60,85,83},
    {0, 4, {58,70,77,80,77,90}, {7,3,1,1,1,1}, 99,76,37,90},
    // Winds/brass have slower fronts and sustained harmonic bodies.
    {6, 4, {54,65,68,80,74,87}, {3,1,2,1,1,1}, 96,56,86,76},
    {17,5, {49,59,72,77,79,93}, {2,1,3,1,1,1}, 99,63,68,82},
    {11,4, {57,63,67,79,71,87}, {3,2,1,1,1,1}, 98,65,61,85},
    {4, 0, {28,65,32,68,17,85}, {3,2,2,1,1,1}, 89,54,85,73},
    {4, 1, {52,76,57,72,21,87}, {2,1,3,1,1,1}, 99,68, 0,88},
    // Strings and pads use small opposing detunes below; not extra voices.
    {20,2, {49,73,75,51,76,80}, {2,1,1,3,1,1}, 72,44,87,61},
    {4, 2, {55,73,49,73,20,90}, {2,1,3,1,1,1}, 99,62, 0,84},
    {4, 0, {57,77,51,77,48,80}, {3,1,5,2,2,1}, 74,43,85,58},
    {20,0, {38,67,70,40,71,76}, {2,1,1,3,1,1}, 59,34,92,51},
    {4, 0, {69,71,63,73,55,77}, {7,1,5,2,3,1}, 71,38,76,54},
    {17,4, {45,55,62,69,74,94}, {3,2,1,2,1,1}, 99,60,79,82},
    {2, 5, {64,68,76,48,66,88}, {11,3,1,7,2,1}, 99,80, 0,93}
};

using Wave = VaWaveform;
// One oscillator/filter/envelope per voice. These recipes deliberately avoid
// names suggesting unavailable PWM, unison, noise or filter-envelope behavior.
//719: contrast in transient length, resonant colour and playable release.
//Sub and pure mallet voices remain restrained; richness is not a synonym for
//high cutoff. No PWM, sync, unison or filter envelope is implied by these data.
//Rounded values match the target's integer controls exactly.
constexpr VaParameters va_recipes[factory_va_preset_count] = {
    {Wave::sine,    12000,0,     3,1105,.25f,416,5,0},
    {Wave::saw,      9200,.12f,  3,210,.86f,140,5,0},
    {Wave::square,   4400,.18f,  3,135,.62f,100,5,0},
    {Wave::triangle,10500,.02f, 10,884,.30f,403,5,0},
    {Wave::saw,       740,.42f,  2,235,.52f, 76,5,0},
    {Wave::square,   5200,.31f,  1,225,0,    65,5,0},
    {Wave::saw,      1900,.09f,430,975,.75f,1430,3.7f,3},
    {Wave::triangle, 6720,.08f, 58,224,.84f,336,6.5f,18},
    {Wave::sine,      336,0,     4,288,.92f, 72,5,0},
    {Wave::saw,      1350,.82f,  1,190,.28f, 63,5,0},
    {Wave::triangle, 1300,.11f,  4,390,.76f,148,5,0},
    {Wave::square,   1050,.35f,  2,180,.50f, 72,5,0},
    {Wave::saw,      3900,.44f,  1,145,.10f, 52,5,0},
    {Wave::square,    294,.08f, 10,494,.84f,195,5,0},
    {Wave::saw,      8400,.26f,  4,170,.90f,115,6.1f,9},
    {Wave::square,   1700,.14f, 12,355,.58f,230,3.8f,3},
    {Wave::square,   3250,.47f, 19,240,.82f,175,6.2f,12},
    {Wave::sine,     7400,0,    98,494,.86f,442,4.4f,13},
    {Wave::saw,     15600,.10f,  2,140,.90f, 96,5,0},
    {Wave::triangle, 4900,.24f, 62,410,.84f,470,6.8f,20},
    {Wave::saw,      1250,.08f,360,1040,.78f,1540,2.5f,3},
    {Wave::saw,      5700,.15f,165,540,.82f,1150,5.5f,7},
    {Wave::square,   1480,.21f,1160,1105,.72f,2450,1.9f,3},
    {Wave::triangle, 9880,.11f,465,560,.80f,1160,7.3f,18},
    {Wave::saw,      8100,.17f,  1,155,0,    59,5,0},
    {Wave::sine,    10500,0,     2,468,0,   182,5,0},
    {Wave::square,   6650,.04f,  3, 35,.94f, 48,5,0},
    {Wave::saw,      4850,.35f, 38,250,.84f,225,5,0},
    {Wave::triangle, 2450,.08f, 12,1100,.08f,740,5,0},
    {Wave::square,   9400,.29f,  1,170,.02f, 55,5,0},
    {Wave::saw,      5300,.48f,  2,190,.05f, 78,5,0},
    {Wave::sine,     5800,.02f,270,975,.86f,3380,1.4f,10}
};

void set_name(Patch& patch, const char* name) noexcept {
    bool end = false;
    for (std::size_t i = 0; i < 10; ++i) {
        if (!end && name[i] == '\0') end = true;
        patch.vced[145+i] = end ? static_cast<unsigned char>(' ') :
            static_cast<unsigned char>(name[i]);
    }
}

//716: DX envelopes and output levels are logarithmic, not percentages.
// Keep brightness sustain near the peak and set the desired modulation index
// with output level. The former low values in BOTH places removed sidebands.
// Each branch below has an explicit musical role; successful715 voices and VA
// are left byte-identical. Original recipes, no imported commercial patches.
void refine_fm(unsigned bank, Patch& p) noexcept {
    auto pair=[&](unsigned n,unsigned mod,unsigned car,unsigned ratio,
                  unsigned body,unsigned decay,unsigned sustain,unsigned attack=99) {
        auto* m=p.vced.data()+42*n;auto* c=m+21;
        for(unsigned j=0;j<2;++j){auto*v=m+21*j;
            v[0]=attack;v[1]=decay;v[2]=48;v[3]=76;
            v[4]=99;v[5]=j?sustain:body;v[6]=j?sustain:body;v[7]=0;
            v[8]=48;v[9]=0;v[10]=j?0:12;v[11]=0;v[12]=1;
            v[13]=1;v[14]=1;v[15]=j?2:2;v[17]=0;v[19]=0;v[20]=7;
        }
        m[16]=mod;m[18]=ratio;c[16]=car;c[18]=1;
    };
    auto three=[&](unsigned a,unsigned b,unsigned c,unsigned sustain,unsigned attack=99){
        p.vced[134]=4;p.vced[135]=0;
        pair(0,a,73,1,94,58,sustain,attack);
        pair(1,b,73,2,92,62,sustain,attack);
        pair(2,c,82,1,90,66,sustain,attack);
    };
    switch(bank){
    case 0: // woody FM piano: fundamental body + third/fourteenth partial attacks
        three(82,76,66,62);p.vced[18]=3;p.vced[60]=14;
        p.vced[5]=p.vced[6]=82;p.vced[47]=p.vced[48]=73;break;
    case 2: case 16: case 17: case 19: { // separate arcade bark/pick/slap roles
        three(bank==19?94:bank==16?91:86,bank==17?88:80,66,bank==19?64:76);
        p.vced[135]=bank==16?5:3;p.vced[18]=bank==19?7:bank==17?4:1;
        p.vced[60]=bank==19?3:2;
        p.vced[1]=bank==19?76:bank==16?66:60;
        p.vced[5]=p.vced[6]=bank==19?83:bank==16?90:87;
        p.vced[43]=70;p.vced[47]=p.vced[48]=84;
        p.vced[16+84]=58; // firm, nearly sine fundamental under the transient
        if(bank==16){ // four-operator stack plus a fundamental pair: arcade bark
            p.vced[134]=0;
            const unsigned char levels[6]={87,89,95,88,0,72};
            const unsigned char ratios[6]={1,1,1,1,1,1};
            for(unsigned op=0;op<6;++op){auto*v=p.vced.data()+21*op;
                const bool carrier=op==3||op==5;
                v[16]=levels[op];v[18]=ratios[op];v[0]=99;v[1]=carrier?56:50;
                v[5]=v[6]=carrier?88:86;v[15]=carrier?2:3;v[20]=7;
                v[10]=0;v[13]=0;
            }
            p.vced[135]=6;
            // Main stack carries the bark; the quiet pure fundamental adds weight.
            // Slight pitch snap is independent of the rapid index decay.
            p.vced[126]=99;p.vced[127]=85;p.vced[128]=75;p.vced[129]=80;
            p.vced[130]=52;p.vced[131]=p.vced[132]=p.vced[133]=50;
        }
        break;}
    case 3: case 20: case 22: // brass: sustained harmonic body, short brighter front
        three(bank==20?88:85,bank==22?83:78,79,88,bank==22?99:90);
        p.vced[135]=4;p.vced[60]=1;
        for(unsigned n=0;n<3;++n){auto*v=p.vced.data()+42*n;v[0]=bank==22?95:79;v[1]=58;v[5]=v[6]=93;v[15]=3;}
        p.vced[20]=6;p.vced[104]=8;
        if(bank==20){ // brief inharmonic lip transient, then the two harmonic pairs
            p.vced[18]=3;p.vced[19]=41;p.vced[16]=84;p.vced[37]=64;
            p.vced[1]=p.vced[22]=72;p.vced[2]=p.vced[23]=69;
            p.vced[5]=p.vced[26]=75;p.vced[6]=p.vced[27]=0;
            p.vced[15]=4;
        }
        if(bank==22)for(unsigned op=1;op<6;op+=2){auto*v=p.vced.data()+21*op;v[1]=56;v[5]=84;v[2]=48;v[6]=0;}
        //717 lip-pressure overshoot: a fast high-index squawk followed by
        // the716 harmonic body. Carrier level stays controlled independently.
        for(unsigned op:{2u,4u}){auto*v=p.vced.data()+21*op;
            v[0]=96;v[1]=72;v[16]=op==2?91:87;v[5]=v[6]=op==2?88:89;}
        p.vced[126]=99;p.vced[127]=78;p.vced[128]=65;p.vced[129]=78;
        p.vced[130]=53;p.vced[131]=p.vced[132]=p.vced[133]=50;
        break;
    case 5: // plucked string, bright attack retaining a softer resonant body
        three(88,81,70,0);p.vced[18]=3;p.vced[60]=2;
        for(unsigned op=0;op<6;++op){auto*v=p.vced.data()+21*op;v[1]=op%2?49:66;v[2]=46;v[5]=op%2?76:86;v[6]=0;}break;
    case 6: // reed: odd harmonics from 2:1, separate nasal 3:1 contribution
        three(84,77,70,87,92);p.vced[18]=2;p.vced[60]=3;p.vced[102]=2;break;
    case 9: // reed keyboard: driven low harmonics, softer than metallic tine
        three(82,75,67,70);p.vced[135]=3;p.vced[18]=1;
        p.vced[5]=p.vced[6]=87;break;
    case 11: { //726 kick: 55 Hz body, short100 Hz punch and noisy beater.
        p.vced[134]=4;p.vced[135]=7;
        const unsigned levels[6]={99,49,65,66,0,86};
        const unsigned freq[6]={280,310,230,200,174,174};
        for(unsigned op=0;op<6;++op){auto*v=p.vced.data()+21*op;
            v[0]=99;v[1]=op<2?79:op<4?67:52;v[2]=op<2?74:op<4?65:49;v[3]=72;
            v[4]=99;v[5]=op%2?82:99;v[6]=op%2?0:99;v[7]=0;
            v[8]=48;v[9]=v[10]=v[13]=v[14]=0;v[15]=op%2?2:0;
            v[16]=levels[op];v[17]=1;v[18]=freq[op]/100;v[19]=freq[op]%100;v[20]=7;
        }
        for(unsigned i=0;i<4;++i){p.vced[126+i]=80;p.vced[130+i]=50;}
        break;}
    case 13: { // snare: chaotic feedback wire burst plus a pitched skin/body
        p.vced[135]=7;p.vced[16]=99;p.vced[37]=82;
        p.vced[18]=2;p.vced[19]=80; // feedback source631Hz
        p.vced[39]=3;p.vced[40]=41; // inharmonic2570Hz wire carrier
        // Hold noise excitation while the *carrier* shapes its decay: reducing
        // both envelopes turns the last part back into a ringing pure tone.
        p.vced[1]=48;p.vced[2]=61;p.vced[5]=99;p.vced[6]=99;p.vced[15]=0;
        p.vced[22]=54;p.vced[23]=58;p.vced[26]=83;p.vced[27]=0;
        p.vced[58]=82;p.vced[79]=65;p.vced[100]=60;p.vced[121]=70;
        p.vced[60]=2;p.vced[61]=43;p.vced[81]=2;p.vced[82]=25;
        break;}
    case 21: // squelch: overmodulated attack that sweeps into a buzzy sustain
        three(96,90,79,84);p.vced[135]=5;p.vced[18]=1;p.vced[60]=3;
        p.vced[1]=62;p.vced[5]=p.vced[6]=88;p.vced[43]=67;
        p.vced[47]=p.vced[48]=85;
        p.vced[134]=17;
        {const unsigned char levels[6]={67,78,86,82,83,89};
         for(unsigned op=0;op<6;++op){auto*v=p.vced.data()+21*op;v[16]=levels[op];v[5]=v[6]=op==5?88:90;}}
        break;
    case 23: //718 pan-flute: audible aperiodic chiff separated from tube tone.
        three(99,65,70,94,90);p.vced[135]=7;
        // Fixed, inharmonic feedback pair: excitation stays high while the
        // carrier controls the breath decay. Avoid attenuating both at once.
        p.vced[17]=1;p.vced[18]=2;p.vced[19]=97;p.vced[15]=0;
        p.vced[5]=p.vced[6]=99;p.vced[10]=0;p.vced[13]=0;
        p.vced[38]=1;p.vced[39]=3;p.vced[40]=31;p.vced[37]=74;
        p.vced[21]=99;p.vced[22]=66;p.vced[23]=61;
        p.vced[26]=88;p.vced[27]=0;p.vced[34]=0;p.vced[36]=2;
        // Quiet second harmonic and strong fundamental, modest index.
        p.vced[60]=1;p.vced[81]=2;p.vced[79]=59;
        p.vced[121]=87;p.vced[84]=90;p.vced[89]=p.vced[90]=87;
        p.vced[137]=30;p.vced[138]=48;p.vced[139]=2;p.vced[140]=1;
        p.vced[126]=99;p.vced[127]=84;p.vced[128]=70;p.vced[129]=78;
        p.vced[130]=52;p.vced[131]=p.vced[132]=p.vced[133]=50;
        break;
    case 25: // bowed ensemble: slow spectral bloom and opposing fine detune
        three(85,81,76,90,73);p.vced[135]=3;p.vced[60]=1;
        p.vced[20]=5;p.vced[104]=9;break;
    case 27: // vowel-like spectrum: three independently voiced harmonic bands
        three(85,83,77,88,78);p.vced[18]=2;p.vced[39]=3;
        p.vced[60]=3;p.vced[81]=5;p.vced[102]=1;
        p.vced[37]=68;p.vced[79]=67;p.vced[20]=6;p.vced[104]=8;break;
    case 28: // warm pad is intentionally less bright, but no longer just sine
        three(79,76,72,93,63);p.vced[20]=5;p.vced[104]=9;break;
    case 29: // glass pad: slowly moving inharmonic upper layers
        three(85,82,72,84,76);p.vced[18]=7;p.vced[19]=21;
        p.vced[60]=5;p.vced[61]=13;break;
    case 30: // cutting lead: near-unison branches with different harmonic sets
        three(89,85,80,91);p.vced[135]=5;p.vced[60]=2;
        p.vced[20]=6;p.vced[104]=8;break;
    case 31: // deliberately strange struck-metal percussion
        three(93,89,84,0);p.vced[18]=11;p.vced[19]=31;p.vced[60]=7;p.vced[61]=17;
        for(unsigned op=0;op<6;++op){auto*v=p.vced.data()+21*op;v[1]=op%2?57:61;v[2]=55;v[5]=op%2?75:90;v[6]=0;}break;
    default: break; // bells, organ, motion, tine, clav, vibes, jingle, hat, sub, log, tom
    }
}

//719 originals: choose the topology for the musical role, then voice its
//transient and body separately. More brightness alone is not more character.
//The successful bell/organ/motion/tine/vibes/jingle and percussion anchors keep
//their718 bytes. No JIANT, Yamaha or third-party preset payload is imported.
void voice_fm_719(unsigned bank, Patch& p) noexcept {
    auto op=[&](unsigned i){return p.vced.data()+21*i;};
    auto env=[&](unsigned i,unsigned attack,unsigned decay,unsigned body,
                 unsigned decay2,unsigned sustain,unsigned release){auto*v=op(i);
        v[0]=attack;v[1]=decay;v[2]=decay2;v[3]=release;
        v[4]=99;v[5]=body;v[6]=sustain;v[7]=0;};
    auto tone=[&](unsigned i,unsigned level,unsigned coarse,unsigned fine=0,
                  unsigned fixed=0){auto*v=op(i);
        v[16]=level;v[17]=fixed;v[18]=coarse;v[19]=fine;};
    auto setup=[&](unsigned algorithm,unsigned feedback,
                   const std::array<unsigned char,6>& levels,
                   const std::array<unsigned char,6>& ratios,
                   unsigned attack,unsigned sustain,unsigned release){
        p.vced[134]=algorithm;p.vced[135]=feedback;
        for(unsigned i=0;i<6;++i){auto*v=op(i);const bool carrier=carrier_mask(algorithm)&(1u<<i);
            for(unsigned j=0;j<21;++j)v[j]=0;
            env(i,attack,50,carrier?sustain:95,40,carrier?sustain:95,release);
            v[8]=48;v[10]=carrier?0:8;v[12]=1;v[13]=0;
            v[14]=1;v[15]=carrier?2:3;v[20]=7;
            tone(i,levels[i],ratios[i]);
        }
        for(unsigned i=0;i<4;++i){p.vced[126+i]=80;p.vced[130+i]=50;}
        p.vced[137]=30;p.vced[138]=40;p.vced[139]=3;p.vced[140]=4;
    };
    switch(bank){
    case 0: // electric piano: hammer, woody middle and a long fundamental decay
        setup(4,1,{82,74,74,71,66,84},{3,1,14,1,1,1},99,0,65);
        for(unsigned i=0;i<6;++i)env(i,99,i%2?43:55,i%2?88:91,34,0,65);
        env(2,99,67,77,55,0,75);env(3,99,61,72,51,0,72);
        op(0)[15]=4;op(2)[15]=5;break;
    case 2: // round finger bass: two unequal three-op stacks, firm low body
        setup(2,3,{66,88,86,74,82,78},{3,1,1,2,1,1},99,87,83);
        env(0,99,53,84,44,79,82);env(1,99,49,91,38,87,82);
        env(3,99,61,78,46,68,82);env(4,99,52,91,40,84,82);break;
    case 3: // ensemble brass: feedback shared by two reeds plus a third stack
        setup(18,5,{94,74,66,77,92,81},{1,1,2,1,1,1},88,94,71);
        env(0,84,48,94,42,92,72);env(3,95,57,87,45,83,73);
        env(4,90,47,95,38,94,72);op(1)[20]=6;op(2)[20]=8;
        p.vced[130]=52;p.vced[127]=72;break;
    case 5: // picked string: bright three-op strike against a hollow second stack
        setup(2,2,{78,91,81,65,82,82},{3,1,1,5,2,1},99,0,81);
        for(unsigned i=0;i<6;++i)env(i,99,(i==2||i==5)?47:61,86,38,0,81);
        env(0,99,67,80,49,0,84);op(0)[15]=5;break;
    case 6: // woody reed: cascaded odd harmonics, separately voiced nasal pair
        setup(0,2,{66,77,89,83,84,76},{2,2,2,1,2,1},88,94,73);
        env(0,99,54,83,42,80,76);env(1,87,52,94,41,92,75);
        env(2,83,48,96,42,95,74);env(4,88,52,93,40,92,73);break;
    case 9: // reed piano: shared modulator drives fundamental and octave
        setup(18,3,{87,81,57,69,78,74},{1,1,2,3,1,1},99,0,67);
        for(unsigned i=0;i<6;++i)env(i,99,carrier_mask(18)&(1u<<i)?41:52,88,34,0,67);
        op(0)[15]=5;op(1)[20]=6;op(5)[20]=8;break;
    case 10: // clav: two stacks, an asymmetric bark and short picked body
        setup(2,4,{72,94,79,80,87,79},{5,1,1,3,2,1},99,0,86);
        for(unsigned i=0;i<6;++i)env(i,99,(i==2||i==5)?54:64,82,47,0,86);
        env(0,99,73,73,58,0,90);op(0)[15]=5;op(1)[15]=4;break;
    case 17: // pick bass: two summed bright sources modulate one body
        setup(10,4,{78,87,84,73,84,77},{4,1,1,3,1,1},99,84,84);
        env(0,99,63,79,46,72,84);env(1,99,48,92,40,89,84);
        env(3,99,67,78,48,66,86);env(4,99,49,91,39,86,84);break;
    case 19: // slap: a full low stack and a brief noninteger string/fret strike
        setup(0,4,{74,83,93,85,90,73},{3,1,1,1,7,1},99,83,85);
        env(0,99,56,85,43,72,85);env(1,99,47,94,40,87,85);
        env(2,99,50,93,43,90,85);env(4,99,63,84,53,0,89);
        env(5,99,62,84,52,0,89);op(4)[19]=13;op(0)[15]=5;
        p.vced[130]=53;p.vced[127]=80;break;
    case 20: // trumpet: forceful lip-stack, distinct from the ensemble recipe
        setup(6,4,{78,87,89,84,91,67},{2,1,1,1,3,1},91,95,76);
        env(0,98,55,89,44,85,77);env(1,92,49,96,44,95,76);
        env(2,87,48,95,41,93,76);
        tone(4,91,3,41);env(4,99,63,87,58,0,79);env(5,99,64,86,57,0,79);
        p.vced[130]=53;p.vced[127]=77;break;
    case 21: // resonant bass: a six-op branched stack, swept index into a growl
        setup(17,5,{69,79,90,83,82,87},{3,1,1,1,2,1},99,90,81);
        for(unsigned i=0;i<5;++i)env(i,99,45+i*2,94-i,38,89-i,81);
        op(2)[15]=4;break;
    case 22: // short synth-brass stab: shared brassy source and octave punch
        setup(21,5,{91,72,71,57,88,82},{1,1,1,2,1,1},99,0,79);
        for(unsigned i=0;i<6;++i)env(i,99,(carrier_mask(21)&(1u<<i))?49:53,90,44,0,79);
        op(1)[20]=6;op(2)[20]=8;p.vced[130]=52;p.vced[127]=75;break;
    case 25: // strings: four gently detuned carriers, shared spectral motion
        setup(20,3,{85,68,68,82,73,73},{1,1,1,1,1,1},39,95,57);
        op(1)[20]=5;op(2)[20]=9;op(4)[20]=6;op(5)[20]=8;
        env(0,36,38,97,31,94,61);env(3,41,36,94,33,96,59);
        p.vced[137]=24;p.vced[138]=32;p.vced[139]=3;p.vced[140]=7;break;
    case 27: // choir vowel: fixed formant carriers under pitched modulators
        setup(4,1,{83,73,88,69,73,74},{1,1,1,1,1,1},71,94,58);
        tone(1,73,2,86,1); // near724Hz first formant
        tone(3,69,3,14,1); // near1380Hz second formant
        env(0,64,40,96,35,94,60);env(2,69,42,95,37,93,60);
        op(1)[20]=6;op(3)[20]=8;p.vced[137]=20;p.vced[138]=38;
        p.vced[139]=2;p.vced[140]=8;break;
    case 28: // warm pad: modulated lower pair plus a three-op airy upper layer
        setup(27,2,{57,72,80,71,79,79},{2,3,1,1,1,1},32,97,51);
        op(0)[20]=8;op(3)[20]=5;op(5)[20]=9;
        env(1,29,32,97,29,93,52);env(2,35,37,95,32,96,54);
        p.vced[137]=18;p.vced[138]=30;p.vced[139]=2;p.vced[140]=6;break;
    case 29: // glass: three inharmonic formant pairs with staggered blooms
        setup(4,0,{88,69,86,70,76,77},{7,1,5,2,3,1},72,90,53);
        tone(0,88,7,23);tone(2,86,5,11);
        env(0,80,43,88,31,93,54);env(2,66,37,96,31,89,54);
        op(1)[20]=6;op(3)[20]=8;p.vced[137]=26;p.vced[140]=15;break;
    case 30: // lead: bite from two summed modulators, weight from a third stack
        setup(10,4,{91,80,80,67,88,79},{1,2,1,3,1,1},97,96,77);
        env(0,99,49,96,42,93,78);env(1,97,50,93,42,91,78);
        env(3,99,59,86,46,79,80);env(4,94,48,95,41,93,78);
        op(2)[20]=6;op(5)[20]=8;break;
    default: break;
    }
}
}

const char* factory_preset_name(std::size_t index) noexcept {
    return index < factory_preset_count ? names[index] : nullptr;
}

SynthEngine factory_preset_engine(std::size_t index) noexcept {
    if (index >= factory_preset_count) return static_cast<SynthEngine>(255);
    return index < 8 || (index >= 16 && index < 40) ? SynthEngine::fm : SynthEngine::va;
}

std::size_t factory_preset_bank_index(std::size_t index) noexcept {
    if (index >= factory_preset_count) return factory_fm_preset_count;
    if (index < 8) return index;
    if (index < 16) return index - 8;
    if (index < 40) return index - 8;
    return index - 32;
}

std::size_t factory_preset_id(SynthEngine engine, std::size_t bank_index) noexcept {
    if (bank_index >= 32) return factory_preset_count;
    if (engine == SynthEngine::fm) return bank_index < 8 ? bank_index : bank_index + 8;
    if (engine == SynthEngine::va) return bank_index < 8 ? bank_index + 8 : bank_index + 32;
    return factory_preset_count;
}

bool load_factory_preset(std::size_t index, FactoryPreset& output) noexcept {
    if (index >= factory_preset_count) return false;
    FactoryPreset result{};
    result.name = names[index];
    result.patch = make_init_patch();
    set_name(result.patch, result.name);
    const auto bank_index = factory_preset_bank_index(index);
    result.engine = factory_preset_engine(index);
    if (result.engine == SynthEngine::fm) {
        const auto& recipe = fm_recipes[bank_index];
        const auto& art = articulation[bank_index];
        result.patch.vced[134] = recipe.algorithm;
        result.patch.vced[135] = recipe.feedback;
        for (std::size_t op = 0; op < 6; ++op) {
            const auto b = 21 * op;
            const bool carrier = (carrier_mask(recipe.algorithm) & (1u << op)) != 0;
            result.patch.vced[b] = recipe.attack;
            result.patch.vced[b+1] = carrier ? recipe.decay : art.decay;
            result.patch.vced[b+2] = recipe.sustain ? 42 : (carrier ? recipe.decay : art.decay);
            result.patch.vced[b+3] = recipe.release;
            result.patch.vced[b+4] = 99;
            result.patch.vced[b+5] = carrier ? (recipe.sustain ? recipe.sustain : 65) : art.body;
            result.patch.vced[b+6] = carrier ? recipe.sustain : art.body;
            result.patch.vced[b+7] = 0;
            result.patch.vced[b+8] = 48; // scaling breakpoint MIDI69 (A4)
            result.patch.vced[b+10] = carrier ? 0 : art.damping;
            result.patch.vced[b+12] = 1; // negative exponential high-key scaling
            result.patch.vced[b+13] = bank_index == 4 ? 0 : (recipe.sustain ? 1 : 2);
            result.patch.vced[b+15] = carrier ? (bank_index == 4 ? 0 : 2) : art.velocity;
            result.patch.vced[b+16] = recipe.levels[op];
            result.patch.vced[b+18] = recipe.ratios[op];
            result.patch.vced[b+19] = (!carrier && op == 0) ? art.fine : 0;
        }
        //715 optional modulation is fully programmed even for dry defaults.
        result.lfo_enabled=bank_index==7 || bank_index==25 || bank_index==27 || bank_index==28 || bank_index==29;
        result.patch.vced[137]=bank_index>=25?23:35;
        result.patch.vced[138]=bank_index>=25?24:38;
        result.patch.vced[139]=bank_index>=25?4:3;
        result.patch.vced[140]=bank_index>=25?10:5;
        result.patch.vced[141]=1;result.patch.vced[142]=4;result.patch.vced[143]=2;
        for(unsigned op=0;op<6;++op)result.patch.vced[21*op+14]=1;
        if (index == 7) {
            result.patch.vced[137] = 24;
            result.patch.vced[140] = 55;
            result.patch.vced[142] = 4;
            // Modulators get deeper motion; carriers retain audible body.
            for (std::size_t op = 0; op < 6; ++op)
                result.patch.vced[21*op+14] = (op == 0 || op == 3) ? 3 : 1;
        }
        if (bank_index >= 25 && bank_index <= 29) {
            for (std::size_t op = 0; op < 6; ++op)
                result.patch.vced[21*op+20] = static_cast<unsigned char>(6 + op % 3);
        }
        if (bank_index == 27 || bank_index == 29) {
            result.patch.vced[137] = bank_index == 27 ? 18 : 29;
            result.patch.vced[140] = bank_index == 27 ? 25 : 38;
            result.patch.vced[142] = 4;
            for (std::size_t op = 0; op < 6; ++op)
                result.patch.vced[21*op+14] = 1;
        }
        // Distinct attacks: brass opens then settles; arcade/slap bass
        // closes its modulators fast while leaving a round carrier body.
        if(bank_index==3 || bank_index==20 || bank_index==21 || bank_index==22) {
            for(unsigned op=0;op<6;++op)if(!(carrier_mask(recipe.algorithm)&(1u<<op))) {
                auto* v=result.patch.vced.data()+21*op;
                v[0]=bank_index==21?99:85;v[1]=bank_index==21?78:64;
                v[5]=bank_index==21?43:68;v[6]=bank_index==21?40:65;v[15]=5;
            }
        }
        if(bank_index==16 || bank_index==19) {
            for(unsigned op=0;op<6;++op)if(!(carrier_mask(recipe.algorithm)&(1u<<op))) {
                auto* v=result.patch.vced.data()+21*op;v[1]=bank_index==19?91:82;
                v[5]=bank_index==19?17:38;v[6]=bank_index==19?12:32;v[15]=5;
            }
        }
        if(bank_index==14) {
            const unsigned char fine[6]={37,0,17,0,23,0};
            for(unsigned op=0;op<6;++op){auto* v=result.patch.vced.data()+21*op;v[19]=fine[op];v[5]=62;v[6]=0;v[2]=38;v[20]=6+op%3;}
        }
        const bool fixed_drum=bank_index==11 || bank_index==13 || bank_index==15;
        const bool pitched_drum=bank_index==24 || bank_index==26 || bank_index==31;
        if(fixed_drum || pitched_drum) {
            result.lfo_enabled=false;result.patch.vced[138]=0;result.patch.vced[139]=3;result.patch.vced[140]=8;
            for(unsigned op=0;op<6;++op) {
                auto* v=result.patch.vced.data()+21*op;
                // Retain an audible drum body; the initial rates produced clicks
                // (95% of hat energy in10ms). Faster modulators keep the snap.
                const auto decay=static_cast<uint8_t>(recipe.decay-(bank_index==15?18:bank_index==31?14:fixed_drum?12:8));
                v[1]=decay+(op%2?0:7);v[2]=decay;v[5]=bank_index==15?35:57;v[6]=0;
                v[13]=0;v[15]=op%2?2:3;v[10]=0;
            }
            if(fixed_drum) {
                // Frequencies are10^(coarse+fine/100)Hz; fixed drums keep
                // their pitch across the keyboard and respond to velocity.
                const unsigned short kick[6]={226,255,104,74,74,74};
                const unsigned short snare[6]={271,270,148,127,152,152};
                const unsigned short hat[6]={391,381,374,366,385,350};
                for(unsigned op=0;op<6;++op){auto* v=result.patch.vced.data()+21*op;
                    unsigned freq=bank_index==11?kick[op]:bank_index==13?snare[op]:hat[op];
                    if(bank_index!=15)freq+=100;v[17]=1;v[18]=static_cast<uint8_t>(freq/100);v[19]=static_cast<uint8_t>(freq%100);v[20]=7;}
            }
            if(bank_index==11 || bank_index==26 || bank_index==24) {
                result.patch.vced[126]=99;result.patch.vced[127]=bank_index==11?82:71;
                result.patch.vced[128]=70;result.patch.vced[129]=80;
                result.patch.vced[130]=bank_index==24?58:72;
                result.patch.vced[131]=result.patch.vced[132]=result.patch.vced[133]=50;
                if(bank_index==26)result.patch.vced[144]=12;
            }
        }
        refine_fm(static_cast<unsigned>(bank_index),result.patch);
        voice_fm_719(static_cast<unsigned>(bank_index),result.patch);
        if(bank_index==23)result.lfo_enabled=true; // delayed breath-like flute vibrato
    } else {
        result.va = va_recipes[bank_index];
        switch(bank_index){
        case 10:result.va={Wave::sine,1500,0,0,390,0,90,5,0};result.patch.vced[144]=0;break;
        case 11:result.va={Wave::noise,6100,.30f,0,165,0,55,5,0};break;
        case 12:result.va={Wave::noise,16000,.05f,0,55,0,22,5,0};break;
        case 13:result.va={Wave::triangle,1400,.25f,0,240,0,90,5,0};result.patch.vced[144]=12;break;
        case 24:result.va={Wave::noise,2800,.65f,0,115,0,35,5,0};break;
        case 29:result.va={Wave::noise,11000,.18f,1,980,0,280,5,0};break;
        default:break;
        }
        // Retain the established oscillator roles; prepare subtle vibrato for
        // every voice while leaving keys/basses/plucks dry until toggled on.
        result.lfo_enabled=result.va.lfo_depth_cents>0;
        if(!result.va.lfo_depth_cents) {
            result.va.lfo_rate_hz=bank_index<14?4.8f:5.6f;
            result.va.lfo_depth_cents=bank_index==8?3.f:bank_index<14?5.f:8.f;
        }
        if(bank_index==6 || bank_index==20 || bank_index==22)result.va.lfo_depth_cents=5;
        if(bank_index==21)result.va.lfo_depth_cents=9;
        if(bank_index==7)result.va.lfo_depth_cents=15;
        if(bank_index==19)result.va.lfo_depth_cents=21;
    }
    output = result;
    return true;
}
} // namespace fmer
