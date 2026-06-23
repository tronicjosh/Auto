import pytest

from antenna_reader.extract import ExtractionError, parse_model_json


def test_raw_json():
    assert parse_model_json('{"a": 1}') == {"a": 1}


def test_fenced_json():
    assert parse_model_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_prose_preamble_then_fenced():
    assert parse_model_json('I will analyse this now:\n\n```json\n{"a": 1}\n```') == {"a": 1}


def test_prose_with_braces_then_fenced():
    # The brace-based fallback alone would grab the prose '{x}'; the fence anchor fixes it.
    assert parse_model_json('Consider band {x} 698-960.\n```json\n{"a": 1}\n```') == {"a": 1}


def test_prose_then_raw_json():
    assert parse_model_json('Some reasoning.\n{"a": 1}') == {"a": 1}


def test_no_json_raises():
    with pytest.raises(ExtractionError):
        parse_model_json("there is no json here at all")
