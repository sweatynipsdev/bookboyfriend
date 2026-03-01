"""Application settings loaded from environment / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database ---
    db_path: str = "bookboyfriend.db"
    chroma_path: str = "./characters_db"

    # --- JWT ---
    jwt_secret: str = "change-me-to-a-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # --- Provider selection ---
    llm_provider: str = "minimax"
    tts_provider: str = "minimax"
    stt_provider: str = "whisper_api"
    embedding_provider: str = "sentence_transformers"

    # --- API keys ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    minimax_api_key: str = ""
    minimax_group_id: str = ""

    # --- MiniMax models ---
    minimax_model: str = "MiniMax-M2.5"
    minimax_tts_model: str = "speech-02-hd"
    minimax_tts_voice: str = "female-shaonv"

    # --- RAG / chunking ---
    chunk_size: int = 512
    chunk_overlap: int = 50
    top_k_results: int = 5


settings = Settings()
