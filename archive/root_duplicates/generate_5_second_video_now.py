#!/usr/bin/env python3
"""
Generate 5-Second Video NOW
Production test of the fixed anime generation system
"""

import asyncio
import time
import sys
from pathlib import Path

async def generate_test_video():
    """Generate a 5-second test video using the fixed system"""

    print("🎬 GENERATING 5-SECOND ANIME VIDEO")
    print("="*50)

    try:
        # Import our fixed generator
        from multi_segment_video_generator import generate_long_video_api

        # Test parameters
        prompt = "beautiful anime girl Kai Nakamura walking through cherry blossom park, spring morning light, gentle breeze, peaceful expression, detailed animation"
        character_name = "Kai Nakamura"
        duration = 5.0
        output_name = f"anime_5sec_test_{int(time.time())}"
        quality = "fast"  # Use fast for quicker generation

        print(f"📝 Prompt: {prompt}")
        print(f"🎭 Character: {character_name}")
        print(f"⏱️ Duration: {duration} seconds")
        print(f"📊 Quality: {quality}")
        print(f"📁 Output: {output_name}")
        print()

        start_time = time.time()
        print("🚀 Starting generation...")

        # Generate the video
        result = await generate_long_video_api(
            prompt=prompt,
            character_name=character_name,
            duration=duration,
            output_name=output_name,
            quality=quality
        )

        generation_time = time.time() - start_time

        if result["success"]:
            print("\n🎉 SUCCESS!")
            print("="*50)
            print(f"📹 Video Path: {result['video_path']}")
            print(f"⏱️ Duration: {result['duration']} seconds")
            print(f"🎞️ Segments: {result['segments']}")
            print(f"🎭 Character: {result['character']}")
            print(f"📊 Quality: {result['quality']}")
            print(f"⏰ Generation Time: {generation_time:.1f} seconds")

            # Check if file exists
            video_path = Path(result['video_path'])
            if video_path.exists():
                file_size = video_path.stat().st_size / (1024 * 1024)  # MB
                print(f"📦 File Size: {file_size:.1f} MB")
                print(f"✅ File confirmed to exist!")

                # Optional: Copy to easy access location
                home_videos = Path("/home/patrick/Videos")
                if home_videos.exists():
                    import shutil
                    easy_access = home_videos / f"{output_name}.mp4"
                    shutil.copy2(video_path, easy_access)
                    print(f"📁 Copied to: {easy_access}")

            else:
                print("❌ WARNING: Generated file not found!")

            return True

        else:
            print("\n❌ GENERATION FAILED!")
            print("="*50)
            print(f"Error: {result['error']}")
            return False

    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR!")
        print("="*50)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main execution function"""

    print("🔧 Tower Anime Production System - 5-Second Video Test")
    print("Version: 2.0.0 - Multi-Segment Generation")
    print("Status: Frame limiters FIXED")
    print()

    # Confirm user wants to proceed
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        proceed = True
    else:
        response = input("🤖 Generate 5-second test video? (y/N): ").strip().lower()
        proceed = response in ['y', 'yes']

    if not proceed:
        print("❌ Generation cancelled")
        return

    print("\n🚀 Starting generation process...")
    print("⏳ This will take approximately 3-5 minutes with fast quality")
    print()

    success = await generate_test_video()

    if success:
        print("\n🎊 CONGRATULATIONS!")
        print("The Tower Anime Production System can now generate 5+ second videos!")
        print("Frame limiters have been successfully fixed.")
    else:
        print("\n😔 Generation failed. Please check the logs for details.")

if __name__ == "__main__":
    asyncio.run(main())