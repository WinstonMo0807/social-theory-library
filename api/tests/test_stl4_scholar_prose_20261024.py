"""Deferred acceptance definitions; no execution during implementation."""
from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from catalog.services.scholar_prose import bound_profile_prose, normalize_profile_prose


class ScholarProseTests(SimpleTestCase):
    def test_unicode_trim_and_fixed_format(self):
        value = normalize_profile_prose({"biography": {
            "text": "  甲😀乙  ", "text_style": "quote",
            "text_marks": [{"start": 3, "end": 5, "kind": "underline"}],
        }})
        self.assertEqual(value["biography"], {"text": "甲😀乙", "text_style": "quote", "text_marks": [{"start": 1, "end": 3, "kind": "underline"}]})
        with self.assertRaises(ValidationError):
            normalize_profile_prose({"biography": {"text": "😀", "text_marks": [{"start": 0, "end": 1, "kind": "strong"}]}})

    def test_changed_person_text_does_not_reuse_marks(self):
        curation = {"profile_prose": {"biography": {"text": "旧传记", "text_style": "quote", "text_marks": []}}}
        self.assertEqual(bound_profile_prose(curation, "", "新传记"), {})
        self.assertEqual(curation["profile_prose"]["biography"]["text"], "旧传记")

    def test_only_exact_published_prose_is_projected(self):
        saved = normalize_profile_prose({"short_description": {"text": "已发布导读", "text_marks": [{"start": 0, "end": 3, "kind": "strong"}]}})
        self.assertEqual(bound_profile_prose({"profile_prose": saved}, "已发布导读", ""), saved)
        self.assertEqual(bound_profile_prose({"profile_prose": saved}, "未发布改写", ""), {})

    def test_unsafe_links_and_arbitrary_markup_are_rejected(self):
        for extra in ({"html": "<script>bad()</script>"}, {"text_marks": [{"start": 0, "end": 1, "kind": "link", "href": "javascript:alert(1)"}]}):
            with self.assertRaises(ValidationError):
                normalize_profile_prose({"short_description": {"text": "导读", **extra}})

    def test_long_plain_text_and_malformed_legacy_format_survive(self):
        self.assertEqual(bound_profile_prose({"profile_prose": {"biography": {"text": "长" * 30001}}}, "", "长" * 30001), {})
        self.assertEqual(bound_profile_prose({"profile_prose": []}, "原导读", "原生平"), {})
