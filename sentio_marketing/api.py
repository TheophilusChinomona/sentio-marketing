"""Site-scoped, permission-checked research and review API. No provider calls or sends."""

import hashlib
import json
import frappe
from sentio_marketing.policy import (
    normalize_record,
    EMAIL,
    _url,
)


def manager():
    if not set(frappe.get_roles()) & {"System Manager", "Sentio Marketing Manager"}:
        frappe.throw("Marketing manager permission required", frappe.PermissionError)


def settings():
    s = frappe.get_single("Sentio Marketing Settings")
    if not s.client_id:
        frappe.throw("Configure this site’s client ID before importing research")
    return s


@frappe.whitelist()
def import_research(client_id: str, records: list, dry_run: bool = True):
    manager()
    s = settings()
    if client_id != s.client_id:
        frappe.throw("Client/site mismatch", frappe.PermissionError)
    if isinstance(records, str):
        records = json.loads(records)
    if not isinstance(records, list) or not 1 <= len(records) <= 100:
        frappe.throw("Import 1–100 records per batch")
    try:
        normalized = [
            normalize_record(
                dict(r, client_id=client_id) if "client_id" not in r else r, s.client_id
            )
            for r in records
        ]
    except (ValueError, TypeError) as e:
        frappe.throw(str(e))
    if len({r["source_key"] for r in normalized}) != len(normalized):
        frappe.throw("Duplicate source identity within batch")
    # Validate all evidence before changing any document; never trust supplied approval fields.
    observations = []
    for original, r in zip(records, normalized):
        ev = original.get("evidence", [])
        if not isinstance(ev, list) or len(ev) > 100:
            frappe.throw("Too many evidence observations")
        entries = []
        for e in ev:
            if not isinstance(e, dict) or not all(
                str(e.get(k) or "").strip()
                for k in ["field_name", "claim", "source_url", "observed_at"]
            ):
                frappe.throw("Evidence field, observation, URL and date required")
            try:
                _url(e["source_url"])
            except ValueError as error:
                frappe.throw(str(error))
            if e.get("evidence_status") not in {
                "observed",
                "client-confirmed",
                "inferred",
                "unknown",
            }:
                frappe.throw("Invalid evidence status")
            entry = {
                k: str(e[k])
                for k in [
                    "field_name",
                    "claim",
                    "source_url",
                    "observed_at",
                    "evidence_status",
                ]
            }
            entry["evidence_key"] = hashlib.sha256(
                (r["source_key"] + json.dumps(entry, sort_keys=True)).encode()
            ).hexdigest()
            entries.append(entry)
        observations.append(entries)
    unchanged = set()
    for row in normalized:
        if frappe.db.exists("Sentio Prospect", row["source_key"]):
            old = frappe.get_doc("Sentio Prospect", row["source_key"])
            old.check_permission("write")
            if old.source_run > row["source_run"]:
                frappe.throw(
                    "A newer source run is already present; stale imports are blocked"
                )
            same = normalize_record(old.as_dict(), s.client_id) == row
            if same:
                unchanged.add(row["source_key"])
            elif (
                old.review_status in {"reviewed", "approved"}
                or old.approval_status == "Approved"
            ):
                frappe.throw(
                    "Reviewed research differs from this import; reconcile the correction explicitly before importing"
                )
    if frappe.utils.sbool(dry_run):
        return {
            "client_id": s.client_id,
            "records": len(normalized),
            "write_performed": False,
            "approvals_granted": 0,
        }
    created = updated = 0
    for r, observed in zip(normalized, observations):
        key = r["source_key"]
        exists = frappe.db.exists("Sentio Prospect", key)
        doc = (
            frappe.get_doc("Sentio Prospect", key)
            if exists
            else frappe.new_doc("Sentio Prospect")
        )
        doc.check_permission("write" if exists else "create")
        if key not in unchanged:
            # Source-only reimports retain unrelated follow-up stop state; approval is always reset.
            follow_up = doc.follow_up_status if exists else "Not started"
            for field, value in r.items():
                setattr(doc, field, value)
            doc.follow_up_status = follow_up
            org = frappe.db.get_value(
                "CRM Organization", {"sentio_account_id": r["account_id"]}, "name"
            )
            if not org:
                # Leave website unset during insert to avoid upstream auto-enrichment/network jobs.
                organization = frappe.get_doc(
                    {
                        "doctype": "CRM Organization",
                        "organization_name": r["company"],
                        "sentio_account_id": r["account_id"],
                    }
                ).insert()
                org = organization.name
                if r["website"]:
                    frappe.db.set_value(
                        "CRM Organization", org, "website", r["website"]
                    )
            doc.organization = org
            doc.save()
        for e in observed:
            if not frappe.db.exists("Sentio Evidence", e["evidence_key"]):
                frappe.get_doc(
                    {"doctype": "Sentio Evidence", "prospect": doc.name, **e}
                ).insert()
        if exists and key not in unchanged:
            updated += 1
        elif not exists:
            created += 1
    return {
        "client_id": s.client_id,
        "created": created,
        "updated": updated,
        "approvals_granted": 0,
        "unchanged": len(unchanged),
    }


