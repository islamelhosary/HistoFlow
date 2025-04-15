import os
import requests
import logging
from tqdm import tqdm

# If I have more time, I would add a retry mechanism here.
def download_file(url: str, dest_path: str) -> None:
    """
    Download a file from a URL if it doesn't already exist.
    Raises an exception on download failure.
    """
    # Create subdirs if needed
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    response = requests.get(url, stream=True)
    if response.status_code != 200:
        raise RuntimeError(f"Failed to download from {url}. HTTP Status: {response.status_code}")

    total_size = int(response.headers.get('content-length', 0))
    chunk_size = 1024

    progress_bar = tqdm(total=total_size, unit='iB', unit_scale=True, desc=os.path.basename(dest_path))
    with open(dest_path, 'wb') as file:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                file.write(chunk)
                progress_bar.update(len(chunk))
    progress_bar.close()

    if total_size != 0 and progress_bar.n != total_size:
        raise RuntimeError("Download ended prematurely. File size mismatch.")

    logging.info(f"Downloaded {dest_path} from {url}")