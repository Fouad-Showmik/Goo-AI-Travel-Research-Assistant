from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llm_base_url : str
    llm_api_key : str
    model_name : str

    system_prompt_file : str = "prompts/goo_travel_assistant.md"
    history_first_exchanges: int = 4
    history_recent_exchanges: int = 6
    session_ttl_seconds : int

    geoapify_api_key: str

    model_config = SettingsConfigDict(env_file=".env")

    @property
    def system_prompt(self):
        return Path(self.system_prompt_file).read_text(encoding="utf-8")

settings = Settings()