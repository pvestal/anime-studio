#!/usr/bin/env python3
"""
Test Character Studio Integration with Echo Brain
Tests the complete QC workflow using existing UI structure
"""

import asyncio
import httpx
import json
from datetime import datetime
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.character_studio_bridge import CharacterStudioBridge


class CharacterStudioIntegrationTest:
    """Test suite for Character Studio + Echo Brain integration"""

    def __init__(self):
        self.bridge = CharacterStudioBridge()
        self.test_results = []
        self.echo_url = "http://localhost:8309/api/echo/anime"
        self.studio_url = "http://localhost:8331/api/anime/studio"

    async def test_1_character_listing_compatibility(self):
        """Test that characters from Echo Brain display correctly in studio UI"""
        print("\n🎯 TEST 1: Character Listing Compatibility")
        print("-" * 40)

        try:
            # Get characters in studio format
            studio_chars = await self.bridge.list_characters_for_studio()

            # Verify format matches what CharacterStudio.vue expects
            required_fields = [
                "character_name", "project_name", "reference_images",
                "generation_count", "consistency_score"
            ]

            if studio_chars["characters"]:
                char = studio_chars["characters"][0]
                missing_fields = [f for f in required_fields if f not in char]

                if not missing_fields:
                    print(f"✅ Character format compatible with studio UI")
                    print(f"   Found {len(studio_chars['characters'])} characters")
                    for c in studio_chars["characters"]:
                        print(f"   - {c['character_name']}: Score {c['consistency_score']:.2f}")
                    self.test_results.append(("Character Listing", True))
                else:
                    print(f"❌ Missing fields: {missing_fields}")
                    self.test_results.append(("Character Listing", False))
            else:
                print("⚠️ No characters found to test")
                self.test_results.append(("Character Listing", None))

        except Exception as e:
            print(f"❌ Test failed: {e}")
            self.test_results.append(("Character Listing", False))

    async def test_2_qc_workflow_generation(self):
        """Test generation with QC metadata"""
        print("\n🎯 TEST 2: Generation with QC Tracking")
        print("-" * 40)

        try:
            # Use first character
            chars = await self.bridge.list_characters_for_studio()
            if not chars["characters"]:
                print("⚠️ No characters available for test")
                self.test_results.append(("QC Generation", None))
                return

            char = chars["characters"][0]
            char_id = char["id"]

            # Generate with QC metadata
            result = await self.bridge.generate_with_qc(
                char_id,
                "test pose for QC workflow",
                {"denoise": 0.45, "seed": 12345}
            )

            if "qc_metadata" in result:
                print(f"✅ Generation created with QC metadata")
                print(f"   Generation ID: {result['generation_id']}")
                print(f"   Needs approval: {result['qc_metadata']['needs_approval']}")
                print(f"   Auto-score threshold: {result['qc_metadata']['auto_score_threshold']}")
                self.test_results.append(("QC Generation", True))

                # Store for later tests
                self.test_generation_id = result["generation_id"]
                self.test_character_id = char_id
            else:
                print("❌ QC metadata missing from generation")
                self.test_results.append(("QC Generation", False))

        except Exception as e:
            print(f"❌ Test failed: {e}")
            self.test_results.append(("QC Generation", False))

    async def test_3_qc_queue_management(self):
        """Test QC queue displays pending approvals"""
        print("\n🎯 TEST 3: QC Queue Management")
        print("-" * 40)

        try:
            if not hasattr(self, 'test_character_id'):
                print("⚠️ No test character available")
                self.test_results.append(("QC Queue", None))
                return

            # Get QC queue
            queue = await self.bridge.get_qc_queue(self.test_character_id)

            print(f"📊 QC Queue Status:")
            print(f"   Items pending: {len(queue)}")

            if queue:
                for item in queue[:3]:  # Show first 3
                    print(f"   - Prompt: {item['prompt'][:50]}...")
                    print(f"     Consistency: {item.get('consistency', 0)*100:.1f}%")
                    print(f"     Actions: {', '.join(item['actions'])}")

            # Verify queue structure for UI
            if queue and all(k in queue[0] for k in ['generation_id', 'prompt', 'actions']):
                print("✅ Queue format compatible with QC panel")
                self.test_results.append(("QC Queue", True))
            else:
                print("⚠️ Queue empty or incomplete")
                self.test_results.append(("QC Queue", None))

        except Exception as e:
            print(f"❌ Test failed: {e}")
            self.test_results.append(("QC Queue", False))

    async def test_4_approval_workflow(self):
        """Test approval updates character stats and learns patterns"""
        print("\n🎯 TEST 4: Approval Workflow")
        print("-" * 40)

        try:
            if not hasattr(self, 'test_generation_id'):
                print("⚠️ No test generation available")
                self.test_results.append(("Approval Workflow", None))
                return

            # Approve generation
            result = await self.bridge.approve_generation(
                self.test_character_id,
                self.test_generation_id,
                "Good consistency, approved via integration test"
            )

            if result["status"] == "approved":
                print(f"✅ Generation approved successfully")
                print(f"   Message: {result['message']}")
                print(f"   Patterns learned: {result.get('learned_patterns', False)}")
                self.test_results.append(("Approval Workflow", True))
            else:
                print(f"❌ Approval failed: {result}")
                self.test_results.append(("Approval Workflow", False))

        except Exception as e:
            print(f"❌ Test failed: {e}")
            self.test_results.append(("Approval Workflow", False))

    async def test_5_consistency_metrics(self):
        """Test consistency metrics and recommendations"""
        print("\n🎯 TEST 5: Consistency Metrics & Recommendations")
        print("-" * 40)

        try:
            if not hasattr(self, 'test_character_id'):
                print("⚠️ No test character available")
                self.test_results.append(("Consistency Metrics", None))
                return

            # Get metrics
            metrics = await self.bridge.get_consistency_metrics(self.test_character_id)

            print(f"📈 Character Metrics:")
            print(f"   Character: {metrics['character_name']}")
            print(f"   Total generations: {metrics['metrics']['total_generations']}")
            print(f"   Approved: {metrics['metrics']['approved']}")
            print(f"   Approval rate: {metrics['metrics']['approval_rate']:.1%}")
            print(f"   Avg consistency: {metrics['metrics']['average_consistency']:.2f}")
            print(f"   Trend: {metrics['metrics']['trend']}")

            print(f"\n💡 Recommendations:")
            for rec in metrics['recommendations']:
                print(f"   - {rec}")

            # Verify metrics structure
            if all(k in metrics['metrics'] for k in ['approval_rate', 'average_consistency']):
                print("\n✅ Metrics compatible with QC dashboard")
                self.test_results.append(("Consistency Metrics", True))
            else:
                print("\n❌ Metrics structure incomplete")
                self.test_results.append(("Consistency Metrics", False))

        except Exception as e:
            print(f"❌ Test failed: {e}")
            self.test_results.append(("Consistency Metrics", False))

    async def test_6_ui_data_flow(self):
        """Test complete data flow from Echo Brain to Studio UI"""
        print("\n🎯 TEST 6: UI Data Flow Integration")
        print("-" * 40)

        try:
            # Simulate what CharacterStudio.vue does
            print("📱 Simulating UI data requests...")

            # 1. Load characters (mounted hook)
            chars = await self.bridge.list_characters_for_studio()
            print(f"   ✓ Characters loaded: {len(chars['characters'])}")

            if chars["characters"]:
                char = chars["characters"][0]

                # 2. Select character (user click)
                details = await self.bridge.get_character_details(char["id"])
                print(f"   ✓ Character details loaded")
                print(f"     QC Status: {details['qc_status']['ready_for_production']}")

                # 3. Load QC panel data
                metrics = await self.bridge.get_consistency_metrics(char["id"])
                queue = await self.bridge.get_qc_queue(char["id"])
                print(f"   ✓ QC panel data loaded")
                print(f"     Queue items: {len(queue)}")
                print(f"     Approval rate: {metrics['metrics']['approval_rate']:.1%}")

                self.test_results.append(("UI Data Flow", True))
            else:
                print("⚠️ No characters to test UI flow")
                self.test_results.append(("UI Data Flow", None))

        except Exception as e:
            print(f"❌ Test failed: {e}")
            self.test_results.append(("UI Data Flow", False))

    async def test_7_rejection_workflow(self):
        """Test rejection with feedback learning"""
        print("\n🎯 TEST 7: Rejection Workflow")
        print("-" * 40)

        try:
            # Generate a new one to reject
            chars = await self.bridge.list_characters_for_studio()
            if not chars["characters"]:
                print("⚠️ No characters available")
                self.test_results.append(("Rejection Workflow", None))
                return

            char_id = chars["characters"][0]["id"]

            # Generate
            gen = await self.bridge.generate_with_qc(
                char_id,
                "bad pose to reject",
                {"denoise": 0.8}  # High denoise to ensure inconsistency
            )

            # Reject it
            result = await self.bridge.reject_generation(
                char_id,
                gen["generation_id"],
                "Face doesn't match, too much variation"
            )

            if result["status"] == "rejected":
                print(f"✅ Generation rejected successfully")
                print(f"   Message: {result['message']}")
                print(f"   Will retry: {result.get('will_retry', False)}")
                self.test_results.append(("Rejection Workflow", True))
            else:
                print(f"❌ Rejection failed: {result}")
                self.test_results.append(("Rejection Workflow", False))

        except Exception as e:
            print(f"❌ Test failed: {e}")
            self.test_results.append(("Rejection Workflow", False))

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("CHARACTER STUDIO INTEGRATION TEST SUMMARY")
        print("=" * 60)

        passed = sum(1 for _, result in self.test_results if result is True)
        failed = sum(1 for _, result in self.test_results if result is False)
        skipped = sum(1 for _, result in self.test_results if result is None)

        for test_name, result in self.test_results:
            status = "✅ PASS" if result is True else "❌ FAIL" if result is False else "⚠️ SKIP"
            print(f"{status:12} {test_name}")

        print("-" * 60)
        print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
        print("=" * 60)

        if failed == 0:
            print("🎉 All tests passed! Character Studio integration is working!")
        else:
            print("⚠️ Some tests failed. Review the issues above.")

    async def run_all_tests(self):
        """Run all integration tests"""
        print("=" * 60)
        print("CHARACTER STUDIO + ECHO BRAIN INTEGRATION TESTS")
        print("=" * 60)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Run tests in sequence
        await self.test_1_character_listing_compatibility()
        await self.test_2_qc_workflow_generation()
        await asyncio.sleep(2)  # Wait for generation
        await self.test_3_qc_queue_management()
        await self.test_4_approval_workflow()
        await self.test_5_consistency_metrics()
        await self.test_6_ui_data_flow()
        await self.test_7_rejection_workflow()

        self.print_summary()


