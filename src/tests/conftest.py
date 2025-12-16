"""Test configuration for pytest.

Ensure the repository root is on sys.path so tests can import the `src` package
without needing PYTHONPATH set externally.
"""
import os
import sys

# Compute project root: two directories above this file (src/tests -> src -> project root)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
