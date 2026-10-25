"""Actual-browser startup, navigation and error recovery; no device requests.

Also invoked against the extracted EXE's server by the portable rehearsal.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'


def check_browser_startup(url, out, executable=EDGE):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    report = dict(browser=executable, checks=[], unexpected_errors=[], hardware_access=False)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=executable, headless=True)
        context = browser.new_context(viewport=dict(width=1440, height=1000))
        context.route('**/api/presence', lambda r: r.fulfill(json=dict(inputs=[], outputs=[])))
        context.route('**/api/device', lambda r: r.abort())
        context.route('**/api/jobs', lambda r: r.abort())
        page = context.new_page()
        page.on('pageerror', lambda e: report['unexpected_errors'].append(str(e)))
        try:
            page.goto(url)
            page.wait_for_selector('#newEditor', timeout=120000)
            page.wait_for_function("document.querySelector('#startup').hidden")
            assert page.locator('#editor').get_attribute('src') is None
            page.locator('[data-view=banks]').click()
            page.wait_for_selector('#bankEdit')
            expected_name=page.evaluate('banks.slots[bankSlot].name')
            page.locator('#bankEdit').click()
            page.wait_for_function("!busy && document.querySelector('#editor').contentWindow.fmerLibrary?.ready()", timeout=120000)
            assert not page.locator('#failure').inner_text()
            assert page.evaluate("async () => (await document.querySelector('#editor').contentWindow.fmerLibrary.capture()).name")==expected_name
            report['checks'].append('First Open editor waits for initialization and opens the selected saved sound')
            for name in ('banks','loadouts','units','firmware','feedback','library'):
                page.locator('[data-view='+name+']').click()
                # Header proves the navigation event executed; async data screens
                # must also settle without a caught initialization failure.
                page.wait_for_function("name => view === name && !busy", arg=name)
                if name == 'loadouts': page.wait_for_function('!!loadouts')
                if name == 'units': page.wait_for_selector('#saveNamedUnit')
                assert not page.locator('#failure').inner_text()
            page.locator('[data-view=editor]').click()
            page.wait_for_function("document.querySelector('#editor').contentWindow.fmerLibrary?.ready()", timeout=120000)
            page.locator('[data-view=library]').click()
            page.screenshot(path=str(out/'workspace.png'))
            report['checks'].append('Library, banks, loadouts, named units, firmware, feedback and lazy editor respond')

            broken = context.new_page()
            broken.route('**/companion_app.js', lambda r: r.abort())
            broken.goto(url)
            broken.wait_for_function("document.querySelector('#startupTitle').textContent.includes('could not')")
            assert broken.locator('a[download="FMER-startup-diagnostics.json"]').is_visible()
            broken.wait_for_function("async () => (await (await fetch('/api/startup-report')).json()).events.some(e=>e.event==='script_load_error')")
            broken.screenshot(path=str(out/'script-blocked.png'))
            broken.close()
            report['checks'].append('Blocked main script shows recovery and exports its failed resource')

            failed = context.new_page()
            failed.route('**/api/banks', lambda r: r.fulfill(status=400, json={'error':'Simulated bank read failure'}))
            failed.goto(url)
            failed.wait_for_function("document.querySelector('#startupTitle').textContent.includes('could not')")
            assert 'Simulated bank read failure' in failed.locator('#failure').inner_text()
            failed.close()
            report['checks'].append('Saved-data read failure is visible without clearing data')
            page.reload()
            page.wait_for_selector('#newEditor', timeout=120000)
            page.wait_for_function("document.querySelector('#startup').hidden")
            assert not report['unexpected_errors']
            report['checks'].append('Reload recovers and normal startup has no browser exceptions')
            report['status']='passed'
        except Exception as error:
            report['status']='failed'; report['error']=repr(error)
            raise
        finally:
            (out/'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
            browser.close()
    return report
