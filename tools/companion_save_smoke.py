"""Browser regression for stale editor banks. Isolated files; no MIDI access."""
from datetime import datetime, timezone
from http.server import HTTPServer
import json
from pathlib import Path
import threading
import traceback
from unittest.mock import patch
from playwright.sync_api import sync_playwright
import companion
import sandbox


def main():
    out=sandbox.ROOT/'artifacts/companion-qa-20261021'/('save-'+datetime.now(timezone.utc).strftime('%H%M%S'))
    out.mkdir(parents=True,exist_ok=False)
    server=HTTPServer(('127.0.0.1',0),companion.handler_for(sandbox.find_executable('Release'),out/'library'))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}';report=dict(checks=[],errors=[],hardware_access=False)
    try:
        with patch.object(companion.companion_device.hardware_bridge,'WinMM',side_effect=AssertionError('Hardware forbidden')),sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
            page=browser.new_page();page.on('pageerror',lambda e:report['errors'].append(str(e)))
            page.route('**/api/presence',lambda r:r.fulfill(json={'inputs':[],'outputs':[]}))
            page.goto(url);page.wait_for_function('!busy && !!catalog')
            page.wait_for_function("document.querySelector('#editor').contentWindow.fmerLibrary?.ready()")
            frame=page.frame_locator('#editor')
            def view(name):
                page.locator('[data-view='+name+']').click();page.wait_for_function('!busy')
            def editor_ready():
                page.wait_for_function("!document.querySelector('#editor').contentWindow.eval('actionBusy')")
                assert not frame.locator('#error').inner_text(),frame.locator('#error').inner_text()
            def rename(slot,name):
                banks=page.request.get(url+'/api/banks').json()
                response=page.request.post(url+'/api/banks',data=dict(action='rename',revision=banks['revision'],slot=slot,name=name))
                assert response.ok;return response.json()
            view('editor');frame.locator('#name').fill('EDIT KEEP');frame.locator('#name').press('Tab')
            view('banks')
            for _ in range(2):
                page.locator('[data-reset=reset_defaults]').click();page.locator('#confirm button[value=apply]').click();page.wait_for_function('!busy')
            view('editor');frame.locator('#save').click();editor_ready()
            assert page.request.get(url+'/api/banks').json()['slots'][0]['name']=='EDIT KEEP'
            report['checks'].append('Two outer bank resets do not strand an edited sound at revision zero')
            rename(1,'OTHER KEEP');frame.locator('#name').fill('SECOND');frame.locator('#name').press('Tab');frame.locator('#save').click();editor_ready()
            assert page.request.get(url+'/api/banks').json()['slots'][1]['name']=='OTHER KEEP'
            report['checks'].append('Unrelated concurrent bank changes survive saving the working sound')
            rename(0,'NEW TARGET');frame.locator('#name').fill('DRAFT');frame.locator('#name').press('Tab');frame.locator('#save').click()
            frame.locator('#confirm[open]').wait_for();frame.locator('#confirmNo').click();editor_ready()
            assert frame.locator('#name').input_value()=='DRAFT'
            assert page.request.get(url+'/api/banks').json()['slots'][0]['name']=='NEW TARGET'
            frame.locator('#save').click();frame.locator('#confirmYes').click();editor_ready()
            assert page.request.get(url+'/api/banks').json()['slots'][0]['name']=='DRAFT'
            report['checks'].append('Changed destination requires review; cancel retains draft and saved target')
            raced=[False]
            def race(route):
                if route.request.method=='POST' and route.request.post_data_json.get('action')=='save' and not raced[0]:
                    raced[0]=True;rename(0,'RACE KEEP')
                route.continue_()
            page.route('**/api/banks',race)
            frame.locator('#name').fill('RACE DRAFT');frame.locator('#name').press('Tab');frame.locator('#save').click()
            page.wait_for_function("!document.querySelector('#editor').contentWindow.eval('actionBusy')")
            assert 'edits' in frame.locator('#error').inner_text().lower()
            assert page.request.get(url+'/api/banks').json()['slots'][0]['name']=='RACE KEEP'
            assert frame.locator('#name').input_value()=='RACE DRAFT'
            frame.locator('#save').click();frame.locator('#confirmYes').click();editor_ready()
            view('banks');assert page.locator('#bankName').input_value()=='RACE DRAFT'
            report['checks'].append('Save-time race refuses overwrite, retains draft and requires review on retry; outer bank view refreshes')
            assert not report['errors'];report['status']='passed';browser.close()
    except Exception:
        report['status']='failed';report['failure']=traceback.format_exc();raise
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
        print(out,flush=True)


if __name__=='__main__':main()
