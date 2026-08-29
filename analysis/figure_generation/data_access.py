"""Portable access to the dissertation ``analysis_results`` tree.

The analysis archive is intentionally not committed to GitHub.  ``AnalysisStore``
therefore accepts either an extracted ``analysis_results`` directory or the
original ``ABC_analysis_results_01_04.tar.gz`` file and exposes the same API.
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path, PurePosixPath
import gzip
import tarfile

import pandas as pd


class AnalysisStore:
    """Read CSV inputs from a directory or a ``.tar(.gz)`` archive."""

    def __init__(self, source: str | Path):
        self.source = Path(source).expanduser().resolve()
        if not self.source.exists():
            raise FileNotFoundError(f"Analysis source does not exist: {self.source}")
        self._archive: tarfile.TarFile | None = None
        self._members: dict[str, str] = {}
        if self.source.is_dir():
            self.root = self._find_directory_root(self.source)
            self.kind = "directory"
        else:
            if not tarfile.is_tarfile(self.source):
                raise ValueError(
                    "--analysis-source must be an extracted analysis_results "
                    "directory or a tar/tar.gz archive"
                )
            self.kind = "archive"
            self.root = None
            self._archive = tarfile.open(self.source, mode="r:*")
            for member in self._archive.getmembers():
                if not member.isfile():
                    continue
                normalized = self._normalise_archive_name(member.name)
                self._members[normalized] = member.name

    @staticmethod
    def _find_directory_root(path: Path) -> Path:
        candidates = [path, path / "analysis_results"]
        for candidate in candidates:
            if (candidate / "04_RQ_outputs").is_dir():
                return candidate
        for candidate in path.glob("*/analysis_results"):
            if (candidate / "04_RQ_outputs").is_dir():
                return candidate
        raise FileNotFoundError(
            f"Could not find analysis_results/04_RQ_outputs below {path}"
        )

    @staticmethod
    def _normalise_archive_name(name: str) -> str:
        parts = list(PurePosixPath(name).parts)
        if "analysis_results" in parts:
            parts = parts[parts.index("analysis_results") + 1 :]
        while parts and parts[0] in {".", ""}:
            parts.pop(0)
        return "/".join(parts)

    def close(self) -> None:
        if self._archive is not None:
            self._archive.close()
            self._archive = None
        self._csv_cached.cache_clear()

    def __enter__(self) -> "AnalysisStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def exists(self, relative: str | Path) -> bool:
        key = PurePosixPath(relative).as_posix()
        if self.kind == "directory":
            assert self.root is not None
            return (self.root / key).is_file()
        return key in self._members

    def bytes(self, relative: str | Path) -> bytes:
        key = PurePosixPath(relative).as_posix()
        if self.kind == "directory":
            assert self.root is not None
            return (self.root / key).read_bytes()
        if key not in self._members:
            raise FileNotFoundError(f"Archive member not found: {key}")
        assert self._archive is not None
        handle = self._archive.extractfile(self._members[key])
        if handle is None:
            raise FileNotFoundError(f"Could not read archive member: {key}")
        return handle.read()

    def _read_csv(self, relative: str, **kwargs: object) -> pd.DataFrame:
        key = PurePosixPath(relative).as_posix()
        if self.kind == "directory":
            assert self.root is not None
            return pd.read_csv(self.root / key, **kwargs)
        else:
            raw = self.bytes(key)
            if key.endswith(".gz"):
                raw = gzip.decompress(raw)
            return pd.read_csv(BytesIO(raw), **kwargs)

    @lru_cache(maxsize=96)
    def _csv_cached(self, relative: str) -> pd.DataFrame:
        return self._read_csv(relative)

    def csv(self, relative: str, **kwargs: object) -> pd.DataFrame:
        """Read a CSV and return a caller-owned data frame.

        Default reads are cached, which matters when repeatedly reading a tar
        archive.  Calls with pandas keyword arguments are intentionally not
        cached because options such as ``usecols`` may be unhashable.
        """

        if kwargs:
            return self._read_csv(relative, **kwargs)
        return self._csv_cached(relative).copy()

    def scenario(self, scenario: str, filename: str, **kwargs: object) -> pd.DataFrame:
        return self.csv(f"02_scenarios/{scenario}/{filename}", **kwargs)

    def rq(self, filename: str, **kwargs: object) -> pd.DataFrame:
        return self.csv(f"04_RQ_outputs/{filename}", **kwargs)

    def available_scenarios(self) -> list[str]:
        inventory = self.csv("02_scenarios/analysis_inventory.csv")
        column = "scenario" if "scenario" in inventory else inventory.columns[0]
        return sorted(inventory[column].dropna().astype(str).unique().tolist())


def scenario_case(scenario: str) -> str:
    case = str(scenario).strip().upper()[:1]
    if case not in {"A", "B", "C"}:
        raise ValueError(f"Cannot infer case from scenario {scenario!r}")
    return case


def bool_series(series: pd.Series) -> pd.Series:
    """Coerce CSV booleans robustly (MATSim exports may contain strings)."""

    if series.dtype == bool:
        return series.fillna(False)
    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .isin({"true", "1", "yes", "y", "t"})
    )
