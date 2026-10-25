# SPDX-License-Identifier: GPL-3.0-only
"""Development-only, passive V16 Bank Export receiver and file converter.

No MIDI/network/flash API is imported or opened here. A future adapter supplies
received bytes after explicit user action and owns endpoint identity/cleanup.
The bank number is a user declaration: standard DX7 bulk data has no bank ID.
Original bytes survive conversion; library/device writes are separate actions.
"""
import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import time

import companion_bank as bank
import companion_dx7 as dx7
import library

ROOT = Path(__file__).resolve().parents[1]
BANK_BYTES = 4104


def validate_bank(raw):
    if not isinstance(raw, bytes) or len(raw) != BANK_BYTES:
        raise ValueError('Expected one complete 32-voice DX7 bank (4104 bytes)')
    if raw[:2] != b'\xf0\x43' or not 0 <= raw[2] <= 15 or raw[3:6] != b'\x09\x20\x00' or raw[-1] != 0xf7:
        raise ValueError('Unsupported DX7 bank envelope')
    if any(x > 127 for x in raw[6:-1]) or (sum(raw[6:-1]) & 127):
        raise ValueError('Invalid DX7 payload or checksum')
    return raw


class BankCapture:
    """Bounded, sticky-failure assembly; no writes and no guessed dump request.

    Real-time messages can be interleaved. Ordinary notes/controllers outside
    SysEx are ignored. Wrong SysEx, truncation, overflow or two different banks
    abort the transaction. Duplicate identical banks do not duplicate imports.
    """
    def __init__(self, *, clock=time.monotonic, timeout=90):
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 300:
            raise ValueError('Capture timeout must be 0..300 seconds, exclusive of zero')
        self.clock = clock
        self.deadline = clock() + timeout
        self.buffer = bytearray()
        self.raw = None
        self.received = self.realtime = self.duplicates = 0
        self.error = None

    def _fail(self, message):
        self.error = message
        self.buffer.clear()
        self.raw = None
        raise ValueError(message)

    @property
    def complete(self):
        return self.raw is not None and not self.buffer and self.error is None

    def feed(self, chunk):
        if self.error:
            raise ValueError(self.error)
        if self.clock() >= self.deadline:
            self._fail('Bank Export timed out; no library changes were made')
        if not isinstance(chunk, bytes):
            self._fail('Expected received MIDI bytes')
        self.received += len(chunk)
        if self.received > 65536:
            self._fail('Capture byte budget exceeded')
        for value in chunk:
            if value >= 0xf8:
                self.realtime += 1
                continue
            if not self.buffer:
                if value == 0xf0:
                    self.buffer.append(value)
                continue
            if value == 0xf7:
                self.buffer.append(value)
                try:
                    raw = validate_bank(bytes(self.buffer))
                except ValueError as exc:
                    self._fail(str(exc))
                self.buffer.clear()
                if self.raw is not None:
                    if self.raw != raw:
                        self._fail('Two different banks received; capture each bank separately')
                    self.duplicates += 1
                else:
                    self.raw = raw
            elif value >= 0x80:
                self._fail('Unexpected status inside bank export')
            else:
                self.buffer.append(value)
                if len(self.buffer) >= BANK_BYTES:
                    self._fail('Bank export exceeds its declared size')

    def finish(self):
        if self.error:
            raise ValueError(self.error)
        if not self.complete:
            self._fail('No complete bank received; retry Bank Export without unplugging')
        return self.raw

    def cancel(self):
        self.buffer.clear()
        self.raw = None
        self.error = 'Capture cancelled; no library changes were made'

    def progress(self):
        phase = ('cancelled' if self.error.startswith('Capture cancelled') else 'failed') if self.error else ('review' if self.complete else 'receiving' if self.buffer else 'waiting')
        return dict(phase=phase,
                    bytes_in_bank=len(self.buffer) if not self.complete else BANK_BYTES,
                    expected_bytes=BANK_BYTES, complete=self.complete,
                    error=self.error, total_received=self.received,
                    realtime_messages=self.realtime, duplicate_banks=self.duplicates)


def make_archive(raw, declared_bank):
    validate_bank(raw)
    if type(declared_bank) is not int or not 1 <= declared_bank <= 4:
        raise ValueError('Declare source bank 1..4')
    body = dict(format='FMER-V16-DX7-CAPTURE', version=1,
                declared_bank=declared_bank, channel=raw[2]+1,
                provenance='Caller-supplied V16 Bank Export; firmware identity and bank number are not encoded in DX7 data',
                raw_base64=base64.b64encode(raw).decode('ascii'),
                source_sha256=hashlib.sha256(raw).hexdigest())
    return dict(payload=body, sha256=hashlib.sha256(library.canonical(body)).hexdigest())


def decode_archive(archive, template, codec):
    """Validate everything before returning a reviewable, unsaved catalog."""
    if not isinstance(archive, dict) or set(archive) != {'payload', 'sha256'}:
        raise ValueError('Invalid V16 capture archive')
    body = archive['payload']
    if not isinstance(body, dict):
        raise ValueError('Invalid capture payload')
    if hashlib.sha256(library.canonical(body)).hexdigest() != archive['sha256']:
        raise ValueError('Capture archive checksum mismatch')
    if body.get('format') != 'FMER-V16-DX7-CAPTURE' or body.get('version') != 1:
        raise ValueError('Unsupported capture archive')
    encoded = body.get('raw_base64')
    if not isinstance(encoded, str) or len(encoded) != 5472:
        raise ValueError('Invalid bank encoding length')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError('Invalid bank encoding') from exc
    expected = make_archive(raw, body.get('declared_bank'))
    if archive != expected:
        raise ValueError('Capture metadata does not match original bytes')
    decoded = dx7.decode(raw, template, codec)
    return dict(catalog=dx7.make_catalog(decoded, f'V16 imports - bank {body["declared_bank"]}'),
                count=decoded['count'], losses=decoded['losses'], source_sha256=decoded['source_sha256'],
                firmware_identity_verified=False, bank_number_verified=False,
                redistribution_license='Not determined by import', hardware_access=False,
                library_written=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('--bank', type=int, required=True)
    p.add_argument('--host', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'private'):
        p.error('Development captures must stay in ignored private/')
    if args.input.stat().st_size > 65536:
        p.error('Input exceeds the capture byte budget')
    receiver = BankCapture()
    receiver.feed(args.input.read_bytes())
    raw = receiver.finish()
    archive = make_archive(raw, args.bank)
    codec = library.PatchCodec(args.host, lambda *a, **k: None)
    template = bank.decode_record(bank.profile(args.host)[0]['native'])
    result = decode_archive(archive, template, codec)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'original.syx').write_bytes(raw)
    (args.output/'capture.json').write_bytes(library.canonical(archive))
    (args.output/'instruments.fmer-catalog.json').write_bytes(library.canonical(result['catalog']))
    result.pop('catalog')
    (args.output/'report.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
