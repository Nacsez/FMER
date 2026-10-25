"""Reviewed library deployment. Validate the whole plan before opening MIDI."""
import hashlib
import companion_bank as bank
import library


def plan(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 144:
        raise ValueError('Choose 1..144 populated instrument/project destinations')
    seen = set()
    result = []
    for row in rows:
        library.fields(row, {'kind', 'slot', 'entry'}, 'transfer row')
        library.choice(row.get('kind'), {'instrument', 'project'}, 'transfer type')
        kind, slot = row['kind'], row.get('slot')
        library.integer(slot, 0, 127 if kind == 'instrument' else 15, 'destination')
        if (kind, slot) in seen:
            raise ValueError('Two items target the same destination; choose distinct slots')
        seen.add((kind, slot))
        bank.BankLibrary.validate_entry(row.get('entry'))
        # Upgrade and validate every byte before any hardware call.
        bank.native.encode(bank.decode_record(row['entry']['native']))
        label = ('Bank B' if slot < 64 else 'Bank A')+' '+str(slot % 64).zfill(2) if kind == 'instrument' else 'Project '+str(slot).zfill(2)
        result.append(dict(kind=kind, slot=slot, name=row['entry']['name'], destination=label))
    sha = hashlib.sha256(library.canonical(rows)).hexdigest()
    return dict(rows=result, count=len(result), sha256=sha, confirmation='Deploy '+sha,
                scope='Back up the complete unit, replace only the listed slots, verify each write, then restore the working state with playback stopped. Other projects keep their slot references. Empty PC slots are not erased on the unit. Transfers can stop partway; completed writes are retained and never retried automatically.')


def deploy(client, rows, directory, progress, journal, result):
    """Caller has durably captured a full unit snapshot before entering here."""
    checked = plan(rows)
    original = __import__('base64').b64decode(result['backup']['payload']['live'])
    result['completed'] = []
    write_failed = False
    try:
        # Sounds precede dependent projects, regardless of displayed selection order.
        for row in sorted(rows, key=lambda r: r['kind'] == 'project'):
            progress('Writing '+row['kind']+' '+row['entry']['name'],
                     done=len(result['completed']), total=checked['count'], unit='slots',
                     completed=list(result['completed']), backup_path=result['backup_path'])
            raw = bank.native.encode(bank.decode_record(row['entry']['native']))
            write = client.push_slot if row['kind'] == 'instrument' else client.push_project
            write(raw, row['slot'], directory)  # existing bridge includes exact readback
            completed = dict(kind=row['kind'], slot=row['slot'], name=row['entry']['name'])
            result['completed'].append(completed)
            journal.record('library_transfer_verified', **completed)
            progress('Verified '+row['entry']['name'], done=len(result['completed']),
                     total=checked['count'], unit='slots', completed=list(result['completed']),
                     backup_path=result['backup_path'])
    except Exception as error:
        write_failed = True
        raise RuntimeError(f'Transfer stopped after {len(result["completed"])}/{checked["count"]} verified slots. No automatic retry. Backup: {result["backup_path"]}. {error}') from error
    finally:
        try:
            result['working_restore'] = client.restore(original, directory)
        except Exception as error:
            result['working_restore_error'] = str(error)
            journal.record('library_transfer_working_restore_failed', error=str(error))
            # Do not hide an earlier write failure with a cleanup failure.
            if not write_failed:
                raise RuntimeError('Slots verified but working state could not be restored. Keep the backup and reconnect. '+str(error)) from error
    result['project_references_remapped'] = False
