import subprocess
r = subprocess.run(["powershell","-NoProfile","-Command",
 "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
 "Where-Object { $_.CommandLine -like '*classify_steal*' } | "
 "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Output ('killed ' + $_.ProcessId) }"],
 capture_output=True, text=True)
print(r.stdout, r.stderr)
