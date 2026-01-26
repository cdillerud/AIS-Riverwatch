import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { 
  Anchor, Clock, Navigation, Shield, Zap, ChevronRight, 
  Radio, BarChart3, Users
} from "lucide-react";

export default function LandingPage() {
  const navigate = useNavigate();
  const [imageLoaded, setImageLoaded] = useState(false);

  return (
    <div className="min-h-screen bg-slate-950 text-white font-sans overflow-x-hidden">
      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center justify-center">
        {/* Background Image with Overlay */}
        <div className="absolute inset-0 z-0">
          <img 
            src="https://images.unsplash.com/photo-1609359972809-fa361cf5b1d0?w=1920&q=80"
            alt="River with commercial vessels"
            className={`w-full h-full object-cover transition-opacity duration-1000 ${imageLoaded ? 'opacity-30' : 'opacity-0'}`}
            onLoad={() => setImageLoaded(true)}
          />
          <div className="absolute inset-0 bg-gradient-to-b from-slate-950/80 via-slate-950/60 to-slate-950" />
        </div>

        {/* Hero Content */}
        <div className="relative z-10 container mx-auto px-6 py-20 text-center">
          {/* Logo/Brand */}
          <div className="flex items-center justify-center gap-3 mb-8">
            <div className="relative">
              <Radio className="w-10 h-10 text-cyan-400" />
              <div className="absolute inset-0 animate-ping opacity-20">
                <Radio className="w-10 h-10 text-cyan-400" />
              </div>
            </div>
            <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-wider uppercase text-white">
              River Watch
            </h1>
          </div>

          {/* Main Headline */}
          <h2 className="font-heading text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-bold uppercase tracking-tight mb-6 leading-none">
            <span className="text-white">Beat the Traffic.</span>
            <br />
            <span className="text-cyan-400">Master the River.</span>
          </h2>

          {/* Subheadline */}
          <p className="text-lg md:text-xl text-slate-300 max-w-2xl mx-auto mb-10 leading-relaxed">
            Real-time lock timing for Upper Mississippi River boaters. 
            Know exactly when to depart to beat commercial tows to the next lock.
          </p>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <Button
              onClick={() => navigate("/register")}
              className="bg-cyan-500 hover:bg-cyan-400 text-black font-heading font-bold uppercase tracking-wider text-lg px-8 py-6 rounded-sm shadow-[0_0_30px_rgba(6,182,212,0.4)] hover:shadow-[0_0_40px_rgba(6,182,212,0.6)] transition-all"
              data-testid="get-started-btn"
            >
              Get Started Free
              <ChevronRight className="w-5 h-5 ml-2" />
            </Button>
            <Button
              onClick={() => navigate("/login")}
              variant="outline"
              className="border-slate-600 text-slate-300 hover:bg-slate-800 font-heading uppercase tracking-wider text-lg px-8 py-6 rounded-sm"
              data-testid="sign-in-btn"
            >
              Sign In
            </Button>
          </div>

          {/* Trust Indicators */}
          <div className="mt-16 flex flex-wrap justify-center gap-8 text-sm text-slate-500">
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-cyan-500" />
              <span>Free to Use</span>
            </div>
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-cyan-500" />
              <span>Real-time AIS Data</span>
            </div>
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4 text-cyan-500" />
              <span>Multi-vessel Support</span>
            </div>
          </div>
        </div>

        {/* Scroll Indicator */}
        <div className="absolute bottom-8 left-1/2 -translate-x-1/2 animate-bounce">
          <div className="w-6 h-10 border-2 border-slate-600 rounded-full flex items-start justify-center p-2">
            <div className="w-1.5 h-3 bg-cyan-400 rounded-full animate-pulse" />
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-24 bg-slate-950">
        <div className="container mx-auto px-6">
          {/* Section Header */}
          <div className="text-center mb-16">
            <p className="font-heading text-sm uppercase tracking-widest text-cyan-400 mb-4">
              Why River Watch
            </p>
            <h3 className="font-heading text-3xl md:text-4xl font-bold uppercase tracking-wide text-white">
              Navigate Smarter
            </h3>
          </div>

          {/* Feature Grid */}
          <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
            {/* Feature 1 */}
            <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-6 hover:border-cyan-500/30 transition-colors">
              <div className="w-12 h-12 bg-cyan-500/10 rounded-lg flex items-center justify-center mb-4">
                <Clock className="w-6 h-6 text-cyan-400" />
              </div>
              <h4 className="font-heading text-xl font-semibold uppercase tracking-wide text-white mb-3">
                Lock Timing
              </h4>
              <p className="text-slate-400 leading-relaxed">
                Know the exact speed needed to beat commercial traffic to the next lock. 
                Avoid hours of waiting behind tows.
              </p>
            </div>

            {/* Feature 2 */}
            <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-6 hover:border-cyan-500/30 transition-colors">
              <div className="w-12 h-12 bg-cyan-500/10 rounded-lg flex items-center justify-center mb-4">
                <Navigation className="w-6 h-6 text-cyan-400" />
              </div>
              <h4 className="font-heading text-xl font-semibold uppercase tracking-wide text-white mb-3">
                Live Tracking
              </h4>
              <p className="text-slate-400 leading-relaxed">
                See all vessels on a simplified river map. Track commercial tows, 
                their barge counts, and estimated lockage times.
              </p>
            </div>

            {/* Feature 3 */}
            <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-6 hover:border-cyan-500/30 transition-colors">
              <div className="w-12 h-12 bg-cyan-500/10 rounded-lg flex items-center justify-center mb-4">
                <BarChart3 className="w-6 h-6 text-cyan-400" />
              </div>
              <h4 className="font-heading text-xl font-semibold uppercase tracking-wide text-white mb-3">
                USACE Data
              </h4>
              <p className="text-slate-400 leading-relaxed">
                Real lock status, queue information, and wait time predictions 
                powered by Army Corps of Engineers data.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* How It Works Section */}
      <section className="py-24 bg-slate-900/50">
        <div className="container mx-auto px-6">
          <div className="text-center mb-16">
            <p className="font-heading text-sm uppercase tracking-widest text-cyan-400 mb-4">
              Simple Setup
            </p>
            <h3 className="font-heading text-3xl md:text-4xl font-bold uppercase tracking-wide text-white">
              How It Works
            </h3>
          </div>

          <div className="grid md:grid-cols-3 gap-12 max-w-4xl mx-auto">
            {/* Step 1 */}
            <div className="text-center">
              <div className="w-16 h-16 bg-cyan-500 text-black font-heading font-bold text-2xl rounded-sm flex items-center justify-center mx-auto mb-4 shadow-[0_0_20px_rgba(6,182,212,0.3)]">
                1
              </div>
              <h4 className="font-heading text-lg font-semibold uppercase tracking-wide text-white mb-2">
                Connect
              </h4>
              <p className="text-slate-400 text-sm">
                Link your Boat Beacon app or AIS receiver to River Watch
              </p>
            </div>

            {/* Step 2 */}
            <div className="text-center">
              <div className="w-16 h-16 bg-cyan-500 text-black font-heading font-bold text-2xl rounded-sm flex items-center justify-center mx-auto mb-4 shadow-[0_0_20px_rgba(6,182,212,0.3)]">
                2
              </div>
              <h4 className="font-heading text-lg font-semibold uppercase tracking-wide text-white mb-2">
                Select Lock
              </h4>
              <p className="text-slate-400 text-sm">
                Choose your target lock and see who's ahead of you
              </p>
            </div>

            {/* Step 3 */}
            <div className="text-center">
              <div className="w-16 h-16 bg-cyan-500 text-black font-heading font-bold text-2xl rounded-sm flex items-center justify-center mx-auto mb-4 shadow-[0_0_20px_rgba(6,182,212,0.3)]">
                3
              </div>
              <h4 className="font-heading text-lg font-semibold uppercase tracking-wide text-white mb-2">
                Beat Traffic
              </h4>
              <p className="text-slate-400 text-sm">
                Follow the recommended speed to arrive before commercial vessels
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-24 bg-slate-950">
        <div className="container mx-auto px-6 text-center">
          <h3 className="font-heading text-3xl md:text-4xl font-bold uppercase tracking-wide text-white mb-6">
            Ready to Save Hours at the Locks?
          </h3>
          <p className="text-slate-400 max-w-xl mx-auto mb-8">
            Join recreational boaters who use River Watch to plan smarter trips 
            on the Upper Mississippi.
          </p>
          <Button
            onClick={() => navigate("/register")}
            className="bg-cyan-500 hover:bg-cyan-400 text-black font-heading font-bold uppercase tracking-wider text-lg px-10 py-6 rounded-sm shadow-[0_0_30px_rgba(6,182,212,0.4)] hover:shadow-[0_0_40px_rgba(6,182,212,0.6)] transition-all"
            data-testid="cta-get-started-btn"
          >
            Start Free Now
            <ChevronRight className="w-5 h-5 ml-2" />
          </Button>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 border-t border-slate-800">
        <div className="container mx-auto px-6">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <Radio className="w-5 h-5 text-cyan-400" />
              <span className="font-heading text-sm uppercase tracking-wider text-slate-500">
                River Watch
              </span>
            </div>
            <p className="text-xs text-slate-600">
              Not affiliated with USACE. For recreational use only.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
