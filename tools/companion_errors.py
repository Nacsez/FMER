"""Musician-facing outcomes; raw exceptions remain in diagnostic records."""
def explain(message, metadata=False):
    if message.startswith('Transfer stopped after') or message.startswith('Slots verified but working state'):
        return dict(title='Library transfer stopped',explanation=message,
                    next_step='Keep the pre-transfer backup. Download it from this operation before deciding whether to restore or continue. Earlier verified slots may have changed; nothing is retried automatically.')
    if 'Multiple candidate instruments' in message:
        return dict(title='More than one FM-1 is connected',explanation='Companion cannot choose which instrument you intend to manage. The operation has stopped.',next_step='Leave only the intended FM-1 connected to this computer, then choose Check connection. Back up and update each unit separately.')
    if ('midiInOpen' in message or 'midiOutOpen' in message) and 'MMRESULT 7' in message:
        return dict(title='The MIDI port is already in use',explanation='Windows could not give Companion access to this instrument’s MIDI port. The operation has stopped.',next_step='Close or disable this FM-1’s MIDI ports in Ableton and other music apps. If diagnostic capture is running in another Companion window, stop it or quit that instance. Then choose Check connection.')
    if 'different memory layout or calibration' in message:
        return dict(title='Installation paused: this unit needs a compatibility check',
          explanation='The updater is running, but layout/calibration verification did not pass. Different metadata or a flash-read problem can cause this; it does not prove different hardware. The FMER application was not written.',
          next_step=('Device metadata was collected automatically. Use Export operation record and share that file so this variant can be supported. Do not retry this same package.' if metadata else 'Use the latest companion with compatibility diagnostics, after turning the instrument off and on. If it pauses again, export the operation record.'))
    if 'Stage 1 timed out' in message:
        return dict(title='The instrument stopped responding during preparation',explanation='The updater transfer did not finish. This is not a completed installation.',next_step='Close other MIDI apps, power the unit off and on, reconnect one unit, and check its connection. If another attempt stops here, export the operation record.')
    if 'Stock firmware does not provide' in message:
        return dict(title='Connected to stock firmware',explanation='This stock firmware does not support the companion library-backup commands.',next_step='Open Firmware to install FMER, or read the stock-backup limitations in Help before proceeding.')
    if 'ota-FM-1_933' in message:
        return dict(title='An older updater is still running',explanation='This version needs its included updater to collect compatibility details.',next_step='Turn the unit off and on, reconnect it, then Check connection. If stock firmware returns, retry installation. Otherwise export this operation record.')
    if 'timed out' in message.lower() or 'MIDI' in message or 'identity' in message.lower():
        return dict(title='Could not verify the instrument connection',explanation='The companion did not receive a usable reply from the instrument.',next_step='Keep one unit powered on, reconnect its USB data cable, close other MIDI apps and choose Check connection. Export the record if this repeats.')
    return dict(title='The operation could not finish',explanation='A transfer or validation check failed. The operation has not been reported as complete.',next_step='Export the operation record for diagnosis. Do not repeat a write until the cause is understood.')
