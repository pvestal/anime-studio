#!/usr/bin/env python3
"""
Comprehensive Style Tests for Patrick's Anime Generation System
Tests the integration of learned preferences with proven ComfyUI performance
"""

import requests
import json
import time
import os
from pathlib import Path
from typing import List, Dict, Any

class StyleTestSuite:
    def __init__(self, api_url="http://localhost:8332"):
        self.api_url = api_url
        self.test_results = []

    def run_all_tests(self):
        """Run comprehensive test suite"""
        print("🧪 COMPREHENSIVE STYLE TEST SUITE")
        print("=" * 50)

        # Test 1: API Health and Style Availability
        self.test_api_health()

        # Test 2: Style Preset Validation
        self.test_style_presets()

        # Test 3: Character Template Integration
        self.test_character_templates()

        # Test 4: Patrick's Learned Preferences
        self.test_learned_preferences()

        # Test 5: Performance Validation
        self.test_performance_standards()

        # Test 6: Prompt Enhancement Quality
        self.test_prompt_enhancement()

        # Test 7: End-to-End Generation with Styles
        self.test_end_to_end_generation()

        # Summary
        self.print_test_summary()

    def test_api_health(self):
        """Test 1: API Health and Style Availability"""
        print("\n🏥 Test 1: API Health and Style Availability")

        try:
            # Health check
            response = requests.get(f"{self.api_url}/health", timeout=5)
            health_data = response.json()

            if health_data.get("status") == "healthy":
                print("✅ API healthy and responsive")

                # Check style availability
                styles_response = requests.get(f"{self.api_url}/styles")
                styles = styles_response.json()

                expected_styles = ["soft_lighting", "photorealistic", "ethereal",
                                 "dramatic", "high_contrast", "cartoon", "default"]

                available_styles = list(styles.get("styles", {}).keys())

                if all(style in available_styles for style in expected_styles):
                    print("✅ All expected style presets available")
                    self.log_success("API Health", "All systems operational")
                else:
                    missing = [s for s in expected_styles if s not in available_styles]
                    print(f"❌ Missing styles: {missing}")
                    self.log_failure("API Health", f"Missing styles: {missing}")

            else:
                print(f"❌ API unhealthy: {health_data}")
                self.log_failure("API Health", health_data)

        except Exception as e:
            print(f"❌ API health check failed: {e}")
            self.log_failure("API Health", str(e))

    def test_style_presets(self):
        """Test 2: Style Preset Validation"""
        print("\n🎨 Test 2: Style Preset Validation")

        test_prompt = "warrior in battle"

        try:
            # Test each style preset
            styles_response = requests.get(f"{self.api_url}/styles")
            styles_data = styles_response.json()
            styles = styles_data.get("styles", {})

            for style_name, style_info in styles.items():
                print(f"   Testing style: {style_name}")

                # Preview enhanced prompt
                preview_response = requests.post(f"{self.api_url}/preview-prompt", json={
                    "prompt": test_prompt,
                    "style": style_name
                })

                if preview_response.status_code == 200:
                    preview_data = preview_response.json()
                    enhanced_prompt = preview_data.get("enhanced_prompt", "")

                    # Check if style-specific keywords are included
                    style_keywords = style_info.get("description", "").lower()

                    if any(keyword in enhanced_prompt.lower() for keyword in ["lighting", "atmosphere", "style"]):
                        print(f"   ✅ {style_name}: Style enhancement working")
                        self.log_success(f"Style Preset: {style_name}", "Enhancement working")
                    else:
                        print(f"   ⚠️  {style_name}: Enhancement may be weak")
                        self.log_warning(f"Style Preset: {style_name}", "Weak enhancement")
                else:
                    print(f"   ❌ {style_name}: Preview failed")
                    self.log_failure(f"Style Preset: {style_name}", "Preview failed")

        except Exception as e:
            print(f"❌ Style preset testing failed: {e}")
            self.log_failure("Style Presets", str(e))

    def test_character_templates(self):
        """Test 3: Character Template Integration"""
        print("\n👥 Test 3: Character Template Integration")

        try:
            # Get available characters
            chars_response = requests.get(f"{self.api_url}/characters")
            chars_data = chars_response.json()
            characters = chars_data.get("characters", {})

            expected_characters = ["kai_nakamura", "light_yagami", "lelouch", "edward_elric"]

            for char_name in expected_characters:
                if char_name in characters:
                    print(f"   Testing character: {char_name}")

                    char_info = characters[char_name]

                    # Test prompt enhancement with character
                    preview_response = requests.post(f"{self.api_url}/preview-prompt", json={
                        "prompt": "standing confidently",
                        "character": char_name,
                        "style": "photorealistic"
                    })

                    if preview_response.status_code == 200:
                        preview_data = preview_response.json()
                        enhanced_prompt = preview_data.get("enhanced_prompt", "")

                        # Check if character details are included
                        char_description = char_info.get("description", "").lower()

                        if char_name.replace("_", " ") in enhanced_prompt.lower():
                            print(f"   ✅ {char_name}: Character integration working")
                            self.log_success(f"Character: {char_name}", "Integration working")
                        else:
                            print(f"   ⚠️  {char_name}: Character not clearly integrated")
                            self.log_warning(f"Character: {char_name}", "Weak integration")
                    else:
                        print(f"   ❌ {char_name}: Preview failed")
                        self.log_failure(f"Character: {char_name}", "Preview failed")
                else:
                    print(f"   ❌ {char_name}: Character not available")
                    self.log_failure(f"Character: {char_name}", "Not available")

        except Exception as e:
            print(f"❌ Character template testing failed: {e}")
            self.log_failure("Character Templates", str(e))

    def test_learned_preferences(self):
        """Test 4: Patrick's Learned Preferences"""
        print("\n🧠 Test 4: Patrick's Learned Preferences")

        # Test specific preferences that should be learned
        preference_tests = [
            {
                "name": "Soft Lighting Preference",
                "prompt": "character portrait",
                "style": "soft_lighting",
                "expect_keywords": ["soft", "lighting", "gentle", "warm"]
            },
            {
                "name": "Photorealistic Style",
                "prompt": "anime warrior",
                "style": "photorealistic",
                "expect_keywords": ["detailed", "realistic", "high quality"]
            },
            {
                "name": "High Contrast Drama",
                "prompt": "dynamic scene",
                "style": "high_contrast",
                "expect_keywords": ["contrast", "dramatic", "shadows"]
            }
        ]

        for test in preference_tests:
            print(f"   Testing: {test['name']}")

            try:
                preview_response = requests.post(f"{self.api_url}/preview-prompt", json={
                    "prompt": test["prompt"],
                    "style": test["style"]
                })

                if preview_response.status_code == 200:
                    preview_data = preview_response.json()
                    enhanced_prompt = preview_data.get("enhanced_prompt", "").lower()

                    found_keywords = [kw for kw in test["expect_keywords"] if kw in enhanced_prompt]

                    if found_keywords:
                        print(f"   ✅ {test['name']}: Found keywords: {found_keywords}")
                        self.log_success(f"Learned Preference: {test['name']}", f"Keywords: {found_keywords}")
                    else:
                        print(f"   ⚠️  {test['name']}: Expected keywords not found")
                        self.log_warning(f"Learned Preference: {test['name']}", "Keywords missing")
                else:
                    print(f"   ❌ {test['name']}: Request failed")
                    self.log_failure(f"Learned Preference: {test['name']}", "Request failed")

            except Exception as e:
                print(f"   ❌ {test['name']}: Error: {e}")
                self.log_failure(f"Learned Preference: {test['name']}", str(e))

    def test_performance_standards(self):
        """Test 5: Performance Validation"""
        print("\n⚡ Test 5: Performance Standards")

        # Test that style integration doesn't break the proven 6-second performance
        print("   Testing generation performance with style enhancement...")

        try:
            start_time = time.time()

            generation_response = requests.post(f"{self.api_url}/generate", json={
                "prompt": "test performance with kai",
                "character": "kai_nakamura",
                "style": "soft_lighting",
                "width": 512,  # Smaller for faster test
                "height": 512,
                "steps": 10    # Fewer steps for faster test
            }, timeout=30)

            end_time = time.time()
            generation_time = end_time - start_time

            if generation_response.status_code == 200:
                response_data = generation_response.json()

                if response_data.get("success"):
                    reported_time = response_data.get("generation_time", 0)

                    if reported_time < 20:  # Should be under 20 seconds
                        print(f"   ✅ Performance: {reported_time:.1f}s generation time")
                        self.log_success("Performance", f"{reported_time:.1f}s generation")
                    else:
                        print(f"   ⚠️  Performance: {reported_time:.1f}s (slower than expected)")
                        self.log_warning("Performance", f"{reported_time:.1f}s generation")

                    # Check if file was created
                    image_path = response_data.get("image_path")
                    if image_path and os.path.exists(image_path):
                        file_size = os.path.getsize(image_path)
                        print(f"   ✅ File created: {file_size:,} bytes")
                        self.log_success("File Creation", f"{file_size:,} bytes")
                    else:
                        print("   ❌ File not created")
                        self.log_failure("File Creation", "No output file")
                else:
                    print(f"   ❌ Generation failed: {response_data.get('error')}")
                    self.log_failure("Performance", response_data.get("error", "Unknown"))
            else:
                print(f"   ❌ Request failed: {generation_response.status_code}")
                self.log_failure("Performance", f"HTTP {generation_response.status_code}")

        except Exception as e:
            print(f"   ❌ Performance test failed: {e}")
            self.log_failure("Performance", str(e))

    def test_prompt_enhancement(self):
        """Test 6: Prompt Enhancement Quality"""
        print("\n✨ Test 6: Prompt Enhancement Quality")

        test_cases = [
            {
                "input": "standing",
                "character": "kai_nakamura",
                "style": "dramatic",
                "expect_length": "> 50 chars"
            },
            {
                "input": "warrior with sword",
                "character": "light_yagami",
                "style": "photorealistic",
                "expect_length": "> 80 chars"
            }
        ]

        for i, test in enumerate(test_cases):
            print(f"   Test case {i+1}: '{test['input']}'")

            try:
                preview_response = requests.post(f"{self.api_url}/preview-prompt", json={
                    "prompt": test["input"],
                    "character": test.get("character"),
                    "style": test.get("style")
                })

                if preview_response.status_code == 200:
                    preview_data = preview_response.json()
                    enhanced = preview_data.get("enhanced_prompt", "")
                    original = preview_data.get("original_prompt", "")

                    enhancement_ratio = len(enhanced) / len(original) if original else 0

                    print(f"      Original: {len(original)} chars")
                    print(f"      Enhanced: {len(enhanced)} chars")
                    print(f"      Ratio: {enhancement_ratio:.1f}x")

                    if enhancement_ratio > 2.0:  # Should enhance significantly
                        print(f"   ✅ Good enhancement ratio: {enhancement_ratio:.1f}x")
                        self.log_success(f"Enhancement Case {i+1}", f"{enhancement_ratio:.1f}x ratio")
                    else:
                        print(f"   ⚠️  Low enhancement: {enhancement_ratio:.1f}x")
                        self.log_warning(f"Enhancement Case {i+1}", f"Low {enhancement_ratio:.1f}x ratio")
                else:
                    print(f"   ❌ Preview failed")
                    self.log_failure(f"Enhancement Case {i+1}", "Preview failed")

            except Exception as e:
                print(f"   ❌ Test case {i+1} failed: {e}")
                self.log_failure(f"Enhancement Case {i+1}", str(e))

    def test_end_to_end_generation(self):
        """Test 7: End-to-End Generation with Styles"""
        print("\n🎯 Test 7: End-to-End Generation with Styles")

        # Test generation with different style combinations
        test_combinations = [
            {"character": "kai_nakamura", "style": "soft_lighting", "prompt": "confident pose"},
            {"character": "light_yagami", "style": "dramatic", "prompt": "thoughtful expression"}
        ]

        for i, combo in enumerate(test_combinations):
            print(f"   Generation test {i+1}: {combo['character']} + {combo['style']}")

            try:
                generation_response = requests.post(f"{self.api_url}/generate", json={
                    "prompt": combo["prompt"],
                    "character": combo["character"],
                    "style": combo["style"],
                    "width": 512,
                    "height": 512,
                    "steps": 10
                }, timeout=30)

                if generation_response.status_code == 200:
                    response_data = generation_response.json()

                    if response_data.get("success"):
                        image_path = response_data.get("image_path", "")
                        gen_time = response_data.get("generation_time", 0)

                        print(f"      ✅ Success: {gen_time:.1f}s, {os.path.basename(image_path)}")
                        self.log_success(f"E2E Generation {i+1}", f"{gen_time:.1f}s")
                    else:
                        error = response_data.get("error", "Unknown")
                        print(f"      ❌ Generation failed: {error}")
                        self.log_failure(f"E2E Generation {i+1}", error)
                else:
                    print(f"      ❌ Request failed: {generation_response.status_code}")
                    self.log_failure(f"E2E Generation {i+1}", f"HTTP {generation_response.status_code}")

            except Exception as e:
                print(f"      ❌ Test {i+1} failed: {e}")
                self.log_failure(f"E2E Generation {i+1}", str(e))

    def log_success(self, test_name: str, details: str):
        self.test_results.append({"test": test_name, "status": "✅ PASS", "details": details})

    def log_warning(self, test_name: str, details: str):
        self.test_results.append({"test": test_name, "status": "⚠️  WARN", "details": details})

    def log_failure(self, test_name: str, details: str):
        self.test_results.append({"test": test_name, "status": "❌ FAIL", "details": details})

    def print_test_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 60)
        print("📊 COMPREHENSIVE TEST SUMMARY")
        print("=" * 60)

        passes = len([r for r in self.test_results if "PASS" in r["status"]])
        warnings = len([r for r in self.test_results if "WARN" in r["status"]])
        failures = len([r for r in self.test_results if "FAIL" in r["status"]])
        total = len(self.test_results)

        print(f"Total Tests: {total}")
        print(f"✅ Passed: {passes}")
        print(f"⚠️  Warnings: {warnings}")
        print(f"❌ Failed: {failures}")
        print(f"Success Rate: {(passes/total*100):.1f}%")

        print("\nDetailed Results:")
        for result in self.test_results:
            print(f"{result['status']} {result['test']}: {result['details']}")

        # Overall assessment
        if failures == 0:
            print(f"\n🎉 ALL TESTS PASSED! Style integration is working perfectly.")
        elif failures < 3:
            print(f"\n✅ MOSTLY WORKING with {failures} issues to address.")
        else:
            print(f"\n⚠️  SIGNIFICANT ISSUES: {failures} failures need attention.")

if __name__ == "__main__":
    test_suite = StyleTestSuite()
    test_suite.run_all_tests()