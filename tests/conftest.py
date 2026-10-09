"""測試不得寫進真實的 Exa 月用量檔（~/.cache/vera-research），否則警示會被測試灌數。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


@pytest.fixture(autouse=True)
def _isolate_exa_usage(tmp_path, monkeypatch):
    import reach
    monkeypatch.setattr(reach, "EXA_USAGE_DIR", str(tmp_path))
