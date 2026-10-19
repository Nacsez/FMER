#!/usr/bin/env python3
"""Build and inspect an FM-1 board candidate ELF; never package, flash or open USB."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import uuid

try:
    from . import target_probe as probe
except ImportError:
    import target_probe as probe

ROOT = Path(__file__).resolve().parents[1]
WIRE_IDENTITY = "FM-1_734"
DSP_OPTIMIZED_SOURCES = frozenset(("core/synth.cpp", "core/effects.cpp", "core/performance.cpp", "core/multitrack.cpp", "firmware/fm1/dsp_adapter.cpp"))


def local_source_files() -> list[Path]:
    """Enumerate portable core sources, including original factory presets."""
    return ([ROOT / "firmware/fm1/board.c", ROOT / "firmware/fm1/runtime.cpp", ROOT / "firmware/fm1/dsp_adapter.cpp"] +
            sorted((ROOT / "core").glob("*.cpp")) + sorted((ROOT / "third_party/msfa/src").glob("*.cc")))


def local_header_files() -> list[Path]:
    """Pin native-state, preset and adapter headers alongside compiled sources."""
    return [p for folder in [ROOT / "core", ROOT / "firmware/fm1", ROOT / "third_party/msfa/src"] for p in sorted(folder.glob("*.h*"))]


def optimization_for_source(relative: str) -> str:
    # No fast-math: preserve the tested floating-point semantics. Space-bounded
    # ELF inspection still applies after these hot paths are optimized for speed.
    return "-O2" if relative in DSP_OPTIMIZED_SOURCES or relative.startswith("third_party/msfa/src/") and relative.endswith(".cc") else "-Oz"
FELUCCA = ROOT / "third_party/acquired/fm1-target-review/community/felucca/source"
FELUCCA_COMMIT = "20c275e39f75fa820978032efaceddfc5283c8cb"
TREE_SHA256 = "8f0acb8cb2fe04db3b54b8087cca1d63815fcc43b30c2b933d03923f62f06147"
USB_SHA256 = "ea2b55ade91cbb0e3d5f9a9fbc290349cb5e66dbf9b552065450345eb0ae6705"
XIP = (0x02000120, 0x02000120 + 0x8DFBC)
REGIONS = {".text": XIP, ".ram_text": (0x01C00000, 0x01C06000),
           ".data": (0x01C08000, 0x01C20000), ".bss": (0x01C08000, 0x01C20000),
           ".pool": (0x01C20000, 0x01C68000), ".workspace": (0x01C68000, 0x01C74000), ".noinit": (0x01C7C000, 0x01C7FD50)}


def verify_upstream(source: Path) -> list[dict]:
    tree_path = source.parent / "tree.json"
    if probe.sha256(tree_path) != TREE_SHA256:
        raise ValueError("Felucca source-tree metadata differs from the reviewed pin")
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    entries = {item["path"]: item for item in tree["tree"] if item["type"] == "blob"}
    selected = ["firmware/crt0.S", "firmware/app.ld", "firmware/hal/fm1_isr.S",
                "firmware/hal/fm1_vec.S", "firmware/src/lcd.c", "firmware/src/usb.c",
                "firmware/src/ota.c", "firmware/src/midi_uart.c"]
    selected += sorted(name for name in entries if name.startswith("firmware/hal/") and name.endswith(".h"))
    records = []
    for name in selected:
        path = source / name
        data = path.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
        if blob != entries[name]["sha"]:
            raise ValueError(f"Upstream Git blob mismatch: {name}")
        records.append({"path": name, "git_blob_sha1": blob,
                        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    return records


def usb_descriptor(text: str) -> str:
    data = text.encode("utf-16-le")
    if len(data) + 2 > 255:
        raise ValueError("USB string descriptor exceeds its byte length field")
    return "{" + ", ".join(str(n) for n in bytes([len(data) + 2, 3]) + data) + "}"


def brand_usb(original: bytes, product: str = "FMER Test01") -> bytes:
    if product not in ("FMER Test01", "FMER Citrine", "FMER"):
        raise ValueError("Unreviewed USB product name")
    if hashlib.sha256(original).hexdigest() != USB_SHA256:
        raise ValueError("Refusing USB branding patch on an unreviewed source")
    text = original.decode("utf-8")
    text, count = re.subn(r"static const uint8_t STR1\[\] = \{[^}]+\};",
                          "static const uint8_t STR1[] = " + usb_descriptor("FMER") + ";", text)
    if count != 1:
        raise ValueError("Expected exactly one manufacturer USB string")
    old = "static const uint8_t STR2[] = {16, 3, 'F', 0, 'e', 0, 'l', 0, 'u', 0, 'c', 0, 'c', 0, 'a', 0};"
    if text.count(old) != 1:
        raise ValueError("Expected exactly one application product USB string")
    text=text.replace(old, "static const uint8_t STR2[] = " + usb_descriptor(product) + ";")
    guard='    if (cin == 0xFu && (st == 0xF8u || st == 0xFAu || st == 0xFBu || st == 0xFCu)) {'
    if text.count(guard)!=1:raise ValueError('USB MIDI realtime patch anchor differs')
    text=text.replace(guard,'''    if (cin == 3u && st == 0xF2u && !(pkt & 0x80800000u)) { midi_enqueue(pkt,1u); return; }
    if (cin == 0xFu && (st == 0xF8u || st == 0xFAu || st == 0xFBu || st == 0xFCu || st == 0xFEu || st == 0xFFu)) {''')
    return text.encode('utf8')



def patch_input(original: bytes) -> bytes:
    if hashlib.sha256(original).hexdigest() != 'b1b6325a72d3a6e7c9aa02c56860417786befde23ab1556ccad87c38ffc5a705':
        raise ValueError('Unreviewed input HAL')
    text=original.decode('utf8')
    start=text.index('static void fm1__frame(void)\n{')
    end=text.index('/* one column per call',start)
    frame='''/* FMER718: replace SOFT2 with per-frame quadrature accumulation.
 * Hardware matrix, key debounce and LED timing remain upstream code. */
#include "encoder_model.h"
static void fm1__frame(void)
{
    uint32_t e;
    for(e=0;e<FM1_NENC;e++) {
        const uint8_t *m=FM1_ENC[e];
        uint32_t cur=((fm1_in.raw[m[0]]>>m[1])&1u)*2u|((fm1_in.raw[m[2]]>>m[3])&1u);
        int32_t delta=fmer_encoder_sample(cur,&fm1_in.enc_prev[e],&fm1_in.enc_rest[e],
            &fm1_in.enc_still[e],&fm1_in.enc_sub[e],&fm1_in_stat.enc_moves[e],&fm1_in_stat.enc_lost[e]);
        int32_t sum=(int32_t)fm1_in.enc_steps[e]+delta;
        fm1_in.enc_steps[e]=(int16_t)(sum>32767?32767:sum< -32767?-32767:sum);
    }
    fm1_in.frames++;
}

'''
    text=text[:start]+frame+text[end:]
    text=text.replace('static uint8_t fm1__tick_col,', '#include "led_pwm.h"\nstatic uint8_t fm1_led_half[FM1_NCOL],fm1_led_phase;\nstatic uint8_t fm1__tick_col,')
    text=text.replace('lit = fm1_led[p],', 'lit = fmer_led_scan_mask(fm1_led[p],fm1_led_half[p],fm1_led_phase),')
    text=text.replace('fm1__led_lines(fm1_led[n]);', 'if(n==0u)fm1_led_phase^=1u;\n    fm1__led_lines(fmer_led_scan_mask(fm1_led[n],fm1_led_half[n],fm1_led_phase));')
    return text.encode('utf8')


def patch_uart(original: bytes) -> bytes:
    if hashlib.sha256(original).hexdigest() != "459cf47e648a91523713b27886448d8992ab8629288c76f6e5d317be54c4435f":raise ValueError("Unreviewed UART source")
    text=original.decode('utf8')
    replacements={
        'b == 0xFBu || b == 0xFCu':'b == 0xFBu || b == 0xFCu || b == 0xFEu || b == 0xFFu',
        'b < 0xF0u ? (uint8_t)b : 0':'(b < 0xF0u || b == 0xF2u) ? (uint8_t)b : 0',
        '(um.st >> 4) | (uint32_t)um.st << 8':'(um.st == 0xF2u ? 3u : um.st >> 4) | (uint32_t)um.st << 8',
        '        um.got = 0;\n        if (midi_enqueue(pkt, 2u))':'        um.got = 0;\n        if(um.st == 0xF2u)um.st=0;\n        if (midi_enqueue(pkt, 2u))'}
    for old,new in replacements.items():
        if text.count(old)!=1:raise ValueError('UART MIDI patch anchor differs')
        text=text.replace(old,new)
    return text.encode('utf8')

def validate_regions(sections: list[dict], entry: int) -> None:
    if entry != XIP[0]:
        raise ValueError("Board entry is not the first SPL application byte")
    occupied = []
    loaded = []
    for section in sections:
        if not section["size"]:
            continue
        if section["name"] not in REGIONS:
            raise ValueError(f"Unexpected allocated section: {section['name']}")
        lo, hi = REGIONS[section["name"]]
        start, end = section["address"], section["address"] + section["size"]
        if start < lo or end > hi:
            raise ValueError(f"Section exceeds reviewed memory region: {section['name']}")
        for other_start, other_end in occupied:
            if start < other_end and other_start < end:
                raise ValueError("Allocated sections overlap")
        occupied.append((start, end))
        if section.get("load_address") is not None:
            load = section["load_address"]
            if load < XIP[0] or load + section["size"] > XIP[1]:
                raise ValueError("File-backed section load address exceeds application XIP")
            if load % 4:
                raise ValueError("Startup load address is not word aligned")
            for other_start, other_end in loaded:
                if load < other_end and other_start < load + section["size"]:
                    raise ValueError("File-backed section load ranges overlap")
            loaded.append((load, load + section["size"]))


def inspect_elf(data: bytes) -> dict:
    identity = probe.elf_identity(data, 2)
    phoff, shoff = struct.unpack_from("<II", data, 28)
    phsize, phnum, shsize, shnum, shstr = struct.unpack_from("<HHHHH", data, 42)
    if shsize != 40 or shnum == 0 or shstr >= shnum or shoff + shsize * shnum > len(data):
        raise ValueError("Invalid or truncated ELF section table")
    sections = [struct.unpack_from("<10I", data, shoff + i * shsize) for i in range(shnum)]
    strings = sections[shstr]
    names = data[strings[4]:strings[4] + strings[5]]

    def name_at(table: bytes, offset: int) -> str:
        if offset >= len(table) or b"\0" not in table[offset:]:
            raise ValueError("Invalid ELF string table offset")
        return table[offset:table.index(b"\0", offset)].decode("ascii")

    if phnum and (phsize != 32 or phoff + phsize * phnum > len(data)):
        raise ValueError("Invalid or truncated ELF program table")
    programs = [struct.unpack_from("<8I", data, phoff + i * phsize) for i in range(phnum)]
    allocated = []
    symbols = {}
    for section in sections:
        name = name_at(names, section[0])
        if section[1] != 8 and section[4] + section[5] > len(data):
            raise ValueError("Truncated ELF section contents")
        if section[2] & 2:
            item = {"name": name, "address": section[3], "size": section[5],
                    "type": section[1], "file_offset": section[4], "load_address": None}
            if section[1] != 8 and section[5]:
                for program in programs:
                    if program[0] == 1 and section[4] >= program[1] and section[4] + section[5] <= program[1] + program[4]:
                        item["load_address"] = program[3] + section[4] - program[1]
                        break
                if item["load_address"] is None:
                    raise ValueError("Allocated file-backed section has no load segment")
            allocated.append(item)
        if section[1] == 2:
            if section[6] >= len(sections) or section[9] != 16 or section[5] % 16:
                raise ValueError("Invalid ELF symbol table")
            table_section = sections[section[6]]
            table = data[table_section[4]:table_section[4] + table_section[5]]
            for offset in range(section[4], section[4] + section[5], 16):
                symbol_name, value, _, _, _, _ = struct.unpack_from("<IIIBBH", data, offset)
                if symbol_name:
                    symbols[name_at(table, symbol_name)] = value
    validate_regions(allocated, identity["entry"])
    needed = ["_start", "_rt_load", "_rt_start", "_rt_end", "_data_load", "_data_start",
              "_data_end", "_bss_start", "_bss_end", "_pool_start", "_pool_end",
              "_workspace_start", "_workspace_end", "_guard0", "_guard1", "_ustack_top", "_sstack_top"]
    if any(name not in symbols for name in needed):
        raise ValueError("Missing required board startup/memory symbols")
    if symbols["_start"] != XIP[0] or symbols["_guard0"] != 0x01C74000:
        raise ValueError("Unexpected board startup or stack protection address")
    workspace = next((s for s in allocated if s['name']=='.workspace'),None)
    if (not workspace or workspace['type'] != 8 or workspace.get('load_address') is not None or
            symbols['_workspace_start'] != workspace['address'] or
            symbols['_workspace_end'] != workspace['address']+workspace['size'] or
            symbols['_workspace_start'] < symbols['_pool_end'] or symbols['_workspace_end'] > symbols['_guard0'] or
            symbols['_workspace_start']%16 or symbols['_workspace_end']%16):
        raise ValueError('Workspace must be aligned NOLOAD RAM between arena and stack guard')
    return {**identity, "sections": allocated, "startup_symbols": {name: symbols[name] for name in needed}}


def build_candidate(toolchain: Path, libcxx: Path, upstream: Path, output: Path, usb_product: str = "FMER Test01", runtime: str = "source") -> dict:
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": 1, "kind": "fm1_board_build_candidate", "success": False,
              "release": False, "packaged": False, "flashable": False,
              "device_opened": False, "device_writes": False, "target_executed": False,
              "created_utc": datetime.now(timezone.utc).isoformat(), "commands": [],
              "sources": [], "objects": [], "upstream_commit": FELUCCA_COMMIT,
              "build_script_sha256": probe.sha256(Path(__file__)),
              "wire_identity": WIRE_IDENTITY, "usb_manufacturer": "FMER", "usb_product": usb_product}
    try:
        lock = json.loads(probe.LOCK.read_text(encoding="utf-8"))
        report["toolchain_lock_sha256"] = probe.sha256(probe.LOCK)
        # Source builds need the compiler/headers, never the vendor archives.
        tool_files=[item for item in lock['toolchain']['files']
                    if runtime != 'source' or not item['path'].endswith('.a')]
        probe.verify_files(toolchain, tool_files)
        probe.verify_files(libcxx, lock["libcxx"]["files"])
        msfa_lock = json.loads((ROOT / "evidence/msfa-source.json").read_text(encoding="utf-8"))
        report["msfa_lock_sha256"] = probe.sha256(ROOT / "evidence/msfa-source.json")
        probe.verify_files(ROOT / "third_party/msfa", [{"path": f["path"], "sha256": f["local_sha256"]} for f in msfa_lock["files"]])
        report["verified_upstream"] = verify_upstream(upstream)
        staged = output / "vendor"
        (staged / "src").mkdir(parents=True)
        (staged / "hal").mkdir()
        for item in report["verified_upstream"]:
            if item["path"].startswith("firmware/hal/") and item["path"].endswith(".h"):
                (staged / "hal" / Path(item["path"]).name).write_bytes((upstream / item["path"]).read_bytes())
        input_path=staged/'hal/fm1_input.h';input_original=input_path.read_bytes()
        input_changed=patch_input(input_original);input_path.write_bytes(input_changed)
        (output/'input-decoder.patch').write_text(''.join(difflib.unified_diff(input_original.decode('utf8').splitlines(keepends=True),input_changed.decode('utf8').splitlines(keepends=True),fromfile='upstream/firmware/hal/fm1_input.h',tofile='generated/vendor/hal/fm1_input.h')),encoding='utf8')
        report['input_patch']={'original_sha256':hashlib.sha256(input_original).hexdigest(),'generated_sha256':probe.sha256(input_path),'patch':'input-decoder.patch'}
        usb_original = (upstream / "firmware/src/usb.c").read_bytes()
        usb_changed = brand_usb(usb_original, usb_product)
        usb_path = staged / "src/usb.c"
        usb_path.write_bytes(usb_changed)
        (output / "usb-branding.patch").write_text("".join(difflib.unified_diff(
            usb_original.decode("utf-8").splitlines(keepends=True), usb_changed.decode("utf-8").splitlines(keepends=True),
            fromfile="upstream/firmware/src/usb.c", tofile="generated/vendor/src/usb.c")), encoding="utf-8")
        report["usb_patch"] = {"original_sha256": hashlib.sha256(usb_original).hexdigest(),
                               "generated_sha256": probe.sha256(usb_path), "patch": "usb-branding.patch"}

        uart_original=(upstream/"firmware/src/midi_uart.c").read_bytes()
        uart_changed=patch_uart(uart_original);uart_path=staged/"src/midi_uart.c";uart_path.write_bytes(uart_changed)
        (output/"uart-midi.patch").write_text("".join(difflib.unified_diff(uart_original.decode("utf8").splitlines(keepends=True),uart_changed.decode("utf8").splitlines(keepends=True),fromfile="upstream/firmware/src/midi_uart.c",tofile="generated/vendor/src/midi_uart.c")),encoding="utf8")
        report["uart_patch"]={"original_sha256":hashlib.sha256(uart_original).hexdigest(),"generated_sha256":probe.sha256(uart_path),"patch":"uart-midi.patch"}

        def checked(name: str, command: list[str]) -> dict:
            result = probe.run_logged(command, output / f"{name}.json")
            report["commands"].append({"log": f"{name}.json", "exit_code": result["exit_code"]})
            if result["exit_code"] != 0:
                raise RuntimeError(f"{name} failed; inspect {name}.json")
            return result

        compiler = str(toolchain / "bin/clang.exe")
        checked("compiler-version", [compiler, "--version"])
        common = [compiler, "-target", "pi32v2", "-mcpu=r3", "-Oz", "-fno-common",
                  "-ffunction-sections", "-fdata-sections", "-fno-builtin", "-D__GCC_PI32V2__",
                  "-DFMER_DEVICE", "-D_XOPEN_SOURCE=700", "-resource-dir", str(toolchain / "lib/clang/4.0.1")]
        cxx = ["-std=c++1z", "-fno-rtti", "-fno-threadsafe-statics", "-nostdinc++",
               "-D_LIBCPP_HAS_NO_THREADS", "-D_LIBCPP_HAS_NO_MONOTONIC_CLOCK", "-isystem", str(libcxx / "include")]
        includes = ["-isystem", str(toolchain / "pi32v2-include")]
        for directory in [ROOT / "core", ROOT / "third_party/msfa/src", ROOT / "firmware/fm1",
                          staged / "hal", upstream / "firmware/src"]:
            includes += ["-I", str(directory)]
        source_files = [(upstream / p, p) for p in ["firmware/crt0.S", "firmware/hal/fm1_isr.S", "firmware/hal/fm1_vec.S"]]
        own_sources = local_source_files()
        source_files += [(p, p.relative_to(ROOT).as_posix()) for p in own_sources]
        objects = []
        for source, relative in source_files:
            name = relative.replace("/", "__")
            obj = output / (name + ".o")
            optimization = optimization_for_source(relative)
            report["sources"].append({"path": relative, "sha256": probe.sha256(source), "optimization": optimization})
            flags = [] if source.suffix == ".S" else (["-std=gnu11"] if source.suffix == ".c" else cxx + [
                "-fexceptions" if relative == "core/patch.cpp" else "-fno-exceptions"])
            if relative == "firmware/fm1/board.c":
                flags += ['-DFELUCCA_ID="' + WIRE_IDENTITY + '"', "-DFELUCCA_UAC=1", "-DFELUCCA_CDC=0", "-DFELUCCA_OTA=1",
                          '-DFMER_USB_SOURCE="' + usb_path.as_posix() + '"', '-DFMER_UART_SOURCE="' + uart_path.as_posix() + '"']
            checked(name, common + [optimization] + flags + includes + ["-c", str(source), "-o", str(obj)])
            report["objects"].append({"path": obj.name, "sha256": probe.sha256(obj), **probe.elf_identity(obj.read_bytes(), 1)})
            objects.append(str(obj))
        report["local_headers"] = [{"path": p.relative_to(ROOT).as_posix(), "sha256": probe.sha256(p)}
                                    for p in local_header_files()]
        elf = output / "fm1.elf"
        script = ROOT / "firmware/fm1/app.ld"
        report["linker_script_sha256"] = probe.sha256(script)
        if runtime == 'source':
            import source_runtime
            report['runtime'] = source_runtime.build(toolchain, output / 'runtime', checked)
            runtime_path = output / 'runtime'
        elif runtime == 'vendor-reference':
            runtime_path = toolchain / 'pi32v2-lib/r3'
            report['runtime'] = {'kind': runtime, 'distribution_review': 'unresolved'}
        else:
            raise ValueError('Unknown runtime selection')
        checked("link", [str(toolchain / "bin/pi32v2-ld.exe"), "-m", "elf32pi32v2", "--gc-sections",
                "-T", str(script), "-Map", str(output / "fm1.map"), "-o", str(elf)] + objects +
                ["-L", str(runtime_path), "--start-group", "-lc", "-lm", "-lcompiler-rt", "--end-group"])
        undefined = checked("undefined-symbols", [str(toolchain / "bin/llvm-nm.exe"), "--undefined-only", str(elf)])
        if undefined["stdout"].strip():
            raise ValueError("Board ELF has unresolved symbols")
        checked("elf-details", [str(toolchain / "bin/llvm-readobj.exe"), "--file-headers", "--sections", "--program-headers", str(elf)])
        disassembly = checked("disassembly", [str(toolchain / "bin/llvm-objdump.exe"), "-d", str(elf)])
        (output / "disassembly.txt").write_text(disassembly["stdout"], encoding="utf-8")
        report["elf"] = {"path": elf.name, "sha256": probe.sha256(elf), **inspect_elf(elf.read_bytes())}
        report["success"] = True
    except (OSError, ValueError, RuntimeError, KeyError, struct.error) as error:
        report["error"] = str(error)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain-root", type=Path)
    parser.add_argument("--libcxx-root", type=Path)
    parser.add_argument("--upstream-root", type=Path, default=FELUCCA)
    parser.add_argument("--out", type=Path)
    parser.add_argument('--runtime', choices=('vendor-reference', 'source'), default='source',
                        help='source uses reviewed source-built libraries; candidate only, requires target qualification')
    parser.add_argument("--usb-product", choices=("FMER Test01", "FMER Citrine", "FMER"), default="FMER Test01")
    args = parser.parse_args(argv)
    lock = json.loads(probe.LOCK.read_text(encoding="utf-8"))
    toolchain = (args.toolchain_root or ROOT / lock["toolchain"]["local_root"]).resolve()
    libcxx = (args.libcxx_root or ROOT / lock["libcxx"]["local_root"]).resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    output = (args.out or ROOT / "artifacts/fm1-candidate" / stamp).resolve()
    try:
        report = build_candidate(toolchain, libcxx, args.upstream_root.resolve(), output, args.usb_product, args.runtime)
    except OSError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({"success": report["success"], "report": str(output / "report.json"), "error": report.get("error")}))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
