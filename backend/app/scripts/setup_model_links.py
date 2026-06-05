import os
import sys
import subprocess
from pathlib import Path
import json

def create_junction(target: Path, link_name: Path):
    """Create a Windows junction (directory symlink) without admin."""
    try:
        # Remove existing junction or directory
        if link_name.exists():
            if link_name.is_dir() and not link_name.is_symlink():
                # It's a real directory, backup it
                backup = link_name.parent / f"{link_name.name}_backup"
                link_name.rename(backup)
                print(f"  Backed up existing directory to: {backup}")
            else:
                link_name.unlink()
        
        # Create junction using mklink /J
        cmd = ['cmd', '/c', 'mklink', '/J', str(link_name), str(target)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"  [OK] Linked: {link_name.name}")
            return True
        else:
            print(f"  [FAIL] {result.stderr}")
            return False
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False

def setup_model_links(external_models_dir: str, app_models_dir: str):
    """Create junctions from external ComfyUI models to app models."""
    
    external_path = Path(external_models_dir)
    app_path = Path(app_models_dir)
    
    if not external_path.exists():
        print(f"[ERROR] External models directory not found: {external_path}")
        return False
    
    print(f"External models: {external_path}")
    print(f"App models:      {app_path}")
    print()
    
    # Ensure app models directory exists
    app_path.mkdir(parents=True, exist_ok=True)
    
    # Map of folders to link
    folders_to_link = {
        "checkpoints": "checkpoints",
        "loras": "loras",
        "vae": "vae",
        "clip": "clip",
        "clip_vision": "clip_vision",
        "controlnet": "controlnet",
        "embeddings": "embeddings",
        "upscale_models": "upscale_models",
        "diffusion_models": "diffusion_models",
        "text_encoders": "text_encoders",
        "unet": "unet",
        "gligen": "gligen",
        "hypernetworks": "hypernetworks",
        "style_models": "style_models",
        "photomaker": "photomaker",
    }
    
    linked = []
    skipped = []
    
    for source_name, dest_name in folders_to_link.items():
        source = external_path / source_name
        dest = app_path / dest_name
        
        if source.exists():
            print(f"Linking {source_name}...")
            if create_junction(source, dest):
                linked.append(source_name)
            else:
                skipped.append(source_name)
        else:
            print(f"[SKIP] {source_name} (not found in external folder)")
            skipped.append(source_name)
    
    print(f"\n{'='*50}")
    print(f"Linked {len(linked)} folders: {', '.join(linked)}")
    if skipped:
        print(f"Skipped {len(skipped)} folders")
    
    # Save config
    config_path = app_path.parent / ".model_config.json"
    with open(config_path, "w") as f:
        json.dump({
            "external_models_dir": str(external_path),
            "linked_folders": linked,
            "skipped_folders": skipped,
        }, f, indent=2)
    
    print(f"\nConfig saved to: {config_path}")
    return True

def remove_links(app_models_dir: str):
    """Remove all junctions and restore backed-up directories."""
    app_path = Path(app_models_dir)
    
    if not app_path.exists():
        return
    
    for item in app_path.iterdir():
        if item.is_symlink() or item.is_junction():
            print(f"Removing link: {item.name}")
            item.unlink()
        elif item.is_dir() and item.name.endswith("_backup"):
            # Restore backup
            original_name = item.name.replace("_backup", "")
            original = app_path / original_name
            item.rename(original)
            print(f"Restored: {original_name}")

def main():
    if len(sys.argv) < 3:
        print("Usage: python setup_model_links.py <external_models_dir> <app_models_dir>")
        print()
        print("Example:")
        print(r'  python setup_model_links.py "F:\ComfyUI\models" "D:\Pinokio_new\api\ai-shorts-creator\backend\comfyui\ComfyUI\models"')
        print()
        print("Or run with the default path:")
        print(r'  python setup_model_links.py "F:\001 Comfyui Easy installer\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\models" "backend\comfyui\ComfyUI\models"')
        sys.exit(1)
    
    external_dir = sys.argv[1]
    app_dir = sys.argv[2]
    
    # If app_dir is relative, resolve it
    app_path = Path(app_dir)
    if not app_path.is_absolute():
        app_path = Path.cwd() / app_path
    
    success = setup_model_links(external_dir, str(app_path))
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
