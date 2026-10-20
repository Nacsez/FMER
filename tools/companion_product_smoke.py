"""Real browser and HTTP product checks. Isolated library; hardware blocked."""
from datetime import datetime,timezone
from http.server import HTTPServer
import hashlib
import json
from pathlib import Path
import threading
import traceback
from unittest.mock import patch
import companion
import launch_companion
import sandbox
from playwright.sync_api import sync_playwright


def main():
    out=sandbox.ROOT/'artifacts/companion-product'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S');out.mkdir(parents=True)
    sandbox.OUTPUT=out/'renders';server=HTTPServer(('127.0.0.1',0),companion.handler_for(sandbox.find_executable('Release'),out/'isolated-library'))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
    report=dict(hardware_access=False,library_root=str(out/'isolated-library'),checks=[],errors=[],sources={str(p.relative_to(sandbox.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (sandbox.ROOT/'host').glob('companion*') if p.is_file()})
    def passed(s):report['checks'].append(s);print(s,flush=True)
    try:
        with patch.object(companion.companion_device.hardware_bridge,'WinMM',side_effect=AssertionError('Hardware forbidden in product smoke')),sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
            page=browser.new_page(viewport=dict(width=1440,height=1000));page.on('pageerror',lambda e:report['errors'].append(str(e)))
            def ready():page.wait_for_function('!busy && !!catalog',timeout=120000);assert not page.locator('#failure').inner_text()
            def view(name):page.locator('[data-view='+name+']').click();ready()
            page.goto(base);page.wait_for_selector('#newEditor');ready()
            assert page.request.get(base+'/api/health').json()['app']==launch_companion.APP
            assert launch_companion.health(server.server_port)
            page.route('**/api/presence',lambda route:route.fulfill(json={'inputs':['FM-1 Midi'],'outputs':['FM-1 Midi']}))
            assert 'FMER Companion 734' in page.locator('footer').inner_text()
            assert page.request.get(base+'/api/capabilities').json()['firmware_identity']=='FM-1_734'
            assert 'Make room' in page.locator('#content').inner_text()
            assert page.locator('#connection').inner_text()=='Check connection'
            view('banks');page.locator('#bankArchive').click();ready();view('library')
            assert page.locator('[data-focus]').count()==1
            page.locator('[data-focus]').click();page.locator('#itemTitle').fill('Stage Bass <safe>');page.locator('#itemName').fill('STAGE BASS')
            page.locator('#itemCollection').fill('Night set');page.locator('#itemTags').fill('bass, performance');page.locator('#itemFavorite').check();page.locator('#saveDetails').click();ready()
            assert page.locator('[data-focus]').inner_text()=='★ Stage Bass <safe>'
            assert page.locator('#itemName').input_value()=='STAGE BASS'
            page.locator('[data-pick]').check();page.locator('#duplicateSelection').click();ready();assert page.locator('[data-focus]').count()==2
            page.locator('#trashSelection').click();ready();assert page.locator('[data-focus]').count()==1
            page.locator('#showTrash').check();assert page.locator('[data-focus]').count()==1
            page.locator('[data-pick]').check();page.locator('#trashSelection').click();ready();assert page.locator('[data-focus]').count()==0
            page.locator('#showTrash').uncheck();page.locator('#selectAll').check()
            with page.expect_download() as download:page.locator('#exportSelection').click()
            export=out/'selection.json';download.value.save_as(export);ready()
            assert len(json.loads(export.read_text())['payload']['slots'])==2
            page.locator('#importCatalog').click();page.locator('#file').set_input_files(export);ready();assert page.locator('[data-focus]').count()==4
            page.reload();page.wait_for_selector('[data-focus]');assert page.locator('[data-focus]').count()==4
            passed('Persistent catalog rename/name agreement, tags/favorite, duplicate, Trash/recover, export/import and HTML escaping')
            page.locator('[data-pick]').first.check();page.locator('#exportDx7').click()
            page.wait_for_selector('#confirm[open]')
            with page.expect_download() as download:page.locator('#confirm button[value="apply"]').click()
            dx7=out/'voice.syx';download.value.save_as(dx7);ready();assert dx7.stat().st_size==163
            page.locator('#importDx7').click();page.locator('#file').set_input_files(dx7)
            page.wait_for_selector('#confirm[open]');page.locator('#confirm button[value="apply"]').click();ready()
            assert page.locator('[data-focus]').count()==1
            assert page.locator('#filterCollection').input_value()=='DX7 imports'
            page.locator('#undoCatalog').click();ready()
            page.locator('#filterCollection').select_option('all');assert page.locator('[data-focus]').count()==4
            passed('DX7 export/import uses shared codec, explicit loss review and atomic catalog Undo without hardware access')
            page.screenshot(path=str(out/'library-desktop.png'),full_page=True)
            view('editor');page.wait_for_function("document.querySelector('#editor').contentWindow.fmerLibrary?.ready()")
            inner=page.frame_locator('#editor')
            assert not inner.locator('#deviceRefresh').is_visible()
            assert inner.locator('[aria-label="Playing mode"]').is_visible()
            inner.locator('[aria-label="Playing mode"]').select_option('2')
            assert inner.locator('[aria-label="Voices"]').count()==0
            assert inner.locator('[aria-label="Playing mode"]').input_value()=='2'
            inner.locator('[aria-label="Playing mode"]').select_option('0')
            assert inner.locator('[aria-label="Voices"]').count()==0
            assert inner.locator('[aria-label="Mono glide"]').input_value()=='1'
            inner.locator('[aria-label="Playing mode"]').select_option('1')
            assert inner.locator('[aria-label="Voices"]').input_value()=='4'
            inner.locator('[aria-label="Voices"]').press('End')
            inner.locator('[aria-label="Voices"]').press('ArrowLeft')
            assert inner.locator('[aria-label="Playing mode"]').input_value()=='3'
            assert '3V' in inner.locator('[aria-label="Playing mode"] option:checked').inner_text()
            inner.locator('[aria-label="Voices"]').press('ArrowLeft')
            assert '2V' in inner.locator('[aria-label="Playing mode"] option:checked').inner_text()
            inner.locator('[aria-label="Playing mode"]').select_option('1')
            assert inner.locator('[aria-label="Voices"]').input_value()=='4'

            page.locator('#captureKind').select_option('project');page.locator('#captureEditor').click();ready()
            assert page.locator('#extractSounds').count()==1
            before=page.locator('[data-focus]').count();page.locator('#extractSounds').click();ready();assert page.locator('[data-focus]').count()>before
            passed('Embedded exact-core editor project capture and extraction of referenced PC instrument snapshots')
            view('banks');page.locator('#bankName').fill('PC RENAME');page.locator('#bankRename').click();ready()
            assert page.locator('#bankName').input_value()=='PC RENAME'
            page.locator('#undoBank').click();ready();assert page.locator('#bankName').input_value()!='PC RENAME'
            page.locator('#pcBank').select_option('1');page.locator('#bankDelete').click();ready();assert page.locator('#bankEdit').is_disabled()
            page.locator('#undoBank').click();ready();assert page.locator('#bankEdit').is_enabled()
            passed('PC bank rename and USER clear/Undo; canonical records retained')
            requests=[];job_count=0
            def mock_job(route):
                nonlocal job_count
                request=route.request.post_data_json;requests.append(request);job_count+=1
                route.fulfill(json=dict(id=str(job_count)))
            page.route('**/api/jobs',mock_job)
            polls=[0]
            def mock_status(route):
                polls[0]+=1
                if polls[0]<=4:
                    route.fulfill(json=dict(state='running',message='Reading instruments',identity='FM-1_733',created=datetime.now(timezone.utc).isoformat(),progress=dict(done=32,total=144,unit='slots')))
                else:route.fulfill(json=dict(state='complete',message='Complete',identity='FM-1_733',result=dict(slots=[])))
            page.route('**/api/jobs/*',mock_status)
            view('unit');page.locator('#readUnit').click()
            page.wait_for_function("document.querySelector('#jobProgress').value===32")
            assert page.locator('#operation').is_visible()
            assert page.locator('#content').evaluate('(e)=>e.inert')
            assert page.locator('#jobCount').inner_text()=='22% '+chr(183)+' 32 / 144 slots'
            assert page.locator('#connection').inner_text()=='FMER connected'
            page.screenshot(path=str(out/'transfer-progress.png'),full_page=True)
            ready();assert requests[-1]['request']['action']=='catalog'
            assert page.locator('#operation').get_attribute('data-state')=='complete'
            assert not page.locator('#content').evaluate('(e)=>e.inert')
            passed('Visible numeric progress, connection identity, transfer lock and persistent completion')
            page.evaluate("unitSlots=[{name:'OLD UNIT'}];unitProjects=[{name:'OLD PROJECT'}];previousPorts=JSON.stringify({inputs:['FM-1 Midi'],outputs:['FM-1 Midi']})")
            page.route('**/api/presence',lambda route:route.fulfill(json={'inputs':[],'outputs':[]}))
            page.evaluate('pollPresence()');assert page.locator('#connection').inner_text()=='Not connected'
            assert page.evaluate('unitSlots===null&&unitProjects===null')
            page.route('**/api/presence',lambda route:route.fulfill(json={'inputs':['FM-1 Midi'],'outputs':['FM-1 Midi']}))
            page.evaluate('pollPresence()');assert 'check connection' in page.locator('#connection').inner_text()
            passed('Unplug clears connection and cached catalogs; reconnect requires fresh verification')
            page.evaluate("unitSlots=[{name:'STALE'}];unitProjects=[{name:'STALE'}];previousPorts=null")
            page.route('**/api/presence',lambda route:route.fulfill(json={'inputs':['FMER','FMER'],'outputs':['FMER','FMER']}))
            page.evaluate('pollPresence()');assert page.locator('#connection').inner_text()=='Multiple FM-1s - connect one'
            assert page.evaluate('unitSlots===null&&unitProjects===null')
            page.route('**/api/presence',lambda route:route.fulfill(json={'inputs':['FMER'],'outputs':['FMER']}))
            page.evaluate('pollPresence()');assert 'check connection' in page.locator('#connection').inner_text()
            passed('Multiple instruments show explicit guidance and clear stale unit catalogs; returning to one requires verification')

            page.locator('#copyUnit').click();page.locator('#confirm button[value=cancel]').click();ready();assert len(requests)==1
            page.locator('#unitSlot').select_option('64');page.locator('#unitDestination').select_option('7');page.locator('#copyUnit').click();page.locator('#confirmApply').click();ready()
            assert requests[-1]['request']==dict(action='instrument_copy',slot=64,destination=7,confirmation='Apply unit instrument change')
            passed('Mock-only background device jobs, explicit destination, cancel sends no operation')
            # Real review UI and validation endpoint; only device jobs are fake.
            view('banks');before=len(requests)
            page.locator('#bankSend').click();page.wait_for_selector('#transfer[open]')
            assert page.locator('[data-transfer]').count()==1
            assert page.locator('[data-transfer]').input_value()=='0'  # PC USER -> unit USER
            page.locator('#transfer button[value=cancel]').click();ready()
            assert len(requests)==before
            page.locator('#pcBank').select_option('0');page.locator('#sendBank').click()
            page.wait_for_selector('#transfer[open]');assert page.locator('[data-transfer]').count()==64
            assert page.locator('[data-transfer="0"]').input_value()=='64'  # PC DEFAULT -> unit DEFAULT
            page.locator('#transferBank').select_option('0');page.locator('#placeTransfer').click()
            assert page.locator('[data-transfer="0"]').input_value()=='0'
            assert page.locator('[data-transfer="63"]').input_value()=='63'
            assert page.locator('#transferStart option').count()==1  # no bank overflow
            page.locator('#transfer button[value=cancel]').click();ready()
            page.locator('#bankSend').click();page.wait_for_selector('#transfer[open]')
            page.locator('[data-transfer="0"]').select_option('12')
            page.locator('#transfer button[value=review]').click();page.wait_for_selector('#confirm[open]')
            assert 'USER 12' in page.locator('#confirmText').inner_text()
            page.locator('#confirmApply').click();ready()
            request=requests[-1]['request']
            assert request['action']=='deploy_library' and request['rows'][0]['slot']==12
            import companion_transfer
            assert request['confirmation']==companion_transfer.plan(request['rows'])['confirmation']
            view('library');page.locator('#selectAll').check();page.locator('#sendSelection').click()
            page.wait_for_selector('#transfer[open]')
            page.locator('[data-transfer="1"]').select_option('0')
            before=len(requests);page.locator('#transfer button[value=review]').click()
            page.wait_for_function('!busy')
            assert 'same destination' in page.locator('#failure').inner_text()
            assert len(requests)==before
            page.evaluate("document.querySelector('#failure').textContent=''")
            assert page.get_by_role('link',name='Updates & downloads').get_attribute('href')=='https://github.com/Nacsez/FMER/releases'
            passed('Reviewed bank/set deployment, USER/DEFAULT mapping, cancellation, duplicate destinations and explicit GitHub links')
            view('unit')
            import companion_errors
            outcome=companion_errors.explain('different memory layout or calibration',True)
            page.route('**/api/jobs/*',lambda route:route.fulfill(json=dict(state='failed',action='install',message='Stopped',error='technical mismatch',outcome=outcome,created=datetime.now(timezone.utc).isoformat())))
            page.locator('#readUnit').click();ready()
            assert 'does not prove different hardware' in page.locator('#jobExplanation').inner_text()
            assert 'Export operation record' in page.locator('#jobNext').inner_text()
            assert page.locator('#downloadJob').is_visible()
            assert page.locator('#jobRecord').get_attribute('open') is None
            assert 'review the message below' not in page.locator('#jobSafety').inner_text().lower()
            page.screenshot(path=str(out/'compatibility-message.png'),full_page=True)
            passed('Human explanation and next action are visible; raw JSON stays collapsed and export is direct')
            view('firmware');assert page.locator('#installFirmware').is_disabled()
            package=sandbox.ROOT/'artifacts/development-721/package-release1/fmer-candidate.fwsc'
            if package.exists():
                page.locator('#chooseFirmware').click();page.locator('#file').set_input_files(package);ready()
                page.wait_for_function('inspection !== null')
                assert page.locator('#installFirmware').is_disabled()
                assert page.locator('#firmwareReport dd').last.inner_text()=='No'
                passed('Historical package inspected; source drift blocks installation without hardware access')
            # Publisher recognition is useful, but cannot be styled as an
            # approved restore or acquire an installation token.
            page.route('**/api/firmware',lambda route:route.fulfill(json=dict(product='FM-1_8000013',title='M-VAVE Open V13',recognized=True,installable=False,compatibility='layout migration not qualified',limitation='Open V13 requires a separately tested layout migration.')))
            official=out/'official-fixture.bin';official.write_bytes(b'not sent to a device')
            page.locator('#chooseStock').click();page.locator('#file').set_input_files(official);ready()
            assert page.locator('#installFirmware').is_disabled()
            assert 'requires a separately tested layout migration' in page.locator('#notice').inner_text()
            assert 'verified' not in page.locator('#notice').inner_text().lower()
            page.unroute('**/api/firmware')
            passed('Recognized official firmware with a different layout stays non-installable with a clear explanation')
            view('feedback');page.locator('#feedback7').fill('Pattern changes worked well.')
            with page.expect_download() as download:page.locator('#feedbackExport').click()
            feedback=out/'feedback.json';download.value.save_as(feedback);ready()
            exported=json.loads(feedback.read_text());assert exported['feedback']=={'Sequencer':'Pattern changes worked well.'}
            assert exported['format']=='FMER-BETA-FEEDBACK'
            passed('Optional beta feedback and sanitized summary export locally without upload')
            view('backups')
            with page.expect_download() as download:page.locator('#catalogBackup').click()
            backup=out/'backup.json';download.value.save_as(backup);ready()
            assert json.loads(backup.read_text())['format']=='FMER-CATALOG-FILE'
            with page.expect_popup() as popup:page.get_by_role('link',name='Help & workflows').click()
            help_page=popup.value;help_page.wait_for_selector('#helpSearch');help_page.locator('#helpSearch').fill('pitch envelope');assert help_page.locator('#results a').count()>0
            help_page.goto((sandbox.ROOT/'host/help/index.htm').as_uri());help_page.locator('#helpSearch').fill('velocity sensitivity');assert help_page.locator('#results a').count()>0
            assert not help_page.locator('#back').get_attribute('href')
            passed('Complete catalog backup download; Help opens a new browser tab and searches offline file://')
            for path in ('/help/../README.md','/help/%2e%2e%2fREADME.md','/help/nope.htm'):
                assert page.request.get(base+path).status==404
            assert page.request.post(base+'/api/catalog',headers={'Origin':'https://untrusted.example'},data={'action':'snapshot'}).status==403
            passed('Help traversal and cross-origin mutations rejected')
            view('banks')
            with page.expect_download() as download:page.locator('#backupBanks').click()
            banks_file=out/'pc-banks.json';download.value.save_as(banks_file);ready()
            view('library');count=page.evaluate('catalog.slots.length')
            page.locator('#importCatalog').click();page.locator('#file').set_input_files(banks_file);ready()
            assert page.evaluate('catalog.slots.length')==count+128
            page.locator('#undoCatalog').click();ready();assert page.evaluate('catalog.slots.length')==count
            passed('PC bank sound-pack import merges all 128 populated copies and one Undo restores the prior Library')
            import companion_archive
            native=page.evaluate('banks.slots[0].native')
            saved=companion_archive.seal(dict(identity='FM-1_734',created=datetime.now(timezone.utc).isoformat(),
                instruments=[native]*128,projects=[None]*16,live=native,midi=[0]*8))
            page.route('**/api/jobs/*',lambda route:route.fulfill(json=dict(id='a'*32,state='failed',message='Stopped',progress=dict(backup_path='private saved backup'),outcome=companion_errors.explain('Transfer stopped after 1/2 verified slots. No automatic retry.'),created=datetime.now(timezone.utc).isoformat())))
            page.route('**/api/jobs/*/backup',lambda route:route.fulfill(json=saved))
            view('unit');page.locator('#readUnit').click();ready()
            assert page.locator('#downloadJobBackup').is_visible()
            assert '1/2 verified' in page.locator('#jobExplanation').inner_text()
            with page.expect_download() as download:page.locator('#downloadJobBackup').click()
            saved_file=out/'interrupted-transfer-backup.json';download.value.save_as(saved_file);ready()
            assert json.loads(saved_file.read_text())==saved
            passed('Interrupted deployment exposes readable partial completion and a direct pre-transfer backup download')
            view('library');page.set_viewport_size(dict(width=390,height=844));page.screenshot(path=str(out/'library-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
            for target in ('banks','unit','backups','firmware','feedback'):
                view(target);assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'),target
            assert not report['errors'];passed('390px responsive layouts and no browser script errors')
            browser.close();report['status']='passed'
    except Exception:
        report['status']='failed';report['failure']=traceback.format_exc();raise
    finally:
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8');server.shutdown();server.server_close();thread.join();print(out,flush=True)
if __name__=='__main__':main()
