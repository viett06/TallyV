# Microsoft-direct Outlook inbox

For the synthetic MVP without your own Microsoft app registration, use [Composio setup](composio-mvp.md). This document describes the retained Microsoft-direct connection. Set `OUTLOOK_TRANSPORT=microsoft` explicitly for this path. Composio is never used as a fallback.

TallyV can connect to a developer's own Outlook mailbox through delegated Microsoft Graph access. The current MVP uses fictional departments, employees and workbooks, with no connection to hospital production systems. An email at a university domain may be a work/school Microsoft account; its domain alone does not prove that it is a consumer Outlook.com account. The default `common` authority supports both account types when the app registration permits them. Microsoft handles sign-in and MFA. The application never receives the Outlook password. Required delegated scopes are `User.Read` and `Mail.Read`; MSAL also requests the identity/offline scopes needed for sign-in and token refresh. Mail writing, sending and deletion permissions are not requested.

## One-time configuration

1. Register a **Web application for development** in a Microsoft Entra directory where you have app-registration permission. Choose **Accounts in any organizational directory and personal Microsoft accounts** to match `OUTLOOK_TENANT_ID=common`. This registration does not need to belong to the hospital. A university account may still require its administrator to approve consent; this cannot be bypassed by the application. Use the [Microsoft app registration guide](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app).
2. Add the Web redirect URI `http://localhost:8000/api/outlook/callback` for local development. The application origin and configured callback origin must match; open TallyV at `http://localhost:8000` when using this URI.
3. Add Microsoft Graph **delegated** permissions `User.Read` and `Mail.Read`. The mailbox owner must consent, subject to any school/work tenant restrictions. Do not add application-wide mailbox permissions or enable password authentication.
4. Create a client secret and put its **value**, not its secret ID, in the backend environment. Do not put it in frontend configuration, source control, or chat.

```dotenv
MAIL_PROVIDER=outlook
OUTLOOK_TENANT_ID=common
OUTLOOK_CLIENT_ID=your-application-client-uuid
OUTLOOK_CLIENT_SECRET=your-client-secret-value
OUTLOOK_REDIRECT_URI=http://localhost:8000/api/outlook/callback
OUTLOOK_SYNC_DAYS=90
OUTLOOK_TEST_MODE=true
```

App registration is a one-time deployment task, separate from choosing a mailbox. The application does not supply a Microsoft tenant, registration, or credentials. Until the client ID, client secret and authority are configured, the UI explains that the administrator must enable Microsoft sign-in. HR never needs to enter environment variables, a mailbox allowlist or an Outlook password into TallyV.

For deployment, use the real HTTPS origin in `OUTLOOK_REDIRECT_URI`, add that origin to `ALLOWED_ORIGINS`, and set `COOKIE_SECURE=true`. HTTPS callbacks use `form_post` with a dedicated Secure/HttpOnly/SameSite=None OAuth state cookie. Local HTTP uses query mode with a dedicated SameSite=Lax state cookie; callback query strings are removed from Uvicorn access logs. The HR application session retains its existing SameSite=Strict policy. State and PKCE data remain encrypted server-side and expire after ten minutes; state can be used only once.

Restart API and worker after changing environment variables. For an entirely Docker-hosted application:

```bash
docker compose -f compose.yaml -f compose.outlook.yaml up -d --build api worker
```

When Uvicorn already serves port 8000 directly, rebuild/restart only the worker:

```bash
docker compose -f compose.yaml -f compose.outlook.yaml build worker
docker compose -f compose.yaml -f compose.outlook.yaml up -d --no-deps worker
```

The Outlook override gives the worker the network route required to reach Microsoft identity and Graph. Base Compose retains the isolated worker network for explicit Mailpit demo runs. The API already has the access network. Requests carrying Graph bearer tokens use HTTPS, stay on `graph.microsoft.com`, do not follow redirects, and do not use environment proxies.

## MVP setup

1. Sign in to TallyV, then choose **Sync Outlook**. When no mailbox is connected, TallyV redirects to Microsoft for account selection, sign-in and delegated consent. The callback connects the selected mailbox and queues the initial sync automatically. Later clicks sync the existing connection. Use **Outlook connection** to view status or disconnect before choosing another account.
2. Add fictional departments and the test sender email addresses you control. A department can have multiple sender addresses, managed in the UI as one address per line or separated by commas. The same handler can also be assigned to multiple departments; the workbook must then unambiguously identify a department for which that sender is configured. Demo departments remain separate and are hidden in Outlook mode.
3. Download the employee CSV template. Import fictional employee records as UTF-8 CSV with `employee_id,name,department_id`, using the department IDs shown in the connection dialog. Imports are atomic, accept up to 2,000 rows/1 MB, preserve string employee IDs, and reject conflicting existing identities instead of overwriting them.
4. Download the attendance workbook template for departments. The existing XLSX headers, evidence anchors and row validation remain mandatory. Embedded workbook images continue through the local evidence/OCR workflow; this is not a general PDF or document extraction connector. One file must describe one payroll period.
5. Complete Microsoft sign-in and consent using the Outlook account you choose. Its address comes from the authenticated Microsoft profile. After the initial sync, the worker polls while the connection remains active. The connector reads departmental mail received in that signed-in Inbox; department sender configuration does not grant access to other users' mailboxes.