@frappe.whitelist()
def review_prospect(name: str, evidence: str, approve: bool = False):
    manager()
    doc = frappe.get_doc("Sentio Prospect", name)
    doc.check_permission("write")
    s = settings()
    if doc.client_id != s.client_id:
        frappe.throw("Client/site mismatch", frappe.PermissionError)
    if not str(evidence or "").strip():
        frappe.throw("Record the actual eligibility-review evidence")
    if doc.approval_status == "Approved":
        doc.approval_status = "Pending"
        doc.save()
        doc.reload()
    doc.eligibility_evidence = evidence
    doc.approval_status = "Approved" if frappe.utils.sbool(approve) else "Rejected"
    doc.save()
    return {"name": doc.name, "approval_status": doc.approval_status}


@frappe.whitelist()
def promote_to_lead(name: str):
    manager()
    s = settings()
    doc = frappe.get_doc("Sentio Prospect", name)
    doc.check_permission("write")
    if doc.client_id != s.client_id:
        frappe.throw("Client/site mismatch", frappe.PermissionError)
    if doc.crm_lead:
        return {"name": doc.crm_lead}
    if (
        not doc.person_name
        or doc.email_type != "named-work"
        or doc.role_status != "supported"
    ):
        frappe.throw(
            "Confirm a named contact and supported role first; aliases stay with research"
        )
    if doc.review_status in {"hold", "excluded"}:
        frappe.throw("Resolve this research hold before creating a CRM lead")
    names = doc.person_name.split(maxsplit=1)
    lead = frappe.get_doc(
        {
            "doctype": "CRM Lead",
            "first_name": names[0],
            "last_name": names[1] if len(names) > 1 else "",
            "email": doc.email,
            "phone": doc.phone,
            "organization": doc.company,
            "sentio_prospect": doc.name,
        }
    ).insert()
    doc.crm_lead = lead.name
    doc.save()
    return {"name": lead.name}


@frappe.whitelist()
def suppress(email: str, evidence: str, reason: str = "Manual hold"):
    manager()
    if (
        not EMAIL.fullmatch(email or "")
        or not evidence.strip()
        or reason not in {"Manual hold", "Bounced", "Opted out"}
    ):
        frappe.throw("Valid email, evidence and suppression reason required")
    email = email.lower()
    if not frappe.db.exists("Sentio Suppression", {"email": email}):
        frappe.get_doc(
            {
                "doctype": "Sentio Suppression",
                "email": email,
                "reason": reason,
                "evidence": evidence,
            }
        ).insert()
    return {"suppressed": True}


@frappe.whitelist(allow_guest=True)
def source_information():
    # Source URLs are public code repositories; no tenant data or credentials are returned.
    return {
        "license": "AGPL-3.0",
        "crm": "https://github.com/TheophilusChinomona/sentio-crm/tree/sentio-v0.1.0",
        "marketing_app": "https://github.com/TheophilusChinomona/sentio-marketing/tree/v0.1.0",
        "note": "These repositories include build and installation instructions. Deploy an exact source revision with each release.",
    }


@frappe.whitelist()
def resume_after_review(name: str, evidence: str):
    manager()
    doc = frappe.get_doc("Sentio Prospect", name)
    doc.check_permission("write")
    if not evidence.strip():
        frappe.throw("Fresh review evidence is required")
    if frappe.db.exists("Sentio Suppression", {"email": doc.email.lower()}):
        frappe.throw("Suppressed addresses cannot be resumed here")
    doc.approval_status = "Pending"
    doc.follow_up_status = "Ready"
    doc.eligibility_evidence = evidence
    doc.save()
    return {
        "name": doc.name,
        "approval_status": "Pending",
        "note": "Outreach still requires a new approval",
    }
