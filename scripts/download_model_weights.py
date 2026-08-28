import os
import sys
from pathlib import Path

try:
    from huggingface_hub import snapshot_download
except ImportError:
    print("Error: huggingface_hub is required. Run: pip install huggingface_hub")
    sys.exit(1)

WEIGHTS_DIR = Path(__file__).parent.parent / "backend" / "model_weights"
REPO_ID = os.environ.get("HF_MODEL_REPO", "swayamohapatra/sentinel-sif")

print(f"Downloading SentinelSIF model weights from Hugging Face: {REPO_ID}...")
os.makedirs(WEIGHTS_DIR, exist_ok=True)
snapshot_download(repo_id=REPO_ID, local_dir=str(WEIGHTS_DIR))
print(f"✅ Model weights downloaded successfully into {WEIGHTS_DIR}!")
