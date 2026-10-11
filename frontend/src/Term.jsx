import { useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

// Plain-language explanations for jargon and labels, shown on hover / keyboard focus.
export const GLOSSARY = {
  "high review risk": "At least one likely permit review here is known for long delays (often months). Not a prediction of the permit decision.",
  "moderate review risk": "Likely permit reviews here can add some time, but none is flagged as a long-delay review.",
  "low review risk": "No permit reviews were flagged from the map layers checked. Things the tool can't see (zoning, local rules) still apply.",
  "high delay": "Reviews of this kind often take many months and can change or stop a project.",
  "medium delay": "Reviews of this kind usually add weeks to a few months.",
  "low delay": "Usually a routine step that adds little time.",
  likely_reviews: "Permit or environmental reviews a project here would probably need, based on what's on or near the land.",
  MW: "Megawatts: how much electricity the data center is built to draw at full use. 1 MW is roughly the power of 750–1,000 homes.",
  MWh: "Megawatt-hours: electricity used over time. 1 MWh = running 1 MW for one hour.",
  "CO₂": "Carbon dioxide from the power plants that would supply the electricity, based on the local grid's mix.",
  "t": "Metric tons (1,000 kg, about 2,200 lb).",
  gal: "US gallons of water used on site per day, mostly for cooling.",
  eGRID: "EPA's map of power-grid regions, used to estimate how much carbon each MWh of electricity produces locally.",
  "¢/kWh": "Cents per kilowatt-hour: the average price large industrial customers pay for electricity in this state.",
  substation: "Where high-voltage power is stepped down for local use. A large data center usually needs to connect near one.",
  "transmission line": "High-voltage power line (69–765 kV) that carries electricity long distances.",
  estimate: "Estimated from 2020 Census tract populations, by the share of each tract's area inside the circle.",
  score: "3 points per high-delay review + 1 per medium-delay review. Lower is better.",
  "water stress": "How much of the area's available water is already being used (WRI Aqueduct). High stress means less room for new big water users.",
};

// <Term k="MW">MW</Term>: dotted underline + tooltip. Falls back to plain text if the key isn't in the glossary.
// Inside a button pass focusable={false} (the button already takes keyboard focus).
export default function Term({ k, tip, focusable = true, children }) {
  const text = tip || GLOSSARY[k] || GLOSSARY[String(k).toLowerCase()];
  const ref = useRef(null);
  const id = useId();
  const [pos, setPos] = useState(null);
  if (!text) return children;

  const show = () => {
    const r = ref.current.getBoundingClientRect();
    const w = 260;
    const left = Math.max(8, Math.min(r.left + r.width / 2 - w / 2, window.innerWidth - w - 8));
    const below = r.bottom + 120 < window.innerHeight;   // flip above when near the bottom of the screen
    setPos({ left, w, top: below ? r.bottom + 6 : undefined, bottom: below ? undefined : window.innerHeight - r.top + 6 });
  };
  const hide = () => setPos(null);

  return (
    <>
      <span ref={ref} tabIndex={focusable ? 0 : undefined} aria-describedby={pos ? id : undefined}
        onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}
        onKeyDown={(e) => e.key === "Escape" && hide()}
        className="cursor-help underline decoration-dotted decoration-1 underline-offset-2">
        {children}
      </span>
      {pos && createPortal(
        <div id={id} role="tooltip" style={{ left: pos.left, top: pos.top, bottom: pos.bottom, width: pos.w }}
          className="pointer-events-none fixed z-50 rounded-md bg-slate-800 px-2.5 py-1.5 text-xs font-normal normal-case leading-snug tracking-normal text-white shadow-lg">
          {text}
        </div>,
        document.body,
      )}
    </>
  );
}
