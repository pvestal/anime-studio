# Archived Standalone Service

This directory contains the standalone anime_service.py that was causing port conflicts.

## Archive Date: Sun Nov  2 08:57:25 PM UTC 2025
## Reason: Duplicate service conflict with systemd tower-anime-production.service
## Status: Replaced by production systemd service at /opt/tower-anime-production/api/main.py

The standalone service has been archived to prevent future port 8328 conflicts.
Use the systemd service for all anime generation:

sudo systemctl status tower-lora-studio
curl -s http://localhost:8401/api/lora/health

---

## Anime Frontend Archived: 2026-02-12

**Reason:** Consolidated into LoRA Studio. All generation, gallery, and Echo Brain
functionality migrated to the 7-tab LoRA Studio UI at `/lora-studio/`.

- Frontend source moved to `frontend.archived/`
- Anime Production API (port 8328) stopped and disabled
- nginx `/anime/` now 301 redirects to `/lora-studio/`
- All `/api/anime/*` endpoints replaced by `/api/lora/*` in LoRA Studio

