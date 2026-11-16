"""The locale layer: docs that must exist, the language-module contract, the
dispatch seam, and the worked example."""
import json
import re
import shutil
import subprocess
import sys
import types

import pytest

from conftest import FIXTURES, SCRIPTS_DIR

import langs
import orthography
from langs import zh

ROOT = SCRIPTS_DIR.parent
LOCALES = ROOT / "references" / "locales"
EXAMPLE = ROOT / "examples" / "mini-schinese"


# ---- the docs -------------------------------------------------------------

def test_every_registered_locale_doc_exists_and_is_indexed():
    index = (LOCALES / "README.md").read_text(encoding="utf-8")
    ids = ["thai", "schinese", "zh_cn", "zh_sg", "zh_hans", "chinese_simplified", "tchinese",
           "zh_tw", "zh_hk", "zh_hant", "chinese_traditional", "chinese", "zh"]
    for language_id in ids:
        docs = langs.locale_docs(language_id)
        assert docs, language_id
        for doc in docs:
            assert (LOCALES / doc).is_file(), f"{language_id} -> {doc}"
            assert doc in index, f"{doc} is not in the locale index"
    assert langs.locale_docs("french") == () and langs.locale_docs(None) == ()
    assert langs.locale_docs("zh-TW") == langs.locale_docs("tchinese")[:1] + (
        "chinese-traditional.md",)


def test_relative_links_in_docs_resolve_and_the_old_path_is_gone():
    link = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)")
    docs = list(LOCALES.glob("*.md")) + list((ROOT / "references").glob("*.md")) + [
        ROOT / "SKILL.md", ROOT / "PLAYBOOK.md"]
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        for target in link.findall(text):
            if target.startswith("http"):
                continue
            assert (doc.parent / target).resolve().is_file(), f"{doc.name}: broken link {target}"
        assert "references/chinese.md" not in text, doc.name
    assert not (ROOT / "references" / "chinese.md").exists()


def test_core_documents_carry_no_chinese_detail():
    """SKILL.md must not grow a section per language: it points at the locale files."""
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "references/locales/" in skill
    assert "全角" not in skill and "……" not in skill and "“" not in skill


# ---- the contract ---------------------------------------------------------

CONTRACT_FUNCS = ("claims", "config", "problem", "prompt_rule", "issues", "normalize",
                  "severity", "heading", "banner", "hints", "locale_docs")


@pytest.mark.parametrize("module", langs.MODULES, ids=lambda m: m.NAME)
def test_every_language_module_follows_the_contract(module):
    for name in ("NAME", "PREFIX", "LABELS", "NOTES"):
        assert hasattr(module, name), name
    for name in CONTRACT_FUNCS:
        assert callable(getattr(module, name)), name
    profile = {"language_id": "schinese"}
    assert module.claims(profile)
    cfg = module.config(profile)
    assert "explicit" in cfg and "truncation_ratio" in cfg
    assert module.severity("anything", cfg) in (2, 4)
    sample = "你好,我来了..."
    found = module.issues(sample, cfg)
    assert isinstance(found, list) and found
    fixed = module.normalize(sample, cfg)
    assert module.normalize(fixed, cfg) == fixed, "the fixer must be idempotent"
    assert module.issues(fixed, cfg) == [], "after the fix, nothing mechanical is left"
    assert module.prompt_rule(profile) and module.heading(cfg) and module.banner(cfg)
    assert module.config({"language_id": "schinese", "orthography": False}) is None


def test_orthography_keeps_its_public_names():
    for name in ("config", "problem", "prompt_rule", "issues", "normalize", "wrong_variant",
                 "severity", "prefix", "banner", "apply", "main", "CHOOSE"):
        assert hasattr(orthography, name), name
    assert orthography.CHOOSE == zh.CHOOSE
    assert orthography.normalize("等等...") == "等等……", "no config: Chinese, the only built-in"


