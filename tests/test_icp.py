"""Tests unitaires pour icp.py — fonctions pures, pas d'appels API."""

import json
import pytest
from icp import _clean_json


def test_clean_json_plain():
    raw = '{"key": "value"}'
    assert _clean_json(raw) == '{"key": "value"}'


def test_clean_json_strips_whitespace():
    raw = '  \n{"key": "value"}\n  '
    assert _clean_json(raw) == '{"key": "value"}'


def test_clean_json_strips_markdown_with_lang():
    raw = '```json\n{"key": "value"}\n```'
    result = _clean_json(raw)
    assert json.loads(result) == {"key": "value"}


def test_clean_json_strips_markdown_no_lang():
    raw = '```\n{"key": "value"}\n```'
    result = _clean_json(raw)
    assert json.loads(result) == {"key": "value"}


def test_clean_json_nested_object():
    raw = '{"a": {"b": [1, 2, 3]}}'
    result = json.loads(_clean_json(raw))
    assert result["a"]["b"] == [1, 2, 3]


def test_clean_json_array():
    raw = '[{"score": 90}, {"score": 70}]'
    result = json.loads(_clean_json(raw))
    assert len(result) == 2
    assert result[0]["score"] == 90
