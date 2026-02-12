"""
Test User Vessel Simulation API endpoints
Tests for GET/POST /api/user-vessel/simulation/{mmsi}
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://lock-timing-demo.preview.emergentagent.com').rstrip('/')
TEST_MMSI = "123456789"

class TestUserVesselSimulation:
    """Test user vessel simulation endpoints"""
    
    def test_get_simulation_status(self):
        """GET /api/user-vessel/simulation/{mmsi} - should return simulation status"""
        response = requests.get(f"{BASE_URL}/api/user-vessel/simulation/{TEST_MMSI}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "mmsi" in data, "Response should contain mmsi"
        assert data["mmsi"] == TEST_MMSI, f"MMSI should be {TEST_MMSI}"
        assert "simulation_enabled" in data, "Response should contain simulation_enabled"
        assert "river_mile" in data, "Response should contain river_mile"
        assert "speed_knots" in data, "Response should contain speed_knots"
        assert "heading" in data, "Response should contain heading"
        assert "in_active_vessels" in data, "Response should contain in_active_vessels"
        
        print(f"Simulation status: enabled={data['simulation_enabled']}, RM={data['river_mile']}, speed={data['speed_knots']}, heading={data['heading']}")
    
    def test_enable_simulation(self):
        """POST /api/user-vessel/simulation/{mmsi} - should enable simulation"""
        payload = {
            "enabled": True,
            "river_mile": 800.0,
            "speed_knots": 8.0,
            "heading": "southbound"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/user-vessel/simulation/{TEST_MMSI}",
            json=payload
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True, "Response should have success=True"
        assert "simulation" in data, "Response should contain simulation config"
        
        sim = data["simulation"]
        assert sim["enabled"] == True, "Simulation should be enabled"
        assert sim["river_mile"] == 800.0, f"River mile should be 800.0, got {sim['river_mile']}"
        assert sim["speed_knots"] == 8.0, f"Speed should be 8.0, got {sim['speed_knots']}"
        assert sim["heading"] == "southbound", f"Heading should be southbound, got {sim['heading']}"
        
        print(f"Simulation enabled: RM={sim['river_mile']}, speed={sim['speed_knots']}, heading={sim['heading']}")
    
    def test_verify_simulation_enabled(self):
        """GET after enabling - verify simulation is enabled"""
        # First enable simulation
        enable_response = requests.post(
            f"{BASE_URL}/api/user-vessel/simulation/{TEST_MMSI}",
            json={"enabled": True, "river_mile": 810.0, "speed_knots": 5.0, "heading": "northbound"}
        )
        assert enable_response.status_code == 200, "Enable should succeed"
        
        # Then verify with GET
        response = requests.get(f"{BASE_URL}/api/user-vessel/simulation/{TEST_MMSI}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["simulation_enabled"] == True, "Simulation should be enabled"
        assert data["river_mile"] == 810.0, f"River mile should be 810.0, got {data['river_mile']}"
        assert data["speed_knots"] == 5.0, f"Speed should be 5.0, got {data['speed_knots']}"
        assert data["heading"] == "northbound", f"Heading should be northbound, got {data['heading']}"
        
        print(f"Verified: enabled={data['simulation_enabled']}, RM={data['river_mile']}")
    
    def test_disable_simulation(self):
        """POST with enabled=False - should disable simulation"""
        payload = {
            "enabled": False
        }
        
        response = requests.post(
            f"{BASE_URL}/api/user-vessel/simulation/{TEST_MMSI}",
            json=payload
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True, "Response should have success=True"
        assert data["simulation"]["enabled"] == False, "Simulation should be disabled"
        
        print("Simulation disabled successfully")
    
    def test_stop_simulation_endpoint(self):
        """POST /api/user-vessel/simulation/{mmsi}/stop - should stop simulation"""
        # First enable
        requests.post(
            f"{BASE_URL}/api/user-vessel/simulation/{TEST_MMSI}",
            json={"enabled": True}
        )
        
        # Then stop
        response = requests.post(f"{BASE_URL}/api/user-vessel/simulation/{TEST_MMSI}/stop")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True, "Response should have success=True"
        assert data.get("enabled") == False, "enabled should be False"
        assert data.get("mmsi") == TEST_MMSI, f"MMSI should be {TEST_MMSI}"
        
        print("Simulation stopped via /stop endpoint")
    
    def test_update_simulation_parameters(self):
        """POST with only some parameters - should update those params only"""
        # First enable with initial values
        requests.post(
            f"{BASE_URL}/api/user-vessel/simulation/{TEST_MMSI}",
            json={"enabled": True, "river_mile": 820.0, "speed_knots": 4.0, "heading": "southbound"}
        )
        
        # Update only speed
        response = requests.post(
            f"{BASE_URL}/api/user-vessel/simulation/{TEST_MMSI}",
            json={"speed_knots": 10.0}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True, "Response should have success=True"
        assert data["simulation"]["speed_knots"] == 10.0, f"Speed should be 10.0, got {data['simulation']['speed_knots']}"
        
        print(f"Parameter update successful: speed_knots={data['simulation']['speed_knots']}")
    
    def test_heading_values(self):
        """Test both heading values work correctly"""
        # Test southbound
        response = requests.post(
            f"{BASE_URL}/api/user-vessel/simulation/{TEST_MMSI}",
            json={"enabled": True, "heading": "southbound"}
        )
        assert response.status_code == 200
        assert response.json()["simulation"]["heading"] == "southbound"
        print("Heading 'southbound' works")
        
        # Test northbound
        response = requests.post(
            f"{BASE_URL}/api/user-vessel/simulation/{TEST_MMSI}",
            json={"enabled": True, "heading": "northbound"}
        )
        assert response.status_code == 200
        assert response.json()["simulation"]["heading"] == "northbound"
        print("Heading 'northbound' works")
    
    def test_vessel_appears_in_active_vessels(self):
        """Verify vessel appears in active_vessels when simulation is enabled"""
        # Enable simulation
        requests.post(
            f"{BASE_URL}/api/user-vessel/simulation/{TEST_MMSI}",
            json={"enabled": True, "river_mile": 815.0, "speed_knots": 5.0, "heading": "southbound"}
        )
        
        # Check if vessel is in active_vessels via the status endpoint
        response = requests.get(f"{BASE_URL}/api/user-vessel/simulation/{TEST_MMSI}")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("in_active_vessels") == True, "Vessel should be in active_vessels when simulation is enabled"
        print(f"Vessel in_active_vessels: {data.get('in_active_vessels')}")


class TestUserVesselSimulationWithAuth:
    """Tests that require authentication for full flow"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Create authenticated session"""
        session = requests.Session()
        
        # Login
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "chaddillerud@gmail.com",
                "password": "test123"
            }
        )
        
        if login_response.status_code != 200:
            pytest.skip("Authentication failed - skipping authenticated tests")
        
        return session
    
    def test_simulation_with_user_mmsi(self, auth_session):
        """Test simulation with user's configured MMSI"""
        # Get user info to find their MMSI
        user_response = auth_session.get(f"{BASE_URL}/api/auth/me")
        if user_response.status_code != 200:
            pytest.skip("Could not get user info")
        
        user = user_response.json()
        vessels = user.get("vessels", [])
        
        if not vessels:
            print("User has no vessels configured - test passed (no MMSI to test)")
            return
        
        # Use user's primary vessel or first vessel
        user_mmsi = None
        for v in vessels:
            if v.get("is_primary"):
                user_mmsi = v.get("mmsi")
                break
        if not user_mmsi and vessels:
            user_mmsi = vessels[0].get("mmsi")
        
        if not user_mmsi:
            print("User has no vessel MMSI - test passed")
            return
        
        print(f"Testing with user's MMSI: {user_mmsi}")
        
        # Enable simulation for user's vessel
        response = requests.post(
            f"{BASE_URL}/api/user-vessel/simulation/{user_mmsi}",
            json={"enabled": True, "river_mile": 815.0, "speed_knots": 5.0, "heading": "southbound"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.json().get("success") == True, "Should succeed"
        
        # Verify it's enabled
        get_response = requests.get(f"{BASE_URL}/api/user-vessel/simulation/{user_mmsi}")
        assert get_response.status_code == 200
        assert get_response.json().get("simulation_enabled") == True
        
        print(f"Simulation enabled for user's MMSI {user_mmsi}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
