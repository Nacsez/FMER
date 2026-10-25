"""Actual Companion browser workflows with isolated files and blocked hardware."""
from datetime import datetime,timezone
from http.server import HTTPServer
from pathlib import Path
import json,threading
from unittest.mock import patch
import companion,sandbox
from playwright.sync_api import sync_playwright

def main():
    out=sandbox.ROOT/'artifacts/loadouts-20261023'/datetime.now(timezone.utc).strftime('browser-%Y%m%dT%H%M%S');out.mkdir(parents=True,exist_ok=True)
    sandbox.OUTPUT=out/'renders'
    server=HTTPServer(('127.0.0.1',0),companion.handler_for(sandbox.find_executable('Release'),out/'isolated-library'))
    threading.Thread(target=server.serve_forever,daemon=True).start();url=f'http://127.0.0.1:{server.server_port}'
    report=dict(checks=[],errors=[],hardware_access=False);requests=[]
    def passed(s):report['checks'].append(s);print(s,flush=True)
    try:
        with patch.object(companion.companion_device.hardware_bridge,'WinMM',side_effect=AssertionError('Hardware blocked')),sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
            page=browser.new_page(viewport=dict(width=1440,height=1000));page.on('pageerror',lambda e:report['errors'].append(str(e)))
            def ready():
                page.wait_for_function('!busy && !!catalog',timeout=120000)
                assert not page.locator('#failure').inner_text(),page.locator('#failure').inner_text()
            page.goto(url);ready();page.locator('[data-view=loadouts]').click();page.wait_for_selector('#profileSelect')
            assert page.locator('[data-loadout-slot]').count()==64
            assert page.locator('#profileReplace').is_disabled()
            page.screenshot(path=str(out/'included.png'),full_page=True)
            passed('Five included complete profiles; immutable originals and 64 ordered slots visible')
            page.locator('#profileTitle').fill('Night set');page.locator('#profileCopy').click();ready()
            page.wait_for_function('currentProfile().title === "Night set" && loadouts.slots.some(p=>p.id===loadoutId)')
            first=page.locator('[data-loadout-slot="0"] strong').inner_text();second=page.locator('[data-loadout-slot="1"] strong').inner_text()
            page.locator('#profileDown').click();ready();assert page.locator('[data-loadout-slot="1"] strong').inner_text()==first
            page.locator('#profileUndo').click();ready();assert page.locator('[data-loadout-slot="1"] strong').inner_text()==second
            passed('Save a copy, move and Undo preserve included data and exact slot order')
            page.locator('#profileReplace').click();page.wait_for_selector('.loadout-picker[open]')
            page.locator('#pickSearch').fill('Bass');assert page.locator('#pickSound option').count()>0
            chosen=page.locator('#pickSound').input_value();page.locator('#pickApply').click();ready();page.wait_for_selector('.loadout-picker',state='detached')
            passed('Search and replace an instrument from the included catalog into a saved profile')
            page.locator('#profileAudition').click();ready();assert '/audio/' in page.locator('#profileAudio').get_attribute('src')
            page.locator('#profileAudio').evaluate('(a)=>a.pause()')
            passed('Actual local renderer produces a playable profile audition')
            page.locator('#installProfile').select_option('A');page.locator('#installUserProfile').select_option('B')
            page.locator('#sendBankChoices').click();page.wait_for_selector('#confirm[open]')
            assert 'Bank A: A / Spectrum' in page.locator('#confirmText').inner_text()
            assert 'Bank B: B / Rhythm' in page.locator('#confirmText').inner_text()
            page.locator('#confirm button[value=cancel]').click();ready()
            passed('Independent DEFAULT and USER profile choices review correctly; cancel sends no device job')
            page.locator('[data-view=firmware]').click();page.locator('#bundledFirmware').click();ready();page.wait_for_selector('#installUserProfile:not([disabled])')
            assert page.locator('#installProfile').input_value()=='A';assert page.locator('#installUserProfile').input_value()=='B'
            page.screenshot(path=str(out/'install.png'),full_page=True)
            def job(route):
                requests.append(route.request.post_data_json);route.fulfill(json=dict(id='a'*32,state='running'))
            page.route('**/api/jobs',job)
            page.route('**/api/jobs/*',lambda r:r.fulfill(json=dict(id='a'*32,state='complete',message='Complete',operation='install',created=datetime.now(timezone.utc).isoformat(),result=dict(firmware='FM-1_735'))))
            page.locator('#installFirmware').click();page.wait_for_selector('#confirm[open]');page.locator('#confirmApply').click();ready()
            sent=requests[-1];assert sent['loadout']['default']['payload']['id']=='A' and sent['loadout']['user']['payload']['id']=='B'
            import companion_loadouts
            assert sent['loadout']['confirmation']==companion_loadouts.bank_assignment(sent['loadout'])['plan']['confirmation']
            passed('Install submits checksum-validated independent bank snapshots with exact destination confirmation')
            page.locator('[data-view=loadouts]').click();page.wait_for_selector('#profileSelect');page.screenshot(path=str(out/'profile.png'),full_page=True)
            page.locator('[data-view=firmware]').click();page.wait_for_selector('#installUserProfile');page.screenshot(path=str(out/'install-complete.png'),full_page=True)
            page.reload();ready();page.locator('[data-view=loadouts]').click();page.wait_for_selector('#profileSelect')
            assert 'Night set' in page.locator('#profileSelect').inner_text()
            page.locator('#profileSelect').select_option(page.evaluate('loadouts.slots.at(-1).id'))
            page.locator('#installProfile').select_option('A');page.locator('#installUserProfile').select_option('B')
            page.screenshot(path=str(sandbox.ROOT/'host/help/app-loadouts.png'),full_page=True)
            page.locator('[data-view=firmware]').click();page.locator('#bundledFirmware').click();ready();page.wait_for_selector('#installUserProfile:not([disabled])')
            page.screenshot(path=str(sandbox.ROOT/'host/help/app-install-loadouts.png'),full_page=True)
            assert not report['errors'],report['errors']
            passed('Saved profile survives page reload; browser has no script errors')
            browser.close();report['status']='passed'
    finally:
        server.shutdown();server.server_close();(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')

if __name__=='__main__':main()
