from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration loaded from environment variables."""

    TABLE_NAME: str = "TenderAnalysis"
    UPLOAD_BUCKET_NAME: str = "licitaciones-uploads"
    BEDROCK_MODEL_ID: str = "anthropic.claude-3-5-haiku-20241022-v1:0"
    AWS_REGION: str = "us-east-1"
    PRESIGNED_URL_EXPIRATION_SECONDS: int = 900
    MAX_TIMEOUT_MARGIN_SECONDS: int = 165
    MAX_RETRIES: int = 5
    ADAPTIVE_RETRY_MODE: str = "adaptive"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
