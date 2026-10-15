"""Exercise production release ordering with mock stores, after the signature boundary."""
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('pdf_mirror', SCRIPTS / 'mirror.py')
mirror = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        parent = Path(os.environ.get('LEES_TEST_OUTPUT', Path(tempfile.gettempdir()) / 'lees-pdf-release-tests'))
        parent.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(dir=parent))
        self.environment = patch.dict(os.environ, {'PUBLIC_TAG': 'lees-pdf-v1.0.1', 'GITHUB_RUN_ID': '42',
                                                   'COS_PUBLIC_BASE_URL': 'https://cos.example/'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        name = 'lees-pdf-test-setup.exe'
        data = b'public test installer'
        (self.root / name).write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        self.asset = {'path': 'lees-pdf/releases/1.0.1/' + name, 'size': len(data), 'sha256': sha,
                      'signature': 'test-package-signature'}
        self.payload = {'version': '1.0.1', 'releaseId': 'lees-pdf-v1.0.1',
                        'platforms': {target: {'updaterArtifact': self.asset, 'installerArtifact': self.asset}
                                      for target in ('darwin-aarch64', 'windows-x86_64')}}
        self.verified = {'payload': self.payload, 'payloadSha256': 'a' * 64}
        (self.root / 'release-manifest.json').write_text(json.dumps({'release': {'testBoundary': True}}), encoding='utf-8')
        (self.root / 'SHA256SUMS').write_text(f'{sha}  {name}\n', encoding='utf-8')
        self.verifier = patch.object(mirror, 'verified_manifest', return_value=self.verified)
        self.verify_mock = self.verifier.start()
        self.addCleanup(self.verifier.stop)
        self.release = mirror.Release(self.root)
        self.store, self.reads, self.writes, self.deleted = {}, [], [], []
        for source in ('cos', 'r2'):
            for key, file in self.release.files.items():
                self.store[mirror.base(source) + key] = file.read_bytes()
            self.store[mirror.base(source) + self.release.prefix + 'release-manifest.json'] = self.release.metadata(source)

    def digest(self, url):
        self.reads.append(url)
        data = self.store.get(url)
        return None if data is None else (hashlib.sha256(data).hexdigest(), len(data))

    def put(self, source, key, file, mutable=False):
        self.writes.append((source, key))
        self.store[mirror.base(source) + key] = file.read_bytes()

    def run_release(self, put=None, prune=None):
        with patch.object(mirror, 'public_digest', side_effect=self.digest), \
             patch.object(mirror, 'put', side_effect=put or self.put), \
             patch.object(mirror, 'prune', side_effect=prune or (lambda *args: self.deleted.append(args))), \
             patch.object(self.release, 'check_previous'):
            self.release.publish()

    def test_both_sources_verified_before_pointers_and_cleanup(self):
        def checked_put(source, key, file, mutable=False):
            for target in ('cos', 'r2'):
                self.assertIn(mirror.base(target) + self.asset['path'], self.reads)
            self.put(source, key, file, mutable)
        self.run_release(put=checked_put)
        self.assertEqual(self.writes, [('cos', 'latest-lees-pdf.json'), ('r2', 'latest-lees-pdf.json')])
        self.assertEqual(len(self.deleted), 1)
        for source in ('cos', 'r2'):
            self.assertEqual(self.reads.count(mirror.base(source) + self.asset['path']), 2)
            readiness = json.loads((self.root / f'readiness-{source}.json').read_text())
            self.assertEqual(readiness['runId'], '42')

    def test_missing_backup_blocks_all_writes_and_cleanup(self):
        self.store.pop(mirror.base('r2') + self.asset['path'])
        with self.assertRaisesRegex(RuntimeError, 'asset'):
            self.run_release()
        self.assertFalse(self.writes)
        self.assertFalse(self.deleted)

    def test_changed_immutable_manifest_blocks_promotion(self):
        self.store[mirror.base('cos') + self.release.prefix + 'release-manifest.json'] = b'changed'
        with self.assertRaisesRegex(RuntimeError, 'manifest'):
            self.run_release()
        self.assertFalse(self.writes)

    def test_second_pointer_failure_never_prunes(self):
        def fail_backup(source, key, file, mutable=False):
            if source == 'r2':
                raise RuntimeError('backup pointer failed')
            self.put(source, key, file, mutable)
        with self.assertRaisesRegex(RuntimeError, 'backup pointer'):
            self.run_release(put=fail_backup)
        self.assertFalse(self.deleted)

    def test_post_cleanup_detects_current_asset_damage(self):
        def damage(*args):
            self.store[mirror.base('cos') + self.asset['path']] = b'broken'
        with self.assertRaisesRegex(RuntimeError, 'asset'):
            self.run_release(prune=damage)

    def test_local_package_tamper_is_rejected(self):
        (self.root / Path(self.asset['path']).name).write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError, 'artifact'):
            mirror.Release(self.root)

    def test_prior_downgrade_and_same_version_conflict_are_rejected(self):
        for version, digest in [('1.0.2', 'a' * 64), ('1.0.1', 'b' * 64)]:
            with self.subTest(version=version), \
                 patch.object(mirror.urllib.request, 'build_opener') as opener:
                opener.return_value.open.side_effect = lambda *args, **kwargs: io.BytesIO(b'prior signed manifest')
                self.verify_mock.return_value = {'payload': {'version': version}, 'payloadSha256': digest}
                with self.assertRaisesRegex(RuntimeError, 'downgrade or conflicting'):
                    self.release.check_previous()

    def test_invalid_prior_signature_blocks_pointer_writes(self):
        with patch.object(mirror.urllib.request, 'build_opener') as opener, \
             patch.object(mirror, 'public_digest', side_effect=self.digest), \
             patch.object(mirror, 'put', side_effect=self.put), patch.object(mirror, 'prune') as prune:
            opener.return_value.open.side_effect = lambda *args, **kwargs: io.BytesIO(b'bad signed manifest')
            self.verify_mock.side_effect = RuntimeError('signature invalid')
            with self.assertRaisesRegex(RuntimeError, 'signature invalid'):
                self.release.publish()
            self.assertFalse(self.writes)
            prune.assert_not_called()

    def test_standalone_cleanup_verifies_assets_before_pruning(self):
        for source in ('cos', 'r2'):
            self.store[mirror.base(source) + 'latest-lees-pdf.json'] = self.release.metadata(source)
        self.store.pop(mirror.base('r2') + self.asset['path'])
        with patch.object(mirror, 'public_digest', side_effect=self.digest), patch.object(mirror, 'prune') as prune:
            with self.assertRaisesRegex(RuntimeError, 'asset'):
                self.release.cleanup()
            prune.assert_not_called()

    def test_unsafe_signed_asset_path_is_rejected(self):
        self.asset['path'] = self.release.prefix + 'bad\\asset.exe'
        with self.assertRaisesRegex(RuntimeError, 'Unsafe asset'):
            mirror.Release(self.root)

    def test_r2_uses_preinstalled_cli_and_checks_public_readback(self):
        file = self.root / Path(self.asset['path']).name
        expected = (self.asset['sha256'], self.asset['size'])
        with patch.dict(os.environ, {'LEESPDF_WRANGLER_CLI': '/tools/wrangler.js', 'CF_ACCOUNT_ID': 'test-account',
                                     'CF_API_TOKEN': 'synthetic-token', 'R2_BUCKET': 'test-bucket'}), \
             patch.object(mirror, 'public_digest', side_effect=[None, expected]), \
             patch.object(mirror.subprocess, 'run') as command:
            mirror.put('r2', self.asset['path'], file)
            self.assertEqual(command.call_args.args[0][:5], ['node', '/tools/wrangler.js', 'r2', 'object', 'put'])
            self.assertTrue(command.call_args.kwargs['check'])

    def test_immutable_conflict_never_uploads(self):
        with patch.object(mirror, 'public_digest', return_value=('changed', 1)), \
             patch.object(mirror.subprocess, 'run') as command:
            with self.assertRaisesRegex(RuntimeError, 'Immutable'):
                mirror.put('r2', self.asset['path'], self.root / Path(self.asset['path']).name)
            command.assert_not_called()

    def test_wrong_public_readback_fails_upload(self):
        with patch.dict(os.environ, {'LEESPDF_WRANGLER_CLI': '/tools/wrangler.js', 'CF_ACCOUNT_ID': 'test-account',
                                     'CF_API_TOKEN': 'synthetic-token', 'R2_BUCKET': 'test-bucket'}), \
             patch.object(mirror, 'public_digest', side_effect=[None, ('wrong', 1)]), \
             patch.object(mirror.subprocess, 'run'):
            with self.assertRaisesRegex(RuntimeError, 'readback'):
                mirror.put('r2', self.asset['path'], self.root / Path(self.asset['path']).name)


if __name__ == '__main__':
    unittest.main()
