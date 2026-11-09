#!/bin/sh
set -eu

model=qwen3.5:4b-q4_K_M
ready=/tmp/qwen-model-ready
rm -f "$ready"
if ! (cd /models && sha256sum -c /bootstrap/models.sha256); then
    printf '%s\n' "Qwen weights missing or invalid. Run sh llm-service/download-model.sh on the host." >&2
    exit 1
fi

ollama serve &
server=$!
cleanup() {
    rm -f "$ready"
    kill "$server" 2>/dev/null || true
    wait "$server" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

attempt=0
until OLLAMA_HOST=http://127.0.0.1:11434 ollama list >/dev/null 2>&1; do
    if ! kill -0 "$server" 2>/dev/null || [ "$attempt" -ge 60 ]; then
        printf '%s\n' "Ollama API did not start." >&2
        exit 1
    fi
    attempt=$((attempt + 1))
    sleep 1
done
OLLAMA_HOST=http://127.0.0.1:11434 ollama create "$model" -f /bootstrap/Modelfile
touch "$ready"
wait "$server"
