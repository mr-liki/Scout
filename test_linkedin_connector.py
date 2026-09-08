import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import linkedin_connector as lc


# ============================================================
# TEST FIXTURES / FAKES
# ============================================================


class FakeClock:
    def __init__(self, start_epoch=1_700_000_000.0, start_monotonic=1_000_000.0):
        self.epoch = start_epoch
        self.mono = start_monotonic

    def time(self):
        return self.epoch

    def monotonic(self):
        return self.mono

    def advance(self, seconds):
        self.epoch += seconds
        self.mono += seconds


class FakeResponse:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.encoding = None

    def raise_for_status(self):
        if self.status_code >= 400:
            raise lc.requests.HTTPError(f"HTTP {self.status_code}")


CARD_TEMPLATE = (
    '<div class="job-search-card" '
    'data-entity-urn="urn:li:fs_normalized_jobPosting:jobPosting:{job_id}" '
    'data-row="{row}">'
    '<h3 class="base-search-card__title">{title}</h3>'
    '<a class="base-card__full-link" '
    'href="https://www.linkedin.com/jobs/view/{slug}-{job_id}"></a>'
    '<a class="hidden-nested-link" '
    'href="https://www.linkedin.com/company/acme">Acme Corp</a>'
    '<span class="job-search-card__location">Remote</span>'
    '<time class="job-search-card__listdate" datetime="2026-01-01">'
    '{posted}</time>'
    '</div>'
)


def make_page_html(job_specs):
    """job_specs: list of (job_id, posted_text, title)"""
    return "\n".join(
        CARD_TEMPLATE.format(
            job_id=jid,
            row=i,
            title=title,
            slug=title.lower().replace(" ", "-"),
            posted=posted,
        )
        for i, (jid, posted, title) in enumerate(job_specs)
    )


DETAIL_TEMPLATE = (
    '<h2 class="topcard__title">{title}</h2>'
    '<a class="topcard__link" '
    'href="https://www.linkedin.com/jobs/view/{slug}-{job_id}"></a>'
    '<a class="topcard__org-name-link" '
    'href="https://www.linkedin.com/company/acme">Acme Corp</a>'
    '<span class="posted-time-ago__text">{posted}</span>'
    '<span class="num-applicants__caption">{applicants}</span>'
)


def make_detail_html(job_id, posted, applicants="", title="Software Engineer"):
    return DETAIL_TEMPLATE.format(
        job_id=job_id,
        title=title,
        slug=title.lower().replace(" ", "-"),
        posted=posted,
        applicants=applicants,
    )


def fresh_rate_session(**overrides):
    kwargs = dict(
        rate_min_interval=0,
        rate_max_interval=0.01,
        rate_cooldown_base=0.01,
        rate_cooldown_cap=0.05,
        rate_burst_size=0,
        rate_burst_rest=0,
    )
    kwargs.update(overrides)
    return lc.create_session(**kwargs)


# ============================================================
# TEST 1 / TEST 4 - PAGINATION + MANUAL START
# ============================================================


class TestScanSearchPagination(unittest.TestCase):
    def setUp(self):
        self.session = fresh_rate_session()

    def test_pagination_survives_stale_pages(self):
        # requested window = 5 minutes = 300s
        pages = {
            0: [("101", "20 minutes ago", "Engineer A")],
            10: [("102", "25 minutes ago", "Engineer B")],
            20: [("103", "5 minutes ago", "Engineer C")],
        }

        def fake_fetch_search_page(session, keywords, location, start, **kwargs):
            specs = pages.get(start)
            if not specs:
                return []
            html = make_page_html(specs)
            return lc.parse_search_results(
                html,
                requested_fresh_seconds=kwargs.get("requested_fresh_seconds"),
                under_10=kwargs.get("under_10", False),
                easy_apply=kwargs.get("easy_apply", False),
            )

        with mock.patch.object(
            lc, "fetch_search_page", side_effect=fake_fetch_search_page
        ), mock.patch("time.sleep", return_value=None):
            jobs, stats = lc.scan_search(
                session=self.session,
                keywords="engineer",
                location="India",
                requested_fresh_seconds=300,
                server_window_seconds=3600,
                under_10=False,
                easy_apply=False,
                sort_mode="newest",
                max_jobs=50,
                max_pages=5,
                page_delay=0,
                detail_html_cache={},
            )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_id"], "103")
        self.assertEqual(stats["stale_dropped"], 2)

    def test_manual_start_offset_requests_correct_pages(self):
        requested_starts = []
        pages = {
            140: [("201", "1 minutes ago", "A")],
            150: [("202", "1 minutes ago", "B")],
            160: [("203", "1 minutes ago", "C")],
        }

        def fake_fetch_search_page(session, keywords, location, start, **kwargs):
            requested_starts.append(start)
            specs = pages.get(start, [])
            if not specs:
                return []
            html = make_page_html(specs)
            return lc.parse_search_results(
                html,
                requested_fresh_seconds=None,
                under_10=False,
                easy_apply=False,
            )

        with mock.patch.object(
            lc, "fetch_search_page", side_effect=fake_fetch_search_page
        ), mock.patch("time.sleep", return_value=None):
            jobs, stats = lc.scan_search(
                session=self.session,
                keywords="engineer",
                location="India",
                requested_fresh_seconds=None,
                server_window_seconds=None,
                under_10=False,
                easy_apply=False,
                sort_mode="newest",
                max_jobs=50,
                max_pages=3,
                page_delay=0,
                detail_html_cache={},
                start_offset=140,
            )

        self.assertEqual(requested_starts, [140, 150, 160])
        self.assertEqual(len(jobs), 3)
        self.assertEqual(stats["stop_reason"], "max_pages")
        # Next page to fetch after this run's budget is exhausted.
        self.assertEqual(stats["resume_start"], 170)


