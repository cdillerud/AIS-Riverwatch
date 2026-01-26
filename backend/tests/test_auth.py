"""
River Watch Authentication & Vessel Management API Tests
Tests for:
- User Registration (POST /api/auth/register)
- User Login (POST /api/auth/login)
- Session Persistence (GET /api/auth/me)
- User Logout (POST /api/auth/logout)
- Add Vessel to Fleet (POST /api/user/vessels)
- Get User Vessels (GET /api/user/vessels)
- Set Primary Vessel (PUT /api/user/vessels/{mmsi}/primary)
- Remove Vessel (DELETE /api/user/vessels/{mmsi})
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test data
TEST_USER_EMAIL = f"test_{uuid.uuid4().hex[:8]}@example.com"
TEST_USER_PASSWORD = "password123"
TEST_USER_NAME = "Test User"

NEW_USER_EMAIL = f"newuser_{uuid.uuid4().hex[:8]}@example.com"
NEW_USER_PASSWORD = "newpass456"
NEW_USER_NAME = "New User"

TEST_MMSI_1 = "123456789"
TEST_MMSI_2 = "987654321"
TEST_BOAT_NAME_1 = "Test Boat One"
TEST_BOAT_NAME_2 = "Test Boat Two"


@pytest.fixture(scope="module")
def api_session():
    """Create a requests session for API calls."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


class TestHealthCheck:
    """Basic health check tests."""
    
    def test_api_status(self, api_session):
        """Test that the API is accessible."""
        response = api_session.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "online"
        print(f"✓ API status: {data}")


class TestUserRegistration:
    """User registration flow tests."""
    
    def test_register_new_user(self, api_session):
        """Test registering a new user with email/password."""
        response = api_session.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD,
                "name": TEST_USER_NAME
            }
        )
        
        assert response.status_code == 200, f"Registration failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert data.get("success") == True
        assert "user" in data
        assert data["user"]["email"] == TEST_USER_EMAIL
        assert data["user"]["name"] == TEST_USER_NAME
        assert "user_id" in data["user"]
        assert "password_hash" not in data["user"]  # Should not expose password
        
        # Verify session cookie was set
        assert "session_token" in response.cookies or any("session_token" in c for c in response.headers.get("set-cookie", ""))
        
        print(f"✓ Registered user: {data['user']['email']} ({data['user']['user_id']})")
    
    def test_register_duplicate_email(self, api_session):
        """Test that duplicate email registration fails."""
        response = api_session.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": TEST_USER_EMAIL,  # Same email as before
                "password": "differentpass",
                "name": "Another User"
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "already registered" in data.get("detail", "").lower()
        print(f"✓ Duplicate email rejected: {data.get('detail')}")
    
    def test_register_invalid_email(self, api_session):
        """Test that invalid email format is rejected."""
        response = api_session.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": "not-an-email",
                "password": "password123",
                "name": "Test User"
            }
        )
        
        assert response.status_code == 422  # Validation error
        print("✓ Invalid email format rejected")


class TestUserLogin:
    """User login flow tests."""
    
    def test_login_success(self, api_session):
        """Test successful login with correct credentials."""
        # First register a user
        register_email = f"login_test_{uuid.uuid4().hex[:8]}@example.com"
        api_session.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": register_email,
                "password": "testpass123",
                "name": "Login Test User"
            }
        )
        
        # Now login
        response = api_session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": register_email,
                "password": "testpass123"
            }
        )
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        
        assert data.get("success") == True
        assert "user" in data
        assert data["user"]["email"] == register_email
        assert "password_hash" not in data["user"]
        
        print(f"✓ Login successful for: {register_email}")
    
    def test_login_wrong_password(self, api_session):
        """Test login with wrong password."""
        response = api_session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": TEST_USER_EMAIL,
                "password": "wrongpassword"
            }
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "invalid" in data.get("detail", "").lower()
        print(f"✓ Wrong password rejected: {data.get('detail')}")
    
    def test_login_nonexistent_user(self, api_session):
        """Test login with non-existent email."""
        response = api_session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "anypassword"
            }
        )
        
        assert response.status_code == 401
        print("✓ Non-existent user login rejected")


