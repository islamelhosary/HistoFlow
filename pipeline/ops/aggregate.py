import os
import pandas as pd
import traceback
from typing import Dict, Any, List

def aggregate_reports(context, reports: List[Dict[str, Any]], config_dict: Dict[str, Any]) -> None:
    """
    Aggregates each .txt report into a single CSV. 
    Handles missing files and ensures directories exist.
    """
    context.log.info("Aggregating reports into a single CSV...")

    if not reports:
        context.log.warning("No reports found to aggregate.")
        return

    output_folder = config_dict["output_folder"]
    os.makedirs(output_folder, exist_ok=True)

    # Define the output CSV path
    csv_path = os.path.join(output_folder, "results.csv")

    aggregated_rows = []
    failed_files = []
    
    for rep in reports:
        wsi_name = rep["wsi_name"]
        rep_path = rep["report_path"]
        
        try:
            # Check if file exists before trying to read it
            if not os.path.exists(rep_path):
                context.log.warning(f"Report file not found: {rep_path}")
                failed_files.append(wsi_name)
                continue
                
            with open(rep_path, "r") as rf:
                text = rf.read()
            aggregated_rows.append({"wsi_name": wsi_name, "report_text": text})
        except Exception as exc:
            context.log.error(f"Error reading report for {wsi_name}: {exc}")
            failed_files.append(wsi_name)

    # Create at least an empty DataFrame if all failed
    if not aggregated_rows:
        context.log.warning("Could not aggregate any reports. Creating empty CSV.")
        df = pd.DataFrame(columns=["wsi_name", "report_text"])
    else:
        df = pd.DataFrame(aggregated_rows)
    
    # Save the CSV
    try:
        df.to_csv(csv_path, index=False)
        context.log.info(f"Aggregation complete. CSV saved to {csv_path}")
    except Exception as e:
        context.log.error(f"Failed to save CSV: {e}")
        raise

    # Log summary 
    context.log.info(f"Successfully aggregated {len(aggregated_rows)} out of {len(reports)} reports")
    if failed_files:
        context.log.warning(f"Failed to aggregate {len(failed_files)} reports")
