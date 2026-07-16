"""
Hermetic tests for connector_registry: resolve, match, auto-detect, seed.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))
_sibling = _root.parent / "certops-dashboard"
if _sibling.exists() and str(_sibling) not in sys.path:
    sys.path.insert(0, str(_sibling))

from src import connector_registry


class TestGenericConnectorFallback(unittest.TestCase):
    def test_unknown_category_returns_generic_connector(self):
        row = {
            "name": "mystery-connector",
            "category": "unknown_type",
            "config": "{}",
            "renewal_threshold_days": 7.0,
        }
        c = connector_registry.resolve_connector(row)
        self.assertEqual(c.name, "mystery-connector")
        self.assertEqual(c.category, "unknown_type")
        self.assertEqual(c.renewal_threshold_days, 7.0)