# ============================================================
# TEST 5 - INVALID --start VALUES
# ============================================================


class TestStartValidation(unittest.TestCase):
    def test_valid_values(self):
        self.assertEqual(lc.validate_start_offset(0), 0)
        self.assertEqual(lc.validate_start_offset(140), 140)

    def test_negative_rejected(self):
        with self.assertRaises(ValueError):
            lc.validate_start_offset(-10)

    def test_non_multiple_rejected(self):
        with self.assertRaises(ValueError):
            lc.validate_start_offset(17)


# ============================================================
# TEST 2 / TEST 3 / TEST 9 / TEST 10 - CIRCUIT BREAKER
# ============================================================


class TestCircuitBreaker(unittest.TestCase):
    def setUp(self):
        self.session = fresh_rate_session()

    def _install(self, dispatcher):
        self.session.get = lambda url, params=None, timeout=None: dispatcher(
            url, params
        )

    def test_soft_limit_circuit_breaker(self):
        good_pages = {
            0: [("301", "1 minutes ago", "A")],
            10: [("302", "1 minutes ago", "B")],
            20: [("303", "1 minutes ago", "C")],
        }

        def dispatcher(url, params):
            self.assertEqual(url, lc.SEARCH_URL)
            start = params.get("start")
            if start in good_pages:
                return FakeResponse(200, make_page_html(good_pages[start]))
            if start == 30:
                return FakeResponse(
                    200,
                    "This page requires additional security "
                    "verification (captcha) before continuing.",
                )
            return FakeResponse(200, "")

        self._install(dispatcher)

        with mock.patch("time.sleep", return_value=None):
            jobs, stats = lc.scan_search(
                session=self.session,
                keywords="engineer",
                location="India",
                requested_fresh_seconds=None,
                server_window_seconds=None,
                under_10=False,
                easy_apply=False,
                sort_mode="newest",
                max_jobs=100,
                max_pages=10,
                page_delay=0,
                detail_html_cache={},
            )

        self.assertEqual(len(jobs), 3)
        self.assertEqual(stats["search_status"], "partial")
        self.assertFalse(stats["search_complete"])
        self.assertEqual(stats["stop_reason"], "soft_limit_circuit_breaker")
        self.assertTrue(stats["circuit_breaker_opened"])
        self.assertEqual(stats["resume_start"], 30)
        self.assertFalse(stats["empty_result_is_conclusive"])

        resume = lc.build_resume_info(stats)
        self.assertTrue(resume["available"])
        self.assertEqual(resume["start"], 30)
        self.assertEqual(resume["linkedin_page"], 4)
        self.assertEqual(resume["reason"], "soft_limit_circuit_breaker")

    def test_circuit_breaker_on_first_page(self):
        def dispatcher(url, params):
            return FakeResponse(
                200, "Please complete this security verification challenge."
            )

        self._install(dispatcher)

        with mock.patch("time.sleep", return_value=None):
            jobs, stats = lc.scan_search(
                session=self.session,
                keywords="engineer",
                location="India",
                requested_fresh_seconds=None,
                server_window_seconds=None,
                under_10=False,
                easy_apply=False,
                sort_mode="newest",
                max_jobs=100,
                max_pages=10,
                page_delay=0,
                detail_html_cache={},
            )

        self.assertEqual(jobs, [])
        self.assertEqual(stats["search_status"], "failed")
        self.assertFalse(stats["search_complete"])
        self.assertFalse(stats["empty_result_is_conclusive"])
        self.assertEqual(stats["resume_start"], 0)

    def test_hard_rate_limit_circuit_breaker(self):
        good_pages = {0: [("401", "1 minutes ago", "A")]}

        def dispatcher(url, params):
            start = params.get("start")
            if start in good_pages:
                return FakeResponse(200, make_page_html(good_pages[start]))
            if start == 10:
                return FakeResponse(429, "", headers={"Retry-After": "0"})
            return FakeResponse(200, "")

        self._install(dispatcher)

        with mock.patch("time.sleep", return_value=None):
            jobs, stats = lc.scan_search(
                session=self.session,
                keywords="engineer",
                location="India",
                requested_fresh_seconds=None,
                server_window_seconds=None,
                under_10=False,
                easy_apply=False,
                sort_mode="newest",
                max_jobs=100,
                max_pages=10,
                page_delay=0,
                detail_html_cache={},
            )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(stats["search_status"], "partial")
        self.assertFalse(stats["search_complete"])
        self.assertEqual(stats["stop_reason"], "hard_rate_limit_circuit_breaker")
        self.assertTrue(stats["circuit_breaker_opened"])
        self.assertEqual(stats["circuit_breaker_reason"], "hard_rate_limit")
        self.assertEqual(stats["resume_start"], 10)

    def test_soft_limit_recovery_keeps_circuit_closed(self):
        call_counts = {}
        good_pages = {0: [("501", "1 minutes ago", "A")]}

        def dispatcher(url, params):
            start = params.get("start")
            call_counts[start] = call_counts.get(start, 0) + 1
            if start == 0:
                if call_counts[start] == 1:
                    return FakeResponse(
                        200, "Unusual activity detected, please verify."
                    )
                return FakeResponse(200, make_page_html(good_pages[0]))
            return FakeResponse(200, "")

        self._install(dispatcher)

        with mock.patch("time.sleep", return_value=None):
            jobs, stats = lc.scan_search(
                session=self.session,
                keywords="engineer",
                location="India",
                requested_fresh_seconds=None,
                server_window_seconds=None,
                under_10=False,
                easy_apply=False,
                sort_mode="newest",
                max_jobs=100,
                max_pages=5,
                page_delay=0,
                detail_html_cache={},
            )

        self.assertEqual(len(jobs), 1)
        self.assertFalse(stats["circuit_breaker_opened"])
        self.assertGreaterEqual(
            self.session.scout_rate_controller.soft_limit_recoveries, 1
        )


