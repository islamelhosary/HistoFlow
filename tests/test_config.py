import os
from pipeline.config import load_app_settings, load_pipeline_settings, AppSettings, PipelineSettings

def test_load_app_settings_defaults():
    # No JSON override; should load the defaults and any environment values.
    settings = load_app_settings()
    assert isinstance(settings, AppSettings)
    # Check a basic default value.
    assert settings.log_level.upper() in ("INFO", "DEBUG", "WARNING", "ERROR")

def test_load_pipeline_settings(tmp_path, monkeypatch):
    # Create temporary directories for the WSI folder and output folder.
    wsi_dir = tmp_path / "wsi_folder"
    wsi_dir.mkdir()
    output_dir = tmp_path / "output_folder"
    output_dir.mkdir()

    # Set environment variables with the PIPELINE_ prefix.
    monkeypatch.setenv("PIPELINE_WSI_FOLDER", str(wsi_dir))
    monkeypatch.setenv("PIPELINE_OUTPUT_FOLDER", str(output_dir))

    settings = load_pipeline_settings()
    assert isinstance(settings, PipelineSettings)
    # Ensure that the temporary folders exist.
    assert os.path.exists(settings.wsi_folder)
    assert os.path.exists(settings.output_folder)
