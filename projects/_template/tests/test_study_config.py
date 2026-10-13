"""Smoke tests for the study config: a freshly copied study must pass as-is."""


def test_all_exports_resolve(study_cfg):
    for name in study_cfg.__all__:
        assert hasattr(study_cfg, name), f"config.__all__ lists {name!r} but it is not defined"


def test_directories_live_under_study_root(study_cfg, study_root):
    for name in study_cfg.__all__:
        if not name.endswith("_DIR"):
            continue
        path = getattr(study_cfg, name)
        assert path.is_relative_to(study_root), f"{name} escapes the study: {path}"
        assert path.exists(), f"{name} is missing on disk (broken copy?): {path}"


def test_shared_constants_match_repo_root(study_cfg, study_root, load_module_by_path):
    root_cfg = load_module_by_path(
        study_root.parents[1] / "config.py", f"{study_root.name}_root_config_under_test"
    )
    assert study_cfg.GEO == root_cfg.GEO
    assert study_cfg.VISUALIZATION == root_cfg.VISUALIZATION


def test_no_shared_value_can_change_a_result(study_cfg):
    # The seed and every other value that can change a result are pinned in each
    # experiment's params.py, so editing a shared config.py never changes a finished one.
    for name in ("RANDOM", "SEED"):
        assert not hasattr(study_cfg, name)
        assert name not in study_cfg.__all__


def test_research_template_names_alias_the_study_paths(study_cfg, study_root):
    # Experiment code ported from a research-template repository uses these names.
    assert study_cfg.PROJECT_ROOT == study_root
    assert study_cfg.DATA_ROOT == study_cfg.RAW_DATA_DIR
    assert study_cfg.EXPERIMENTS_DIR == study_root / "experiments"
    assert study_cfg.EXP_DIR == study_cfg.EXPERIMENTS_DIR  # research-template's older name


def test_both_experiment_templates_are_in_place(study_cfg):
    for template in ("_template", "_import_template"):
        for name in ("run.py", "summary.md"):
            path = study_cfg.EXPERIMENTS_DIR / template / name
            assert path.is_file(), f"experiments/{template}/{name} is missing"
