import tempfile
import unittest
from unittest import mock
from pathlib import Path
import json
import gzip
import subprocess
import sys


class WorkerConnection:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.responses = []

    def poll(self, timeout):
        return True

    def recv(self):
        if hasattr(self, 'before_first_recv'):
            hook = self.before_first_recv
            del self.before_first_recv
            hook()
        try:
            cmd, payload = next(self.messages)
            return {'cmd': cmd, 'payload': payload}
        except StopIteration:
            raise EOFError

    def send(self, value):
        self.responses.append(value)


DOMAIN = {'grid_shape': [8, 8, 8], 'voxel_size_nm': 5, 'threads': 1}


class MaskApplyTransactionTests(unittest.TestCase):
    def test_idle_autosave_preserves_pending_flag_without_crossing_failed_rollback(self):
        import tcad_simulator as tcad
        from mask_assets.transaction import MaskApplyTransaction
        from tests.test_mask_assets import _candidate
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blocked = False
            idle_tick = False
            time_offset = 0
            writes_while_blocked = []
            original_time = tcad.time.time
            original_dump = tcad._webui_pickle_dump
            original_recover = MaskApplyTransaction.recover
            class IdleConnection(WorkerConnection):
                def poll(self, timeout):
                    nonlocal idle_tick, time_offset
                    if blocked and not idle_tick:
                        idle_tick = True
                        time_offset = 10
                        return False
                    return True
            conn = IdleConnection([
                ('recipe_insert_steps', {'steps': [{'name': 'Mask Exposure'}], 'insert_index': -1, 'no_autosave': True}),
                ('save', {}),
                ('recipe_set_name', {'name': 'Pending autosave'}),
                ('mask_asset_save_apply', {'step_index': 0, 'asset': _candidate()}),
                ('get_recipe', {}),
            ])
            def fail_commit(transaction):
                nonlocal blocked
                blocked = True
                raise OSError('commit failed')
            def recover(transaction):
                if blocked:
                    raise OSError('rollback failed')
                return original_recover(transaction)
            def dump(path, payload):
                if blocked:
                    writes_while_blocked.append(Path(path))
                return original_dump(path, payload)
            with mock.patch.object(MaskApplyTransaction, 'commit', new=fail_commit), mock.patch.object(MaskApplyTransaction, 'recover', new=recover), mock.patch.object(tcad, '_webui_pickle_dump', new=dump), mock.patch.object(tcad.time, 'time', side_effect=lambda: original_time() + time_offset):
                tcad._webui_worker_main(conn, str(root), default_domain=DOMAIN)
            self.assertTrue(idle_tick)
            self.assertEqual(writes_while_blocked, [])
            self.assertTrue(conn.responses[-1]['ok'])
            self.assertTrue((root / '.mask-apply-pending.json').exists())

    def test_pending_rollback_blocks_new_mutations_until_recovery_succeeds(self):
        import tcad_simulator as tcad
        from mask_assets.transaction import MaskApplyTransaction
        from tests.test_mask_assets import _candidate
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_recover = MaskApplyTransaction.recover
            blocked = False
            setup = [
                ('recipe_insert_steps', {'steps': [{'name': 'Mask Exposure'}], 'insert_index': -1, 'no_autosave': True}),
                ('save', {}),
                ('get_recipe', {}),
                ('mask_asset_save_apply', {'step_index': 0, 'asset': _candidate()}),
                ('recipe_insert_steps', {'steps': [{'name': 'Etch'}]}),
                ('save', {}),
                ('get_recipe', {}),
                ('recipe_insert_steps', {'steps': [{'name': 'Etch'}]}),
                ('save', {}),
                ('get_recipe', {}),
            ]
            class RecoveryConnection(WorkerConnection):
                def recv(self):
                    nonlocal blocked
                    if len(self.responses) == 7:
                        blocked = False
                    return super().recv()
            conn = RecoveryConnection(setup)
            def fail_commit(transaction):
                nonlocal blocked
                blocked = True
                raise OSError('private commit failure')
            def recover(transaction):
                if blocked:
                    raise OSError('private rollback failure')
                return original_recover(transaction)
            with mock.patch.object(MaskApplyTransaction, 'commit', new=fail_commit), mock.patch.object(MaskApplyTransaction, 'recover', new=recover):
                tcad._webui_worker_main(conn, str(root), default_domain=DOMAIN)
            self.assertEqual(conn.responses[3].get('code'), 'mask_asset_apply_failed')
            for response in conn.responses[4:6]:
                self.assertFalse(response['ok'])
                self.assertEqual(response.get('code'), 'mask_asset_recovery_blocked')
                self.assertEqual(response.get('status'), 500)
                self.assertNotIn('private', response['error'])
            self.assertEqual(conn.responses[6]['result'], conn.responses[2]['result'])
            self.assertTrue(conn.responses[7]['ok'])
            self.assertTrue(conn.responses[8]['ok'])
            expected = conn.responses[9]['result']
            self.assertEqual(len(expected), len(conn.responses[2]['result']) + 1)
            restarted = WorkerConnection([('get_recipe', {})])
            tcad._webui_worker_main(restarted, str(root), default_domain=DOMAIN)
            actual = restarted.responses[0]['result']
            self.assertEqual([(step['name'], step['params']) for step in actual], [(step['name'], step['params']) for step in expected])

    def test_store_directory_flush_failure_restores_previous_manifest(self):
        from mask_assets import MaskAssetError, MaskAssetService, MaskAssetStore
        import mask_assets.store as store_module
        from tests.test_mask_assets import _candidate
        with tempfile.TemporaryDirectory() as directory:
            store = MaskAssetStore(Path(directory))
            service = MaskAssetService(store)
            service.save_candidate(_candidate())
            old_manifest = store.manifest_bytes('mask_metal1')
            original_fsync = store_module.fsync_directory
            failed = False
            def fail_after_manifest(path):
                nonlocal failed
                original_fsync(path)
                if path.name == 'mask_metal1' and not failed:
                    failed = True
                    raise OSError('flush failed')
            with mock.patch.object(store_module, 'fsync_directory', side_effect=fail_after_manifest):
                with self.assertRaises(MaskAssetError):
                    service.save_candidate(_candidate())
            self.assertEqual(store.manifest_bytes('mask_metal1'), old_manifest)
            self.assertFalse((store.root / 'mask_metal1/revisions/2.json').exists())

    def test_restart_restores_all_partial_publications(self):
        from mask_assets.transaction import MaskApplyTransaction
        for phase in range(4):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                history = root / 'history'
                history.mkdir()
                recipe = history / 'recipe.pkl.gz'
                recipe.write_bytes(b'old recipe')
                tx = MaskApplyTransaction(root)
                revision = root / 'mask_assets/a/revisions/1.json'
                tx.begin([recipe, root / 'autosave.pkl.gz', revision, revision.parent.parent / 'manifest.json'])
                revision.parent.mkdir(parents=True)
                revision.write_bytes(b'revision')
                if phase >= 1:
                    (revision.parent.parent / 'manifest.json').write_bytes(b'manifest')
                if phase >= 2:
                    recipe.write_bytes(b'new recipe')
                if phase >= 3:
                    (root / 'autosave.pkl.gz').write_bytes(b'new recipe')
                MaskApplyTransaction(root).recover()
                self.assertEqual(recipe.read_bytes(), b'old recipe')
                self.assertFalse(revision.exists())
                self.assertFalse((root / 'autosave.pkl.gz').exists())

    def test_commit_preserves_new_recipe_on_restart(self):
        from mask_assets.transaction import MaskApplyTransaction
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tx = MaskApplyTransaction(root)
            tx.begin([root / 'autosave.pkl.gz'])
            (root / 'autosave.pkl.gz').write_bytes(b'new recipe')
            tx.commit()
            MaskApplyTransaction(root).recover()
            self.assertEqual((root / 'autosave.pkl.gz').read_bytes(), b'new recipe')

    def test_worker_rolls_back_failed_last_active_recipe_write(self):
        import tcad_simulator as tcad
        from tests.test_mask_assets import _candidate

        class Connection:
            def __init__(self):
                self.messages = iter([
                    ('recipe_insert_steps', {'steps': [{'name': 'Mask Exposure'}], 'insert_index': -1, 'no_autosave': True}),
                    ('save', {}),
                    ('mask_asset_save_apply', {'step_index': 0, 'asset': _candidate()}),
                    ('get_recipe', {}),
                ])
                self.responses = []

            def poll(self, timeout):
                return True

            def recv(self):
                try:
                    cmd, payload = next(self.messages)
                    return {'cmd': cmd, 'payload': payload}
                except StopIteration:
                    raise EOFError

            def send(self, value):
                self.responses.append(value)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_dump = tcad._webui_pickle_dump
            def dump(path, payload):
                if Path(path) == root / 'autosave.pkl.gz' and str(payload.get('note', '')).startswith('apply mask asset'):
                    raise OSError('private disk failure')
                return original_dump(path, payload)
            conn = Connection()
            with mock.patch.object(tcad, '_webui_pickle_dump', side_effect=dump):
                tcad._webui_worker_main(conn, str(root), default_domain={'grid_shape': [8, 8, 8], 'voxel_size_nm': 5, 'threads': 1})
            applied = conn.responses[-2]
            self.assertFalse(applied['ok'], conn.responses)
            self.assertEqual(applied['code'], 'mask_asset_apply_failed')
            self.assertNotIn('private', applied['error'])
            self.assertTrue(conn.responses[-1]['ok'])
            self.assertNotEqual(conn.responses[-1]['result'][0]['params'].get('mask_mode'), 'Asset')
            self.assertFalse((root / 'mask_assets/mask_metal1/manifest.json').exists())

    def test_worker_failures_restore_recipe_assets_and_keep_worker_alive(self):
        import tcad_simulator as tcad
        import mask_assets.store as store
        from mask_assets.transaction import MaskApplyTransaction
        from tests.test_mask_assets import _candidate
        for command in ('mask_asset_save_apply', 'mask_asset_import_apply'):
            for phase in ('revision', 'manifest', 'binding', 'recipe'):
                with self.subTest(command=command, phase=phase), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    setup = WorkerConnection([
                        ('recipe_insert_steps', {'steps': [{'name': 'Mask Exposure'}], 'insert_index': -1, 'no_autosave': True}),
                        ('mask_asset_save_apply', {'step_index': 0, 'asset': _candidate()}),
                        ('save', {}),
                    ])
                    tcad._webui_worker_main(setup, str(root), default_domain=DOMAIN)
                    self.assertTrue(all(response['ok'] for response in setup.responses))
                    files = [root / 'autosave.pkl.gz', root / 'session_state.json', *list((root / 'history').glob('*')),
                             root / 'mask_assets/mask_metal1/manifest.json', root / 'mask_assets/mask_metal1/revisions/1.json']
                    before = {path: path.read_bytes() for path in files if path.is_file()}
                    payload = {'step_index': 0, 'asset': _candidate()} if command.endswith('save_apply') else {
                        'step_index': 0, 'filename': 'mask.json', 'data': json.dumps(_candidate()).encode(),
                    }
                    conn = WorkerConnection([('get_recipe', {}), (command, payload), ('get_recipe', {})])
                    conn.before_first_recv = lambda: before.update({path: path.read_bytes() for path in files if path.is_file()})
                    original_fsync = store.fsync_directory
                    original_bind = tcad.ExposureStep.bind_mask_asset_service
                    def fsync(path):
                        original_fsync(path)
                        if (phase == 'revision' and path.name == 'revisions') or (phase == 'manifest' and path.name == 'mask_metal1'):
                            raise OSError('private publication failure')
                    def bind(step, service):
                        original_bind(step, service)
                        if phase == 'binding' and step.params.get('mask_mode') == 'Asset':
                            raise OSError('private binding failure')
                    with mock.patch.object(store, 'fsync_directory', side_effect=fsync), mock.patch.object(tcad.ExposureStep, 'bind_mask_asset_service', new=bind):
                        if phase == 'recipe':
                            with mock.patch.object(MaskApplyTransaction, 'commit', side_effect=OSError('private commit failure')):
                                tcad._webui_worker_main(conn, str(root), default_domain=DOMAIN)
                        else:
                            tcad._webui_worker_main(conn, str(root), default_domain=DOMAIN)
                    self.assertEqual(conn.responses[1].get('code'), 'mask_asset_apply_failed')
                    self.assertEqual(conn.responses[1].get('status'), 500)
                    self.assertNotIn('private', conn.responses[1]['error'])
                    self.assertTrue(conn.responses[2]['ok'])
                    self.assertEqual(conn.responses[2]['result'], conn.responses[0]['result'])
                    self.assertFalse((root / 'mask_assets/mask_metal1/revisions/2.json').exists())
                    for path, data in before.items():
                        self.assertEqual(path.read_bytes(), data)

    def test_killed_process_is_recovered_before_worker_loads_recipe(self):
        import tcad_simulator as tcad
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            setup = WorkerConnection([('save', {}), ('get_recipe', {})])
            tcad._webui_worker_main(setup, str(root), default_domain=DOMAIN)
            old_recipe = setup.responses[-1]['result']
            old_bytes = (root / 'autosave.pkl.gz').read_bytes()
            script = '''
import sys, time
from pathlib import Path
from mask_assets.transaction import MaskApplyTransaction
root = Path(sys.argv[1])
paths = [root / 'autosave.pkl.gz', root / 'mask_assets/a/manifest.json', root / 'mask_assets/a/revisions/1.json']
tx = MaskApplyTransaction(root)
tx.begin(paths)
for path in paths:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'partial transaction')
print('ready', flush=True)
time.sleep(60)
'''
            process = subprocess.Popen([sys.executable, '-c', script, str(root)], stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(process.stdout.readline().strip(), 'ready')
                process.kill()
                process.wait(timeout=10)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
                process.stdout.close()
            restarted = WorkerConnection([('get_recipe', {})])
            tcad._webui_worker_main(restarted, str(root), default_domain=DOMAIN)
            self.assertEqual(restarted.responses[0]['result'], old_recipe)
            self.assertEqual(gzip.decompress((root / 'autosave.pkl.gz').read_bytes()), gzip.decompress(old_bytes))
            self.assertFalse((root / 'mask_assets/a/manifest.json').exists())
            self.assertFalse((root / '.mask-apply-pending.json').exists())

    def test_success_response_has_durable_recipe_and_survives_restart(self):
        import tcad_simulator as tcad
        from tests.test_mask_assets import _candidate
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class DurableResponseConnection(WorkerConnection):
                def send(self, value):
                    if value.get('ok') and isinstance(value.get('result'), dict) and 'asset' in value['result']:
                        blob = tcad._webui_pickle_load(root / 'autosave.pkl.gz')
                        self_test.assertEqual(blob['steps_full'][0]['params']['mask_asset_revision'], 1)
                        recipe_path = root / 'history' / (blob['recipe_id'] + '.autosave.pkl.gz')
                        self_test.assertEqual(tcad._webui_pickle_load(recipe_path)['steps_full'][0]['params']['mask_asset_id'], 'mask_metal1')
                        self_test.assertFalse((root / '.mask-apply-pending.json').exists())
                    super().send(value)
            self_test = self
            conn = DurableResponseConnection([
                ('recipe_insert_steps', {'steps': [{'name': 'Mask Exposure'}], 'insert_index': -1, 'no_autosave': True}),
                ('mask_asset_save_apply', {'step_index': 0, 'asset': _candidate()}),
            ])
            tcad._webui_worker_main(conn, str(root), default_domain=DOMAIN)
            self.assertTrue(conn.responses[-1]['ok'])
            restarted = WorkerConnection([('get_recipe', {})])
            tcad._webui_worker_main(restarted, str(root), default_domain=DOMAIN)
            self.assertEqual(restarted.responses[0]['result'][0]['params']['mask_asset_revision'], 1)

    def test_recovery_rejects_escaping_and_symlink_paths(self):
        from mask_assets.transaction import MaskApplyTransaction
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # No external file is required: a forged journal must be rejected
            # before attempting any target read, removal, or replacement.
            (root / '.mask-apply-pending.json').write_text(json.dumps({'../outside-mask-transaction': False}))
            with self.assertRaises(ValueError):
                MaskApplyTransaction(root).recover()
            (root / '.mask-apply-pending.json').unlink()
            (root / 'escape').symlink_to(root.parent, target_is_directory=True)
            tx = MaskApplyTransaction(root)
            tx.begin()
            with self.assertRaises(ValueError):
                tx.capture(root / 'escape/outside-mask-transaction')
