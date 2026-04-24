
import sys
import os
sys.path.append(os.getcwd() + '/backend')
from main import app

for route in app.routes:
    print(f"{route.path} [{', '.join(route.methods)}]")
