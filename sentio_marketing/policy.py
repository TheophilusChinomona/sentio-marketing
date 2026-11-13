"""Pure, deterministic import and outreach policy. No credentials or provider calls."""

import hashlib
import json
import re
from datetime import datetime
from email.utils import parseaddr
from html.parser import HTMLParser
from urllib.parse import urlsplit

STATUSES = {"valid", "invalid", "catch-all", "unknown", "unverified"}
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,139}$")
CLIENT = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
EMAIL = re.compile(r"^[^\s@<>;,]+@[^\s@<>;,]+\.[^\s@<>;,]+$")
APPROVAL_FIELDS = (
    "company",
    "person_name",
    "fit",
    "duplicate_group",
    "client_id",
    "account_id",
    "contact_id",
    "email",
    "email_type",
    "role_status",
    "verification_status",
    "verification_provider",
    "verified_at",
    "verification_ref",
    "review_status",
    "selected",
    "source_url",
    "source_run",
    "eligibility_evidence",
)


def as_bool(v):
    return v is True or v == 1 or str(v).lower() in {"yes", "true", "1"}


def source_key(record):
    return hashlib.sha256(
        "|".join(
            str(record.get(k, "")).strip()
            for k in ["client_id", "account_id", "contact_id"]
        ).encode()
    ).hexdigest()


def approval_fingerprint(record):
    return hashlib.sha256(
        json.dumps(
            {k: record.get(k) for k in APPROVAL_FIELDS}, sort_keys=True, default=str
        ).encode()
    ).hexdigest()


def _url(value):
    p = urlsplit(value)
    if p.scheme not in {"https", "http"} or not p.hostname or p.username or p.password:
        raise ValueError(
            "Evidence URL must be an attributable HTTP(S) URL without credentials"
        )
    return value


