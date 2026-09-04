/**
 * Backdrop for the recruiter console.
 *
 * The ground and the orange pools come straight from welyne.com — `--color-bg`
 * #0b0a0a and its hero gradient `radial-gradient(60% 50% at 85% 8%,
 * rgba(255,107,0,.20), transparent 60%)` — so the console reads as the same
 * surface as the marketing site. Over that sit three quiet layers: a fine
 * drafting grid (the product *is* an audited state machine), film grain, and a
 * vignette that keeps the eye on the content column.
 *
 * Every layer is CSS, forked under `.dark` — never a colour read from JS.
 * `next-themes` resolves only on the client, so a JS-driven ground renders the
 * wrong colour on the server and visibly flips after hydration.
 *
 * Deliberately not a canvas. The previous version rebuilt grain tiles in a
 * `requestAnimationFrame` loop and stretched a 256px bitmap over the viewport,
 * which read as chunky television static and burned a frame budget all day on a
 * page that is open all day. An SVG turbulence filter rasterises once, costs
 * nothing after paint, and gives a finer grain.
 */

export function BackgroundNoise() {
  return (
    <div
      aria-hidden
      className="bg-background pointer-events-none fixed inset-0 -z-10 overflow-hidden"
    >
      {/* welyne.com's own hero gradient, top-right */}
      <div className="console-glow-a absolute inset-0" />
      {/* A softer pool bottom-left — the console is far wider than the site's
          column and goes flat on that side without it. */}
      <div className="console-glow-b absolute inset-0" />
      <div className="console-grid absolute inset-0" />
      <div className="console-grain absolute inset-0" />
      <div className="console-vignette absolute inset-0" />
    </div>
  );
}

export default BackgroundNoise;