def test_orthography_cli_runs_from_any_directory(tmp_path):
    proc = subprocess.run([sys.executable, str(SCRIPTS_DIR / "orthography.py"), "--help"],
                          cwd=tmp_path, capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0 and "--write" in proc.stdout


# ---- the seam: a second language plugs in without touching anything else -----

def fake_language():
    """A toy 'french' module: flags a space before ':' and fixes it."""
    m = types.ModuleType("fake_fr")
    m.NAME, m.PREFIX, m.LABELS, m.NOTES = "French", "fr", ("colon",), {}
    m.claims = lambda profile: profile.get("language_id") == "french"
    m.config = lambda profile: (None if profile.get("orthography") is False
                                else {"explicit": True, "truncation_ratio": 0.5})
    m.problem = lambda profile, need_variant=True: (
        "decide the quote style first" if profile.get("quotes_undecided") else None)
    m.prompt_rule = lambda profile: "FRENCH CONVENTIONS: no space before a colon.\n"
    m.issues = lambda text, cfg: ["colon"] if " :" in text else []
    m.normalize = lambda text, cfg=None: text.replace(" :", ":")
    m.severity = lambda label, cfg: 2
    m.heading = lambda cfg: "French conventions"
    m.banner = lambda cfg: "French conventions: colon spacing"
    m.hints = lambda cfg: []
    m.locale_docs = lambda language_id: ()
    return m


def test_a_new_language_needs_only_its_own_module(monkeypatch):
    fr = fake_language()
    monkeypatch.setattr(langs, "MODULES", langs.MODULES + (fr,))
    profile = {"language_id": "french"}
    cfg = orthography.config(profile)
    assert cfg["_module"] is fr and orthography.prompt_rule(profile).startswith("FRENCH")
    assert orthography.issues("Attention : ici", cfg) == ["colon"]
    assert orthography.normalize("Attention : ici", cfg) == "Attention: ici"
    assert orthography.severity("colon", cfg) == 2 and orthography.prefix(cfg) == "fr"
    assert orthography.banner(cfg).startswith("French")
    assert orthography.wrong_variant("Attention : ici", cfg) == "", "no script variants here"
    assert orthography.problem({"language_id": "french", "quotes_undecided": True})
    assert orthography.problem(profile) is None
    # the existing language is untouched, and a language with no module still has none
    assert orthography.config({"language_id": "schinese"})["_module"] is zh
    assert orthography.config({"language_id": "german"}) is None
    changed, counts, skipped = orthography.apply(
        [("p", {"a": "Oui : non"}, lambda k: k)], cfg,
        {"echo_check": False, "script_check": False, "terms": []})
    assert counts == {"colon": 1} and changed == {"p": 1} and skipped == 0


# ---- the worked example -------------------------------------------------------

DICTIONARY = {
    "Hello there, [partner_name]!": "你好，[partner_name]！",
    'She said \\"hold the door\\" and left.': '她说了句\\"帮我扶一下门\\"就走了。',
    "I'm {b}really{/b} glad you came.": "你能来，我{b}真的{/b}很高兴。",
    "The rain kept falling outside the cafe.": "咖啡馆外，雨还在下个不停。",
    "CHAPTER ONE": "第一章", "Order a coffee": "点一杯咖啡",
    "One espresso, please.": "请给我一杯浓缩咖啡。", "Leave the cafe": "离开咖啡馆",
    "Maybe another day.\\nI should go.": "改天吧……\\n我该走了。",
    "(She seems happier today.)": "(她今天看起来开心多了。)",
    "Hey, Nora. You are up early.": "嘿，诺拉。你起得真早。",
    "Could not sleep.": "睡不着。", "(She looks exhausted today.)": "(她今天看起来累坏了。)",
    "Stop staring at me.": "别盯着我看。", "Morning, all of you.": "各位，早上好。",
    "You are late again.": "你又迟到了。", "Take a seat, Mr. Reed.": "请坐，里德先生。",
    "Nobody here but me.": "这里除了我，一个人也没有。",
    "I saw Nora yesterday.": "我昨天见到诺拉了。",
    "Were you talking about me?": "你们刚才是在说我吗？",
    "Emma, are you there?": "艾玛，你在吗？", "She left an hour ago.": "她一个小时前就走了。",
    "Narration that belongs to nobody.": "不属于任何人的旁白。",
    "Let me try that once more.": "让我再试一次。",
}


def build_example(tmp_path):
    for name in ("profile.json", "qa_rules.json", "translation-guide.md"):
        shutil.copy(EXAMPLE / name, tmp_path / name)
    (tmp_path / "decompiled").mkdir()
    for name in ("mini_game.rpy", "scenes.rpy"):
        shutil.copy(FIXTURES / name, tmp_path / "decompiled" / name)
    run = lambda script, *a: subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script), "--profile", str(tmp_path / "profile.json"), *a],
        capture_output=True, text=True, encoding="utf-8")
    assert run("extract_strings.py").returncode == 0
    return run


def test_example_is_a_valid_clean_chinese_project(tmp_path):
    profile = json.loads((EXAMPLE / "profile.json").read_text(encoding="utf-8"))
    assert orthography.problem(profile) is None, "the script is chosen and consistent"
    assert profile["orthography"]["variant"] == "simplified" and profile["language_id"] == "schinese"
    run = build_example(tmp_path)
    strings = json.loads((tmp_path / "strings.json").read_text(encoding="utf-8"))
    assert {s["text"] for s in strings} == set(DICTIONARY), "the dictionary covers the fixture"
    (tmp_path / "translations.json").write_text(
        json.dumps(DICTIONARY, ensure_ascii=False), encoding="utf-8")
    qa = run("qa_check.py")
    assert qa.returncode == 0, qa.stdout
    assert "Hard issues:      0" in qa.stdout and "variant=simplified" in qa.stdout
    assert "0 entr(ies) to change" in run("orthography.py").stdout
    assert run("build_patch.py", "--out", str(tmp_path / "out")).returncode == 0


def test_example_rules_catch_what_they_are_for(tmp_path):
    run = build_example(tmp_path)
    broken = dict(DICTIONARY)
    broken["Take a seat, Mr. Reed."] = "老子让你坐，里德先生。"          # slang from the professor
    broken["Could not sleep."] = "睡不着,真的..."                        # half-width, ASCII ellipsis
    broken["Stop staring at me."] = "請別盯著我看。"                     # Traditional characters
    (tmp_path / "translations.json").write_text(
        json.dumps(broken, ensure_ascii=False), encoding="utf-8")
    out = run("qa_check.py")
    assert out.returncode == 1
    for needle in ("professor does not use street slang", "zh halfwidth", "zh ellipsis",
                   "zh variant:"):
        assert needle in out.stdout, needle


# ---- the scaffold points at the right files ------------------------------------

@pytest.mark.parametrize("language,expect,absent", [
    ("thai", ["references/locales/thai.md"], ["chinese"]),
    ("schinese", ["locales/chinese.md", "locales/chinese-simplified.md"], ["thai.md"]),
    ("french", [], ["references/locales"]),
])
def test_scaffold_names_the_locale_files(tmp_path, language, expect, absent):
    game = tmp_path / "Game-1.0-pc"
    (game / "game").mkdir(parents=True)
    proc = subprocess.run([sys.executable, str(SCRIPTS_DIR / "init_project.py"), "--game", str(game),
                           "--language", language, "--dir", str(tmp_path / "p")],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    for text in expect:
        assert text in proc.stdout, text
    for text in absent:
        assert text not in proc.stdout, text
