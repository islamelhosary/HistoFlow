from dagster import op, job, RetryPolicy, Out, In
from typing import List, Dict, Any

from .ops.embeddings import run_embeddings
from .ops.report_gen import generate_report
from .ops.aggregate import aggregate_reports

@op(
    out={"config_dict": Out()},
    description="Loads configuration from run_config"
)
def load_config_op(context) -> Dict[str, Any]:
    """
    Loads pipeline configuration from the run_config.
    This op now only receives pipeline-specific settings.
    """
    config_dict = context.op_config
    context.log.info(f"Pipeline configuration loaded: {config_dict}")
    return config_dict

# Using retry_policy with max_retries=2 and a 30s delay to handle transient errors.
# Adjust based on system resilience.
@op(
    ins={"config_dict": In()},
    out={"embeddings": Out()},
    retry_policy=RetryPolicy(max_retries=2, delay=30), 
    description="Op that handles embedding generation with potential retries"
)
def process_embeddings_op(context, config_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Passes the config to run_embeddings.
    """
    return run_embeddings(context, config_dict)

 # Retry policy rationale: to mitigate transient issues during report generation.
@op(
    ins={"config_dict": In(), "embeddings": In()},
    out={"reports": Out()},
    retry_policy=RetryPolicy(max_retries=2, delay=30),
    description="Op that generates clinical reports from embeddings"
)
def process_report_gen_op(context, config_dict: Dict[str, Any], embeddings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return generate_report(context, embeddings, config_dict)

@op(
    ins={"config_dict": In(), "reports": In()},
    description="Op that aggregates all generated report files into a single CSV"
)
def process_aggregation_op(context, config_dict: Dict[str, Any], reports: List[Dict[str, Any]]) -> None:
    aggregate_reports(context, reports, config_dict)

@job
def histogpt_pipeline():
    """
    The main Dagster job. If any op raises an exception,
    Dagster will retry the op if a RetryPolicy is set.
    """
    config_dict = load_config_op()
    embeddings = process_embeddings_op(config_dict)
    reports = process_report_gen_op(config_dict, embeddings)
    process_aggregation_op(config_dict, reports)
