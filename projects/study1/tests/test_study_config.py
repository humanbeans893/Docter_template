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
    assert study_cfg.RANDOM == root_cfg.RANDOM
    assert study_cfg.VISUALIZATION == root_cfg.VISUALIZATION
