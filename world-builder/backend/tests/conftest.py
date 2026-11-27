"""Every test writes into a throwaway data folder, set before the app is imported."""

import os
import sys
import tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="world-builder-tests-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
