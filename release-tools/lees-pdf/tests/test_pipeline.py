"""Guard workflow configuration without adding runtime or test dependencies."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = (ROOT / '.github/workflows/lees-pdf-release.yml').read_text(encoding='utf-8')


def job(name):
    return re.search(r'^  ' + re.escape(name) + r':\n(.*?)(?=^  [^ \n]+:|\Z)', WORKFLOW, re.M | re.S)[1]


class PipelineTests(unittest.TestCase):
    def test_promotion_skips_staging_and_uses_one_verified_release_operation(self):
        self.assertIn('!inputs.promote', job('mirror'))
        promotion = job('promote')
        self.assertIn("needs.mirror.result == 'skipped'", promotion)
        self.assertEqual(promotion.count('gh release download'), 1)
        self.assertIn('mirror.py release public-output', promotion)
        self.assertNotIn('mirror.py cleanup', promotion)
        self.assertIn('--draft=false --latest=false', promotion)
        self.assertNotIn('readiness-r2.json lees-pdf-build-status', promotion)

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
