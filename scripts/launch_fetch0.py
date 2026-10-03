import subprocess, sys
DETACHED = 0x00000008 | 0x00000200
lf = open(r"C:\Users\schof\veracity2\data\deepqa_fetch_0.log", "w")
subprocess.Popen([sys.executable, r"C:\Users\schof\veracity2\scripts\deepqa_fetch.py", "--shard", "0"],
                 stdout=lf, stderr=subprocess.STDOUT, cwd=r"C:\Users\schof\veracity2",
                 creationflags=DETACHED, close_fds=True)
print("launched shard0")