class TestSessionPersistence:
    """Session persistence tests."""
    
    def test_get_current_user_authenticated(self, api_session):
        """Test GET /api/auth/me returns user data when authenticated."""
        # Register and login to get session
        session_email = f"session_test_{uuid.uuid4().hex[:8]}@example.com"
        
        # Register
        reg_response = api_session.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": session_email,
                "password": "sessionpass123",
                "name": "Session Test User"
            }
        )
        assert reg_response.status_code == 200
        
        # Get current user (should work with session cookie)
        response = api_session.get(f"{BASE_URL}/api/auth/me")
        
        assert response.status_code == 200, f"Auth check failed: {response.text}"
        data = response.json()
        
        assert data["email"] == session_email
        assert data["name"] == "Session Test User"
        assert "user_id" in data
        assert "password_hash" not in data
        
        print(f"✓ Session persistence verified for: {session_email}")
    
    def test_get_current_user_unauthenticated(self):
        """Test GET /api/auth/me returns 401 when not authenticated."""
        # Create a fresh session without cookies
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        
        response = fresh_session.get(f"{BASE_URL}/api/auth/me")
        
        assert response.status_code == 401
        print("✓ Unauthenticated request correctly rejected")


class TestUserLogout:
    """User logout tests."""
    
    def test_logout_clears_session(self, api_session):
        """Test that logout clears the session."""
        # Register and login
        logout_email = f"logout_test_{uuid.uuid4().hex[:8]}@example.com"
        
        api_session.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": logout_email,
                "password": "logoutpass123",
                "name": "Logout Test User"
            }
        )
        
        # Verify logged in
        me_response = api_session.get(f"{BASE_URL}/api/auth/me")
        assert me_response.status_code == 200
        
        # Logout
        logout_response = api_session.post(f"{BASE_URL}/api/auth/logout")
        assert logout_response.status_code == 200
        data = logout_response.json()
        assert data.get("success") == True
        
        # Verify session is cleared - should get 401 now
        me_after_logout = api_session.get(f"{BASE_URL}/api/auth/me")
        assert me_after_logout.status_code == 401
        
        print("✓ Logout successfully cleared session")


