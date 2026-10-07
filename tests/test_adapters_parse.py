"""Adapter result-parsing contract.

These pin the degradation rules from `adapters/base.py`. The fenced-JSON case is
not hypothetical: a run whose result was wrapped in a markdown fence once looked
like it had done nothing, because the structured parse simply failed.
"""

import unittest

from taskproof.adapters.base import ResultParseError, extract_json


class ExtractJsonTest(unittest.TestCase):
    def test_plain_object(self):
        self.assertEqual(extract_json('{"status": "ok"}'), {"status": "ok"})

    def test_fenced_with_language_tag(self):
        text = 'Here you go:\n```json\n{"status": "ok", "files": 3}\n```\nDone.'
        self.assertEqual(extract_json(text), {"status": "ok", "files": 3})

    def test_fenced_without_language_tag(self):
        text = '```\n{"status": "ok"}\n```'
        self.assertEqual(extract_json(text), {"status": "ok"})

    def test_trailing_noise_after_object(self):
        text = '{"status": "ok"}\n\n[notice] telemetry flushed'
        self.assertEqual(extract_json(text), {"status": "ok"})

    def test_nested_object_survives_fence(self):
        text = '```json\n{"a": {"b": [1, 2]}, "c": null}\n```'
        self.assertEqual(extract_json(text), {"a": {"b": [1, 2]}, "c": None})

    def test_raises_on_garbage(self):
        with self.assertRaises(ResultParseError):
            extract_json("no json here at all")

    def test_raises_on_empty(self):
        with self.assertRaises(ResultParseError):
            extract_json("")


if __name__ == "__main__":
    unittest.main()
