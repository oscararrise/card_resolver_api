"""Secrets come from the instance role's SSM permissions in production.

Direct environment values are retained for isolated development and tests.
Parameter names may be placed in EnvironmentFile; secret values must not be.
"""
import os
from functools import lru_cache


@lru_cache(maxsize=None)
def setting(name: str) -> str:
    parameter_name = os.getenv(f"{name}_PARAMETER")
    if parameter_name:
        import boto3

        return boto3.client("ssm").get_parameter(
            Name=parameter_name, WithDecryption=True
        )["Parameter"]["Value"]
    return os.getenv(name, "")
