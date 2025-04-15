import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import Field, validator
from pydantic_settings import BaseSettings
from pythonjsonlogger import jsonlogger

class AppSettings(BaseSettings):
    """
    Application-specific settings (API, services, infrastructure).
    """
    environment: str = Field("development", description="Application environment")
    
    # Logging
    log_level: str = Field("INFO", description="Logging level")
    log_file: Optional[str] = Field(None, description="Log file path")
    log_format: str = Field(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
        description="Log format string"
    )
    
    # Redis Configuration
    redis_url: str = Field("redis://localhost:6379", description="Redis connection URL")
    redis_pool_size: int = Field(10, description="Redis connection pool size")
    redis_timeout: int = Field(5, description="Redis operation timeout in seconds")
    redis_retry_attempts: int = Field(3, description="Number of retry attempts for Redis operations")

    # Dagster Infrastructure Configuration
    dagster_home: str = Field("~/.dagster", description="Dagster home directory")
    dagster_execution_timeout: str = Field("3600", description="Dagster execution timeout")
    dagster_max_retries: str = Field("2", description="Dagster maximum retries")

    class Config:
        extra = "allow"
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        env_prefix = "APP_"


class PipelineSettings(BaseSettings):
    """
    Pipeline-specific configuration related to data processing.
    """
    # Pipeline Configuration
    wsi_folder: str = Field(..., description="Path to the WSI folder")
    file_ending: str = Field(".svs", description="File extension for WSI files")
    save_patches: bool = Field(False, description="Whether to save patches")
    output_folder: str = Field(..., description="Path to save outputs")
    batch_size: int = Field(32, description="Batch size for processing")
    max_workers: int = Field(os.cpu_count(), description="Maximum number of workers")

    # Pipeline Execution Settings
    execution_timeout: int = Field(3600, description="Pipeline execution timeout in seconds")
    max_retries: int = Field(2, description="Maximum number of retries for pipeline operations")

    # NEW FIELDS FOR MODEL PATHS
    ctranspath_model_path: str = Field("data/models/ctranspath.pth", description="Path to the CTranspath model weights")
    histogpt_model_path: str = Field("data/models/histogpt-1b-6k-pruned.pth", description="Path to the HistoGPT model weights")
    ctranspath_model_url: str = Field(
        "https://huggingface.co/marr-peng-lab/histogpt/resolve/main/ctranspath.pth?download=true",
        description="HTTP URL to download the CTranspath weights if not found locally"
    )
    histogpt_model_url: str = Field(
        "https://huggingface.co/marr-peng-lab/histogpt/resolve/main/histogpt-1b-6k-pruned.pth?download=true",
        description="HTTP URL to download the HistoGPT weights if not found locally"
    )

    # (Optional) Additional patching parameters
    patch_size: int = Field(256, description="Patch size for WSI patch extraction")
    white_thresh: str = Field("170,185,175", description="White threshold for skipping background patches")
    edge_threshold: int = Field(2, description="Edge threshold for patching")
    downscaling_factor: float = Field(4.0, description="Downscaling factor for patching WSI")
    
    class Config:
        extra = "allow"
        env_file = ".env_pipeline"
        env_file_encoding = "utf-8"
        case_sensitive = False
        env_prefix = "PIPELINE_"

    @validator("wsi_folder", pre=True)
    def validate_input_folder(cls, v: str) -> str:
        path = Path(os.path.expanduser(v))
        if not path.exists():
            raise ValueError(f"Input WSI folder does not exist: {v}")
        return str(path.resolve())

    @validator("output_folder", pre=True)
    def validate_output_folder(cls, v: str) -> str:
        path = Path(os.path.expanduser(v))
        path.mkdir(parents=True, exist_ok=True)
        return str(path.resolve())


def load_app_settings(json_path: Optional[str] = None) -> AppSettings:
    """
    Loads application settings from .env and environment variables,
    with optional JSON override.
    """
    base_settings = AppSettings()
    
    if json_path and os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            # Create a new settings object with JSON taking precedence
            app_data = data.get("app", {})
            merged_data = {**base_settings.dict(), **app_data}
            return AppSettings(**merged_data)
        except Exception as ex:
            raise ValueError(f"Failed to load or parse app config from '{json_path}': {ex}")
    
    return base_settings


def load_pipeline_settings(json_path: Optional[str] = None) -> PipelineSettings:
    """
    Loads pipeline settings from .env and environment variables,
    with optional JSON override.
    """
    
    if json_path and os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            # Create a new settings object with JSON taking precedence
            pipeline_data = data.get("pipeline", {})
            return PipelineSettings(**pipeline_data)
        except Exception as ex:
            raise ValueError(f"Failed to load or parse pipeline config from '{json_path}': {ex}")
    # For test environments, provide default values for required fields
    # In production, these would be set by environment variables
    try:
        return PipelineSettings()
    except Exception:
        # Fallback for testing: provide default values for required fields
        return PipelineSettings(
            wsi_folder="data/wsi",
            output_folder="data/test_output"
        )


def setup_logging(settings: AppSettings) -> None:
    """
    Configure Python logging globally based on the app settings.
    Uses JSON formatting for structured logging.
    """
    log_handlers = []
    stream_handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(fmt=settings.log_format)
    stream_handler.setFormatter(formatter)
    log_handlers.append(stream_handler)

    if settings.log_file:
        file_handler = logging.FileHandler(settings.log_file, mode="a")
        file_handler.setFormatter(formatter)
        log_handlers.append(file_handler)

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        handlers=log_handlers
    )
