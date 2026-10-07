# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
import subprocess, sys
DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
log = r"C:\Users\schof\veracity2\data\classify_all.log"
with open(log, "w") as lf:
    subprocess.Popen([sys.executable, r"C:\Users\schof\veracity2\scripts\classify_all.py"],
                     stdout=lf, stderr=subprocess.STDOUT, cwd=r"C:\Users\schof\veracity2",
                     creationflags=DETACHED, close_fds=True)
print("launched")
