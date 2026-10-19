"""Portable entrypoint: writable per-user data, loopback server, no setup."""
from pathlib import Path
import os,sys,json,ctypes,traceback
if 'FMER_DATA_DIR' not in os.environ:
    os.environ['FMER_DATA_DIR']=str(Path(os.environ['LOCALAPPDATA'])/'FMER'/'Companion')
folder=Path(os.environ['FMER_DATA_DIR']);folder.mkdir(parents=True,exist_ok=True)
try:
    import launch_companion
    result=launch_companion.launch('--no-browser' not in sys.argv)
    (folder/'launch.json').write_text(json.dumps(result,indent=2),encoding='utf8')
except Exception:
    message=traceback.format_exc();(folder/'startup-error.log').write_text(message,encoding='utf8')
    ctypes.windll.user32.MessageBoxW(None,'See '+str(folder/'startup-error.log')+'\n'+message,'FMER startup failed',16)
    sys.exit(1)