# ============================================================
# TEST 8 / TEST 11 / TEST 12 - END OF RESULTS
# ============================================================


class TestEndOfResults(unittest.TestCase):
    def setUp(self):
        self.session = fresh_rate_session()

    def _install(self, session, dispatcher):
        session.get = lambda url, params=None, timeout=None: dispatcher(url, params)

    def test_normal_end_of_results(self):
        short_page = [(f"{600 + i}", "1 minutes ago", "A") for i in range(5)]

        def dispatcher(url, params):
            start = params.get("start")
            if start == 0:
                return FakeResponse(200, make_page_html(short_page))
            if start == 10:
                return FakeResponse(200, "<!-- no more postings -->")
            return FakeResponse(200, "")

        self._install(self.session, dispatcher)

        with mock.patch("time.sleep", return_value=None):
            jobs, stats = lc.scan_search(
                session=self.session,
                keywords="engineer",
                location="India",
                requested_fresh_seconds=None,
                server_window_seconds=None,
                under_10=False,
                easy_apply=False,
                sort_mode="newest",
                max_jobs=100,
                max_pages=5,
                page_delay=0,
                detail_html_cache={},
            )

        self.assertEqual(len(jobs), 5)
        self.assertEqual(stats["stop_reason"], "end_of_results")
        self.assertTrue(stats["search_complete"])
        self.assertEqual(stats["search_status"], "success")
        self.assertFalse(stats["circuit_breaker_opened"])
        self.assertIsNone(stats["resume_start"])

    def test_genuine_empty_search_is_conclusive(self):
        def dispatcher(url, params):
            return FakeResponse(200, "")

        self._install(self.session, dispatcher)

        with mock.patch("time.sleep", return_value=None):
            jobs, stats = lc.scan_search(
                session=self.session,
                keywords="engineer",
                location="Nowhere",
                requested_fresh_seconds=None,
                server_window_seconds=None,
                under_10=False,
                easy_apply=False,
                sort_mode="newest",
                max_jobs=100,
                max_pages=5,
                page_delay=0,
                detail_html_cache={},
            )

        self.assertEqual(jobs, [])
        self.assertEqual(stats["search_status"], "success")
        self.assertTrue(stats["search_complete"])
        self.assertTrue(stats["empty_result_is_conclusive"])

    def test_failed_search_differs_from_empty_success(self):
        def failing_dispatcher(url, params):
            return FakeResponse(200, "Please complete a captcha challenge.")

        def empty_dispatcher(url, params):
            return FakeResponse(200, "")

        self._install(self.session, failing_dispatcher)
        with mock.patch("time.sleep", return_value=None):
            _, failed_stats = lc.scan_search(
                session=self.session,
                keywords="engineer",
                location="India",
                requested_fresh_seconds=None,
                server_window_seconds=None,
                under_10=False,
                easy_apply=False,
                sort_mode="newest",
                max_jobs=10,
                max_pages=3,
                page_delay=0,
                detail_html_cache={},
            )

        session2 = fresh_rate_session()
        self._install(session2, empty_dispatcher)
        with mock.patch("time.sleep", return_value=None):
            _, empty_stats = lc.scan_search(
                session=session2,
                keywords="engineer",
                location="India",
                requested_fresh_seconds=None,
                server_window_seconds=None,
                under_10=False,
                easy_apply=False,
                sort_mode="newest",
                max_jobs=10,
                max_pages=3,
                page_delay=0,
                detail_html_cache={},
            )

        self.assertNotEqual(
            failed_stats["search_status"], empty_stats["search_status"]
        )
        self.assertFalse(failed_stats["empty_result_is_conclusive"])
        self.assertTrue(empty_stats["empty_result_is_conclusive"])


