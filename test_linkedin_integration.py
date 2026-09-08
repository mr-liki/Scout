"""
test_linkedin_integration.py - Backend integration tests for LinkedIn service layer.

Tests the linkedin_connector_tracker.py service layer without hitting live LinkedIn.
Mocks the connector boundary for all tests.
"""

import json
import os
import sys
import unittest
from unittest import mock

# Ensure backend/web is importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "web"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trackers.linkedin_connector_tracker import (
    normalize_linkedin_job,
    normalize_search_response,
    search_linkedin,
    fetch_detail,
    _generate_job_id,
)
import linkedin_connector as lc


# ============================================================
# TEST FIXTURES
# ============================================================

SAMPLE_CONNECTOR_JOB = {
    "source": "linkedin",
    "job_id": "12345678",
    "title": "Software Engineer",
    "company": "Acme Corp",
    "location": "Remote",
    "posted": "5 minutes ago",
    "posted_date": "2026-09-01",
    "posted_age_minutes": 5,
    "freshness_filter_passed": True,
    "freshness_exact": False,
    "freshness_basis": "linkedin_relative_display_plus_elapsed_time",
    "freshness_observed_at": "2026-09-07T10:00:00+00:00",
    "freshness_observed_age_seconds": 300,
    "freshness_age_estimate_seconds_at_check": 300,
    "linkedin_badge": None,
    "under_10_filter_requested": True,
    "under_10_filter_matched": True,
    "under_10_filter_source": "linkedin_f_EA_EARLY_APPLICANT",
    "under_10_applicants": None,
    "under_10_exact_count_verified": False,
    "easy_apply_filter_requested": False,
    "easy_apply_filter_matched": None,
    "job_url": "https://www.linkedin.com/jobs/view/software-engineer-12345678",
    "company_url": "https://www.linkedin.com/company/acme",
    "company_logo": None,
    "linkedin_row": 0,
}

SAMPLE_CONNECTOR_RESULT_SUCCESS = {
    "source": "linkedin",
    "search_status": "success",
    "search_complete": True,
    "stop_reason": "end_of_results",
    "zero_conclusive": False,
    "total_jobs": 1,
    "search_results_found": 1,
    "expired_before_output": 0,
    "jobs": [SAMPLE_CONNECTOR_JOB],
    "resume": {"available": False, "start": None, "linkedin_page": None, "reason": None},
    "circuit_breaker": {"opened": False, "reason": None, "failed_start": None, "failed_page": None},
    "linkedin_filters": {"sortBy": "DD", "f_TPR": "r3600"},
    "freshness_policy": {"mode": "relative_display_plus_elapsed_time", "exact": False},
    "under_10_policy": {"filter_mapping": "f_EA=EARLY_APPLICANT"},
    "rate_limit_policy": {"rate_limit_events": 0, "soft_limit_events": 0, "soft_limit_recoveries": 0},
    "query": {"keywords": "Software Engineer", "location": "India"},
}

SAMPLE_CONNECTOR_RESULT_PARTIAL = {
    "source": "linkedin",
    "search_status": "partial",
    "search_complete": False,
    "stop_reason": "soft_limit_circuit_breaker",
    "zero_conclusive": False,
    "total_jobs": 18,
    "search_results_found": 18,
    "expired_before_output": 0,
    "jobs": [SAMPLE_CONNECTOR_JOB] * 18,
    "resume": {"available": True, "start": 140, "linkedin_page": 15, "reason": "soft_limit_circuit_breaker"},
    "circuit_breaker": {"opened": True, "reason": "soft_limit", "failed_start": 140, "failed_page": 15},
    "linkedin_filters": {"sortBy": "DD"},
    "freshness_policy": None,
    "under_10_policy": None,
    "rate_limit_policy": {"rate_limit_events": 0, "soft_limit_events": 3, "soft_limit_recoveries": 0},
}


# ============================================================
# TEST 1: Parameter mapping
# ============================================================

