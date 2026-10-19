"""Extract exact reviewed staged MIDI functions for a synthetic-I/O host test."""
from pathlib import Path
import sys,hashlib,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build_fm1_candidate as build
from extract_fm1_storage_board import block
root,out=map(Path,sys.argv[1:]);out.parent.mkdir(parents=True,exist_ok=True)
usb=build.brand_usb((build.FELUCCA/'firmware/src/usb.c').read_bytes()).decode('utf8')
uart=build.patch_uart((build.FELUCCA/'firmware/src/midi_uart.c').read_bytes()).decode('utf8')
board=(root/'firmware/fm1/board.c').read_text(encoding='utf8')
text='\n'.join(block(source,marker) for source,marker in ((uart,'static uint32_t um_len('),(uart,'static void um_byte('),(usb,'static void midi_in_event('),(board,'static int midi_output('),(board,'static void midi_output_recover(')))
out.write_text(text+'\n',encoding='utf8')
out.with_suffix('.json').write_text(json.dumps(dict(board_sha256=hashlib.sha256(board.encode()).hexdigest(),staged_usb_sha256=hashlib.sha256(usb.encode()).hexdigest(),staged_uart_sha256=hashlib.sha256(uart.encode()).hexdigest(),extracted_sha256=hashlib.sha256((text+'\n').encode()).hexdigest()),indent=2),encoding='utf8')
