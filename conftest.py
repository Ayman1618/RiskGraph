"""
Root conftest.py — ensures the project root is on sys.path so that
'from src.xxx import yyy' imports work in CI without 'pip install -e .'.
"""
import sys
from pathlib import Path

# Insert project root at the front of sys.path so all 'src.*' imports resolve
# regardless of whether the package was installed in editable mode.
ROOT = Path(__file__).parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
