import os
import sys

# Resolve project paths and add scripts directory to system path
api_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(api_dir)
sys.path.append(os.path.join(project_root, "scripts"))

# Import the Flask app instance
from linkedin_dashboard import app
