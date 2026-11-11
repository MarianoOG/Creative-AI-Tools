import pytest

from youtube_scout.config import load_config
from youtube_scout.errors import ScoutError


@pytest.mark.parametrize("body, message", [
    ("", "set my_channel_id"),
    ("[size_band]\nmin_subscribers = 10\n", "set both"),
    ('my_channel_id = "UC"\nretention_days = 60\n', "retention_days"),
    ('my_channel_id = "UC"\n[quota]\nstop_fraction = 0.95\n', "stop_fraction"),
    ('my_channel_id = "UC"\nlanguages = []\n', "languages"),
])
def test_invalid_configs(tmp_path, body, message):
    (tmp_path / "config.toml").write_text(body)
    with pytest.raises(ScoutError, match=message):
        load_config(root=tmp_path)


def test_absolute_band_without_channel(tmp_path):
    (tmp_path / "config.toml").write_text("[size_band]\nmin_subscribers = 10\nmax_subscribers = 100\n")
    cfg = load_config(root=tmp_path)
    assert cfg.size_band.is_absolute and cfg.max_results_per_run == 20


def test_exclude_file(tmp_path):
    (tmp_path / "config.toml").write_text('my_channel_id = "UC"\nexclude_channel_ids_file = "exclude.txt"\n')
    (tmp_path / "exclude.txt").write_text("# mine\nUCa\nUCb  # friend\n\n")
    assert load_config(root=tmp_path).exclude_ids() == {"UCa", "UCb"}
