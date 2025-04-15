# HistoGPT Production Pipeline

A productionized data pipeline and API service for generating diagnostic reports from whole slide images (WSIs) using a two-stage ML process.  
The pipeline:
1. Extracts patches and generates embeddings using the CTranspath model.
2. Uses the HistoGPT transformer model to produce clinical diagnostic reports.
3. Aggregates individual WSI reports into a single CSV result.

This solution leverages **FastAPI** for API endpoints, **Dagster** for orchestrating the processing pipeline, and **Redis** for task status management.

---

## Table of Contents

- [Features](#features)
- [Installation & Setup](#installation--setup)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
  - [API Service](#api-service)
  - [Pipeline CLI](#pipeline-cli)
- [Testing](#testing)
- [Deployment Considerations](#deployment-considerations)
- [Dependencies](#dependencies)
- [Conclusion](#conclusion)

---

## Features

- **Data Pipeline Orchestration:**  
  Uses Dagster to manage the multi-step pipeline that processes WSIs to generate embeddings, diagnostic reports, and a final CSV aggregation.

- **API Endpoints:**  
  A FastAPI server provides endpoints to:
  - Initiate pipeline runs
  - Check task status
  - Retrieve completed results
  - List all running/completed tasks
  - Perform health checks on critical services (e.g., Redis connectivity).

- **Configuration-Driven:**  
  Parameters such as the location of WSI images, file type, and options for saving intermediate results (e.g., patch images) are managed via environment configuration and/or JSON files.

- **Robust Logging & Error Handling:**  
  Implements structured logging (JSON formatted) and uses Redis to track the state of pipeline tasks, enabling effective production monitoring.

---

## Installation & Setup

### Prerequisites

- **Python:** Version 3.8 or later  
- **Docker:** For running Redis locally (or install Redis directly)  
- **OS Tools:**  
  - **Linux:** Install OpenSlide tools:  
    ```bash
    sudo apt-get install openslide-tools
    ```
  - **macOS:** Install OpenSlide with Homebrew:  
    ```bash
    brew install openslide
    ```

### Setting Up the Environment

1. **Clone the Repository:**
    ```bash
    git clone <REPOSITORY_URL>
    cd <repository_directory>
    ```

2. **Create a Virtual Environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3. **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    > **Note:** If you are developing or running tests, also install:
    > ```bash
    > pip install -r requirements-dev.txt
    > pip install -r requirements-test.txt
    > ```

4. **Environment Configuration:**  
   - Copy the template configuration files:
     ```bash
     cp .env.template .env
     cp .env_pipeline.template .env_pipeline
     ```
   - Customize these files as needed. See the [Configuration](#configuration) section below.

---

## Configuration

The pipeline relies on environment variables and/or JSON configuration files. There are two major areas:

### Application Settings (FastAPI & Infrastructure)
Configured via the `.env` file:
- **`APP_REDIS_URL`**: URL to connect to the Redis instance.
- **`APP_LOG_LEVEL`**: Logging level (e.g., INFO, DEBUG).
- **`APP_DAGSTER_HOME`**: Path for Dagster's home directory.
- **Other settings:** Logging format, pool sizes, timeouts, etc.

### Pipeline Settings
Configured via the `.env_pipeline` file (or an optional JSON file override):
- **`PIPELINE_WSI_FOLDER`**: Directory containing the whole slide images.
- **`PIPELINE_FILE_ENDING`**: Filter for file types (e.g., `.svs`).
- **`PIPELINE_SAVE_PATCHES`**: Boolean flag to store patch images for debugging.
- **`PIPELINE_OUTPUT_FOLDER`**: Directory for outputs (e.g., generated reports and CSV).
- **`PIPELINE_BATCH_SIZE`** and **`PIPELINE_MAX_WORKERS`**: Resource management.
- **Model-specific settings:** Paths and URLs for the CTranspath and HistoGPT model weights.
- **Optional Settings:** Fields such as patch size, white thresholds, etc.

#### Additional Pipeline Configuration Details
- **`PIPELINE_PATCH_SIZE`**: Patch size for WSI patch extraction (default: 256)
- **`PIPELINE_WHITE_THRESH`**: White threshold for skipping background patches (default: "170,185,175")
- **`PIPELINE_EDGE_THRESHOLD`**: Edge threshold for patching (default: 2)
- **`PIPELINE_DOWNSCALING_FACTOR`**: Downscaling factor for patching WSI (default: 4.0)
- **`PIPELINE_EXECUTION_TIMEOUT`**: Pipeline execution timeout in seconds (default: 3600)
- **`PIPELINE_MAX_RETRIES`**: Maximum number of retries (default: 2)

#### Configuration Precedence
Configuration values are loaded with the following precedence (highest to lowest):
1. JSON payload in API request
2. Environment variables
3. Environment files (.env or .env_pipeline)
4. Default values from code

---

## Running the Application

### API Service

1. **Start Redis (using Docker):**
    ```bash
    docker pull redis:latest
    docker run --name histogpt-redis -p 6379:6379 -d redis:latest
    ```
    > To stop and remove the container later:
    > ```bash
    > docker stop histogpt-redis
    > docker rm histogpt-redis
    > ```

2. **Launch the FastAPI Server:**
    ```bash
    uvicorn fastapi_app.main:app --reload
    ```
    The API will be live at:  
    - Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)  
    - ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

3. **API Endpoints Overview:**
    - **`POST /run-pipeline`**: Start a new pipeline run. Accepts JSON configuration to override defaults.
    - **`GET /status/{task_id}`**: Check the status of a specific pipeline task.
    - **`GET /result/{task_id}`**: Retrieve the report (and other results) for a completed pipeline task.
    - **`GET /tasks`**: List all submitted pipeline tasks.
    - **`GET /health`**: Health check for the API (tests Redis connectivity and component status).

### Pipeline CLI

In addition to the API, you can run the pipeline directly via the command line:

```bash
python -m pipeline.run_pipeline --config sample_config.json
```

> Note: The JSON configuration file (sample_config.json) should follow the structure:
> Adjust additional parameters as required.
```json
{
    "pipeline": {
        "wsi_folder": "data/wsi",
        "file_ending": ".svs",
        "save_patches": false,
        "output_folder": "data/output",
        "batch_size": 32,
        "max_workers": 8,
        "execution_timeout": 3600,
        "max_retries": 2,
        "ctranspath_model_path": "data/models/ctranspath.pth",
        "histogpt_model_path": "data/models/histogpt-1b-6k-pruned.pth",
        "ctranspath_model_url": "https://huggingface.co/marr-peng-lab/histogpt/resolve/main/ctranspath.pth?download=true",
        "histogpt_model_url": "https://huggingface.co/marr-peng-lab/histogpt/resolve/main/histogpt-1b-6k-pruned.pth?download=true",
        "patch_size": 256,
        "white_thresh": "170,185,175",
        "edge_threshold": 2,
        "downscaling_factor": 4.0
    }
} 
```

### Running with Dagster UI

To run the pipeline with the Dagster UI for more detailed monitoring and execution:

```bash
dagster dev -m pipeline.pipeline_definition --verbose
```

This will start the Dagster UI, allowing you to visualize and interact with the pipeline execution graph.

### Testing
To run the automated test suite, use:
```bash
pytest
```
This will execute tests for API endpoints, configuration loading, and pipeline operations.

## Future Deployment Plans

- **Containerization:**
  
  I plan to package the API and pipeline within Docker containers. I will use a single Docker Compose file to orchestrate the FastAPI app, Redis instance, and optionally a Dagster scheduler/webserver. This approach will streamline the environment setup, simplify scaling, and make maintenance more straightforward.

- **Logging & Monitoring:**
  
  In the future, I intend to integrate centralized logging and monitoring solutions. My plan is to enhance the logging infrastructure to automatically collect and parse JSON-formatted logs, enable real-time alerting, and implement customizable log retention policies. These measures will ensure efficient troubleshooting and operational transparency.

- **Configuration & Secrets Management:**
  
  For production deployment, I will adopt robust configuration and secrets management practices. I plan to use environment variables along with dedicated secret management services (such as HashiCorp Vault or AWS Secrets Manager etc ...) to securely handle sensitive data like Redis URLs and API keys. This will help me follow security best practices and prevent any exposure of sensitive configuration files.

    
---

## Dependencies

### Key Libraries

- **ML & Model Dependencies:**
    - [HistoGPT](https://github.com/islamelhosary/HistoGPT/tree/islamelhosary-patch-1) 
    - `flamingo-pytorch` 
    - `openslide-python` 
    - `torch` and `torchvision`
    - `transformers` 
    - `h5py` 
- **Data Pipeline & API:**
    - `dagster` 
    - `fastapi` and `uvicorn` 
    - `redis` 
    - `python-dotenv` and `pydantic`/`pydantic-settings`
- **Utilities:**
    - `pandas` and `numpy`
    - `tqdm` 
    - `requests` 

---

## Conclusion

This project provides a modular and configurable data pipeline built around state-of-the-art pathology image processing models. With a clear separation between configuration, API, and pipeline operations, it is designed to be maintainable and scalable for production use.

For questions or contributions, please open an issue or submit a pull request.

Happy Diagnosing!