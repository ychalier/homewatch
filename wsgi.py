import os
import sys
from pathlib import Path
sys.path.append(os.path.dirname(__file__))
from homewatch.settings import Settings
from homewatch.server import create_app
default_config = Path(__file__).parent / "default.toml"
settings = Settings.from_file(os.environ.get("HOMEWATCH_CONFIG", str(default_config)))
application = create_app(settings, False)
