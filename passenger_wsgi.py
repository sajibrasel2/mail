import os
import sys

project_root = os.path.dirname(__file__)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app import app as application
