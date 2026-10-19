"""Read-only Windows endpoint identity. Port location is NOT a unit serial.

No MIDI messages, device configuration or registry writes. Explicit location
selection survives the updater PID change while refusing same-name ambiguity.
"""
from __future__ import annotations
import ctypes as c
import hashlib
import re
import uuid


class Key(c.Structure):
    _fields_ = [('guid', c.c_ubyte * 16), ('pid', c.c_uint32)]


def key(guid, pid):
    return Key((c.c_ubyte * 16).from_buffer_copy(uuid.UUID(guid).bytes_le), pid)


def interface(api, direction, index):
    fn = getattr(api.dll, 'midi' + direction + 'Message')
    fn.argtypes = [c.c_void_p, c.c_uint, c.c_size_t, c.c_size_t]
    fn.restype = c.c_uint
    size = c.c_uint32()
    if fn(index, 0x80d, c.addressof(size), 0) or not 2 <= size.value <= 8192 or size.value % 2:
        raise ValueError('MIDI interface size unavailable')
    buf = c.create_unicode_buffer(size.value // 2)
    if fn(index, 0x80c, c.addressof(buf), size.value) or not buf.value:
        raise ValueError('MIDI interface unavailable')
    return buf.value.lower()


def locations(path):
    dll = c.WinDLL('cfgmgr32')
    prop = dll.CM_Get_Device_Interface_PropertyW
    prop.argtypes = [c.c_wchar_p, c.POINTER(Key), c.POINTER(c.c_uint32), c.c_void_p, c.POINTER(c.c_uint32), c.c_uint32]
    prop.restype = c.c_uint32
    instance_key = key('78c34fc8-104a-4aca-9ea4-524d52996e57', 256)
    buf = c.create_unicode_buffer(4096); size = c.c_uint32(c.sizeof(buf)); kind = c.c_uint32()
    if prop(path, c.byref(instance_key), c.byref(kind), buf, c.byref(size), 0) or kind.value != 18:
        raise ValueError('MIDI device instance unavailable')
    locate = dll.CM_Locate_DevNodeW
    locate.argtypes = [c.POINTER(c.c_uint32), c.c_wchar_p, c.c_uint32]; locate.restype = c.c_uint32
    node = c.c_uint32()
    if locate(c.byref(node), buf.value, 0): raise ValueError('MIDI device node unavailable')
    get = dll.CM_Get_DevNode_PropertyW
    get.argtypes = [c.c_uint32, c.POINTER(Key), c.POINTER(c.c_uint32), c.c_void_p, c.POINTER(c.c_uint32), c.c_uint32]
    get.restype = c.c_uint32
    parent = dll.CM_Get_Parent
    parent.argtypes = [c.POINTER(c.c_uint32), c.c_uint32, c.c_uint32]; parent.restype = c.c_uint32
    location_key = key('a45c254e-df1c-4efd-8020-67d146a850e0', 37)
    for _ in range(4):
        size.value = c.sizeof(buf)
        if not get(node.value, c.byref(location_key), c.byref(kind), buf, c.byref(size), 0) and kind.value == 0x2012:
            paths = c.string_at(c.addressof(buf), size.value).decode('utf-16-le').rstrip('\0').split('\0')
            # USB interface suffix is absent on the physical device/updater.
            paths = sorted(set(re.sub(r'#USBMI\(\d+\)$', '', p.upper()) for p in paths))
            if paths: return paths
        previous = node.value
        if parent(c.byref(node), previous, 0): break
    raise ValueError('Physical USB location unavailable')


def annotate(api, rows):
    result = {'inputs': [], 'outputs': []}
    for group, direction in [('inputs', 'In'), ('outputs', 'Out')]:
        for row in rows[group]:
            record = dict(row)
            try:
                path = interface(api, direction, row['id'])
                record.update(interface_sha256=hashlib.sha256(path.encode()).hexdigest(), location_paths=locations(path))
            except (OSError, ValueError) as exc:
                record['identity_error'] = str(exc)
            result[group].append(record)
    return result


def filter_location(rows, location):
    if not isinstance(location, str) or not re.fullmatch(r'PCIROOT\([0-9A-F]+\)(?:#(?:PCI|USBROOT|USB)\([0-9A-F]+\))+', location):
        raise ValueError('Exact physical USB location required')
    result = {g: [r for r in rows[g] if location in r.get('location_paths', [])] for g in ('inputs', 'outputs')}
    for group in result:
        if len(result[group]) > 1: raise ValueError('Multiple MIDI endpoints at selected USB location')
    if all(result.values()) and result['inputs'][0].get('interface_sha256') != result['outputs'][0].get('interface_sha256'):
        raise ValueError('MIDI input/output physical interfaces differ')
    return result


def verify_opened(api, direction, handle, expected):
    getid = getattr(api.dll, 'midi' + direction + 'GetID')
    getid.argtypes = [c.c_void_p, c.POINTER(c.c_uint)]; getid.restype = c.c_uint
    index = c.c_uint()
    if getid(handle, c.byref(index)): raise ValueError('Opened MIDI handle identity unavailable')
    path = interface(api, direction, index.value)
    if hashlib.sha256(path.encode()).hexdigest() != expected['interface_sha256']:
        raise ValueError('Opened MIDI interface changed since enumeration')
    if locations(path) != expected['location_paths']:
        raise ValueError('Opened MIDI physical location changed since enumeration')
