# Notion → iCloud Calendar Sync

Cloudflare Python Worker that mirrors every dated Notion task into a single iCloud calendar. Webhooks push near-real-time updates, and a cron-triggered rewrite keeps the calendar authoritative.

## Requirements
- Python 3.12+, [uv](https://github.com/astral-sh/uv), and Cloudflare’s `pywrangler` CLI.
- Cloudflare account with Workers + KV access.
- Notion internal integration token shared with your task databases.
- Apple ID plus app-specific password for CalDAV.

## Configuration
Create a `.env` (used locally and when running `pywrangler secret put`):

| Key | Purpose |
| --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | Worker account |
| `CLOUDFLARE_API_TOKEN` | Token with Workers + KV permissions |
| `CLOUDFLARE_STATE_NAMESPACE` | KV namespace ID for the `STATE` binding |
| `NOTION_TOKEN` | Notion integration token |
| `ADMIN_TOKEN` | Required by `/admin/*` endpoints |
| `APPLE_ID` / `APPLE_APP_PASSWORD` | iCloud Calendar credentials |

When Notion first performs the webhook verification handshake, the worker automatically persists the provided verification token into KV and uses it for all future signature checks—no manual secret management required.
### Create the KV namespace once
```bash
uv run -- pywrangler kv namespace create --namespace "notion-caldav-sync-STATE"
```
Copy the returned ID into `CLOUDFLARE_STATE_NAMESPACE`.

## Deployment
```bash
# setup venv
uv venv --python 3.12
uv sync
uv sync --group dev

# deploy to cloudflare
chmod a+x deploy.sh
./deploy.sh
```

The script ensures `wrangler.toml` matches your KV namespace, prompts for secrets via `pywrangler`, and deploys the Worker. Update your Notion webhook URL to the production Worker afterwards.

Pywrangler automatically bundles your project code and dependencies during `dev`/`deploy` (see Cloudflare’s [Python packages guide](https://developers.cloudflare.com/workers/languages/python/packages)).

### Create the Notion integration
1. Visit [Notion Developers → My integrations](https://www.notion.so/my-integrations) and create a new integration.
2. Fill out the basic form:
   - **Integration name:** e.g. `iCloud Calendar`.
   - **Associated workspace:** whichever workspace owns your task databases.
3. **Capabilities**
   - *Content* → enable only **Read content**.
   - *Comments* → leave every option unchecked.
   - *User information* → choose **No user information**.
4. **Access**
   - Under *Page and database access*, explicitly select the databases that should appear in the calendar.
5. **Webhooks**
   - *Webhook URL:* `https://<worker-url>/webhook/notion` (replace with your .workers.dev domain or custom route).
   - *Subscribed events:* check every **Page**, **Database**, and **Data source** entry. Leave **Comment** and **File upload** unchecked.
6. Save the integration and copy the generated secret into your `.env` as `NOTION_TOKEN`.

### Useful HTTP endpoints
- Manual full rewrite: `curl -X POST -H "X-Admin-Token: $ADMIN_TOKEN" http://localhost:8787/admin/full-sync`
- Settings view/update: `curl -H "X-Admin-Token: $ADMIN_TOKEN" http://localhost:8787/admin/settings`
- Debug info: `curl -H "X-Admin-Token: $ADMIN_TOKEN" http://localhost:8787/admin/debug`


## Testing
All tests hit live APIs, so use staging credentials.
```bash
uv run -- pywrangler dev --persist-to .wrangler/state
uv run python -m tests.cli smoke --env-file .env
uv run python -m tests.cli full --env-file .env
```

## Notes
- Only tasks with a start date sync; undated pages are skipped.
- The worker stores only calendar metadata (`calendar_href`, `calendar_name`, `calendar_color`, `full_sync_interval_minutes`, `event_hashes`, `last_full_sync`, `webhook_verification_token`) in KV.
- Rename/recolour the iCloud calendar directly—the worker reuses those values from KV.
- Cron runs every 30 minutes (see `wrangler.toml`). The actual rewrite occurs when `full_sync_interval_minutes` (stored in KV via `/admin/settings`) has elapsed.

## License
MIT – see `LICENSE`.
