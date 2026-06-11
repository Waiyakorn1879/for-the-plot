import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "skills" / "renpy-translation" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

FIXTURES = Path(__file__).parent / "fixtures"
