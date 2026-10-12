r"""NNN_<slug>: <one-line purpose>.

Run from the repository root, first with --smoke (params.SMOKE, out/smoke/, nothing is
published), then without it; --overwrite replaces a completed run:

    docker compose exec research-template uv run python \
        projects/study1/experiments/NNN_<slug>/run.py \
        --smoke

Stages run cheapest first and the slow part last. Each stage calls src/; move a stage into
src/ (with a test) when it outgrows a screen or a second experiment needs it.
"""

import sys
from pathlib import Path

# Bootstrap: make the study root importable (config, src.*). Python puts this
# script's directory, not the study root, on sys.path. Do not remove.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

import config  # this study's paths; experiment.start() reads it too
import params

# Keep these imports at the top: the commit every result is credited to is read here.
from src.utils import experiment, figures, tables  # noqa: F401


def main() -> None:
    with experiment.start(__file__, params) as run:
        p = run.params  # params.PARAMS, with params.SMOKE applied under --smoke
        rng = np.random.default_rng(run.seed)
        figures.apply_visualization_defaults(config)  # the figure look shared by all chapters

        run.stage("load and check inputs")
        # Read inputs through config paths and loaders in src/, and check them here,
        # before anything expensive.

        run.stage("compute")
        sample = rng.standard_normal(p["n_samples"])  # placeholder so the template runs
        run.log(f"{sample.size} samples")

        run.stage("write outputs")
        summary = pd.DataFrame({"n": [sample.size], "mean": [sample.mean()]})
        summary.to_csv(run.out("sample_mean.csv"), index=False)  # working output, out/ only
        # What the thesis or another experiment uses is written here, in code. It is
        # staged under out/staged/ and reaches result/ only when a full run completes
        # (never with --smoke or after a failure). Names start with the study name:
        #   figures.save_figure(fig, "study1-overview", config)
        #   tables.write_latex_table(summary, "study1-summary", config)
        #   tables.write_latex_values(
        #       {"n": n, "rmse": rmse}, "study1-main", config,
        #       formats={"rmse": "{:.2f}"},
        #   )
        #   run.promote("study1-points.csv")  # a run.out() file
        #   run.promote("grid.nc", dest_dir=config.PROCESSED_DATA_DIR / run.name)  # large
        # Register a values file once in draft/values.tex; the text then writes
        # \val{study1-main-rmse}.
        # Presentation code (styling, layout) lives in src/ or in a scripts/ promotion
        # script that reads result/tables/*.csv or data/processed/ and names them with
        # sources=[...].


if __name__ == "__main__":
    main()
