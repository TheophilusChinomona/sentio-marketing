"""Guard ordinary CRM messages and keep source evidence/review state distinct."""

import frappe
from sentio_marketing.policy import (
    CLIENT,
    EMAIL,
    APPROVAL_FIELDS,
    approval_fingerprint,
    eligibility_reasons,
    normalize_record,
    mailbox,
    reply_action,
    message_fingerprint,
    _url,
)


def _manager():
    return bool(
        set(frappe.get_roles()) & {"System Manager", "Sentio Marketing Manager"}
    )


def validate_settings(doc, method=None):
    if not CLIENT.fullmatch(doc.client_id or ""):
        frappe.throw("Choose an explicit client ID, such as thuto-tutorials")
    old = doc.get_doc_before_save()
    if old and old.client_id != doc.client_id and frappe.db.count("Sentio Prospect"):
        frappe.throw("An imported site cannot be reassigned to a different client")
    if doc.outreach_enabled and (
        not doc.sender_domain
        or "." not in doc.sender_domain
        or "@" in doc.sender_domain
    ):
        frappe.throw("Configure the authorised sender domain before enabling outreach")


def validate_prospect(doc, method=None):
    s = frappe.get_single("Sentio Marketing Settings")
    try:
        normalized = normalize_record(doc.as_dict(), s.client_id)
        if doc.source_key != normalized["source_key"]:
            raise ValueError("Source identity does not match its account/contact IDs")
        doc.review_status = normalized["review_status"]
    except ValueError as e:
        frappe.throw(str(e))
    old = doc.get_doc_before_save()
    if old and any(
        doc.get(k) != old.get(k)
        for k in ["client_id", "account_id", "contact_id", "source_key"]
    ):
        frappe.throw("Source identity is immutable")
    if not _manager() and any(
        doc.get(k) != (old.get(k) if old else None)
        for k in [
            "approval_status",
            "eligibility_evidence",
            "approved_fingerprint",
            "reviewed_by",
            "reviewed_at",
        ]
    ):
        frappe.throw(
            "Only a marketing manager can approve outreach", frappe.PermissionError
        )
    if (
        old
        and old.approval_status == "Approved"
        and any(doc.get(k) != old.get(k) for k in APPROVAL_FIELDS)
    ):
        doc.approval_status = "Pending"
        doc.approved_fingerprint = ""
        doc.reviewed_by = None
        doc.reviewed_at = None
    if doc.approval_status == "Approved":
        if not _manager() and (not old or old.approval_status != "Approved"):
            frappe.throw("Marketing manager review required", frappe.PermissionError)
        blocked = frappe.db.exists("Sentio Suppression", {"email": doc.email.lower()})
        reasons = eligibility_reasons(
            doc.as_dict(), s.client_id, True, suppressed=bool(blocked)
        )
        if reasons:
            frappe.throw("; ".join(reasons))
        doc.approved_fingerprint = approval_fingerprint(doc.as_dict())
        if not old or old.approval_status != "Approved":
            doc.reviewed_by = frappe.session.user
            doc.reviewed_at = frappe.utils.now_datetime()


def validate_evidence(doc, method=None):
    if not doc.is_new():
        frappe.throw("Evidence observations are immutable; append a new observation")
    try:
        _url(doc.source_url)
    except ValueError as e:
        frappe.throw(str(e))


def validate_suppression(doc, method=None):
    old = doc.get_doc_before_save()
    if old and old.email != doc.email:
        frappe.throw(
            "A suppression address is immutable; keep the original suppression record"
        )
    doc.email = (doc.email or "").lower().strip()
    if not EMAIL.fullmatch(doc.email):
        frappe.throw("Invalid suppression email")
    if not str(doc.evidence or "").strip():
        frappe.throw("Suppression evidence is required")


def _prospect_for_communication(doc):
    if doc.reference_doctype not in {"CRM Lead", "CRM Deal"} or not doc.reference_name:
        return None
    ref = frappe.get_doc(doc.reference_doctype, doc.reference_name)
    name = ref.get("sentio_prospect")
    if not name:
        frappe.throw(
            "Link this CRM record to a reviewed research prospect before outreach"
        )
    prospect = frappe.get_doc("Sentio Prospect", name)
    if ref.get("email") and ref.email.lower() != prospect.email.lower():
        frappe.throw("CRM contact email differs from its reviewed research record")
    return prospect


