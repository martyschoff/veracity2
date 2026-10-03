import subprocess, sys
DETACHED = 0x00000008 | 0x00000200
for k, name in enumerate(["nimo128", "local", "mac"]):
    log = rf"C:\Users\schof\veracity2\data\classify_{name}.log"
    lf = open(log, "w")
    subprocess.Popen([sys.executable, r"C:\Users\schof\veracity2\scripts\classify_worker.py",
                      "--shard", str(k)],
                     stdout=lf, stderr=subprocess.STDOUT, cwd=r"C:\Users\schof\veracity2",
                     creationflags=DETACHED, close_fds=True)
    print("launched", k)
