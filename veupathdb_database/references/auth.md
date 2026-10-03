# Authentication and transport

## Getting and managing credentials

Authentication requires a registered VEuPathDB account. Tokens are stored
globally in `~/.config/veupathdb/token` with strict `0600` permissions (or
provided via the `VEUPATHDB_BEARER_TOKEN` environment variable). Because
VEuPathDB uses single sign-on across all 14 sites, a token obtained on any site
works on all of them.

### Agent-driven onboarding (Desktop & chat harnesses)
When an assistant runs this skill on behalf of a user:
- Chat/desktop users should **never** be instructed to run bash commands or open terminals.
- If `whoami` fails or reports GUEST, the assistant must **never** inspect `~/.config` or `env` (which triggers security approval popups), and must never attempt data queries.
- Instead, the assistant presents an interactive questionnaire (via `ask_question` in Antigravity, `AskUserQuestion` in Claude Code, or markdown chat choices) offering Option 1 (file path), Option 2 (direct paste), or Option 3 (registration).
- When the user provides their choice and input, the **assistant** runs the appropriate CLI login command and verifies with `whoami`.

> [!IMPORTANT] **Why password authentication is not supported**
> Account passwords must **never** be collected in chat conversations or command-line parameters. In assistant environments (Antigravity, Claude Code, etc.), session transcripts are persisted to disk (e.g. `~/.gemini`, `~/.claude`) and may be group- or world-readable, and process arguments are visible in system process tables. Personal API keys obtained from the browser can be revoked and regenerated at any time from the account profile without endangering master account passwords.

### Option 1: File path (Recommended — keeps token out of chat transcripts)
Best practice for chat/assistant environments:
1. Direct the user to open their community profile: `<profile_url>` (e.g. `https://plasmodb.org/plasmo/app/user/profile#serviceAccess`).
2. The user copies their personal API key from the **Service Access** tab and saves it to a local file (e.g. `/tmp/<site>-key` such as `/tmp/plasmodb-key` or `/tmp/vectorbase-key`).
3. The user replies with the file path in chat, and the agent executes:

       uv run scripts/wdk.py login [site] --token-file /tmp/<site>-key

   The CLI validates the token, writes it to `~/.config/veupathdb/token` (mode 0600), and the temporary file can then be deleted.

### Option 2: Direct paste into chat
For users who prefer not to create a local file:
1. Direct the user to open their community profile: `<profile_url>`.
2. The user copies their API key from the **Service Access** tab and pastes it into the chat message box.
3. The agent executes via stdin to prevent exposing the token in `ps` process tables:

       printf '%s' "<PASTED_KEY>" | uv run scripts/wdk.py login [site] --token -

### Option 3: Unregistered users
If the user does not have an account, direct them to register for free:
`https://veupathdb.org/veupathdb/app/user/registration` (or the component site's
registration page). After registration, they open their profile's Service Access tab, copy their API key, and provide it via Option 1 or Option 2.

### Community / Site Detection
To identify which community website a user's prompt pertains to:

    uv run scripts/wdk.py detect-site "Toxoplasma gondii rhoptry kinases"

This detects the target site (e.g. `toxodb`, `vectorbase`, `plasmodb`) and
outputs the community-specific profile and registration URLs, falling back to
the unified portal `veupathdb` (`veupathdb.org`).

### Logging out
To delete the stored token:

    uv run scripts/wdk.py logout

## How auth actually works (distilled from pathfinder's WDK rules)

- The token travels as both a COOKIE: `Cookie: Authorization=<token>` (honored
  by Tomcat for `/users/…` strategy paths) and an `Authorization: Bearer <token>`
  header (required by `POST /record-types/…/records`). Tomcat honors the FIRST
  cookie pair if duplicates are sent — the client sends exactly one cookie pair.
- An uncredentialed request is NOT rejected: WDK mints a fresh guest user per
  request. Guests get 401s on `/users/…` programmatic paths (VEuPathDB policy
  since 2026-08-19) and results that silently belong to nobody. Always verify
  with `whoami` first; the client refuses guest tokens for user-scoped calls.
- `GET /users/current` → `{"id": <int>, "isGuest": bool, "email": …}`. The
  client resolves the numeric id ONCE and uses it in every `/users/{uid}/…`
  path (the `current` alias is only ever used for that one resolution call —
  concrete ids make ownership errors loud 403s instead of silent misfires).
- Logout does NOT invalidate a bearer token; treat tokens as long-lived
  secrets. Never print or commit them.

## Transport quirks the client handles for you

- Retries ×3 (exponential backoff) on timeouts, connect errors, 5xx.
- A 2xx body of `{"status": "accepted", "message": "WDK-DELAYED-RESULT"}` means
  "result not ready" and is retried like a failure.
- Step/strategy/temporary-result CREATION is never retried (a proxy 502 after
  a committed create would otherwise duplicate objects).
- 422 = well-formed request, semantically invalid values; the WDK message is
  surfaced verbatim — read it, it names the offending parameter.
- Timeouts: 30 s per site; 120 s for the veupathdb.org portal.
