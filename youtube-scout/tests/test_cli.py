from youtube_scout import cli


def test_missing_youtube_key_exits_with_clear_message(project, monkeypatch, capsys):
    monkeypatch.setenv("SCOUT_HOME", str(project))
    assert cli.main(["run"]) == 2
    assert "YOUTUBE_API_KEY is not set" in capsys.readouterr().err


def test_missing_llm_key_exits_with_clear_message(project, monkeypatch, capsys):
    monkeypatch.setenv("SCOUT_HOME", str(project))
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    assert cli.main(["keywords"]) == 2
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err


def test_unknown_provider(project, monkeypatch, capsys):
    monkeypatch.setenv("SCOUT_HOME", str(project))
    monkeypatch.setenv("SCOUT_LLM_PROVIDER", "other")
    assert cli.main(["keywords"]) == 2
    assert "Unknown SCOUT_LLM_PROVIDER" in capsys.readouterr().err


def test_missing_config_and_brand(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SCOUT_HOME", str(tmp_path))
    assert cli.main(["quota"]) == 2
    assert "config.toml not found" in capsys.readouterr().err
    (tmp_path / "config.toml").write_text('my_channel_id = "UCme"\n')
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert cli.main(["keywords"]) == 2
    assert "brand.txt not found" in capsys.readouterr().err


def test_purge_needs_confirmation(project, monkeypatch):
    monkeypatch.setenv("SCOUT_HOME", str(project))
    (project / "out").mkdir()
    assert cli.main(["purge"]) == 1 and (project / "out").exists()
    assert cli.main(["purge", "--yes"]) == 0 and not (project / "out").exists()
