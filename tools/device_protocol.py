"""Offline, bounded FM-1 identity and documented Baud preset reply codecs.

No OS imports, MIDI ports, device discovery, boot commands or transmit function.
Source/version and format boundaries are documented in docs/DEVICE_PROTOCOL.md.
An identity is self-reported text, never proof of image or board compatibility.
"""
from __future__ import annotations

import re


IDENTITY_QUERY = bytes.fromhex("F0 00 32 45 00 00 00 40 7F F7")
IDENTITY_REPLY_BYTES = 41
MAX_FRAME_BYTES = 4096


class ProtocolError(ValueError):
    """A complete frame does not meet its documented contract."""


def _bytes(data: bytes | bytearray | memoryview) -> bytes:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("Protocol data must be bytes, bytearray or memoryview")
    size = data.nbytes if isinstance(data, memoryview) else len(data)
    if size > MAX_FRAME_BYTES:
        raise ProtocolError("Protocol input exceeds the 4096-byte bound")
    return bytes(data)


def pack_seven_bit(data: bytes) -> bytes:
    """Continuous LSB-first packing, not a Yamaha high-bit-prefix group codec."""
    data = _bytes(data)
    if (len(data) * 8 + 6) // 7 > MAX_FRAME_BYTES:
        raise ProtocolError("Packed output would exceed the 4096-byte bound")
    result = bytearray()
    accumulator = count = 0
    for value in data:
        accumulator |= value << count
        count += 8
        while count >= 7:
            result.append(accumulator & 127)
            accumulator >>= 7
            count -= 7
    if count:
        result.append(accumulator)
    return bytes(result)


def unpack_seven_bit(data: bytes, expected_length: int | None = None) -> bytes:
    """Reject high wire bits, extra bytes and nonzero unused terminal bits."""
    data = _bytes(data)
    if expected_length is not None:
        if type(expected_length) is not int or not 0 <= expected_length <= MAX_FRAME_BYTES:
            raise ProtocolError("Invalid expected decoded length")
        if len(data) != (expected_length * 8 + 6) // 7:
            raise ProtocolError("Packed length does not match the decoded length")
    result = bytearray()
    accumulator = count = 0
    for value in data:
        if value > 127:
            raise ProtocolError("Non-seven-bit byte inside SysEx payload")
        accumulator |= value << count
        count += 7
        while count >= 8:
            result.append(accumulator & 255)
            accumulator >>= 8
            count -= 8
    if accumulator:
        raise ProtocolError("Nonzero padding in the packed stream")
    if expected_length is not None and len(result) != expected_length:
        raise ProtocolError("Unexpected decoded length")
    return bytes(result)


def _payload(frame: bytes) -> bytes:
    frame = _bytes(frame)
    if len(frame) < 3 or frame[0] != 0xF0 or frame[-1] != 0xF7:
        raise ProtocolError("Expected exactly one complete F0..F7 SysEx frame")
    if any(value > 127 for value in frame[1:-1]):
        raise ProtocolError("Non-seven-bit byte inside SysEx payload")
    return frame[1:-1]


def parse_identity_reply(frame: bytes, *, allow_bad_checksum: bool = False) -> dict:
    """Parse the documented 41-byte plain identity reply.

    Default checksum enforcement is strict. Diagnostic callers may retain a
    structurally valid custom-firmware identity with checksum_valid=False; that
    explicit result must not be promoted to verified image compatibility.
    """
    frame = _bytes(frame)
    if len(frame) != IDENTITY_REPLY_BYTES:
        raise ProtocolError("Identity reply must contain exactly 41 bytes")
    block = unpack_seven_bit(_payload(frame), 34)
    if block[:3] != b"\x00\x59\x11":
        raise ProtocolError("Unexpected identity block header")
    if int.from_bytes(block[3:6], "little") != 27:
        raise ProtocolError("Identity name field must declare 27 bytes")
    field = block[6:33]
    name, separator, padding = field.partition(b"\0")
    if not name or any(value < 32 or value > 126 for value in name):
        raise ProtocolError("Identity must contain nonempty printable ASCII")
    if separator and any(padding):
        raise ProtocolError("Identity name padding must be zero")
    expected = (~sum(field)) & 255
    checksum_valid = block[-1] == expected
    if not checksum_valid and not allow_bad_checksum:
        raise ProtocolError("Identity checksum mismatch")
    identity = name.decode("ascii")
    match = re.fullmatch(r"(FM-1|ota-FM-1)_([0-9]{3})", identity)
    return {
        "identity": identity,
        "model": match[1] if match else None,
        "version": int(match[2]) if match else None,
        "mode": ("update" if match[1].startswith("ota-") else "normal") if match else "unknown",
        "checksum_valid": checksum_valid,
        "checksum_received": block[-1],
        "checksum_expected": expected,
        "wire_bytes": len(frame),
        "encoding": "plain_ascii",
        "identity_source": "device_reported",
        "image_compatibility_verified": False,
    }


