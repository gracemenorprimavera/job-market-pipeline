from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Supabase (required)
    supabase_url: str
    supabase_service_key: str

    # Arbeitnow API
    arbeitnow_base_url: str = "https://www.arbeitnow.com/api/job-board-api"

    # Pipeline tuning — adjustable without touching pipeline code
    batch_size: int = 200  # rows per upsert batch (stays under PostgREST 1 MB limit)
    max_pages: int = 10  # max API pages per run (~100 jobs/page → ~1,000 jobs max)
    retry_attempts: int = 3
    retry_delay_seconds: int = 60

    # Email notifications via Resend (resend.com) — leave blank to disable
    resend_api_key: str = ""  # get from resend.com dashboard
    email_from: str = "onboarding@resend.dev"  # use your verified domain in production
    email_recipient: str = ""  # destination address

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
