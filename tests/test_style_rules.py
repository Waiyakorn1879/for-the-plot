"""Style Rules Engine: one rule, prompt side and QA side."""
import style_rules as sr

SPK = {"mc": {"gender": "male"}, "an": {"gender": "female"}, "an2": {"alias_of": "an"}}


def test_problems():
    assert sr.problems([{"name": "a", "forbid": ["x"]}]) == []
    assert sr.problems([{"name": "a"}])
    assert sr.problems([{"name": "a", "forbid": ["x"], "except_in": ["y"]}])
    assert sr.problems([{"name": "a", "forbid": ["x"]}, {"name": "a", "say": "s"}])
    assert sr.problems([{"name": "a", "forbid": ["x"], "to": ["p"]}])


def test_scope_by_attribute_includes_aliases():
    rules = [{"name": "f", "forbid": ["กู"], "speakers_where": {"gender": "Female"}}]
    q = sr.qa_rules(rules, SPK)
    assert q[0]["speakers"] == ["an", "an2"] and q[0]["category"] == 4


def test_prompt_only_rule_has_no_qa_and_scoped_prompt():
    rules = [{"name": "tone", "say": "Keep it dry."},
             {"name": "f", "forbid": ["x"], "speakers": ["an"]}]
    assert sr.qa_rules(rules, SPK)[0]["name"] == "style: f"
    assert len(sr.qa_rules(rules, SPK)) == 1
    block = sr.prompt_block(rules, SPK, ["mc"])
    assert "Keep it dry" in block and "Never write: x" not in block
    assert "Never write: x" in sr.prompt_block(rules, SPK, ["an2"])
    assert sr.prompt_block([], SPK, ["mc"]) == ""


def test_standalone_exceptions():
    rules = [{"name": "k", "mode": "standalone", "forbid": ["กู"], "except_in": ["กูเกิล"]}]
    q = sr.qa_rules(rules, SPK)[0]
    import re
    hit = lambda t: re.search(q["pattern"], sr.strip_exceptions(t, q))
    assert not hit("เปิดกูเกิล") and hit("กูไป") and hit("กูเกิล กู")


def test_prompt_reaches_translate_batch():
    import translate_api
    seen = {}

    def fake(system, user):
        seen["user"] = user
        return '[{"id": 1, "tr": "x"}]'

    batch = [{"id": 1, "speaker": "an", "kind": "say", "text": "Hi"}]
    rules = [{"name": "f", "forbid": ["BAD"], "speakers_where": {"gender": "female"}}]
    translate_api.translate_batch(fake, "sys", SPK, "Greek", batch, style=rules)
    assert "STYLE RULES" in seen["user"] and "BAD" in seen["user"]
    translate_api.translate_batch(fake, "sys", SPK, "Greek", batch)
    assert "STYLE RULES" not in seen["user"]
