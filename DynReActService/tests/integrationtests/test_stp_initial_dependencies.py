"""Cold-start regression: the browser must know STP callbacks before visiting STP."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class InitialStpDependenciesTest(unittest.TestCase):
    def test_oss_first_dependencies_and_unselected_fin01_orders(self):
        code = r'''
import os
from pathlib import Path
from dynreact.app_config import ConfigProvider
root = Path(os.environ['STP_TEST_ROOT'])
c = ConfigProvider.config
c.profile = None
c.auth_method = None
c.aggregation = False
c.stp_frontend = 'default'
c.config_provider = 'default+file:' + str(root / 'DynReActService/data/site.json')
c.snapshot_provider = 'default+file:' + str(root / 'DynReActService/data/snapshots')
Path('stp.json').write_text((root / 'DynReActService/data/stp_context.json').read_text())
c.short_term_planning = 'default+file:stp.json'
os.environ['SHORT_TERM_PLANNING_PARAMS'] = c.short_term_planning
from dynreact.gui.dash_app import app
client = app.server.test_client()
# This must be the first HTTP request: no prior page layout can register STP.
r = client.get('/_dash-dependencies')
assert r.status_code == 200
output = '..ag-cont_item-materials.children...ag-materials.options...ag-sect3.style...ag-materials.value..'
assert any(d['output'] == output for d in r.json), 'STP absent from initial dependencies'
import dash
for path in ['/stp', '/ltp', '/lots/create2']:
    assert any(p['path'] == path for p in dash.page_registry.values()), path
    assert client.get(path).status_code == 200, path
r = client.post('/_dash-update-component', json=dict(
    output=output,
    outputs=[dict(id=i, property=p) for i,p in [
        ('ag-cont_item-materials','children'),('ag-materials','options'),
        ('ag-sect3','style'),('ag-materials','value')]],
    inputs=[dict(id='ag-matypes',property='value',value='Orders'),
            dict(id='ag-resources',property='value',value=['FIN01'])],
    state=[],changedPropIds=['ag-resources.value']))
assert r.status_code == 200, r.data
selector = r.json['response']['ag-materials']
assert {o['value'] for o in selector['options']} == {'order3','order6'}, selector
assert selector['value'] == [], selector
'''
        env = os.environ.copy()
        env['STP_TEST_ROOT'] = str(ROOT)
        env['PYTHONPATH'] = os.pathsep.join(str(ROOT / p) for p in (
            'DynReActService', 'DynReActBase', 'SampleUseCase', 'ShortTermPlanning',
            'MidTermPlanning', 'LongTermPlanning'))
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run([sys.executable, '-c', code], cwd=cwd, env=env,
                                    text=True, capture_output=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
