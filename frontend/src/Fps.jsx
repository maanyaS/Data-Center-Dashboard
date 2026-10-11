import { useEffect, useState } from "react";

// Small frames-per-second readout (updates twice a second)
export default function Fps() {
  const [fps, setFps] = useState(0);
  useEffect(() => {
    let frames = 0, last = performance.now(), id;
    const tick = (now) => {
      frames++;
      if (now - last >= 500) {
        setFps(Math.round((frames * 1000) / (now - last)));
        frames = 0;
        last = now;
      }
      id = requestAnimationFrame(tick);
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, []);
  const color = fps >= 50 ? "text-emerald-600" : fps >= 30 ? "text-amber-600" : "text-red-600";
  return <span className={`font-mono ${color}`}>{fps} FPS</span>;
}
