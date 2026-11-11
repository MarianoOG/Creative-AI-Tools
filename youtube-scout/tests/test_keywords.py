from youtube_scout import keywords as kw


def test_generate_writes_file_dedups_and_filters_languages(cfg, llm, frozen):
    generated = kw.generate_keywords(cfg, llm)
    assert [k.text for k in generated] == ["claymation walk cycle", "animación con plastilina"]
    text = cfg.keywords_file.read_text()
    assert "en | claymation walk cycle" in text and "Edit brand.txt instead" in text
    assert kw.read_keywords(cfg.keywords_file) == generated
    assert "clay stop-motion" in llm.prompts[0]


def test_generation_uses_comment_phrases_and_found_titles(cfg, llm, frozen):
    cfg.out_dir.mkdir()
    (cfg.out_dir / "comments-2026-11-10.txt").write_text("# header\n3\tbest clay for claymation\n")
    (cfg.out_dir / "2026-11-10.json").write_text('{"channels": [{"recent_titles": ["Clay walk cycle test"]}]}')
    kw.generate_keywords(cfg, llm)
    assert "best clay for claymation" in llm.prompts[0]
    assert "Clay walk cycle test" in llm.prompts[0]
    assert "comment phrases, found titles" in cfg.keywords_file.read_text()


def test_rotation_picks_least_recently_searched(cfg):
    words = [kw.Keyword("en", w) for w in ("a", "b", "c")]
    kw.mark_searched(cfg, words[0], "2026-11-10")
    kw.mark_searched(cfg, words[1], "2026-11-09")
    assert [k.text for k in kw.pick_keywords(cfg, words, 2)] == ["c", "b"]
