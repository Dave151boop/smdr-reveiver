import re
from pathlib import Path

def test_inno_setup_script_contains_nssm():
    path = Path('installer/SMDR.iss')
    assert path.exists()
    txt = path.read_text()
    assert re.search(r'\bnssm\.exe\b', txt)
    assert 'install SMDR' in txt
