#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
IMAGE_NAME=${1:-pr-reviewer-mcp:latest}

docker build --tag "$IMAGE_NAME" --file "$SCRIPT_DIR/Dockerfile" "$SCRIPT_DIR"