#!/usr/bin/env python3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
import uvicorn
import json

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    return psycopg2.connect(
        host="localhost",
        database="anime_production",
        user="patrick",
        password="",
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
    uvicorn.run(app, host="127.0.0.1", port=8323)
