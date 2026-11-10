import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Radio, Mail, Lock, User, AlertCircle, Loader2, ChevronLeft, Check } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import GoogleSignInButton from "@/components/GoogleSignInButton";

export default function RegisterPage() {
  const navigate = useNavigate();
  const { register, loginWithGoogle, error } = useAuth();
  
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [localError, setLocalError] = useState("");
  const [userExistsError, setUserExistsError] = useState(false);

  const handleRegister = async (e) => {
    e.preventDefault();
    setLocalError("");
    setUserExistsError(false);

    if (password !== confirmPassword) {
      setLocalError("Passwords do not match");
      return;
    }

    if (password.length < 6) {
      setLocalError("Password must be at least 6 characters");
      return;
    }

    setLoading(true);

    try {
      await register(email, password, name);
      navigate("/dashboard");
    } catch (err) {
      if (err.userExists) {
        setUserExistsError(true);
      }
      setLocalError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleCredential = async (credential) => {
    setLocalError("");
    setLoading(true);
    try {
      await loginWithGoogle(credential);
      navigate("/dashboard");
    } catch (err) {
      setLocalError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const displayError = localError || error;

  // Password requirements check
  const hasMinLength = password.length >= 6;
  const passwordsMatch = password && confirmPassword && password === confirmPassword;

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      {/* Background Gradient */}
      <div className="fixed inset-0 bg-gradient-to-b from-slate-950 via-slate-900/50 to-slate-950 pointer-events-none" />
      
      {/* Back to Home */}
      <Link 
        to="/" 
        className="fixed top-6 left-6 flex items-center gap-2 text-slate-500 hover:text-white transition-colors z-20"
      >
        <ChevronLeft className="w-4 h-4" />
        <span className="font-heading text-sm uppercase tracking-wider">Back</span>
      </Link>

      {/* Register Card */}
      <div className="relative z-10 w-full max-w-md">
        <div className="bg-slate-900/80 backdrop-blur-xl border border-white/10 rounded-xl shadow-2xl p-8">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="flex items-center justify-center gap-2 mb-4">
              <Radio className="w-8 h-8 text-cyan-400" />
              <span className="font-heading text-xl font-bold uppercase tracking-wider text-white">
                RiverWatch<span className="text-cyan-400 ml-1">AIS</span>
              </span>
            </div>
            <h1 className="font-heading text-2xl font-bold uppercase tracking-wide text-white mb-2">
              Create Account
            </h1>
            <p className="text-slate-400 text-sm">
              Start tracking vessels and timing locks
            </p>
          </div>

          {/* Error Message */}
          {displayError && (
            <div className={`mb-6 p-3 rounded-lg flex items-start gap-2 text-sm ${
              userExistsError 
                ? 'bg-amber-500/10 border border-amber-500/30 text-amber-400' 
                : 'bg-red-500/10 border border-red-500/30 text-red-400'
            }`}>
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <div>
                <div>{displayError}</div>
                {userExistsError && (
                  <div className="mt-2 flex gap-2">
                    <Link 
                      to="/login" 
                      className="text-cyan-400 hover:text-cyan-300 underline"
                    >
                      Sign in instead
                    </Link>
                    <span className="text-slate-500">or</span>
                    <button 
                      onClick={() => {
                        // TODO: Implement password reset flow
                        alert('Password reset coming soon! Please contact support.');
                      }}
                      className="text-cyan-400 hover:text-cyan-300 underline"
                    >
                      Reset password
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Google sign-in (hidden unless the server has GOOGLE_CLIENT_ID) */}
          <GoogleSignInButton text="signup_with" onCredential={handleGoogleCredential} onError={setLocalError}>
            {/* Divider */}
            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-slate-700"></div>
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="px-2 bg-slate-900 text-slate-500 uppercase tracking-wider">or</span>
              </div>
            </div>
          </GoogleSignInButton>

          {/* Email Form */}
          <form onSubmit={handleRegister} className="space-y-4">
            <div>
              <Label className="text-xs text-slate-400 uppercase tracking-wider font-heading">
                Name
              </Label>
              <div className="relative mt-1">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <Input
                  type="text"
                  placeholder="Captain John"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="pl-10 bg-slate-950/50 border-slate-700 text-white placeholder:text-slate-600 rounded-sm focus:border-cyan-500/50 focus:ring-cyan-500/20"
                  required
                  data-testid="register-name-input"
                />
              </div>
            </div>

            <div>
              <Label className="text-xs text-slate-400 uppercase tracking-wider font-heading">
                Email
              </Label>
              <div className="relative mt-1">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <Input
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="pl-10 bg-slate-950/50 border-slate-700 text-white placeholder:text-slate-600 rounded-sm focus:border-cyan-500/50 focus:ring-cyan-500/20"
                  required
                  data-testid="register-email-input"
                />
              </div>
            </div>

            <div>
              <Label className="text-xs text-slate-400 uppercase tracking-wider font-heading">
                Password
              </Label>
              <div className="relative mt-1">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <Input
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pl-10 bg-slate-950/50 border-slate-700 text-white placeholder:text-slate-600 rounded-sm focus:border-cyan-500/50 focus:ring-cyan-500/20"
                  required
                  minLength={6}
                  data-testid="register-password-input"
                />
              </div>
            </div>

            <div>
              <Label className="text-xs text-slate-400 uppercase tracking-wider font-heading">
                Confirm Password
              </Label>
              <div className="relative mt-1">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <Input
                  type="password"
                  placeholder="••••••••"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="pl-10 bg-slate-950/50 border-slate-700 text-white placeholder:text-slate-600 rounded-sm focus:border-cyan-500/50 focus:ring-cyan-500/20"
                  required
                  data-testid="register-confirm-password-input"
                />
              </div>
            </div>

            {/* Password Requirements */}
            <div className="space-y-1.5 text-xs">
              <div className={`flex items-center gap-2 ${hasMinLength ? 'text-green-400' : 'text-slate-500'}`}>
                <Check className={`w-3 h-3 ${hasMinLength ? 'opacity-100' : 'opacity-30'}`} />
                At least 6 characters
              </div>
              <div className={`flex items-center gap-2 ${passwordsMatch ? 'text-green-400' : 'text-slate-500'}`}>
                <Check className={`w-3 h-3 ${passwordsMatch ? 'opacity-100' : 'opacity-30'}`} />
                Passwords match
              </div>
            </div>

            <Button
              type="submit"
              className="w-full bg-cyan-500 hover:bg-cyan-400 text-black font-heading font-bold uppercase tracking-wider py-6 rounded-sm shadow-[0_0_20px_rgba(6,182,212,0.3)] hover:shadow-[0_0_30px_rgba(6,182,212,0.5)] transition-all"
              disabled={loading || !hasMinLength || !passwordsMatch}
              data-testid="register-submit-btn"
            >
              {loading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                "Create Account"
              )}
            </Button>
          </form>

          {/* Login Link */}
          <p className="mt-6 text-center text-sm text-slate-500">
            Already have an account?{" "}
            <Link to="/login" className="text-cyan-400 hover:text-cyan-300 font-medium">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
