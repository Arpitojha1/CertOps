import { useRef, useEffect } from "react";
import * as THREE from "three";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

/**
 * 3D vault safe built in Three.js — matches the reference image geometry:
 * rounded-cube body, recessed door panel, circular dial with handle,
 * two hinge pegs, four feet.
 *
 * Colors: neutral body (dark graphite), single indigo accent on dial/handle only.
 * Scroll-driven: subtle Y-axis rotation tied to scroll progress through the hero.
 *
 * ponytail: Using procedural geometry instead of a .glb model — no asset pipeline
 * needed, total control over colors, and keeps the bundle lean. If the vault
 * design needs to get much more detailed (rivets, textures, normal maps), switch
 * to a Blender-exported glTF.
 */

// oklch(0.51 0.19 274.74) ≈ #4338ca — CertOps primary indigo
const INDIGO = 0x4338ca;
// Neutral body: dark graphite that reads well on light background
const BODY_COLOR = 0x3a3a44;
// Door panel: slightly lighter neutral
const DOOR_COLOR = 0x4a4a54;
// Feet/hinges: very dark
const DARK_ACCENT = 0x1a1a22;

interface Vault3DProps {
  className?: string;
  style?: React.CSSProperties;
}

function createRoundedBox(
  width: number,
  height: number,
  depth: number,
  radius: number,
  segments: number
): THREE.BufferGeometry {
  // ponytail: Three.js doesn't ship RoundedBoxGeometry in core.
  // Using a BoxGeometry and modifying vertices for rounded edges is complex.
  // Instead, use ExtrudeGeometry with a RoundedRectangle shape for the front/back
  // and a simple box approach. For visual fidelity at this scale, a slightly
  // smoothed box via subdivision is sufficient.
  //
  // Simpler approach: use a box with bevel via ExtrudeGeometry.
  const shape = new THREE.Shape();
  const w = width / 2 - radius;
  const h = height / 2 - radius;

  shape.moveTo(-w, -height / 2);
  shape.lineTo(w, -height / 2);
  shape.quadraticCurveTo(width / 2, -height / 2, width / 2, -h);
  shape.lineTo(width / 2, h);
  shape.quadraticCurveTo(width / 2, height / 2, w, height / 2);
  shape.lineTo(-w, height / 2);
  shape.quadraticCurveTo(-width / 2, height / 2, -width / 2, h);
  shape.lineTo(-width / 2, -h);
  shape.quadraticCurveTo(-width / 2, -height / 2, -w, -height / 2);

  const extrudeSettings: THREE.ExtrudeGeometryOptions = {
    depth: depth,
    bevelEnabled: true,
    bevelThickness: radius * 0.3,
    bevelSize: radius * 0.3,
    bevelSegments: segments,
    curveSegments: segments,
  };

  const geo = new THREE.ExtrudeGeometry(shape, extrudeSettings);
  // Center the depth
  geo.translate(0, 0, -depth / 2);
  return geo;
}