The first scan reads Inbox, including already-read mail, over the configured recent window (90 days by default, configurable from 1 to 365 days). Later scans follow the saved delta cursor for new mail. Previously imported records remain in TallyV. After changing `OUTLOOK_SYNC_DAYS`, disconnect and reconnect Outlook to restart the initial scan with the new window. In the default test mode, the worker fetches bodies and attachments only for messages carrying **both** `[TALLYV-MVP]` and `[DCC]`, including messages from configured senders. Unmarked mail is not copied into TallyV. Graph still returns Inbox metadata while scanning; the delegated `Mail.Read` permission itself applies to the mailbox, not just tagged messages. The tag is an application filter, not a Microsoft permission boundary.

The preferred subject explicitly identifies the payroll period and collection round:

```text
[TALLYV-MVP] [DCC] [2026-11] [WEEK:2026-10-31] Test department summary
```

In test mode both test tags are mandatory. If the period tag is absent, the payroll period is inferred only when valid workbook dates identify exactly one 26th–25th payroll period. The collection round remains unassigned unless explicitly declared. Dates are not guessed from the email receipt time. Invalid templates, mixed periods, unknown employees or mismatched departments require HR review. Cloud-file links and SharePoint/OneDrive references are not downloaded: the report must be an attached XLSX file.

Send the fictional workbook as an actual email attachment from your configured test sender to your test Outlook Inbox. For a single fictional department you can map your own address as its sender and manually send the test email to yourself. TallyV does not send these emails on your behalf. Use a new case ID such as `MVP-CASE-001`, a new employee ID such as `MVP-EMP-001`, and a fictional employee name that matches the imported CSV. The workbook uses the same department name entered in TallyV. Use the current payroll period and its Saturday/Monday round; the 26th–25th cutoff is unchanged.

Changing a department sender restarts the recent-window scan to pick up messages that were previously outside the sender allowlist. Already imported messages remain deduplicated. A stored message requiring review can be retried after correcting its department mapping or employee master.

## Persistence and isolation

There is no hardcoded mailbox address or required mailbox allowlist. Microsoft account selection determines which mailbox is connected, subject to the supported account types and any configured tenant restriction. One mailbox is active per workspace; disconnect before replacing it. Token cache identities, rather than the authority alias, scope message deduplication, so moving from `common` to a tenant UUID does not change source identities.

Migration `d035a91e7b62` moves every existing department sender into the `department_senders` table before removing the single-sender column. Existing department IDs, employee links, cases and emails are preserved. A sender shared across departments is resolved by the workbook department; ambiguous or unmapped submissions require review. Downgrade refuses mappings that cannot fit the previous one-sender schema without losing data.

For a later organization deployment, use a specific tenant UUID and its matching single-tenant registration. Disabling `OUTLOOK_TEST_MODE` restores `[DCC]` or configured-sender routing; it is not needed for this MVP and must not be used to import hospital production data during development.

Migration `c914e3fa7012` adds Outlook connection and temporary authorization-flow tables. MSAL access/refresh cache and PKCE flow data are encrypted with a key derived from the backend `SECRET_KEY`; rotating that key requires reconnecting Outlook. Keep the backend secret and database backups protected. Tokens are never sent to the frontend or stored in job payloads.

Graph delta/next-page URLs are persisted in the same transaction as imported emails. A page failure rolls back its email rows and checkpoint. Each job processes one page; remaining pages are queued immediately. HTTP 410 restarts the recent scan, using deduplication to avoid duplicate cases. Microsoft throttle responses honor `Retry-After`. Read/unread status is never the sync cursor.

Mailbox/tenant-bound immutable message identities protect against Outlook message moves. MIME Message-ID and workbook fingerprints add existing deduplication checks. See [Microsoft account/authority configuration](https://learn.microsoft.com/en-us/entra/msal/python/), [supported account types](https://learn.microsoft.com/en-us/security/zero-trust/develop/identity-supported-account-types), [Microsoft delta queries](https://learn.microsoft.com/en-us/graph/api/message-delta?view=graph-rest-1.0), [immutable IDs](https://learn.microsoft.com/en-us/graph/outlook-immutable-id), and [MSAL token acquisition](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens).

The UI scopes lists, dashboard and export to Outlook, preserving but excluding existing Mailpit samples. Real and sample cases cannot silently reuse the same case identity. Disconnect removes the local token cache and stops polling; revoking the application's Microsoft consent is a separate action in the organization's Microsoft account/admin tools.

## Local test mailbox

Set `MAIL_PROVIDER=mailpit` and restart API/worker to use Mailpit and the synthetic generators. Demo buttons are disabled by the backend in Outlook mode. Do not use the Outlook network override for a demo-only worker if network isolation is desired.

## Validation

Run `python -m pytest -q`, Ruff, `alembic check`, and the frontend build. Tests cover account selection without an email restriction, automatic initial-sync enqueue, multiple handlers and shared-sender department routing, preservation of migrated addresses, the actual MSAL PKCE initialization with in-memory discovery metadata, browser-bound one-time callbacks, token encryption, real-header MIME/XLSX intake, sender routing, payroll inference, pagination, cursor rollback, token-safe origin validation, Graph permission/throttle failures and separation from Mailpit data. Microsoft HTTP and SMTP are mocked in tests. A live sign-in must be verified after the development app registration is configured; passing local tests does not establish a live mailbox connection.
