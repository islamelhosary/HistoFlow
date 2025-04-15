import os
import json
import uuid
import logging
import redis
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

# Dagster
from dagster import execute_job, reconstructable, DagsterInstance

# Import our settings system
from pipeline.config import (
    load_app_settings, 
    load_pipeline_settings, 
    setup_logging, 
    AppSettings, 
    PipelineSettings
)
from pipeline.pipeline_definition import histogpt_pipeline

app = FastAPI(title="HistoGPT Pipeline API", version="2.0.0")

# Load base settings
app_settings = load_app_settings(None)
pipeline_settings = load_pipeline_settings(None)

# Initialize Redis client using app settings
base_redis_client = redis.Redis.from_url(app_settings.redis_url, decode_responses=True)

# Simple status object
class TaskStatus(BaseModel):
    status: str
    start_time: float
    end_time: Optional[float] = None
    error: Optional[str] = None
    results: Optional[Dict[str, Any]] = None
    pipeline_config: Optional[Dict[str, Any]] = None

@app.on_event("startup")
async def startup_event():
    # Basic connectivity check
    retry_count = 0
    max_retries = 3
    while retry_count < max_retries:
        try:
            base_redis_client.ping()
            logging.info("Connected to Redis successfully.")
            return
        except redis.exceptions.ConnectionError as e:
            retry_count += 1
            if retry_count >= max_retries:
                logging.error(f"Failed to connect to Redis after {max_retries} attempts: {e}")
            else:
                logging.warning(f"Redis connection attempt {retry_count} failed, retrying...")
                import time
                time.sleep(1)  # Simple backoff

class ApiPipelineConfig(BaseModel):
    """
    Example pydantic model to capture user config in the request body
    that will override environment-based defaults.
    """
    wsi_folder: Optional[str] = None
    file_ending: Optional[str] = None
    save_patches: Optional[bool] = None
    output_folder: Optional[str] = None
    batch_size: Optional[int] = None
    max_workers: Optional[int] = None

def update_task_status(redis_client: redis.Redis, task_id: str, status_obj: dict) -> None:
    try:
        redis_client.set(f"task:{task_id}", json.dumps(status_obj))
    except Exception as e:
        logging.critical(f"Failed to update status for task {task_id}: {e}")

def run_pipeline_in_background(task_id: str, app_config: AppSettings, pipeline_config: PipelineSettings, redis_client: redis.Redis):
    """
    The background task that executes our Dagster job.
    """
    # Update the stored status to "running"
    current_time = datetime.now().timestamp()
    status_obj = {
        "status": "running",
        "start_time": current_time,
        "end_time": None,
        "error": None,
        "results": None,
        "pipeline_config": pipeline_config.dict()
    }
    
    try:
        # Store initial status
        update_task_status(redis_client, task_id, status_obj)
        
        # Setup logging
        setup_logging(app_config)
        logging.info(f"Starting pipeline for task {task_id}")

        # Ensure DAGSTER_HOME is set
        dagster_home = os.path.abspath(os.path.expanduser(app_config.dagster_home))
        os.environ["DAGSTER_HOME"] = dagster_home
        os.makedirs(dagster_home, exist_ok=True)

        # Get Dagster instance
        instance = DagsterInstance.get()

        # Prepare run_config - pass ONLY pipeline settings to the pipeline
        logging.info(f"Sending pipeline configuration to Dagster: {pipeline_config.dict()}")
        
        run_config = {
            "ops": {
                "load_config_op": {
                    "config": pipeline_config.dict()
                }
            }
        }

        # Execute the pipeline
        recon_job = reconstructable(histogpt_pipeline)
        result = execute_job(
            recon_job,
            run_config=run_config,
            instance=instance,
            tags={
                "task_id": task_id,
                "execution_timeout": app_config.dagster_execution_timeout,
                "max_retries": app_config.dagster_max_retries
            }
        )

        # Update status based on result
        final_time = datetime.now().timestamp()
        if result.success:
            status_obj["status"] = "completed"
            status_obj["results"] = {"success": True}
            logging.info(f"Pipeline completed successfully for task {task_id}")
        else:
            status_obj["status"] = "failed"
            failure_event = next(
                (e for e in result.all_events if e.event_type_value == "PIPELINE_FAILURE"), 
                None
            )
            error_msg = failure_event.message if failure_event else "Unknown pipeline error"
            status_obj["error"] = error_msg
            logging.error(f"Pipeline failed for task {task_id}: {error_msg}")
        
        status_obj["end_time"] = final_time

    except redis.exceptions.RedisError as e:
        # Handle Redis-specific errors
        logging.exception(f"Redis error for task {task_id}: {e}")
        status_obj["status"] = "failed"
        status_obj["error"] = f"Redis error: {str(e)}"
        status_obj["end_time"] = datetime.now().timestamp()
    except Exception as e:
        # Handle all other errors
        logging.exception(f"Error running pipeline for task {task_id}: {e}")
        status_obj["status"] = "failed"
        status_obj["error"] = str(e)
        status_obj["end_time"] = datetime.now().timestamp()

    # Final attempt to store the status, with extra error handling
    update_task_status(redis_client, task_id, status_obj)

