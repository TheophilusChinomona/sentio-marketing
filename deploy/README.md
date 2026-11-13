# Dokploy staging and upgrades

Use Docker Compose mode and an x86-64 build server with BuildKit. This is a source-reviewed configuration, not a verified production deployment. Do not apply it directly over the working CRM as the first test.

## New staging site

Create a separate Dokploy Compose project so its named volumes are new and isolated. Paste compose.yaml, set the five environment variables from environment.example (including the public app manifest), and route the chosen staging hostname to frontend:8080 with HTTPS. Never expose database/Redis/backend ports. Set the explicit pilot client ID and different strong passwords.

The source manifest includes the tagged CRM fork and marketing app. The backend build uses Frappe's pinned layered Containerfile with Frappe version-16 and an apps_json BuildKit secret. All application services share its locally built image. Backend builds before services start; no registry publishing is required. The configurator checks BOTH apps exist. First bootstrap installs both apps and configures the client with outreach disabled.

Validate build logs, configurator completion, create-site completion, `/crm`, `/crm/research`, `/desk/sentio-prospect` and `/source`. Test as a restricted Sales User as well as an administrator. Run the supplied integration suite on a disposable test site. Import synthetic data before authorising any real client upload. No live mailboxes or messages are required to test data isolation and review rules.

## Existing CRM site — deliberate upgrade only

1. Back up the running site's database, all site files and encryption/site configuration; verify the recovery location. Preserve the old image tag/digest and matching application source. Test a restore and this upgrade on staging first.
2. Build the new image without deleting the production service or its existing volumes. Keep its current hostname/password values. The initializer intentionally stops when it sees an existing non-Sentio site; do not delete data or forge the completion marker to bypass it.
3. During an agreed maintenance window, use a one-shot backend container from the new image (`docker compose run --rm --no-deps backend ...`) to run `bench --site YOUR-SITE migrate`, then `bench --site YOUR-SITE install-app sentio_marketing`. Confirm site client settings through Desk. Existing CRM data is not imported into the new research model automatically.
4. Only after migration and installation succeed, use the same one-shot backend to create `sites/YOUR-SITE/.sentio-bootstrap-complete` (with `touch`), then redeploy/start services. Run browser/permission/import checks. Keep outreach off until recipient, sender and mailbox checks are complete. Changing passwords in .env does not rotate stored credentials.
5. For subsequent releases, back up, build versioned images, migrate explicitly, test, and retain the previous image plus backups. A database migration may require restore rather than an image-only rollback. The completion marker prevents reinitialisation; it does not perform migrations.

No script here changes your live Dokploy service, logs into a mailbox, imports client data remotely, sends email or buys research. Firecrawl/Treg remain external scoped tools; their integration point is the source-backed import API, not an unattended paid worker.

## Source obligations and release identity

Each release tags both repositories and supplies corresponding source, build scripts and deployment instructions. `/source` and the CRM sidebar link make this discoverable. If you apply further patches, provide their matching source too. Client data, credentials, provider journals and mailbox passwords are excluded. Source bundles can be made with tools/export_source.py after committing both trees.
