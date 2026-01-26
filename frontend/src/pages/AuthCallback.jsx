import { useEffect, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Loader2, Anchor } from "lucide-react";

export default function AuthCallback() {
  const navigate = useNavigate();
  const location = useLocation();
  const { processGoogleCallback } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    // Prevent double processing in StrictMode
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const processCallback = async () => {
      // Extract session_id from URL hash
      const hash = location.hash;
      const params = new URLSearchParams(hash.replace('#', ''));
      const sessionId = params.get('session_id');

      if (!sessionId) {
        console.error('No session_id found in callback URL');
        navigate('/login');
        return;
      }

      try {
        await processGoogleCallback(sessionId);
        // Clear the URL hash and navigate to dashboard
        window.history.replaceState(null, '', window.location.pathname);
        navigate('/', { replace: true });
      } catch (error) {
        console.error('Google auth callback failed:', error);
        navigate('/login');
      }
    };

    processCallback();
  }, [location, navigate, processGoogleCallback]);

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center">
      <div className="text-center">
        <div className="mx-auto w-16 h-16 rounded-full bg-cyan-500/10 flex items-center justify-center mb-4">
          <Anchor className="w-8 h-8 text-cyan-400 animate-pulse" />
        </div>
        <Loader2 className="w-8 h-8 text-cyan-400 animate-spin mx-auto mb-4" />
        <p className="text-slate-400">Completing sign in...</p>
      </div>
    </div>
  );
}
