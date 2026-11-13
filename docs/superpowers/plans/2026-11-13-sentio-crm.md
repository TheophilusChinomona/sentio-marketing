# Sentio CRM Implementation Plan

> Execution: native in this session; no additional agents. User approved the fork/custom-app direction. Use existing research without paid calls or sending.

**Goal:** Deliver a tested, source-controlled first version of the client-hosted marketing CRM.
**Architecture:** Thin Frappe CRM v16 fork plus AGPL custom Frappe app; one configured client per site. Pure validation/policy modules are independent of Frappe so boundary tests run locally.
**Tech stack:** Python, Frappe 16, Vue 3, existing CRM UI; MariaDB/Redis production Compose.
**Spec:** ../../spec.md

## Global constraints
- No client CSVs, API credentials, journals or actual mail passwords in either repository.
- No live deployment, import, mailbox connection, messages or new research spending.
- Preserve aliases, unknown fields, holds and historical verification dates; never infer named buyers.
- No private/proprietary licence claim for the modified AGPL application.

## Review focus
- Forged client IDs or source IDs must not cross site/import boundaries.
- Unknown/catch-all/held addresses and edits after approval must not become eligible accidentally.
- Password placeholders/disabled incoming mail must not leak credentials or cause unintended IMAP connections.
- Suppression/reply handling must not mistake quoted opt-out text for a new opt-out.
- Bootstrap/build configuration must preserve tenant volumes and require explicit settings.

## Tasks
1. [x] Fork: add failing pure mailbox validation tests; implement custom/Zoho create/edit UI and permission-first backend adapter; run existing frontend suite and new backend tests; commit.
2. [x] App: write failing import/policy tests; implement strict reviewed-data normalisation, custom DocTypes, installation and API; test client/identity/evidence boundaries; commit.
3. [x] Outreach: implement manager review, guarded CRM communications and reply/suppression tracking with focused tests and Frappe integration tests; commit.
4. [x] Delivery: create build/Compose/source export/runbooks, validate config and licence/source offer, prepare Thuto dry-run locally without publishing customer data; run all checks, push review branches and report actual runtime limitations.

## Verification boundary
Implementation/local checks complete. Frappe integration tests are supplied but not run; no accessible Docker daemon or Bench database exists here. Image build, schema migration, browser roles and mailbox connections require the documented staging step. No live deployment is authorised by a source commit.
