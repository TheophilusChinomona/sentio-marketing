# Sentio Marketing for Frappe CRM

An AGPL-3.0 Frappe 16 app for client-hosted CRM research, evidence and reviewed outreach. Companion CRM fork: https://github.com/TheophilusChinomona/sentio-crm/tree/sentio-v16 . This is a first implementation for staging; no production deployment or customer migration is implied.

## What it does

- One configured client per site. Imports reject a different client ID. Separate Frappe sites/databases are the tenant boundary; Organizations are prospects, not client workspaces.
- Research records preserve account/contact IDs, public phones, named versus shared email type, role status, original verification provider/date/receipt, source URLs and research holds. Aliases do not become invented people.
- Immutable evidence observations sit alongside CRM Organizations. Supported named candidates can be promoted to CRM Leads by a manager. Imports do not trigger website enrichment; no provider keys, paid calls or budget assumptions are included.
- Outreach eligibility, research review and mailbox validity are separate. Imports never grant approval. Reviewed corrections are not silently overwritten by a differing import; older source runs are rejected. Exact reimports preserve existing state.
- A manager records actual recipient-eligibility evidence and reviews an exact email subject/body. Ordinary CRM-linked communications are checked against that approval, content fingerprint, sender domain, single recipient and suppression state. Subject/text/link changes require a new copy review.
- The Frappe 16 Email Queue mixin rechecks just before standard queued delivery, including scheduled/retried messages. Replies stop unsolicited follow-ups; an explicit reply to the same person's incoming Communication may still pass review. Exact first-line opt-outs create a suppression record. Other opt-out language requires human handling, but any reply pauses marketing follow-ups. Transport errors pause outreach rather than claiming a confirmed hard bounce. No automatic campaign scheduler is provided.
- Public `/source` information links to source, licence and build/install material. Keep exact deployed revisions available to users; hosting/support can be charged while preserving their AGPL rights.

## Installation on a staging Bench site

First install the CRM fork (app name remains `crm`), then this app:

```sh
bench get-app --branch sentio-v16 https://github.com/TheophilusChinomona/sentio-crm
bench get-app --branch main https://github.com/TheophilusChinomona/sentio-marketing
bench --site YOUR-STAGING-SITE install-app crm
bench --site YOUR-STAGING-SITE install-app sentio_marketing
```

For production images use `deploy/compose.yaml` and the app manifest, not live `bench get-app` changes inside running containers. Build both apps with Frappe branch version-16. Preserve licences and upstream notices. The public manifest contains code URLs only; mailbox/provider credentials never belong there.

On the site, open **Sentio Marketing Settings** in Desk. Set the explicit client ID and authorised sender domain. Outreach defaults off. Assign the `Sentio Marketing Manager` role only to reviewers; `Sales User` can view research and prepare drafts. Connecting mailboxes still requires appropriate `Email Account` permissions, usually a site administrator. Test these roles with non-administrator accounts before onboarding clients.

## Import the existing research

The CLI consumes only the exact reviewed allowlist in a marketing workspace's `client.json` and four CSVs in the selected run. It rejects traversal/symlink paths, preserves historical dates and excludes unmatched bulk research that is absent from those reviewed contacts.

```sh
python3 -m sentio_marketing.prepare --workspace /path/to/marketing \
  --client-id YOUR-CLIENT --run-id YYYYMMDDTHHMMSSZ \
  --output /private/path/research-batches.json
```

This only writes a permission-restricted local JSON file. It contains batches of at most 100 records with `dry_run: true`; it makes no network requests. Submit each batch, after authorising transfer to that client's own site, to `/api/method/sentio_marketing.api.import_research` using a permission-scoped Frappe API user. Run every batch as a dry run first. Explicitly set `dry_run: false` to write only after review. There is no upload/send/provider-research action in this repository's preparation command. Do not commit these JSON files.

Source IDs are the deduplication key. Unchanged reimports preserve reviews/follow-up stops; differing reviewed records require explicit reconciliation. CRM Organization name collisions with an unrelated existing record are errors for manual reconciliation, not permission to merge branches. Each import RPC is transactional, but a multi-batch import is not a single transaction; reconcile returned counts before continuing after a failure.

## Client workflow

1. **Research** in the CRM sidebar shows mailbox and review states. Open an item in Desk to inspect fields/evidence. Unidentified people and missing emails remain visibly missing.
2. A marketing manager identifies the real named contact, resolves research holds and records actual recipient eligibility. Use **Approve outreach**; this does not enable global sending or grant permission by itself. If reviewed source attributes change, approval resets.
3. Create a CRM lead only for a supported named candidate. Shared inboxes stay research-only in this initial conservative workflow.
4. Create a **Sentio Email Draft**, including the actual subject, signature, links and body. A manager sets its status to Reviewed after saving the final text. Editing the text resets it to Draft. In CRM, use that reviewed message and the linked recipient. CC/BCC are not approved by this first-version flow.
5. After site tests and mailbox checks, a site administrator may enable reviewed outreach. Stop/suppress requests are recorded in **Sentio Suppression**. `resume_after_review` can reset a non-suppressed paused record to Pending with fresh evidence; it cannot override a suppression or itself grant approval.

Hooks protect CRM Lead/Deal-linked Communication and standard Email Queue delivery. They do not prevent a privileged administrator from changing code, direct SMTP outside Frappe, unrelated applications or emails already delivered. System emails such as password resets are not treated as prospect outreach. This is an operational review workflow, not a certification of consent or legal compliance.

## Verification

```sh
python3 -m unittest discover -s sentio_marketing/tests
python3 -m compileall -q sentio_marketing
# Disposable test site only, with crm and this app installed:
bench --site YOUR-TEST-SITE run-tests --module sentio_marketing.tests.integration_frappe
```

Local pure/adapter tests cover client mismatch, source identity, status/date integrity, holds, approval changes, suppression, reviewed message changes, queued delivery ordering, reply/opt-out handling and mail sender/recipient restrictions. Integration tests are supplied but **not run locally**: the development environment has no usable Docker daemon/Bench database. Full image build, migration, role behaviour, browser login, provider authentication, actual sending and reply ingestion still require staging verification. No real mail or research providers are contacted by local tests.

## Source and deployment

Use `tools/export_source.py` after committing both repositories to make a corresponding-source bundle with revision manifest. The repositories, release tags, app code and deployment files must match the hosted version; include further operator modifications as well. Do not put secrets or client data in the bundle. See `deploy/README.md` before changing a live site. Do not reuse another client's volumes.
