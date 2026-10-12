"""The repo-root config must expose the shared constants every study relies on."""


def test_shared_constants_present_and_sane(repo_root, load_module_by_path):
    cfg = load_module_by_path(repo_root / "config.py", "root_config_under_test")

    assert cfg.GEO["earth_radius_m"] > 0
    assert {"dpi", "format", "font"} <= set(cfg.VISUALIZATION)
    assert {"family", "size"} <= set(cfg.VISUALIZATION["font"])


def test_shared_paths_exist(repo_root, load_module_by_path):
    cfg = load_module_by_path(repo_root / "config.py", "root_config_paths_under_test")

    assert cfg.REPO_ROOT == repo_root
    assert cfg.DRAFT_DIR.is_dir()
    assert cfg.PROJECTS_DIR.is_dir()


def test_no_shared_seed(repo_root, load_module_by_path):
    # Seeds and every other value that can change a result live in each experiment's
    # params.py; a shared one would let one edit change every finished experiment.
    cfg = load_module_by_path(repo_root / "config.py", "root_config_seed_under_test")

    assert not hasattr(cfg, "RANDOM")