def parse_baud_preset_reply(frame: bytes, *, expected_slot: int) -> dict:
    """Decode an existing Baud >=079 preset reply; never generate a request.

    The opaque record remains 59 bytes. This does not recognize stock replies,
    convert VA bytes to DX7, interpret future record versions, or prove a full
    device backup. Preserve original frames alongside extracted bytes.
    """
    if type(expected_slot) is not int or not 0 <= expected_slot <= 127:
        raise ProtocolError("Expected preset slot must be 0..127")
    wire = _payload(frame)
    block = unpack_seven_bit(wire)
    if len(block) < 10 or block[0] != 0x7D or block[1] != 0x50:
        raise ProtocolError("Expected a Baud preset reply")
    length = int.from_bytes(block[7:9], "little")
    # Recheck canonical size/padding after reading the declared length.
    block = unpack_seven_bit(wire, 10 + length)
    if block[-1] != ((~sum(block[:-1])) & 255):
        raise ProtocolError("Preset reply checksum mismatch")
    slot = int.from_bytes(block[3:7], "little")
    if slot != expected_slot:
        raise ProtocolError("Preset reply does not match the requested slot")
    status = block[2]
    if status not in (0, 1, 2, 3):
        raise ProtocolError("Unknown preset reply status")
    if status != 0:
        if length:
            raise ProtocolError("Unexpected payload on a refused preset read")
        return {"slot": slot, "status": status, "complete": False}
    if length != 187:
        raise ProtocolError("Preset reply must contain 128 voice and 59 record bytes")
    return {"slot": slot, "status": status, "complete": True,
            "voice": block[9:137], "record": block[137:196]}


class SysExAssembler:
    """Assemble callback fragments with bounded memory and explicit counters.

    Real-time bytes may interleave SysEx and are counted separately. Truncated,
    interrupted or oversized messages never become accepted frames. Complete
    messages still require a format-specific parser and checksum validation.
    """
    def __init__(self, max_message_bytes: int = MAX_FRAME_BYTES):
        if type(max_message_bytes) is not int or not 3 <= max_message_bytes <= MAX_FRAME_BYTES:
            raise ValueError("SysEx frame bound must be 3..4096")
        self.max_message_bytes = max_message_bytes
        self.buffer = bytearray()
        self.realtime_bytes = 0
        self.discarded_bytes = 0
        self.aborted_messages = 0
        self.oversized_messages = 0

    def feed(self, chunk: bytes) -> list[bytes]:
        chunk = _bytes(chunk)
        messages = []
        for value in chunk:
            if value >= 0xF8:
                self.realtime_bytes += 1
                continue
            if value == 0xF0:
                self.aborted_messages += bool(self.buffer)
                self.buffer[:] = b"\xF0"
                continue
            if not self.buffer:
                self.discarded_bytes += 1
                continue
            if value > 127 and value != 0xF7:
                self.aborted_messages += 1
                self.buffer.clear()
                continue
            if len(self.buffer) >= self.max_message_bytes:
                self.oversized_messages += 1
                self.buffer.clear()
                continue
            self.buffer.append(value)
            if value == 0xF7:
                messages.append(bytes(self.buffer))
                self.buffer.clear()
        return messages

    def finish(self) -> None:
        if self.buffer:
            self.aborted_messages += 1
            self.buffer.clear()
