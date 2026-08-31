from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SRE_AGENT_",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    llm_base_url: str
    llm_api_key: str
    llm_model: str = "qwen-plus"
    prom_url: str = "http://localhost:9090"
    prom_basic_auth: str | None = None
    prom_bearer: str | None = None
    am_url: str = "http://localhost:9093"
    query_timeout_seconds: int = 15
    max_points: int = 1000
    allow_ad_hoc_promql: bool = False
    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    feishu_encrypt_key: str | None = None
    feishu_verification_token: str | None = None
    dingtalk_app_key: str | None = None
    dingtalk_app_secret: str | None = None
    metrics_port: int = 9108
    database_url: str = "postgresql://sre_agent:sre_agent@localhost:5432/sre_agent"
    read_only: bool = True


def load_settings() -> Settings:
    return Settings()