export default function Vault3D({ className, style }: Vault3DProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const vaultGroupRef = useRef<THREE.Group | null>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const width = container.clientWidth;
    const height = container.clientHeight;

    // Scene
    const scene = new THREE.Scene();
    scene.background = null; // Transparent — page background shows through
    sceneRef.current = scene;

    // Camera
    const camera = new THREE.PerspectiveCamera(35, width / height, 0.1, 100);
    camera.position.set(0, 0.3, 5.5);
    camera.lookAt(0, 0, 0);
    cameraRef.current = camera;

    // Renderer
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const keyLight = new THREE.DirectionalLight(0xffffff, 1.0);
    keyLight.position.set(3, 4, 5);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0xdde4f0, 0.4);
    fillLight.position.set(-3, 1, 3);
    scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight(0xc8d4ff, 0.3);
    rimLight.position.set(0, -2, -3);
    scene.add(rimLight);

    // Materials
    const bodyMat = new THREE.MeshStandardMaterial({
      color: BODY_COLOR,
      roughness: 0.65,
      metalness: 0.15,
    });

    const doorMat = new THREE.MeshStandardMaterial({
      color: DOOR_COLOR,
      roughness: 0.5,
      metalness: 0.2,
    });

    const indigoMat = new THREE.MeshStandardMaterial({
      color: INDIGO,
      roughness: 0.3,
      metalness: 0.4,
      emissive: INDIGO,
      emissiveIntensity: 0.1,
    });

    const darkMat = new THREE.MeshStandardMaterial({
      color: DARK_ACCENT,
      roughness: 0.8,
      metalness: 0.1,
    });

    // Vault group
    const vaultGroup = new THREE.Group();
    vaultGroupRef.current = vaultGroup;

    // === Body: rounded cube ===
    const bodyGeo = createRoundedBox(2.0, 2.0, 1.8, 0.2, 4);
    const body = new THREE.Mesh(bodyGeo, bodyMat);
    vaultGroup.add(body);

    // === Recessed door panel (front face) ===
    const doorGeo = createRoundedBox(1.6, 1.6, 0.08, 0.12, 3);
    const door = new THREE.Mesh(doorGeo, doorMat);
    door.position.z = 0.92;
    vaultGroup.add(door);

    // === Circular dial ===
    const dialOuterGeo = new THREE.CylinderGeometry(0.38, 0.38, 0.08, 32);
    const dialOuter = new THREE.Mesh(dialOuterGeo, indigoMat);
    dialOuter.rotation.x = Math.PI / 2;
    dialOuter.position.set(0, 0, 1.02);
    vaultGroup.add(dialOuter);

    // Inner dial ring
    const dialInnerGeo = new THREE.CylinderGeometry(0.28, 0.28, 0.1, 32);
    const dialInner = new THREE.Mesh(dialInnerGeo, indigoMat);
    dialInner.rotation.x = Math.PI / 2;
    dialInner.position.set(0, 0, 1.04);
    vaultGroup.add(dialInner);

    // Dial center nub
    const dialCenterGeo = new THREE.CylinderGeometry(0.1, 0.1, 0.12, 16);
    const dialCenter = new THREE.Mesh(dialCenterGeo, indigoMat);
    dialCenter.rotation.x = Math.PI / 2;
    dialCenter.position.set(0, 0, 1.06);
    vaultGroup.add(dialCenter);

    // === Protruding handle ===
    const handleGeo = new THREE.CylinderGeometry(0.05, 0.05, 0.5, 8);
    const handle = new THREE.Mesh(handleGeo, indigoMat);
    handle.rotation.z = Math.PI / 2;
    handle.position.set(0.3, 0, 1.06);
    vaultGroup.add(handle);

    // Handle knob
    const knobGeo = new THREE.SphereGeometry(0.075, 12, 12);
    const knob = new THREE.Mesh(knobGeo, indigoMat);
    knob.position.set(0.55, 0, 1.06);
    vaultGroup.add(knob);

    // === Two hinge pegs (right side) ===
    const hingePegGeo = new THREE.CylinderGeometry(0.06, 0.06, 0.15, 8);
    for (const yPos of [0.55, -0.55]) {
      const peg = new THREE.Mesh(hingePegGeo, darkMat);
      peg.rotation.x = Math.PI / 2;
      peg.position.set(1.02, yPos, 0.3);
      vaultGroup.add(peg);
    }

    // === Four feet ===
    const footGeo = new THREE.CylinderGeometry(0.12, 0.1, 0.15, 12);
    const footPositions = [
      [-0.7, -1.1, -0.6],
      [0.7, -1.1, -0.6],
      [-0.7, -1.1, 0.6],
      [0.7, -1.1, 0.6],
    ];
    for (const [fx, fy, fz] of footPositions) {
      const foot = new THREE.Mesh(footGeo, darkMat);
      foot.position.set(fx, fy, fz);
      vaultGroup.add(foot);
    }

    // === Three decorative bolt dots on door (like reference) ===
    const boltGeo = new THREE.CylinderGeometry(0.04, 0.04, 0.06, 8);
    const boltPositions = [
      [-0.45, 0.35],
      [-0.45, 0],
      [-0.45, -0.35],
    ];
    for (const [bx, by] of boltPositions) {
      const bolt = new THREE.Mesh(boltGeo, bodyMat);
      bolt.rotation.x = Math.PI / 2;
      bolt.position.set(bx, by, 0.98);
      vaultGroup.add(bolt);
    }

    // Position vault slightly right and down for visual balance in hero layout
    vaultGroup.position.set(0, -0.1, 0);
    vaultGroup.rotation.y = -0.15; // Slight initial rotation
    scene.add(vaultGroup);

    // === Scroll-driven rotation ===
    const scrollState = { rotationY: -0.15 };

    const heroSection = container.closest(".lp-hero");
    if (heroSection) {
      gsap.to(scrollState, {
        rotationY: 0.4,
        ease: "none",
        scrollTrigger: {
          trigger: heroSection,
          start: "top top",
          end: "bottom top",
          scrub: 1.5,
          onUpdate: () => {
            if (vaultGroupRef.current) {
              vaultGroupRef.current.rotation.y = scrollState.rotationY;
            }
          },
        },
      });
    }

    // === Render loop ===
    function animate() {
      renderer.render(scene, camera);
      rafRef.current = requestAnimationFrame(animate);
    }
    rafRef.current = requestAnimationFrame(animate);

    // === Resize handling ===
    function onResize() {
      const w = container!.clientWidth;
      const h = container!.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    }
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(rafRef.current);
      window.removeEventListener("resize", onResize);
      renderer.dispose();
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          obj.geometry.dispose();
          if (Array.isArray(obj.material)) {
            obj.material.forEach((m) => m.dispose());
          } else {
            obj.material.dispose();
          }
        }
      });
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{
        width: "100%",
        height: "100%",
        ...style,
      }}
    />
  );
}
