import subprocess, time
while True:
    subprocess.run(['python', r'C:/Users/schof/veracity2/scripts/watchdog.py'], capture_output=True)
    time.sleep(300)
