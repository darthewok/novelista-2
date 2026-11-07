from __future__ import annotations
import json


def test_defaults_created_on_first_load(tmp_path):
    from app import settings as st
    s = st.load()
    assert s.provider == "anthropic"
    assert s.quality.auto_polish is False and s.quality.max_polish_passes == 1
    assert s.providers["ollama"].num_ctx == 32768
    on_disk = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert on_disk["providers"]["lmstudio"] == {"api_key": "lm-studio", "base_url": "http://localhost:1234/v1"}
    assert on_disk["models"]["summary"] == "claude-haiku-5-5"


def test_masked_hides_keys():
    from app import settings as st
    s = st.apply_patch(st.load(), {"providers": {"anthropic": {"api_key": "sk-ant-abcdefghijkl1234"}}})
    m = st.masked(s)
    assert m["providers"]["anthropic"]["api_key"] == "sk-ant…1234"
    assert m["providers"]["openai"]["api_key"] == ""
    assert "abcdefghijkl" not in json.dumps(m)


def test_apply_patch_masked_or_empty_key_keeps_old_and_new_key_replaces():
    from app import settings as st
    s = st.apply_patch(st.load(), {"providers": {"anthropic": {"api_key": "sk-ant-abcdefghijkl1234"}}})
    st.save(s)
    for unchanged in ("sk-ant…1234", ""):
        s2 = st.apply_patch(st.load(), {"providers": {"anthropic": {"api_key": unchanged}}, "provider": "openai"})
        assert s2.providers["anthropic"].api_key == "sk-ant-abcdefghijkl1234"
        assert s2.provider == "openai"
    s3 = st.apply_patch(s, {"providers": {"anthropic": {"api_key": "sk-ant-NEW"}}, "quality": {"auto_polish": True}})
    assert s3.providers["anthropic"].api_key == "sk-ant-NEW"
    assert s3.quality.auto_polish is True and s3.quality.tells_threshold == 3


def test_custom_provider_and_provider_config():
    from app import settings as st
    s = st.apply_patch(st.load(), {"provider": "mine",
                                   "providers": {"mine": {"api_key": "k" * 20, "base_url": "http://x/v1"}}})
    st.save(s)
    assert st.provider_config() == {"provider": "mine", "api_key": "k" * 20, "base_url": "http://x/v1"}


def test_model_for_and_cache_invalidated_by_save():
    from app import settings as st
    assert st.model_for("draft") == "claude-opus-5-5"
    st.save(st.apply_patch(st.load(), {"models": {"draft": "gpt-x"}}))
    assert st.model_for("draft") == "gpt-x"
