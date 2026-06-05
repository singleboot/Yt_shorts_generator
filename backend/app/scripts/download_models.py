#!/usr/bin/env python3
"""
VRAM-aware model downloader for AI Shorts Creator's built-in ComfyUI.
Detects GPU VRAM and downloads appropriate models + LoRAs.
"""

import os
import sys
import subprocess
from pathlib import Path
import urllib.request
import json

# Configuration
COMFYUI_DIR = Path(__file__).parent.parent.parent / "comfyui" / "ComfyUI"
MODELS_DIR = COMFYUI_DIR / "models"
CHECKPOINTS_DIR = MODELS_DIR / "checkpoints"
VAE_DIR = MODELS_DIR / "vae"
LORA_DIR = MODELS_DIR / "loras"
CLIP_DIR = MODELS_DIR / "clip"
DIFFUSION_DIR = MODELS_DIR / "diffusion_models"

# Create directories
for d in [CHECKPOINTS_DIR, VAE_DIR, LORA_DIR, CLIP_DIR, DIFFUSION_DIR]:
    d.mkdir(parents=True, exist_ok=True)

def get_vram_gb():
    """Detect available GPU VRAM in GB."""
    try:
        import torch
        if torch.cuda.is_available():
            total_memory = torch.cuda.get_device_properties(0).total_memory
            return total_memory / (1024**3)
    except:
        pass
    
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            vram_mb = float(result.stdout.strip().split('\n')[0])
            return vram_mb / 1024
    except:
        pass
    
    return 0

def find_file_recursively(base_dir: Path, pattern: str) -> list:
    """Search for files recursively in a directory."""
    results = []
    if base_dir.exists():
        for path in base_dir.rglob(pattern):
            if path.is_file():
                results.append(path)
    return results

def find_z_image_turbo():
    """Find Z-Image Turbo model in any subfolder."""
    # Search in checkpoints and diffusion_models
    patterns = [
        "z_image_turbo*.safetensors",
        "z-image-turbo*.safetensors",
        "ZIT*.safetensors",
    ]
    
    for search_dir in [CHECKPOINTS_DIR, DIFFUSION_DIR, MODELS_DIR]:
        for pattern in patterns:
            matches = find_file_recursively(search_dir, pattern)
            if matches:
                return matches[0]
    return None

def find_ltx_video():
    """Find LTX Video model."""
    patterns = [
        "ltx*.safetensors",
        "LTX*.safetensors",
    ]
    
    for search_dir in [CHECKPOINTS_DIR, DIFFUSION_DIR, MODELS_DIR]:
        for pattern in patterns:
            matches = find_file_recursively(search_dir, pattern)
            if matches:
                return matches[0]
    return None

def find_vae():
    """Find VAE (ae.safetensors)."""
    # Direct in vae folder
    vae_path = VAE_DIR / "ae.safetensors"
    if vae_path.exists():
        return vae_path
    
    # Search recursively
    matches = find_file_recursively(VAE_DIR, "ae.safetensors")
    if matches:
        return matches[0]
    
    # Also check in checkpoints/diffusion
    for search_dir in [CHECKPOINTS_DIR, DIFFUSION_DIR]:
        matches = find_file_recursively(search_dir, "ae.safetensors")
        if matches:
            return matches[0]
    
    return None

def find_clip():
    """Find Qwen CLIP model."""
    patterns = [
        "qwen*.safetensors",
        "Qwen*.safetensors",
    ]
    
    for search_dir in [CLIP_DIR, MODELS_DIR]:
        for pattern in patterns:
            matches = find_file_recursively(search_dir, pattern)
            if matches:
                return matches[0]
    return None

