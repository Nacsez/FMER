"""Actual browser captures for the shipped handbook; isolated data, no MIDI."""
from pathlib import Path
from http.server import HTTPServer
from unittest.mock import patch
import json,threading
from datetime import datetime,timezone
import companion,sandbox
from playwright.sync_api import sync_playwright
R=sandbox.ROOT
def main():
    root=R/'artifacts/development-734/help-browser'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    root.mkdir(parents=True,exist_ok=True);sandbox.OUTPUT=root/'renders'
    server=HTTPServer(('127.0.0.1',0),companion.handler_for(sandbox.find_executable('Release'),root/'isolated-library'))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    errors=[]
    try:
        with patch.object(companion.companion_device.hardware_bridge,'WinMM',side_effect=AssertionError('No hardware in help capture')),sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
            page=browser.new_page(viewport=dict(width=1280,height=960),device_scale_factor=1)
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}');page.wait_for_selector('#newEditor')
            def view(name):
                page.locator('[data-view='+name+']').click();page.wait_for_function('!busy && !!catalog')
            def shot(name):page.screenshot(path=str(R/'host/help'/('app-'+name+'.png')),full_page=True)
            view('banks');shot('banks')
            page.locator('#bankArchive').click();page.wait_for_function('!busy')
            view('library');shot('library')
            view('editor');page.wait_for_function("document.querySelector('#editor').contentWindow.fmerLibrary?.ready()")
            shot('editor')
            inner=page.frame_locator('#editor');inner.locator('[aria-label="Engine"]').select_option('1');shot('editor-va')
            for name in ('unit','backups','feedback','firmware'):view(name);shot(name)
            page.locator('#bundledFirmware').click();page.wait_for_function('!busy')
            if page.locator('#failure').inner_text():raise ValueError(page.locator('#failure').inner_text())
            assert page.locator('#installFirmware').is_enabled();shot('firmware')
            if errors:raise ValueError(str(errors))
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join()
        (root/'report.json').write_text(json.dumps(dict(hardware_access=False,errors=errors,output='host/help/app-*.png'),indent=2))
if __name__=='__main__':main()
