import characters
from characters import (
    cast_block, character_line, get_record, is_character, missing_must_use,
    persona_card, register_rules, relationship, resolve_alias,
)

SPEAKERS = {
    "mc": {
        "name": "MC", "gender": "male", "role": "protagonist",
        "register": "blunt, 18-year-old male",
        "self_pronoun": "กู", "address_pronoun": "มึง",
        "monologue": {"self_pronoun": "กู"},
        "speech_notes": "dry humor",
        "to": {"my": {"self_pronoun": "เรา", "address_pronoun": "แก",
                      "note": "closest friend"}},
        "examples": [{"en": "I'm a loser.", "tr": "กูนี่ห่วย", "note": "not whiny"},
                     {"en": "Sure.", "tr": "ได้"},
                     {"en": "Third.", "tr": "สาม"}],
    },
    "my": {"name": "Maya", "gender": "female", "role": "best friend",
           "self_pronoun": "ฉัน", "forbidden": ["กู", "มึง"],
           "must_use": ["นะ"]},
    "sa": {"name": "Sage", "gender": "female", "role": "president"},  # thin, v1.3-style
    "my_q": {"name": "???", "alias_of": "my"},
    "narrator": {"name": "(narration)"},
}


class TestAliases:
    def test_resolves_to_canonical(self):
        assert resolve_alias(SPEAKERS, "my_q") == "my"

    def test_plain_code_unchanged(self):
        assert resolve_alias(SPEAKERS, "mc") == "mc"

    def test_unknown_code_unchanged(self):
        assert resolve_alias(SPEAKERS, "nobody") == "nobody"

    def test_alias_shares_the_target_record(self):
        assert get_record(SPEAKERS, "my_q")["name"] == "Maya"

    def test_circular_alias_does_not_hang(self):
        speakers = {"a": {"name": "A", "alias_of": "b"},
                    "b": {"name": "B", "alias_of": "a"}}
        assert resolve_alias(speakers, "a") in {"a", "b"}

    def test_self_alias_does_not_hang(self):
        assert resolve_alias({"a": {"name": "A", "alias_of": "a"}}, "a") == "a"


class TestIsCharacter:
    def test_pseudo_speakers_are_not_characters(self):
        for code in ("narrator", "_menu", "_screen", "_ui", "_text"):
            assert not is_character(SPEAKERS, code)

    def test_real_speaker_is_a_character(self):
        assert is_character(SPEAKERS, "mc")


class TestPersonaCard:
    def test_thin_record_falls_back_to_the_v13_one_liner(self):
        """An un-enriched profile must produce exactly the old prompt."""
        assert persona_card(SPEAKERS, "sa") == character_line(SPEAKERS, "sa")
        assert persona_card(SPEAKERS, "sa") == "Sage (female) — president"

    def test_unknown_speaker_is_named_as_unknown(self):
        assert "unknown speaker" in persona_card(SPEAKERS, "zz")

    def test_card_carries_register_and_pronouns(self):
        card = persona_card(SPEAKERS, "mc")
        assert "blunt, 18-year-old male" in card
        assert "กู" in card and "มึง" in card

    def test_card_carries_relationship_overrides(self):
        card = persona_card(SPEAKERS, "mc")
        assert "to Maya" in card and "เรา" in card and "แก" in card

    def test_card_carries_monologue_override(self):
        assert "inner monologue" in persona_card(SPEAKERS, "mc")

    def test_card_carries_forbidden_and_must_use(self):
        card = persona_card(SPEAKERS, "my")
        assert "NEVER use: กู, มึง" in card
        assert "MUST use: นะ" in card

    def test_examples_are_capped(self):
        card = persona_card(SPEAKERS, "mc")
        assert card.count("e.g. EN") == 2          # third example dropped
        assert "not whiny" in card                 # the note survives

    def test_example_without_a_translation_is_skipped(self):
        speakers = {"x": {"name": "X", "register": "r",
                          "examples": [{"en": "only english"}]}}
        assert "e.g." not in persona_card(speakers, "x")


class TestCastBlock:
    def test_lists_each_speaker_once(self):
        block = cast_block(SPEAKERS, ["mc", "my", "mc", "my"])
        assert block.count("MC (male)") == 1
        assert block.count("Maya (female)") == 1

    def test_alias_does_not_duplicate_its_target(self):
        block = cast_block(SPEAKERS, ["my", "my_q"])
        assert block.count("best friend") == 1

    def test_excludes_narration_and_ui(self):
        block = cast_block(SPEAKERS, ["narrator", "_menu", "_screen"])
        assert block == ""

    def test_emitted_once_regardless_of_batch_size(self):
        block = cast_block(SPEAKERS, ["mc"] * 60)
        assert block.count("CAST IN THIS BATCH") == 1
        assert block.count("blunt, 18-year-old male") == 1

    def test_preserves_first_appearance_order(self):
        block = cast_block(SPEAKERS, ["my", "mc"])
        assert block.index("Maya") < block.index("MC (male)")


