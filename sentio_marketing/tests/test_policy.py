import unittest
from sentio_marketing.policy import (
    eligibility_reasons,
    normalize_record,
    source_key,
    approval_fingerprint,
    reply_action,
)


class PolicyTests(unittest.TestCase):
    def record(self):
        return dict(
            client_id="thuto-tutorials",
            account_id="a1",
            contact_id="c1",
            company="Example Ltd",
            email="buyer@example.test",
            email_type="named-work",
            role_status="supported",
            verification_status="valid",
            verification_provider="provider",
            verified_at="2026-11-13T00:00:00Z",
            verification_ref="receipt",
            review_status="draft",
            selected=True,
            source_url="https://example.test/contact",
            source_run="20261113T022621Z",
            approval_status="Approved",
            eligibility_evidence="Reviewed eligibility record ref 1",
            follow_up_status="Ready",
        )

    def test_unknown_identity_never_invented(self):
        r = normalize_record(
            dict(self.record(), name="", email_type="shared-work"), "thuto-tutorials"
        )
        self.assertEqual(r["person_name"], "")
        self.assertEqual(r["approval_status"], "Pending")
        self.assertEqual(r["review_status"], "hold")

    def test_cross_client_and_bad_ids_rejected(self):
        for patch in [
            {"client_id": "another-client"},
            {"account_id": "../x"},
            {"source_run": "2026/bad"},
            {"verification_status": "maybe"},
        ]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                normalize_record(dict(self.record(), **patch), "thuto-tutorials")

    def test_valid_requires_dated_receipt_and_source(self):
        for patch in [
            {"verified_at": ""},
            {"verification_ref": ""},
            {"source_url": "javascript:alert(1)"},
            {"verified_at": "tomorrow"},
        ]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                normalize_record(dict(self.record(), **patch), "thuto-tutorials")

    def test_blank_email_stays_unverified(self):
        r = normalize_record(
            dict(self.record(), email="", verification_status="unverified"),
            "thuto-tutorials",
        )
        self.assertEqual(r["verification_status"], "unverified")

    def test_only_reviewed_named_valid_record_can_pass(self):
        r = self.record()
        self.assertEqual(eligibility_reasons(r, "thuto-tutorials", True), [])
        for patch in [
            {"verification_status": "unknown"},
            {"email_type": "shared-work"},
            {"role_status": "conflicting"},
            {"review_status": "hold"},
            {"selected": False},
            {"approval_status": "Pending"},
            {"eligibility_evidence": ""},
            {"follow_up_status": "Replied"},
        ]:
            self.assertTrue(
                eligibility_reasons(dict(r, **patch), "thuto-tutorials", True), patch
            )

    def test_outreach_disabled_suppression_and_changed_record_block(self):
        r = self.record()
        self.assertTrue(eligibility_reasons(r, "thuto-tutorials", False))
        self.assertTrue(
            eligibility_reasons(r, "thuto-tutorials", True, suppressed=True)
        )
        fingerprint = approval_fingerprint(r)
        self.assertNotEqual(
            fingerprint, approval_fingerprint(dict(r, email="new@example.test"))
        )

    def test_source_identity_includes_account_and_contact(self):
        self.assertNotEqual(
            source_key(self.record()), source_key(dict(self.record(), contact_id="c2"))
        )

    def test_opt_out_does_not_match_quoted_footer(self):
        self.assertEqual(
            reply_action("Thanks, please send the details.\n\n> Reply stop to opt out"),
            "Replied",
        )
        self.assertEqual(reply_action("STOP"), "Opted out")
        self.assertEqual(
            reply_action("<p>Thanks</p><blockquote>stop</blockquote>"), "Replied"
        )


if __name__ == "__main__":
    unittest.main()
