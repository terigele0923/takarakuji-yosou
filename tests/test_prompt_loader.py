from app.services import prompt_loader


def test_analysis_prompt_is_read_from_file_for_each_call(tmp_path, monkeypatch):
    prompt_path = tmp_path / "analysis.md"
    prompt_path.write_text("first prompt", encoding="utf-8")
    monkeypatch.setattr(prompt_loader, "ANALYSIS_PROMPT_PATH", prompt_path)

    assert prompt_loader.load_analysis_prompt() == "first prompt"

    prompt_path.write_text("updated prompt", encoding="utf-8")
    assert prompt_loader.load_analysis_prompt() == "updated prompt"
