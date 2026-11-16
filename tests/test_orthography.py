import json
import subprocess
import sys

from conftest import SCRIPTS_DIR

import orthography as o
import punctuation
import translate_api
from characters import is_monologue

SC = o.config({"language_id": "schinese"})
TC = o.config({"language_id": "tchinese"})


def test_config_by_language_id_and_profile():
    assert o.config({"language_id": "thai"}) is None
    assert SC["variant"] == "simplified" and not SC["explicit"]
    assert o.config({"language_id": "zh-TW"})["variant"] == "traditional"
    assert o.config({"language_id": "chinese"})["variant"] is None
    named = o.config({"language_id": "chinese", "orthography": {"variant": "traditional"}})
    assert named["variant"] == "traditional" and named["explicit"]
    assert o.config({"language_id": "schinese", "orthography": False}) is None


def test_variant_leaks_both_ways_and_shared_characters_pass():
    assert o.wrong_variant("我們这样說", SC) == "們說"
    assert o.wrong_variant("我們这样說", TC) == "这样"
    # 后 里 只 面 干 are real Traditional characters too: never flagged
    assert o.wrong_variant("后面只有里面干", TC) == ""
    # the same text in each script is clean in its own variant
    assert o.wrong_variant("这是为了我们的国家，请听他说话。", SC) == ""
    assert o.wrong_variant("這是為了我們的國家，請聽他說話。", TC) == ""
    # tokens are not text; allow_chars is an escape hatch
    assert o.wrong_variant("[們]{這}好", SC) == ""
    allow = o.config({"language_id": "schinese", "orthography": {"allow_chars": "瞭"}})
    assert o.wrong_variant("瞭望", SC) == "瞭" and o.wrong_variant("瞭望", allow) == ""
    assert o.wrong_variant("我們", o.config({"language_id": "chinese"})) == ""


def test_normalize_mechanical_conventions():
    for raw, want in (
            ("你好,我是[name]。", "你好，我是[name]。"),
            ("什么?!", "什么？！"),
            ("等等...", "等等……"), ("等等。。。", "等等……"), ("嗯…", "嗯……"),
            ("为什么…………", "为什么…………"),
            ("你 好 吗", "你好吗"),
            ("好的. 走吧", "好的。走吧"),
            ("{i}真的{/i}!走吧", "{i}真的{/i}！走吧"),
            ("[name],你好", "[name]，你好"),
            ("OK,走吧", "OK，走吧"),
            # not Chinese punctuation: decimals, file names, Latin text, tokens
            ("版本3.5更新", "版本3.5更新"), ("点击setup.exe", "点击setup.exe"),
            ("Hello, world.", "Hello, world."),
            ("他说\\\"好,走\\\"{w=0.5}", "他说\\\"好，走\\\"{w=0.5}")):
        assert o.normalize(raw) == want, raw
        assert o.normalize(want) == want, "idempotent: " + want


def test_issues_name_exactly_what_normalize_changes():
    assert o.issues("等等...", SC) == ["ellipsis"]
    assert o.issues("他說:好 的", SC) == ["variant:說", "halfwidth", "space"]
    assert o.issues("他说：好的……", SC) == []


def test_prompt_rule_states_the_variant_and_reaches_the_system_prompt(tmp_path):
    assert o.prompt_rule({"language_id": "thai"}) == ""
    assert "Simplified characters only" in o.prompt_rule({"language_id": "schinese"})
    assert "「 」" in o.prompt_rule({"language_id": "tchinese"})
    assert "style guide names" in o.prompt_rule({"language_id": "chinese"})
    system = translate_api.build_system_instruction(
        {"language_id": "schinese", "language_name": "Simplified Chinese"}, tmp_path)
    assert "CHINESE WRITING CONVENTIONS" in system and "……" in system
    plain = translate_api.build_system_instruction({"language_id": "french"}, tmp_path)
    assert "CHINESE" not in plain


def test_full_width_monologue_and_exclamation_policy():
    assert is_monologue("（唉，又是早上。）") and is_monologue("(Ugh.)")
    assert not is_monologue("（唉）不是")
    cfg = {"short_words": 2}
    assert punctuation.over_policy("It is a long day!", "真是漫长的一天！", cfg)
    assert not punctuation.over_policy("Hey!", "嘿！", cfg)
    assert punctuation.soften("真是漫长的一天！") == "真是漫长的一天。"
    assert punctuation.soften("什么？！你确定！？") == "什么？你确定？"
    assert punctuation.soften("好！……走吧！") == "好……走吧。"


