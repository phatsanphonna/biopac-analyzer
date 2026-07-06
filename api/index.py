import sys
import os

# Add the analyzer folder to python path so we can import its modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "analyzer")))

from server import app
