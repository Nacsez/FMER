import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import fm1_native_state as v1
import fm1_native_state_v3 as native
import fm1_native_bridge_v8 as bridge
from tests.test_fm1_native_state import state_fixture, reply


def fixture():
    return native.decode(native.upgrade_v1(v1.encode(state_fixture())))


class Journal:
    def __init__(self): self.events=[]
    def record(self, event, **values): self.events.append(dict(event=event, **values))


class Session:
    verified_identity='FM-1_714'
    def __init__(self):
        self.state=fixture();self.state['source_generation']=7
        self.generation=7;self.export=0;self.last_tx=0;self.last_result=0;self.tx=0
        self.frame=None;self.sent=[];self.received=bytearray();self.commit_result=0
        self.chunk_failure=False;self.commit_timeout=False;self.corrupt_after_commit=False
        self.before_packet=None;self.store_generation=2;self.job=0;self.finished=0
        self.action=0;self.slot=0;self.store_result=0;self.busy=0;self.never_finish=False
        self.misidentify_job=False;self.native_writes=0;self.flash_writes=0
        self.corrupt_saved=False;self.stale_capture=False;self.action_timeout=False
        old=copy.deepcopy(self.state);old['controls'][162]=1000;old['vced'][145:]=list(b'OLD SLOT0 ')
        self.slots={0:native.encode(old),5:native.encode(self.state)};self.slot_generation={0:1,5:2}

    def store_values(self):
        latest=max(self.slot_generation,key=self.slot_generation.get) if self.slots else 65535
        return [2,1,self.busy,self.action,self.slot,self.store_result,self.job,self.finished,len(self.slots),latest,
                self.store_generation&0xffffffff,self.store_generation>>32,73-len(self.slots),0,0,1234,0,native.SIZE]

    def _send(self, packet, purpose):
        self.sent.append(packet)
        if self.before_packet:self.before_packet(packet,purpose)
        op=packet[6]
        number=lambda start,count=5:sum(packet[start+i]<<(7*i) for i in range(count))
        if op==13:
            self.frame=reply(op,[2,self.generation,self.state['preset_id'],0,0,0,self.export,self.last_tx,self.last_result])
        elif op==14:
            self.export+=1;state=copy.deepcopy(self.state);state['source_generation']=self.generation
            self.frozen=native.encode(state);self.frame=packet
        elif op==15:
            token,offset=number(7),number(12,2)
            assert token==self.export
            raw=self.frozen[offset:offset+64];self.frame=reply(op,[token,offset,len(raw),*raw])
        elif op==16:
            self.tx,self.expected=number(7),number(12);self.received=bytearray()
            self.frame=reply(op,[self.tx,0])
        elif op==17:
            tx,offset,count=number(7),number(12,2),packet[14]
            assert tx==self.tx and offset==len(self.received) and len(packet)==16+2*count
            self.received.extend((packet[15+2*i]<<4)|packet[16+2*i] for i in range(count))
            self.frame=reply(op,[tx,12 if self.chunk_failure else 0])
        elif op==18:
            tx=number(7);self.frame=reply(op,[tx,self.commit_result or 9])
            if not self.commit_result:
                self.state=native.decode(bytes(self.received));self.native_writes+=1
                if self.corrupt_after_commit:self.state['controls'][194]=72
                self.generation+=1;self.state['source_generation']=self.generation
                self.last_tx,self.last_result=tx,0
            if self.commit_timeout:self.frame=None
        elif op==19:self.frame=reply(op,[number(7),0])
        elif op==20:
            self.tx=0;self.received=bytearray();self.frame=reply(op,[number(7),0])
        elif op==21:self.frame=reply(op,self.store_values())
        elif op==23:
            slot=packet[7];raw=self.slots.get(slot)
            if raw:
                values=native.decode(raw)['vced'][145:];name=[c if 32<=c<127 else 32 for c in values]
                generation=self.slot_generation[slot];crc=zlib.crc32(raw)&0xffffffff
            else:name=[0]*10;generation=crc=0
            self.frame=reply(op,[slot,int(raw is not None),generation&0xffffffff,generation>>32,crc,*name])
        elif op==24:
            slot=packet[7]
            if slot in self.slots:
                self.export+=1;self.frozen=self.slots[slot];self.frame=reply(op,[slot,0])
            else:self.frame=reply(op,[slot,1])
        elif op==22:
            assert len(packet)==25
            action,slot=packet[7:9];generation=number(9);store_generation=number(14)|(number(19)<<32)
            if generation!=self.generation or store_generation!=self.store_generation:
                self.frame=reply(op,[slot,14]);return
            if self.busy:self.frame=reply(op,[slot,9]);return
            self.job+=1;self.action=action;self.slot=slot;self.store_result=0
            if self.stale_capture and action==1:
                self.generation+=1;self.store_result=11
            elif action==1:
                state=copy.deepcopy(self.state);state['source_generation']=self.generation
                if self.corrupt_saved:state['controls'][194]=(state['controls'][194]+1)%101
                self.slots[slot]=native.encode(state);self.store_generation+=1
                self.slot_generation[slot]=self.store_generation;self.flash_writes+=1
            elif slot not in self.slots:self.store_result=1
            else:
                self.state=native.decode(self.slots[slot]);self.generation+=1
                self.state['source_generation']=self.generation;self.native_writes+=1
            if self.never_finish:self.busy=2
            else:self.finished=self.job
            values=self.store_values()
            if self.misidentify_job:values[4]=(slot+1)%64
            self.frame=None if self.action_timeout else reply(21,values)
        else:raise AssertionError('Unexpected device command '+str(op))

    def read(self, timeout):
        result=self.frame;self.frame=None;return result


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.session,self.journal=Session(),Journal()
        self.bridge=bridge.NativeBridge(self.session,self.journal,sleep=lambda duration:None)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.directory=Path(self.temp.name)

    def test_truncated_read_retries_same_frozen_chunk_without_writes(self):
        original=self.session.read; dropped=[]
        def read(timeout):
            frame=original(timeout)
            if frame and frame[6]==15 and not dropped:
                dropped.append(frame)
                return frame[:48]+frame[96:]
            return frame
        self.session.read=read
        wire,_=self.bridge.snapshot()
        self.assertEqual(native.decode(wire),self.session.state)
        chunks=[p for p in self.session.sent if p[6]==15]
        self.assertEqual(chunks[0],chunks[1])
        self.assertEqual(len(chunks),native.SIZE//64+1)
        self.assertEqual((self.session.native_writes,self.session.flash_writes),(0,0))
        self.assertEqual(len([e for e in self.journal.events if e['event']=='native_chunk_rejected']),1)

    def test_persistent_invalid_read_is_bounded_and_refused(self):
        original=self.session.read
        def read(timeout):
            frame=original(timeout)
            return frame[:48]+frame[96:] if frame and frame[6]==15 else frame
        self.session.read=read
        with self.assertRaises(native.NativeStateError):self.bridge.snapshot()
        self.assertEqual(len([p for p in self.session.sent if p[6]==15]),3)
        self.assertEqual((self.session.native_writes,self.session.flash_writes),(0,0))

    def test_chunk_with_valid_count_but_corrupt_data_still_fails_crc(self):
        def corrupt(packet,purpose):
            if packet[6]==15 and packet[12]==0 and packet[13]==0:
                raw=bytearray(self.session.frozen);raw[100]^=1;self.session.frozen=bytes(raw)
        self.session.before_packet=corrupt
        with self.assertRaises(native.NativeStateError):self.bridge.snapshot()
        self.assertEqual(len([p for p in self.session.sent if p[6]==15]),native.SIZE//64)
        self.assertEqual((self.session.native_writes,self.session.flash_writes),(0,0))

    def test_exact_identity_before_first_or_later_command(self):
        for invalid in ('FM-1_707','FM-1_714X',None):
            self.session.verified_identity=invalid
            with self.assertRaises(RuntimeError):bridge.NativeBridge(self.session,self.journal)
            with self.assertRaises(RuntimeError):self.bridge.store_status()
        self.assertEqual(self.session.sent,[])

    def test_native_backup_and_ram_restore_complete_v2(self):
        backup=self.bridge.backup(self.directory)
        self.assertEqual(native.decode(Path(backup['backup']['path']).read_bytes()),self.session.state)
        wanted=fixture();wanted['patterns'][7]['steps'][63]=[127,83,99];wanted['controls'][194]=43
        result=self.bridge.restore(native.encode(wanted),self.directory,transaction=89)
        self.assertTrue(result['complete_state_verified']);self.assertFalse(result['flash_writes'])
        self.assertEqual(self.session.state['patterns'][7]['steps'][63],[127,83,99])
        self.assertEqual(self.session.flash_writes,0)

    def test_list_catalog_reads_only(self):
        result=self.bridge.list_slots()
        self.assertEqual(len(result['slots']),128)
        self.assertEqual([x['slot'] for x in result['slots'] if x['present']],[0,5])
        self.assertEqual(set(p[6] for p in self.session.sent),{21,23})

    def test_export_slot0_retains_exact_bytes_without_ram_write(self):
        original=self.session.slots[0];before=copy.deepcopy(self.session.state)
        result=self.bridge.export_slot(0,self.directory)
        self.assertEqual(Path(result['backup']['path']).read_bytes(),original)
        self.assertEqual(self.session.state,before)
        self.assertEqual(set(p[6] for p in self.session.sent),{13,15,21,23,24})

    def test_save_existing_slot_keeps_both_prebackups_then_verifies_full_data(self):
        old=self.session.slots[0];before=copy.deepcopy(self.session.state)
        result=self.bridge.save_slot(0,self.directory)
        self.assertEqual(Path(result['pre_action_slot_backup']['path']).read_bytes(),old)
        self.assertEqual(native.decode(Path(result['pre_action_live_backup']['path']).read_bytes()),before)
        self.assertEqual(native.decode(self.session.slots[0]),before)
        self.assertTrue(result['complete_state_verified']);self.assertEqual(self.session.flash_writes,1)
        self.assertEqual(self.session.native_writes,0)
        events=[x['event'] for x in self.journal.events]
        self.assertLess(events.index('onboard_pre_action_slot_backup_committed'),events.index('onboard_action_intent'))
        packet=next(p for p in self.session.sent if p[6]==22)
        self.assertEqual(len(packet),25);self.assertEqual(packet[7:9],bytes([1,0]))

    def test_save_empty_slot_never_overwrites_other_slots(self):
        old=dict(self.session.slots);result=self.bridge.save_slot(63,self.directory)
        self.assertIsNone(result['pre_action_slot_backup'])
        for slot,raw in old.items():self.assertEqual(self.session.slots[slot],raw)
        self.assertIn(63,self.session.slots)

    def test_load_has_ram_and_stored_backups_before_full_state_apply(self):
        old=copy.deepcopy(self.session.state);stored=self.session.slots[0]
        result=self.bridge.load_slot(0,self.directory)
        self.assertEqual(native.decode(Path(result['pre_action_live_backup']['path']).read_bytes()),old)
        self.assertEqual(Path(result['pre_action_slot_backup']['path']).read_bytes(),stored)
        self.assertEqual(self.session.state['controls'][162],1000)
        self.assertEqual(self.session.flash_writes,0);self.assertEqual(self.session.native_writes,1)
        self.assertTrue(result['complete_state_verified'])

    def test_push_backs_up_both_domains_and_syncs_complete_bank(self):
        old=self.session.slots[0];live=copy.deepcopy(self.session.state)
        wanted=fixture();wanted['patterns'][6]['steps'][61]=[111,99,38];wanted['vced'][145:]=list(b'NEW PATCH ')
        result=self.bridge.push_slot(native.encode(wanted),0,self.directory,transaction=42)
        self.assertEqual(Path(result['pre_action_slot_backup']['path']).read_bytes(),old)
        self.assertEqual(native.decode(Path(result['pre_action_live_backup']['path']).read_bytes()),live)
        stored=native.decode(self.session.slots[0]);wanted['source_generation']=stored['source_generation']
        self.assertEqual(stored,wanted);self.assertEqual(self.session.flash_writes,1);self.assertEqual(self.session.native_writes,1)
        self.assertTrue(result['complete_state_verified'])

    def test_malformed_file_or_slot_precedes_every_command(self):
        for method,args in [(self.bridge.restore,(bytes(native.SIZE),self.directory)),
                            (self.bridge.push_slot,(bytes(native.SIZE),0,self.directory)),
                            (self.bridge.save_slot,(128,self.directory)),(self.bridge.load_slot,(-1,self.directory)),
                            (self.bridge.export_slot,(True,self.directory))]:
            with self.assertRaises(ValueError):method(*args)
        self.assertEqual(self.session.sent,[])

    def test_failed_prebackup_blocks_all_device_mutations(self):
        for operation in ('save_slot','load_slot','push_slot'):
            self.session.sent.clear()
            with patch.object(native,'save_backup',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    if operation=='push_slot':self.bridge.push_slot(native.encode(fixture()),0,self.directory)
                    else:getattr(self.bridge,operation)(0,self.directory)
            self.assertFalse({16,17,18,22}&{p[6] for p in self.session.sent})

    def test_existing_backup_files_are_never_replaced(self):
        result=self.bridge.export_slot(0,self.directory);path=Path(result['backup']['path']);original=path.read_bytes()
        with self.assertRaises(FileExistsError):native.write_record(path,native.encode(fixture()))
        self.assertEqual(path.read_bytes(),original)

    def test_empty_load_refused_without_mutation(self):
        with self.assertRaisesRegex(RuntimeError,'empty'):self.bridge.load_slot(63,self.directory)
        self.assertFalse({16,17,18,22}&{p[6] for p in self.session.sent})

    def test_atomic_live_and_store_revision_guards(self):
        for domain in ('live','store'):
            session=Session();client=bridge.NativeBridge(session,Journal(),sleep=lambda duration:None)
            def race(packet,purpose):
                if packet[6]==22:
                    if domain=='live':session.generation+=1
                    else:session.store_generation+=1
            session.before_packet=race
            with self.assertRaisesRegex(RuntimeError,'refused: stale'):client.save_slot(0,self.directory)
            self.assertEqual(session.flash_writes,0)

    def test_capture_generation_race_fails_before_nor_commit(self):
        self.session.stale_capture=True
        with self.assertRaisesRegex(RuntimeError,'failed: stale'):self.bridge.save_slot(0,self.directory)
        self.assertEqual(self.session.flash_writes,0)

    def test_slot_change_during_export_is_not_a_valid_backup(self):
        def race(packet,purpose):
            if packet[6]==15 and len([p for p in self.session.sent if p[6]==15])==1:
                self.session.store_generation+=1
        self.session.before_packet=race
        with self.assertRaisesRegex(RuntimeError,'changed while exporting'):self.bridge.export_slot(0,self.directory)
        self.assertEqual(list(self.directory.glob('*.fmer-native')),[])

    def test_slot_change_during_native_restore_prevents_push_flash(self):
        def race(packet,purpose):
            if packet[6]==18:self.session.store_generation+=1
        self.session.before_packet=race
        with self.assertRaisesRegex(RuntimeError,'destination changed'):self.bridge.push_slot(native.encode(fixture()),0,self.directory)
        self.assertEqual(self.session.native_writes,1);self.assertEqual(self.session.flash_writes,0)
        self.assertIn('onboard_push_incomplete',[x['event'] for x in self.journal.events])

    def test_edit_after_restore_snapshot_cannot_hide_in_newer_status_generation(self):
        def race(packet,purpose):
            # After restore verification is frozen, before its status reply:
            # status can truthfully be newer than the snapshot we verified.
            if packet[6]==13 and self.session.native_writes and self.session.export==3:
                self.session.before_packet=None
                self.session.state['controls'][194]=37
                self.session.generation+=1
        self.session.before_packet=race
        with self.assertRaisesRegex(RuntimeError,'Live state changed after PC restore'):
            self.bridge.push_slot(native.encode(fixture()),0,self.directory)
        self.assertEqual(self.session.native_writes,1);self.assertEqual(self.session.flash_writes,0)

    def test_storage_timeout_is_bounded_and_never_retried(self):
        self.session.never_finish=True
        with self.assertRaisesRegex(TimeoutError,'do not assume rollback'):self.bridge.save_slot(0,self.directory)
        self.assertEqual(sum(p[6]==22 for p in self.session.sent),1)
        self.assertLessEqual(sum(p[6]==21 for p in self.session.sent),410)

    def test_ambiguous_write_timeout_preserves_backup_and_no_rollback_claim(self):
        self.session.action_timeout=True
        with self.assertRaises(TimeoutError):self.bridge.save_slot(0,self.directory)
        self.assertEqual(self.session.flash_writes,1)
        self.assertEqual(sum(p[6]==22 for p in self.session.sent),1)
        event=next(x for x in self.journal.events if x['event']=='onboard_action_unverified')
        self.assertFalse(event['rollback_claimed']);self.assertFalse(event['automatic_retry'])
        self.assertEqual(len(list(self.directory.glob('*.fmer-native'))),2)

    def test_acknowledgement_for_different_slot_is_not_success(self):
        self.session.misidentify_job=True
        with self.assertRaisesRegex(ValueError,'another job'):self.bridge.save_slot(0,self.directory)

    def test_complete_readback_mismatch_never_reports_success(self):
        self.session.corrupt_saved=True
        with self.assertRaisesRegex(RuntimeError,'Complete native state differs'):self.bridge.save_slot(0,self.directory)
        self.assertIn('onboard_save_mismatch',[x['event'] for x in self.journal.events])

    def test_native_chunk_failure_aborts_only_incomplete_own_staging(self):
        self.session.chunk_failure=True
        with self.assertRaisesRegex(RuntimeError,'chunk refused'):self.bridge.restore(native.encode(fixture()),self.directory,transaction=89)
        self.assertEqual(self.session.sent[-1],native.abort_request(89));self.assertEqual(self.session.native_writes,0)

    def test_ambiguous_native_commit_timeout_never_aborts_or_claims_rollback(self):
        self.session.commit_timeout=True
        with self.assertRaises(TimeoutError):self.bridge.restore(native.encode(fixture()),self.directory,transaction=89)
        self.assertEqual(self.session.sent[-1][6],18);self.assertEqual(self.session.native_writes,1)


class WireTests(unittest.TestCase):
    def test_store_status_strict_fields_and_ranges(self):
        values=Session().store_values();parsed=bridge.parse_storage_status(reply(21,values))
        self.assertEqual(parsed['generation'],2)
        for index,bad in [(0,1),(1,2),(2,4),(3,7),(4,128),(5,13),(8,129),(9,128),(12,74),(16,13),(17,784)]:
            broken=list(values);broken[index]=bad
            with self.assertRaises(ValueError):bridge.parse_store_status(reply(21,broken))
        for frame in (reply(21,values+[0]),reply(22,values),native.PREFIX+b'\x15-1\xf7'):
            with self.assertRaises(ValueError):bridge.parse_store_status(frame)

    def test_slot_catalog_name_and_destination_are_strict(self):
        values=[0,1,1,0,123]+list(b'SLOT ZERO ')
        self.assertEqual(bridge.parse_slot_catalog(reply(23,values),0)['name'],'SLOT ZERO')
        for index,bad in [(0,1),(1,2),(5,127),(6,1)]:
            broken=list(values);broken[index]=bad
            with self.assertRaises(ValueError):bridge.parse_slot_catalog(reply(23,broken),0)

    def test_guarded_packet_exact_little7bit_generation_fields(self):
        packet=bridge.store_action_request(1,63,0xffffffff,0x123456789abcdef0)
        number=lambda start:sum(packet[start+i]<<(7*i) for i in range(5))
        self.assertEqual(len(packet),25);self.assertEqual(packet[:9],native.PREFIX+bytes([22,1,63]))
        self.assertEqual(number(9),0xffffffff);self.assertEqual(number(14),0x9abcdef0);self.assertEqual(number(19),0x12345678)
        self.assertTrue(all(x<128 for x in packet[1:-1]))
        for args in ((0,0,0,0),(1,128,0,0),(1,0,-1,0),(1,0,0,1<<64),(1,True,0,0)):
            with self.assertRaises(ValueError):bridge.store_action_request(*args)

    def test_slot0_results_are_valid_but_mismatched_slot_or_opcode_refused(self):
        self.assertEqual(bridge.parse_slot_result(reply(24,[0,0]),opcode=24,slot=0)['result'],0)
        for frame,op,slot in ((reply(24,[1,0]),24,0),(reply(22,[0,0]),24,0),(reply(24,[0,15]),24,0)):
            with self.assertRaises(ValueError):bridge.parse_slot_result(frame,opcode=op,slot=slot)


if __name__=='__main__':unittest.main()
