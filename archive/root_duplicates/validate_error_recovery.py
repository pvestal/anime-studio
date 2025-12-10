#!/usr/bin/env python3
"""
Standalone validation script for Error Recovery System
Tests error recovery scenarios and validates 80% recovery rate
"""
import asyncio
import sys
import os
from unittest.mock import AsyncMock
from enum import Enum

# Add the modules directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'modules'))

try:
    from error_recovery_manager import ErrorRecoveryManager, ErrorType, RecoveryStrategy
    print("✅ Successfully imported error recovery modules")
except ImportError as e:
    print(f"❌ Failed to import modules: {e}")
    sys.exit(1)


async def run_validation_tests():
    """Run comprehensive validation tests to ensure 80% recovery rate target"""

    print("🧪 Running Error Recovery System Validation Tests...")
    print("=" * 60)

    # Test 1: Error classification accuracy
    print("\n1. Testing Error Classification System...")
    print("-" * 40)

    error_manager = ErrorRecoveryManager(AsyncMock())

    test_errors = [
        ("CUDA out of memory. Tried to allocate 2.00 GiB", ErrorType.CUDA_OOM),
        ("RuntimeError: CUDA out of memory", ErrorType.CUDA_OOM),
        ("Request timeout after 30 seconds", ErrorType.TIMEOUT),
        ("TimeoutError during generation", ErrorType.TIMEOUT),
        ("FileNotFoundError: Model not found at /models/test.safetensors", ErrorType.MODEL_MISSING),
        ("Missing model checkpoint", ErrorType.MODEL_MISSING),
        ("ConnectionError: Network unreachable", ErrorType.NETWORK_ERROR),
        ("HTTP 500 Internal Server Error", ErrorType.NETWORK_ERROR),
        ("No space left on device", ErrorType.DISK_FULL),
        ("OSError: [Errno 28] No space", ErrorType.DISK_FULL)
    ]

    correct_classifications = 0
    for i, (error_msg, expected_type) in enumerate(test_errors, 1):
        actual_type, pattern = error_manager.classify_error(error_msg)
        if actual_type == expected_type:
            correct_classifications += 1
            print(f"   {i:2d}. ✅ {expected_type.value} - '{error_msg[:50]}...'")
        else:
            print(f"   {i:2d}. ❌ Expected {expected_type.value}, got {actual_type.value}")
            print(f"        Error: '{error_msg[:50]}...'")

    classification_rate = (correct_classifications / len(test_errors)) * 100
    print(f"\n   📊 Error Classification Accuracy: {classification_rate:.1f}% ({correct_classifications}/{len(test_errors)})")

    # Test 2: Parameter adjustment effectiveness
    print("\n2. Testing Parameter Adjustment System...")
    print("-" * 40)

    # Test CUDA OOM parameter reduction
    print("   Testing CUDA OOM recovery:")
    oom_adjustments = {
        "batch_size": {"operation": "divide", "factor": 2, "min_value": 1},
        "width": {"operation": "reduce", "factor": 0.8, "min_value": 512},
        "height": {"operation": "reduce", "factor": 0.8, "min_value": 512}
    }

    test_params_scenarios = [
        {"batch_size": 8, "width": 1024, "height": 1024},
        {"batch_size": 4, "width": 512, "height": 512},  # Edge case
        {"batch_size": 16, "width": 2048, "height": 2048}  # High resource case
    ]

    adjustment_successes = 0
    total_adjustments = 0

    for i, test_params in enumerate(test_params_scenarios, 1):
        adjusted = error_manager.adjust_parameters(test_params, oom_adjustments)

        batch_reduced = adjusted["batch_size"] <= test_params["batch_size"]
        width_reduced = adjusted["width"] <= test_params["width"]
        height_reduced = adjusted["height"] <= test_params["height"]

        if batch_reduced and width_reduced and height_reduced:
            adjustment_successes += 1
            print(f"      Scenario {i}: ✅ {test_params} → {adjusted}")
        else:
            print(f"      Scenario {i}: ❌ Failed to reduce parameters properly")

        total_adjustments += 1

    adjustment_rate = (adjustment_successes / total_adjustments) * 100
    print(f"   📊 Parameter Adjustment Success Rate: {adjustment_rate:.1f}%")

    # Test 3: Recovery strategy assignment
    print("\n3. Testing Recovery Strategy Assignment...")
    print("-" * 40)

    expected_strategies = {
        ErrorType.CUDA_OOM: RecoveryStrategy.REDUCE_PARAMS,
        ErrorType.TIMEOUT: RecoveryStrategy.RESUME_CHECKPOINT,
        ErrorType.MODEL_MISSING: RecoveryStrategy.SWITCH_MODEL,
        ErrorType.NETWORK_ERROR: RecoveryStrategy.RETRY,
        ErrorType.DISK_FULL: RecoveryStrategy.ABORT
    }

    correct_strategies = 0
    total_strategies = 0

    for error_type, expected_strategy in expected_strategies.items():
        # Find pattern for this error type
        pattern_found = False
        for pattern in error_manager.error_patterns:
            if pattern.error_type == error_type:
                pattern_found = True
                if pattern.strategy == expected_strategy:
                    correct_strategies += 1
                    print(f"   ✅ {error_type.value} → {expected_strategy.value}")
                else:
                    print(f"   ❌ {error_type.value} → Expected {expected_strategy.value}, got {pattern.strategy.value}")
                break

        if not pattern_found:
            print(f"   ❌ {error_type.value} → No pattern found")

        total_strategies += 1

    strategy_rate = (correct_strategies / total_strategies) * 100
    print(f"   📊 Strategy Assignment Accuracy: {strategy_rate:.1f}%")

    # Test 4: Recovery attempt simulation
    print("\n4. Testing Recovery Attempt Logic...")
    print("-" * 40)

    recovery_scenarios = [
        ("CUDA out of memory", {"batch_size": 8}, True),  # Should succeed with reduction
        ("CUDA out of memory", {"batch_size": 1}, True),  # Minimal batch, still try
        ("Network error", {}, True),  # Should retry
        ("No space left", {}, False),  # Should abort
    ]

    successful_recovery_attempts = 0
    total_recovery_attempts = len(recovery_scenarios)

    for i, (error_msg, params, should_succeed) in enumerate(recovery_scenarios, 1):
        try:
            success, new_params, message = await error_manager.attempt_recovery(
                job_id=1000 + i,
                error_message=error_msg,
                original_params=params,
                workflow_data={}
            )

            if success == should_succeed:
                successful_recovery_attempts += 1
                status = "✅" if success else "✅ (Expected failure)"
                print(f"   {i}. {status} {error_msg[:30]}... → {message[:50]}...")
            else:
                print(f"   {i}. ❌ Expected {'success' if should_succeed else 'failure'}, got {'success' if success else 'failure'}")

        except Exception as e:
            print(f"   {i}. ❌ Recovery attempt failed with exception: {e}")

    recovery_logic_rate = (successful_recovery_attempts / total_recovery_attempts) * 100
    print(f"   📊 Recovery Logic Accuracy: {recovery_logic_rate:.1f}%")

    # Test 5: Checkpoint system
    print("\n5. Testing Checkpoint System...")
    print("-" * 40)

    checkpoint_tests = [
        (101, {"node1": "completed"}, 25.0),
        (102, {"node1": "completed", "node2": "processing"}, 50.0),
        (103, {"node1": "completed", "node2": "completed"}, 75.0),
    ]

    checkpoint_successes = 0
    for job_id, workflow_state, progress in checkpoint_tests:
        try:
            checkpoint = error_manager.create_checkpoint(job_id, workflow_state, progress)
            retrieved = error_manager.get_latest_checkpoint(job_id)

            if retrieved and retrieved.checkpoint_id == checkpoint.checkpoint_id:
                checkpoint_successes += 1
                print(f"   ✅ Job {job_id} checkpoint at {progress}% created and retrieved")
            else:
                print(f"   ❌ Job {job_id} checkpoint creation/retrieval failed")

        except Exception as e:
            print(f"   ❌ Job {job_id} checkpoint failed: {e}")

    checkpoint_rate = (checkpoint_successes / len(checkpoint_tests)) * 100
    print(f"   📊 Checkpoint System Success Rate: {checkpoint_rate:.1f}%")

    # Final Assessment
    print("\n" + "=" * 60)
    print("📊 COMPREHENSIVE VALIDATION SUMMARY")
    print("=" * 60)

    test_scores = [
        ("Error Classification", classification_rate),
        ("Parameter Adjustment", adjustment_rate),
        ("Strategy Assignment", strategy_rate),
        ("Recovery Logic", recovery_logic_rate),
        ("Checkpoint System", checkpoint_rate)
    ]

    total_score = sum(score for _, score in test_scores) / len(test_scores)

    print(f"\nIndividual Test Scores:")
    for test_name, score in test_scores:
        status = "✅" if score >= 80 else "⚠️" if score >= 60 else "❌"
        print(f"   {status} {test_name:<20}: {score:6.1f}%")

    print(f"\n🎯 Overall System Score: {total_score:.1f}%")

    if total_score >= 80.0:
        print("   ✅ SUCCESS: System meets the 80% recovery target!")
        print("   🚀 Ready for production deployment")
    elif total_score >= 70.0:
        print("   ⚠️  WARNING: System close to target but needs improvement")
        print("   🔧 Consider additional testing and optimization")
    else:
        print("   ❌ FAILURE: System below acceptable threshold")
        print("   🛠️  Requires significant improvements before deployment")

    # Recovery rate projection
    print(f"\n📈 Recovery Rate Projection:")
    print(f"   Based on current test performance:")
    print(f"   • Expected error detection rate: {classification_rate:.1f}%")
    print(f"   • Expected recovery success rate: {recovery_logic_rate:.1f}%")

    projected_recovery_rate = (classification_rate * recovery_logic_rate) / 100
    print(f"   • Projected overall recovery rate: {projected_recovery_rate:.1f}%")

    if projected_recovery_rate >= 80.0:
        print("   ✅ Projected recovery rate meets acceptance criteria!")
    else:
        print(f"   ⚠️  Projected rate below target. Need {80.0 - projected_recovery_rate:.1f}% improvement")

    print("\n" + "=" * 60)
    print("🎯 VALIDATION COMPLETE")
    print("=" * 60)

    return total_score >= 80.0


if __name__ == "__main__":
    try:
        success = asyncio.run(run_validation_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n🛑 Validation interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Validation failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)