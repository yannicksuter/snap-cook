#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run the built image the two ways it is deployed, and check it.

1. On its own, as on Unraid: one container, its own Postgres, one /data volume.
2. Split, as in docker-compose.yml: Postgres, then `web` and `worker` from the
   image sharing one /data volume.

Both on a temporary Docker network with no route out. An image that needs the
internet to start fails here instead of at boot on the server.

    python3 scripts/test-container.py IMAGE COMMIT

CI runs it on every image before publishing it (.github/workflows/ci.yml).
Standard library only, so it needs nothing but Docker and a Python 3.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import uuid

# The database image docker-compose.yml and docs/install.md use.
POSTGRES_IMAGE = "postgres:17-alpine"
DB_CREDENTIALS = (
    "-e", "POSTGRES_DB=snapcook",
    "-e", "POSTGRES_USER=snapcook",
    "-e", "POSTGRES_PASSWORD=container-test-only",
)  # fmt: skip
CORPUS_SIZE = 6

# Runs inside the web container: the network is internal, so the host cannot
# reach a published port. Prints [status, Location, body] as JSON.
_FETCH = """
import json, sys, urllib.error, urllib.request

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None

try:
    response = urllib.request.build_opener(_NoRedirect).open(
        "http://127.0.0.1:8931" + sys.argv[1], timeout=5
    )
except urllib.error.HTTPError as error:
    response = error
location = response.headers.get("Location", "")
print(json.dumps([response.getcode(), location, response.read().decode()]))
"""


def docker(*args: str) -> str:
    return subprocess.check_output(
        ["docker", *args],
        text=True,
        # `docker logs` replays the container's stderr on its own stderr.
        stderr=subprocess.STDOUT if args[0] == "logs" else None,
    ).strip()


def state(container: str) -> dict:
    return json.loads(docker("inspect", container))[0]["State"]


def wait_for(condition, what: str, seconds: int = 90) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.5)
    raise AssertionError(f"{what} within {seconds} seconds")


def wait_healthy(container: str) -> None:
    def healthy() -> bool:
        current = state(container)
        if not current["Running"]:
            raise AssertionError(f"{container[:12]} exited before it was healthy")
        return current.get("Health", {}).get("Status") == "healthy"

    wait_for(healthy, f"{container[:12]} did not become healthy")


def wait_exit(container: str) -> int:
    return int(docker("wait", container))


def stop(container: str) -> int:
    docker("stop", "--timeout", "30", container)
    return state(container)["ExitCode"]


def fetch(container: str, path: str) -> tuple[int, str, str]:
    status, location, body = json.loads(docker("exec", container, "python", "-c", _FETCH, path))
    return status, location, body


def pg_ready(db: str) -> bool:
    # Over TCP: during initialisation Postgres answers on its socket only.
    probe = ["docker", "exec", db, "pg_isready", "-q", "-h", "127.0.0.1", "-U", "snapcook"]
    return subprocess.run(probe, check=False).returncode == 0


def sql(db: str, query: str) -> str:
    return docker(
        "exec", db, "psql", "-U", "snapcook", "-d", "snapcook", "-At",
        "-v", "ON_ERROR_STOP=1", "-c", query,
    )  # fmt: skip


def _count_recipes(container: str) -> str:
    output = docker(
        "exec", container, "python", "manage.py", "shell", "-c",
        "from catalog.models import Recipe; print(Recipe.objects.count())",
    )  # fmt: skip
    return output.splitlines()[-1]


def all_in_one(image: str, commit: str) -> None:
    """The default: one container, no POSTGRES_HOST, everything in /data."""
    name = "snapcook-aio-" + uuid.uuid4().hex[:12]
    data, network = name + "-data", name
    docker("network", "create", "--internal", network)
    docker("volume", "create", data)
    container = ""
    try:
        container = docker(
            "run", "-d", "--network", network,
            "--health-interval=1s", "--health-start-period=0s",
            "--mount", f"type=volume,source={data},target=/data",
            "-e", "DJANGO_SECRET_KEY=container-test-only-secret-key",
            "-e", "DJANGO_ALLOWED_HOSTS=cook.example.com,127.0.0.1",
            image,
        )  # fmt: skip
        wait_healthy(container)
        status, _, body = fetch(container, "/up")
        assert status == 200 and json.loads(body) == {"status": "ok", "commit": commit}, body
        wait_for(
            lambda: re.search(r"Q Cluster \S+ \[snapcook\] running\.", docker("logs", container)),
            "The worker's cluster did not start",
        )
        print("One container runs its own database, web and worker, with no internet.", flush=True)

        port = docker(
            "exec", container, "python", "-c",
            "import socket; print(socket.socket().connect_ex(('127.0.0.1', 5432)))",
        )  # fmt: skip
        assert port != "0", "the embedded database must not listen on TCP"
        print("Its database listens on a socket only, not on a port.", flush=True)

        docker("exec", container, "python", "manage.py", "seed_corpus")
        assert _count_recipes(container) == str(CORPUS_SIZE)
        assert stop(container) == 0
        assert "database system is shut down" in docker("logs", container)
        docker("start", container)
        wait_healthy(container)
        assert _count_recipes(container) == str(CORPUS_SIZE)
        print("Recipes and database survive a restart, and it stops cleanly.", flush=True)
        assert stop(container) == 0
    except Exception:
        if container:
            print(f"--- logs of {container[:12]}", flush=True)
            subprocess.run(["docker", "logs", "--tail", "80", container], check=False)
        raise
    finally:
        if container:
            subprocess.run(
                ["docker", "rm", "-fv", container], check=False, stdout=subprocess.DEVNULL
            )
        docker("volume", "rm", data)
        docker("network", "rm", network)


