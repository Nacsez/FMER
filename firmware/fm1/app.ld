/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Leo Kuroshita (@kurogedelic), Hügelton Instruments
 * Derived from Felucca 20c275e39f75fa820978032efaceddfc5283c8cb firmware/app.ld.
 * FMER 2026-10-05: explicit entry, section alignment, boundary assertions,
 * and rejection of unsupported static C++ constructors. Memory map unchanged.
 */
ENTRY(_start)
MEMORY
{
    XIP    (rx)  : ORIGIN = 0x02000120, LENGTH = 0x8DFBC
    RAMTEXT (rwx): ORIGIN = 0x01C00000, LENGTH = 0x6000
    RAM    (rwx) : ORIGIN = 0x01C08000, LENGTH = 96K
    POOL   (rw)  : ORIGIN = 0x01C20000, LENGTH = 0x54000
    NOINIT (rw)  : ORIGIN = 0x01C7C000, LENGTH = 0x3D50
}
SECTIONS
{
    .text : { KEEP(*(.text.crt0)) *(.text*) *(.rodata*) . = ALIGN(4); _etext = .; } > XIP
    .ram_text : { _rt_start = .; KEEP(*(.ram_text*)) . = ALIGN(4); _rt_end = .; } > RAMTEXT AT > XIP
    _rt_load = LOADADDR(.ram_text);
    .data : { . = ALIGN(4); _data_start = .; *(.data*) *(.sdata*) . = ALIGN(4); _data_end = .; } > RAM AT > XIP
    _data_load = LOADADDR(.data);
    .bss (NOLOAD) : { _bss_start = .; *(.bss*) *(.sbss*) *(COMMON) . = ALIGN(4); _bss_end = .; } > RAM
    .pool (NOLOAD) : { . = ALIGN(16); _pool_start = .; *(.pool*) . = ALIGN(16); _pool_end = .; } > POOL
    .workspace (NOLOAD) : {
        . = ALIGN(16); _workspace_start = .;
        *(.workspace*)
        . = ALIGN(16); _workspace_end = .;
    } > POOL
    .noinit (NOLOAD) : { *(.noinit*) } > NOINIT
    .unsupported_ctors : { KEEP(*(.init_array*)) KEEP(*(.ctors*)) } > XIP
    /* 719: give nested audio/MIDI callbacks 4KiB more system stack. The user
     * stack retains20,224B; arena/workspace/noinit addresses remain unchanged. */
    _guard0 = 0x01C74000; _ustack_lo = 0x01C74100; _ustack_top = 0x01C79000;
    _guard1 = 0x01C79000; _sstack_lo = 0x01C79100; _sstack_top = 0x01C7C000;
    /DISCARD/ : { *(.comment) *(.note*) }
    ASSERT(_start == ORIGIN(XIP), "SPL entry must be first byte of XIP app")
    ASSERT((_rt_load & 3) == 0 && (_data_load & 3) == 0, "Startup load addresses must be word aligned")
    ASSERT(_rt_end <= ORIGIN(RAMTEXT) + LENGTH(RAMTEXT), "RAM text overlaps debug area")
    ASSERT(_bss_end <= ORIGIN(RAM) + LENGTH(RAM), "RAM globals exceed 96 KiB")
    ASSERT(_pool_end <= _guard0, "Pool overlaps stack guard")
    ASSERT(_pool_start == 0x01C20000 && _pool_end == 0x01C68000, "Startup arena placement changed")
    ASSERT(_workspace_start >= _pool_end && _workspace_end <= _guard0, "Workspace overlaps arena or stack guard")
    ASSERT((_workspace_start & 15) == 0 && (_workspace_end & 15) == 0, "Workspace must be16-byte aligned")
    ASSERT(_ustack_top - _ustack_lo == 20224 && _sstack_top - _sstack_lo == 12032, "Reviewed stack budgets changed")
    ASSERT(SIZEOF(.unsupported_ctors) == 0, "Board startup does not run static C++ constructors")
}