# ============================================================
# TEST 6 - EXPIRATION BEFORE OUTPUT
# ============================================================


class TestFreshnessExpiration(unittest.TestCase):
    def test_job_expires_before_output(self):
        clock = FakeClock()
        with mock.patch("time.time", clock.time), mock.patch(
            "time.monotonic", clock.monotonic
        ):
            job = {}
            lc.record_posted_observation(
                job,
                "9 minutes ago",
                source="linkedin_search_card_relative_display",
                observed_at_epoch=clock.time(),
            )
            passed = lc.evaluate_job_freshness(job, 600, now_epoch=clock.time())
            self.assertTrue(passed)

            # Simulate meaningful elapsed runtime before final output.
            clock.advance(120)

            final_jobs, drop_stats = lc.finalize_jobs_for_output([job], 600)

        self.assertEqual(final_jobs, [])
        self.assertEqual(drop_stats["expired"], 1)
        self.assertEqual(drop_stats["unknown"], 0)


# ============================================================
# TEST 7 - APPLICANT DROP IS NOT EXPIRATION
# ============================================================


class TestApplicantDropIsNotExpiration(unittest.TestCase):
    def setUp(self):
        self.session = fresh_rate_session()

    def test_applicant_evidence_drop_not_counted_as_expired(self):
        search_job = {
            "source": "linkedin",
            "job_id": "701",
            "title": "Software Engineer",
            "under_10_filter_requested": True,
            "under_10_filter_matched": True,
        }
        lc.record_posted_observation(
            search_job,
            "2 minutes ago",
            source="linkedin_search_card_relative_display",
        )

        detail_html = make_detail_html(
            "701", posted="2 minutes ago", applicants="14 applicants"
        )

        self.session.get = (
            lambda url, params=None, timeout=None: FakeResponse(200, detail_html)
        )

        with mock.patch("time.sleep", return_value=None):
            final_jobs, stats = lc.enrich_jobs_with_details(
                session=self.session,
                jobs=[search_job],
                posted_within_seconds=None,
                under_10=True,
                detail_delay=0,
                detail_html_cache={},
            )

        self.assertEqual(final_jobs, [])
        self.assertEqual(stats["under_10_contradictions_dropped"], 1)
        self.assertEqual(stats["freshness_expired_during_enrichment"], 0)
        self.assertEqual(stats["freshness_unknown_during_enrichment"], 0)


