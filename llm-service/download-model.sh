#!/bin/sh
set -eu

service_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
models_dir=${1:-"$service_dir/models"}
filename=Qwen3.5-4B-Q4_K_M.gguf
revision=e87f176479d0855a907a41277aca2f8ee7a09523
checksum=$(cut -d ' ' -f 1 "$service_dir/models.sha256")

mkdir -p -- "$models_dir"
cd -- "$models_dir"

verify() {
    if command -v sha256sum >/dev/null 2>&1; then
        printf '%s  %s\n' "$checksum" "$1" | sha256sum -c -
    else
        printf '%s  %s\n' "$checksum" "$1" | shasum -a 256 -c -
    fi
}

if [ -f "$filename" ]; then
    verify "$filename"
    exit
fi

partial="$filename.part"
curl --fail --location --retry 3 --retry-all-errors --continue-at - --output "$partial" \
    "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/$revision/$filename?download=true"
if ! verify "$partial"; then
    printf '%s\n' "Downloaded file did not match. Remove $partial before retrying." >&2
    exit 1
fi
mv -- "$partial" "$filename"
