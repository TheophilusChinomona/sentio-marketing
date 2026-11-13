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

## 0.1.1 build-cache repair

Docker does not include build-secret contents in its cache checksum. A deployment using `--build` can therefore reuse a Framework-only app-install layer after FRAPPE_APPS_JSON changes. Version 0.1.1 uses the canonical public manifest SHA256 as CACHE_BUST, requires the BuildKit secret, validates that the supplied manifest matches this release and checks/imports both apps in the builder. A mismatch now stops the build with a clear error rather than producing an incomplete runtime image. No Docker cache pruning or volume deletion is needed.

Replace BOTH the Compose YAML and the FRAPPE_APPS_JSON Environment value from this release's environment.example; keep existing hostname/passwords/volumes. Dockerfile_inline contains no dollar variables, avoiding accidental Compose interpolation of Docker build arguments. Its equivalent standalone source is deploy/Containerfile, adapted from the pinned upstream builder with its licence in deploy/FRAPPE-DOCKER-LICENSE.

If using the existing `crm-frappe-ghecbc` service, a successful build is followed by the deliberate existing-site guard in create-site. That guard is expected: use the existing-site upgrade steps above after backup and staging validation. Do not delete site_config.json, forge a completion marker or reset volumes to get past it.
