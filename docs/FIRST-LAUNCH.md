# First Launch Sequence

This is deliberately staged. The repository contains the full groundwork, but
we do not expose every capability before its credentials and policy are ready.

## 1. Prepare host paths

```bash
cd /srv/ix/llm-services
cp .env.example .env
printf 'HERMES_UID=%s\nHERMES_GID=%s\n' "$(id -u)" "$(id -g)"
./scripts/bootstrap-runtime.sh
```

Edit `.env` so `HERMES_UID` and `HERMES_GID` match the `lightweight` account.

## 2. Build the derived Hermes image

```bash
docker compose build hermes
```

## 3. Run Hermes setup interactively

Use the persistent runtime volume:

```bash
docker compose run --rm hermes setup
```

Select the OpenAI Codex provider and complete its device-code OAuth flow.

Do not launch the unattended gateway until its initial configuration is valid.

## 4. Establish Leto identity

Hermes' live SOUL file is bind-mounted directly from:

```text
/srv/ix/golden-path/agents/leto/SOUL.md
```

Leto's historical/role/personality sources are available under:

```text
/workspace/golden-path/agents/leto/
```

Set Hermes' terminal working directory to that path so Leto begins in his own
institutional workspace.

## 5. Configure Discord and voice

Place Discord secrets in Hermes' private runtime `.env`, not this repository.

Initial recommendations:

- Discord as canonical conversational surface
- local faster-whisper STT
- Edge TTS
- voice replies when the user speaks; text when the user types

## 6. Configure dashboard authentication

The dashboard binds non-loopback inside Docker and therefore requires an auth
provider. Configure Hermes' bundled basic-auth provider or another supported
provider in the private Hermes runtime before proxying it.

Only after the auth gate is verified should Arrakis/Caddy expose the dashboard.

## 7. Enable the API intentionally

For future Kami/custom clients, configure these in Hermes' private runtime:

```text
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0
API_SERVER_KEY=<strong secret>
```

Keep port 8642 LAN/VPN scoped initially.

## 8. Start Hermes

```bash
docker compose up -d hermes
docker compose logs -f hermes
```

## 9. Verify Leto's hands from inside the container

The relevant test is non-interactive SSH:

```bash
docker exec hermes ssh -o BatchMode=yes arrakis hostname
docker exec hermes ssh -o BatchMode=yes midway hostname
docker exec hermes ssh -o BatchMode=yes heighliner hostname
```

Do not proceed to broader autonomous operations until these behave predictably.

## 10. Optional local inference later

Nothing launches by default.

When ready to experiment:

```bash
docker compose --profile local-inference up -d ollama
```
