#!/usr/bin/env python3
"""
Comprehensive tests for UX Enhancement Module
Tests real-time preview, contextual progress, and smart error recovery
"""

import asyncio
import base64
import json
import sys
import time
from unittest.mock import AsyncMock, Mock

import pytest

# Add the API directory to the path
sys.path.insert(0, '/opt/tower-anime-production/api')

from ux_enhancements import (ContextualProgressTracker, GenerationPhase, PreviewGenerator,
                             ProgressUpdate, SmartErrorRecovery, UXEnhancementManager)


class TestGenerationPhase:
    """Test generation phase enum"""


    def test_phase_progression(self):
        """Test that phases progress in correct order"""
        phases = list(GenerationPhase)
        for i, phase in enumerate(phases[:-1]):
            next_phase = phases[i + 1]
            assert phase.end_percent <= next_phase.start_percent


    def test_phase_messages(self):
        """Test that all phases have user-friendly messages"""
        for phase in GenerationPhase:
            assert phase.message
            assert len(phase.message) > 5
            assert phase.start_percent >= 0
            assert phase.end_percent <= 100


class TestProgressUpdate:
    """Test progress update data structure"""


    def test_websocket_message_format(self):
        """Test WebSocket message serialization"""
        update = ProgressUpdate(
            job_id="test-123",
            phase=GenerationPhase.GENERATING_LATENTS,
            current_step=5,
            total_steps=20,
            message="Creating composition",
            percentage=25.0,
            preview_image="data:image/jpeg;base64,test",
            estimated_time_remaining=15.5
        )

        message = update.to_websocket_message()
        data = json.loads(message)

        assert data["type"] == "progress"
        assert data["job_id"] == "test-123"
        assert data["phase"] == "GENERATING_LATENTS"
        assert data["percentage"] == 25.0
        assert data["preview_image"] == "data:image/jpeg;base64,test"


class TestPreviewGenerator:
    """Test preview image generation"""

    @pytest.fixture


    def preview_gen(self):
        return PreviewGenerator()

    @pytest.mark.asyncio


    async def test_generate_preview_from_latents(self, preview_gen, tmp_path):
        """Test preview generation from image file"""
        # Create a test image
        from PIL import Image
        test_image = Image.new('RGB', (512, 512), color='red')
        test_path = tmp_path / "test.jpg"
        test_image.save(test_path)

        # Generate preview
        preview = await preview_gen.generate_preview_from_latents(str(test_path))

        assert preview is not None
        assert preview.startswith("data:image/jpeg;base64,")

        # Decode and verify it's valid base64
        base64_data = preview.split(",")[1]
        decoded = base64.b64decode(base64_data)
        assert len(decoded) > 0

    @pytest.mark.asyncio


    async def test_preview_with_missing_file(self, preview_gen):
        """Test preview generation with missing file"""
        preview = await preview_gen.generate_preview_from_latents("/nonexistent/file.jpg")
        assert preview is None

    @pytest.mark.asyncio


    async def test_progress_visualization(self, preview_gen):
        """Test progress bar visualization creation"""
        preview = await preview_gen.create_progress_visualization(
            percentage=50.0,
            phase=GenerationPhase.REFINING_DETAILS
        )

        assert preview.startswith("data:image/jpeg;base64,")


