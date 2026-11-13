"""Run on a disposable Frappe/CRM test site, never on a customer site."""

import frappe
from frappe.tests.utils import FrappeTestCase
from sentio_marketing.api import import_research, review_prospect
from sentio_marketing.policy import source_key


class TestSentioSiteIntegration(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        s = frappe.get_single("Sentio Marketing Settings")
        s.client_id = "test-client"
        s.outreach_enabled = 0
        s.save()
        self.record = dict(
            client_id="test-client",
            account_id="test-account",
            contact_id="test-contact",
            company="_Test Sentio Organisation",
            person_name="Example Buyer",
            email="buyer@example.test",
            phone="",
            website="https://example.test",
            email_type="named-work",
            role_status="supported",
            verification_status="valid",
            verification_provider="fixture",
            verified_at="2026-11-13T00:00:00Z",
            verification_ref="fixture-ref",
            review_status="draft",
            source_url="https://example.test/contact",
            source_run="20261113T022621Z",
            selected=True,
            notes="",
            evidence=[],
        )

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def test_import_is_site_scoped_and_never_approves(self):
        with self.assertRaises(frappe.PermissionError):
            import_research("another-client", [self.record], False)
        dry = import_research("test-client", [self.record], True)
        self.assertFalse(dry["write_performed"])
        self.assertFalse(frappe.db.exists("Sentio Prospect", source_key(self.record)))
        import_research("test-client", [self.record], False)
        doc = frappe.get_doc("Sentio Prospect", source_key(self.record))
        self.assertEqual(doc.approval_status, "Pending")
        self.assertEqual(doc.verification_ref, "fixture-ref")

    def test_approval_resets_when_reviewed_email_changes(self):
        import_research("test-client", [self.record], False)
        name = source_key(self.record)
        review_prospect(name, "actual test eligibility proof", True)
        doc = frappe.get_doc("Sentio Prospect", name)
        self.assertEqual(doc.approval_status, "Approved")
        doc.email = "changed@example.test"
        doc.save()
        self.assertEqual(doc.approval_status, "Pending")

    def test_shared_mailbox_is_held(self):
        r = dict(self.record, email_type="shared-work", person_name="")
        import_research("test-client", [r], False)
        doc = frappe.get_doc("Sentio Prospect", source_key(r))
        self.assertEqual(doc.review_status, "hold")
        with self.assertRaises(frappe.ValidationError):
            review_prospect(doc.name, "test proof", True)