# ============================================================
# TEST 14 - INTERRUPT SAFETY
# ============================================================


class TestInterruptSafety(unittest.TestCase):
    def test_keyboard_interrupt_preserves_partial_results_and_resume(self):
        session = fresh_rate_session()
        good_pages = {0: [("801", "1 minutes ago", "A")]}

        def fake_fetch_search_page(session, keywords, location, start, **kwargs):
            if start == 0:
                html = make_page_html(good_pages[0])
                return lc.parse_search_results(
                    html,
                    requested_fresh_seconds=None,
                    under_10=False,
                    easy_apply=False,
                )
            raise KeyboardInterrupt()

        checkpoint_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "_test_checkpoint.partial.json",
        )
        if os.path.exists(checkpoint_path):
            os.remove(checkpoint_path)

        try:
            with mock.patch.object(
                lc, "fetch_search_page", side_effect=fake_fetch_search_page
            ), mock.patch("time.sleep", return_value=None):
                with self.assertRaises(KeyboardInterrupt):
                    lc.scan_search(
                        session=session,
                        keywords="engineer",
                        location="India",
                        requested_fresh_seconds=None,
                        server_window_seconds=None,
                        under_10=False,
                        easy_apply=False,
                        sort_mode="newest",
                        max_jobs=100,
                        max_pages=5,
                        page_delay=0,
                        detail_html_cache={},
                        checkpoint_file=checkpoint_path,
                    )

            self.assertTrue(os.path.exists(checkpoint_path))
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            self.assertEqual(payload["total_jobs"], 1)
            self.assertEqual(payload["stop_reason"], "interrupted")
            self.assertTrue(payload["resume"]["available"])
            self.assertEqual(payload["resume"]["start"], 10)
        finally:
            if os.path.exists(checkpoint_path):
                os.remove(checkpoint_path)


# ============================================================
# END-TO-END INTEGRATION (fetch_linkedin_jobs)
# ============================================================


class TestFetchLinkedinJobsIntegration(unittest.TestCase):
    def _patched_create_session(self, dispatcher):
        original_create_session = lc.create_session

        def fake_create_session(*args, **kwargs):
            session = original_create_session(*args, **kwargs)
            session.get = lambda url, params=None, timeout=None: dispatcher(
                url, params
            )
            return session

        return fake_create_session

    def test_end_to_end_success_no_details(self):
        good_pages = {0: [("901", "1 minutes ago", "Engineer")]}

        def dispatcher(url, params):
            start = params.get("start")
            if start in good_pages:
                return FakeResponse(200, make_page_html(good_pages[start]))
            return FakeResponse(200, "")

        with mock.patch.object(
            lc,
            "create_session",
            side_effect=self._patched_create_session(dispatcher),
        ), mock.patch("time.sleep", return_value=None):
            data = lc.fetch_linkedin_jobs(
                keywords="engineer",
                location="India",
                max_jobs=10,
                max_pages=3,
                fetch_details=False,
                start=0,
            )

        self.assertEqual(data["search_status"], "success")
        self.assertTrue(data["search_complete"])
        self.assertEqual(data["query"]["start"], 0)
        self.assertIn("scan", data)
        self.assertFalse(data["resume"]["available"])
        self.assertFalse(data["circuit_breaker"]["opened"])
        self.assertEqual(data["expired_before_output"], 0)
        self.assertEqual(data["total_jobs"], 1)

    def test_end_to_end_soft_limit_circuit_breaker_resume(self):
        good_pages = {0: [("911", "1 minutes ago", "Engineer")]}

        def dispatcher(url, params):
            start = params.get("start")
            if start in good_pages:
                return FakeResponse(200, make_page_html(good_pages[start]))
            if start == 10:
                return FakeResponse(200, "Please verify you are human (captcha).")
            return FakeResponse(200, "")

        checkpoint_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "_test_checkpoint_full.partial.json",
        )
        if os.path.exists(checkpoint_path):
            os.remove(checkpoint_path)

        try:
            with mock.patch.object(
                lc,
                "create_session",
                side_effect=self._patched_create_session(dispatcher),
            ), mock.patch("time.sleep", return_value=None):
                data = lc.fetch_linkedin_jobs(
                    keywords="engineer",
                    location="India",
                    max_jobs=100,
                    max_pages=5,
                    fetch_details=False,
                    checkpoint_file=checkpoint_path,
                )

            self.assertEqual(data["search_status"], "partial")
            self.assertFalse(data["search_complete"])
            self.assertEqual(
                data["search_stop_reason"], "soft_limit_circuit_breaker"
            )
            self.assertTrue(data["resume"]["available"])
            self.assertEqual(data["resume"]["start"], 10)
            self.assertEqual(data["total_jobs"], 1)

            self.assertTrue(os.path.exists(checkpoint_path))
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                checkpoint = json.load(f)
            self.assertEqual(checkpoint["resume"]["start"], 10)
        finally:
            if os.path.exists(checkpoint_path):
                os.remove(checkpoint_path)



