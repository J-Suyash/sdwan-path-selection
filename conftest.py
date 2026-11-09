# Make the repository root importable regardless of entry point
# (uv run pytest, python -m pytest, IDE runners). Tests import the
# emulator, offline and testbed packages directly from the tree.
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
