import os
from unittest.mock import patch

import pytest

from lambdas.shared.security.aws_secrets import SecretsManager


@pytest.mark.parametrize(
    "explicit,environment,expected",
    [
        ("eu-west-1", {"AWS_REGION": "us-west-2"}, "eu-west-1"),
        (None, {"AWS_REGION": "us-west-2", "AWS_DEFAULT_REGION": "us-east-1"}, "us-west-2"),
        (None, {"AWS_REGION": "us-west-2"}, "us-west-2"),
        (None, {"AWS_DEFAULT_REGION": "us-west-2"}, "us-west-2"),
        (None, {}, "us-east-1"),
    ],
)
def test_secret_client_region_matches_lambda_runtime(explicit, environment, expected):
    with patch.dict(os.environ, environment, clear=True):
        with patch("lambdas.shared.security.aws_secrets.boto3.client") as client:
            SecretsManager(region_name=explicit)
    client.assert_called_once_with("secretsmanager", region_name=expected)
