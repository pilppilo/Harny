"""Boundary codec tests."""

import pytest

from vharness.agent.codec import canonical_json, parse_json_object
from vharness.agent.errors import ContractError


def test_canonical_json_is_stable_and_rejects_non_finite_values():
    assert canonical_json({"b": 1, "a": [True, None]}) == '{"a":[true,null],"b":1}'
    with pytest.raises(ContractError, match="finite"):
        canonical_json({"value": float("nan")})


def test_json_object_decoder_rejects_non_objects_and_non_finite_constants():
    with pytest.raises(ContractError, match="expected a JSON object"):
        parse_json_object("[]")
    with pytest.raises(ContractError, match="non-finite"):
        parse_json_object('{"value": NaN}')
