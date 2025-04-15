import os
import traceback
from typing import Dict, Any, List

import torch
from pipeline.utils import download_file
# The patching entrypoint from your HistoGPT library
from histogpt.helpers.patching import main as run_patching, PatchingConfigs

def run_embeddings(context, config_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Generates features for each WSI in the wsi_folder using the CTranspath model.
    This step replaces the old placeholder with actual patch extraction and embedding.
    
    Returns a list of dictionaries, each containing:
      - wsi_name: name of the WSI
      - hdf5_path: path to the extracted .h5 features for that WSI
      - status: 'success' or 'error'
      - error: error message if any
    """
    context.log.info("Starting embedding generation with CTranspath...")

    wsi_folder = config_dict["wsi_folder"]
    file_ending = config_dict["file_ending"]
    ctranspath_url = config_dict["ctranspath_model_url"]
    output_folder = config_dict["output_folder"]
    ctranspath_model_path = config_dict["ctranspath_model_path"]

    # Basic checks
    if not os.path.exists(wsi_folder):
        raise ValueError(f"WSI folder does not exist: {wsi_folder}")
    if not os.path.isfile(ctranspath_model_path):
        context.log.info(f"CTranspath model not found at {ctranspath_model_path}. Downloading from {ctranspath_url}...")
        try:
            download_file(ctranspath_url, ctranspath_model_path)
        except Exception as e:
            context.log.error(f"Failed to download CTranspath model: {e}")
            raise

    # Build patching configs from pipeline settings
    patch_configs = PatchingConfigs()
    patch_configs.slide_path = wsi_folder
    patch_configs.save_path = output_folder
    patch_configs.model_path = ctranspath_model_path
    patch_configs.save_patch_images = config_dict.get("save_patches", False)
    patch_configs.file_extension = file_ending
    # Convert string "170,185,175" -> [170,185,175]
    white_thresh_str = config_dict.get("white_thresh", "170,185,175")
    patch_configs.white_thresh = [int(x) for x in white_thresh_str.split(",")]

    patch_configs.patch_size = config_dict.get("patch_size", 256)
    patch_configs.edge_threshold = config_dict.get("edge_threshold", 2)
    patch_configs.downscaling_factor = config_dict.get("downscaling_factor", 4.0)
    patch_configs.batch_size = config_dict.get("batch_size", 16)
    patch_configs.resolution_in_mpp = 0.0  # example default

    # Run patching (which includes feature extraction) on all .svs (or .ndpi, etc.) in the folder
    context.log.info(f"Running patch extraction for WSIs in {wsi_folder} with model {ctranspath_model_path}")
    try:
        run_patching(patch_configs)
        context.log.info("Patch extraction and feature generation completed.")
    except Exception as e:
        context.log.error(f"Error during patch extraction: {e}")
        # Return an empty list or raise. We'll raise here to stop the pipeline if patching fails entirely
        raise

    # Gather references to the newly created .h5 files
    # Typically, run_patching outputs them under something like /output_folder/h5_files/...
    hdf5_dir = os.path.join(output_folder, "h5_files")
    if not os.path.exists(hdf5_dir):
        context.log.warning(f"No HDF5 directory found at {hdf5_dir}, no features generated?")
        return []

    # For each WSI we processed, we assume run_patching named the HDF5 file after the WSI
    results = []
    for root, dirs, files in os.walk(hdf5_dir):
        for fname in files:
            if fname.endswith(".h5"):
                wsi_name = os.path.splitext(fname)[0]
                results.append({
                    "wsi_name": wsi_name,
                    "hdf5_path": os.path.join(root, fname),
                    "status": "success",
                    "error": None
                })

    context.log.info(f"Completed embedding generation: Found {len(results)} .h5 files.")
    return results
