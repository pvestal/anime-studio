"""Tests for character profile bible endpoints — detail, multi-field PATCH, character_profile narration."""

import json
from datetime import datetime

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# GET /characters/{slug}/detail
# ---------------------------------------------------------------------------

@pytest.mark.unit
async def test_get_character_detail(app_client):
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={
        "id": 24,
        "name": "Mario",
        "description": "The plumber hero",
        "design_prompt": "short stocky man, red cap",
        "traits": None,
        "age": 26,
        "appearance_data": json.dumps({
            "species": "human",
            "key_colors": {"cap": "red"},
            "hair": {"color": "brown"},
        }),
        "personality": "Heroic and cheerful",
        "background": "From the Mushroom Kingdom",
        "role": None,
        "character_role": "protagonist",
        "personality_tags": ["heroic", "cheerful"],
        "relationships": json.dumps({"luigi": "brother"}),
        "voice_profile": None,
        "lora_trigger": "mario",
        "lora_path": None,
        "created_at": datetime(2026, 1, 27, 22, 0, 0),
        "updated_at": datetime(2026, 2, 24, 1, 0, 0),
        "project_id": 41,
        "project_name": "Mario Galaxy",
    })
    mock_conn.close = AsyncMock()
    with patch(
        "packages.story.story_characters.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ):
        resp = await app_client.get("/api/story/characters/mario/detail")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 24
        assert data["name"] == "Mario"
        assert data["slug"] == "mario"
        assert data["project_name"] == "Mario Galaxy"
        assert data["description"] == "The plumber hero"
        assert data["age"] == 26
        assert data["character_role"] == "protagonist"
        assert data["personality"] == "Heroic and cheerful"
        assert data["personality_tags"] == ["heroic", "cheerful"]
        assert data["lora_trigger"] == "mario"
        # JSONB fields should be parsed
        assert data["appearance_data"]["species"] == "human"
        assert data["appearance_data"]["key_colors"]["cap"] == "red"
        assert data["appearance_data"]["hair"]["color"] == "brown"
        assert data["relationships"]["luigi"] == "brother"


@pytest.mark.unit
async def test_get_character_detail_not_found(app_client):
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.close = AsyncMock()
    with patch(
        "packages.story.story_characters.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ):
        resp = await app_client.get("/api/story/characters/nonexistent/detail")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


@pytest.mark.unit
async def test_get_character_detail_null_jsonb(app_client):
    """Null JSONB/timestamp fields should return None, not crash."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={
        "id": 1, "name": "Ghost", "description": None, "design_prompt": None,
        "traits": None, "age": None, "appearance_data": None, "personality": None,
        "background": None, "role": None, "character_role": None, "personality_tags": None,
        "relationships": None, "voice_profile": None, "lora_trigger": None, "lora_path": None,
        "created_at": None, "updated_at": None, "project_id": 1, "project_name": "Test",
    })
    mock_conn.close = AsyncMock()
    with patch(
        "packages.story.story_characters.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ):
        resp = await app_client.get("/api/story/characters/ghost/detail")
        assert resp.status_code == 200
        data = resp.json()
        assert data["appearance_data"] is None
        assert data["traits"] is None
        assert data["created_at"] is None


# ---------------------------------------------------------------------------
# PATCH /characters/{slug} — multi-field update
# ---------------------------------------------------------------------------

@pytest.mark.unit
async def test_patch_character_design_prompt_only(app_client):
    """Backward compat: design_prompt-only PATCH still works."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"id": 24, "name": "Mario", "project_id": 41})
    mock_conn.execute = AsyncMock()
    mock_conn.close = AsyncMock()
    with patch(
        "packages.story.story_characters.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ), patch("packages.story.story_characters.invalidate_char_cache"):
        resp = await app_client.patch("/api/story/characters/mario", json={
            "design_prompt": "updated prompt text",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated_fields"] == ["design_prompt"]
        assert data["character_name"] == "Mario"
        # Verify SQL was called with correct params
        mock_conn.execute.assert_called_once()
        sql = mock_conn.execute.call_args[0][0]
        assert "design_prompt=" in sql
        assert "updated_at=NOW()" in sql


@pytest.mark.unit
async def test_patch_character_multiple_fields(app_client):
    """Multi-field PATCH with text, int, and text[] fields."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"id": 24, "name": "Mario", "project_id": 41})
    mock_conn.execute = AsyncMock()
    mock_conn.close = AsyncMock()
    with patch(
        "packages.story.story_characters.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ), patch("packages.story.story_characters.invalidate_char_cache"):
        resp = await app_client.patch("/api/story/characters/mario", json={
            "description": "The hero plumber",
            "age": 26,
            "personality_tags": ["heroic", "cheerful"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert set(data["updated_fields"]) == {"description", "age", "personality_tags"}
        # Verify SQL includes all fields + updated_at
        sql = mock_conn.execute.call_args[0][0]
        assert "description=" in sql
        assert "age=" in sql
        assert "personality_tags=" in sql
        assert "::text[]" in sql
        assert "updated_at=NOW()" in sql


@pytest.mark.unit
async def test_patch_character_jsonb_field(app_client):
    """JSONB fields (appearance_data, traits) get ::jsonb cast."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"id": 24, "name": "Mario", "project_id": 41})
    mock_conn.execute = AsyncMock()
    mock_conn.close = AsyncMock()
    with patch(
        "packages.story.story_characters.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ), patch("packages.story.story_characters.invalidate_char_cache"):
        appearance = {
            "species": "human",
            "key_colors": {"cap": "red"},
            "hair": {"color": "brown", "style": "hidden", "length": "short"},
        }
        resp = await app_client.patch("/api/story/characters/mario", json={
            "appearance_data": appearance,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated_fields"] == ["appearance_data"]
        sql = mock_conn.execute.call_args[0][0]
        assert "::jsonb" in sql
        # The JSON string should be passed as a parameter
        args = mock_conn.execute.call_args[0]
        assert json.loads(args[1]) == appearance


@pytest.mark.unit
async def test_patch_character_no_valid_fields(app_client):
    """PATCH with no valid fields returns 400."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"id": 24, "name": "Mario", "project_id": 41})
    mock_conn.close = AsyncMock()
    with patch(
        "packages.story.story_characters.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ):
        resp = await app_client.patch("/api/story/characters/mario", json={
            "invalid_field": "bad",
            "another_bad": 123,
        })
        assert resp.status_code == 400
        assert "No valid fields" in resp.json()["detail"]


@pytest.mark.unit
async def test_patch_character_not_found(app_client):
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.close = AsyncMock()
    with patch(
        "packages.story.story_characters.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ):
        resp = await app_client.patch("/api/story/characters/nonexistent", json={
            "design_prompt": "test",
        })
        assert resp.status_code == 404


@pytest.mark.unit
async def test_patch_character_all_field_types(app_client):
    """Full PATCH with every field type: text, int, jsonb, text[]."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"id": 1, "name": "Test", "project_id": 1})
    mock_conn.execute = AsyncMock()
    mock_conn.close = AsyncMock()
    with patch(
        "packages.story.story_characters.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ), patch("packages.story.story_characters.invalidate_char_cache"):
        resp = await app_client.patch("/api/story/characters/test", json={
            "design_prompt": "visual prompt",
            "description": "A test character",
            "personality": "Bold and brave",
            "background": "From a test project",
            "role": "warrior",
            "character_role": "protagonist",
            "age": 30,
            "personality_tags": ["bold", "brave"],
            "traits": {"strength": "high"},
            "appearance_data": {"species": "human"},
            "relationships": {"ally": "friend"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["updated_fields"]) == 11


# ---------------------------------------------------------------------------
# POST /echo/narrate — character_profile context_type
# ---------------------------------------------------------------------------

def _make_urlopen_response(data: dict):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(data).encode()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


@pytest.mark.unit
async def test_narrate_character_profile(app_client):
    """character_profile narration returns structured fields."""
    profile_json = {
        "description": "A cyberpunk warrior",
        "personality": "Stoic and determined",
        "background": "Lost family to goblins",
        "age": 28,
        "character_role": "protagonist",
        "personality_tags": ["stoic", "determined"],
        "design_prompt": "armored warrior, dark anime style",
        "species": "human",
        "body_type": "muscular",
        "key_colors": {"armor": "black", "eyes": "red"},
        "key_features": ["full helmet", "battle scars"],
        "common_errors": [],
        "hair": {"color": "silver", "style": "short", "length": "short"},
        "eyes": {"color": "red", "shape": "narrow", "special": "glow"},
        "skin": {"tone": "pale", "markings": "scars on arms"},
        "face": {"shape": "angular", "features": "sharp jaw"},
        "body": {"build": "muscular", "height": "6'0\""},
        "clothing": {"default_outfit": "dark armor", "style": "medieval cyberpunk"},
        "weapons": [{"name": "broadsword", "type": "melee", "description": "large blade"}],
        "accessories": ["metal gauntlets"],
        "sexual": {"orientation": "heterosexual", "preferences": "", "physical_traits": "athletic"},
    }
    echo_response = {
        "answer": json.dumps(profile_json),
        "sources": [],
        "confidence": 0.85,
    }
    mock_resp = _make_urlopen_response(echo_response)
    with patch("packages.echo_integration.router._ur.urlopen", return_value=mock_resp):
        resp = await app_client.post("/api/echo/narrate", json={
            "context_type": "character_profile",
            "character_name": "Goblin Slayer",
            "project_name": "Cyberpunk Goblin Slayer",
            "project_genre": "cyberpunk action",
            "design_prompt": "dark warrior in armor",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["context_type"] == "character_profile"
        assert "fields" in data
        fields = data["fields"]
        assert fields["description"] == "A cyberpunk warrior"
        assert fields["character_role"] == "protagonist"
        assert fields["age"] == 28
        assert fields["personality_tags"] == ["stoic", "determined"]
        assert fields["species"] == "human"
        assert fields["key_colors"]["armor"] == "black"
        assert fields["hair"]["color"] == "silver"
        assert len(fields["weapons"]) == 1
        assert fields["weapons"][0]["name"] == "broadsword"


@pytest.mark.unit
async def test_narrate_character_profile_bad_json(app_client):
    """character_profile with non-JSON response falls back to text suggestion."""
    echo_response = {
        "answer": "Here is a character description that is not JSON formatted.",
        "sources": [],
        "confidence": 0.5,
    }
    mock_resp = _make_urlopen_response(echo_response)
    with patch("packages.echo_integration.router._ur.urlopen", return_value=mock_resp):
        resp = await app_client.post("/api/echo/narrate", json={
            "context_type": "character_profile",
            "character_name": "Test",
            "project_name": "Test Project",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["context_type"] == "character_profile"
        # No fields parsed, but suggestion text is still returned
        assert "suggestion" in data
        assert data.get("fields") is None


@pytest.mark.unit
async def test_narrate_character_profile_prompt_includes_context(app_client):
    """Verify the built prompt includes character name, project, genre, and design prompt."""
    captured_url = None
    captured_data = None

    def _capture_urlopen(req, **kwargs):
        nonlocal captured_url, captured_data
        captured_url = req.full_url
        captured_data = json.loads(req.data)
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "answer": '{"description":"test"}',
            "sources": [],
            "confidence": 0.5,
        }).encode()
        return mock_resp

    with patch("packages.echo_integration.router._ur.urlopen", side_effect=_capture_urlopen):
        resp = await app_client.post("/api/echo/narrate", json={
            "context_type": "character_profile",
            "character_name": "Goblin Slayer",
            "project_name": "Neon Shadows",
            "project_genre": "cyberpunk",
            "project_premise": "Goblins in a cyberpunk world",
            "design_prompt": "armored dark warrior",
        })
        assert resp.status_code == 200
        # Check the prompt sent to Echo Brain includes our context
        question = captured_data["question"]
        assert "Goblin Slayer" in question
        assert "Neon Shadows" in question
        assert "cyberpunk" in question
        assert "armored dark warrior" in question
        assert "character bible" in question.lower() or "comprehensive" in question.lower()


# ---------------------------------------------------------------------------
# Integration: detail → patch → detail round-trip (mock DB)
# ---------------------------------------------------------------------------

@pytest.mark.unit
async def test_patch_then_detail_round_trip(app_client):
    """Simulate: load detail, patch fields, load detail again."""
    stored_data = {
        "id": 50, "name": "Rosalina", "description": None, "design_prompt": "space princess",
        "traits": None, "age": None, "appearance_data": None, "personality": None,
        "background": None, "role": None, "character_role": None, "personality_tags": None,
        "relationships": None, "voice_profile": None, "lora_trigger": None, "lora_path": None,
        "created_at": datetime(2026, 2, 24), "updated_at": datetime(2026, 2, 24),
        "project_id": 41, "project_name": "Mario Galaxy",
    }

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=stored_data)
    mock_conn.close = AsyncMock()

    # Step 1: GET detail — should show null fields
    with patch(
        "packages.story.story_characters.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ):
        resp = await app_client.get("/api/story/characters/rosalina/detail")
        assert resp.status_code == 200
        assert resp.json()["description"] is None

    # Step 2: PATCH with new data
    mock_conn2 = AsyncMock()
    mock_conn2.fetchrow = AsyncMock(return_value={"id": 50, "name": "Rosalina", "project_id": 41})
    mock_conn2.execute = AsyncMock()
    mock_conn2.close = AsyncMock()
    with patch(
        "packages.story.story_characters.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn2,
    ), patch("packages.story.story_characters.invalidate_char_cache"):
        resp = await app_client.patch("/api/story/characters/rosalina", json={
            "description": "Guardian of the cosmos",
            "age": 1000,
            "character_role": "mentor",
            "appearance_data": {
                "species": "cosmic being",
                "hair": {"color": "platinum blonde", "style": "flowing", "length": "very long"},
            },
        })
        assert resp.status_code == 200
        assert set(resp.json()["updated_fields"]) == {"description", "age", "character_role", "appearance_data"}

    # Step 3: GET detail again — simulate updated DB row
    updated_data = {**stored_data}
    updated_data["description"] = "Guardian of the cosmos"
    updated_data["age"] = 1000
    updated_data["character_role"] = "mentor"
    updated_data["appearance_data"] = json.dumps({
        "species": "cosmic being",
        "hair": {"color": "platinum blonde", "style": "flowing", "length": "very long"},
    })
    updated_data["updated_at"] = datetime(2026, 2, 24, 2, 0, 0)

    mock_conn3 = AsyncMock()
    mock_conn3.fetchrow = AsyncMock(return_value=updated_data)
    mock_conn3.close = AsyncMock()
    with patch(
        "packages.story.story_characters.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn3,
    ):
        resp = await app_client.get("/api/story/characters/rosalina/detail")
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "Guardian of the cosmos"
        assert data["age"] == 1000
        assert data["character_role"] == "mentor"
        assert data["appearance_data"]["species"] == "cosmic being"
        assert data["appearance_data"]["hair"]["color"] == "platinum blonde"