class TestContextualProgressTracker:
    """Test contextual progress tracking"""

    @pytest.fixture


    def tracker(self):
        preview_gen = PreviewGenerator()
        return ContextualProgressTracker(preview_gen)


    def test_start_job(self, tracker):
        """Test job initialization"""
        tracker.start_job("job-123", total_steps=30)

        assert "job-123" in tracker.job_progress
        assert tracker.job_progress["job-123"]["total_steps"] == 30
        assert tracker.job_progress["job-123"]["current_step"] == 0


    def test_phase_tracking(self, tracker):
        """Test phase transition tracking"""
        tracker.start_job("job-456")

        tracker.update_phase("job-456", GenerationPhase.LOADING_MODELS)
        assert tracker.job_progress["job-456"]["phase"] == GenerationPhase.LOADING_MODELS

        time.sleep(0.1)  # Let some time pass
        tracker.update_phase("job-456", GenerationPhase.PROCESSING_PROMPT)

        # Check that phase time was tracked
        assert "LOADING_MODELS" in tracker.job_progress["job-456"]["phase_times"]
        assert tracker.job_progress["job-456"]["phase_times"]["LOADING_MODELS"] > 0


    def test_time_estimation(self, tracker):
        """Test remaining time estimation"""
        tracker.start_job("job-789", total_steps=10)

        # No estimation at step 0
        assert tracker.estimate_time_remaining("job-789") is None

        # Simulate progress
        tracker.job_progress["job-789"]["current_step"] = 5
        time.sleep(0.1)

        estimate = tracker.estimate_time_remaining("job-789")
        assert estimate is not None
        assert estimate > 0

    @pytest.mark.asyncio


    async def test_progress_update_creation(self, tracker):
        """Test creating rich progress updates"""
        tracker.start_job("job-999", total_steps=20)

        update = await tracker.create_progress_update(
            job_id="job-999",
            current_step=10,
            custom_message="Custom progress message"
        )

        assert update.job_id == "job-999"
        assert update.current_step == 10
        assert update.percentage == 50.0
        assert update.message == "Custom progress message"
        assert update.phase == GenerationPhase.GENERATING_LATENTS


    def test_phase_determination(self, tracker):
        """Test correct phase determination based on percentage"""
        assert tracker._determine_phase(3) == GenerationPhase.INITIALIZING
        assert tracker._determine_phase(10) == GenerationPhase.LOADING_MODELS
        assert tracker._determine_phase(30) == GenerationPhase.GENERATING_LATENTS
        assert tracker._determine_phase(60) == GenerationPhase.REFINING_DETAILS
        assert tracker._determine_phase(100) == GenerationPhase.COMPLETE


    def test_contextual_message_generation(self, tracker):
        """Test contextual message generation"""
        message = tracker._generate_contextual_message(
            GenerationPhase.REFINING_DETAILS, 60
        )
        assert message
        assert len(message) > 10


class TestSmartErrorRecovery:
    """Test smart error recovery system"""

    @pytest.fixture


    def recovery(self):
        return SmartErrorRecovery()

    @pytest.mark.asyncio


    async def test_memory_error_handling(self, recovery):
        """Test handling of out of memory errors"""
        error = Exception("CUDA out of memory")
        context = {"width": 1024, "height": 1024, "quality_mode": "high"}

        response = await recovery.handle_error(error, context)

        assert response["error_type"] == "memory"
        assert response["auto_fix_available"] is True
        assert response["auto_fix_params"]["width"] == 512
        assert response["auto_fix_params"]["height"] == 512
        assert response["auto_fix_params"]["quality_mode"] == "draft"
        assert len(response["suggestions"]) > 0

    @pytest.mark.asyncio


    async def test_model_error_handling(self, recovery):
        """Test handling of model not found errors"""
        error = Exception("Model not found: anime_v3")
        context = {"model": "anime_v3"}

        response = await recovery.handle_error(error, context)

        assert response["error_type"] == "model"
        assert response["auto_fix_available"] is True
        assert response["auto_fix_params"]["model"] == "default"
        assert "Use the default model" in response["suggestions"][0]

    @pytest.mark.asyncio


    async def test_timeout_error_handling(self, recovery):
        """Test handling of timeout errors"""
        error = Exception("Request timeout after 60 seconds")
        context = {"quality_mode": "high", "timeout": 60}

        response = await recovery.handle_error(error, context)

        assert response["error_type"] == "timeout"
        assert response["auto_fix_available"] is True
        assert response["auto_fix_params"]["quality_mode"] == "draft"
        assert response["auto_fix_params"]["timeout"] == 300

    @pytest.mark.asyncio


    async def test_auto_recovery_attempt(self, recovery):
        """Test automatic recovery with fixes"""
        error_response = {
            "auto_fix_available": True,
            "retry_with_fix": True,
            "auto_fix_params": {"width": 512, "height": 512}
        }

        original_request = {"width": 1024, "height": 1024, "prompt": "test"}

        # Mock retry function


        async def mock_retry(params):
            assert params["width"] == 512
            assert params["height"] == 512
            assert params["prompt"] == "test"
            return {"success": True}

        result = await recovery.attempt_auto_recovery(
            error_response, original_request, mock_retry
        )

        assert result["success"] is True

    @pytest.mark.asyncio


    async def test_no_auto_recovery_when_disabled(self, recovery):
        """Test that auto-recovery respects the flag"""
        error_response = {
            "auto_fix_available": False,
            "retry_with_fix": False
        }

        result = await recovery.attempt_auto_recovery(
            error_response, {}, AsyncMock()
        )

        assert result is None


