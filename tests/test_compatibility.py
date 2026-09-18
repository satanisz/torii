"""Verify old notebook/model module paths after the product rename."""

import importlib.util
import sys
import unittest
from pathlib import Path

SCAFFOLD = Path(__file__).resolve().parents[1] / "scaffold"
sys.path.insert(0, str(SCAFFOLD / "src"))


class NamespaceCompatibilityTests(unittest.TestCase):
    def test_old_and_new_imports_resolve_the_same_workspace(self):
        from automl_project.config import PROJECT_ROOT as legacy_root
        from torii_project.config import PROJECT_ROOT

        self.assertEqual(PROJECT_ROOT, SCAFFOLD)
        self.assertEqual(legacy_root, PROJECT_ROOT)

    def test_saved_model_and_notebook_module_paths_remain_discoverable(self):
        # Finding module specs does not import the heavy ML dependencies.
        for module in ("automl.pyfunc", "automl.mvp", "automl.demo", "modeling.train"):
            with self.subTest(module=module):
                old = importlib.util.find_spec(f"automl_project.{module}")
                new = importlib.util.find_spec(f"torii_project.{module}")
                self.assertIsNotNone(old)
                self.assertIsNotNone(new)
                self.assertEqual(old.origin, new.origin)


if __name__ == "__main__":
    unittest.main()