def normalize_record(raw, site_client):
    if not CLIENT.fullmatch(site_client or "") or raw.get("client_id") != site_client:
        raise ValueError("Import client does not match this site")
    for k in ["account_id", "contact_id"]:
        if not ID.fullmatch(str(raw.get(k) or "")):
            raise ValueError("Invalid or missing " + k)
    if not re.fullmatch(r"\d{8}T\d{6}Z", str(raw.get("source_run") or "")):
        raise ValueError("Invalid source run")
    r = {
        k: str(raw.get(k) or "").strip()
        for k in [
            "client_id",
            "account_id",
            "contact_id",
            "company",
            "email",
            "email_type",
            "role_status",
            "verification_status",
            "verification_provider",
            "verified_at",
            "verification_ref",
            "review_status",
            "source_url",
            "source_run",
            "phone",
            "website",
            "notes",
            "fit",
            "timing",
            "source_confidence",
            "customer_screening",
            "dnc_consent",
            "duplicate_group",
        ]
    }
    r["fit"] = r.get("fit") or "unknown"
    r["timing"] = r.get("timing") or "unknown"
    r["source_confidence"] = r.get("source_confidence") or "low"
    if (
        r["fit"] not in {"strong", "possible", "poor", "unknown"}
        or r["timing"] not in {"current-signal", "no-current-signal", "unknown"}
        or r["source_confidence"] not in {"high", "medium", "low"}
    ):
        raise ValueError("Invalid account fit, timing or source confidence")
    r["person_name"] = str(raw.get("person_name", raw.get("name", "")) or "").strip()
    r["email"] = r["email"].lower()
    r["selected"] = as_bool(raw.get("selected"))
    if not r["company"]:
        raise ValueError("Company is required")
    if r["email"] and not EMAIL.fullmatch(r["email"]):
        raise ValueError("Malformed email")
    if r["email_type"] not in {"shared-work", "named-work", "unknown"}:
        raise ValueError("Invalid email type")
    if r["role_status"] not in {"supported", "unknown", "conflicting"}:
        raise ValueError("Invalid role status")
    if r["verification_status"] not in STATUSES:
        raise ValueError("Invalid verification status")
    if not r["email"] and r["verification_status"] != "unverified":
        raise ValueError("A blank email cannot be verified")
    if r["verification_status"] != "unverified":
        if not all(
            r[k] for k in ["verification_provider", "verified_at", "verification_ref"]
        ):
            raise ValueError("Provider, date and receipt required")
        try:
            datetime.fromisoformat(r["verified_at"].replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError("Invalid verification timestamp") from e
    if r["review_status"] not in {"draft", "reviewed", "approved", "hold", "excluded"}:
        raise ValueError("Invalid research review status")
    if (
        r["email_type"] == "shared-work"
        or r["role_status"] == "conflicting"
        or r["verification_status"] in {"invalid", "unknown", "catch-all"}
    ):
        if r["review_status"] != "excluded":
            r["review_status"] = "hold"
    r["source_url"] = _url(r["source_url"])
    if r["website"]:
        _url(r["website"])
    r.update(
        source_key=source_key(r),
        approval_status="Pending",
        eligibility_evidence="",
        approved_fingerprint="",
        follow_up_status="Not started",
    )
    return r


def eligibility_reasons(
    record, site_client, enabled, *, suppressed=False, is_reply=False
):
    reasons = []
    if not enabled:
        reasons.append("Client outreach is disabled")
    if record.get("client_id") != site_client:
        reasons.append("Client/site mismatch")
    if not EMAIL.fullmatch(record.get("email") or ""):
        reasons.append("No attributable email")
    if record.get("verification_status") != "valid":
        reasons.append("Mailbox is not provider-valid")
    if not all(
        record.get(k)
        for k in ["verification_provider", "verified_at", "verification_ref"]
    ):
        reasons.append("Verification evidence is incomplete")
    if (
        record.get("email_type") != "named-work"
        or record.get("role_status") != "supported"
    ):
        reasons.append("Named current-role review required")
    if record.get("fit") == "poor" or record.get("duplicate_group"):
        reasons.append("Account fit or duplicate review is unresolved")
    if record.get("review_status") in {"hold", "excluded"} or not as_bool(
        record.get("selected")
    ):
        reasons.append("Research record held or not selected")
    if (
        record.get("approval_status") != "Approved"
        or not str(record.get("eligibility_evidence") or "").strip()
    ):
        reasons.append("Eligibility approval and evidence required")
    if suppressed:
        reasons.append("Address is suppressed")
    if record.get("follow_up_status") in {"Opted out", "Bounced", "Paused"} or (
        record.get("follow_up_status") == "Replied" and not is_reply
    ):
        reasons.append("Follow-ups stopped")
    return reasons


class _ReplyText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.quote = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "blockquote":
            self.quote += 1
        elif tag in {"p", "div", "br"} and not self.quote:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "blockquote":
            self.quote = max(0, self.quote - 1)

    def handle_data(self, data):
        if not self.quote:
            self.parts.append(data)


def reply_action(content):
    p = _ReplyText()
    p.feed(str(content or "")[:100000])
    text = "".join(p.parts)
    lines = [
        x.strip().lower().rstrip(".!")
        for x in text.splitlines()
        if x.strip() and not x.lstrip().startswith(">")
    ]
    return (
        "Opted out"
        if lines
        and lines[0]
        in {
            "stop",
            "unsubscribe",
            "remove me",
            "please remove me",
            "please stop",
            "do not contact me",
        }
        else "Replied"
    )


def mailbox(value):
    return parseaddr(str(value or ""))[1].lower()


class _MessageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "div", "br", "blockquote"}:
            self.parts.append("\n")
        self.links.extend(
            (tag, k, v) for k, v in attrs if k in {"href", "src", "srcset"}
        )

    def handle_data(self, data):
        self.parts.append(data)


def message_fingerprint(subject, content):
    p = _MessageText()
    p.feed(str(content or ""))
    body = " ".join("".join(p.parts).split())
    return hashlib.sha256(
        json.dumps(
            [str(subject or "").strip(), body, p.links], ensure_ascii=False
        ).encode()
    ).hexdigest()
