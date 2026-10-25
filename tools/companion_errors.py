"""Musician-facing outcomes; raw exceptions remain in diagnostic records."""
def explain(message, metadata=False):
    # Discovery means locating the physical unit, not reading its sound bank.
    # Keep transition failures separate: absence alone cannot prove whether a
    # previous write completed, so never recommend a blind reset/reflash here.
    if 'Timed out waiting for ota-FM-1_' in message:
        return dict(title='The updater did not reconnect', explanation='Companion could not verify the FM-1 updater after the connection changed. Installation has not been confirmed complete.', next_step='Keep the unit powered on. Wait for the operation to stop, then use Export operation record. Note what the unit screen shows; do not erase banks or repeatedly restart installation.')
    if 'Timed out waiting for FM-1_' in message:
        return dict(title='The expected firmware was not detected', explanation='Companion could not verify the expected firmware identity. This does not tell us whether an earlier transfer finished.', next_step='Keep the unit powered on and export the operation record after the operation stops. Include what its screen shows before trying another installation.')
    if '[discovery:identity_timeout]' in message or '[discovery:transitional_identity]' in message or message=='Identity reply timed out':
        return dict(title='FM-1 MIDI ports found, but no usable firmware reply', explanation='Windows exposes both MIDI ports, but Companion could not verify a supported reply. This is a device connection check, not a missing instrument bank.', next_step='Close other music apps and any other Companion instance, then choose Check connection. If FMER is in USB Master mode, select GLO > USB LINK > PC/NORMAL and press SEL. If it still fails, export the operation record and include the firmware shown on the unit.')
    if '[discovery:incomplete_pair]' in message:
        return dict(title='Only one FM-1 MIDI port is available', explanation='Companion needs both the FM-1 MIDI input and output. Windows currently exposes only one matching side.', next_step='After the operation stops, reconnect one powered-on FM-1 directly with a USB data cable and choose Check connection. Close other MIDI apps. If it persists, export the operation record; do not reset the instrument banks.')
    if '[discovery:no_ports]' in message or '[discovery:unrecognized_ports]' in message or 'Timed out waiting for None;' in message or 'Timed out waiting for compatible-FM-1;' in message:
        return dict(title='FM-1 USB MIDI connection not found', explanation='Companion could not locate a usable FM-1 MIDI connection. This refers to the physical unit, not its instrument presets. Charging or USB audio alone does not establish MIDI connectivity.', next_step='Connect one powered-on FM-1 directly using a USB data cable, close other MIDI apps, and choose Check connection. On FMER, leave USB Master mode using GLO > USB LINK > PC/NORMAL, then SEL. If it still fails, export the operation record and include the firmware shown on the unit; other firmware may use an unrecognized MIDI name.')
    if 'community' in message.lower() or 'FM6' in message:
        return dict(title='Community voice capture could not finish',explanation=message,
                    next_step='No firmware or patch write was requested. Check the supported family in Help, connect one unit and leave its controls untouched. Export the operation record if the read still fails.')
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
