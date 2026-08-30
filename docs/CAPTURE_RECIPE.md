# Capture Recipe — grabbing the live LinkedIn Voyager API

This is the highest-value 15 minutes of the whole project. Doing it yourself, from a
logged-in browser on a **residential IP**, gives us two things no library and no
desk-research can:

1. The **exact current endpoints + `queryId` hashes** the LinkedIn web app is using
   *today* (these rotate, so trusting a blog post or an old library is how you ship a
   broken scraper).
2. **Real response payloads** we sanitize into test fixtures, so our parser is proven
   against real data and the grader can run the tests with no cookie of their own.

> ⚠️ **Account safety.** Capturing by hand (a handful of requests) is low risk. What
> gets accounts restricted is an automated server hammering endpoints. So: capture with
> whatever account you like, but for the **deployed** service use a **throwaway
> account's** cookie. Keep your real account clean.

---

## Part A — Copy your session cookies (2 min)

1. In Chrome/Firefox, log into <https://www.linkedin.com> and load your own profile.
2. Open **DevTools** (`F12` or `Cmd/Ctrl+Shift+I`).
3. Go to **Application** (Chrome) / **Storage** (Firefox) → **Cookies** →
   `https://www.linkedin.com`.
4. Copy the **Value** of these two cookies:
   - `li_at`  → a long opaque string.
   - `JSESSIONID` → looks like `"ajax:1234567890123456789"` (**keep the quotes**).
5. Paste them into a local `.env` file (copy `.env.example` first). **Never commit this.**

```bash
cp .env.example .env
# then edit .env:
#   LINKEDIN_LI_AT=AQEDAT...      (no quotes)
#   LINKEDIN_JSESSIONID="ajax:1234567890123456789"   (keep the quotes)
```

The CSRF token our client sends is just the `JSESSIONID` value with the quotes stripped
— the app does that for you.

---

## Part B — Capture the live Voyager requests (8 min)

We want to see exactly which endpoints hydrate a profile page and grab their `queryId`s.

1. In DevTools open the **Network** tab. Tick **Preserve log**. In the filter box type
   `voyager`.
2. Now open a **public profile** in the same tab, e.g. `https://www.linkedin.com/in/williamhgates/`.
   Scroll the whole page (experience, education, skills, licenses, languages) so every
   lazy-loaded section fires its request.
3. You'll see requests to:
   - `…/voyager/api/graphql?…queryId=voyagerIdentityDash…` — the modern calls.
   - possibly `…/voyager/api/identity/…` — the older REST calls.
4. For the ones that clearly carry profile data (click a row → **Preview** to check),
   capture **both** of these for me:
   - **The request:** right-click the row → **Copy → Copy as cURL (bash)**.
   - **The response:** click the row → **Response** tab → select-all → copy, OR
     right-click → **Copy → Copy response**.
5. Note especially, for each GraphQL call, the **`queryId`** value and the shape of the
   **`variables=(...)`** parameter.

Paste the cURL commands and response JSON back to me in chat (or drop the JSON into a
`captures/` folder — it's git-ignored). I'll turn them into:
- the endpoint/`queryId` registry the client uses, and
- sanitized fixtures under `tests/fixtures/` for the parser tests.

> Tip: the single most useful capture is **one full profile's GraphQL responses** for a
> profile you're allowed to view. That alone lets me build the parser end-to-end.

---

## Part C — (Optional) Automated capture once cookies are set

After `.env` is filled, you can also let the client dump raw payloads:

```bash
python -m scripts.capture "https://www.linkedin.com/in/williamhgates/"
```

This writes raw responses to `captures/` (git-ignored) and a **sanitized** copy to
`tests/fixtures/`. If it returns HTTP `999` or a login redirect, that's LinkedIn
blocking this machine's IP — expected from a datacenter; do Part B from your browser
instead, which uses your residential IP.

---

## While you're in there — the high-value things to confirm

The recon pass flagged a handful of values that rotate or couldn't be verified from
research alone. If you can note these from the same session, it saves a round-trip:

- [ ] **Does `.../profileView` still work?** In the Network tab, does a request to
      `identity/profiles/<id>/profileView` return **200** or **410 Gone**? (Decides
      whether the legacy path stays as a fallback.)
- [ ] **Current `queryId`s.** Copy the full `queryId=voyagerIdentityDash….<hash>` from the
      GraphQL requests (profile, cards, components).
- [ ] **The Dash profile request**, if you see one — the exact
      `identity/dash/profiles?q=…` finder and its `decorationId=…-NN` version.
- [ ] **`sectionType` tokens** on any `profileComponents` request (e.g. `experience`,
      `education`, `skills` — exact spelling/casing).
- [ ] **One full profile response body** (the most important item) — with that I can map
      the real per-element field names (`degreeName`, `fieldOfStudy`, `authority`,
      date shapes, skill endorsement counts, open-to-work) instead of guessing.

Don't worry about getting all of these — **one full profile's response JSON covers most of
it.** The rest are nice-to-haves.

## What I need back from you to finish the build

- ✅ `.env` filled locally (you keep it; don't paste `li_at` into chat if you'd rather
  not — the fixtures are enough for me to build the parser).
- ✅ At least **one profile's** GraphQL/REST **response JSON** (Part B step 4) — ideally
  your own profile plus one other, so we cover fields that need a connection.
- ✅ The **`queryId` values** you saw (Part B step 5).

With those I wire the real endpoints, finish the parser, and we validate live.
