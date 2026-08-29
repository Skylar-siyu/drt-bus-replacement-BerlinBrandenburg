# Reconstruction provenance

The code in this folder was reconstructed and validated on 29 August 2026
against the three supplied packages below.  They are not included in this code
folder.  A local file can be renamed freely; the SHA-256 digest identifies its
contents.

| Supplied package | Bytes | SHA-256 |
|---|---:|---|
| `ABC_analysis_results_01_04.tar(2).gz` | 495,809,442 | `a611c08d3c873c86b73268ff5aee64fb0fe44183b00f4e27e0c5df97b675fb73` |
| `ressultfinal.zip` | 25,079,565 | `a37f1e2045de15f42411f2a01a8f925d0c594b656dfbf5c6afdf470d086a2cfc` |
| `Figure_3_1_B5_B10_source_code.zip` | 16,669 | `48a456f9cf4a96494fcaa3ba5e3b91a30dd64c7d754b46c1b3add9c74b514ad1` |

## Checks performed

- The analysis archive passed `validate_analysis_source.py` and was read both
  as an archive and as an extracted `analysis_results` directory.
- The one-command non-spatial pipeline generated 25 readable PNGs: Figures
  4.1–4.14, 5.1–5.3, B.1–B.4 and B.6–B.9.
- Main-figure calculations were also spot-tested by reading the 495.8 MB tar
  archive directly; the appendix generator completed a full direct-archive run.
- `ressultfinal.zip` contained 27 reference PNGs: 3.1, 4.1–4.14, 5.1–5.3 and
  B.2–B.10.  It did not contain B.1.  Figure B.1 was reconstructed from the
  final dissertation caption and documented calculation.
- The three map scripts passed compilation and analytical input-schema tests.
  End-to-end map execution was not possible because the exact external OSM,
  Berlin-boundary and MATSim baseline files were not supplied.

See `README.md` for the remaining Figure B.6 and cartographic provenance
limitations.
