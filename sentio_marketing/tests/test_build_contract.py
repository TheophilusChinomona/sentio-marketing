"""Regression checks for cached/missing app manifests; no Docker daemon needed."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BuildContractTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "deploy/apps.json").read_text())
        self.digest = hashlib.sha256(
            json.dumps(self.manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.dockerfile = (ROOT / "deploy/Containerfile").read_text()

    def guard(self, manifest):
        code = re.search(r"python -c '(.*?)' &&", self.dockerfile, re.S).group(1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "apps.json"
            path.write_text(json.dumps(manifest))
            code = code.replace('"/opt/frappe/apps.json"', repr(str(path)))
            return subprocess.run(
                [sys.executable, "-c", code],
                env=dict(os.environ, CACHE_BUST=self.digest),
                text=True,
                capture_output=True,
            )

    def test_guard_accepts_exact_public_manifest(self):
        self.assertEqual(self.guard(self.manifest).returncode, 0)

    def test_previous_one_app_manifest_fails_with_actionable_error(self):
        r = self.guard([{"url": "https://github.com/frappe/crm", "branch": "v16.0.3"}])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("FRAPPE_APPS_JSON does not match", r.stderr)

    def test_cache_key_is_tied_to_manifest(self):
        compose = (ROOT / "deploy/compose.yaml").read_text()
        self.assertIn(self.digest, compose)
        changed = [dict(x) for x in self.manifest]
        changed[1]["branch"] = "different-release"
        self.assertNotEqual(self.guard(changed).returncode, 0)

    def test_missing_secret_and_missing_apps_cannot_succeed(self):
        self.assertIn("id=apps_json", self.dockerfile)
        self.assertIn("required=true", self.dockerfile)
        self.assertIn(
            "test -d apps/crm && test -d apps/sentio_marketing", self.dockerfile
        )
        self.assertIn("import crm, sentio_marketing", self.dockerfile)

    def test_inline_dockerfile_is_compose_safe(self):
        self.assertNotIn("$", self.dockerfile)
        self.assertTrue(self.dockerfile.startswith("# syntax="))


if __name__ == "__main__":
    unittest.main()
