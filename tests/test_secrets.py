from unittest.mock import MagicMock, patch

from core.secrets import get_secret


def test_get_secret_from_env(monkeypatch) -> None:
    monkeypatch.setenv("SECRETS_BACKEND", "env")
    monkeypatch.setenv("MY_TEST_SECRET", "from-env")
    assert get_secret("MY_TEST_SECRET") == "from-env"


def test_get_secret_default_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("MISSING_SECRET", raising=False)
    monkeypatch.setenv("SECRETS_BACKEND", "env")
    assert get_secret("MISSING_SECRET", "fallback") == "fallback"


@patch("boto3.client")
def test_get_secret_from_aws(mock_boto_client: MagicMock, monkeypatch) -> None:
    import core.secrets as secrets_module

    secrets_module._aws_cache.clear()
    monkeypatch.setenv("SECRETS_BACKEND", "aws")
    monkeypatch.setenv("AWS_SECRETS_ARN", "arn:aws:secretsmanager:us-east-1:123:secret:finflow")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    client = MagicMock()
    client.get_secret_value.return_value = {
        "SecretString": '{"SECRET_KEY": "aws-secret-value"}',
    }
    mock_boto_client.return_value = client

    assert get_secret("SECRET_KEY") == "aws-secret-value"
