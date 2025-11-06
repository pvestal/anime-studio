#!/usr/bin/env python3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
import uvicorn
import json
import os
import hvac

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_vault_secret(path):
    """Get secret from HashiCorp Vault"""
    try:
        vault_url = os.getenv('VAULT_ADDR', 'http://127.0.0.1:8200')
        vault_token = os.getenv('VAULT_TOKEN')

        if not vault_token:
            raise Exception("VAULT_TOKEN environment variable not set")

        client = hvac.Client(url=vault_url, token=vault_token)
        response = client.secrets.kv.v2.read_secret_version(path=path)
        return response['data']['data']
    except Exception as e:
        print(f"Vault error: {e}")
        # Fallback for now but this should be removed in production
        return {
            'host': '***REMOVED***',
            'database': 'anime_production',
            'user': 'patrick',
            'password': '***REMOVED***'
        }

def get_db():
    db_config = get_vault_secret('tower/database')
    return psycopg2.connect(
        host=db_config['host'],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password'],
        cursor_factory=RealDictCursor
    )

@app.get("/api/anime/episodes")
async def list_episodes():
    """Get all actual episodes from the database"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM episodes ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        episodes = []
        for row in rows:
            episodes.append({
                "id": str(row["id"]),
                "episode_number": row["episode_number"],
                "title": row["title"],
                "synopsis": row["synopsis"],
                "duration": row["duration"],
                "status": row["status"],
                "scenes": row["scenes"],
                "characters": row["characters"],
                "metadata": row["metadata"],
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
                "video_path": row.get("video_path"),
                "quality_score": row.get("quality_score", 0.0)
            })
        
        return episodes
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/anime/health")
async def health():
    return {"status": "healthy", "service": "episodes-api"}

if __name__ == "__main__":
    # Get port from environment or default
    port = int(os.getenv('EPISODE_API_PORT', 8323))
    # Bind to all interfaces for network access
    uvicorn.run(app, host="0.0.0.0", port=port)
