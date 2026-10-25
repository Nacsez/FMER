"""Extract production native quiet handoff/main service for host execution.

No firmware is rewritten. The test includes these exact statements against the
real DSP adapter and fake board globals, so a mirror of intended behavior cannot
conceal ordering bugs in board.c. Refuse changed boundaries instead of silently
testing an empty or different region.
"""
from pathlib import Path
import argparse
import hashlib
import json
from extract_fm1_storage_board import block


def extract(source: str) -> str:
    return "\n".join(block(source, marker) for marker in (
        "static void mirror_controls(void)", "static void sync_audio_budget(void)", "static int native_import_conflict(void)",
        "static void native_import_service(void)", "void fm1_timer5_irq(void)"))


def extract_commit_guard(source: str) -> str:
    start_marker = "                if(controls_generation!=diag.controls_applied"
    if source.count(start_marker) != 1:
        raise ValueError("Expected one exact native commit publication guard")
    start = source.index(start_marker)
    end = source.index("result=FMER_NATIVE_STALE;", start) + len("result=FMER_NATIVE_STALE;")
    block = source[start:end]
    if "native_transfer.expected_generation!=native_live_generation" not in block:
        raise ValueError("Commit probe lacks the expected-generation publication guard")
    return block


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    raw = args.source.read_bytes()
    source = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    body = extract(source)
    overload = block(source, "        if (late || observed>2800u || fm1_audio_free_half()!=half) {")
    body += "\nstatic void production_overload(uint32_t late,uint32_t observed,uint32_t half) {\n" + overload + " else severe_streak=0;\n}\n"
    digest = hashlib.sha256(raw).hexdigest()
    generated = '#define FMER_NATIVE_BOARD_SOURCE_SHA256 "' + digest + '"\n' + body + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not args.output.exists() or args.output.read_text() != generated:
        args.output.write_text(generated, encoding="utf-8", newline="\n")
    manifest = dict(source=str(args.source.resolve()), source_sha256=digest,
                    generated_sha256=hashlib.sha256(generated.encode()).hexdigest(),
                    scope="Exact production native quiet handoff, main adoption and timer ownership deferral")
    args.output.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    guard = extract_commit_guard(source) + "\n"
    guard_path = args.output.with_name("fm1_native_commit_guard.inc")
    if not guard_path.exists() or guard_path.read_text() != guard:
        guard_path.write_text(guard, encoding="utf-8", newline="\n")
    pause = block(source, "        if(native_import_ready==1u) {") + "\n"
    if "fmer_dsp_set_native" in pause or "fmer_dsp_panic" in pause:
        raise ValueError("Native ISR admission must not restore or panic")
    args.output.with_name("fm1_native_pause.inc").write_text(pause, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
