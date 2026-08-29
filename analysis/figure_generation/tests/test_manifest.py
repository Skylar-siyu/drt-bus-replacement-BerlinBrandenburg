from pathlib import Path
import csv


ROOT = Path(__file__).resolve().parents[1]


def test_manifest_covers_complete_thesis_set():
    with (ROOT / "FIGURE_MANIFEST.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    expected = (
        {"3.1"}
        | {f"4.{i}" for i in range(1, 15)}
        | {f"5.{i}" for i in range(1, 4)}
        | {f"B.{i}" for i in range(1, 11)}
    )
    assert len(rows) == 28
    assert {row["figure"] for row in rows} == expected
    assert len({row["output_file"] for row in rows}) == 28


def test_manifest_generators_exist():
    with (ROOT / "FIGURE_MANIFEST.csv").open(newline="", encoding="utf-8") as handle:
        generators = {row["generator"] for row in csv.DictReader(handle)}
    assert all((ROOT / generator).is_file() for generator in generators)
