"""Secrets resolution: environment variables with optional AWS Secrets Manager."""

from __future__ import annotations

import json
import os

import structlog

logger = structlog.get_logger(__name__)

_aws_cache: dict[str, str] = {}


def get_secret(name: str, default: str = "") -> str:
    """Resolve a secret by name from env or AWS Secrets Manager."""
    env_value = os.getenv(name)
    if env_value:
        return env_value

    backend = os.getenv("SECRETS_BACKEND", "env").lower()
    if backend != "aws":
        return default

    secret_arn = os.getenv("AWS_SECRETS_ARN")
    if not secret_arn:
        return default

    if name in _aws_cache:
        return _aws_cache[name]

    try:
        import boto3

        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_arn)
        payload = json.loads(response["SecretString"])
        _aws_cache.update({k: str(v) for k, v in payload.items()})
        return _aws_cache.get(name, default)
    except Exception:
        logger.exception("aws_secret_fetch_failed", secret=name)
        return default
