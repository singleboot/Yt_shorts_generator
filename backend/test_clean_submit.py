import sys
from app.database import SessionLocal
from app.services.scheduler import scheduler_service
import app.models as models

print("Starting clean-scenes test...")
result = scheduler_service.cleanup_intermediate_scenes(project_id=1, video_index=3)
print("Result:", result)
sys.exit(0)
