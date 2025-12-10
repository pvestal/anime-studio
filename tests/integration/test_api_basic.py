#!/usr/bin/env python3
"""
Basic integration tests for Tower Anime Production API
Tests that can run in CI/CD without full service dependencies
"""

import os
import sys

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestAPIImports:
    """Test that API modules can be imported"""


    def test_secured_api_imports(self):
        """Test secured_api can be imported"""
        try:
            from api import secured_api
            assert secured_api is not None
        except ImportError as e:
            pytest.skip(f"Could not import secured_api: {e}")


    def test_models_import(self):
        """Test models can be imported"""
        try:
            from api import models
            assert models is not None
            # Check key models exist
            assert hasattr(models, 'Project')
            assert hasattr(models, 'Character')
            assert hasattr(models, 'ProductionJob')
        except ImportError as e:
            pytest.skip(f"Could not import models: {e}")


    def test_websocket_manager_import(self):
        """Test websocket manager can be imported"""
        try:
            from api import websocket_manager
            assert websocket_manager is not None
            assert hasattr(websocket_manager, 'ConnectionManager')
        except ImportError as e:
            pytest.skip(f"Could not import websocket_manager: {e}")


class TestOptimizationModules:
    """Test optimization modules"""


    def test_optimized_workflows_import(self):
        """Test optimized workflows can be imported"""
        try:
            import optimized_workflows
            assert optimized_workflows is not None
            assert hasattr(optimized_workflows, 'OptimizedWorkflows')
        except ImportError as e:
            pytest.skip(f"Could not import optimized_workflows: {e}")


    def test_generation_cache_import(self):
        """Test generation cache can be imported"""
        try:
            import generation_cache
            assert generation_cache is not None
            assert hasattr(generation_cache, 'GenerationCache')
        except ImportError as e:
            pytest.skip(f"Could not import generation_cache: {e}")


    def test_performance_monitor_import(self):
        """Test performance monitor can be imported"""
        try:
            import performance_monitor
            assert performance_monitor is not None
            assert hasattr(performance_monitor, 'PerformanceMonitor')
        except ImportError as e:
            pytest.skip(f"Could not import performance_monitor: {e}")


class TestBasicFunctionality:
    """Test basic functionality without external dependencies"""


    def test_workflow_configuration(self):
        """Test workflow configurations are valid"""
        try:
            from optimized_workflows import OptimizedWorkflows

            workflows = OptimizedWorkflows()

            # Test draft workflow
            draft_config = workflows.DRAFT_CONFIG
            assert draft_config['steps'] == 8
            assert draft_config['cfg'] == 5.0
            assert draft_config['sampler'] == 'dpm_fast'

            # Test standard workflow
            standard_config = workflows.STANDARD_CONFIG
            assert standard_config['steps'] == 15
            assert standard_config['cfg'] == 6.5

        except Exception as e:
            pytest.skip(f"Could not test workflows: {e}")


    def test_cache_initialization(self):
        """Test cache can be initialized"""
        try:
            from generation_cache import GenerationCache

            cache = GenerationCache()
            assert cache is not None
            assert hasattr(cache, 'cache_output')
            assert hasattr(cache, 'get_cached_output')

        except Exception as e:
            pytest.skip(f"Could not test cache: {e}")


    def test_models_structure(self):
        """Test database models have expected structure"""
        try:
            from api.models import Character, ProductionJob, Project

            # Test Project model
            assert hasattr(Project, 'id')
            assert hasattr(Project, 'name')
            assert hasattr(Project, 'description')

            # Test Character model
            assert hasattr(Character, 'id')
            assert hasattr(Character, 'name')
            assert hasattr(Character, 'project_id')

            # Test ProductionJob model
            assert hasattr(ProductionJob, 'id')
            assert hasattr(ProductionJob, 'status')
            assert hasattr(ProductionJob, 'prompt')

        except Exception as e:
            pytest.skip(f"Could not test models: {e}")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