class TestParameterMapping(unittest.TestCase):
    """TEST 1: Valid LinkedIn search request maps API parameters correctly."""

    @mock.patch("trackers.linkedin_connector_tracker.lc.fetch_linkedin_jobs")
    def test_full_parameter_mapping(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_CONNECTOR_RESULT_SUCCESS.copy()

        search_linkedin(
            keywords="Software Engineer",
            location="India",
            posted_within="10m",
            under_10=True,
            easy_apply=False,
            sort_mode="newest",
            max_jobs=100,
            max_pages=20,
            start=0,
        )

        mock_fetch.assert_called_once()
        call_kwargs = mock_fetch.call_args[1]

        self.assertEqual(call_kwargs["keywords"], "Software Engineer")
        self.assertEqual(call_kwargs["location"], "India")
        self.assertEqual(call_kwargs["posted_within"], "10m")
        self.assertTrue(call_kwargs["under_10"])
        self.assertFalse(call_kwargs["easy_apply"])
        self.assertEqual(call_kwargs["sort_mode"], "newest")
        self.assertEqual(call_kwargs["max_jobs"], 100)
        self.assertFalse(call_kwargs["fetch_details"])  # NEVER fetch details in feed


# ============================================================
# TEST 2: Successful connector response
# ============================================================

class TestSuccessfulResponse(unittest.TestCase):
    """TEST 2: Successful connector response returns HTTP 200 with jobs."""

    @mock.patch("trackers.linkedin_connector_tracker.lc.fetch_linkedin_jobs")
    def test_success_returns_jobs(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_CONNECTOR_RESULT_SUCCESS.copy()

        result = search_linkedin(keywords="Python", location="India")

        self.assertEqual(result["search_status"], "success")
        self.assertTrue(result["search_complete"])
        self.assertEqual(result["total_jobs"], 1)
        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["jobs"][0]["source"], "LinkedIn")
        self.assertEqual(result["jobs"][0]["title"], "Software Engineer")


# ============================================================
# TEST 3: Partial response with jobs
# ============================================================

class TestPartialResponse(unittest.TestCase):
    """TEST 3: Partial connector response still returns valid jobs."""

    @mock.patch("trackers.linkedin_connector_tracker.lc.fetch_linkedin_jobs")
    def test_partial_returns_jobs(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_CONNECTOR_RESULT_PARTIAL.copy()

        result = search_linkedin(keywords="Engineer", location="India")

        self.assertEqual(result["search_status"], "partial")
        self.assertFalse(result["search_complete"])
        self.assertEqual(len(result["jobs"]), 18)
        self.assertTrue(result["resume"]["available"])
        self.assertEqual(result["resume"]["start"], 140)


# ============================================================
# TEST 4: Circuit breaker resume
# ============================================================

class TestCircuitBreakerResume(unittest.TestCase):
    """TEST 4: Circuit breaker preserves exact resume.start."""

    @mock.patch("trackers.linkedin_connector_tracker.lc.fetch_linkedin_jobs")
    def test_circuit_breaker_resume_start(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_CONNECTOR_RESULT_PARTIAL.copy()

        result = search_linkedin(keywords="Engineer", location="India")

        self.assertTrue(result["circuit_breaker"]["opened"])
        self.assertEqual(result["resume"]["start"], 140)
        self.assertEqual(result["stop_reason"], "soft_limit_circuit_breaker")


# ============================================================
# TEST 5: Failed request
# ============================================================

class TestFailedRequest(unittest.TestCase):
    """TEST 5: Failed LinkedIn search returns machine-readable failure."""

    @mock.patch("trackers.linkedin_connector_tracker.lc.fetch_linkedin_jobs")
    def test_failed_search(self, mock_fetch):
        mock_fetch.side_effect = lc.LinkedInRateLimited("Rate limited")

        result = search_linkedin(keywords="Engineer", location="India")

        self.assertEqual(result["search_status"], "failed")
        self.assertFalse(result["search_complete"])
        self.assertEqual(result["total_jobs"], 0)
        self.assertEqual(len(result["jobs"]), 0)
        self.assertIn("error", result)


# ============================================================
# TEST 6: Validation
# ============================================================

class TestValidation(unittest.TestCase):
    """TEST 6: Request validation rejects invalid parameters."""

    def test_missing_keywords(self):
        result = search_linkedin(keywords="", location="India")
        self.assertEqual(result["search_status"], "failed")
        self.assertIn("error", result)

    def test_invalid_start_negative(self):
        result = search_linkedin(keywords="Python", start=-10)
        self.assertEqual(result["search_status"], "failed")
        self.assertIn("error", result)

    def test_invalid_start_not_divisible_by_10(self):
        result = search_linkedin(keywords="Python", start=17)
        self.assertEqual(result["search_status"], "failed")
        self.assertIn("error", result)

    def test_valid_start(self):
        with mock.patch("trackers.linkedin_connector_tracker.lc.fetch_linkedin_jobs") as mock_fetch:
            mock_fetch.return_value = SAMPLE_CONNECTOR_RESULT_SUCCESS.copy()
            result = search_linkedin(keywords="Python", start=140)
            # Should not fail validation
            self.assertNotEqual(result.get("search_status"), "failed")

    def test_invalid_sort_mode_falls_back_to_newest(self):
        with mock.patch("trackers.linkedin_connector_tracker.lc.fetch_linkedin_jobs") as mock_fetch:
            mock_fetch.return_value = SAMPLE_CONNECTOR_RESULT_SUCCESS.copy()
            search_linkedin(keywords="Python", sort_mode="invalid")
            call_kwargs = mock_fetch.call_args[1]
            self.assertEqual(call_kwargs["sort_mode"], "newest")

    def test_limit_clamped_to_max(self):
        with mock.patch("trackers.linkedin_connector_tracker.lc.fetch_linkedin_jobs") as mock_fetch:
            mock_fetch.return_value = SAMPLE_CONNECTOR_RESULT_SUCCESS.copy()
            search_linkedin(keywords="Python", max_jobs=9999)
            call_kwargs = mock_fetch.call_args[1]
            self.assertEqual(call_kwargs["max_jobs"], 500)  # MAX_MAX_JOBS


# ============================================================
# TEST 7: Job ID dedup
# ============================================================

class TestJobDedup(unittest.TestCase):
    """TEST 7: Same provider_job_id produces same canonical ID."""

    def test_same_provider_id_same_canonical_id(self):
        job1 = {"job_id": "12345"}
        job2 = {"job_id": "12345"}
        self.assertEqual(_generate_job_id(job1), _generate_job_id(job2))

    def test_different_provider_id_different_canonical_id(self):
        job1 = {"job_id": "12345"}
        job2 = {"job_id": "67890"}
        self.assertNotEqual(_generate_job_id(job1), _generate_job_id(job2))

    def test_linkedin_prefix_in_id(self):
        job = {"job_id": "12345"}
        self.assertTrue(_generate_job_id(job).startswith("linkedin:"))


# ============================================================
# TEST 8: Different providers with same numeric ID
# ============================================================

class TestCrossProviderDedup(unittest.TestCase):
    """TEST 8: Different providers with same numeric ID are NOT deduplicated."""

    def test_linkedin_and_other_source_not_deduped(self):
        linkedin_job = normalize_linkedin_job(SAMPLE_CONNECTOR_JOB)
        other_job = {
            "id": "12345678",  # Same numeric ID but from Indeed
            "source": "Indeed",
            "title": "Different Job",
        }
        self.assertNotEqual(linkedin_job["id"], other_job["id"])
        self.assertTrue(linkedin_job["id"].startswith("linkedin:"))


# ============================================================
# TEST 9: List endpoint uses fetch_details=False
# ============================================================

class TestListEndpointNoDetails(unittest.TestCase):
    """TEST 9: List endpoint never fetches details eagerly."""

    @mock.patch("trackers.linkedin_connector_tracker.lc.fetch_linkedin_jobs")
    def test_fetch_details_always_false(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_CONNECTOR_RESULT_SUCCESS.copy()

        search_linkedin(keywords="Python", location="India")

        call_kwargs = mock_fetch.call_args[1]
        self.assertFalse(call_kwargs["fetch_details"])


# ============================================================
# TEST 10: Detail endpoint invokes detail fetch only for requested job
# ============================================================

class TestDetailEndpoint(unittest.TestCase):
    """TEST 10: Detail endpoint fetches only the requested job."""

    @mock.patch("trackers.linkedin_connector_tracker.lc.create_session")
    @mock.patch("trackers.linkedin_connector_tracker.lc.fetch_detail_html")
    @mock.patch("trackers.linkedin_connector_tracker.lc.parse_job_detail")
    def test_detail_fetches_only_requested_job(self, mock_parse, mock_fetch_html, mock_session):
        mock_session.return_value = mock.MagicMock()
        mock_fetch_html.return_value = {
            "html": "<html></html>",
            "fetched_at_epoch": 1000000,
        }
        mock_parse.return_value = {
            "job_id": "12345",
            "title": "Software Engineer",
            "company": "Acme",
        }

        result = fetch_detail("12345")

        self.assertEqual(result["provider_job_id"], "12345")
        self.assertEqual(result["upstream_status"], "success")
        mock_fetch_html.assert_called_once()
        # Verify it was called with the correct job_id
        call_kwargs = mock_fetch_html.call_args[1]
        self.assertEqual(call_kwargs["job_id"], "12345")


# ============================================================
# TEST 11: Invalid detail ID
# ============================================================

class TestInvalidDetailId(unittest.TestCase):
    """TEST 11: Invalid detail ID returns validation failure without external request."""

    def test_non_numeric_id_rejected(self):
        result = fetch_detail("abc")
        self.assertEqual(result["upstream_status"], "invalid_id")
        self.assertIn("error", result)

    def test_empty_id_rejected(self):
        result = fetch_detail("")
        self.assertEqual(result["upstream_status"], "invalid_id")

    def test_none_id_rejected(self):
        result = fetch_detail(None)
        self.assertEqual(result["upstream_status"], "invalid_id")


# ============================================================
# TEST 12: Detail upstream failure
# ============================================================

class TestDetailUpstreamFailure(unittest.TestCase):
    """TEST 12: Detail upstream failure returns clean error, no stack trace."""

    @mock.patch("trackers.linkedin_connector_tracker.lc.create_session")
    @mock.patch("trackers.linkedin_connector_tracker.lc.fetch_detail_html")
    def test_rate_limited_detail(self, mock_fetch, mock_session):
        mock_session.return_value = mock.MagicMock()
        mock_fetch.side_effect = lc.LinkedInRateLimited("Rate limited")

        result = fetch_detail("12345")

        self.assertEqual(result["upstream_status"], "rate_limited")
        self.assertIn("error", result)
        # Must NOT expose internal stack traces
        self.assertNotIn("Traceback", result.get("error", ""))

    @mock.patch("trackers.linkedin_connector_tracker.lc.create_session")
    @mock.patch("trackers.linkedin_connector_tracker.lc.fetch_detail_html")
    def test_generic_error_detail(self, mock_fetch, mock_session):
        mock_session.return_value = mock.MagicMock()
        mock_fetch.side_effect = lc.LinkedInError("Some error")

        result = fetch_detail("12345")

        self.assertEqual(result["upstream_status"], "unavailable")
        self.assertIn("error", result)


# ============================================================
# TEST 13: Freshness metadata survives normalization
# ============================================================

class TestFreshnessMetadataNormalization(unittest.TestCase):
    """TEST 13: Freshness metadata survives normalization."""

    def test_freshness_fields_preserved(self):
        normalized = normalize_linkedin_job(SAMPLE_CONNECTOR_JOB)
        meta = normalized["provider_metadata"]

        self.assertTrue(meta["freshness_filter_passed"])
        self.assertFalse(meta["freshness_exact"])
        self.assertEqual(meta["freshness_basis"], "linkedin_relative_display_plus_elapsed_time")
        self.assertIsNotNone(meta["freshness_observed_at"])
        self.assertEqual(meta["freshness_observed_age_seconds"], 300)


# ============================================================
# TEST 14: Under-10 filter metadata NOT converted to exact proof
# ============================================================

class TestUnder10MetadataNormalization(unittest.TestCase):
    """TEST 14: Under-10 filter-match metadata is NOT converted into exact applicant proof."""

    def test_under10_not_false_applicant_proof(self):
        normalized = normalize_linkedin_job(SAMPLE_CONNECTOR_JOB)
        meta = normalized["provider_metadata"]

        # Filter match is True (LinkedIn matched the filter)
        self.assertTrue(meta["under_10_filter_matched"])
        # But this is NOT an exact applicant count verification
        self.assertFalse(meta["under_10_exact_count_verified"])
        # Applicants count is None (not independently verified)
        self.assertIsNone(meta["under_10_applicants"])

    def test_early_applicant_flag_preserved(self):
        normalized = normalize_linkedin_job(SAMPLE_CONNECTOR_JOB)
        self.assertTrue(normalized["early_applicant"])


# ============================================================
# TEST 15: Async safety (sync framework)
# ============================================================

class TestAsyncSafety(unittest.TestCase):
    """TEST 15: Verify the connector is callable from sync framework."""

    def test_search_linkedin_is_sync(self):
        """The backend is sync (stdlib HTTP server), verify no async issues."""
        import inspect
        self.assertFalse(inspect.iscoroutinefunction(search_linkedin))
        self.assertFalse(inspect.iscoroutinefunction(fetch_detail))


# ============================================================
# TEST 16: Provider isolation
# ============================================================

class TestProviderIsolation(unittest.TestCase):
    """TEST 16: LinkedIn failure does not break other providers."""

    def test_linkedin_exception_captured(self):
        """search_linkedin catches all exceptions and returns structured error."""
        with mock.patch("trackers.linkedin_connector_tracker.lc.fetch_linkedin_jobs") as mock_fetch:
            mock_fetch.side_effect = Exception("Unexpected LinkedIn failure")

            result = search_linkedin(keywords="Python", location="India")

            self.assertEqual(result["search_status"], "failed")
            self.assertEqual(result["total_jobs"], 0)
            self.assertNotIn("Traceback", result.get("error", ""))


# ============================================================
# TEST 17: Cache behavior (in-memory)
# ============================================================

class TestCacheBehavior(unittest.TestCase):
    """TEST 17: Partial response preserves resume metadata (if caching were added)."""

    @mock.patch("trackers.linkedin_connector_tracker.lc.fetch_linkedin_jobs")
    def test_partial_preserves_resume_in_response(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_CONNECTOR_RESULT_PARTIAL.copy()

        result = search_linkedin(keywords="Engineer", location="India")

        self.assertTrue(result["resume"]["available"])
        self.assertEqual(result["resume"]["start"], 140)
        self.assertEqual(result["resume"]["reason"], "soft_limit_circuit_breaker")


# ============================================================
# TEST 18: Repeated detail request
# ============================================================

class TestRepeatedDetailRequest(unittest.TestCase):
    """TEST 18: Repeated detail requests work (caching would help)."""

    @mock.patch("trackers.linkedin_connector_tracker.lc.create_session")
    @mock.patch("trackers.linkedin_connector_tracker.lc.fetch_detail_html")
    @mock.patch("trackers.linkedin_connector_tracker.lc.parse_job_detail")
    def test_repeated_detail_calls(self, mock_parse, mock_fetch_html, mock_session):
        mock_session.return_value = mock.MagicMock()
        mock_fetch_html.return_value = {
            "html": "<html></html>",
            "fetched_at_epoch": 1000000,
        }
        mock_parse.return_value = {"job_id": "12345", "title": "Engineer"}

        # Call twice
        result1 = fetch_detail("12345")
        result2 = fetch_detail("12345")

        self.assertEqual(result1["provider_job_id"], "12345")
        self.assertEqual(result2["provider_job_id"], "12345")
        # Both should succeed
        self.assertEqual(result1["upstream_status"], "success")
        self.assertEqual(result2["upstream_status"], "success")


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