@app.post("/run-pipeline")
async def start_pipeline(config: ApiPipelineConfig, background_tasks: BackgroundTasks) -> Dict[str, str]:
    """
    Endpoint to start a new pipeline run. 
    JSON fields override environment-based defaults.
    """
    try:
        # Load base settings
        app_config = load_app_settings(None)
        pipeline_config = load_pipeline_settings(None)
        logging.info(f"Pipeline config: {pipeline_config.dict()}")
        # Convert the user's incoming config to a dict and remove None values
        user_overrides = {k: v for k, v in config.dict().items() if v is not None}
        
        # Merge only pipeline settings (user config overrides environment settings)
        pipeline_data = {**pipeline_config.dict(), **user_overrides}
        merged_pipeline_settings = PipelineSettings(**pipeline_data)

        # Validate and create folders
        if not os.path.exists(merged_pipeline_settings.wsi_folder):
            raise HTTPException(status_code=400, detail=f"WSI folder does not exist: {merged_pipeline_settings.wsi_folder}")

        # Create the output folder if it doesn't exist
        os.makedirs(merged_pipeline_settings.output_folder, exist_ok=True)
        logging.info(f"Using output folder: {merged_pipeline_settings.output_folder}")

        # Create a unique task_id
        task_id = str(uuid.uuid4())
        logging.info(f"Created new pipeline task: {task_id}")

        # Initial status
        init_status = {
            "status": "queued",
            "start_time": datetime.now().timestamp(),
            "end_time": None,
            "error": None,
            "results": None,
            "pipeline_config": merged_pipeline_settings.dict()
        }
        
        # Store initial status
        try:
            update_task_status(base_redis_client, task_id, init_status)
        except redis.exceptions.RedisError as e:
            logging.error(f"Failed to store initial status for task {task_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to initialize task: {str(e)}")

        # Run the pipeline in the background
        background_tasks.add_task(
            run_pipeline_in_background, 
            task_id, 
            app_config, 
            merged_pipeline_settings, 
            base_redis_client
        )

        return {"task_id": task_id}
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logging.exception(f"Error starting pipeline: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start pipeline: {str(e)}")

@app.get("/status/{task_id}", response_model=TaskStatus)
async def check_status(task_id: str) -> TaskStatus:
    """
    Check the status of a pipeline run.
    """
    try:
        raw_data = base_redis_client.get(f"task:{task_id}")
        if not raw_data:
            raise HTTPException(status_code=404, detail="Task not found")

        task_data = json.loads(raw_data)
        return TaskStatus(**task_data)
    except redis.exceptions.RedisError as e:
        logging.error(f"Redis error while checking status for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve task status: {str(e)}")
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON format for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Invalid task data format")
    except Exception as e:
        logging.exception(f"Error checking status for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving task status: {str(e)}")

@app.get("/result/{task_id}")
async def get_result(task_id: str) -> Dict[str, Any]:
    """
    Get the result of a completed pipeline run.
    """
    try:
        raw_data = base_redis_client.get(f"task:{task_id}")
        if not raw_data:
            raise HTTPException(status_code=404, detail="Task not found")

        task_data = json.loads(raw_data)
        if task_data["status"] in ("running", "queued"):
            raise HTTPException(status_code=400, detail="Task is still running")

        return task_data
    except redis.exceptions.RedisError as e:
        logging.error(f"Redis error while getting result for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve task result: {str(e)}")
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON format for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Invalid task data format")
    except HTTPException:
        raise
    except Exception as e:
        logging.exception(f"Error retrieving result for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving task result: {str(e)}")

@app.get("/tasks", response_model=List[str])
async def list_tasks() -> List[str]:
    """
    List all pipeline tasks (keys) in Redis.
    """
    try:
        keys = base_redis_client.keys("task:*")
        # Each key is like "task:abc123"; parse out the actual task ID
        return [k.split("task:")[1] for k in keys]
    except redis.exceptions.RedisError as e:
        logging.error(f"Redis error while listing tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list tasks: {str(e)}")
    except Exception as e:
        logging.exception(f"Error listing tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing tasks: {str(e)}")

@app.get("/health")
async def health_check():
    """
    Basic health check.
    """
    try:
        # Test Redis connection
        redis_ok = base_redis_client.ping()
        
        # Return status with components and version
        return {
            "status": "healthy" if redis_ok else "degraded",
            "version": "2.0.0",
            "components": {
                "redis": "connected" if redis_ok else "disconnected"
            }
        }
    except redis.exceptions.RedisError as e:
        logging.error(f"Redis error during health check: {e}")
        return {
            "status": "degraded",
            "version": "2.0.0",
            "components": {
                "redis": f"error: {str(e)}"
            }
        }
    except Exception as e:
        logging.exception(f"Error during health check: {e}")
        return {
            "status": "error",
            "version": "2.0.0",
            "error": str(e)
        }
