import React, { useRef, useLayoutEffect } from "react"
import { Shield, Lock, Activity, ArrowRight, Cloud, RefreshCw, Check } from "lucide-react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { gsap } from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"
import { MOCK_PLANS } from "@/mock-data"
import Shuffle from "@/components/Shuffle"

gsap.registerPlugin(ScrollTrigger)

const MockupStatCards = () => (
  <div className="flex flex-col gap-4">
    <div className="bg-[#1C1C1C] rounded-2xl p-5 border border-white/10 shadow-2xl w-56 flex flex-col">
       <div className="text-sm font-semibold text-neutral-400 mb-2">Total Certificates</div>
       <div className="text-4xl font-display font-bold text-white">612</div>
    </div>
    <div className="bg-[#1C1C1C] rounded-2xl p-5 border border-white/10 shadow-2xl w-56 flex flex-col">
       <div className="text-sm font-semibold text-brand-lime mb-2">Expiring Soon</div>
       <div className="text-4xl font-display font-bold text-white">89</div>
    </div>
  </div>
);

const MockupBubbleChart = () => (
  <div className="w-64 bg-[#1C1C1C] rounded-2xl border border-white/10 p-6 shadow-2xl relative overflow-hidden flex items-center justify-center h-56">
     <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-28 h-28 rounded-full bg-brand-lime/20 border border-brand-lime flex flex-col items-center justify-center font-bold text-2xl text-white shadow-lg">450<span className="text-[10px] text-brand-lime uppercase tracking-wider">AWS</span></div>
     <div className="absolute bottom-4 right-4 w-14 h-14 rounded-full bg-[#B497CF]/20 border border-[#B497CF] flex flex-col items-center justify-center font-bold text-sm text-white shadow-sm">80<span className="text-[8px] text-[#B497CF] uppercase tracking-wider">GCP</span></div>
     <div className="absolute top-6 left-6 w-16 h-16 rounded-full bg-white/10 border border-white/20 flex flex-col items-center justify-center font-bold text-sm text-white shadow-sm">120<span className="text-[8px] text-neutral-400 uppercase tracking-wider">Azure</span></div>
  </div>
);

const MockupActivityLog = () => {
  const logs = [
    { action: "Renewed Let's Encrypt Cert", target: "api.production.com", time: "2m ago" },
    { action: "Pushed to Secrets Manager", target: "us-east-1 /prod", time: "2m ago" },
    { action: "Detected expiring certificate", target: "auth.internal.net", time: "1h ago" },
  ];
  return (
    <div className="w-80 bg-[#1C1C1C] border border-white/10 rounded-2xl p-6 shadow-2xl flex flex-col gap-5">
       <div className="text-lg font-bold text-white tracking-tight">Recent Activity</div>
       <div className="flex flex-col gap-4">
       {logs.map((log, i) => (
         <div key={i} className="flex gap-4 items-start">
           <div className="w-0.5 h-full bg-white/10 rounded-full mt-2 relative">
              <div className="absolute top-0 left-1/2 -translate-x-1/2 w-2 h-2 bg-brand-lime rounded-full"></div>
           </div>
           <div className="flex-1">
             <div className="flex justify-between items-baseline mb-0.5">
               <div className="text-sm font-bold text-white leading-tight">{log.action}</div>
             </div>
             <div className="flex justify-between items-baseline mt-1">
                <div className="text-xs font-medium text-neutral-500">{log.target}</div>
                <div className="text-[10px] font-medium text-neutral-600">{log.time}</div>
             </div>
           </div>
         </div>
       ))}
       </div>
    </div>
  )
}

