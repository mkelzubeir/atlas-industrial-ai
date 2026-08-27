# Deployment

Getting Atlas off your laptop and onto a URL you can send someone.

The end state: FastAPI on Fly.io, Next.js on Vercel, and the ElevenLabs agent
pointed at a hostname that does not change. No tunnel, no terminal windows that
have to stay open.

---

## Why a tunnel is not the answer

`cloudflared tunnel --url` is fine for a first run-through, and it is what the
README uses to get you talking to the agent in ten minutes. It is not a
deployment:

- The hostname is random and **changes on every restart**, and the agent's seven
  tool definitions have it baked in — so a new URL means re-running
  `scripts/provision_agent.py` every time.
- It only works while your machine is awake with two processes running.
- Close the laptop and the demo dies mid-sentence.

Hosting the backend fixes all three at once.

---

## 1. Backend → Fly.io

`backend/Dockerfile` and `backend/fly.toml` are ready to go.

```bash
cd backend
fly auth login
fly launch --no-deploy          # claims an app name
```

> **`fly launch` overwrites `Dockerfile` and `fly.toml`.** It detects a Python
> project and writes its own versions over the ones in this repo, silently. The
> generated Dockerfile does not work here, and the generated `fly.toml` drops the
> always-warm settings. Restore them immediately afterwards, keeping the app name
> Fly assigned:
>
> ```bash
> APP=$(grep '^app = ' fly.toml | cut -d'"' -f2)   # the name Fly just created
> git checkout Dockerfile fly.toml
> sed -i '' "s/^app = .*/app = \"$APP\"/" fly.toml
> ```
>
> Fly app names are globally unique, so yours will be something like
> `backend-damp-coastline-2707` rather than `atlas-industrial-ai`. Whatever it is,
> that hostname is what goes in the provisioner and in Vercel.

Set the shared secret as a Fly secret rather than an env var — secrets are
encrypted at rest and never appear in `fly config show`:

```bash
fly secrets set ATLAS_API_KEY="$(grep ATLAS_API_KEY .env | cut -d= -f2-)"
fly deploy
```

Confirm it is alive:

```bash
curl https://atlas-industrial-ai.fly.dev/health
# {"status":"ok","service":"atlas-backend","demo_mode":true}
```

### Two choices baked into the config

**One machine stays warm.** `auto_stop_machines = false` with
`min_machines_running = 1`. Scale-to-zero looks appealing on a demo, but a cold
start takes longer than the agent's 15–20s tool timeout — so the first question
of every demo would be answered with *"I can't reach that system right now."*
That is precisely the failure this project exists to avoid, and it is not worth
saving pennies to reintroduce it.

**The disk is ephemeral, and that is deliberate.** `ATLAS_SEED_ON_STARTUP=true`
rebuilds the synthetic data when the database is empty, so every restart gives a
clean, known demo state. Seeding is skipped when data already exists, so a
restart mid-demo will not wipe a change you just made on a call.

If you would rather have the data survive restarts, attach a volume:

```bash
fly volumes create atlas_data --size 1
```

and add to `fly.toml`:

```toml
[[mounts]]
  source = "atlas_data"
  destination = "/srv/data"
```

Not required. `POST /api/demo/reset` gets you back to a known state either way.

---

## 2. Point the agent at it

The agent's tools still hold the old tunnel hostname. Re-provision once:

```bash
cd ..
export ELEVENLABS_API_KEY=$(grep ELEVENLABS_API_KEY frontend/.env.local | cut -d= -f2-)
export ATLAS_API_KEY=$(grep ATLAS_API_KEY backend/.env | cut -d= -f2-)
export ATLAS_PUBLIC_BASE_URL=https://atlas-industrial-ai.fly.dev

python3 scripts/provision_agent.py
```

Idempotent — it updates the seven existing tools in place. The agent id does not
change, so nothing downstream needs touching.

**This is the last time you run this**, unless you change the prompt or a tool.

---

## 3. Frontend → Vercel

Import the repo, then:

**Settings → Build and Deployment → Root Directory:** `frontend`

This is a monorepo; there is no `package.json` at the root. Without it the build
finds nothing and every route 404s. Turn off "Include files outside the root
directory" while you are there — the frontend has no dependencies outside its
folder.

**Settings → Environments → Production:**

| Key | Type | Value |
|---|---|---|
| `NEXT_PUBLIC_ELEVENLABS_AGENT_ID` | Config | `agent_...` |
| `ATLAS_BACKEND_URL` | Config | `https://atlas-industrial-ai.fly.dev` |
| `ELEVENLABS_API_KEY` | Secret | `sk_...` |
| `ATLAS_API_KEY` | Secret | same value as the Fly secret |

`NEXT_PUBLIC_ELEVENLABS_AGENT_ID` **must be Config, not Secret.** Vercel rejects
sensitive variables carrying that prefix, because the prefix means the value is
compiled into the browser bundle — and a rejected variable fails the whole batch,
which is reported as "no environment variables were created".

Then redeploy. Environment variables are read at build time, so an existing
deployment will not pick them up.

---

## 4. Verify

```bash
curl https://atlas-industrial-ai.fly.dev/health
```

Then open the Vercel URL and:

1. **Browse demo data** — proves the frontend can reach the backend through its
   server-side proxy.
2. **Start call**, ask about PO 1847 — proves ElevenLabs can reach the backend
   from *its* servers, which is a different network path.
3. **Developer View** — confirms tool calls with their arguments are landing.

If (1) works and (2) does not, the agent's tools are still pointed at the old
hostname: re-run the provisioner.

---

## Before you share the link

Anyone with the URL can talk to the agent and spend your ElevenLabs credits, and
the demo endpoints let them reset the database while you are recording.

Options, cheapest first:

- **Leave it open.** Fine for a link you send to two people this week.
- **Vercel Deployment Protection** (Settings → Deployment Protection) puts
  password or SSO in front of the whole site. One switch, no code.
- **Turn the demo endpoints off** with `fly secrets set ATLAS_DEMO_MODE=false`.
  This also disables the data browser and the reset button, so the demo loses
  some of what makes it legible. Reads and writes still work.

Whatever you choose, `POST /api/demo/reset` before recording gives you a known
starting state.

---

## Status of this config

The image has **not been built from this repository** — no Docker daemon was
available where it was authored. The first real deploy attempt found a genuine
bug in it, since fixed: `pip install .` ran before `app/` and `seed/` were
copied, and `pyproject.toml` declares them as packages, so setuptools failed
with `package directory 'app' does not exist`. Dependencies-first layer caching
does not work when the project installs itself; the source is now copied first.

Verified since:

- the install step, reproduced outside Docker in a clean virtualenv against a
  directory containing only what the image copies — `pip install .` succeeds and
  `app` and `seed` import from the installed package
- booting against an empty database seeds it (`startup.seeded`, 31 products)
- booting again against a populated one skips seeding rather than wiping it
  (`startup.seed_skipped`)
