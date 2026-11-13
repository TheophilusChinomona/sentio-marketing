import importlib
import sys
import types
import unittest
from unittest.mock import patch
from sentio_marketing.policy import approval_fingerprint, message_fingerprint


class Doc(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__

    def as_dict(self):
        return dict(self)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        def throws(message, *args):
            raise ValueError(message)

        self.fake = types.ModuleType("frappe")
        self.fake.throw = throws
        self.fake.PermissionError = PermissionError
        self.settings = Doc(
            client_id="thuto-tutorials",
            outreach_enabled=1,
            sender_domain="example.test",
        )
        self.p = Doc(
            client_id="thuto-tutorials",
            account_id="a1",
            contact_id="c1",
            email="buyer@customer.test",
            email_type="named-work",
            role_status="supported",
            verification_status="valid",
            verification_provider="provider",
            verified_at="2026-11-13T00:00:00Z",
            verification_ref="receipt",
            review_status="draft",
            selected=True,
            source_url="https://customer.test",
            source_run="20261113T022621Z",
            approval_status="Approved",
            eligibility_evidence="actual review proof",
            follow_up_status="Ready",
        )
        self.p.approved_fingerprint = approval_fingerprint(self.p)
        self.c = Doc(
            reference_doctype="CRM Lead",
            reference_name="L1",
            sender="sales@example.test",
            recipients=self.p.email,
            cc="",
            bcc="",
            subject="Study support",
            content="<p>Would an overview help?</p>",
            in_reply_to="",
        )
        self.suppressed = False
        self.reviewed = True

        def exists(dt, filters):
            return self.suppressed if dt == "Sentio Suppression" else self.reviewed

        self.fake.db = types.SimpleNamespace(exists=exists)
        self.fake.get_single = lambda dt: self.settings
        self.fake.get_doc = lambda dt, name: (
            Doc(sentio_prospect="P1")
            if dt == "CRM Lead"
            else self.p
            if dt == "Sentio Prospect"
            else Doc(sent_or_received="Received", sender=self.p.email)
        )
        self.modules = patch.dict(sys.modules, frappe=self.fake)
        self.modules.start()
        sys.modules.pop("sentio_marketing.events", None)
        self.events = importlib.import_module("sentio_marketing.events")

    def tearDown(self):
        self.modules.stop()
        sys.modules.pop("sentio_marketing.events", None)

    def test_reviewed_message_passes(self):
        self.events.check_outgoing(self.c)

    def test_suppression_added_after_review_blocks(self):
        self.suppressed = True
        with self.assertRaisesRegex(ValueError, "suppressed"):
            self.events.check_outgoing(self.c)

    def test_changed_email_invalidates_review_fingerprint(self):
        self.p.email = "other@customer.test"
        self.c.recipients = self.p.email
        with self.assertRaisesRegex(ValueError, "changed"):
            self.events.check_outgoing(self.c)

    def test_unreviewed_copy_and_wrong_sender_block(self):
        self.reviewed = False
        with self.assertRaisesRegex(ValueError, "exact subject"):
            self.events.check_outgoing(self.c)
        self.reviewed = True
        self.c.sender = "sales@another.test"
        with self.assertRaisesRegex(ValueError, "sender domain"):
            self.events.check_outgoing(self.c)

    def test_reply_stops_followups_but_explicit_response_can_pass(self):
        self.p.follow_up_status = "Replied"
        with self.assertRaisesRegex(ValueError, "stopped"):
            self.events.check_outgoing(self.c)
        self.c.in_reply_to = "incoming-1"
        self.events.check_outgoing(self.c)

    def test_cc_bcc_are_not_implicitly_approved(self):
        self.c.cc = "other@customer.test"
        with self.assertRaisesRegex(ValueError, "CC/BCC"):
            self.events.check_outgoing(self.c)

    def test_message_hash_covers_links_and_quoted_content(self):
        a = message_fingerprint("hello", '<a href="https://one.test">Details</a>')
        self.assertNotEqual(
            a, message_fingerprint("hello", '<a href="https://two.test">Details</a>')
        )
        self.assertNotEqual(
            message_fingerprint("hello", "A<blockquote>B</blockquote>"),
            message_fingerprint("hello", "A<blockquote>C</blockquote>"),
        )

    def test_queue_mixin_checks_before_delivery(self):
        sys.modules.pop("sentio_marketing.outbound", None)
        m = importlib.import_module("sentio_marketing.outbound")

        class Base:
            def send(self):
                raise AssertionError("SMTP delivery must not be reached")

        class Queue(m.ReviewedQueueMixin, Base):
            pass

        with patch.object(m, "guard_queue", side_effect=ValueError("suppressed")):
            with self.assertRaisesRegex(ValueError, "suppressed"):
                Queue().send()


if __name__ == "__main__":
    unittest.main()
