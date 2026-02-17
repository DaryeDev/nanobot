import json
import time
import uuid
from pathlib import Path
import os

JOBS_FILE = Path.home() / ".nanobot" / "cron" / "jobs.json"

def add_notification(subject: str = "External Notification", message: str = "Say hello to the User."):
    if not JOBS_FILE.exists():
        print(f"Error: No se encontró el archivo en {JOBS_FILE}")
        # Crear estructura básica si no existe
        JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        initial_data = {"version": 1, "jobs": []}
        JOBS_FILE.write_text(json.dumps(initial_data, indent=2))
        print(f"Creado archivo nuevo en {JOBS_FILE}")

    try:
        data = json.loads(JOBS_FILE.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"Error leyendo JSON: {e}")
        return

    now_ms = int(time.time() * 1000)
    job_id = str(uuid.uuid4())[:8]

    new_job = {
        "id": job_id,
        "name": subject,
        "enabled": True,
        "schedule": {
            "kind": "at",
            "atMs": 0,
            "everyMs": None,
            "expr": None,
            "tz": None
        },
        "payload": {
            "kind": "agent_turn",
            "message": message,
            "deliver": False,
            "channel": "telegram",
            "to": "6519163070"
        },
        "state": {
            "nextRunAtMs": now_ms, 
            "lastRunAtMs": None,
            "lastStatus": None,
            "lastError": None
        },
        "createdAtMs": now_ms,
        "updatedAtMs": now_ms,
        "deleteAfterRun": True
    }

    data["jobs"].append(new_job)

    JOBS_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')
    
    print(f"Notification injected successfully!")

if __name__ == "__main__":
    add_notification(subject="Twitch Notification: New Subscriber", message="Notify the User: holaCaracola57 se ha suscrito en Twitch!")