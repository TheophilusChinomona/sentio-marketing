"""Prepare a reviewed research run for explicit API import, without any HTTP calls."""

import argparse
import csv
import json
import re
from pathlib import Path
from sentio_marketing.policy import CLIENT, normalize_record


def _read(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def prepare(workspace: Path, client_id: str, run_id: str):
    if not CLIENT.fullmatch(client_id) or not re.fullmatch(r"\d{8}T\d{6}Z", run_id):
        raise ValueError("Invalid client or run ID")
    original = workspace.resolve() / "clients"
    for part in [
        original,
        original / client_id,
        original / client_id / "runs",
        original / client_id / "runs" / run_id,
        original / client_id / "client.json",
    ]:
        if part.is_symlink():
            raise ValueError("Symlinked client input is not permitted")
    clients = (workspace.resolve() / "clients").resolve()
    root = (clients / client_id).resolve()
    if root.parent != clients or not root.is_dir():
        raise ValueError("Client path is not isolated")
    run = (root / "runs" / run_id).resolve()
    if run.parent != (root / "runs").resolve():
        raise ValueError("Run path escapes client")

    def file(name):
        p = run / name
        if p.is_symlink() or p.resolve().parent != run:
            raise ValueError("Source file escapes reviewed run")
        return p

    manifest = json.loads((root / "client.json").read_text(encoding="utf-8-sig"))
    if manifest["client_id"] != client_id or not manifest.get("export_reviewed"):
        raise ValueError("Client export review is required")
    required = ["accounts.csv", "contacts.csv", "lead-master.csv", "evidence.csv"]
    for n in required:
        if "runs/" + run_id + "/" + n not in manifest["export_allowlist"]:
            raise ValueError("Input not in reviewed client allowlist: " + n)
    accounts = {r["account_id"]: r for r in _read(file("accounts.csv"))}
    leads = {r["account_id"]: r for r in _read(file("lead-master.csv"))}
    ev = {r["evidence_id"]: r for r in _read(file("evidence.csv"))}
    contacts = _read(file("contacts.csv"))
    result = []
    for c in contacts:
        a = accounts[c["account_id"]]
        l = leads[c["account_id"]]
        urls = [
            u.strip()
            for u in c.get("source_urls", "").split(" | ")
            if u.strip().startswith(("https://", "http://"))
        ]
        source = urls[0] if urls else l.get("source_url") or "https://" + a["domain"]
        raw = dict(
            client_id=client_id,
            account_id=c["account_id"],
            contact_id=c["contact_id"],
            company=a["company"],
            person_name=c.get("name", ""),
            email=c["email"],
            phone=l.get("phone", "").lstrip("'"),
            website=l.get("website") or "",
            email_type=c["email_type"],
            role_status=c["role_status"],
            verification_status=c["verification_status"],
            verification_provider=c["verification_provider"],
            verified_at=c["verified_at"],
            verification_ref=c["verification_ref"],
            review_status="excluded"
            if a["exclusion"] or a["review_status"] == "excluded"
            else "hold"
            if a["review_status"] == "hold"
            else c["review_status"],
            source_url=source,
            source_run=run_id,
            selected=l["selected"],
            fit=a["fit"],
            timing=a["timing"],
            source_confidence=a["confidence"],
            customer_screening=l.get(
                "customer_screening", l.get("supplier_screening", "unchecked")
            ),
            dnc_consent=l.get("dnc_consent", "unchecked"),
            duplicate_group=l.get("duplicate_group", ""),
            notes=l.get("notes", "")
            + ("\nAccount exclusion: " + a["exclusion"] if a["exclusion"] else ""),
        )
        r = normalize_record(raw, client_id)
        observations = []
        for evidence_id in set(
            a["evidence_ids"].split(" | ") + c["role_evidence_ids"].split(" | ")
        ):
            if not evidence_id:
                continue
            if evidence_id not in ev:
                raise ValueError("Unresolved evidence " + evidence_id)
            e = ev[evidence_id]
            if e["source_url"].startswith(("https://", "http://")):
                observations.append(
                    dict(
                        field_name="account_or_role",
                        claim=e["claim"],
                        source_url=e["source_url"],
                        observed_at=e["retrieved_at"],
                        evidence_status=e["status"],
                    )
                )
        if r["verification_status"] != "unverified":
            observations.append(
                dict(
                    field_name="email",
                    claim=r["verification_status"]
                    + " via "
                    + r["verification_provider"],
                    source_url="https://treg.to/calls/"
                    + r["verification_ref"]
                    + "/result",
                    observed_at=r["verified_at"],
                    evidence_status="observed",
                )
            )
        r["evidence"] = observations
        r.pop("approval_status")
        r.pop("eligibility_evidence")
        r.pop("approved_fingerprint")
        r.pop("follow_up_status")
        result.append(r)
    if len({r["source_key"] for r in result}) != len(result):
        raise ValueError("Duplicate source records")
    return result


def main():
    p = argparse.ArgumentParser(
        description="Prepare research JSON locally; does not upload or send anything"
    )
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--client-id", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    records = prepare(args.workspace, args.client_id, args.run_id)
    if args.output.exists():
        p.error("Output exists; choose a new file")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(
            {
                "client_id": args.client_id,
                "source_run": args.run_id,
                "record_count": len(records),
                "batches": [
                    {
                        "client_id": args.client_id,
                        "records": records[i : i + 100],
                        "dry_run": True,
                    }
                    for i in range(0, len(records), 100)
                ],
            },
            f,
            indent=2,
        )
    args.output.chmod(0o600)
    print(
        str(len(records))
        + " research records prepared; 0 approvals granted; no upload or sends."
    )


if __name__ == "__main__":
    main()
