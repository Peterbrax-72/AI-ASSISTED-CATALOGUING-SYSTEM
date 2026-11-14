"""Offline tests. Run from the project folder:  python -m unittest discover -s tests -v
No network is used; external APIs are replaced with fakes."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import classifier as C  # noqa: E402
import server as S  # noqa: E402


def inferred(title, subjects=(), description=""):
    return C.classify({"title": title, "subject": list(subjects), "description": description})


class ClassifierInference(unittest.TestCase):
    def num(self, *a, **k):
        return inferred(*a, **k)["classification"]["number"]

    def test_python_programming_is_class_005(self):
        self.assertTrue(self.num("Learning Python", ["Python (Computer program language)"]).startswith("005"))

    def test_general_computer_science_is_004(self):
        self.assertEqual(self.num("Introduction to Computer Science"), "004")

    def test_library_cataloguing_is_025_3(self):
        self.assertEqual(self.num("Cataloging and Classification for Librarians"), "025.3")

    def test_general_psychology_150(self):
        self.assertEqual(self.num("Introduction to Psychology"), "150")

    def test_applied_psychology_self_help(self):
        self.assertEqual(self.num("The Mountain Is You", ["Self-help techniques", "Self-sabotage"]), "158.1")

    def test_educational_psychology(self):
        self.assertEqual(self.num("Educational Psychology"), "370.15")

    def test_religion_200(self):
        self.assertEqual(self.num("Understanding Religion"), "200")

    def test_economics_330(self):
        self.assertEqual(self.num("Principles of Economics"), "330")

    def test_chemistry_540_and_exercises_540_76(self):
        self.assertEqual(self.num("General Chemistry"), "540")
        self.assertEqual(self.num("Chemistry Problems and Exercises"), "540.76")

    def test_education_370(self):
        self.assertEqual(self.num("Foundations of Education"), "370")

    def test_journalism_070_4(self):
        self.assertEqual(self.num("Journalism: A Digital Age Guide", description="Reporting with digital technology and computer tools."), "070.4")

    def test_kenya_history_is_specific(self):
        self.assertEqual(self.num("A History of Kenya"), "967.62")

    def test_psychology_not_ict_because_description_says_computer(self):
        r = inferred("Psychology of Habits", ["Psychology"], "Uses a computer model and computer programs.")
        self.assertEqual(r["classification"]["number"], "150")

    def test_python_snake_not_programming(self):
        self.assertFalse((self.num("Pythons of the world", ["Snakes"]) or "").startswith("005"))

    def test_no_evidence_is_not_000(self):
        r = inferred("Zxqv")
        self.assertIsNone(r["classification"]["number"])
        self.assertEqual(r["shelf"], "Librarian review required")

    def test_science_not_triggered_by_computer_science(self):
        self.assertEqual(self.num("Computer Science Basics"), "004")

    def test_motivating_library_staff_without_source(self):
        self.assertEqual(self.num("Motivating Today's Library Staff"), "023")

    def test_inferred_is_flagged_for_review(self):
        c = inferred("Introduction to Psychology")["classification"]
        self.assertEqual(c["provenance"], "inferred")
        self.assertTrue(c["review_required"])


class RealTitles(unittest.TestCase):
    def test_adult_education_in_uganda(self):
        r = inferred("Adult education in Uganda")
        self.assertEqual(r["classification"]["number"], "374.96761")  # matches a Makerere catalogue record
        self.assertEqual(r["lcsh_terms"][0], "Adult education -- Uganda")
        self.assertIn("Uganda", r["primary_subject"])
        self.assertTrue(r["shelf"].startswith("300–399"))

    def test_place_alone_is_not_history(self):
        self.assertEqual(inferred("Adult education in Kenya")["classification"]["number"], "374.96762")
        self.assertEqual(inferred("A Political History of Uganda")["classification"]["number"], "967.61")

    def test_mountain_is_you_with_open_library_data(self):
        r = C.classify({"title": "The Mountain Is You", "author_name": ["Brianna Wiest"],
                        "subject": ["Self-help techniques", "Self-defeating behavior", "Self-realization"],
                        "source_ddcs": [{"number": "158.1", "source": "Open Library"}],
                        "lcc": [{"number": "BF637.S37W5 2024", "source": "Open Library"}]})
        self.assertEqual(r["classification"]["number"], "158.1")
        self.assertIsNone(r["conflict"])
        self.assertEqual(r["suggested_call_number"]["value"], "158.1 WIE")
        self.assertEqual(r["call_number"]["type"], "not_available")  # LC class is not a call number

    def test_guide_to_living_amphibians(self):
        r = inferred("Guide to Living Amphibians", ["Amphibians"])
        self.assertEqual(r["classification"]["number"], "597.8")
        self.assertEqual(r["primary_subject"], "Amphibians")
        self.assertEqual(r["suggested_call_number"]["value"], "597.8 XXX")
        r2 = C.classify({"title": "Guide to Living Amphibians", "author_name": ["J.E. Webb", "J.A. Wallwork"],
                         "subject": ["Amphibians"]})
        self.assertEqual(r2["suggested_call_number"]["value"], "597.8 WEB")
        self.assertTrue(r2["shelf"].startswith("500–599"))

    def test_python_snake_still_not_programming_and_fishing_not_fish(self):
        self.assertEqual(inferred("Python snakes", ["Snakes"])["classification"]["number"], "597.9")
        self.assertNotEqual(inferred("Fly fishing basics")["classification"]["number"], "597")

    def test_scholarly_noise_does_not_override_the_book(self):
        r = C.classify({"title": "Guide to Living Amphibians", "subject": ["Amphibians", "Natural history"],
                        "scholarly_subjects": ["History and criticism", "History", "History in art", "History and criticism -- Theory, etc."]})
        self.assertEqual(r["classification"]["number"], "597.8")

    def test_natural_history_is_not_history(self):
        self.assertNotEqual(inferred("Natural history of birds", ["Natural history"])["classification"]["number"], "900")

    def test_article_not_merged_into_book(self):
        book = S.make_doc("Open Library", title="Guide to Living Amphibians", author_name=["J. E. Webb"], first_publish_year=1978)
        art = S.make_doc("Crossref", title="Guide to Living Amphibians", author_name=["J.E. Webb"], first_publish_year=1978,
                         type="journal-article", metadata_type="scholarly_bibliographic_record", scholarly_subjects=["History"])
        merged = S.merge_docs([[book], [art]])
        self.assertEqual(len(merged), 2)

    def test_author_names_deduped(self):
        self.assertEqual(S.unique_names(["J. E. Webb", "J.E. Webb", "j e webb"]), ["J. E. Webb"])

    def test_no_cache_headers_and_build(self):
        r = S.app.test_client().get("/static/app.js")
        self.assertEqual(r.headers["Cache-Control"], "no-store")
        self.assertEqual(S.app.test_client().get("/health").get_json()["version"], "6.1")

    def test_unknown_title_is_left_for_review(self):
        r = inferred("Enjoy your today but consider your tomorrow")
        self.assertIsNone(r["classification"]["number"])


class SourceDdc(unittest.TestCase):
    def test_strict_normalization(self):
        n = C.normalize_ddc
        self.assertEqual(n("023/.9"), "023.9")
        self.assertEqual(n("658.3/124"), "658.3124")
        self.assertEqual(n("[B]"), None)
        self.assertEqual(n("Fic"), None)
        self.assertEqual(n("HF5549.5"), None)  # LC number must never become DDC "554"
        self.assertEqual(n("j823.914"), "823.914")
        self.assertEqual(n("823.914 22"), "823.914")

    def test_source_ddc_drives_subject_and_shelf_consistently(self):
        r = C.classify({
            "title": "Motivating Today's Library Staff", "source": "Open Library",
            "subject": ["Library employees", "Motivation (Psychology)"],
            "source_ddcs": [{"number": "023.9", "source": "Open Library"}],
        })
        self.assertEqual(r["classification"]["number"], "023.9")
        self.assertEqual(r["classification"]["provenance"], "source_record")
        self.assertIn("library", r["primary_subject"].lower())
        self.assertTrue(r["shelf"].startswith("000–099"))
        self.assertNotIn("158", r["shelf"])
        self.assertTrue(r["suggested_call_number"]["value"].startswith("023.9 "))
        self.assertEqual(r["call_number"]["type"], "not_available")
        self.assertIsNone(r["conflict"])

    def test_conflict_is_flagged_not_mixed(self):
        r = C.classify({"title": "Introduction to Psychology", "subject": ["Psychology"],
                        "source_ddcs": [{"number": "004", "source": "X"}]})
        self.assertEqual(r["classification"]["number"], "004")
        self.assertIsNotNone(r["conflict"])
        self.assertEqual(r["conflict"]["inferred_number"], "150")
        self.assertTrue(r["shelf"].startswith("000–099"))

    def test_consensus_source_ddc_wins(self):
        c, _ = C.choose_source_ddc([{"number": "150", "source": "A"}, {"number": "150.1", "source": "B"},
                                    {"number": "004", "source": "C"}])
        self.assertTrue(c["number"].startswith("150"))

    def test_shelf_always_derived_from_number(self):
        self.assertEqual(C.shelf_for("540.76"), "500–599 • Science › Chemistry (540)")
        self.assertEqual(C.shelf_for("023.9"),
                         "000–099 • Computer science, information & general works › Library & information sciences (020)")
        self.assertEqual(C.shelf_for("150"), "100–199 • Philosophy & psychology › Psychology (150)")

    def test_source_call_number_kept_and_labelled(self):
        r = C.classify({"title": "T", "subject": ["Psychology"], "author_name": ["Smith, Jane"],
                        "source_call_numbers": [{"value": "BF121 .S65 2010", "source": "Library of Congress"}]})
        self.assertEqual(r["call_number"]["value"], "BF121 .S65 2010")
        self.assertEqual(r["call_number"]["source"], "Library of Congress")
        self.assertEqual(r["suggested_call_number"]["type"], "generated_suggestion")

    def test_author_mark(self):
        self.assertEqual(C.author_mark("Smith, John"), "SMI")
        self.assertEqual(C.author_mark("John R. Smith Jr."), "SMI")
        self.assertEqual(C.author_mark(None), "XXX")


class MergeAndRank(unittest.TestCase):
    def test_merge_keeps_all_source_data(self):
        ol = S.make_doc("Open Library", title="The Mountain Is You", author_name=["Brianna Wiest"],
                        isbn=["9781949759228"], first_publish_year=2020, ddc=["158.1"])
        gb = S.make_doc("Google Books", title="The Mountain Is You: Transforming Self-Sabotage",
                        author_name=["Brianna Wiest"], isbn=["1949759229"], number_of_pages=240,
                        description="A book.")
        merged = S.merge_docs([[ol], [gb]])
        self.assertEqual(len(merged), 1)
        m = merged[0]
        self.assertEqual(m["sources"], ["Open Library", "Google Books"])
        self.assertEqual(m["number_of_pages"], 240)
        self.assertEqual(m["source_ddcs"][0]["source"], "Open Library")

    def test_different_years_not_merged_blindly(self):
        a = S.make_doc("Open Library", title="Statistics", author_name=["Jo Doe"], first_publish_year=1999)
        b = S.make_doc("Google Books", title="Statistics", author_name=["Jo Doe"], first_publish_year=2015)
        self.assertEqual(len(S.merge_docs([[a], [b]])), 2)

    def test_isbn10_matches_isbn13(self):
        self.assertEqual(S.to_isbn13("1949759229"), "9781949759228")

    def test_isbn_query_ranking(self):
        match = S.make_doc("Open Library", title="Other", isbn=["9781949759228"])
        other = S.make_doc("Open Library", title="Other", isbn=["9780000000002"])
        self.assertGreater(S.search_relevance(match, "978-1-949759-22-8"), S.search_relevance(other, "978-1-949759-22-8"))

    def test_article_ranks_below_book(self):
        book = S.make_doc("Open Library", title="The Mountain Is You", author_name=["Brianna Wiest"])
        article = S.make_doc("OpenAlex", title="The mountain is you: climate in mountain environments",
                             type="article", metadata_type="scholarly_bibliographic_record")
        q = "the mountain is you"
        self.assertGreater(S.search_relevance(book, q), S.search_relevance(article, q))

    def test_text_of_strips_jats(self):
        self.assertEqual(S.text_of("<jats:p>Hello <b>world</b></jats:p>"), "Hello world")
        self.assertEqual(S.text_of({"value": "Hi"}), "Hi")


class FakeResp:
    def __init__(self, code=200, data=None, bad_json=False):
        self.status_code, self._d, self._bad = code, data, bad_json

    def json(self):
        if self._bad:
            raise ValueError("bad")
        return self._d


class ApiBehaviour(unittest.TestCase):
    def setUp(self):
        S._cache.clear()
        self.client = S.app.test_client()

    def test_error_kinds(self):
        import requests
        cases = [(FakeResp(429), "quota"), (FakeResp(403), "auth"), (FakeResp(500), "http_error"),
                 (FakeResp(200, bad_json=True), "invalid_response")]
        for resp, kind in cases:
            with mock.patch.object(S.session, "get", return_value=resp):
                with self.assertRaises(S.SourceError) as cm:
                    S.request_json("http://x")
                self.assertEqual(cm.exception.kind, kind)
        with mock.patch.object(S.session, "get", side_effect=requests.Timeout()):
            with self.assertRaises(S.SourceError) as cm:
                S.request_json("http://x")
            self.assertEqual(cm.exception.kind, "timeout")

    def test_total_failure_is_not_reported_as_empty(self):
        with mock.patch.object(S.session, "get", return_value=FakeResp(429)):
            data = self.client.get("/api/search?q=anything").get_json()
        self.assertTrue(data["fallback"])
        self.assertTrue(data["all_sources_failed"])
        self.assertIn("NOT an empty result", data["message"])
        self.assertTrue(all(s["status"] == "failed" and s["error_kind"] == "quota" for s in data["sources"]))

    def test_empty_success_differs_from_failure(self):
        def fake(url, **kw):
            if "crossref" in url:
                return FakeResp(200, {"message": {"items": []}})
            if "googleapis" in url:
                return FakeResp(200, {"items": []})
            if "openalex" in url:
                return FakeResp(200, {"results": []})
            if "loc.gov" in url:
                return FakeResp(200, {"results": []})
            return FakeResp(200, {"docs": []})
        with mock.patch.object(S.session, "get", side_effect=fake):
            data = self.client.get("/api/search?q=zzzz").get_json()
        self.assertFalse(data["all_sources_failed"])
        self.assertTrue(all(s["status"] == "no_results" for s in data["sources"]))

    def test_partial_success_and_merge_through_api(self):
        def fake(url, **kw):
            if "openlibrary" in url:
                return FakeResp(200, {"docs": [{"key": "/works/1", "title": "Motivating Today's Library Staff",
                                                "author_name": ["Rooney"], "ddc": ["023/.9"],
                                                "subject": ["Library employees"]}]})
            return FakeResp(429)
        with mock.patch.object(S.session, "get", side_effect=fake):
            data = self.client.get("/api/search?q=Motivating Today's Library Staff").get_json()
        self.assertFalse(data["fallback"])
        self.assertEqual(data["docs"][0]["source_ddcs"][0]["number"], "023.9")
        self.assertIn("incomplete", data["message"])

    def test_classify_endpoint(self):
        r = self.client.post("/api/classify", json={"title": "Educational Psychology"})
        self.assertEqual(r.get_json()["classification"]["number"], "370.15")
        self.assertEqual(self.client.post("/api/classify", data="nope").status_code, 400)

    def test_source_code_not_served(self):
        for path in ("/static/server.py", "/static/classifier.py", "/static/../server.py", "/static/README.txt"):
            self.assertEqual(self.client.get(path).status_code, 404, path)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)
        self.assertEqual(self.client.get("/static/style.css").status_code, 200)

    def test_lcsh_parsing(self):
        raw = ["libraries", ["Libraries", "Libraries--Kenya"], ["", ""], ["http://id.loc.gov/a", "http://id.loc.gov/b"]]
        with mock.patch.object(S.session, "get", return_value=FakeResp(200, raw)):
            data = self.client.get("/api/lcsh?q=libraries").get_json()
        self.assertEqual(data["headings"], ["Libraries", "Libraries--Kenya"])
        self.assertEqual(data["verification"], "authority_candidate_unverified")


if __name__ == "__main__":
    unittest.main()
