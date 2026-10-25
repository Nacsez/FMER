"""Small, local browser-startup journal; never reads musical or device data."""
from datetime import datetime, timezone
import json
from pathlib import Path


class StartupLog:
    def __init__(self, root):
        self.path = Path(root) / 'logs/startup/events.jsonl'

    def record(self, value):
        if not isinstance(value, dict) or set(value) != {'event', 'detail', 'browser'}:
            raise ValueError('Invalid startup diagnostic')
        for key, limit in (('event', 40), ('detail', 1000), ('browser', 300)):
            if not isinstance(value[key], str) or len(value[key]) > limit:
                raise ValueError('Startup diagnostic exceeds limit')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size > 65536:
            self.path.replace(self.path.with_suffix('.previous.jsonl'))
        with self.path.open('a', encoding='utf8') as stream:
            stream.write(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(), **value))+'\n')

    def report(self, source):
        events = []
        if self.path.is_file():
            # Bound reads even if a local file has been replaced externally.
            with self.path.open('rb') as stream:
                stream.seek(max(0, self.path.stat().st_size - 65536))
                for line in stream.read(65536).splitlines()[-40:]:
                    try: events.append(json.loads(line))
                    except (ValueError, UnicodeError): pass
        return dict(format='FMER-STARTUP-DIAGNOSTICS', version=1,
                    companion='735/r11', source=source, events=events,
                    privacy='Local browser diagnostics only; no sounds, projects, ROMs or automatic upload. Review error text before sharing.')
