"""Cloud-hosted LLM via AWS Bedrock (LangChain)."""
from __future__ import annotations

from functools import lru_cache

from langchain_aws import ChatBedrockConverse

from app.config import get_settings


@lru_cache(maxsize=1)
def get_llm() -> ChatBedrockConverse:
    settings = get_settings()
    return ChatBedrockConverse(
        model=settings.bedrock_model_id,
        region_name=settings.aws_region,
        temperature=0.0,
        max_tokens=1024,
    )