def main() -> None:
    image, commit = sys.argv[1:]
    all_in_one(image, commit)
    name = "snapcook-test-" + uuid.uuid4().hex[:12]
    data, pgdata, network = name + "-data", name + "-pgdata", name
    containers: list[str] = []

    docker("network", "create", "--internal", network)
    docker("volume", "create", data)
    docker("volume", "create", pgdata)

    try:
        db = docker(
            "run", "-d", "--network", network,
            "--mount", f"type=volume,source={pgdata},target=/var/lib/postgresql/data",
            *DB_CREDENTIALS, POSTGRES_IMAGE,
        )  # fmt: skip
        containers.append(db)
        wait_for(lambda: pg_ready(db), "Postgres did not start")
        # By address, not by name: Docker's name resolution needs NAT kernel
        # modules a host can lack (after a kernel upgrade without a reboot,
        # say), and resolving names is Docker's job rather than the image's.
        networks = json.loads(docker("inspect", db))[0]["NetworkSettings"]["Networks"]
        db_host = networks[network]["IPAddress"]

        def start(*args: str) -> str:
            container = docker(
                "run", "-d", "--network", network,
                "--health-interval=1s", "--health-start-period=0s",
                "--mount", f"type=volume,source={data},target=/data",
                *DB_CREDENTIALS,
                "-e", f"POSTGRES_HOST={db_host}",
                "-e", "DJANGO_SECRET_KEY=container-test-only-secret-key",
                "-e", "DJANGO_ALLOWED_HOSTS=cook.example.com,127.0.0.1",
                *args,
            )  # fmt: skip
            containers.append(container)
            return container

        container = start("-e", "POSTGRES_PASSWORD=incorrect-password", image, "web")
        assert wait_exit(container) != 0
        print("web refuses to start with the wrong database password.", flush=True)

        web = start(image, "web")
        wait_healthy(web)
        status, _, body = fetch(web, "/up")
        assert status == 200 and json.loads(body) == {"status": "ok", "commit": commit}, body
        status, _, _ = fetch(web, "/")
        assert status == 200, status  # anyone reads
        status, location, _ = fetch(web, "/add/")
        assert status == 302 and location.startswith("/accounts/login/"), location
        status, _, _ = fetch(web, "/static/account/js/account.js")
        assert status == 200, status
        debug = docker(
            "exec", web, "python", "manage.py", "shell", "-c",
            "from django.conf import settings; print(settings.DEBUG)",
        )  # fmt: skip
        assert debug.splitlines()[-1] == "False", debug
        print(
            "web migrates, serves /up with the commit, the open recipe list, static "
            "files and the sign-in redirect, with DEBUG off by default, and no internet.",
            flush=True,
        )

        worker = start(image, "worker")
        wait_healthy(worker)
        wait_for(
            lambda: re.search(r"Q Cluster \S+ \[snapcook\] running\.", docker("logs", worker)),
            "The worker's cluster did not start",
        )
        print("The worker's cluster runs.", flush=True)

        # A command in place of a role runs once, as `docker compose run --rm
        # web python manage.py migrate` does in the restore runbook.
        once = start(image, "python", "manage.py", "migrate", "--check")
        assert wait_exit(once) == 0, docker("logs", once)
        print("A one-off command runs in place of a role.", flush=True)

        # The runbooks' commands, as written, in a running container.
        docker("exec", web, "python", "manage.py", "seed_corpus")
        assert sql(db, "SELECT count(*) FROM catalog_recipe") == str(CORPUS_SIZE)
        print("seed_corpus writes the store and projects it.", flush=True)

        assert stop(web) == 0
        assert "Shutting down: Master" in docker("logs", web)
        docker("rm", "-v", web)
        containers.remove(web)
        web = start(image, "web")
        wait_healthy(web)
        docker("exec", worker, "python", "manage.py", "reindex", "--full", "--yes")
        assert sql(db, "SELECT count(*) FROM catalog_recipe") == str(CORPUS_SIZE)
        print(
            "The store survives replacing web, and the worker reindexes it from the same /data.",
            flush=True,
        )

        assert stop(web) == 0
        assert stop(worker) == 0
        assert "has stopped" in docker("logs", worker)
        print("web and worker stop cleanly.", flush=True)
    except Exception:
        for container in containers:
            print(f"--- logs of {container[:12]}", flush=True)
            subprocess.run(["docker", "logs", "--tail", "60", container], check=False)
        raise
    finally:
        for container in containers:
            subprocess.run(
                ["docker", "rm", "-fv", container], check=False, stdout=subprocess.DEVNULL
            )
        docker("volume", "rm", data, pgdata)
        docker("network", "rm", network)


if __name__ == "__main__":
    main()
