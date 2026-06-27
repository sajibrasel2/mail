import sys
import os

project_root = os.path.dirname(__file__)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from app import app as application
except Exception:
    try:
        from app import application
    except Exception as exc:
        raise
import sys
import os

# Add the app directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

from app import app as application
