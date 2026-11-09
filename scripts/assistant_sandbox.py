"""Run on a dedicated internal Linux host with Docker and the gVisor runsc runtime."""

import os
import selectors
import shutil
import subprocess
import tempfile
import time
from hmac import compare_digest
from threading import BoundedSemaphore
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.assistant.schema.sandbox import MAX_INPUT, MAX_OUTPUT, ExecutionRequest, ExecutionResult

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
slots = BoundedSemaphore(2)
DOCKER = ["docker", "--host=unix:///var/run/docker.sock"]

# Fixed bootstrap. The generated code and source tables travel via stdin, never argv or mounts.
BOOTSTRAP = """
import json, sys

request = json.load(sys.stdin)
namespace = {"__name__": "assistant_transform"}
exec(compile(request["code"], "<assistant>", "exec"), namespace)
result = namespace["transform"](request["sources"], request["steps"], request["outputs"])
json.dump(result, sys.stdout, ensure_ascii=False, allow_nan=False)
"""


def docker_command(name, image):
    return [
        *DOCKER,
        "run",
        "--rm",
        "--interactive",
        "--name",
        name,
        "--pull=never",
        "--runtime=runsc",
        "--network=none",
        "--read-only",
        "--user=65532:65532",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=64",
        "--cpus=2",
        "--memory=1g",
        "--memory-swap=1g",
        "--ulimit=nofile=128:128",
        "--log-driver=none",
        "--entrypoint=python3",
        image,
        "-I",
        "-B",
        "-c",
        BOOTSTRAP,
    ]


def run_in_sandbox(payload, timeout):
    # Docker CLI proxy settings can inject environment variables into a container.
    # Use an empty client config and a dedicated local socket.
    with tempfile.TemporaryDirectory(prefix="tallyv-docker-") as config:
        docker_env = {"PATH": os.environ.get("PATH", os.defpath), "DOCKER_CONFIG": config}
        return run_container(payload, timeout, docker_env)


def run_container(payload, timeout, docker_env):
    image = os.environ.get("ASSISTANT_SANDBOX_IMAGE", "python:3.11-slim")
    if not shutil.which("docker"):
        raise HTTPException(503, "Sandbox runtime unavailable")
    name = "tallyv-assistant-" + uuid4().hex
    deadline = time.monotonic() + timeout
    proc = None
    try:
        with tempfile.TemporaryFile() as source:
            source.write(payload)
            source.seek(0)
            proc = subprocess.Popen(
                docker_command(name, image),
                stdin=source,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=docker_env,
            )
            with proc.stdout, selectors.DefaultSelector() as reader:
                reader.register(proc.stdout, selectors.EVENT_READ)
                output = bytearray()
                while (remaining := deadline - time.monotonic()) > 0 and reader.select(remaining):
                    chunk = os.read(proc.stdout.fileno(), 64 * 1024)
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > MAX_OUTPUT:
                        return ExecutionResult(error="OUTPUT_LIMIT")
                exit_code = proc.wait(timeout=max(0, deadline - time.monotonic()))
            if exit_code in {125, 126, 127}:
                raise HTTPException(503, "Sandbox runtime unavailable")
            if exit_code != 0:
                return ExecutionResult(error="SCRIPT_ERROR")
            try:
                # Wrap the only permitted artifact. Never return stdout/stderr as diagnostic strings.
                return ExecutionResult.model_validate_json(b'{"result":' + output + b"}")
            except ValidationError:
                return ExecutionResult(error="INVALID_OUTPUT")
    except subprocess.TimeoutExpired:
        return ExecutionResult(error="TIME_LIMIT")
    except OSError as error:
        raise HTTPException(503, "Sandbox runtime unavailable") from error
    finally:
        if proc is not None and proc.poll() is None:
            try:
                subprocess.run(
                    [*DOCKER, "rm", "-f", name],
                    timeout=8,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=docker_env,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()


@app.post("/execute", response_model=ExecutionResult)
async def execute(request: Request):
    token = os.environ.get("ASSISTANT_SANDBOX_TOKEN", "")
    auth = request.headers.get("Authorization", "")
    if len(token) < 32 or not compare_digest(auth.encode(), f"Bearer {token}".encode()):
        raise HTTPException(401, "Unauthorized")
    if not slots.acquire(blocking=False):
        raise HTTPException(503, "Sandbox busy")
    try:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_INPUT:
                raise HTTPException(413, "Sandbox input exceeds limit")
        try:
            parsed = ExecutionRequest.model_validate_json(body)
        except ValidationError as error:
            raise HTTPException(422, "Invalid sandbox request") from error
        return await run_in_threadpool(run_in_sandbox, body, parsed.timeout)
    finally:
        slots.release()
