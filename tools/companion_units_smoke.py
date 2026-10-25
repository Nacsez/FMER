"""Real-browser named instrument workflows, isolated files and no hardware."""
from pathlib import Path
from datetime import datetime,timezone
from http.server import HTTPServer
import json,threading
from unittest.mock import patch
from playwright.sync_api import sync_playwright
import companion,sandbox

def main():
 out=sandbox.ROOT/'artifacts/development-735'/datetime.now(timezone.utc).strftime('unit-browser-%H%M%S');out.mkdir()
 server=HTTPServer(('127.0.0.1',0),companion.handler_for(sandbox.find_executable('Release'),out/'library'))
 threading.Thread(target=server.serve_forever,daemon=True).start();result=dict(success=False,errors=[],hardware_access=False)
 try:
  with patch.object(companion.companion_device.hardware_bridge,'WinMM',side_effect=AssertionError('No hardware in UI test')),sync_playwright() as pw:
   browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
   page=browser.new_page(viewport=dict(width=1440,height=1000));page.on('pageerror',lambda e:result['errors'].append(str(e)))
   page.goto(f'http://127.0.0.1:{server.server_port}/#units');page.wait_for_selector('#saveNamedUnit',timeout=120000)
   def ready():
    page.wait_for_function('!busy');assert not page.locator('#failure').inner_text(),page.locator('#failure').inner_text()
   def create(name,a,b):
    page.locator('#editUnit').select_option('new');page.locator('#namedUnitName').fill(name)
    page.locator('#namedBankA').select_option(a);page.locator('#namedBankB').select_option(b)
    page.locator('#saveNamedUnit').click();ready()
   create('Malachite','A','B');create('Citrine','C','D')
   rows=page.request.get(f'http://127.0.0.1:{server.server_port}/api/units').json()['slots']
   assert [(r['name'],r['default'],r['user']) for r in rows]==[('Malachite','A','B'),('Citrine','C','D')]
   page.locator('#editUnit').select_option(rows[0]['id']);page.locator('#useNamedUnit').click();ready()
   assert page.locator('#namedUnitSelect').input_value()==rows[0]['id']
   assert page.evaluate('[installProfile,installUserProfile]')==['A','B']
   page.locator('#namedUnitSelect').select_option(rows[1]['id']);ready()
   assert page.evaluate('[installProfile,installUserProfile]')==['C','D']
   assert page.evaluate('unitSlots===null && unitProjects===null && inspection===null')
   page.locator('#editUnit').select_option(rows[1]['id']);page.screenshot(path=str(out/'units.png'),full_page=True)
   page.screenshot(path=str(sandbox.ROOT/'host/help/app-units.png'),full_page=True)
   page.reload();page.wait_for_selector('#editUnit');assert 'Malachite' in page.locator('#editUnit').inner_text()
   assert page.locator('#namedUnitSelect').input_value()==''  # No silent hardware/name association after restart.
   page.locator('#editUnit').select_option(rows[0]['id']);page.locator('#namedUnitName').fill('Studio FM');page.locator('#saveNamedUnit').click();ready()
   page.locator('#unitProfileUndo').click();ready();assert 'Malachite' in page.locator('#editUnit').inner_text()
   page.locator('#editUnit').select_option(rows[0]['id']);page.locator('#removeNamedUnit').click();page.locator('#confirmApply').click();ready()
   assert 'Malachite' not in page.locator('#editUnit').inner_text();assert 'Citrine' in page.locator('#editUnit').inner_text()
   page.set_viewport_size(dict(width=390,height=844));page.screenshot(path=str(out/'mobile.png'),full_page=True)
   assert not result['errors'],result['errors'];result.update(success=True,profiles=2,checks=['independent assignments','switch clears device cache','no implicit hardware binding','persistence','rename undo','delete isolation','mobile layout'])
   browser.close()
 finally:
  server.shutdown();server.server_close();(out/'report.json').write_text(json.dumps(result,indent=2))
 print(json.dumps(dict(success=result['success'],artifacts=str(out))))

if __name__=='__main__':main()
