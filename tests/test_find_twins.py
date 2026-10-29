from find_twins import find_twins


def test_differing_twins_found_identical_ignored():
    tr = {'Say \\"hi\\"': "A", 'Say "hi"': "B",
          "It’s": "X", "It's": "X",
          "Solo": "S"}
    assert [n for n, _ in find_twins(tr)] == ['Say "hi"']


def test_value_escaping_mirroring_key_is_not_a_difference():
    assert find_twins({'a \\"b\\"': 'x \\"y\\"', 'a "b"': 'x "y"'}) == []
