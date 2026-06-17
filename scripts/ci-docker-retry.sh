#!/usr/bin/env bash
# Retry docker pulls in CI when Docker Hub is slow or rate-limited.
set -euo pipefail

retry_docker_pull() {
  local image=$1
  local max_attempts=${2:-5}
  local attempt=1

  while [ "$attempt" -le "$max_attempts" ]; do
    echo "Pulling ${image} (attempt ${attempt}/${max_attempts})..."
    if docker pull "$image"; then
      return 0
    fi
    sleep $((attempt * 15))
    attempt=$((attempt + 1))
  done

  echo "Failed to pull ${image} after ${max_attempts} attempts" >&2
  return 1
}

pull_compose_images() {
  if [ "$#" -lt 1 ]; then
    echo "Usage: pull_compose_images <docker compose args...>" >&2
    return 1
  fi

  mapfile -t images < <("$@" config --images 2>/dev/null | sort -u)
  for image in "${images[@]}"; do
    [ -z "$image" ] && continue
    case "$image" in
      finflow-*|*finflow_* ) continue ;;
    esac
    retry_docker_pull "$image"
  done
}

mirror_base_images() {
  retry_docker_pull public.ecr.aws/docker/library/python:3.11-slim-bookworm
  docker image inspect python:3.11-slim-bookworm >/dev/null 2>&1 \
    || docker tag public.ecr.aws/docker/library/python:3.11-slim-bookworm python:3.11-slim-bookworm

  retry_docker_pull public.ecr.aws/docker/library/node:22-alpine
  docker image inspect node:22-alpine >/dev/null 2>&1 \
    || docker tag public.ecr.aws/docker/library/node:22-alpine node:22-alpine

  retry_docker_pull public.ecr.aws/docker/library/nginx:1.27-alpine
  docker image inspect nginx:1.27-alpine >/dev/null 2>&1 \
    || docker tag public.ecr.aws/docker/library/nginx:1.27-alpine nginx:1.27-alpine
}
