"""Regression tests for the frozen ProcureHarness fresh package."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from validate_procureharness_fresh_package_v01 import (
    MANIFEST_PATH,
    validate_manifest,
)


class ProcureHarnessFreshPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_frozen_manifest_passes(self):
        validate_manifest(deepcopy(self.manifest))

    def test_validation_split_cannot_absorb_final_episode(self):
        mutated = deepcopy(self.manifest)
        mutated["validation_split"]["episode_ids"][-1] = (
            mutated["final_split"]["episode_ids"][0]
        )
        with self.assertRaisesRegex(ValueError, "031-040"):
            validate_manifest(mutated)

    def test_final_exposure_policy_cannot_weaken(self):
        mutated = deepcopy(self.manifest)
        mutated["final_split"]["exposure_policy"] = "may be inspected during search"
        with self.assertRaisesRegex(ValueError, "Final exposure policy"):
            validate_manifest(mutated)

    def test_frozen_blob_hash_cannot_change(self):
        mutated = deepcopy(self.manifest)
        mutated["frozen_files"][0]["git_blob_sha1"] = "0" * 40
        with self.assertRaisesRegex(
            ValueError,
            "Manifest hash does not match freeze commit",
        ):
            validate_manifest(mutated)


if __name__ == "__main__":
    unittest.main()