def download_file(url: str, dest: Path, desc: str = ""):
    """Download a file with progress."""
    print(f"Downloading {desc or dest.name}...")
    print(f"  From: {url}")
    print(f"  To: {dest}")
    
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Use urllib directly with proper headers
        opener = urllib.request.build_opener()
        opener.addheaders = [
            ('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
            ('Accept', '*/*'),
        ]
        urllib.request.install_opener(opener)
        
        def report_progress(block_num, block_size, total_size):
            if total_size > 0:
                downloaded = block_num * block_size
                percent = min(downloaded * 100 / total_size, 100)
                mb = downloaded / (1024 * 1024)
                total_mb = total_size / (1024 * 1024)
                print(f"\r  Progress: {percent:.1f}% ({mb:.1f}/{total_mb:.1f} MB)", end="", flush=True)
        
        urllib.request.urlretrieve(url, str(dest), reporthook=report_progress)
        print()
        
        file_size = dest.stat().st_size / (1024**2)
        print(f"  [OK] Done ({file_size:.1f} MB)")
        return True
    except Exception as e:
        print(f"\n  [ERROR] {e}")
        if dest.exists():
            try:
                dest.unlink()
            except:
                pass
        return False

def check_model_link_status():
    """Check if models are linked from external source."""
    config_path = COMFYUI_DIR / ".model_config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
                return config.get("external_models_dir", "")
        except:
            pass
    return ""

def create_readme():
    """Create a README with manual download instructions."""
    readme_path = MODELS_DIR / "README_MODELS.txt"
    content = """========================================
AI Shorts Creator - Model Setup Guide
========================================

This folder contains AI models for the built-in ComfyUI.

REQUIRED MODELS:
----------------

1. Z-Image Turbo (Image Generation)
   File: checkpoints/z_image_turbo_bf16.safetensors
   Source: https://huggingface.co/ZImageTeam/Z-Image-Turbo
   
   The app searches recursively, so you can place it in:
   - models/checkpoints/
   - models/diffusion_models/IMAGE/Z IMAGE/
   - Or any subfolder

2. LTX Video (Video Generation)
   File: checkpoints/ltx-*.safetensors
   Source: https://huggingface.co/Lightricks/LTX-Video

3. VAE (Required for Z-Image Turbo)
   File: vae/ae.safetensors
   
4. CLIP Model (Required for Z-Image Turbo)
   File: clip/qwen_3_4b.safetensors
   Source: https://huggingface.co/ZImageTeam/Z-Image-Turbo

LINKING EXISTING MODELS:
------------------------
If you already have ComfyUI installed elsewhere, you can link its models
folder instead of downloading duplicates:

1. Go to Settings in the web UI
2. Under "AI Models", enter your existing ComfyUI models path
3. Click "Link Models"

Example paths:
- F:\\ComfyUI\\models
- F:\\001 Comfyui Easy installer\\ComfyUI-Easy-Install\\ComfyUI-Easy-Install\\ComfyUI\\models

OPTIONAL STYLE LoRAs:
--------------------
Place .safetensors LoRA files in: models/loras/

Supported styles (case-insensitive):
- Studio_Ghibli.safetensors
- Cinematic.safetensors
- Anime.safetensors
- Realistic.safetensors
- Cyberpunk.safetensors
- Comic.safetensors
- Horror.safetensors
- Documentary.safetensors

Download LoRAs from:
- CivitAI: https://civitai.com
- HuggingFace: https://huggingface.co

The app works without LoRAs (uses base model).
"""
    
    with open(readme_path, "w") as f:
        f.write(content)
    
    print(f"\n[OK] Created model setup guide: {readme_path}")

def main():
    print("=" * 60)
    print("AI Shorts Creator - Model Setup")
    print("=" * 60)
    
    vram = get_vram_gb()
    print(f"\nDetected GPU VRAM: {vram:.1f} GB")
    
    if vram >= 16:
        print("Tier: HIGH VRAM (16GB+) - Full quality models")
    elif vram >= 12:
        print("Tier: MEDIUM VRAM (12-16GB) - Standard models")
    elif vram >= 8:
        print("Tier: LOW VRAM (8-12GB) - Optimized models")
    else:
        print("Tier: MINIMAL VRAM (<8GB) - Lightweight models")
    
    # Check if models are linked
    external_dir = check_model_link_status()
    if external_dir:
        print(f"\n[OK] Models are linked from: {external_dir}")
    
    print(f"\nModel directories:")
    print(f"  Checkpoints: {CHECKPOINTS_DIR}")
    print(f"  VAE: {VAE_DIR}")
    print(f"  LoRAs: {LORA_DIR}")
    print(f"  CLIP: {CLIP_DIR}")
    print(f"  Diffusion: {DIFFUSION_DIR}")
    
    results = {}
    
    # === CHECK MODELS ===
    print("\n" + "=" * 60)
    print("CHECKING MODELS")
    print("=" * 60)
    
    # Z-Image Turbo - Search recursively
    print("\n1. Z-Image Turbo (Image Generation)")
    z_image_path = find_z_image_turbo()
    if z_image_path:
        size_gb = z_image_path.stat().st_size / (1024**3)
        print(f"   [OK] Found: {z_image_path.relative_to(MODELS_DIR)}")
        print(f"   Size: {size_gb:.2f} GB")
        results["z_image_turbo"] = True
    else:
        print("   [NOT FOUND] Z-Image Turbo not found")
        print("   Searched in: checkpoints/, diffusion_models/, and subfolders")
        print("   Source: https://huggingface.co/ZImageTeam/Z-Image-Turbo")
        results["z_image_turbo"] = False
    
    # LTX Video - Search recursively
    print("\n2. LTX Video (Video Generation)")
    ltx_path = find_ltx_video()
    if ltx_path:
        size_gb = ltx_path.stat().st_size / (1024**3)
        print(f"   [OK] Found: {ltx_path.relative_to(MODELS_DIR)}")
        print(f"   Size: {size_gb:.2f} GB")
        results["ltx_video"] = True
    else:
        print("   [NOT FOUND] LTX Video not found")
        print("   Download from: https://huggingface.co/Lightricks/LTX-Video")
        results["ltx_video"] = False
    
    # VAE
    print("\n3. VAE (ae.safetensors)")
    vae_path = find_vae()
    if vae_path:
        size_mb = vae_path.stat().st_size / (1024**2)
        print(f"   [OK] Found: {vae_path.relative_to(MODELS_DIR)}")
        print(f"   Size: {size_mb:.1f} MB")
        results["vae"] = True
    else:
        print("   [NOT FOUND] VAE not found")
        results["vae"] = False
    
    # CLIP
    print("\n4. CLIP Model (qwen_3_4b.safetensors)")
    clip_path = find_clip()
    if clip_path:
        size_gb = clip_path.stat().st_size / (1024**3)
        print(f"   [OK] Found: {clip_path.relative_to(MODELS_DIR)}")
        print(f"   Size: {size_gb:.2f} GB")
        results["clip"] = True
    else:
        print("   [NOT FOUND] CLIP model not found")
        print("   Source: https://huggingface.co/ZImageTeam/Z-Image-Turbo")
        results["clip"] = False
    
    # === CHECK LoRAs ===
    print("\n" + "=" * 60)
    print("STYLE LoRAs")
    print("=" * 60)
    
    expected_loras = [
        "Studio_Ghibli.safetensors",
        "Cinematic.safetensors",
        "Anime.safetensors",
        "Realistic.safetensors",
        "Cyberpunk.safetensors",
        "Comic.safetensors",
        "Horror.safetensors",
        "Documentary.safetensors",
    ]
    
    lora_count = 0
    print("\nChecking installed LoRAs:")
    for name in expected_loras:
        # Search in loras folder and subfolders
        matches = find_file_recursively(LORA_DIR, name)
        if not matches:
            # Also check for partial matches
            matches = find_file_recursively(LORA_DIR, name.replace("_", "*"))
        
        if matches:
            print(f"  [OK] {name}")
            lora_count += 1
        else:
            print(f"  [MISSING] {name}")
    
    # Also list any other LoRAs found
    all_loras = list(LORA_DIR.rglob("*.safetensors"))
    other_loras = [l for l in all_loras if l.name not in expected_loras]
    if other_loras:
        print(f"\n  Other LoRAs found ({len(other_loras)}):")
        for lora in other_loras[:10]:
            print(f"    - {lora.relative_to(MODELS_DIR)}")
        if len(other_loras) > 10:
            print(f"    ... and {len(other_loras) - 10} more")
    
    print(f"\nTotal style LoRAs: {lora_count}/{len(expected_loras)}")
    
    # === SUMMARY ===
    print("\n" + "=" * 60)
    print("SETUP SUMMARY")
    print("=" * 60)
    
    essential_ready = True
    
    if results.get("z_image_turbo"):
        print("[OK] Z-Image Turbo: Ready")
    else:
        print("[MISSING] Z-Image Turbo: Not found")
        essential_ready = False
    
    if results.get("ltx_video"):
        print("[OK] LTX Video: Ready")
    else:
        print("[MISSING] LTX Video: Not found")
    
    if results.get("vae"):
        print("[OK] VAE: Ready")
    else:
        print("[MISSING] VAE: Not found")
        essential_ready = False
    
    if results.get("clip"):
        print("[OK] CLIP: Ready")
    else:
        print("[MISSING] CLIP: Not found")
        essential_ready = False
    
    print(f"LoRAs: {lora_count} style LoRAs installed")
    
    print("\n" + "-" * 60)
    if essential_ready:
        print("Essential models are ready!")
        print("You can now use AI-generated visuals.")
    else:
        print("Some essential models are missing.")
        print("The app can still use stock footage as fallback.")
    
    if external_dir:
        print(f"\nModels linked from: {external_dir}")
        print("To update models, add them to your external ComfyUI folder.")
    
    # Create README
    create_readme()
    
    # Save manifest
    manifest = {
        "tier": "medium" if vram >= 12 else "low" if vram >= 8 else "minimal",
        "vram_gb": round(vram, 1),
        "models": {
            "z_image_turbo": str(z_image_path.relative_to(MODELS_DIR)) if z_image_path else None,
            "ltx_video": str(ltx_path.relative_to(MODELS_DIR)) if ltx_path else None,
            "vae": str(vae_path.relative_to(MODELS_DIR)) if vae_path else None,
            "clip": str(clip_path.relative_to(MODELS_DIR)) if clip_path else None,
        },
        "loras": lora_count,
        "external_models_dir": external_dir,
        "models_linked": bool(external_dir),
    }
    
    manifest_path = MODELS_DIR / ".manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    print(f"\nManifest saved to: {manifest_path}")
    print("\nDone!")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
