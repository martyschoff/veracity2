
import importlib.util, sys, subprocess
sys.argv = ['x']
spec = importlib.util.spec_from_file_location('mw', r'C:/Users/schof/veracity2/scripts/miro_worker.py')
mw = importlib.util.module_from_spec(spec); spec.loader.exec_module(mw)
fixture = r'C:/Users/schof/veracity-panel/backend/app/fixtures/marty_pred_20261001184623_b1d18cb100bd.json'
r = subprocess.run([mw.VPY, str(mw.RUNNER), '--claim-json', fixture, '--output', r'C:/Users/schof/veracity-panel/backend/app/fixtures/test_out.json', '--rounds', '2'], cwd=str(mw.PANEL), env=dict(mw.ENV_BASE), capture_output=True, text=True, timeout=1500)
open(r'C:/Users/schof/veracity2/data/delphi_test_run.log','w',encoding='utf-8').write(f'rc={r.returncode}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}')
print('DONE rc', r.returncode)
