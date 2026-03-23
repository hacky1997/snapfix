import sys
import pathlib

# Add the src directory relative to this conftest so pytest can find snapfix
# regardless of where the repo is cloned.
_src = pathlib.Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))
