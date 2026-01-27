"""
Test new features for River Watch AIS app:
1. Demo vessel direction (upriver/downriver)
2. ETA to next lock calculation
3. Demo vessel toggle in Settings
4. Session persistence
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_USER = {
    "email": "chaddillerud@gmail.com",
    "password": "test123"
}


class TestDemoVessels:
    """Test demo vessel features - direction and ETA"""
    
    def test_demo_vessels_status_endpoint(self):
        """Test /api/demo-vessels/status returns correct structure"""
        response = requests.get(f"{BASE_URL}/api/demo-vessels/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "enabled" in data
        assert "vessels" in data
        assert isinstance(data["enabled"], bool)
        assert isinstance(data["vessels"], list)
        print(f"✓ Demo vessels status: enabled={data['enabled']}, vessels={data['vessels']}")
    
    def test_demo_vessel_delta_queen_direction(self):
        """Test DELTA QUEEN shows 'downriver' direction"""
        response = requests.get(f"{BASE_URL}/api/vessels")
        assert response.status_code == 200
        
        vessels = response.json()
        delta_queen = next((v for v in vessels if v.get("mmsi") == "DEMO001"), None)
        
        if delta_queen is None:
            pytest.skip("Demo vessels may be disabled - DEMO001 not found")
        
        # Verify direction fields
        assert delta_queen.get("direction") == "downriver", f"Expected 'downriver', got '{delta_queen.get('direction')}'"
        assert delta_queen.get("heading_direction") == "southbound", f"Expected 'southbound', got '{delta_queen.get('heading_direction')}'"
        assert delta_queen.get("name") == "M/V DELTA QUEEN"
        print(f"✓ DELTA QUEEN direction: {delta_queen.get('direction')}, heading: {delta_queen.get('heading_direction')}")
    
    def test_demo_vessel_river_runner_direction(self):
        """Test RIVER RUNNER shows 'upriver' direction"""
        response = requests.get(f"{BASE_URL}/api/vessels")
        assert response.status_code == 200
        
        vessels = response.json()
        river_runner = next((v for v in vessels if v.get("mmsi") == "DEMO002"), None)
        
        if river_runner is None:
            pytest.skip("Demo vessels may be disabled - DEMO002 not found")
        
        # Verify direction fields
        assert river_runner.get("direction") == "upriver", f"Expected 'upriver', got '{river_runner.get('direction')}'"
        assert river_runner.get("heading_direction") == "northbound", f"Expected 'northbound', got '{river_runner.get('heading_direction')}'"
        assert river_runner.get("name") == "M/V RIVER RUNNER"
        print(f"✓ RIVER RUNNER direction: {river_runner.get('direction')}, heading: {river_runner.get('heading_direction')}")


class TestNextLockETA:
    """Test ETA to next lock calculation"""
    
    def test_demo_vessel_has_next_lock_eta(self):
        """Test demo vessels have next_lock ETA calculated"""
        response = requests.get(f"{BASE_URL}/api/vessels")
        assert response.status_code == 200
        
        vessels = response.json()
        demo_vessels = [v for v in vessels if v.get("mmsi") in ["DEMO001", "DEMO002"]]
        
        if not demo_vessels:
            pytest.skip("Demo vessels not found - may be disabled")
        
        for vessel in demo_vessels:
            next_lock = vessel.get("next_lock")
            assert next_lock is not None, f"Vessel {vessel.get('name')} missing next_lock"
            
            # Verify next_lock structure
            assert "next_lock_id" in next_lock
            assert "next_lock_name" in next_lock
            assert "next_lock_rm" in next_lock
            assert "distance_miles" in next_lock
            assert "eta_minutes" in next_lock
            assert "eta_display" in next_lock
            
            # Verify eta_display format (e.g., "2h 50m" or "45m")
            eta_display = next_lock.get("eta_display")
            assert eta_display is not None
            assert "m" in eta_display, f"ETA display should contain 'm': {eta_display}"
            
            print(f"✓ {vessel.get('name')}: next_lock={next_lock.get('next_lock_name')}, ETA={eta_display}")
    
    def test_eta_calculation_logic(self):
        """Test ETA calculation is reasonable based on speed and distance"""
        response = requests.get(f"{BASE_URL}/api/vessels")
        assert response.status_code == 200
        
        vessels = response.json()
        delta_queen = next((v for v in vessels if v.get("mmsi") == "DEMO001"), None)
        
        if delta_queen is None:
            pytest.skip("DEMO001 not found")
        
        next_lock = delta_queen.get("next_lock")
        if not next_lock:
            pytest.skip("next_lock not calculated")
        
        # Verify ETA is reasonable
        # DELTA QUEEN: ~4.5 knots = ~5.2 mph
        # Distance varies, but ETA should be positive and reasonable
        eta_minutes = next_lock.get("eta_minutes")
        distance = next_lock.get("distance_miles")
        
        assert eta_minutes > 0, "ETA should be positive"
        assert distance > 0, "Distance should be positive"
        
        # Rough check: at 5 mph, 10 miles = 120 minutes
        # Allow for some variance
        expected_eta_rough = (distance / 5.2) * 60  # minutes
        assert abs(eta_minutes - expected_eta_rough) < expected_eta_rough * 0.5, \
            f"ETA {eta_minutes}m seems off for {distance}mi at ~5mph (expected ~{expected_eta_rough:.0f}m)"
        
        print(f"✓ ETA calculation verified: {distance}mi → {eta_minutes}m")


class TestDemoVesselToggle:
    """Test demo vessel toggle functionality"""
    
    @pytest.fixture
    def auth_session(self):
        """Get authenticated session"""
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/auth/login", json=TEST_USER)
        if response.status_code != 200:
            pytest.skip("Could not authenticate")
        return session
    
    def test_toggle_requires_auth(self):
        """Test toggle endpoint requires authentication"""
        response = requests.post(f"{BASE_URL}/api/demo-vessels/toggle", json={"enabled": False})
        assert response.status_code == 401
        print("✓ Toggle endpoint requires authentication")
    
    def test_toggle_demo_vessels_off(self, auth_session):
        """Test disabling demo vessels"""
        # First ensure they're enabled
        auth_session.post(f"{BASE_URL}/api/demo-vessels/toggle", json={"enabled": True})
        
        # Now disable
        response = auth_session.post(f"{BASE_URL}/api/demo-vessels/toggle", json={"enabled": False})
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") == True
        assert data.get("enabled") == False
        
        # Verify status endpoint reflects change
        status_response = requests.get(f"{BASE_URL}/api/demo-vessels/status")
        assert status_response.json().get("enabled") == False
        print("✓ Demo vessels disabled successfully")
    
    def test_toggle_demo_vessels_on(self, auth_session):
        """Test enabling demo vessels"""
        # First ensure they're disabled
        auth_session.post(f"{BASE_URL}/api/demo-vessels/toggle", json={"enabled": False})
        
        # Now enable
        response = auth_session.post(f"{BASE_URL}/api/demo-vessels/toggle", json={"enabled": True})
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") == True
        assert data.get("enabled") == True
        
        # Verify status endpoint reflects change
        status_response = requests.get(f"{BASE_URL}/api/demo-vessels/status")
        assert status_response.json().get("enabled") == True
        print("✓ Demo vessels enabled successfully")


class TestSessionPersistence:
    """Test session persistence across requests"""
    
    def test_login_sets_cookie(self):
        """Test login sets session cookie"""
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/auth/login", json=TEST_USER)
        assert response.status_code == 200
        
        # Check cookie was set
        cookies = session.cookies.get_dict()
        assert "session_token" in cookies or len(cookies) > 0, "Session cookie should be set"
        print(f"✓ Login sets session cookie")
    
    def test_session_persists_across_requests(self):
        """Test session persists across multiple requests"""
        session = requests.Session()
        
        # Login
        login_response = session.post(f"{BASE_URL}/api/auth/login", json=TEST_USER)
        assert login_response.status_code == 200
        
        # Make multiple requests with same session
        for i in range(3):
            me_response = session.get(f"{BASE_URL}/api/auth/me")
            assert me_response.status_code == 200
            assert me_response.json().get("email") == TEST_USER["email"]
        
        print("✓ Session persists across multiple requests")
    
    def test_auth_me_returns_user_data(self):
        """Test /api/auth/me returns correct user data"""
        session = requests.Session()
        
        # Login
        login_response = session.post(f"{BASE_URL}/api/auth/login", json=TEST_USER)
        assert login_response.status_code == 200
        
        # Get user data
        me_response = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response.status_code == 200
        
        user = me_response.json()
        assert user.get("email") == TEST_USER["email"]
        assert "user_id" in user
        assert "vessels" in user
        print(f"✓ /api/auth/me returns user: {user.get('email')}")
    
    def test_logout_clears_session(self):
        """Test logout clears session"""
        session = requests.Session()
        
        # Login
        login_response = session.post(f"{BASE_URL}/api/auth/login", json=TEST_USER)
        assert login_response.status_code == 200
        
        # Verify logged in
        me_response = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response.status_code == 200
        
        # Logout
        logout_response = session.post(f"{BASE_URL}/api/auth/logout")
        assert logout_response.status_code == 200
        
        # Verify session is cleared
        me_response_after = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response_after.status_code == 401
        print("✓ Logout clears session")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
