"""Guard workflow configuration without adding runtime or test dependencies."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = (ROOT / '.github/workflows/lees-pdf-release.yml').read_text(encoding='utf-8')


def job(name):
    return re.search(r'^  ' + re.escape(name) + r':\n(.*?)(?=^  [^ \n]+:|\Z)', WORKFLOW, re.M | re.S)[1]


class PipelineTests(unittest.TestCase):
    def test_release_prepares_dependencies_on_runner_without_private_archives(self):
        build = job('build')
        self.assertNotIn('runtime_tag:', WORKFLOW)
        self.assertNotIn('RUNTIME_SHA256:', build)
        self.assertIn("PYTHONUTF8: '1'", build)
        self.assertIn('SOURCE_TAG: ${{ inputs.tag }}', build)
        self.assertIn('runtime.ps1 -SourceRoot private-source', build)
        runtime = (ROOT / 'release-tools/lees-pdf/runtime.ps1').read_text(encoding='utf-8')
        self.assertNotIn('gh release download', runtime)
        self.assertIn('prepare-windows.ps1', runtime)
        self.assertIn('scripts/release/prepare-macos.sh', runtime)
        self.assertIn('LEESPDF_RUNTIME_INDEX_SHA256=', runtime)
        publisher = (ROOT / 'release-tools/lees-pdf/build.ps1').read_text(encoding='utf-8')
        self.assertIn('$seedIndex.sourceRevision -ne $revision', publisher)
        self.assertIn('Assert-LeesPdfNativeSources', publisher)
        self.assertNotIn('LEESPDF_RUNTIME_SOURCE_INDEX', publisher)
    def test_temurin_separate_jmods_remain_version_and_hash_pinned(self):
        windows = (ROOT / 'release-tools/lees-pdf/prepare-windows.ps1').read_text(encoding='utf-8')
        self.assertIn('OpenJDK25U-jmods_x64_windows_hotspot_25.0.4.1_1.zip', windows)
        self.assertIn('c6b6b19ba9ab28bb4c15b936a7cef40dedcd99ab69f69109dcb0ffad805f0847', windows)
        self.assertIn("'java.base@25.0.4.1'", windows)
        jdk = (ROOT / 'release-tools/lees-pdf/prepare-jdk.ps1').read_text(encoding='utf-8')
        self.assertIn("'lib/modules'", jdk)
        self.assertNotIn("'jmods/java.base.jmod'", jdk)

    def test_promotion_skips_staging_and_uses_one_verified_release_operation(self):
        self.assertIn('!inputs.promote', job('mirror'))
        promotion = job('promote')
        self.assertIn("needs.mirror.result == 'skipped'", promotion)
        self.assertEqual(promotion.count('gh release download'), 1)
        self.assertIn('mirror.py release public-output', promotion)
        self.assertNotIn('mirror.py cleanup', promotion)
        self.assertIn('--draft=false --latest=false', promotion)
        self.assertNotIn('readiness-r2.json lees-pdf-build-status', promotion)

    def test_normal_release_and_promotion_retry_gate(self):
        condition = re.search(r"^    if: \$\{\{ (.*?) \}\}$", job('promote'), re.M)[1]
        for promote in (False, True):
            for validation in ('success', 'failure', 'cancelled', 'skipped'):
                for mirror in ('success', 'failure', 'cancelled', 'skipped'):
                    expression = condition.replace('always()', 'True')
                    expression = expression.replace('inputs.promote', str(promote))
                    expression = expression.replace('needs.validate.result', repr(validation))
                    expression = expression.replace('needs.mirror.result', repr(mirror))
                    expression = expression.replace('&&', ' and ').replace('||', ' or ')
                    expression = re.sub(r'!(?!=)', ' not ', expression)
                    actual = eval(expression.strip(), {'__builtins__': {}}, {})
                    expected = validation == 'success' and mirror == ('skipped' if promote else 'success')
                    with self.subTest(promote=promote, validation=validation, mirror=mirror):
                        self.assertEqual(actual, expected)

    def test_cache_contains_only_public_registry_archives(self):
        build = job('build')
        self.assertEqual(build.count('uses: actions/cache@'), 1)
        cache = build.split('uses: actions/cache@', 1)[1].split('      - ', 1)[0]
        paths = re.findall(r'^          path: (.*)$', cache, re.M)
        self.assertEqual(paths, ['${{ env.CARGO_HOME }}/registry/cache/index.crates.io-*/*.crate'])
        for name in ('mirror', 'promote'):
            self.assertEqual(job(name).count('wrangler@4.151.0'), 1)
            self.assertIn('LEESPDF_WRANGLER_CLI=', job(name))


if __name__ == '__main__':
    unittest.main()
