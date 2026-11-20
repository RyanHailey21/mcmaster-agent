# ABOUTME: Test script for McMaster CAD model download functionality.
# ABOUTME: Verifies downloading 3D models with format selection and SHA-256 verification.

import os
import shutil
import tempfile
from pathlib import Path
from browser import McMasterBrowser

def test_download_cad():
    """Test downloading CAD model for a known part."""
    print("Testing McMaster CAD download...", flush=True)

    # Test part: standard socket head screw
    part_number = "91290A115"
    temp_dir = tempfile.mkdtemp(prefix="mcmaster_cad_test_")

    try:
        with McMasterBrowser(headless=False) as browser:
            print(f"Downloading CAD model for {part_number} to {temp_dir}...", flush=True)
            result = browser.download_cad(
                part_number=part_number,
                file_format="3-D STEP",
                output_dir=temp_dir,
                timeout=30.0,
            )

            print("\nDownload Result:", flush=True)
            for k, v in result.items():
                print(f"  {k}: {v}", flush=True)

            assert result.get("success") is True, f"Download failed: {result.get('error')}"
            assert os.path.exists(result["file_path"]), f"File does not exist: {result['file_path']}"
            assert result["size_bytes"] > 0, "File is empty"
            assert len(result["sha256"]) == 64, "Invalid SHA-256 hash"
            print("\nVerification successful!", flush=True)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_download_cad()
