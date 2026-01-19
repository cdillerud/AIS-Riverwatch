#!/usr/bin/env python3
"""
AIS Vessel Tracker Backend API Testing
Tests all backend endpoints for the River Watch application
"""

import requests
import sys
import json
from datetime import datetime
from typing import Dict, Any, Optional

# Use the public endpoint from frontend .env
BACKEND_URL = "https://vessel-tracker-21.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"

class AISBackendTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
    def log_test(self, name: str, success: bool, details: str = "", response_data: Any = None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            
        result = {
            "test": name,
            "success": success,
            "details": details,
            "response_data": response_data,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
        if details:
            print(f"    {details}")
        if not success and response_data:
            print(f"    Response: {response_data}")
        print()

    def test_api_status(self) -> bool:
        """Test basic API status endpoint"""
        try:
            response = requests.get(f"{API_BASE}/", timeout=10)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                expected_keys = ["message", "status"]
                has_keys = all(key in data for key in expected_keys)
                success = has_keys and data.get("status") == "online"
                
                self.log_test(
                    "API Status Check", 
                    success,
                    f"Status: {response.status_code}, Data: {data}" if success else "Missing required keys or wrong status",
                    data
                )
            else:
                self.log_test(
                    "API Status Check", 
                    False,
                    f"HTTP {response.status_code}: {response.text}",
                    response.text
                )
                
            return success
            
        except Exception as e:
            self.log_test("API Status Check", False, f"Connection error: {str(e)}")
            return False

    def test_locks_endpoint(self) -> bool:
        """Test locks endpoint returns lock positions"""
        try:
            response = requests.get(f"{API_BASE}/locks", timeout=10)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                success = isinstance(data, list) and len(data) >= 2
                
                if success:
                    # Check lock structure
                    required_fields = ["id", "name", "river_mile", "lat", "lon"]
                    for lock in data:
                        if not all(field in lock for field in required_fields):
                            success = False
                            break
                    
                    # Check specific locks exist
                    lock_ids = [lock["id"] for lock in data]
                    expected_locks = ["lock_2", "lock_3"]
                    has_expected = all(lock_id in lock_ids for lock_id in expected_locks)
                    success = success and has_expected
                
                self.log_test(
                    "Locks Endpoint", 
                    success,
                    f"Found {len(data)} locks: {[l.get('name', l.get('id')) for l in data]}" if success else "Invalid lock data structure",
                    data
                )
            else:
                self.log_test(
                    "Locks Endpoint", 
                    False,
                    f"HTTP {response.status_code}: {response.text}",
                    response.text
                )
                
            return success
            
        except Exception as e:
            self.log_test("Locks Endpoint", False, f"Error: {str(e)}")
            return False

    def test_connection_test_endpoint(self) -> bool:
        """Test connection test endpoint"""
        try:
            test_data = {
                "ip_address": "192.168.1.100",
                "port": 5353,
                "user_mmsi": "123456789"
            }
            
            response = requests.post(
                f"{API_BASE}/connection/test", 
                json=test_data,
                timeout=10
            )
            
            success = response.status_code == 200
            
            if success:
                data = response.json()
                success = "success" in data and "message" in data
                
                self.log_test(
                    "Connection Test Endpoint", 
                    success,
                    f"Response: {data}" if success else "Missing required response fields",
                    data
                )
            else:
                self.log_test(
                    "Connection Test Endpoint", 
                    False,
                    f"HTTP {response.status_code}: {response.text}",
                    response.text
                )
                
            return success
            
        except Exception as e:
            self.log_test("Connection Test Endpoint", False, f"Error: {str(e)}")
            return False

    def test_set_user_mmsi(self) -> bool:
        """Test setting user MMSI"""
        try:
            test_data = {"mmsi": "123456789"}
            
            response = requests.post(
                f"{API_BASE}/set-user-mmsi", 
                json=test_data,
                timeout=10
            )
            
            success = response.status_code == 200
            
            if success:
                data = response.json()
                success = data.get("success") is True and data.get("mmsi") == "123456789"
                
                self.log_test(
                    "Set User MMSI", 
                    success,
                    f"MMSI set to: {data.get('mmsi')}" if success else "Invalid response format",
                    data
                )
            else:
                self.log_test(
                    "Set User MMSI", 
                    False,
                    f"HTTP {response.status_code}: {response.text}",
                    response.text
                )
                
            return success
            
        except Exception as e:
            self.log_test("Set User MMSI", False, f"Error: {str(e)}")
            return False

    def test_add_demo_vessel(self) -> bool:
        """Test adding demo vessels"""
        try:
            demo_vessel = {
                "mmsi": "123456789",
                "name": "TEST VESSEL",
                "lat": 44.82,
                "lon": -92.90,
                "speed": 8,
                "course": 180,
                "is_user_vessel": True,
                "vessel_type": "recreational"
            }
            
            response = requests.post(
                f"{API_BASE}/demo/add-vessel", 
                json=demo_vessel,
                timeout=10
            )
            
            success = response.status_code == 200
            
            if success:
                data = response.json()
                success = data.get("success") is True and "vessel" in data
                
                if success:
                    vessel = data["vessel"]
                    # Check that river_mile and heading were calculated
                    success = "river_mile" in vessel and "heading" in vessel
                
                self.log_test(
                    "Add Demo Vessel", 
                    success,
                    f"Added vessel: {vessel.get('name', vessel.get('mmsi'))} at RM {vessel.get('river_mile')}" if success else "Invalid vessel data",
                    data
                )
            else:
                self.log_test(
                    "Add Demo Vessel", 
                    False,
                    f"HTTP {response.status_code}: {response.text}",
                    response.text
                )
                
            return success
            
        except Exception as e:
            self.log_test("Add Demo Vessel", False, f"Error: {str(e)}")
            return False

    def test_get_vessels(self) -> bool:
        """Test getting tracked vessels"""
        try:
            response = requests.get(f"{API_BASE}/vessels", timeout=10)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                success = isinstance(data, list)
                
                if success and len(data) > 0:
                    # Check vessel structure
                    vessel = data[0]
                    required_fields = ["mmsi", "lat", "lon", "speed", "course", "river_mile", "heading"]
                    success = all(field in vessel for field in required_fields)
                
                self.log_test(
                    "Get Vessels", 
                    success,
                    f"Found {len(data)} vessels" if success else "Invalid vessel data structure",
                    {"vessel_count": len(data), "sample_vessel": data[0] if data else None}
                )
            else:
                self.log_test(
                    "Get Vessels", 
                    False,
                    f"HTTP {response.status_code}: {response.text}",
                    response.text
                )
                
            return success
            
        except Exception as e:
            self.log_test("Get Vessels", False, f"Error: {str(e)}")
            return False

    def test_race_analysis(self, lock_id: str = "lock_2") -> bool:
        """Test race analysis endpoint"""
        try:
            response = requests.get(f"{API_BASE}/race-analysis/{lock_id}", timeout=10)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                required_fields = ["target_lock", "target_lock_name", "target_lock_rm", "competitors"]
                success = all(field in data for field in required_fields)
                
                if success:
                    # Check if analysis is present when user vessel exists
                    has_analysis = "analysis" in data and data["analysis"] is not None
                    
                self.log_test(
                    f"Race Analysis ({lock_id})", 
                    success,
                    f"Target: {data.get('target_lock_name')}, Competitors: {len(data.get('competitors', []))}, Has Analysis: {has_analysis}" if success else "Invalid analysis structure",
                    {
                        "target_lock": data.get("target_lock"),
                        "competitors_count": len(data.get("competitors", [])),
                        "has_analysis": "analysis" in data
                    }
                )
            else:
                self.log_test(
                    f"Race Analysis ({lock_id})", 
                    False,
                    f"HTTP {response.status_code}: {response.text}",
                    response.text
                )
                
            return success
            
        except Exception as e:
            self.log_test(f"Race Analysis ({lock_id})", False, f"Error: {str(e)}")
            return False

    def test_settings_endpoints(self) -> bool:
        """Test settings save and retrieve"""
        try:
            # Test saving settings
            test_settings = {
                "user_mmsi": "123456789",
                "connection_config": json.dumps({
                    "ip_address": "192.168.1.100",
                    "port": 5353,
                    "user_mmsi": "123456789"
                })
            }
            
            save_response = requests.post(
                f"{API_BASE}/settings", 
                json=test_settings,
                timeout=10
            )
            
            save_success = save_response.status_code == 200
            
            if save_success:
                save_data = save_response.json()
                save_success = save_data.get("success") is True
            
            # Test retrieving settings
            get_response = requests.get(f"{API_BASE}/settings", timeout=10)
            get_success = get_response.status_code == 200
            
            if get_success:
                get_data = get_response.json()
                get_success = isinstance(get_data, dict)
                
                if get_success:
                    # Check if saved settings are retrieved
                    has_mmsi = get_data.get("user_mmsi") == "123456789"
                    get_success = has_mmsi
            
            overall_success = save_success and get_success
            
            self.log_test(
                "Settings Endpoints", 
                overall_success,
                f"Save: {save_success}, Get: {get_success}, Retrieved MMSI: {get_data.get('user_mmsi') if get_success else 'N/A'}" if overall_success else "Settings save/retrieve failed",
                {
                    "save_success": save_success,
                    "get_success": get_success,
                    "retrieved_settings": get_data if get_success else None
                }
            )
            
            return overall_success
            
        except Exception as e:
            self.log_test("Settings Endpoints", False, f"Error: {str(e)}")
            return False

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all backend tests"""
        print("🚀 Starting AIS Vessel Tracker Backend Tests")
        print(f"Testing against: {BACKEND_URL}")
        print("=" * 60)
        
        # Test basic connectivity first
        if not self.test_api_status():
            print("❌ API is not accessible. Stopping tests.")
            return self.get_summary()
        
        # Core API tests
        self.test_locks_endpoint()
        self.test_connection_test_endpoint()
        self.test_set_user_mmsi()
        self.test_settings_endpoints()
        
        # Vessel management tests
        self.test_add_demo_vessel()
        self.test_get_vessels()
        
        # Race analysis tests
        self.test_race_analysis("lock_2")
        self.test_race_analysis("lock_3")
        
        return self.get_summary()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get test summary"""
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        print("=" * 60)
        print(f"📊 Test Summary: {self.tests_passed}/{self.tests_run} passed ({success_rate:.1f}%)")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
        else:
            print("⚠️  Some tests failed. Check details above.")
        
        return {
            "total_tests": self.tests_run,
            "passed_tests": self.tests_passed,
            "success_rate": success_rate,
            "test_results": self.test_results
        }

def main():
    """Main test runner"""
    tester = AISBackendTester()
    summary = tester.run_all_tests()
    
    # Return appropriate exit code
    return 0 if summary["passed_tests"] == summary["total_tests"] else 1

if __name__ == "__main__":
    sys.exit(main())