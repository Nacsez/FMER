#include "../firmware/fm1/panel_gesture.h"
#include <cstdio>
#include <initializer_list>
#include "../firmware/fm1/battery_history.h"
#include <cstdlib>
static void require(bool ok,const char *why){if(!ok){std::fprintf(stderr,"FAIL: %s\n",why);std::exit(1);}}
int main(){
 fmer_panel_gesture_t g{};
 require(!fmer_panel_gesture_edge(&g,3,1,0) && g.select_down,"SEL press starts fine mode without navigation");
 require(fmer_panel_gesture_edge(&g,3,0,25)==4 && !g.select_down,"unused SEL release navigates once");
 require(!fmer_panel_gesture_edge(&g,3,0,26),"duplicate release cannot navigate");
 fmer_panel_gesture_edge(&g,3,1,30);fmer_panel_gesture_encoder(&g);
 fmer_panel_gesture_edge(&g,3,1,31);
 require(!fmer_panel_gesture_edge(&g,3,0,32) && !g.select_down,"used modifier never flips page including duplicate press");
 require(!fmer_panel_gesture_edge(&g,12,1,100),"PLAY waits for release");
 require(fmer_panel_gesture_edge(&g,12,0,200)==13,"short PLAY releases exactly one transport action");
 fmer_panel_gesture_edge(&g,12,1,300);
 require(!fmer_panel_gesture_tick(&g,1099),"hold threshold is not early");
 require(fmer_panel_gesture_tick(&g,1100)==FMER_GESTURE_PANIC,"hold panics at800ms");
 require(!fmer_panel_gesture_tick(&g,1200) && !fmer_panel_gesture_edge(&g,12,0,1300),"held release cannot restart sequence");
 fmer_panel_gesture_edge(&g,12,1,0xffffff00u);
 require(fmer_panel_gesture_edge(&g,12,0,600)==FMER_GESTURE_PANIC,"late release across timerwrap still panics");
 require(fmer_panel_gesture_edge(&g,10,1,1500)==11 && !fmer_panel_gesture_edge(&g,10,0,1501),"ARP dispatches once on press");

 g={};fmer_panel_gesture_edge(&g,3,1,0);fmer_panel_gesture_edge(&g,12,1,10);
 require(!fmer_panel_gesture_edge(&g,12,0,20),"modified first release waits for possible double click");
 require(!fmer_panel_gesture_edge(&g,3,0,30),"launch consumes SEL navigation");
 require(!fmer_panel_gesture_tick(&g,319),"single launch is not early");
 require(fmer_panel_gesture_tick(&g,320)==FMER_GESTURE_LAUNCH_TRACK,"single launch resolves once after double-click window");
 require(!fmer_panel_gesture_tick(&g,321),"single launch cannot repeat");
 g={};fmer_panel_gesture_edge(&g,3,1,0);fmer_panel_gesture_edge(&g,12,1,10);fmer_panel_gesture_edge(&g,12,0,20);
 fmer_panel_gesture_edge(&g,12,1,100);
 require(fmer_panel_gesture_edge(&g,12,0,120)==FMER_GESTURE_LAUNCH_ALL,"double click launches all instead of an early selected launch");
 require(!fmer_panel_gesture_tick(&g,400) && !fmer_panel_gesture_edge(&g,3,0,401),"double launch leaves no latent selected action or page change");

 fmer_battery_history_t history{};
 fmer_battery_history_add(&history,1000,633,632,1);fmer_battery_history_add(&history,2000,632,632,1);
 require(history.total==1,"battery samples bounded to five minutes");
 fmer_battery_history_add(&history,2001,631,632,0);require(history.total==2,"USB detach is retained immediately");
 for(unsigned i=1;i<=130;i++)fmer_battery_history_add(&history,2001+i*300000,600-i,600-i,0);
 require(fmer_battery_history_count(&history)==128 && history.total==132,"history wraps without allocation or flash writes");
 require(fmer_battery_history_get(&history,127)->raw==470 && !fmer_battery_history_get(&history,128),"history reads newest and bounds safely");
 fmer_battery_history_add(&history,9000000,1024,500,1);require(history.total==132,"invalid ADC never fabricates calibration evidence");
 std::puts("FMER705 gestures PASS: fine modifier, short release, panic hold and wrap");
 fmer_panel_gesture_t home{};
 require(fmer_panel_gesture_edge(&home,3,1,0)==0,"SEL arms modifier");
 require(fmer_panel_gesture_edge(&home,8,1,1)==9 && home.select_used,"SEL HOME consumes modifier");
 require(fmer_panel_gesture_edge(&home,8,0,2)==0 && fmer_panel_gesture_edge(&home,3,0,3)==0,"mode shortcut release cannot also page");
 fmer_panel_gesture_t fx{};
 require(!fmer_panel_gesture_edge(&fx,3,1,0),"SEL arms FX default shortcut");
 require(fmer_panel_gesture_edge(&fx,2,1,1)==3 && fx.select_used,"SEL FX dispatches once and consumes modifier");
 require(!fmer_panel_gesture_edge(&fx,2,0,2) && !fmer_panel_gesture_edge(&fx,3,0,3),"saving FX default cannot also navigate on release");
 fmer_panel_gesture_edge(&fx,3,1,4);
 require(fmer_panel_gesture_edge(&fx,3,0,5)==4,"ordinary SEL navigation still works after FX shortcut");
 for(unsigned modifier:{3u,8u,4u,5u}) {
    fmer_panel_gesture_t h{};unsigned trigger=modifier==3u||modifier==8u?11u:8u;
    unsigned expected=modifier==3u?FMER_GESTURE_SONG:modifier==8u?FMER_GESTURE_MIXER:modifier==4u?FMER_GESTURE_MONO:FMER_GESTURE_POLY;
    require(!fmer_panel_gesture_edge(&h,modifier,1,1),"shortcut modifier has no premature tap action");
    require(fmer_panel_gesture_edge(&h,trigger,1,2)==expected,"global shortcut dispatches correct mode");
    require(!fmer_panel_gesture_edge(&h,trigger,0,3) && !fmer_panel_gesture_edge(&h,modifier,0,4),"shortcut releases cannot also navigate");
 }
 for(unsigned button:{2u,5u,6u,7u,11u}) {
  fmer_panel_gesture_t h{};
  require(!fmer_panel_gesture_edge(&h,button,1,100),"section press defers tap so a hold has no premature page or LFO toggle");
  require(!fmer_panel_gesture_tick(&h,899),"section hold threshold is not early");
  require(fmer_panel_gesture_tick(&h,900)==FMER_GESTURE_SECTION_HOME+button,"section hold opens its landing after800ms");
  require(!fmer_panel_gesture_tick(&h,1200) && !fmer_panel_gesture_edge(&h,button,0,1300),"long hold resolves once and suppresses release tap");
  require(!fmer_panel_gesture_edge(&h,button,1,1400) && fmer_panel_gesture_edge(&h,button,0,1450)==button+1,"short tap keeps original action without long-press delay");
  fmer_panel_gesture_edge(&h,button,1,0xfffffff0u);
  require(fmer_panel_gesture_edge(&h,button,0,800)==FMER_GESTURE_SECTION_HOME+button,"late release across clock wrap resolves hold even without service tick");
 }
 for(unsigned modifier:{3u,8u,4u,5u}) {
  fmer_panel_gesture_t h{};unsigned trigger=modifier==3u||modifier==8u?11u:8u;
  fmer_panel_gesture_edge(&h,modifier,1,0);fmer_panel_gesture_edge(&h,trigger,1,10);
  require(!fmer_panel_gesture_tick(&h,2000),"consumed shortcut cannot later emit a section hold");
 }
 for(unsigned release_select_first:{0u,1u}) {
  fmer_panel_gesture_t h{};fmer_panel_gesture_edge(&h,3,1,0);
  require(fmer_panel_gesture_edge(&h,2,1,10)==3u,"SEL FX default shortcut remains immediate");
  require(!fmer_panel_gesture_edge(&h,2,1,11),"duplicate FX down cannot repeat a persistent default action");
  require(!fmer_panel_gesture_tick(&h,2000),"holding SEL FX cannot become section return");
  require(!fmer_panel_gesture_edge(&h,release_select_first?3u:2u,0,2001) &&
          !fmer_panel_gesture_edge(&h,release_select_first?2u:3u,0,2002),"either modifier release order suppresses both navigation and duplicate default action");
  h={};require(!fmer_panel_gesture_edge(&h,2,1,3000) && !fmer_panel_gesture_edge(&h,3,1,3010),"FX then SEL is a consumed reversed chord, never a save shortcut");
  require(!fmer_panel_gesture_tick(&h,3900),"reversed chord cannot emit a latent section hold");
  require(!fmer_panel_gesture_edge(&h,release_select_first?3u:2u,0,3901) &&
          !fmer_panel_gesture_edge(&h,release_select_first?2u:3u,0,3902),"reversed chord suppresses both release orders without saving defaults or navigating");
 }

}
