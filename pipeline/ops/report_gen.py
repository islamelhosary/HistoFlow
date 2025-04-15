import os
import torch
import h5py
from typing import Dict, Any, List

from histogpt.models import HistoGPTForCausalLM, PerceiverResamplerConfig
from transformers import BioGptConfig, BioGptTokenizer
from histogpt.helpers.inference import generate
from pipeline.utils import download_file
def generate_report(context, embeddings: List[Dict[str, Any]], config_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Uses HistoGPT to generate clinical reports from the HDF5 features produced
    by the embedding step. One text file per WSI is created in the output folder.

    Returns a list of dictionaries, each containing:
      - wsi_name
      - report_path
      - status
      - error
    """

    if not embeddings:
        context.log.warning("No embeddings were provided; skipping report generation.")
        return []

    output_folder = config_dict["output_folder"]
    histogpt_path = config_dict["histogpt_model_path"]
    histogpt_url = config_dict["histogpt_model_url"]
    # Check model presence (and download if missing)
    if not os.path.isfile(histogpt_path):
        context.log.info(f"HistoGPT model not found at {histogpt_path}. Downloading from {histogpt_url}...")
        try:
            download_file(histogpt_url, histogpt_path)
        except Exception as e:
            context.log.error(f"Failed to download HistoGPT model: {e}")
            raise
    # Ensure the report directory exists
    reports_dir = os.path.join(output_folder, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    # Prepare the HistoGPT model
    context.log.info(f"Loading HistoGPT model from {histogpt_path}")
    model_config = BioGptConfig()
    perceiver_config = PerceiverResamplerConfig()
    histogpt_model = HistoGPTForCausalLM(model_config, perceiver_config)
    try:
        histogpt_model.load_state_dict(torch.load(histogpt_path, map_location="cpu"), strict=True)
    except Exception as e:
        context.log.error(f"Failed to load HistoGPT state dict: {e}")
        raise

    histogpt_model.eval()

    # If GPU is available, move model to GPU
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    histogpt_model.to(device)

    # Prepare tokenizer
    tokenizer = BioGptTokenizer.from_pretrained("microsoft/biogpt")

    # Some basic generation parameters (could also be stored in config)
    gen_length = 256
    top_k = 40
    top_p = 0.95
    temp = 0.7
    # If I have more time, I would make a prompt template using Jinja2 and load it here.
    initial_prompt = config_dict.get("diagnosis_prompt", "Final diagnosis:")
    reports = []
    for item in embeddings:
        wsi_name = item["wsi_name"]
        hdf5_path = item["hdf5_path"]

        if item["status"] == "error":
            context.log.warning(f"Skipping report generation for {wsi_name} due to embedding error.")
            reports.append({
                "wsi_name": wsi_name,
                "report_path": None,
                "status": "skipped",
                "error": "Embedding step failed"
            })
            continue

        context.log.info(f"Generating report for WSI: {wsi_name}")

        # Load image features from .h5
        if not os.path.exists(hdf5_path):
            context.log.error(f"No feature file found at {hdf5_path}. Skipping {wsi_name}.")
            reports.append({
                "wsi_name": wsi_name,
                "report_path": None,
                "status": "error",
                "error": "Missing HDF5 features"
            })
            continue

        try:
            with h5py.File(hdf5_path, 'r') as f:
                features = f['feats'][:]  # shape [n_patches, feature_dim]
            features = torch.tensor(features, device=device).unsqueeze(0)  # [1, n_patches, feat_dim]

            # Tokenize the prompt
            prompt = tokenizer.encode(initial_prompt, return_tensors="pt").to(device)

            # Generate text with the histogpt
            output_tokens = generate(
                model=histogpt_model,
                prompt=prompt,
                image=features,
                length=gen_length,
                top_k=top_k,
                top_p=top_p,
                temp=temp,
                device=device
            )

            decoded_text = tokenizer.decode(output_tokens[0, 1:])
            # Save report
            report_path = os.path.join(reports_dir, f"{wsi_name}.txt")
            with open(report_path, "w", encoding="utf-8") as rf:
                rf.write(decoded_text)

            reports.append({
                "wsi_name": wsi_name,
                "report_path": report_path,
                "status": "success",
                "error": None
            })
            context.log.info(f"Report saved to {report_path}")

        except Exception as e:
            context.log.error(f"Error generating report for {wsi_name}: {e}")
            reports.append({
                "wsi_name": wsi_name,
                "report_path": None,
                "status": "error",
                "error": str(e)
            })

    return reports