class TestRegisterRules:
    def test_forbidden_becomes_a_category_2_rule(self):
        rules = register_rules(SPEAKERS)
        assert len(rules) == 1
        rule = rules[0]
        assert rule["category"] == 2
        assert rule["name"] == "Maya: forbidden term"

    def test_rule_covers_the_alias_code_too(self):
        rule = register_rules(SPEAKERS)[0]
        assert set(rule["speakers"]) == {"my", "my_q"}

    def test_terms_are_regex_escaped(self):
        rules = register_rules({"x": {"name": "X", "forbidden": ["a.b", "c+d"]}})
        assert rules[0]["pattern"] == r"a\.b|c\+d"

    def test_characters_without_forbidden_produce_no_rule(self):
        assert register_rules({"x": {"name": "X"}}) == []

    def test_empty_terms_are_ignored(self):
        assert register_rules({"x": {"name": "X", "forbidden": ["", None]}}) == []


class TestMustUse:
    def test_reports_absent_terms(self):
        assert missing_must_use(SPEAKERS, "my", "ไม่มีอะไร") == ["นะ"]

    def test_present_term_is_not_reported(self):
        assert missing_must_use(SPEAKERS, "my", "ดีนะ") == []

    def test_character_without_must_use(self):
        assert missing_must_use(SPEAKERS, "mc", "anything") == []


class TestRelationship:
    def test_declared_pair_overrides(self):
        rel = relationship(SPEAKERS, "mc", "my")
        assert rel["self_pronoun"] == "เรา" and rel["address_pronoun"] == "แก"

    def test_relationship_resolves_the_target_alias(self):
        assert relationship(SPEAKERS, "mc", "my_q")["address_pronoun"] == "แก"

    def test_undeclared_pair_is_empty(self):
        assert relationship(SPEAKERS, "mc", "sa") == {}


class TestRelationshipForbiddenRules:
    """v1.5: `to[other].forbidden` -> a category-3 rule.

    Generated from a field that did not exist in v1.4 on purpose — category 3
    is a hard failure, so a rule derived from data existing profiles already
    carry would fail them on upgrade.
    """

    SPEAKERS = {
        "mc": {"name": "Ethan",
               "forbidden": ["X"],
               "to": {"prof": {"address_pronoun": "formal", "forbidden": ["Y"]},
                      "amy": {"note": "close"}}},
        "prof": {"name": "Sandra"},
        "amy": {"name": "Amy"},
        "mc_q": {"name": "???", "alias_of": "mc"},
    }

    def rules(self):
        return characters.register_rules(self.SPEAKERS)

    def test_relationship_rule_is_generated(self):
        rule = next(r for r in self.rules() if r["category"] == 3)
        assert rule["name"] == "Ethan to Sandra: forbidden term"
        assert rule["pattern"] == "Y"
        assert rule["to"] == ["prof"]

    def test_it_carries_the_speaker_and_their_aliases(self):
        rule = next(r for r in self.rules() if r["category"] == 3)
        assert rule["speakers"] == ["mc", "mc_q"]

    def test_the_speaker_level_rule_is_untouched(self):
        rule = next(r for r in self.rules() if r["category"] == 2)
        assert (rule["pattern"], rule.get("to")) == ("X", None)

    def test_a_relationship_without_forbidden_generates_nothing(self):
        names = [r["name"] for r in self.rules()]
        assert not any("Amy" in n for n in names)

    def test_a_v14_to_map_generates_no_rules(self):
        speakers = {"mc": {"name": "Ethan", "to": {"prof": {"self_pronoun": "p"}}},
                    "prof": {"name": "Sandra"}}
        assert characters.register_rules(speakers) == []

    def test_addressee_codes_are_canonical(self):
        speakers = {"mc": {"name": "Ethan", "to": {"p_q": {"forbidden": ["Y"]}}},
                    "prof": {"name": "Sandra"},
                    "p_q": {"name": "???", "alias_of": "prof"}}
        rule = characters.register_rules(speakers)[0]
        assert rule["to"] == ["prof"]

    def test_malformed_relationship_entries_are_skipped(self):
        speakers = {"mc": {"name": "Ethan", "to": {"prof": "not a dict"}}}
        assert characters.register_rules(speakers) == []


class TestIsMonologue:
    """One definition, three consumers (prompt override, QA, resolver)."""

    def test_parenthesized_line(self):
        assert characters.is_monologue("(She looks tired.)")

    def test_plain_line(self):
        assert not characters.is_monologue("She looks tired.")

    def test_partial_parens(self):
        assert not characters.is_monologue("(Ugh) she said")
        assert not characters.is_monologue("")


class TestRelationshipForbiddenInPersonaCard:
    def test_the_prompt_asks_for_what_the_gate_checks(self):
        speakers = {"mc": {"name": "Ethan", "register": "casual",
                           "to": {"prof": {"address_pronoun": "formal",
                                           "forbidden": ["Y", "Z"]}}},
                    "prof": {"name": "Sandra"}}
        card = persona_card(speakers, "mc")
        assert "to Sandra: calls them formal; NEVER Y, Z" in card
        rule = next(r for r in register_rules(speakers) if r["category"] == 3)
        assert rule["pattern"] == "Y|Z"
