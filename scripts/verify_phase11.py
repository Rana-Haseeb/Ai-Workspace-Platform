"""Phase 11 gate: the deployed thing actually works, over HTTP, as a stranger would use it.

    python scripts/verify_phase11.py                                   # local container
    python scripts/verify_phase11.py --url https://<space>.hf.space    # the live deployment

Every other gate builds the app in-process with a TestClient. This one talks to a running server
over the network and knows nothing about the code, because the failures it exists to catch only
exist in a deployment: a frontend that 404s on refresh, an API that lost its routes behind a
catch-all, a database URL the driver cannot parse, secrets that were never set in the Space.

The journey is the one the challenge asks for — register, make a workspace, upload a document,
get a cited answer, and have memory recall in a **second session** with a fresh login.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASSWORD = "correct-horse-battery"
failures: list[str] = []

DOCUMENT = """# Deployment Runbook

The staging environment is rebuilt every night at 02:00 UTC.

Rollback is a single command and takes approximately 4 minutes. The on-call engineer for
infrastructure is Priya Raman, reachable through the incident channel.

Database migrations run before the new image is promoted, never after.
"""

MEMORY_STATEMENT = (
    "Worth remembering about me: I am a platform engineer, I prefer British English, and I "
    "want answers kept to two sentences unless I ask for more."
)


def safe(text) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"   {'OK  ' if ok else 'FAIL'} {label}" + (f"  [{safe(detail)}]" if detail else ""))
    if not ok:
        failures.append(label)


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.token: str | None = None

    def request(self, method: str, path: str, payload=None, raw=None, content_type=None,
                timeout: int = 120):
        url = path if path.startswith("http") else f"{self.base}{path}"
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = None
        if raw is not None:
            data, headers["Content-Type"] = raw, content_type
        elif payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
                text = body.decode("utf-8", errors="replace")
                try:
                    return response.status, json.loads(text)
                except json.JSONDecodeError:
                    return response.status, text
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8", errors="replace")[:200]
        except Exception as error:  # noqa: BLE001 — network, DNS, TLS
            return 0, safe(error)[:200]

    def upload(self, workspace: int, filename: str, text: str):
        boundary = "----phase11verify"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: text/markdown\r\n\r\n"
        ).encode() + text.encode() + f"\r\n--{boundary}--\r\n".encode()
        return self.request("POST", f"/api/workspaces/{workspace}/documents", raw=body,
                            content_type=f"multipart/form-data; boundary={boundary}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:7860",
                        help="base URL of the running deployment")
    args = parser.parse_args()

    print(f"\nPhase 11 verification - {args.url}\n")
    client = Client(args.url)

    # ------------------------------------------------------------------- 1. it is alive
    print("1. The deployment answers")
    status, body = client.request("GET", "/api/health", timeout=90)
    check("health probe", status == 200, str(body)[:80])
    if status != 200:
        return _finish()
    check("running on PostgreSQL, not SQLite", body.get("database") == "postgresql",
          str(body.get("database")))
    check("at least one provider configured", body.get("providers_configured", 0) >= 1,
          f"{body.get('providers_configured')} configured")

    # --------------------------------------------------------------- 2. the SPA is served
    print("\n2. The frontend is served from the same origin")
    status, page = client.request("GET", "/")
    check("root returns the app shell", status == 200 and 'id="root"' in str(page))

    # The failure this catches: a plain static mount 404s on any client-side route, so the app
    # looks fine until somebody refreshes or shares a link.
    status, page = client.request("GET", "/w/1/dashboard")
    check("a client-side route survives a refresh", status == 200 and 'id="root"' in str(page),
          f"status {status}")

    status, _ = client.request("GET", "/api/definitely-not-a-route")
    check("an unknown API path still 404s", status == 404, f"status {status}")

    # ------------------------------------------------------------------ 3. register
    print("\n3. Register and sign in")
    email = f"gate-{uuid.uuid4().hex[:10]}@example.com"
    status, _ = client.request("POST", "/api/auth/register",
                               {"name": "Phase 11", "email": email, "password": PASSWORD})
    check("a new account can be created", status in (200, 201), f"status {status}")

    status, body = client.request("POST", "/api/auth/login",
                                  {"email": email, "password": PASSWORD})
    check("sign in returns a token", status == 200 and "access_token" in str(body))
    if status != 200:
        return _finish()
    client.token = body["access_token"]

    # ----------------------------------------------------------------- 4. workspace
    print("\n4. Create a workspace")
    status, workspace = client.request("POST", "/api/workspaces",
                                       {"name": "Deployment check",
                                        "description": "Created by the Phase 11 gate."})
    check("workspace created", status == 201, f"status {status}")
    if status != 201:
        return _finish()
    wid = workspace["id"]

    # ------------------------------------------------------------------ 5. document
    print("\n5. Upload a document and get a cited answer")
    status, _ = client.upload(wid, "deployment_runbook.md", DOCUMENT)
    check("upload accepted", status in (200, 201), f"status {status}")

    ready = False
    for _ in range(60):
        _, listed = client.request("GET", f"/api/workspaces/{wid}/documents")
        if listed and all(d["status"] in ("ready", "failed") for d in listed):
            ready = listed[0]["status"] == "ready"
            break
        time.sleep(2)
    check("document ingested", ready)

    status, reply = client.request(
        "POST", f"/api/workspaces/{wid}/conversations", {})
    conversation = reply["id"] if status == 201 else None
    check("conversation created", conversation is not None)

    if conversation:
        status, message = client.request(
            "POST", f"/api/workspaces/{wid}/conversations/{conversation}/messages",
            {"content": "According to the runbook, how long does a rollback take, and who is "
                        "on call for infrastructure?"})
        answer = message["assistant_message"]["content"] if status == 200 else ""
        citations = message["assistant_message"].get("citations", []) if status == 200 else []
        check("the model answered", status == 200 and bool(answer), f"status {status}")
        check("the answer is grounded in the document",
              "4" in answer and "priya" in answer.lower(), answer[:70])
        check("the answer carries a citation", bool(citations),
              citations[0]["filename"] if citations else "none")

    # -------------------------------------------------------- 6. memory across sessions
    print("\n6. Memory survives a second session")
    if conversation:
        client.request("POST", f"/api/workspaces/{wid}/conversations/{conversation}/messages",
                       {"content": MEMORY_STATEMENT})
        time.sleep(3)

    _, memories = client.request("GET", f"/api/workspaces/{wid}/memory")
    check("something was remembered", bool(memories), f"{len(memories or [])} items")

    # A genuinely new session: fresh login, fresh token, brand-new conversation.
    second = Client(args.url)
    status, body = second.request("POST", "/api/auth/login",
                                  {"email": email, "password": PASSWORD})
    check("can sign in again", status == 200)
    if status == 200:
        second.token = body["access_token"]
        status, fresh = second.request("POST", f"/api/workspaces/{wid}/conversations", {})
        if status == 201:
            status, message = second.request(
                "POST", f"/api/workspaces/{wid}/conversations/{fresh['id']}/messages",
                {"content": "What do you know about my job?"})
            answer = message["assistant_message"]["content"] if status == 200 else ""
            used = message["assistant_message"].get("memory_used", []) if status == 200 else []
            check("memory was injected into the new conversation", bool(used),
                  f"{len(used)} memories")
            check("the answer reflects what was remembered",
                  any(word in answer.lower() for word in ("platform", "engineer")), answer[:70])

    # ---------------------------------------------------------------- 7. isolation, live
    print("\n7. Another user cannot reach any of it")
    intruder = Client(args.url)
    other = f"gate-other-{uuid.uuid4().hex[:8]}@example.com"
    intruder.request("POST", "/api/auth/register",
                     {"name": "Other", "email": other, "password": PASSWORD})
    status, body = intruder.request("POST", "/api/auth/login",
                                    {"email": other, "password": PASSWORD})
    if status == 200:
        intruder.token = body["access_token"]
        for label, path in [
            ("workspace", f"/api/workspaces/{wid}"),
            ("documents", f"/api/workspaces/{wid}/documents"),
            ("memory", f"/api/workspaces/{wid}/memory"),
        ]:
            status, _ = intruder.request("GET", path)
            check(f"  {label} refused", status in (403, 404), f"status {status}")

    return _finish()


def _finish() -> int:
    if failures:
        print(f"\nPHASE 11 FAILED - {len(failures)} problem(s):")
        for problem in failures:
            print(f"   - {problem}")
        return 1
    print("\nPHASE 11 PASSED - register, cite, recall and isolate, all over HTTP.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
