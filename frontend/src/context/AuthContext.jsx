import { createContext, useContext, useState, useEffect, useCallback } from 'react';

import { API } from '../lib/api';
import { unsubscribePush } from '../lib/push';

const AuthContext = createContext(null);

// The server answered with something other than JSON (an HTML error page from
// static hosting or a proxy): say so plainly instead of Safari's
// "The string did not match the expected pattern".
export const SERVER_UNAVAILABLE = "River Watch's server isn't reachable right now. Please try again in a little while.";
export async function readJson(response) {
  const type = response.headers.get('content-type') || '';
  if (!type.includes('json')) throw new Error(SERVER_UNAVAILABLE);
  try {
    return await response.json();
  } catch (e) {
    throw new Error(SERVER_UNAVAILABLE);
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Check authentication status on mount
  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      const response = await fetch(`${API}/auth/me`, {
        credentials: 'include'
      });
      
      if (response.ok) {
        const userData = await readJson(response);
        setUser(userData);
      } else {
        setUser(null);
      }
    } catch (err) {
      console.error('Auth check failed:', err);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const login = async (email, password) => {
    setError(null);
    try {
      const response = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email, password })
      });

      const data = await readJson(response);
      
      if (!response.ok) {
        throw new Error(data.detail || 'Login failed');
      }

      setUser(data.user);
      return data.user;
    } catch (err) {
      // fetch itself failed (offline, DNS, server down): Safari says "Load failed"
      const e = err instanceof TypeError ? new Error(SERVER_UNAVAILABLE) : err;
      setError(e.message);
      throw e;
    }
  };

  const register = async (email, password, name) => {
    setError(null);
    try {
      const response = await fetch(`${API}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email, password, name })
      });

      const data = await readJson(response);
      
      // Handle existing user case (not an HTTP error, but a logical error)
      if (data.user_exists) {
        const error = new Error(data.message || 'An account with this email already exists');
        error.userExists = true;
        throw error;
      }
      
      if (!response.ok) {
        throw new Error(data.detail || 'Registration failed');
      }

      setUser(data.user);
      return data.user;
    } catch (err) {
      // fetch itself failed (offline, DNS, server down): Safari says "Load failed"
      const e = err instanceof TypeError ? new Error(SERVER_UNAVAILABLE) : err;
      setError(e.message);
      throw e;
    }
  };

  // credential: the Google Identity Services ID token from GoogleSignInButton.
  const loginWithGoogle = async (credential) => {
    setError(null);
    try {
      const response = await fetch(`${API}/auth/google`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ credential })
      });

      const data = await readJson(response);

      if (!response.ok) {
        throw new Error(data.detail || 'Google sign-in failed');
      }

      setUser(data.user);
      return data.user;
    } catch (err) {
      // fetch itself failed (offline, DNS, server down): Safari says "Load failed"
      const e = err instanceof TypeError ? new Error(SERVER_UNAVAILABLE) : err;
      setError(e.message);
      throw e;
    }
  };

  const logout = async () => {
    try {
      // Stop alerts to this phone while the session still exists (DELETE needs it).
      await Promise.race([unsubscribePush(), new Promise((r) => setTimeout(r, 3000))]);
    } catch (e) { /* push unavailable */ }
    try {
      await fetch(`${API}/auth/logout`, {
        method: 'POST',
        credentials: 'include'
      });
    } catch (err) {
      console.error('Logout error:', err);
    } finally {
      // Clear all user-specific localStorage data to prevent session bleed
      localStorage.removeItem('riverwatch_mmsi');
      localStorage.removeItem('riverwatch_connection');
      console.log('[AUTH] Cleared localStorage on logout');
      // Offline copies of lock boards (service worker, sw.js) carry the boat's
      // MMSI in their URLs: drop them with the session.
      try {
        if (typeof caches !== 'undefined') {
          caches.keys().then((ks) => ks.filter((k) => k.endsWith('-api')).forEach((k) => caches.delete(k))).catch(() => {});
        }
      } catch (e) { /* no Cache API */ }
      setUser(null);
    }
  };

  const addVessel = async (mmsi, boatName, isPrimary = false) => {
    try {
      const response = await fetch(`${API}/user/vessels`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ mmsi, boat_name: boatName, is_primary: isPrimary })
      });

      const data = await readJson(response);
      
      if (!response.ok) {
        throw new Error(data.detail || 'Failed to add vessel');
      }

      // Refresh user data
      await checkAuth();
      return data.vessel;
    } catch (err) {
      throw err;
    }
  };

  const removeVessel = async (mmsi) => {
    try {
      const response = await fetch(`${API}/user/vessels/${mmsi}`, {
        method: 'DELETE',
        credentials: 'include'
      });

      if (!response.ok) {
        const data = await readJson(response);
        throw new Error(data.detail || 'Failed to remove vessel');
      }

      // Refresh user data
      await checkAuth();
    } catch (err) {
      throw err;
    }
  };

  const setPrimaryVessel = async (mmsi) => {
    try {
      const response = await fetch(`${API}/user/vessels/${mmsi}/primary`, {
        method: 'PUT',
        credentials: 'include'
      });

      if (!response.ok) {
        const data = await readJson(response);
        throw new Error(data.detail || 'Failed to set primary vessel');
      }

      // Refresh user data
      await checkAuth();
    } catch (err) {
      throw err;
    }
  };

  const updateProfile = async (updates) => {
    try {
      const response = await fetch(`${API}/user/profile`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(updates)
      });

      if (!response.ok) {
        const data = await readJson(response);
        throw new Error(data.detail || 'Failed to update profile');
      }

      // Refresh user data
      await checkAuth();
    } catch (err) {
      throw err;
    }
  };

  const value = {
    user,
    loading,
    error,
    isAuthenticated: !!user,
    login,
    register,
    loginWithGoogle,
    logout,
    addVessel,
    removeVessel,
    setPrimaryVessel,
    updateProfile,
    refreshUser: checkAuth
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export default AuthContext;