def check_outgoing(doc):
    p = _prospect_for_communication(doc)
    if p is None:
        return
    s = frappe.get_single("Sentio Marketing Settings")
    sender = mailbox(doc.sender)
    if not sender or sender.rsplit("@", 1)[-1] != s.sender_domain:
        frappe.throw("Choose this client’s authorised sender domain")
    # One reviewed recipient only; CC/BCC require a separate reviewed workflow.
    from email.utils import getaddresses

    addresses = [a.lower() for _, a in getaddresses([doc.recipients or ""]) if a]
    if addresses != [p.email.lower()] or doc.cc or doc.bcc:
        frappe.throw(
            "Use one reviewed prospect recipient; CC/BCC are not approved by this workflow"
        )
    blocked = frappe.db.exists("Sentio Suppression", {"email": p.email.lower()})
    is_reply = False
    if doc.get("in_reply_to"):
        reply = frappe.get_doc("Communication", doc.in_reply_to)
        is_reply = (
            reply.sent_or_received == "Received"
            and mailbox(reply.sender) == p.email.lower()
        )
    reasons = eligibility_reasons(
        p.as_dict(),
        s.client_id,
        bool(s.outreach_enabled),
        suppressed=bool(blocked),
        is_reply=is_reply,
    )
    content_hash = message_fingerprint(doc.subject, doc.content)
    if not frappe.db.exists(
        "Sentio Email Draft",
        {
            "prospect": p.name,
            "draft_status": "Reviewed",
            "content_fingerprint": content_hash,
        },
    ):
        reasons.append("Review this exact subject and message before sending")
    if p.approved_fingerprint != approval_fingerprint(p.as_dict()):
        reasons.append("Research changed after approval")
    if reasons:
        frappe.throw("; ".join(reasons))


def guard_communication(doc, method=None):
    if doc.communication_medium == "Email" and doc.sent_or_received == "Sent":
        check_outgoing(doc)


def guard_queue(doc, method=None):
    if doc.communication:
        c = frappe.get_doc("Communication", doc.communication)
        if c.sent_or_received == "Sent" and c.communication_medium == "Email":
            if c.reference_doctype in {"CRM Lead", "CRM Deal"}:
                from email.utils import getaddresses

                expected = {
                    a.lower() for _, a in getaddresses([c.recipients or ""]) if a
                }
                actual = {str(r.recipient).lower() for r in (doc.recipients or [])}
                if actual != expected or mailbox(doc.sender) != mailbox(c.sender):
                    frappe.throw(
                        "Queued sender or recipients differ from the reviewed CRM message"
                    )
            check_outgoing(c)


def record_reply(doc, method=None):
    if doc.communication_medium != "Email" or doc.sent_or_received != "Received":
        return
    address = mailbox(doc.sender)
    if not address:
        return
    action = reply_action(doc.content)
    names = frappe.get_all("Sentio Prospect", filters={"email": address}, pluck="name")
    if not names:
        return
    for name in names:
        frappe.db.set_value("Sentio Prospect", name, "follow_up_status", action)
    if action == "Opted out" and not frappe.db.exists(
        "Sentio Suppression", {"email": address}
    ):
        # A received message is evidence for stopping, never for granting permission.
        frappe.get_doc(
            {
                "doctype": "Sentio Suppression",
                "email": address,
                "reason": "Opted out",
                "evidence": "Incoming Communication " + doc.name,
            }
        ).insert(ignore_permissions=True)


def validate_draft(doc, method=None):
    p = frappe.get_doc("Sentio Prospect", doc.prospect)
    p.check_permission("read")
    old = doc.get_doc_before_save()
    if old and (
        old.subject != doc.subject
        or old.body != doc.body
        or old.prospect != doc.prospect
    ):
        doc.draft_status = "Draft"
    if doc.draft_status == "Reviewed":
        if not _manager() and (not old or old.draft_status != "Reviewed"):
            frappe.throw(
                "A marketing manager must review this message", frappe.PermissionError
            )
        doc.content_fingerprint = message_fingerprint(doc.subject, doc.body)
    else:
        doc.content_fingerprint = ""


def pause_delivery(doc):
    if not doc.communication:
        return
    c = frappe.get_doc("Communication", doc.communication)
    if c.reference_doctype not in {"CRM Lead", "CRM Deal"} or not c.reference_name:
        return
    ref = frappe.get_doc(c.reference_doctype, c.reference_name)
    if ref.get("sentio_prospect"):
        frappe.db.set_value(
            "Sentio Prospect", ref.sentio_prospect, "follow_up_status", "Paused"
        )
