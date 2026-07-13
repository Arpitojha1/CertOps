import { useRef, useEffect } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Zap, Lock, Shield, BarChart3, type LucideIcon } from "lucide-react";
import "./ScrollStack.css";

gsap.registerPlugin(ScrollTrigger);

interface Feature {
  Icon: LucideIcon;
  title: string;
  body: string;
}

const FEATURES: Feature[] = [
  {
    Icon: Zap,
    title: "Automated Discovery",
    body: "Scan vaults and hosts to find all certificates. No manual inventory, no guessing.",
  },
  {
    Icon: Lock,
    title: "Policy-Driven Renewal",
    body: "Set renewal thresholds per group. Certificates renew automatically before expiry.",
  },
  {
    Icon: Shield,
    title: "Host Reload Confirmation",
    body: "Explicit approval before restarting services. You control when production changes.",
  },
  {
    Icon: BarChart3,
    title: "Audit Trail",
    body: "Full log of renewals, deployments, and reloads. Compliance-ready from day one.",
  },
];

function useReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export default function ScrollStack() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    if (reducedMotion || !wrapRef.current) return;

    const ctx = gsap.context(() => {
      const cards = gsap.utils.toArray<HTMLElement>(
        ".ss-card",
        wrapRef.current
      );

      cards.forEach((card, i) => {
        if (i === cards.length - 1) return;

        // Pin each card at the top of the viewport
        ScrollTrigger.create({
          trigger: card,
          start: "top top",
          endTrigger: cards[cards.length - 1],
          end: "top top",
          pin: true,
          pinSpacing: false,
        });

        // Scale/fade outgoing card as next card arrives
        gsap.to(card, {
          scale: 0.92,
          opacity: 0.5,
          ease: "none",
          scrollTrigger: {
            trigger: cards[i + 1],
            start: "top bottom",
            end: "top top",
            scrub: true,
          },
        });
      });
    }, wrapRef);

    return () => ctx.revert();
  }, [reducedMotion]);

  if (reducedMotion) {
    return (
      <section className="ss-static">
        <h2 className="ss-static-heading">Built for infrastructure teams</h2>
        <div className="ss-static-grid">
          {FEATURES.map(({ Icon, title, body }) => (
            <div key={title} className="ss-static-card">
              <Icon size={28} className="text-primary" strokeWidth={1.5} />
              <h3>{title}</h3>
              <p>{body}</p>
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <div ref={wrapRef} className="ss-wrap">
      {FEATURES.map(({ Icon, title, body }, i) => (
        <div
          key={title}
          className="ss-card"
          style={{ zIndex: i + 1 }}
        >
          <div className="ss-card-inner">
            <div className="ss-card-progress">
              {FEATURES.map((_, fi) => (
                <span
                  key={fi}
                  className={fi <= i ? "ss-progress-active" : "ss-progress-inactive"}
                />
              ))}
            </div>
            <div className="ss-icon">
              <Icon size={44} strokeWidth={1.25} />
            </div>
            <h3 className="ss-card-title">{title}</h3>
            <p className="ss-card-body">{body}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
