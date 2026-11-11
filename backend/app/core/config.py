"""运行配置：全部来自环境变量，见 docs/deployment.md 第 4 节。"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EI_", extra="ignore")

    database_url: str = "postgresql+psycopg://ei:ei@localhost:5432/easyimporter"
    # 32 字节主密钥的 base64。api 与 worker 启动时由 crypto.ensure_keys 校验，缺失即拒绝启动。
    secret_key: str = ""
    admin_init_password: str = "admin123456"
    upload_dir: str = "/tmp/easyimporter-uploads"
    upload_max_mb: int = 20
    rows_max_mb: int = 200
    upload_retention_days: int = 90
    # 逗号分隔的主机或 CIDR 白名单；空表示不限制。
    datasource_allowed_hosts: str = ""
    cookie_secure: bool = False
    session_idle_hours: int = 8
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    # 导入错误表只保留前 N 条，完整错误写入错误报告文件。
    error_row_limit: int = 1000
    batch_size: int = 1000
    worker_poll_seconds: int = 2
    heartbeat_seconds: int = 10
    heartbeat_timeout_seconds: int = 120
    scope_tuple_chunk: int = 500

    @field_validator("database_url")
    @classmethod
    def normalize_url(cls, value: str) -> str:
        # 允许直接写 postgresql://，统一补上 psycopg 驱动。
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @property
    def allowed_hosts(self) -> list[str]:
        return [item.strip() for item in self.datasource_allowed_hosts.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