function Footer() {
  const [email, setEmail] = React.useState("");
  const [subscribed, setSubscribed] = React.useState(false);

  const handleSubscribe = (e: React.FormEvent) => {
    e.preventDefault();
    if (email) {
      setSubscribed(true);
      setEmail("");
      setTimeout(() => setSubscribed(false), 3000);
    }
  };

  return (
    <footer className="bg-[#0A0A0A] border-t border-white/10 pt-20 pb-10 relative z-10">
      <div className="container mx-auto px-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-12 mb-16">
          <div className="md:col-span-1">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-8 h-8 rounded-full bg-brand-lime flex items-center justify-center">
                <Shield className="w-5 h-5 text-[#0A0A0A]" />
              </div>
              <Shuffle 
                tag="span" 
                text="CertOps" 
                className="text-xl font-display font-bold text-white tracking-tight" 
                shuffleDirection="up"
                duration={0.35}
                shuffleTimes={3}
              />
            </div>
            <p className="text-neutral-400 text-sm mb-6">
              Modern certificate lifecycle management. Automate discovery, deployment, and renewal of your infrastructure certificates.
            </p>
            <div className="flex gap-4">
               <a href="https://twitter.com/certops" target="_blank" rel="noreferrer" className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center hover:bg-white/10 transition-colors cursor-pointer text-white font-bold">X</a>
               <a href="https://linkedin.com/company/certops" target="_blank" rel="noreferrer" className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center hover:bg-white/10 transition-colors cursor-pointer text-white font-bold">in</a>
            </div>
          </div>
          
          <div>
            <h4 className="text-white font-bold mb-6">Product</h4>
            <ul className="flex flex-col gap-3 text-sm text-neutral-400">
              <li><Link to="/dashboard" className="hover:text-brand-lime transition-colors">Dashboard</Link></li>
              <li><Link to="/certificates" className="hover:text-brand-lime transition-colors">Certificates</Link></li>
              <li><Link to="/connectors" className="hover:text-brand-lime transition-colors">Connectors</Link></li>
              <li><Link to="/enterprise/upgrade" className="hover:text-brand-lime transition-colors">Enterprise</Link></li>
            </ul>
          </div>
          
          <div>
            <h4 className="text-white font-bold mb-6">Company</h4>
            <ul className="flex flex-col gap-3 text-sm text-neutral-400">
              <li><Link to="/about" className="hover:text-brand-lime transition-colors">About Us</Link></li>
              <li><Link to="/careers" className="hover:text-brand-lime transition-colors">Careers</Link></li>
              <li><Link to="/pricing" className="hover:text-brand-lime transition-colors">Pricing</Link></li>
            </ul>
          </div>
          
          <div>
            <h4 className="text-white font-bold mb-6">Resources</h4>
            <ul className="flex flex-col gap-3 text-sm text-neutral-400 mb-6">
              <li><Link to="/help" className="hover:text-brand-lime transition-colors">Docs & Support</Link></li>
            </ul>
            <h4 className="text-white font-bold mb-4">Subscribe</h4>
            <form onSubmit={handleSubscribe} className="flex flex-col gap-2 relative">
              <div className="flex gap-2">
                <input 
                  type="email" 
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Email address" 
                  className="bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-sm text-white focus:outline-none focus:border-brand-lime w-full" 
                />
                <button type="submit" className="bg-brand-lime text-[#0A0A0A] font-bold px-4 py-2 rounded-lg hover:bg-brand-lime/90 transition-colors shrink-0">
                   <ArrowRight className="w-4 h-4" />
                </button>
              </div>
              {subscribed && (
                <div className="text-brand-lime text-xs font-bold absolute -bottom-6 left-0">Successfully subscribed!</div>
              )}
            </form>
          </div>
        </div>
        
        <div className="pt-8 border-t border-white/5 flex flex-col md:flex-row justify-between items-center gap-4 text-xs text-neutral-500">
          <p>© 2026 CertOps, Inc. All rights reserved.</p>
          <div className="flex gap-6">
            <Link to="/privacy" className="hover:text-white transition-colors">Privacy Policy</Link>
            <Link to="/terms" className="hover:text-white transition-colors">Terms of Service</Link>
          </div>
        </div>
      </div>
    </footer>
  )
}