class TestUXEnhancementManager:
    """Test the main UX enhancement manager"""

    @pytest.fixture


    def ux_manager(self):
        return UXEnhancementManager()

    @pytest.mark.asyncio


    async def test_track_generation(self, ux_manager):
        """Test generation tracking initialization"""
        mock_websocket = AsyncMock()

        await ux_manager.track_generation(
            job_id="test-job",
            websocket_send=mock_websocket,
            total_steps=25
        )

        assert "test-job" in ux_manager.progress_tracker.job_progress
        assert ux_manager.progress_tracker.job_progress["test-job"]["total_steps"] == 25
        assert "test-job" in ux_manager.websocket_connections

        # Should send initial update
        mock_websocket.assert_called_once()

    @pytest.mark.asyncio


    async def test_progress_updates_via_websocket(self, ux_manager):
        """Test that progress updates are sent via WebSocket"""
        mock_websocket = AsyncMock()

        await ux_manager.track_generation("job-123", mock_websocket)

        # Send progress update
        update = await ux_manager.update_progress(
            job_id="job-123",
            current_step=5,
            custom_message="Processing..."
        )

        assert update.current_step == 5
        assert update.message == "Processing..."

        # Should have sent 2 messages (initial + update)
        assert mock_websocket.call_count == 2

        # Verify WebSocket message format
        call_args = mock_websocket.call_args[0][0]
        message_data = json.loads(call_args)
        assert message_data["type"] == "progress"
        assert message_data["job_id"] == "job-123"

    @pytest.mark.asyncio


    async def test_error_handling_with_recovery(self, ux_manager):
        """Test error handling with auto-recovery"""
        mock_websocket = AsyncMock()
        ux_manager.websocket_connections["job-error"] = mock_websocket

        error = Exception("CUDA out of memory")
        context = {"width": 1024, "height": 1024}


        async def mock_retry(params):
            assert params["width"] == 512  # Auto-fixed
            return {"success": True, "result": "recovered"}

        result = await ux_manager.handle_generation_error(
            job_id="job-error",
            error=error,
            context=context,
            retry_function=mock_retry
        )

        # Should have sent error and recovery messages
        assert mock_websocket.call_count >= 2
        assert result["success"] is True


    def test_cleanup_job(self, ux_manager):
        """Test job cleanup"""
        ux_manager.websocket_connections["cleanup-job"] = Mock()
        ux_manager.progress_tracker.job_progress["cleanup-job"] = {}
        ux_manager.progress_tracker.start_times["cleanup-job"] = time.time()

        ux_manager.cleanup_job("cleanup-job")

        assert "cleanup-job" not in ux_manager.websocket_connections
        assert "cleanup-job" not in ux_manager.progress_tracker.job_progress
        assert "cleanup-job" not in ux_manager.progress_tracker.start_times


class TestIntegrationScenarios:
    """Test complete UX scenarios end-to-end"""

    @pytest.mark.asyncio


    async def test_successful_generation_flow(self):
        """Test a complete successful generation with progress updates"""
        manager = UXEnhancementManager()
        received_messages = []


        async def mock_websocket(message):
            received_messages.append(json.loads(message))

        # Start tracking
        await manager.track_generation("success-job", mock_websocket, total_steps=10)

        # Simulate generation progress
        for step in range(1, 11):
            await manager.update_progress(
                job_id="success-job",
                current_step=step
            )
            await asyncio.sleep(0.01)  # Simulate work

        # Verify we got all progress updates
        assert len(received_messages) == 11  # Initial + 10 updates

        # Check progression
        percentages = [msg["percentage"] for msg in received_messages if msg["type"] == "progress"]
        assert percentages[-1] == 100.0

        # Cleanup
        manager.cleanup_job("success-job")

    @pytest.mark.asyncio


    async def test_error_recovery_flow(self):
        """Test error occurrence and recovery flow"""
        manager = UXEnhancementManager()
        received_messages = []


        async def mock_websocket(message):
            received_messages.append(json.loads(message))

        manager.websocket_connections["error-job"] = mock_websocket

        # Simulate error and recovery
        error = Exception("CUDA out of memory. Tried to allocate 2GB")
        context = {"width": 2048, "height": 2048, "batch_size": 4}

        recovery_called = False


        async def mock_retry(params):
            nonlocal recovery_called
            recovery_called = True
            # Verify fixes were applied
            assert params["width"] == 512
            assert params["height"] == 512
            assert params["batch_size"] == 1
            return {"success": True}

        await manager.handle_generation_error(
            job_id="error-job",
            error=error,
            context=context,
            retry_function=mock_retry
        )

        # Verify error handling flow
        assert recovery_called
        error_messages = [m for m in received_messages if m["type"] == "error"]
        assert len(error_messages) == 1
        assert error_messages[0]["error_type"] == "memory"

        recovery_messages = [m for m in received_messages if m["type"] == "recovery_success"]
        assert len(recovery_messages) == 1

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
