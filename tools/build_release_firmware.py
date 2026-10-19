"""Build the portable compatibility-checked installer without opening hardware.
The private reference is build-time only. A public160-byte stock-compatible
flash descriptor permits stage1 parsing; private protected-head data is absent.
"""
from pathlib import Path
import argparse, hashlib, json, subprocess
import fm1_package as p
import release_firmware as release
import build_fm1_candidate as candidate_builder
R=Path(__file__).resolve().parents[1]

def build(candidate, out, loader_test):
    out.mkdir(parents=True, exist_ok=False)
    report=json.loads((candidate/'report.json').read_text())
    elf=candidate/'fm1.elf'
    if not report['success'] or report['usb_product']!='FMER' or release.digest(elf.read_bytes())!=report['elf']['sha256']:
        raise ValueError('Expected successful generic FMER candidate')
    for item in report['sources']+report['local_headers']:
        source=R/item['path']
        if not source.is_file():source=candidate_builder.FELUCCA/item['path']
        if release.digest(source.read_bytes())!=item['sha256']:
            raise ValueError('Candidate source changed: '+item['path'])
    app,details=p.extract_elf(elf.read_bytes(),'app')
    lock=json.loads((R/'evidence/target-toolchain.json').read_text())
    ota=p.build_loader(out/'loader',R/lock['toolchain']['local_root'],lock,p.CITRINE_TEMPLATE,stock_v15=True,portable=True)
    stock=p.citrine_flash_reference()
    if release.digest(stock[0x4000:])!=release.ORIGIN_SHA:raise ValueError('Stock reference changed')
    flash=release.distribution_head()+p.flash_image(app,p.KEY,p.CITRINE_TEMPLATE)[0x4000:]
    raw=p.ufw(flash,ota,release.TARGET)
    filename='fmer734-compatible-r1.fwsc'
    (out/filename).write_bytes(raw);(out/'app.bin').write_bytes(app)
    # The deployed file intentionally has no boot/identity head. Supply the
    # simulated device's existing head separately to the independent C test.
    (out/'device-head-fixture.bin').write_bytes(stock[:0x4000])
    result=subprocess.run([str(loader_test.resolve()),str((out/filename).resolve()),str((out/'loader/loader.bin').resolve()),str((out/'device-head-fixture.bin').resolve())],capture_output=True,text=True)
    (out/'loader-tests.json').write_text(json.dumps(dict(command=result.args,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr),indent=2))
    if result.returncode or 'passed' not in result.stdout.lower():raise ValueError('Independent loader qualification failed; inspect loader-tests.json')
    sources=['tools/'+x+'.py' for x in ('release_firmware','fm1_flash_transport','fm1_package','hardware_bridge','unit_endpoints','companion_jobs','companion_stock')]
    entry=dict(id=release.PROFILE,title='FMER 734',filename=filename,
        product=release.TARGET,origin_identity='compatible-FM-1',loader_identity=release.LOADER,
        origin_app_sha256=release.ORIGIN_SHA,record_address=0xE7F00,
        qualification='offline-qualified-first-install-preview',package_sha256=release.digest(raw),
        loader_sha256=release.digest(p.validate_loader(ota)),app_region_sha256=release.digest(flash[0x4000:]),
        app_padded_sha256=release.digest(app+b'\xff'*(p.TEST01_APP_SLOT-len(app))),
        source_files=[dict(path=s,sha256=release.digest((R/s).read_bytes())) for s in sources])
    destination=R/'firmware/releases';destination.mkdir(exist_ok=True)
    (destination/filename).write_bytes(raw)
    (destination/'catalog.json').write_text(json.dumps(dict(schema=1,releases=[entry]),indent=2)+'\n',encoding='utf8')
    inspected=release.inspect_bytes(raw)
    (out/'report.json').write_text(json.dumps(dict(success=True,device_opened=False,device_writes=False,
        hardware_qualified=False,application=details,inspection=inspected,
        loader_tests_sha256=release.digest((out/'loader-tests.json').read_bytes())),indent=2),encoding='utf8')
    print(json.dumps(dict(package=str(destination/filename),sha256=entry['package_sha256'],bytes=len(raw),hardware_qualified=False)))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--candidate',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--loader-test',type=Path,required=True)
    args=parser.parse_args();build(args.candidate,args.out,args.loader_test)
