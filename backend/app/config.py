"""Central configuration for MediBot backend, loaded from environment / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # AWS
    aws_region: str = "ap-south-1"

    # S3
    s3_bucket: str = "mediassist-documents"
    s3_prefix: str = "docs/"

    # Bedrock
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20240620-v1:0"

    # Cognito
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""
    cognito_region: str = "ap-south-1"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "mediassist_docs"

    # Embedding / rerank models
    dense_model: str = "BAAI/bge-small-en-v1.5"
    sparse_model: str = "Qdrant/bm25"
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Retrieval params
    candidate_k: int = 10   # broad hybrid candidate set
    final_k: int = 3        # after reranking

    # Chunking
    max_tokens_per_chunk: int = 512

    # Local data
    data_dir: str = "../data"
    sqlite_db_path: str = "../data/mediassist.db"

    # CORS — comma-separated allowed origins (add your Amplify URL in prod)
    frontend_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