def project(tmp_path, tr, sp=None, extra=None, language="schinese"):
    strings = [{"text": t, "speaker": "a", "file": "a.rpy", "line": i + 1, "kind": "say"}
               for i, t in enumerate(tr)]
    (tmp_path / "profile.json").write_text(json.dumps({
        "language_id": language, "language_name": "Chinese",
        "validation": {"target_script": "chinese"}, **(extra or {})}), encoding="utf-8")
    for name, data in (("strings", strings), ("translations", tr),
                       ("speaker_translations", sp or {})):
        (tmp_path / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False),
                                               encoding="utf-8")


def run(tmp_path, script, *args):
    return subprocess.run([sys.executable, str(SCRIPTS_DIR / script), "--profile",
                           str(tmp_path / "profile.json"), *args],
                          capture_output=True, text=True, encoding="utf-8")


LINES = {"Wait, [name]...": "等等,[name]...",
         "I really can not believe it at all.": "我真不敢相信。",
         "We said so.": "我們说过。"}


def test_qa_lists_conventions_for_review_and_keeps_short_lines_quiet(tmp_path):
    project(tmp_path, LINES)
    proc = run(tmp_path, "qa_check.py")
    out = proc.stdout
    assert proc.returncode == 0, out            # inferred variant: review only
    assert "zh ellipsis" in out and "zh halfwidth" in out and "zh variant:們" in out
    assert "Chinese conventions: variant=simplified" in out
    assert "short?" not in out                  # 7 characters for 35 is normal


def test_declared_variant_makes_a_leak_a_hard_issue(tmp_path):
    project(tmp_path, LINES, extra={"orthography": {"variant": "simplified"}})
    proc = run(tmp_path, "qa_check.py")
    cat2 = proc.stdout.split("CAT 2")[1].split("CAT 3")[0]
    assert proc.returncode == 1 and "zh variant:們" in cat2 and "zh halfwidth" not in cat2
    # --technical-only stays category 1 only; opting out silences everything
    assert "zh " not in run(tmp_path, "qa_check.py", "--technical-only").stdout
    project(tmp_path, LINES, extra={"orthography": False})
    proc = run(tmp_path, "qa_check.py")
    assert "zh " not in proc.stdout and "Chinese conventions" not in proc.stdout


def test_fixer_dry_run_then_write_with_backup(tmp_path):
    project(tmp_path, LINES, sp={"a::We said so.": "我们说过..."})
    before = (tmp_path / "translations.json").read_text(encoding="utf-8")
    out = run(tmp_path, "orthography.py").stdout
    assert "dry-run" in out and "2 entr(ies) to change" in out
    assert "variant        1 entr(ies)  (reported only" in out
    assert (tmp_path / "translations.json").read_text(encoding="utf-8") == before
    run(tmp_path, "orthography.py", "--write")
    read = lambda n: json.loads((tmp_path / n).read_text(encoding="utf-8"))
    assert read("translations.json") == {**LINES, "Wait, [name]...": "等等，[name]……"}
    assert read("speaker_translations.json") == {"a::We said so.": "我们说过……"}
    assert list(tmp_path.glob("translations.json.bak-*"))
    assert "0 entr(ies) to change" in run(tmp_path, "orthography.py").stdout


def test_fixer_refuses_other_languages(tmp_path):
    project(tmp_path, {}, language="thai")
    proc = run(tmp_path, "orthography.py")
    assert proc.returncode == 1 and "nothing to do" in proc.stderr


def test_scaffold_declares_the_variant(tmp_path):
    game = tmp_path / "Game-1.0-pc"
    (game / "game").mkdir(parents=True)
    for lang, variant, name in (("schinese", "simplified", "Simplified Chinese"),
                                ("tchinese", "traditional", "Traditional Chinese")):
        proc = subprocess.run([sys.executable, str(SCRIPTS_DIR / "init_project.py"),
                               "--game", str(game), "--language", lang,
                               "--dir", str(tmp_path / lang)],
                              capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr
        profile = json.loads((tmp_path / lang / "profile.json").read_text(encoding="utf-8"))
        assert profile["orthography"] == {"variant": variant}
        assert profile["language_name"] == name
        assert profile["validation"]["target_script"] == "chinese"
        assert "references/chinese.md" in proc.stdout
    proc = subprocess.run([sys.executable, str(SCRIPTS_DIR / "init_project.py"),
                           "--game", str(game), "--language", "chinese",
                           "--dir", str(tmp_path / "zh")],
                          capture_output=True, text=True, encoding="utf-8")
    profile = json.loads((tmp_path / "zh" / "profile.json").read_text(encoding="utf-8"))
    assert "orthography" not in profile and "Simplified or Traditional is not known" in proc.stdout
