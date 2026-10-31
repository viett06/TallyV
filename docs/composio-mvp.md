# Outlook end-to-end MVP through Composio

Use a dedicated test Outlook mailbox containing only synthetic departments, employees, workbooks and evidence images. Email delivery, Microsoft sign-in, mailbox reads and attachment downloads are real; all business data is fictional. Do not connect hospital production accounts or upload hospital data to this environment.

Composio is an external processor in this path. The UI identifies it explicitly. This prototype does not establish hospital accreditation, privacy or security compliance. A later Microsoft-direct deployment requires separate institutional review and approval; changing the mail connector alone does not establish compliance.

## One-time setup

1. Create a Hobby project in the [Composio dashboard](https://dashboard.composio.dev). Obtain a **project API key**, not a Microsoft secret or an organization key. Keep the key local; never paste it into chat or commit it.
2. In a local Python environment with `requirements.txt` installed, run from the repository root:

   ```bash
   python -m scripts.configure_composio
   ```

   The prompt hides the key. The script creates an Outlook **Composio-managed OAuth** auth config with `User.Read`, `Mail.Read` and identity/offline scopes, and saves its ID and the project key in `.env` with mode `0600`. It preserves existing database credentials and application secrets. No Microsoft Entra app registration is needed for this managed connection. Restarting the script creates another auth config; delete unused configs in the dashboard if necessary.

3. Build and start the API and worker with outbound access:

   ```bash
   docker compose -f compose.yaml -f compose.outlook.yaml up -d --build
   ```

   The API applies Alembic migrations before startup. If running the API through Uvicorn instead, apply `alembic upgrade head`, restart that process and rebuild/restart only the Docker worker. Do not start a Docker API on a port already used by Uvicorn. The setup script runs on the host so it can update the host `.env`; running it inside an already-created container does not update Compose's source environment file.

4. Open `http://localhost:8000`, sign in with the existing local HR credentials, and choose **Connect Outlook**. Continue through Composio's Connect Link, Microsoft account selection and the consent screen. Check the account and permissions before accepting. Composio returns to `http://localhost:8000/api/outlook/callback`. Its address must match `OUTLOOK_REDIRECT_URI` and the origin used to open TallyV.

The Composio dashboard's current allowance and project/account eligibility still apply. The connector handles exhausted quotas and upstream throttling without advancing the inbox checkpoint. Pricing can change; see the [current pricing](https://composio.dev/pricing), including the separate proxy-execution allowance.

## Configuration

The setup command writes these values:

```dotenv
MAIL_PROVIDER=outlook
OUTLOOK_TRANSPORT=composio
OUTLOOK_TEST_MODE=true
COMPOSIO_API_KEY=your-project-api-key
COMPOSIO_AUTH_CONFIG_ID=ac_your-read-only-outlook-auth-config
COMPOSIO_POLL_INTERVAL=0
```

`OUTLOOK_CLIENT_ID` and `OUTLOOK_CLIENT_SECRET` are not used in Composio mode. Microsoft refresh/access tokens remain with Composio; TallyV never retrieves them. The API key is sent only from the backend to `https://backend.composio.dev/api/v3.1`.

The first successful connection queues an initial sync. Later syncs run when HR clicks **Sync Outlook**. Background polling is disabled by default to conserve the free allowance. Set `COMPOSIO_POLL_INTERVAL` to at least 60 seconds only if you intentionally want polling and have checked its quota impact; restart the worker after a change.

After changing `.env`, recreate the Compose services with `up -d`; `docker compose restart` does not reload their environment. If Uvicorn runs locally, restart Uvicorn and run `docker compose -f compose.yaml -f compose.outlook.yaml up -d --no-deps worker`. Updating only the API can leave a valid Outlook connection with a worker that still has no Composio key.

The connection panel displays the connected mailbox, connection time, last successful sync and any separate sync failure. It refreshes while open and when the window regains focus. A worker configuration failure does not invalidate Microsoft authorization; only an authentication/permission failure requests reconnection.

## Demonstrate real email delivery and processing

1. In **Connect Outlook**, add a fictional department and one or more test sender addresses you control. An address may serve multiple departments; the workbook identifies the intended department.
2. Download the employee CSV template. Import a fictional employee and the ID of the department just created. Download the workbook template and fill it with the same employee ID, name and department name. Use dates within the selected payroll period.
3. From a configured test sender, send an actual email to the connected **Outlook receiving address**, attaching the test workbook and synthetic evidence images. Check the address in Outlook itself: the Microsoft profile displayed in TallyV can be a Gmail sign-in alias, which is not necessarily the Outlook receiving address. A message sent from the same mailbox must also arrive in Inbox; Sent Items is not scanned.
4. Put both `[TALLYV-MVP]` and `[DCC]` in the subject, followed by the payroll period and Saturday round. For example:

   ```text
   [TALLYV-MVP] [DCC] [2026-11] [WEEK:2026-10-31] Synthetic department summary
   ```

   This is the November payroll period (26 October through 25 November). Its first Saturday is 31 October; the corresponding Monday is 2 November. Use the period and round currently selected in the UI rather than copying this example into another period.
5. Click **Scan Outlook**, then **Start Outlook scan**. Choose new messages since the previous scan or replay the most recent 1–365 days. Inspect scanned metadata, tagged messages, newly received emails and existing emails in the dialog. Open the email results to inspect workbook rows and errors, or open attendance cases for the aggregated department and period/round view. The worker continues after the dialog closes. Downloading emails and importing/analyzing Excel are separate queue stages; follow processing progress while workbooks are being processed. Repeating either scan mode must not create duplicate emails or cases. Invalid workbook rows remain visible for HR review.

The replay window is saved with the scan job. Each committed Graph page updates its counters and cursor together, so retrying a later page does not restart the window or double-count earlier pages. Clicking scan again while the job is active returns that job without replacing its requested window.

No automatic test-mail sender is added: send the synthetic message yourself from Outlook or another mailbox you control. TallyV does not send, delete, move or mark Outlook messages read.

## Boundaries

- Only tagged messages have bodies and attachments downloaded. Inbox metadata still passes through Composio during the scan. Tags are application filters, not a Microsoft permission boundary; use a dedicated synthetic mailbox.
- The connector rechecks tags before downloading attachments. It only sends GET requests to Microsoft Graph via the proxy. It never exposes a generic tool executor, exports provider tokens or follows arbitrary file-download URLs.
- New connection scope snapshots must contain `User.Read` and `Mail.Read` and must not request broader scopes. A broad default auth config is rejected; use the setup script to create the restricted config.
- Disabling `OUTLOOK_TEST_MODE` in Composio mode is rejected both at startup and before external reads. This does not detect real data disguised as test data; synthetic input remains the operator's responsibility.
- Browser-bound, expiring, one-use state and the server-created connected account ID are checked before accepting a callback. Returned account status, toolkit, auth config and Microsoft profile are verified server-side.
- Disconnect stops local reads immediately and requests upstream revocation/deletion. If that remote request fails, TallyV reports it; repeat disconnect or remove the account in Composio. Previously imported synthetic data remains local.
- Outlook-derived records remain separate from existing Mailpit samples. The source reference includes `outlook:composio:` so the ingestion transport is traceable.

## Later Microsoft-direct deployment

Disconnect the Composio test account before changing transport. Use a separately approved environment, database and storage for hospital data; do not reuse the synthetic MVP database as a production database.

Set `OUTLOOK_TRANSPORT=microsoft` and configure the institution-approved app registration described in [outlook.md](outlook.md). Restart the API and worker. Microsoft-direct mode does not call Composio, and connections from a different transport cannot be used silently. HR can then connect the approved Microsoft mailbox while using the same workbook parsing and review workflows.

## Validation

Automated tests use mocked Composio/Microsoft HTTP responses with real workbook bytes. They cover browser/callback binding, initial sync enqueueing, scope checks, tag filtering, attachment parsing, import, payroll rounds, deduplication, export, throttling, disconnect and migration preservation. Passing these tests is not evidence of a successful live Microsoft login. Live validation requires your project key and Microsoft consent.

API references: [Connect Links](https://docs.composio.dev/reference/api-reference/connected-accounts/postConnectedAccountsLink), [managed OAuth scopes](https://docs.composio.dev/docs/authentication/controlling-scopes), [read-only proxy execution](https://docs.composio.dev/reference/api-reference/tools/postToolsExecuteProxy), [account revocation](https://docs.composio.dev/reference/api-reference/connected-accounts/deleteConnectedAccountsByNanoid).
