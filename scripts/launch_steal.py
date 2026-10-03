import subprocess, sys
DETACHED = 0x00000008 | 0x00000200
lf = open(r"C:\Users\schof\veracity2\data\classify_steal_mac.log", "w")
subprocess.Popen([sys.executable, r"C:\Users\schof\veracity2\scripts\classify_steal.py",
                  "--slot", "mac", "--ep", "2"],
                 stdout=lf, stderr=subprocess.STDOUT, cwd=r"C:\Users\schof\veracity2",
                 creationflags=DETACHED, close_fds=True)
print("launched steal mac")
