#!/usr/bin/env python3
import argparse
import sys
import logging

from dagster import execute_job, DagsterInstance, reconstructable
from pipeline.config import (
    load_app_settings,
    load_pipeline_settings,
    setup_logging
)
from pipeline.pipeline_definition import histogpt_pipeline

def main():
    parser = argparse.ArgumentParser(description="Run the HistoGPT pipeline via CLI")
    parser.add_argument("--config", type=str, help="Path to the JSON configuration file (optional)")
    args = parser.parse_args()

    # 1. Load settings with optional JSON overrides
    app_settings = load_app_settings(args.config)
    pipeline_settings = load_pipeline_settings(args.config)

    # 2. Configure logging using app settings
    setup_logging(app_settings)

    # 3. Ensure DAGSTER_HOME from app settings
    import os
    import pathlib
    dagster_home = os.path.abspath(os.path.expanduser(app_settings.dagster_home))
    pathlib.Path(dagster_home).mkdir(parents=True, exist_ok=True)
    os.environ["DAGSTER_HOME"] = dagster_home

    # 4. Run the pipeline
    instance = DagsterInstance.get()

    # Only pass pipeline configuration to the first operation
    logging.info(f"Sending pipeline configuration to Dagster: {pipeline_settings.dict()}")
    
    run_config = {
        "ops": {
            "load_config_op": {
                "config": pipeline_settings.dict()
            }
        }
    }

    recon_job = reconstructable(histogpt_pipeline)
    result = execute_job(
        recon_job,
        run_config=run_config,
        instance=instance,
        tags={
            "execution_timeout": app_settings.dagster_execution_timeout,
            "max_retries": app_settings.dagster_max_retries
        },
    )

    if result.success:
        logging.info("Pipeline completed successfully.")
        sys.exit(0)
    else:
        logging.error("Pipeline failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