# ============================================================
# ISSUE 1 - TERMINAL EMPTY FALSE POSITIVE
# ============================================================


class TestTerminalEmptyFalsePositive(unittest.TestCase):
    """Arbitrary HTML fragments with visible text must NOT become
    terminal_empty after a short page."""

    def test_visible_text_fragments_not_terminal_empty(self):
        fragments = [
            "<div>temporary backend issue</div>",
            "<div>maintenance</div>",
            "<p>oops</p>",
            "<div>Please try again later</div>",
            "<span>Service unavailable</span>",
            "<div>Something went wrong</div>",
        ]
        for frag in fragments:
            with self.assertRaises(
                lc.LinkedInUnexpectedResponse,
                msg=f"Fragment should NOT be terminal_empty: {frag}",
            ):
                lc.classify_search_response_html(
                    frag,
                    previous_page_card_count=9,
                )

    def test_empty_fragment_after_short_page_still_ok(self):
        """Trivially empty markup after a short page is still empty."""
        result = lc.classify_search_response_html(
            "", previous_page_card_count=9
        )
        self.assertEqual(result, "empty")

    def test_comment_only_fragment_after_short_page(self):
        """A comment-only fragment with no visible text after a short page
        is terminal_empty (benign end-of-results signal)."""
        result = lc.classify_search_response_html(
            "<!-- no more postings -->",
            previous_page_card_count=5,
        )
        self.assertEqual(result, "terminal_empty")

    def test_visible_text_fragment_after_full_page_is_unexpected(self):
        """A fragment with visible text after a FULL page is still unexpected."""
        with self.assertRaises(lc.LinkedInUnexpectedResponse):
            lc.classify_search_response_html(
                "<div>temporary backend issue</div>",
                previous_page_card_count=10,
            )


# ============================================================
# ISSUE 2 - FINAL ZERO CONCLUSIVE
# ============================================================


class TestFinalZeroConclusive(unittest.TestCase):
    """When all accepted jobs expire before final output, the top-level
    zero_conclusive must be True for a complete successful search."""

    def test_final_zero_conclusive_after_all_jobs_expire(self):
        good_pages = {0: [("1001", "1 minutes ago", "Engineer A")]}

        def dispatcher(url, params):
            start = params.get("start")
            if start in good_pages:
                return FakeResponse(
                    200, make_page_html(good_pages[start])
                )
            return FakeResponse(200, "")

        original_create_session = lc.create_session

        def fake_create_session(*args, **kwargs):
            session = original_create_session(*args, **kwargs)
            session.get = lambda url, params=None, timeout=None: dispatcher(
                url, params
            )
            return session

        def fake_finalize(jobs, posted_within_seconds):
            return [], {"expired": len(jobs), "unknown": 0}

        with mock.patch.object(
            lc, "create_session", side_effect=fake_create_session
        ):
            with mock.patch("time.sleep", return_value=None):
                with mock.patch.object(
                    lc,
                    "finalize_jobs_for_output",
                    side_effect=fake_finalize,
                ):
                    data = lc.fetch_linkedin_jobs(
                        keywords="engineer",
                        location="India",
                        max_jobs=10,
                        max_pages=3,
                        fetch_details=False,
                        posted_within="5m",
                        start=0,
                    )

        self.assertEqual(data["total_jobs"], 0)
        self.assertTrue(data["zero_conclusive"])
        self.assertEqual(data["search_status"], "success")
        self.assertTrue(data["search_complete"])
        # empty_result_is_conclusive remains the search-stage value
        # (which was False because search found jobs)
        self.assertFalse(data["empty_result_is_conclusive"])


# ============================================================
# ISSUE 3 - CHECKPOINT RATE/CIRCUIT TELEMETRY
# ============================================================