class TestVesselManagement:
    """Vessel management (fleet) tests."""
    
    @pytest.fixture(autouse=True)
    def setup_authenticated_session(self, api_session):
        """Setup an authenticated session for vessel tests."""
        vessel_email = f"vessel_test_{uuid.uuid4().hex[:8]}@example.com"
        
        # Register new user
        reg_response = api_session.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": vessel_email,
                "password": "vesselpass123",
                "name": "Vessel Test User"
            }
        )
        assert reg_response.status_code == 200, f"Setup failed: {reg_response.text}"
        
        self.test_email = vessel_email
        self.session = api_session
        yield
        
        # Cleanup - logout
        api_session.post(f"{BASE_URL}/api/auth/logout")
    
    def test_add_vessel_to_fleet(self):
        """Test adding a vessel to user's fleet."""
        response = self.session.post(
            f"{BASE_URL}/api/user/vessels",
            json={
                "mmsi": TEST_MMSI_1,
                "boat_name": TEST_BOAT_NAME_1,
                "is_primary": True
            }
        )
        
        assert response.status_code == 200, f"Add vessel failed: {response.text}"
        data = response.json()
        
        assert data.get("success") == True
        assert "vessel" in data
        assert data["vessel"]["mmsi"] == TEST_MMSI_1
        assert data["vessel"]["boat_name"] == TEST_BOAT_NAME_1
        assert data["vessel"]["is_primary"] == True
        
        print(f"✓ Added vessel: {TEST_BOAT_NAME_1} (MMSI: {TEST_MMSI_1})")
    
    def test_get_user_vessels(self):
        """Test getting user's fleet."""
        # First add a vessel
        self.session.post(
            f"{BASE_URL}/api/user/vessels",
            json={
                "mmsi": TEST_MMSI_1,
                "boat_name": TEST_BOAT_NAME_1,
                "is_primary": True
            }
        )
        
        # Get vessels
        response = self.session.get(f"{BASE_URL}/api/user/vessels")
        
        assert response.status_code == 200, f"Get vessels failed: {response.text}"
        data = response.json()
        
        assert "vessels" in data
        assert len(data["vessels"]) >= 1
        
        # Find our vessel
        vessel = next((v for v in data["vessels"] if v["mmsi"] == TEST_MMSI_1), None)
        assert vessel is not None
        assert vessel["boat_name"] == TEST_BOAT_NAME_1
        
        print(f"✓ Retrieved {len(data['vessels'])} vessel(s)")
    
    def test_add_multiple_vessels(self):
        """Test adding multiple vessels to fleet."""
        # Add first vessel as primary
        self.session.post(
            f"{BASE_URL}/api/user/vessels",
            json={
                "mmsi": TEST_MMSI_1,
                "boat_name": TEST_BOAT_NAME_1,
                "is_primary": True
            }
        )
        
        # Add second vessel (not primary)
        response = self.session.post(
            f"{BASE_URL}/api/user/vessels",
            json={
                "mmsi": TEST_MMSI_2,
                "boat_name": TEST_BOAT_NAME_2,
                "is_primary": False
            }
        )
        
        assert response.status_code == 200
        
        # Verify both vessels exist
        vessels_response = self.session.get(f"{BASE_URL}/api/user/vessels")
        data = vessels_response.json()
        
        assert len(data["vessels"]) >= 2
        print(f"✓ Multiple vessels added successfully")
    
    def test_set_primary_vessel(self):
        """Test setting a vessel as primary."""
        # Add two vessels
        self.session.post(
            f"{BASE_URL}/api/user/vessels",
            json={"mmsi": TEST_MMSI_1, "boat_name": TEST_BOAT_NAME_1, "is_primary": True}
        )
        self.session.post(
            f"{BASE_URL}/api/user/vessels",
            json={"mmsi": TEST_MMSI_2, "boat_name": TEST_BOAT_NAME_2, "is_primary": False}
        )
        
        # Set second vessel as primary
        response = self.session.put(f"{BASE_URL}/api/user/vessels/{TEST_MMSI_2}/primary")
        
        assert response.status_code == 200, f"Set primary failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        
        # Verify primary changed
        vessels_response = self.session.get(f"{BASE_URL}/api/user/vessels")
        vessels = vessels_response.json()["vessels"]
        
        vessel_1 = next((v for v in vessels if v["mmsi"] == TEST_MMSI_1), None)
        vessel_2 = next((v for v in vessels if v["mmsi"] == TEST_MMSI_2), None)
        
        assert vessel_1["is_primary"] == False
        assert vessel_2["is_primary"] == True
        
        print(f"✓ Primary vessel changed to: {TEST_BOAT_NAME_2}")
    
    def test_remove_vessel(self):
        """Test removing a vessel from fleet."""
        # Add a vessel
        self.session.post(
            f"{BASE_URL}/api/user/vessels",
            json={"mmsi": TEST_MMSI_1, "boat_name": TEST_BOAT_NAME_1, "is_primary": True}
        )
        
        # Remove it
        response = self.session.delete(f"{BASE_URL}/api/user/vessels/{TEST_MMSI_1}")
        
        assert response.status_code == 200, f"Remove vessel failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        
        # Verify removed
        vessels_response = self.session.get(f"{BASE_URL}/api/user/vessels")
        vessels = vessels_response.json()["vessels"]
        
        vessel = next((v for v in vessels if v["mmsi"] == TEST_MMSI_1), None)
        assert vessel is None
        
        print(f"✓ Vessel removed: {TEST_MMSI_1}")
    
    def test_add_duplicate_vessel_fails(self):
        """Test that adding the same MMSI twice fails."""
        # Add vessel first time
        self.session.post(
            f"{BASE_URL}/api/user/vessels",
            json={"mmsi": TEST_MMSI_1, "boat_name": TEST_BOAT_NAME_1, "is_primary": True}
        )
        
        # Try to add same MMSI again
        response = self.session.post(
            f"{BASE_URL}/api/user/vessels",
            json={"mmsi": TEST_MMSI_1, "boat_name": "Different Name", "is_primary": False}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "already" in data.get("detail", "").lower()
        
        print("✓ Duplicate vessel correctly rejected")


class TestProtectedRoutes:
    """Test that protected routes require authentication."""
    
    def test_vessels_endpoint_requires_auth(self):
        """Test that /api/user/vessels requires authentication."""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        
        response = fresh_session.get(f"{BASE_URL}/api/user/vessels")
        assert response.status_code == 401
        print("✓ Vessels endpoint requires authentication")
    
    def test_add_vessel_requires_auth(self):
        """Test that adding vessel requires authentication."""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        
        response = fresh_session.post(
            f"{BASE_URL}/api/user/vessels",
            json={"mmsi": "111111111", "boat_name": "Test", "is_primary": True}
        )
        assert response.status_code == 401
        print("✓ Add vessel endpoint requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
