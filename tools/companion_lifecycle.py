"""Browser leases: release the local server after its last tab closes.
Transfers own the server until complete; a missed heartbeat cannot cancel writes.
"""
import time
class BrowserLeases:
    def __init__(self, clock=time.monotonic, grace=45, startup=120, heartbeat_timeout=180):
        self.clock=clock;self.heartbeat_timeout=heartbeat_timeout;self.grace=grace;self.startup=startup;self.born=clock();self.tabs={};self.seen=False;self.last= self.born
    def update(self, token, closed=False):
        if not isinstance(token,str) or not 1<=len(token)<=80:raise ValueError('Invalid browser session')
        now=self.clock();self.seen=True;self.last=now
        if closed:self.tabs.pop(token,None)
        else:self.tabs[token]=now
    def expired(self, active=False):
        now=self.clock()
        if active:self.last=now;return False
        if any(now-t<self.heartbeat_timeout for t in list(self.tabs.values())):return False
        return now-self.last>=self.grace if self.seen else now-self.born>=self.startup
