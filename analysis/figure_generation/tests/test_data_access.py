from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_access import AnalysisStore, bool_series  # noqa: E402


def test_bool_series_handles_text_false():
    values = pd.Series([True, False, "true", "False", 1, 0, None])
    assert bool_series(values).tolist() == [True, False, True, False, True, False, False]


def test_directory_store(tmp_path):
    root = tmp_path / "analysis_results"
    (root / "04_RQ_outputs").mkdir(parents=True)
    (root / "02_scenarios").mkdir()
    pd.DataFrame({"x": [1, 2]}).to_csv(root / "04_RQ_outputs" / "tiny.csv", index=False)
    pd.DataFrame({"scenario": ["A8_FM"]}).to_csv(
        root / "02_scenarios" / "analysis_inventory.csv", index=False
    )
    with AnalysisStore(tmp_path) as store:
        assert store.rq("tiny.csv")["x"].sum() == 3
        assert store.available_scenarios() == ["A8_FM"]
