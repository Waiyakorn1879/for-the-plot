import replay_vars

SRC = '''
default seen = False
define narrator_name = "N"
init python:
    helper = 1
    def f():
        local_var = 2
label start:
    $ anniepath = 1
    $ anniepath += 1
    $ flag = True
    $ seen = True
    $ helper = 5
    $ title = "Boss"
    $ mc = renpy.input("name?")
    $ obj.attr = 3
'''


def test_only_play_assigned_undefaulted_names(tmp_path):
    (tmp_path / "a.rpy").write_text(SRC, encoding="utf-8")
    found = replay_vars.candidates(tmp_path)
    assert set(found) == {"anniepath", "flag", "title", "mc"}
    assert found["anniepath"]["rhs"] == "1"          # first assignment wins


def test_neutral_values():
    assert replay_vars.neutral("True") is False
    assert replay_vars.neutral("7") == 0
    assert replay_vars.neutral('"x"') == ""
    assert replay_vars.neutral("renpy.input('a')") is None
