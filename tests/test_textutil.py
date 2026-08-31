from vharness.textutil import extract_json_block, mask_positions, strip_code_fences


def test_strip_fences_basic():
    assert strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_fences_none_present():
    assert strip_code_fences('{"a": 1}') == '{"a": 1}'


def test_extract_json_with_surrounding_prose():
    text = 'Here is my analysis:\n{"has_vulnerability": false, "vulnerabilities": []}\nDone.'
    assert extract_json_block(text) == '{"has_vulnerability": false, "vulnerabilities": []}'


def test_extract_json_nested_and_strings_with_braces():
    text = '{"a": {"b": "literal } brace"}, "c": [1, 2]}'
    assert extract_json_block(text) == text


def test_extract_json_none():
    assert extract_json_block("no json here") is None


def test_mask_ignores_braces_in_strings_and_comments():
    code = 'int x = 0; /* } */ char *s = "}"; if (x) { y(); }'
    masked = mask_positions(code)
    assert code.index("/* } */") in masked
    assert code.index('"}"') in masked
    assert code.index("if (x) {") not in masked
