"""Pure, bounded WL82 UBOOT1.00 bootstrap and LoaderV2 flash reader.

This module never opens a device. The injected transport must bind one exact
OS device handle, admit its INQUIRY, and enforce SCSI status/sense/byte counts.
Only a pinned vendor bootstrap can be uploaded to its fixed RAM interval.
There are no flash erase/write, key-write, reset, or arbitrary-command APIs.

Protocol references (read as source, not executed):
  kagaimiq/jl-uboot-tool @ adb3f18889e88ac512ce0a3c4d8cc3d3cb30696a
    jltech/{uboot,cipher,crc}.py and docs/usb-loader-v2.md
  kurogedelic/FM-1-transporter @ a632d923203170e3a08565f4056dbb3fd3d65ca5
    src/jieli_uboot.c and docs/PROTOCOL.md
The RAM loader is opaque vendor code; its source/redistribution rights remain
unestablished. Its presence in an MIT source repository does not resolve that.
Keep the acquired binary and device dumps in ignored private directories.
Host commands do not erase/program flash arrays. Opaque bootstrap startup may
configure NOR status/quad-mode registers; absence of those side effects is not
established by this allowlist or by successful offline protocol tests.

Protocol/cipher source attribution: Copyright (c) 2023 Andrey Grigoryev
(kagaimiq); Copyright (c) 2026 kurogedelic. MIT License: Permission is hereby
granted, free of charge, to any
person obtaining a copy of this software and associated documentation files
(the "Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom
the Software is furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED
"AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE
AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""
from __future__ import annotations

import binascii
import hashlib
import time
from typing import Callable

BLOCK_SIZE = 512
FLASH_SIZE = 0x100000
RAM_BASE = 0x01C02000
BOOTSTRAP_SIZE = 24064
BOOTSTRAP_SHA256 = "d41da6126760c9d66660bcc0cac8d27d221806c5e369a8036921efe68dca5376"
BOOTSTRAP_GIT_BLOB = "3b47cffaf7bd87f27163ca7bf0c7deb0c783ac87"
BOOTSTRAP_COMMIT = "adb3f18889e88ac512ce0a3c4d8cc3d3cb30696a"
BOOTSTRAP_URL = (
    "https://raw.githubusercontent.com/kagaimiq/jl-uboot-tool/"
    + BOOTSTRAP_COMMIT + "/data/loaderblobs/usb/wl82loader.bin")
EXPECTED_CHIP_KEY = 0x980F
EXPECTED_DEVICE_TYPE = 3
EXPECTED_FLASH_ID = 0x856014
INQUIRY_CDB = bytes.fromhex("120000002400")
_MAGIC = bytes.fromhex("c3cfc0e8ced2b0aec4e3a3acd3f1c1d6")
_EXPECTED_INQUIRY = {"vendor": "WL82", "product": "UBOOT1.00", "revision": "1.00"}


class RomProtocolError(ValueError):
    """Malformed, unsupported, or uncertain protocol state; stop this session."""


def crc16(data: bytes, initial: int = 0) -> int:
    """CRC-16/XMODEM (poly1021, no reflection); ROM writes use initial zero."""
    return binascii.crc_hqx(data, initial)


def crc_cipher(data: bytes) -> bytes:
    """Per-transfer WL82 RAM XOR cipher with fixed key FFFFFFFF.

    Reset for every 512-byte transfer. Applying it twice restores the input.
    LoaderV2 raw flash reads do not use this cipher.
    """
    crc = crc16(b"\xff\xff", 0xFFFF)
    out = bytearray(len(data))
    for index, value in enumerate(data):
        crc = crc16(_MAGIC[index % 16:index % 16 + 1], crc)
        out[index] = value ^ (crc & 255)
    return bytes(out)


def validate_bootstrap(blob: bytes) -> dict:
    """Validate both immutable source hashes before any RAM transfer."""
    if type(blob) is not bytes or len(blob) != BOOTSTRAP_SIZE:
        raise RomProtocolError(f"Bootstrap must be exactly {BOOTSTRAP_SIZE} immutable bytes")
    sha = hashlib.sha256(blob).hexdigest()
    git_sha = hashlib.sha1(b"blob " + str(len(blob)).encode("ascii") + b"\0" + blob).hexdigest()
    if sha != BOOTSTRAP_SHA256 or git_sha != BOOTSTRAP_GIT_BLOB:
        raise RomProtocolError(f"Bootstrap hash mismatch: sha256={sha}, git_blob={git_sha}")
    plaintext = b"".join(crc_cipher(blob[off:off + BLOCK_SIZE])
                         for off in range(0, len(blob), BLOCK_SIZE))
    return {"bytes": len(blob), "sha256": sha, "git_blob_sha1": git_sha,
            "commit": BOOTSTRAP_COMMIT, "ram_base": RAM_BASE,
            "decoded_ram_sha256": hashlib.sha256(plaintext).hexdigest(),
            "blocks": len(blob) // BLOCK_SIZE}


def parse_inquiry(data: bytes) -> dict:
    """Accept only the documented WL82 ROM identity, never a generic disk."""
    if type(data) is not bytes or len(data) != 36:
        raise RomProtocolError("INQUIRY must return exactly 36 bytes")
    try:
        info = {"vendor": data[8:16].decode("ascii").strip(" "),
                "product": data[16:32].decode("ascii").strip(" "),
                "revision": data[32:36].decode("ascii").strip(" ")}
    except UnicodeDecodeError as exc:
        raise RomProtocolError("Non-ASCII INQUIRY identity") from exc
    if info != _EXPECTED_INQUIRY:
        raise RomProtocolError(f"Unsupported ROM INQUIRY identity: {info!r}")
    return {**info, "raw_hex": data.hex()}


def _cdb(command: int, args: bytes = b"") -> bytes:
    return (command.to_bytes(2, "big") + args).ljust(16, b"\xff")


def _block_range(address: int, length: int, start: int, end: int) -> None:
    if (type(address) is not int or type(length) is not int
            or length != BLOCK_SIZE or address % BLOCK_SIZE
            or address < start or address > end - length):
        raise RomProtocolError(f"Unsupported block range {address!r}+{length!r}; expected aligned 512 bytes in [{start:#x},{end:#x})")


def validate_transfer(cdb: bytes, data_out: bytes | None = None, data_in: int = 0) -> str:
    """Stateless defense for the OS transport; reject every unlisted CDB.

    This checks framing/bounds/direction/CRC. The reader adds state, exact blob
    hashes and readback proof. The transport must enforce same-handle INQUIRY
    admission as well; this function alone is not an identity or state proof.
    """
    if type(cdb) is not bytes or type(data_in) is not int or data_in < 0:
        raise RomProtocolError("Invalid immutable CDB or input byte count")
    if data_out is not None and type(data_out) is not bytes:
        raise RomProtocolError("Output transfer must be immutable bytes")
    if cdb == INQUIRY_CDB:
        if data_out is not None or data_in != 36:
            raise RomProtocolError("INQUIRY direction/length mismatch")
        return "inquiry"
    if len(cdb) != 16:
        raise RomProtocolError("Vendor CDB must be exactly 16 bytes")
    command = int.from_bytes(cdb[:2], "big")
    if command in (0xFB06, 0xFD07, 0xFD05):
        address = int.from_bytes(cdb[2:6], "big")
        length = int.from_bytes(cdb[6:8], "big")
        if command == 0xFD05:
            _block_range(address, length, 0, FLASH_SIZE)
        else:
            _block_range(address, length, RAM_BASE, RAM_BASE + BOOTSTRAP_SIZE)
        if command == 0xFB06:
            if (data_out is None or len(data_out) != length or data_in != 0
                    or cdb[8] != 0 or cdb[11:] != b"\xff" * 5
                    or int.from_bytes(cdb[9:11], "little") != crc16(data_out)):
                raise RomProtocolError("RAM write framing, length or CRC mismatch")
            return "write_ram"
        if data_out is not None or data_in != length or cdb[8:] != b"\xff" * 8:
            raise RomProtocolError("Read framing/direction/length mismatch")
        return "read_ram" if command == 0xFD07 else "read_flash"
    if data_out is not None or data_in != 16:
        raise RomProtocolError("Command reply must be a 16-byte input transfer")
    if command == 0xFB08 and cdb == _cdb(0xFB08, RAM_BASE.to_bytes(4, "big") + b"\x00\x01"):
        return "jump_ram"
    if command == 0xFC09 and cdb == _cdb(0xFC09, bytes.fromhex("00ac6900")):
        return "read_key"
    if command == 0xFC0A and cdb == _cdb(0xFC0A):
        return "online_device"
    raise RomProtocolError(f"CDB {cdb.hex()} is outside the read-only-flash allowlist")


def verify_matching_dumps(first: bytes, second: bytes) -> dict:
    """Require two complete equal raw reads, not just matching short prefixes."""
    if (type(first) is not bytes or type(second) is not bytes
            or len(first) != FLASH_SIZE or len(second) != FLASH_SIZE):
        raise RomProtocolError("Both flash dumps must contain exactly 1 MiB")
    if first != second:
        offset = next(i for i, (a, b) in enumerate(zip(first, second)) if a != b)
        raise RomProtocolError(f"Independent flash reads differ at offset {offset:#x}")
    digest = hashlib.sha256(first).hexdigest()
    return {"bytes": FLASH_SIZE, "sha256": digest, "first_sha256": digest,
            "second_sha256": digest, "byte_equal": True}


class RomReader:
    """One-shot stateful bootstrap/read session over a separately scoped handle.

    Progress callbacks receive metadata and must return promptly. The vendor
    loader reportedly resets after approximately three seconds without a
    command. Continuous 512-byte reads need no extra keepalive; callers doing
    other work should call keepalive at least once a second. No background
    threads or implicit retries obscure command ordering or failed transfers.
    """
    def __init__(self, execute: Callable, progress: Callable[[dict], None] | None = None):
        self._execute = execute
        self._progress = progress
        self._state = "new"
        self._sequence = 0
        self._identity: dict | None = None
        self._loader_info: dict | None = None

    @property
    def state(self) -> str:
        return self._state

    def _notify(self, event: str, **fields) -> None:
        if self._progress is not None:
            self._progress({"event": event, "state": self._state,
                            "sequence": self._sequence, **fields})

    def _require(self, state: str) -> None:
        if self._state != state:
            raise RomProtocolError(f"Operation requires {state} state; current state is {self._state}")

    def _exchange(self, cdb: bytes, *, data_out: bytes | None = None, data_in: int = 0) -> bytes:
        operation = validate_transfer(cdb, data_out, data_in)
        self._sequence += 1
        started = time.monotonic()
        try:
            self._notify("command_start", operation=operation, cdb_hex=cdb.hex(),
                         data_out_bytes=len(data_out) if data_out is not None else 0,
                         data_in_bytes=data_in)
            result = self._execute(cdb, data_out=data_out, data_in=data_in)
            if type(result) is not bytes or len(result) != data_in:
                raise RomProtocolError(f"{operation}: transport returned an unexpected byte count/type")
            self._notify("command_complete", operation=operation,
                         elapsed_ms=round((time.monotonic() - started) * 1000, 3),
                         input_sha256=hashlib.sha256(result).hexdigest() if data_in else None)
            return result
        except Exception:
            self._state = "failed"
            raise

    def _reply(self, command: int, args: bytes = b"") -> bytes:
        reply = self._exchange(_cdb(command, args), data_in=16)
        if int.from_bytes(reply[:2], "big") != command:
            self._state = "failed"
            raise RomProtocolError(f"Reply command mismatch for {command:04X}: {reply.hex()}")
        return reply[2:]

    def inquiry(self) -> dict:
        self._require("new")
        try:
            self._identity = parse_inquiry(self._exchange(INQUIRY_CDB, data_in=36))
            self._state = "rom"
            self._notify("rom_admitted", identity=self._identity)
            return dict(self._identity)
        except Exception:
            self._state = "failed"
            raise

    def start_loader(self, blob: bytes) -> dict:
        """Upload the pinned pre-ciphered bytes; verify every byte before jump.

        ROM writes decipher wire bytes into RAM, and ROM reads cipher RAM onto
        the wire. Consequently a readback must equal the original pre-ciphered
        blob block. It is not plaintext. No extra cipher is applied on upload.
        """
        self._require("rom")
        try:
            pin = validate_bootstrap(blob)
            self._state = "uploading"
            self._notify("bootstrap_validated", **pin)
            for offset in range(0, BOOTSTRAP_SIZE, BLOCK_SIZE):
                block = blob[offset:offset + BLOCK_SIZE]
                args = ((RAM_BASE + offset).to_bytes(4, "big")
                        + BLOCK_SIZE.to_bytes(2, "big") + b"\0"
                        + crc16(block).to_bytes(2, "little"))
                self._exchange(_cdb(0xFB06, args), data_out=block)
            self._state = "verifying_ram"
            for offset in range(0, BOOTSTRAP_SIZE, BLOCK_SIZE):
                args = (RAM_BASE + offset).to_bytes(4, "big") + BLOCK_SIZE.to_bytes(2, "big")
                actual = self._exchange(_cdb(0xFD07, args), data_in=BLOCK_SIZE)
                if actual != blob[offset:offset + BLOCK_SIZE]:
                    raise RomProtocolError(f"ROM RAM readback mismatch at loader offset {offset:#x}; jump refused")
            self._notify("bootstrap_ram_verified", **pin)
            self._state = "starting_loader"
            self._reply(0xFB08, RAM_BASE.to_bytes(4, "big") + b"\x00\x01")
            key_reply = self._reply(0xFC09, bytes.fromhex("00ac6900"))
            key = int.from_bytes(crc_cipher(key_reply[4:6][::-1]), "little")
            if key != EXPECTED_CHIP_KEY:
                raise RomProtocolError(f"Unsupported chip key {key:#06x}; expected {EXPECTED_CHIP_KEY:#06x}")
            device = self._online_device()
            self._loader_info = {**device, "chip_key": key, "bootstrap": pin,
                                 "inquiry": dict(self._identity or {}),
                                 "flash_bytes": FLASH_SIZE, "read_block_bytes": BLOCK_SIZE,
                                 "ram_readback_verified": True}
            self._state = "loader"
            self._notify("loader_admitted", info=self._loader_info)
            return dict(self._loader_info)
        except Exception:
            self._state = "failed"
            raise

    def _online_device(self) -> dict:
        reply = self._reply(0xFC0A)
        device_type, flash_id = reply[0], int.from_bytes(reply[2:6], "little")
        if device_type != EXPECTED_DEVICE_TYPE or flash_id != EXPECTED_FLASH_ID:
            self._state = "failed"
            raise RomProtocolError(f"Unsupported flash device: type={device_type}, id={flash_id:#08x}")
        return {"device_type": device_type, "flash_id": flash_id}

    def keepalive(self) -> dict:
        self._require("loader")
        return self._online_device()

    def read_flash(self, offset: int, length: int = BLOCK_SIZE) -> bytes:
        """One aligned, fixed 512-byte raw read within the admitted 1 MiB map."""
        self._require("loader")
        _block_range(offset, length, 0, FLASH_SIZE)
        args = offset.to_bytes(4, "big") + length.to_bytes(2, "big")
        return self._exchange(_cdb(0xFD05, args), data_in=length)

    def read_full_flash(self, *, pass_number: int = 1, on_chunk: Callable | None = None) -> bytes:
        """Read the complete map in order; optionally persist each received block.

        on_chunk(pass_number, offset, bytes) must return promptly. A failing
        sink stops the session so callers cannot silently report a full dump.
        The method does not treat one pass as a verified backup.
        """
        self._require("loader")
        if type(pass_number) is not int or pass_number not in (1, 2):
            raise RomProtocolError("Dump pass number must be 1 or 2")
        result = bytearray(FLASH_SIZE)
        try:
            self._notify("dump_start", pass_number=pass_number, bytes=FLASH_SIZE)
            for offset in range(0, FLASH_SIZE, BLOCK_SIZE):
                block = self.read_flash(offset)
                result[offset:offset + BLOCK_SIZE] = block
                if on_chunk is not None:
                    on_chunk(pass_number, offset, block)
            output = bytes(result)
            self._notify("dump_complete", pass_number=pass_number, bytes=len(output),
                         sha256=hashlib.sha256(output).hexdigest())
            return output
        except Exception:
            self._state = "failed"
            raise
