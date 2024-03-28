import os
import sys
sys.path.append(os.path.dirname(__file__))
from homewatch.server import create_app
application = create_app(False)