const PricingSection = () => {
  return (
    <div id="pricing" className="container mx-auto px-6 py-32 relative z-10 bg-[#141414]">
      <div className="text-center mb-16">
        <h2 className="text-4xl md:text-5xl font-display font-bold tracking-tight mb-4 text-white">Simple, transparent pricing</h2>
        <p className="text-xl text-neutral-400 max-w-2xl mx-auto">
          Choose the plan that fits your infrastructure needs. Automate your certificates today.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-6xl mx-auto">
        {MOCK_PLANS.map((p) => {
          const isPopular = p.id === "Professional";

          return (
            <div key={p.id} className={`p-8 rounded-[32px] flex flex-col relative ${isPopular ? 'bg-white/10 border-2 border-brand-lime shadow-xl transform md:-translate-y-4' : 'bg-white/5 border border-white/10'}`}>
              {isPopular && (
                <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-brand-lime text-brand-dark text-xs font-bold px-4 py-1 rounded-full shadow-sm">
                  Most Popular
                </div>
              )}
              <h3 className="text-2xl font-bold mb-2 text-white">{p.name}</h3>
              <p className="text-sm text-neutral-400 mb-6 min-h-[40px]">{p.description}</p>
              
              <div className="mb-6">
                <span className="text-5xl font-display font-bold text-white">${p.annualPrice}</span>
                <span className="text-neutral-500 font-medium">/mo</span>
                <div className="text-xs text-brand-lime mt-1 font-medium">Billed annually</div>
              </div>
              
              <Link to="/pricing">
                <Button 
                  variant={isPopular ? "lime" : "outline"} 
                  className={`w-full rounded-full mb-8 font-bold text-md h-12 ${isPopular ? '' : 'bg-[#ababab] text-white border-0 hover:bg-[#ababab]/80 hover:text-white'}`}
                >
                  {p.id === "Enterprise" ? "Contact Sales" : "Get Started"}
                </Button>
              </Link>

              <div className="space-y-4 flex-1">
                <div className="text-sm font-bold mb-4 text-white">What's included:</div>
                {p.features.map((feat, i) => (
                  <div key={i} className="flex items-start gap-3">
                    <div className="w-5 h-5 rounded-full bg-brand-lime/20 text-brand-lime flex flex-shrink-0 items-center justify-center mt-0.5">
                      <Check className="w-3 h-3" />
                    </div>
                    <span className="text-sm font-medium text-neutral-300">{feat}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  )
}

function renderHDDFallback(ctx: CanvasRenderingContext2D, frame: number, width: number, height: number) {
    ctx.clearRect(0, 0, width, height);
    const progress = frame / 240;
    
    let explosion = 0;
    if (progress > 0.15 && progress <= 0.4) explosion = (progress - 0.15) / 0.25;
    else if (progress > 0.4 && progress <= 0.6) explosion = 1;
    else if (progress > 0.6 && progress <= 0.85) explosion = 1 - ((progress - 0.6) / 0.25);

    const easeOutQuad = (t: number) => t * (2 - t);
    explosion = easeOutQuad(explosion);

    const cx = width / 2;
    const cy = height / 2;

    ctx.save();
    ctx.translate(cx, cy);
    
    // Animate rotation during reassembly to land at a different angle
    let rotation = Math.PI / 6; // starting angle
    if (progress > 0.6) {
       // gently rotate to a new angle by the end
       const rotProgress = (progress - 0.6) / 0.4; 
       rotation = (Math.PI / 6) + rotProgress * (-Math.PI / 4);
    }
    
    ctx.rotate(rotation);
    ctx.scale(1, 0.6); // isometric squash

    // Colors matching the near-black + lime palette
    const bgBase = "#1A1A1A";
    const bgPcb = "#1a3314";
    const pcbAccent = "#D6F24C"; // lime
    const bgPlatter = "#E5E5E5";
    const bgCover = "#222222";

    // Shadow
    ctx.fillStyle = "rgba(0,0,0,0.5)";
    ctx.beginPath();
    ctx.rect(-150, -200 + 40, 300, 400);
    ctx.fill();

    // Base
    ctx.fillStyle = bgBase;
    ctx.strokeStyle = "#333";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.rect(-150, -200 + (explosion * 50), 300, 400);
    ctx.fill();
    ctx.stroke();

    // PCB
    ctx.fillStyle = bgPcb;
    ctx.strokeStyle = pcbAccent;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.rect(-130, -180 + (explosion * 250), 260, 150);
    ctx.fill();
    ctx.stroke();
    // PCB details
    ctx.fillStyle = "rgba(214, 242, 76, 0.2)";
    ctx.fillRect(-110, -160 + (explosion * 250), 40, 40);
    ctx.fillRect(-50, -160 + (explosion * 250), 80, 40);

    // Platters
    ctx.fillStyle = bgPlatter;
    ctx.strokeStyle = "#FFF";
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.arc(0, 0 - (explosion * 20), 120, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    
    // Spindle
    ctx.fillStyle = "#111";
    ctx.beginPath();
    ctx.arc(0, 0 - (explosion * 20), 30, 0, Math.PI * 2);
    ctx.fill();

    // Read/Write Arm
    ctx.fillStyle = "#888";
    ctx.shadowColor = "rgba(0,0,0,0.5)";
    ctx.shadowBlur = 15;
    ctx.beginPath();
    ctx.moveTo(100 + (explosion * 150), 100);
    ctx.lineTo(20 + (explosion * 150), -20);
    ctx.lineTo(40 + (explosion * 150), -30);
    ctx.lineTo(120 + (explosion * 150), 90);
    ctx.closePath();
    ctx.fill();
    ctx.shadowBlur = 0; // reset

    // Cover
    ctx.fillStyle = bgCover;
    ctx.strokeStyle = "#444";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.rect(-150 - (explosion * 180), -200 - (explosion * 220), 300, 400);
    ctx.arc(-150 - (explosion * 180) + 150, -200 - (explosion * 220) + 200, 100, 0, Math.PI * 2, true);
    ctx.fill("evenodd");
    ctx.stroke();

    ctx.restore();
    
}

export default function LandingPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useLayoutEffect(() => {
    const isReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const isTablet = window.innerWidth < 768; // For theoretical downsampled sequence handling

    const ctx = gsap.context(() => {
      if (isReduced) {
         gsap.set(".hdd-canvas", { display: "none" });
         gsap.set(".hero-outro-text", { opacity: 1, position: "relative", zIndex: 10, height: '100vh' });
         gsap.set(".hero-intro-text", { display: "none" });
         gsap.set(".mockup-1, .mockup-2, .mockup-3", { display: "none" });
         return;
      }

      const frameCount = 240;
      const currentFrame = { value: 0 };
      
      // Simulate Image Preloading - in a real app, this array would hold actual Image objects
      const images: HTMLImageElement[] = [];
      let imagesLoaded = false;
      // In production:
      // for(let i=0; i<frameCount; i++) {
      //   const img = new Image(); img.src = `/assets/hdd/frame_${i}.webp`; images.push(img);
      // }

      const renderCanvas = (frameIndex?: number) => {
         const canvas = canvasRef.current;
         if (!canvas) return;
         const context = canvas.getContext("2d");
         if (!context) return;
         const frame = frameIndex ?? Math.round(currentFrame.value);
         
         const img = images[frame];
         if (imagesLoaded && img && img.complete && img.naturalWidth > 0) {
            context.clearRect(0, 0, canvas.width, canvas.height);
            const scale = Math.min(canvas.width / img.width, canvas.height / img.height);
            const x = (canvas.width / 2) - (img.width / 2) * scale;
            const y = (canvas.height / 2) - (img.height / 2) * scale;
            context.drawImage(img, x, y, img.width * scale, img.height * scale);
         } else {
            renderHDDFallback(context, frame, canvas.width, canvas.height);
         }
      };

      const handleResize = () => {
         if (canvasRef.current) {
           canvasRef.current.width = window.innerWidth;
           canvasRef.current.height = window.innerHeight;
           renderCanvas();
         }
      };
      window.addEventListener('resize', handleResize);
      handleResize();

      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: ".hero-pin-container",
          start: "top top",
          end: "+=4000",
          scrub: 1, 
          pin: true,
          anticipatePin: 1
        }
      });

      // 1. Canvas frame scrubbing (duration 10 to map to 10s video source)
      tl.to(currentFrame, {
        value: frameCount - 1,
        ease: "none",
        onUpdate: () => renderCanvas(),
        duration: 10
      }, 0);

      // 2. Intro Text out (0 - 1s)
      tl.to(".hero-intro-text", { opacity: 0, y: -30, duration: 1, ease: "power2.inOut" }, 0);

      // 3. Disassembly (1.5s - 4s). Mockups fade into negative space as parts clear.
      // Cover clear (~1.5s) -> Mockup 1
      tl.fromTo(".mockup-1", { opacity: 0, scale: 0.95 }, { opacity: 1, scale: 1, duration: 1, ease: "power2.out" }, 1.5);
      // Arm clear (~2.5s) -> Mockup 2
      tl.fromTo(".mockup-2", { opacity: 0, scale: 0.95 }, { opacity: 1, scale: 1, duration: 1, ease: "power2.out" }, 2.5);
      // PCB clear (~3s) -> Mockup 3
      tl.fromTo(".mockup-3", { opacity: 0, scale: 0.95 }, { opacity: 1, scale: 1, duration: 1, ease: "power2.out" }, 3.0);

      // 4. Dwell Time (4s - 6s). Peak explosion, mockups fully visible.

      // 5. Reassembly (6s - 8.5s). Mockups fade out as parts return.
      tl.to(".mockup-3", { opacity: 0, scale: 0.95, duration: 0.8, ease: "power2.in" }, 6.0);
      tl.to(".mockup-2", { opacity: 0, scale: 0.95, duration: 0.8, ease: "power2.in" }, 6.5);
      tl.to(".mockup-1", { opacity: 0, scale: 0.95, duration: 0.8, ease: "power2.in" }, 7.0);

      // 6. Final State / Outro text in (8.5s - 10s)
      tl.fromTo(".hero-outro-text", { opacity: 0, x: -30 }, { opacity: 1, x: 0, duration: 1.5, ease: "power3.out" }, 8.5);

      return () => {
         window.removeEventListener('resize', handleResize);
      };

    }, containerRef); 

    return () => ctx.revert(); 
  }, []);

  return (
    <div ref={containerRef} className="min-h-screen bg-[#141414] text-white font-sans selection:bg-brand-lime selection:text-[#141414]">
      
      {/* Navbar - Absolute positioning to hover over pinned section */}
      <nav className="absolute top-0 left-0 right-0 z-50 container mx-auto px-6 py-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-brand-lime flex items-center justify-center">
            <Shield className="w-6 h-6 text-brand-dark" />
          </div>
          <span className="text-2xl font-display font-bold tracking-tight">CertOps</span>
        </div>
        <div className="hidden md:flex items-center gap-8 text-sm font-medium text-neutral-300">
          <Link to="/about" className="hover:text-white transition-colors">About Us</Link>
          <a href="#features" className="hover:text-white transition-colors">Catalog</a>
          <Link to="/pricing" className="hover:text-white transition-colors">Price</Link>
          <Link to="/help" className="hover:text-white transition-colors">Help</Link>
        </div>
        <Link to="/login">
          <Button variant="lime" className="font-semibold px-6">
            Log In <ArrowRight className="ml-2 w-4 h-4" />
          </Button>
        </Link>
      </nav>

      {/* Hero Pin Container */}
      <div className="hero-pin-container h-screen w-full relative flex items-center justify-center overflow-hidden bg-[#141414]">
         <canvas ref={canvasRef} className="hdd-canvas absolute inset-0 w-full h-full object-cover z-10" />
         {/* Diegetic asset-pipeline label — survives webP swap since it's DOM, not canvas-baked */}
         <div className="hdd-canvas absolute top-20 left-6 z-30 text-white/30 text-xs font-mono pointer-events-none select-none" aria-hidden="true">Simulating webP Sequence...</div>

         <div className="hero-intro-text absolute inset-0 flex flex-col items-center justify-center z-20 pointer-events-none px-6 text-center">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 border border-white/20 text-brand-lime text-sm font-medium mb-8">
              <span className="w-2 h-2 rounded-full bg-brand-lime animate-pulse"></span>
              CertOps CLM 2.0 is now live
            </div>
            <h1 className="text-5xl md:text-7xl font-display font-bold tracking-tight mb-6 text-white leading-[1.1]">
              Modern Certificate<br/>Lifecycle Management.
            </h1>
            <p className="text-xl text-neutral-400 max-w-2xl mx-auto">
              Automate discovery, deployment, and renewal of your infrastructure certificates. Stop tracking expirations in spreadsheets.
            </p>
         </div>

         {/* Floating Mockup Overlays */}
         <div className="absolute inset-0 z-20 pointer-events-none max-w-7xl mx-auto w-full">
            {/* Upper Left - Cover zone */}
            <div className="mockup-1 absolute top-[15%] left-[5%] md:left-[10%]">
               <MockupStatCards />
            </div>

            {/* Right - Arm zone */}
            <div className="mockup-2 absolute top-[40%] right-[5%] md:right-[10%]">
               <MockupBubbleChart />
            </div>

            {/* Lower Area - PCB zone */}
            <div className="mockup-3 absolute bottom-[15%] left-[50%] -translate-x-1/2 md:translate-x-0 md:left-[35%]">
               <MockupActivityLog />
            </div>
         </div>

         <div className="hero-outro-text absolute inset-0 flex flex-col items-start justify-center z-20 pointer-events-auto px-12 md:px-32 opacity-0">
            <h2 className="text-5xl font-display font-bold tracking-tight mb-8 text-white max-w-xl leading-[1.1]">
              Ready to automate your infrastructure?
            </h2>
            <Link to="/dashboard">
              <Button variant="lime" size="lg" className="text-lg h-14 px-8 font-bold text-brand-dark">
                Access Dashboard <ArrowRight className="ml-2 w-5 h-5" />
              </Button>
            </Link>
         </div>
      </div>

      {/* Feature Grid (Bento Cascade) */}
      <div id="features" className="bento-grid container mx-auto px-6 py-40 relative z-10 bg-[#141414]">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-left max-w-6xl mx-auto">
          {/* Large Card */}
          <div className="bento-card md:col-span-2 p-10 rounded-[32px] bg-white/5 border border-white/10 relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-brand-lime/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
            <Activity className="w-12 h-12 text-brand-lime mb-8 relative z-10" />
            <h3 className="text-2xl font-display font-bold mb-4 relative z-10">Automated Renewals</h3>
            <p className="text-neutral-400 text-lg leading-relaxed max-w-md relative z-10">
              Direct integration with Let's Encrypt, DigiCert, and internal PKI to renew certificates before they expire, ensuring zero downtime.
            </p>
          </div>
          
          {/* Square Card 1 */}
          <div className="bento-card p-10 rounded-[32px] bg-white/5 border border-white/10 relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-brand-purple/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
            <Lock className="w-12 h-12 text-brand-purple mb-8 relative z-10" />
            <h3 className="text-2xl font-display font-bold mb-4 relative z-10">Secret Store Sync</h3>
            <p className="text-neutral-400 leading-relaxed relative z-10">
              Push renewed certificates directly to AWS Secrets Manager & Vault.
            </p>
          </div>

          {/* Square Card 2 */}
          <div className="bento-card p-10 rounded-[32px] bg-white/5 border border-white/10 relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-brand-lime/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
            <Shield className="w-12 h-12 text-brand-lime mb-8 relative z-10" />
            <h3 className="text-2xl font-display font-bold mb-4 relative z-10">Policy Engine</h3>
            <p className="text-neutral-400 leading-relaxed relative z-10">
              Define maintenance windows and failure alerts per environment.
            </p>
          </div>

          {/* Wide Card */}
          <div className="bento-card md:col-span-2 p-10 rounded-[32px] bg-white/5 border border-white/10 relative overflow-hidden flex flex-col justify-center group">
            <div className="absolute inset-0 bg-gradient-to-tr from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
            <div className="flex flex-col md:flex-row gap-8 items-center relative z-10">
              <div className="flex-1">
                <Cloud className="w-12 h-12 text-white mb-6" />
                <h3 className="text-2xl font-display font-bold mb-4">Multi-Cloud Discovery</h3>
                <p className="text-neutral-400 leading-relaxed">
                  Continuously scan AWS, GCP, and Azure for unmanaged certificates and bring them into compliance automatically.
                </p>
              </div>
              <div className="w-full md:w-1/3 flex flex-col gap-3">
                 <div className="bg-brand-dark p-4 rounded-xl border border-white/10 flex items-center justify-between">
                   <span className="font-bold">AWS Scanned</span>
                   <span className="text-brand-lime">100%</span>
                 </div>
                 <div className="bg-brand-dark p-4 rounded-xl border border-white/10 flex items-center justify-between">
                   <span className="font-bold">GCP Scanned</span>
                   <span className="text-brand-lime">100%</span>
                 </div>
              </div>
            </div>
          </div>
          
          {/* Action Card */}
          <div className="bento-card md:col-span-3 p-10 md:p-16 rounded-[32px] bg-brand-lime text-brand-dark relative overflow-hidden flex flex-col md:flex-row items-center justify-between group">
             <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/noise-pattern-with-subtle-cross-lines.png')] opacity-20"></div>
             <div className="relative z-10 flex flex-col items-start w-full md:w-1/2">
               <div className="w-16 h-16 rounded-2xl bg-[#0A0A0A]/10 flex items-center justify-center mb-6">
                 <RefreshCw className="w-8 h-8" />
               </div>
               <h3 className="text-4xl md:text-5xl font-display font-bold mb-4 tracking-tight">Ready to automate?</h3>
               <p className="text-brand-dark/80 text-lg font-medium mb-8 max-w-md">
                 Join top engineering teams managing millions of certificates with CertOps CLM 2.0.
               </p>
               <Link to="/dashboard">
                 <button className="bg-brand-dark text-white font-bold text-lg h-14 px-8 rounded-full hover:bg-black transition-colors flex items-center gap-2 hover:scale-105 duration-300">
                   Get Started <ArrowRight className="w-5 h-5" />
                 </button>
               </Link>
             </div>
             
             <div className="relative z-10 w-full md:w-1/2 h-64 md:h-auto mt-10 md:mt-0 flex items-center justify-center md:justify-end">
               {/* Decorative Graphic */}
               <div className="absolute top-1/2 md:right-10 left-1/2 md:left-auto -translate-x-1/2 md:translate-x-0 -translate-y-1/2 w-[280px] h-[280px] md:w-[360px] md:h-[360px] border-[40px] border-[#0A0A0A]/5 rounded-full animate-[spin_10s_linear_infinite]"></div>
               <div className="absolute top-1/2 md:right-10 left-1/2 md:left-auto -translate-x-1/2 md:translate-x-0 -translate-y-1/2 w-[280px] h-[280px] md:w-[360px] md:h-[360px] border-b-[40px] border-l-[40px] border-[#0A0A0A]/10 rounded-full animate-[spin_4s_linear_infinite_reverse]"></div>
               
               {/* Floating elements */}
               <div className="absolute top-4 right-4 md:top-8 md:right-8 bg-white text-black text-xs font-bold px-3 py-1.5 rounded-full shadow-lg transform rotate-12 animate-bounce flex items-center gap-1 z-20">
                 <Shield className="w-3 h-3 text-green-600" /> Secure
               </div>
               <div className="absolute bottom-8 left-4 md:bottom-12 md:left-12 bg-[#0A0A0A] text-brand-lime text-xs font-bold px-3 py-1.5 rounded-full shadow-lg transform -rotate-12 animate-pulse flex items-center gap-1 z-20 border border-brand-lime/30">
                 <Lock className="w-3 h-3" /> Encrypted
               </div>

               <div className="relative bg-[#0A0A0A] text-brand-lime font-mono text-sm md:text-base p-6 md:p-8 rounded-2xl shadow-2xl md:mr-16 rotate-[-5deg] group-hover:rotate-[2deg] transition-transform duration-700 ease-out z-10">
                 <div className="flex items-center gap-2 mb-4 border-b border-white/10 pb-2">
                   <div className="w-3 h-3 rounded-full bg-red-500"></div>
                   <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
                   <div className="w-3 h-3 rounded-full bg-green-500"></div>
                 </div>
                 <div><span className="text-white opacity-50">$</span> certops init --auto</div>
                 <div className="opacity-70 mt-2 flex items-center gap-2">
                   <span className="w-2 h-2 rounded-full bg-brand-lime animate-pulse"></span>
                   Initializing CLM 2.0...
                 </div>
                 <div className="opacity-70 mt-1">Scanning infrastructure...</div>
                 <div className="text-white font-bold mt-3">✓ 1,492 certs found</div>
                 <div className="text-white font-bold mt-1">✓ Zero-trust policy applied</div>
                 <div className="text-brand-lime font-bold mt-3 animate-pulse">_</div>
               </div>
             </div>
          </div>
        </div>
      </div>

      <PricingSection />
      <Footer />
    </div>
  )
}

