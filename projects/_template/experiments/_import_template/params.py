"""Parameters for importing a past result (see docs/importing-past-results.md).

Nothing here is typed from memory: hashes come from the generated manifest,
numbers from a cited source.
"""

from pathlib import Path

import config

# Every experiment pins a seed (unused unless the regeneration draws random numbers).
SEED = 42

HERE = Path(__file__).resolve().parent
# Past outputs, copied by the user on the host (raw data is immutable and read-only in Docker).
# Data that must stay outside the repository may live under /external (EXTERNAL_FILES_DIR on
# the host); its manifest is then generated inside the container (run.py prints the command).
# Set SOURCE_DIR = None only when nothing but a publication survives (see TRANSCRIBED).
SOURCE_DIR = config.RAW_DATA_DIR / "legacy" / "<source>"
# sha256 manifest of SOURCE_DIR, committed next to this file (generate it; never type hashes).
MANIFEST = HERE / "inputs.sha256"
# Hashes the old tool recorded itself for files INSIDE SOURCE_DIR (manifest-relative path
# -> hex, e.g. from run_meta.json), checked against the manifest. A hash of input data
# (e.g. run_meta.json's ocean_data_sha256) does not go here: check it against the checksum
# in the data/README.md entry of that dataset under data/raw/<dataset>/.
RECORDED_SHA256: dict[str, str] = {}
# Numbers reported elsewhere (paper, old README) that the regenerated values must reproduce,
# e.g. {"rmse": {"value": 0.42, "atol": 0.005, "source": "smith2024ocean, Table 2"}}.
REFERENCE_VALUES: dict[str, dict] = {}
# Numbers that survive only in a publication: transcribed once, cited, and marked R3.
TRANSCRIBED: dict[str, float | int | str] = {}
TRANSCRIBED_SOURCE = ""  # e.g. "smith2024ocean, Table 2"
# Rounding of transcribed floats as printed in the source, e.g. {"rmse": "{:.2f}"}.
TRANSCRIBED_FORMATS: dict[str, str] = {}

# What experiment.start() records (out/params_used.json) and run.py reads (run.params).
PARAMS = {
    "source_dir": SOURCE_DIR,
    "manifest": MANIFEST,
    "recorded_sha256": RECORDED_SHA256,
    "reference_values": REFERENCE_VALUES,
    "transcribed": TRANSCRIBED,
    "transcribed_source": TRANSCRIBED_SOURCE,
    "transcribed_formats": TRANSCRIBED_FORMATS,
}
# --smoke runs every step on the same files and publishes nothing.
SMOKE: dict = {}
