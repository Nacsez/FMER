# SPDX-License-Identifier: GPL-3.0-only
"""Actual HTTP/browser sound-pack workflows, isolated library and no hardware."""
from datetime import datetime,timezone
from http.server import HTTPServer
import json
from pathlib import Path
import threading
from unittest.mock import patch
from playwright.sync_api import sync_playwright
import companion,sandbox


def main():
    out=sandbox.ROOT/'artifacts/community-integration-20261020'/('browser-'+datetime.now(timezone.utc).strftime('%H%M%S'))
    out.mkdir(parents=True);report=dict(hardware_access=False,checks=[],errors=[])
    server=HTTPServer(('127.0.0.1',0),companion.handler_for(sandbox.find_executable('Release'),out/'isolated-library'))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}'
    try:
        with patch.object(companion.companion_device.hardware_bridge,'WinMM',side_effect=AssertionError('No hardware allowed')),sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
            page=browser.new_page(viewport=dict(width=1360,height=1000));page.on('pageerror',lambda e:report['errors'].append(str(e)))
            page.route('**/api/presence',lambda route:route.fulfill(json={'inputs':[],'outputs':[]}))
            page.goto(url);page.wait_for_function('!busy && !!catalog')
            before=page.request.get(url+'/api/banks').json()
            def ready():
                page.wait_for_function('!busy',timeout=120000)
                assert not page.locator('#failure').inner_text(),page.locator('#failure').inner_text()
            page.locator('#soundSources').click();ready()
            page.screenshot(path=str(sandbox.ROOT/'host/help/app-sound-sources.png'),full_page=True)
            page.locator('#addDefaults').click();page.wait_for_selector('#confirm[open]');page.locator('#confirm button[value=apply]').click();ready()
            assert len(page.request.get(url+'/api/catalog').json()['slots'])==64
            page.locator('#soundSources').click();ready();page.locator('#addOEM').click()
            page.wait_for_selector('#confirm[open]',timeout=30000);page.locator('#confirm button[value=apply]').click();ready()
            snapshot=page.request.get(url+'/api/catalog').json();assert len(snapshot['slots'])==192
            assert page.locator('[data-focus]').count()==128
            assert all('OEM' in i['tags'] for i in snapshot['slots'][64:])
            assert before==page.request.get(url+'/api/banks').json()
            report['checks'].append('64 FMER + 128 OEM voices added with review; banks unchanged')
            page.screenshot(path=str(out/'oem-library.png'),full_page=True)
            page.locator('#soundSources').click();ready();page.locator('#addOEM').click();ready()
            assert 'already' in page.locator('#notice').inner_text()
            assert len(page.request.get(url+'/api/catalog').json()['slots'])==192
            report['checks'].append('Repeated complete pack import does not create duplicates')
            page.locator('#backLibrary').click();ready();page.locator('#undoCatalog').click();ready()
            assert len(page.request.get(url+'/api/catalog').json()['slots'])==64
            report['checks'].append('OEM bank import is one Undo action')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not report['errors'];browser.close();report['success']=True
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report));return report

if __name__=='__main__':main()
