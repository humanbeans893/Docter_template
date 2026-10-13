r"""NNN_<slug>: import a past result into this study.

Run from the repository root, first with --smoke (it verifies, regenerates and checks, and
publishes nothing), then without it; --overwrite replaces a completed run:

    docker compose exec research-template uv run python \
        projects/study1/experiments/NNN_<slug>/run.py \
        --smoke

Order: verify the copied past files against inputs.sha256, regenerate what the thesis uses
under out/, check the numbers against the reported ones, then write the artifacts. A failed
check fails the run, and result/ stays as it was. See docs/importing-past-results.md.
"""

import csv
import sys
from pathlib import Path

# Bootstrap: make the study root importable (config, src.*). Python puts this
# script's directory, not the study root, on sys.path. Do not remove.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import config  # this study's paths; experiment.start() reads it too
import params

# Keep these imports at the top: the commit every result is credited to is read here.
from src.utils import experiment, figures, tables
from src.utils.provenance import crosscheck, verify_inputs

NAME = Path(__file__).resolve().parent.name
# Artifact names start with the study name and this experiment's slug in kebab case.
SLUG = NAME.split("_", 1)[-1].replace("_", "-")
PREFIX = f"{config.STUDY_ROOT.name}-{SLUG}"


def main() -> None:
    with experiment.start(__file__, params) as run:
        p = run.params  # params.PARAMS (params.SMOKE changes nothing for an import)
        figures.apply_visualization_defaults(config)  # the figure look shared by all chapters

        run.stage("verify the past files")
        # Nothing is used before the copied past files match the manifest.
        verified: dict[str, str] = {}
        if p["source_dir"] is not None:
            verified = verify_inputs(
                p["source_dir"],
                p["manifest"],
                recorded=p["recorded_sha256"],
                # Outside out/, which every run clears, so the past files are hashed again
                # only when they or the manifest change (full and smoke runs share it).
                cache=config.INTERIM_DATA_DIR / NAME / "inputs_verified.json",
            )
            run.log(f"{len(verified)} past files match {Path(p['manifest']).name}")
        else:
            assert p["transcribed"], (
                "SOURCE_DIR is None but TRANSCRIBED is empty: there is nothing to import"
            )
        if p["transcribed"]:
            assert p["transcribed_source"].strip(), (
                "TRANSCRIBED needs TRANSCRIBED_SOURCE (bib key and table or page)"
            )

        run.stage("regenerate under out/")
        # TODO: regenerate what the thesis uses, in memory or under run.out(...). Decide the
        # level per artifact and record it in the README table.
        #  R1 (recomputed here): port the old computation into src/ (or run the old code
        #     snapshot unchanged in a separate process:
        #       subprocess.run([sys.executable, str(entry), ...], cwd=run.out_dir,
        #                      env={**os.environ, 'PYTHONPATH': str(snapshot)}, check=True),
        #     with every output path pointed at run.out_dir. Never import it: config/params/src
        #     would resolve to this study's modules) and put the new numbers into `actual`,
        #     with REFERENCE_VALUES taken from the archived outputs.
        #  R2 (redrawn from preserved numbers): read the archived CSV/JSON in SOURCE_DIR
        #     without recomputing; put the numbers the text reports into `actual` as well.
        #  R3 (only an image survives): choose the file; a resized copy or a single frame of
        #     an animation is written with run.out(...).
        actual: dict[str, float] = {}  # TODO: regenerated numbers to check, key -> value

        run.stage("check against the reported numbers")
        # A mismatch fails the run here, and nothing is published.
        if p["reference_values"]:
            rows = crosscheck(actual, p["reference_values"])
            table = run.out(f"{PREFIX}-crosscheck.csv")
            with table.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            # -> result/tables/ when the full run completes; summary.md (照合) cites its rows.
            run.promote(f"{PREFIX}-crosscheck.csv")
            run.log(f"{len(rows)} values match the reported ones")

        run.stage("write the artifacts")
        # Staged under out/staged/; they reach result/ only when the full run completes.
        # Name artifacts f"{PREFIX}-<what>" and describe the past files each comes from with
        #   from src.utils.provenance import source_entry
        #   sources = [source_entry(p["source_dir"] / name, config, sha256=verified[name])]
        #  R1 / R2:
        #   figures.save_figure(fig, f"{PREFIX}-overview", config,
        #                       provenance={"reproducibility": "R2", "sources": sources})
        #   tables.write_latex_table(df, f"{PREFIX}-summary", config, provenance=...)
        #   tables.write_latex_values(values, f"{PREFIX}-main", config, formats=...,
        #                             provenance=...)
        #  R3: figures.import_figure(p["source_dir"] / name, f"{PREFIX}-map", config,
        #                            note="why it cannot be regenerated", license="own work")
        #     A copy made with run.out() keeps the verified original as its source:
        #       figures.import_figure(run.out("map_small.png"), f"{PREFIX}-map", config,
        #                             note="...; resized in run.py", license="own work",
        #                             sources=sources)
        #  Never write into SOURCE_DIR.
        # Numbers that survive only in a publication: R3, with the citation.
        if p["transcribed"]:
            tables.write_latex_values(
                p["transcribed"],
                f"{PREFIX}-transcribed",
                config,
                formats=p["transcribed_formats"],
                provenance={
                    "reproducibility": "R3",
                    "transcribed_from": p["transcribed_source"],
                },
            )


if __name__ == "__main__":
    main()
