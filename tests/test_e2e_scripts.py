import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "e2e" / "p03.sh"


def first_docker_call(tmp_path: Path, env: dict[str, str]) -> str:
    log = tmp_path / "docker.log"
    docker = tmp_path / "docker"
    docker.write_text(f'#!/bin/sh\necho "$COMPOSE_PROJECT_NAME $*" >> {log}\nexit 1\n')
    docker.chmod(0o755)
    path = f"{tmp_path}:{os.environ['PATH']}"
    subprocess.run(["bash", str(SCRIPT)], env={**env, "PATH": path}, check=False)
    return log.read_text().splitlines()[0]


def test_p03_e2e_uses_its_own_compose_project_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("COMPOSE_PROJECT_NAME", raising=False)

    assert first_docker_call(tmp_path, dict(os.environ)) == (
        "fda-e2e-p03 compose down -v --remove-orphans"
    )


def test_p03_e2e_keeps_a_caller_compose_project(tmp_path: Path) -> None:
    env = {**os.environ, "COMPOSE_PROJECT_NAME": "p03"}

    assert first_docker_call(tmp_path, env) == "p03 compose down -v --remove-orphans"
