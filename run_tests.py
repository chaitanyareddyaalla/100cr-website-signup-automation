#!/usr/bin/env python
import subprocess
import sys

result = subprocess.run([
    sys.executable, "-m", "pytest", 
    "tests/test_api.py", 
    "-q", "--tb=short"
], cwd=r"c:\Users\chait\Desktop\task-automation")

sys.exit(result.returncode)
