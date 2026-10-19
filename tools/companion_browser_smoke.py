"""Headless real-browser workflow tests in an isolated bank root; no device APIs."""
from datetime import datetime,timezone
from http.server import HTTPServer
import json
import base64
import hashlib
import re
from pathlib import Path
import threading
import traceback
import companion
import sandbox
from playwright.sync_api import sync_playwright

def main():
    out=sandbox.ROOT/'artifacts/companion-browser'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S');out.mkdir(parents=True)
    sandbox.OUTPUT=out/'renders';exe=sandbox.find_executable('Release')
    server=HTTPServer(('127.0.0.1',0),companion.handler_for(exe,out/'test-banks'));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    report=dict(hardware_access=False,library_root=str(out/'test-banks'),checks=[],errors=[],sources={str(p):hashlib.sha256((sandbox.ROOT/p).read_bytes()).hexdigest() for p in ['host/companion.html','tools/companion.py','tools/companion_bank.py','tools/fm1_native_state_v8.py','tools/companion_browser_smoke.py']})
    def passed(text):report['checks'].append(text);print(text,flush=True)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1050},reduced_motion='reduce');page.on('pageerror',lambda e:report['errors'].append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/editor');page.wait_for_function("document.querySelectorAll('#list button').length===64 && document.querySelector('#title').textContent.includes('/ 00')")
            assert page.locator('#error').inner_text()==''
            page.wait_for_selector('#algorithmDiagram svg')
            graphs=json.loads((sandbox.ROOT/'host/fm_algorithms.json').read_text())['algorithms']
            for a in range(32):
                page.evaluate('(a)=>{state.controls[134]=a;state.vced[134]=a;algorithmDiagram();}',a)
                assert page.locator('#algorithmDiagram svg rect').count()==6
                assert page.locator('#algorithmDiagram svg').get_attribute('aria-label')=='FM algorithm '+str(a+1)+' operator routing'
                assert ('unavailable' in page.locator('#algorithmDiagram').inner_text())==bool(graphs[a]['unsupported_feedback'])
            page.evaluate('state.controls[134]=4;state.vced[134]=4;controls()')
            passed('All32 actual routing diagrams, six operators, unavailable feedback labels')
            page.screenshot(path=str(out/'desktop.png'),full_page=True)
            page.locator('#engine').select_option('0');assert page.locator('#list button').count()==32
            page.locator('#engine').select_option('1');assert page.locator('#list button').count()==32
            page.locator('#search').fill('VA LONG');assert page.locator('#list button').count()==1
            page.locator('#list button').click();page.wait_for_function("document.querySelector('#name').value==='VA LONG'")
            passed('64 presets / both32-sound engine filters / name search / VA load')
            cutoff=page.get_by_role('slider',name='Voice cutoff · Hz',exact=True)
            before_gesture=page.evaluate('state')
            cutoff.press('Home');cutoff.press('Tab');assert page.evaluate('state.controls[177]')==20
            assert cutoff.get_attribute('aria-valuetext')=='20'
            page.locator('#undo').click();assert page.evaluate('state.controls[177]')==5800
            assert page.evaluate('state')==before_gesture
            cutoff.press('End');cutoff.press('Tab');assert page.evaluate('state.controls[177]')==18000
            page.locator('#undo').click();assert page.evaluate('state.controls[177]')==5800
            assert page.evaluate('state')==before_gesture
            passed('Logarithmic cutoff endpoints, exact canonical values and one-gesture Undo')
            page.locator('[data-tab=fx]').click()
            before_recipe=page.evaluate('state')
            page.get_by_role('combobox',name='Chorus character',exact=True).select_option('3')
            assert page.evaluate('state.modulation_profiles[0]')==3
            page.locator('#undo').click();assert page.evaluate('state')==before_recipe
            page.get_by_role('combobox',name='Chorus character',exact=True).select_option('2')
            page.get_by_role('combobox',name='Phaser character',exact=True).select_option('3')
            assert page.evaluate('state.modulation_profiles')==[2,3]
            passed('Chorus/phaser characters use exact native11 values and one-action Undo')
            page.get_by_role('combobox',name='Filter type',exact=True).select_option('2')
            resonance=page.get_by_role('slider',name='FX resonance · %',exact=True)
            resonance.fill('83');resonance.press('Tab')
            page.get_by_role('combobox',name='Program LFO',exact=True).select_option('0')
            for model in ('2','3'):
                page.get_by_role('combobox',name='Reverb model',exact=True).select_option(model)
                assert page.evaluate('state.controls[148]')==int(model)
            page.get_by_role('combobox',name='Delay sync',exact=True).select_option('2')
            assert page.evaluate('state.controls[159]')==2
            page.get_by_role('combobox',name='Delay sync',exact=True).select_option('0')
            assert page.evaluate('state.controls[159]')==0
            passed('Hall/Cloud and synced/free delay choices update canonical controls in the actual editor')
            page.get_by_role('combobox',name='Reverb model',exact=True).select_option('1')
            page.get_by_role('combobox',name='Delay model',exact=True).select_option('1')
            assert page.evaluate('state.controls.slice(145,150)')==[2,83,0,1,1]
            preserved=page.evaluate('({vced:state.vced,patterns:state.patterns})')
            with page.expect_download() as dl:page.locator('#exportFx').click()
            fx_file=out/'FX.json';dl.value.save_as(fx_file)
            profile=json.loads(fx_file.read_text(encoding='utf8'))
            assert profile['version']==4 and profile['modulation_profiles']==[2,3]
            resonance.fill('7');resonance.press('Tab')
            page.locator('#fxFile').set_input_files(fx_file)
            page.wait_for_function('state.controls[146]===83')
            assert page.evaluate('({vced:state.vced,patterns:state.patterns})')==preserved
            page.locator('#undo').click();assert page.evaluate('state.controls[146]')==7
            page.screenshot(path=str(out/'fx.png'),full_page=True)
            passed('Filter modes, resonance, shared LFO and Room/Plate/Clean/Warm controls; FX profile import preserves synth/patterns and is one Undo')
            page.locator('#audition').click();page.wait_for_function("document.querySelector('#metrics').textContent.includes('VA LONG') && !document.querySelector('#busy').textContent")
            page.wait_for_function("document.querySelector('#audio').readyState>=2");page.locator('#stop').click()
            assert not page.locator('#error').inner_text();passed('Actual C++ VA render, bounded report and playable browser WAV')
            page.locator('#name').fill('VA ORBIT');page.locator('#name').press('Tab');page.locator('#favorite').check()
            page.locator('#save').click();page.wait_for_function("!workingDirty && banks.slots[63].name==='VA ORBIT'")
            assert page.evaluate('banks.slots[127].name')=='VA LONG'
            page.locator('#copy').click();page.locator('#destination').select_option('5');page.locator('#confirmYes').click();page.wait_for_function("selected===69 && !workingDirty")
            copied=page.evaluate('banks.slots[69]');assert copied['name']=='VA ORBIT'
            passed('Editable default Save and copy into shared USER bank preserve original copy independently')
            page.get_by_text('Bank management & backups',exact=True).click()
            page.locator('[data-reset=reset_defaults]').click();page.locator('#confirmYes').click();page.wait_for_function("banks.slots[63].name==='VA LONG'")
            assert page.evaluate('banks.slots[69]')==copied
            page.locator('[data-reset=clear_user]').click();page.locator('#confirmNo').click();assert page.evaluate('banks.slots[69]')==copied
            page.locator('[data-reset=clear_user]').click();page.locator('#confirmYes').click();page.wait_for_function('banks.slots.slice(64).every(x=>x===null)')
            assert page.evaluate('banks.slots.slice(0,64).every(x=>x!==null)')
            page.locator('#bankUndo').click();page.locator('#confirmYes').click();page.wait_for_function("banks.slots[69]?.name==='VA ORBIT'")
            page.locator('[data-reset=reset_user]').click();page.locator('#confirmYes').click();page.wait_for_function("banks.slots[69]?.name==='FM PLUCK'")
            passed('Named reset, cancel, clear, bank Undo and restore-default-copies scopes')
            page.locator('[data-tab=seq]').click()
            page.get_by_role('button',name='P15 · 16 steps',exact=True).click()
            page.get_by_role('button',name='Step 1 Rest',exact=True).click()
            pitch=page.get_by_role('slider',name='Step MIDI note · 128 = Rest,129 = Tie',exact=True);pitch.fill('62');pitch.press('Tab')
            assert page.evaluate('state.patterns[15].steps[0][0]')==62
            page.get_by_role('combobox',name='Sequencer mode',exact=True).select_option('1')
            page.get_by_role('combobox',name='Record mode',exact=True).select_option('1')
            page.get_by_role('combobox',name='Track 3 instrument',exact=True).select_option('96')
            page.get_by_role('combobox',name='Track 3 pattern',exact=True).select_option('15')
            page.get_by_role('combobox',name='Track 3 mute',exact=True).select_option('1')
            level=page.get_by_role('slider',name=re.compile(r'^Track 3 level'))
            level.fill('71');level.press('Tab')
            page.get_by_role('button',name=re.compile(r'^Track 3 .* 2$')).click()
            assert page.evaluate('state.controls.slice(154,158)')==[2,96,71,1]
            page.get_by_role('checkbox',name=re.compile(r'Track 3 chain enabled')).check()
            page.get_by_role('checkbox',name='P0',exact=True).check()
            assert page.evaluate('state.tracks[2].chain_mask')==32769
            assert page.get_by_role('combobox',name='Record mode',exact=True).locator('option').count()==3
            page.get_by_role('combobox',name='Record mode',exact=True).select_option('2')
            assert page.evaluate('state.controls[158]')==2
            page.get_by_role('combobox',name='Record mode',exact=True).select_option('1')
            page.get_by_role('combobox',name='Track 3 solo',exact=True).select_option('1')
            page.get_by_role('combobox',name='Track 3 FX send',exact=True).select_option('1')
            assert page.evaluate('state.tracks[2].solo===1 && state.tracks[2].fx_bypass===1')
            retained=page.evaluate('state.tracks')
            page.locator('[data-tab=sound]').click()
            assert page.get_by_role('slider',name='Voices',exact=True).count()==0
            page.get_by_role('combobox',name='Playing mode',exact=True).select_option('0')
            page.get_by_role('slider',name='Voices',exact=True).fill('2')
            page.get_by_role('combobox',name='Mono glide',exact=True).select_option('2')
            assert page.evaluate('state.controls[191]')==1
            assert page.get_by_role('slider',name='Voices',exact=True).count()==0
            page.get_by_role('combobox',name='Mono glide',exact=True).select_option('0')
            assert page.evaluate('state.controls[191]')==2
            page.get_by_role('combobox',name='Mono glide',exact=True).select_option('2')
            page.get_by_role('combobox',name='Playing mode',exact=True).select_option('1')
            assert page.evaluate('state.controls[191]')==4
            page.get_by_role('combobox',name='Playing mode',exact=True).select_option('0')
            assert page.evaluate('state.controls[191]')==1
            page.locator('#undo').click()
            assert page.evaluate('state.controls[153]===1 && state.controls[191]===4')
            page.get_by_role('combobox',name='Playing mode',exact=True).select_option('0')
            page.get_by_role('combobox',name='Mono glide',exact=True).select_option('0')
            assert page.evaluate('state.controls[191]')==4
            page.get_by_role('combobox',name='Mono glide',exact=True).select_option('2')
            page.get_by_role('combobox',name='Glide curve',exact=True).select_option('1')
            time_slider=page.get_by_role('slider',name=re.compile(r'^Glide time'))
            time_slider.press('End');time_slider.press('Tab')
            assert page.evaluate('state.controls.slice(150,153)')==[2,2000,1]
            page.locator('#undo').click();assert page.evaluate('state.controls[151]')==150
            assert page.evaluate('state.tracks')==retained
            page.locator('[data-tab=seq]').click()
            passed('Four-track refs/pattern/mixer/record mode mirrors, mono glide exact values and one-gesture Undo')
            page.locator('[data-tab=fx]').click()
            assert page.evaluate('state.fx_order')==0
            page.get_by_role('button',name='Distortion earlier',exact=True).click()
            assert page.evaluate('state.fx_order')!=0
            reordered=page.evaluate('state.fx_order')
            page.locator('#undo').click();assert page.evaluate('state.fx_order')==0
            page.get_by_role('button',name='Distortion earlier',exact=True).click()
            page.screenshot(path=str(out/'fx-order.png'),full_page=True)
            passed('FX reorder uses the saved rank, observable stage movement and one-action Undo')
            page.locator('#save').click();page.wait_for_function('!workingDirty')
            with page.expect_download() as dl:page.locator('#exportNative').click()
            download=dl.value;native=out/'export.fmer-native';download.save_as(native);assert native.stat().st_size==4000
            page.locator('#nativeFile').set_input_files(native);page.wait_for_function('workingDirty')
            assert page.evaluate('state.patterns[15].steps[0][0]')==62
            assert page.evaluate('state.tracks')==retained
            assert page.evaluate('state.controls.slice(150,153)')==[2,150,1]
            assert page.evaluate('state.fx_order')==reordered
            page.locator('#phrase').select_option('pattern');page.locator('#audition').click();page.wait_for_function("!renderBusy && document.querySelector('#metrics').textContent.includes('Working')")
            assert not page.locator('#error').inner_text();passed('Sixteen-pattern editor, native v7 export/import, cursor mirrors and selected-pattern audition')
            page.locator('#save').click();page.wait_for_function('!workingDirty')
            with page.expect_download() as dl:page.locator('#backup').click()
            backup=out/'bank-backup.json';dl.value.save_as(backup)
            page.locator('#backupFile').set_input_files(backup);page.locator('#confirmYes').click();page.wait_for_function('!workingDirty')
            page.reload();page.wait_for_function("document.querySelectorAll('#list button').length===64")
            assert page.evaluate('banks.slots[69].name')=='FM PLUCK'
            passed('Checksummed whole-bank backup/restore and persistence after page reload')
            # Exercise every new browser project action against explicit HTTP
            # fixtures. These requests never reach WinMM or the attached unit.
            from companion_bank import native as codec
            project_raw=native.read_bytes();project_state=codec.decode(project_raw)
            sound_state=codec.canonical_sound(project_state)
            sound_state['controls'][134]=sound_state['vced'][134]=17
            sound_raw=codec.encode(sound_state);requests=[]
            def fake_device(route):
                request=route.request.post_data_json;requests.append(request)
                action=request['action'];result=dict(success=True,artifacts='isolated-browser-fixture')
                if action=='project_catalog':result['slots']=[dict(slot=i,present=i==15,name='BROWSER') for i in range(16)]
                elif action=='project_pull':result['raw']=base64.b64encode(project_raw).decode()
                elif action=='pull':result['raw']=base64.b64encode(sound_raw).decode()
                elif action=='project_push':
                    codec.decode(base64.b64decode(request['raw']));result['complete_state_verified']=True
                elif action not in ('project_load','project_save'):raise AssertionError('Unexpected device access: '+action)
                route.fulfill(status=200,content_type='application/json',body=json.dumps(result))
            page.route('**/api/device',fake_device)
            page.get_by_text('Projects - 16 onboard arrangements',exact=True).click()
            page.locator('#projectRefresh').click();page.wait_for_function("document.querySelector('#projectStatus').textContent==='1 / 16 saved projects'")
            assert page.locator('#projectSlot option').count()==16
            page.locator('#projectSlot').select_option('15');page.locator('#projectPull').click()
            page.wait_for_function('workingDirty && state.patterns[15].steps[0][0]===62')
            assert page.evaluate('state.tracks')==retained
            page.locator('#projectPush').click();page.locator('#confirmNo').click()
            assert not any(r['action']=='project_push' for r in requests)
            page.locator('#projectPush').click();page.locator('#confirmYes').click();page.wait_for_function('!actionBusy')
            sent=next(r for r in requests if r['action']=='project_push')
            assert sent['slot']==15 and sent['confirmation']=='Replace device project 15'
            assert codec.decode(base64.b64decode(sent['raw']))['patterns']==project_state['patterns']
            before_load=page.evaluate('state')
            page.locator('#projectLoad').click();page.locator('#confirmYes').click();page.wait_for_function('!actionBusy')
            page.locator('#projectSave').click();page.locator('#confirmYes').click();page.wait_for_function('!actionBusy')
            assert page.evaluate('state')==before_load
            assert requests[-1]==dict(action='project_save',slot=15,confirmation='Save device project 15')
            page.get_by_text('Connected FM-1 \u00b7 device banks and test recording',exact=True).click()
            page.locator('#deviceSlot').select_option('63');page.locator('#devicePull').click();page.locator('#confirmYes').click();page.wait_for_function('!actionBusy')
            merged=page.evaluate('state');expected=codec.merge_sound(sound_state,before_load)
            assert merged==expected
            assert merged['patterns'][15]['steps'][0][0]==62 and merged['controls'][134]==17
            passed('Mock transport: project catalog16, pull/push/cancel/exact destination, on-unit Load/Save, sound pull preserves editor arrangement')
            page.locator('#projectSlot').select_option('0')
            page.screenshot(path=str(out/'projects.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(out/'mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
            assert not report['errors'];assert not page.locator('#error').inner_text();passed('390px mobile layout without horizontal overflow; no browser script errors')
            browser.close()
        report['status']='passed'
    except Exception:
        report['status']='failed';report['failure']=traceback.format_exc();raise
    finally:
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');server.shutdown();server.server_close();thread.join();print(out,flush=True)
if __name__=='__main__':main()