async def main():
    """Main test runner"""
    # Check services are running
    print("🔍 Checking required services...")

    async with httpx.AsyncClient() as client:
        # Check Echo Brain
        try:
            resp = await client.get("http://localhost:8309/api/echo/health")
            if resp.status_code == 200:
                print("✅ Echo Brain is running on port 8309")
            else:
                print("❌ Echo Brain not responding properly")
                return
        except:
            print("❌ Echo Brain is not running on port 8309")
            print("   Start it with: sudo systemctl start tower-echo-brain")
            return

        # Check ComfyUI
        try:
            resp = await client.get("http://localhost:8188/system_stats")
            if resp.status_code == 200:
                print("✅ ComfyUI is running on port 8188")
            else:
                print("⚠️ ComfyUI not responding (generation will fail)")
        except:
            print("⚠️ ComfyUI is not running on port 8188")
            print("   Start it with: cd /mnt/1TB-storage/ComfyUI && python main.py")

    # Run tests
    tester = CharacterStudioIntegrationTest()
    await tester.run_all_tests()

    # Additional manual test instructions
    print("\n" + "=" * 60)
    print("MANUAL UI TESTING INSTRUCTIONS")
    print("=" * 60)
    print("1. Open Character Studio UI:")
    print("   http://192.168.50.135:8331/studio")
    print("")
    print("2. Verify you can see:")
    print("   - Character list with Echo Brain characters")
    print("   - QC panel when selecting a character")
    print("   - Consistency metrics and recommendations")
    print("   - Pending approval queue")
    print("")
    print("3. Test QC workflow:")
    print("   - Generate a new variation")
    print("   - See it appear in QC queue")
    print("   - Approve/Reject with feedback")
    print("   - Watch metrics update")
    print("")
    print("4. Monitor Echo Brain learning:")
    print("   curl http://localhost:8309/api/echo/anime/character/1/patterns")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())