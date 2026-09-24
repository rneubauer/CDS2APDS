import sys
from pathlib import Path

# Make the test helpers (fake_upstream) importable as plain modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))