class TestCheckpointTelemetry(unittest.TestCase):
    """Checkpoint JSON must include circuit breaker and rate telemetry."""

    def test_checkpoint_contains_required_telemetry(self):
        good_pages = {0: [("1101", "1 minutes ago", "A")]}

        def dispatcher(url, params):
            start = params.get("start")
            if start in good_pages:
                return FakeResponse(
                    200, make_page_html(good_pages[start])
                )
            return FakeResponse(200, "")

        original_create_session = lc.create_session

        def fake_create_session(*args, **kwargs):
            session = original_create_session(*args, **kwargs)
            session.get = lambda url, params=None, timeout=None: dispatcher(
                url, params
            )
            return session

        checkpoint_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "_test_checkpoint_telemetry.partial.json",
        )
        if os.path.exists(checkpoint_path):
            os.remove(checkpoint_path)

        try:
            with mock.patch.object(
                lc, "create_session", side_effect=fake_create_session
            ):
                with mock.patch("time.sleep", return_value=None):
                    data = lc.fetch_linkedin_jobs(
                        keywords="engineer",
                        location="India",
                        max_jobs=10,
                        max_pages=3,
                        fetch_details=False,
                        checkpoint_file=checkpoint_path,
                    )

            self.assertTrue(os.path.exists(checkpoint_path))
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                checkpoint = json.load(f)

            # Required top-level keys
            self.assertIn("circuit_breaker", checkpoint)
            self.assertIn("rate_limit", checkpoint)
            self.assertIn("failed_start", checkpoint)
            self.assertIn("last_successful_start", checkpoint)
            self.assertIn("search_status", checkpoint)
            self.assertIn("search_complete", checkpoint)
            self.assertIn("stop_reason", checkpoint)
            self.assertIn("resume", checkpoint)

            # Circuit breaker structure
            cb = checkpoint["circuit_breaker"]
            self.assertIn("opened", cb)
            self.assertIn("reason", cb)
            self.assertIn("failed_start", cb)
            self.assertIn("failed_page", cb)

            # Rate limit structure
            rl = checkpoint["rate_limit"]
            self.assertIn("total_requests", rl)
            self.assertIn("successful_requests", rl)
            self.assertIn("rate_limit_events", rl)
            self.assertIn("soft_limit_events", rl)
            self.assertIn("soft_limit_recoveries", rl)
            self.assertIn("current_interval_seconds", rl)
        finally:
            if os.path.exists(checkpoint_path):
                os.remove(checkpoint_path)

    def test_checkpoint_circuit_breaker_on_no_details_run(self):
        """--no-details runs with a circuit breaker must also save
        rate/circuit telemetry."""
        good_pages = {0: [("1111", "1 minutes ago", "A")]}

        def dispatcher(url, params):
            start = params.get("start")
            if start in good_pages:
                return FakeResponse(
                    200, make_page_html(good_pages[start])
                )
            if start == 10:
                return FakeResponse(
                    200, "Please verify you are human (captcha)."
                )
            return FakeResponse(200, "")

        original_create_session = lc.create_session

        def fake_create_session(*args, **kwargs):
            session = original_create_session(*args, **kwargs)
            session.get = lambda url, params=None, timeout=None: dispatcher(
                url, params
            )
            return session

        checkpoint_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "_test_checkpoint_cb_no_detail.partial.json",
        )
        if os.path.exists(checkpoint_path):
            os.remove(checkpoint_path)

        try:
            with mock.patch.object(
                lc, "create_session", side_effect=fake_create_session
            ):
                with mock.patch("time.sleep", return_value=None):
                    data = lc.fetch_linkedin_jobs(
                        keywords="engineer",
                        location="India",
                        max_jobs=100,
                        max_pages=5,
                        fetch_details=False,
                        checkpoint_file=checkpoint_path,
                    )

            self.assertEqual(
                data["search_stop_reason"],
                "soft_limit_circuit_breaker",
            )

            with open(checkpoint_path, "r", encoding="utf-8") as f:
                checkpoint = json.load(f)

            self.assertIn("circuit_breaker", checkpoint)
            self.assertTrue(checkpoint["circuit_breaker"]["opened"])
            self.assertIn("rate_limit", checkpoint)
            self.assertIn(
                "soft_limit_events", checkpoint["rate_limit"]
            )
        finally:
            if os.path.exists(checkpoint_path):
                os.remove(checkpoint_path)


# ============================================================
# ISSUE 4 - FRESHNESS BOUNDARY (whole-second truncation)
# ============================================================


class TestFreshnessExactBoundary(unittest.TestCase):
    """Freshness uses deterministic whole-second truncation (never
    banker's rounding). For a 300-second window and '5 minutes ago':
      0 sec elapsed -> pass
      0.5 sec elapsed -> pass (int(0.5) = 0)
      1.0 sec elapsed -> fail (int(1.0) = 1)
    """

    def test_boundary_zero_half_one_seconds(self):
        clock = FakeClock(
            start_epoch=1_700_000_000.0,
            start_monotonic=1_000_000.0,
        )

        with mock.patch("time.time", clock.time), mock.patch(
            "time.monotonic", clock.monotonic
        ):
            job = {}
            lc.record_posted_observation(
                job,
                "5 minutes ago",
                source="linkedin_search_card_relative_display",
                observed_at_epoch=clock.time(),
            )

            # 0 seconds elapsed: 300 + 0 = 300 <= 300 -> pass
            passed = lc.evaluate_job_freshness(
                job, 300, now_epoch=clock.time()
            )
            self.assertTrue(passed)
            self.assertFalse(job["freshness_exact"])

            # 0.5 seconds elapsed: int(0.5) = 0, 300 + 0 = 300 <= 300 -> pass
            clock.advance(0.5)
            passed = lc.evaluate_job_freshness(
                job, 300, now_epoch=clock.time()
            )
            self.assertTrue(passed)

            # 1.0 seconds elapsed: int(1.0) = 1, 300 + 1 = 301 > 300 -> fail
            clock.advance(0.5)
            passed = lc.evaluate_job_freshness(
                job, 300, now_epoch=clock.time()
            )
            self.assertFalse(passed)

    def test_freshness_exact_always_false(self):
        clock = FakeClock()
        with mock.patch("time.time", clock.time), mock.patch(
            "time.monotonic", clock.monotonic
        ):
            job = {}
            lc.record_posted_observation(
                job,
                "1 minutes ago",
                source="linkedin_search_card_relative_display",
                observed_at_epoch=clock.time(),
            )
            lc.evaluate_job_freshness(
                job, 300, now_epoch=clock.time()
            )
            self.assertFalse(job["freshness_exact"])


# ============================================================
# ISSUE 5 - DETAIL RESPONSE SOFT-BLOCK HARDENING
# ============================================================


class TestDetailInterstitialHardening(unittest.TestCase):
    """Detail HTTP 200 interstitial/challenge bodies must not reset
    the adaptive rate controller or be cached as valid detail."""

    def test_detail_interstitial_not_marked_success(self):
        session = fresh_rate_session()

        def dispatcher(url, params):
            if "jobPosting" in url:
                return FakeResponse(
                    200,
                    "Please complete this security verification "
                    "challenge.",
                )
            return FakeResponse(200, "")

        session.get = lambda url, params=None, timeout=None: dispatcher(
            url, params
        )

        with mock.patch("time.sleep", return_value=None):
            with self.assertRaises(lc.LinkedInUnexpectedResponse):
                lc.fetch_detail_html(
                    session=session,
                    job_id="9999",
                    detail_html_cache={},
                )

        controller = lc._rate_controller(session)
        # HTTP 200 interstitial must NOT be counted as a success
        self.assertEqual(controller.successful_requests, 0)

    def test_detail_valid_response_marked_success(self):
        session = fresh_rate_session()
        valid_html = make_detail_html("9998", "2 minutes ago")

        def dispatcher(url, params):
            if "jobPosting" in url:
                return FakeResponse(200, valid_html)
            return FakeResponse(200, "")

        session.get = lambda url, params=None, timeout=None: dispatcher(
            url, params
        )

        with mock.patch("time.sleep", return_value=None):
            result = lc.fetch_detail_html(
                session=session,
                job_id="9998",
                detail_html_cache={},
            )

        self.assertIn("html", result)
        controller = lc._rate_controller(session)
        self.assertGreaterEqual(controller.successful_requests, 1)

    def test_detail_interstitial_not_cached(self):
        session = fresh_rate_session()
        cache = {}

        def dispatcher(url, params):
            if "jobPosting" in url:
                return FakeResponse(
                    200, "Unusual activity detected, please verify."
                )
            return FakeResponse(200, "")

        session.get = lambda url, params=None, timeout=None: dispatcher(
            url, params
        )

        with mock.patch("time.sleep", return_value=None):
            with self.assertRaises(lc.LinkedInUnexpectedResponse):
                lc.fetch_detail_html(
                    session=session,
                    job_id="8888",
                    detail_html_cache=cache,
                )

        self.assertNotIn("8888", cache)

if __name__ == "__main__":
    unittest.main(verbosity=2)
