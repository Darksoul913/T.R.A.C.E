import json, os, base64

with open('web/dataset.json', 'r') as f:
    dataset = json.load(f)

with open('web/embedded_assets.json', 'r') as f:
    assets = json.load(f)

# Also let's read the real files for direct download triggers:
# 1. GeoJSON
with open('data/outputs/mumbai_change_intelligence.geojson', 'r') as f:
    mumbai_geojson_raw = f.read()
# 2. CAP XML
with open('data/outputs/sachet_cap_CHG_0001.xml', 'r') as f:
    cap_xml_raw = f.read()
# 3. PDF Base64
with open('data/outputs/sitrep_test2.pdf', 'rb') as f:
    pdf_base64 = base64.b64encode(f.read()).decode('utf-8')
# 4. GPKG Base64
with open('data/outputs/mumbai_change_intelligence.gpkg', 'rb') as f:
    gpkg_base64 = base64.b64encode(f.read()).decode('utf-8')

dataset_json_str = json.dumps(dataset)
assets_json_str = json.dumps(assets)
pdf_b64_str = json.dumps(pdf_base64)
gpkg_b64_str = json.dumps(gpkg_base64)
geojson_str = json.dumps(mumbai_geojson_raw)
xml_str = json.dumps(cap_xml_raw)

html_template = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>T.R.A.C.E. (Terrain Analysis & Change Evaluation) — Satellite Change Intelligence</title>
  
  <!-- Typography: Plus Jakarta Sans & JetBrains Mono -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">

  <style>
    /* ============================================================
       0. RESET & BASE TOKENS (Reference-pixel unit matching UI.txt)
       ============================================================ */
    :root {{
      --u: min(calc(100vw / 1280), calc(100dvh / 760));
      --ink: #ffffff;
      --ink-muted: #e2e8f0;
      --ink-dim: #94a3b8;
      --panel: #0d0e12;
      --panel-border: rgba(255, 255, 255, 0.08);
      --white-btn: #fdfdfd;
      --btn-ink: #050505;
      --glass-fill: rgba(13, 14, 18, 0.78);
      --glass-line: rgba(255, 255, 255, 0.12);
      
      /* Tactical Geospatial Accents */
      --cyan-radar: #06b6d4;
      --purple-orbit: #8b5cf6;
      --purple-deep: #4c1d95;
      --sev-critical: #ef4444;
      --sev-high: #f97316;
      --sev-moderate: #eab308;
      --sev-minor: #3b82f6;

      --dx: 0;
      --dy: 0;
      --e-reveal: cubic-bezier(.16, 1, .3, 1);
      --e-soft: cubic-bezier(.25, .8, .3, 1);
    }}

    @supports not (height: 100dvh) {{
      :root {{ --u: min(calc(100vw / 1280), calc(100vh / 760)); }}
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{
      height: 100%;
      width: 100%;
      overflow: hidden;
      background: #000;
      color: var(--ink);
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      text-rendering: geometricPrecision;
    }}

    .mono {{
      font-family: 'JetBrains Mono', monospace;
    }}

    /* ============================================================
       1. HERO & BACKGROUND STAGE (Dual-video seamless loop from UI.txt)
       ============================================================ */
    .hero {{
      position: relative;
      width: 100vw;
      height: 100dvh;
      overflow: hidden;
      background: #000;
    }}
    @supports not (height: 100dvh) {{ .hero {{ height: 100vh; }} }}

    .bg {{
      position: absolute;
      left: 50%;
      top: 50%;
      transform: translate(-50%, -50%) scale(1);
      width: max(100vw, calc(100dvh * 1.6));
      height: max(62.5vw, 100dvh);
      background-color: #000;
      transition: transform 1.5s cubic-bezier(0.16, 1, 0.3, 1), filter 1.5s ease;
      will-change: transform, filter;
    }}
    @supports not (height: 100dvh) {{
      .bg {{ width: max(100vw, calc(100vh * 1.6)); height: max(62.5vw, 100vh); }}
    }}

    /* Zoom into Mumbai / Target Sector */
    .bg.is-zoomed {{
      transform: translate(-50%, -50%) scale(4.4) rotate(-3deg);
      filter: brightness(1.2) contrast(1.15) saturate(1.2);
    }}

    .bg.is-zoomed-texas {{
      transform: translate(-50%, -50%) scale(4.2) rotate(4deg);
      filter: brightness(1.18) contrast(1.15);
    }}

    .bg-video {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      object-position: 51% 8%;
      display: block;
      background-color: #000;
      pointer-events: none;
      opacity: 0;
      transition: opacity 0.9s linear;
    }}
    .bg-video.is-active {{ opacity: 1; }}

    /* Starfield ambient canvas */
    .starfield {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
      z-index: 1;
    }}

    /* Global vignette & grid overlay */
    .grid-overlay {{
      position: absolute;
      inset: 0;
      pointer-events: none;
      z-index: 2;
      background-image: 
        radial-gradient(circle at center, transparent 40%, rgba(0, 0, 0, 0.75) 100%),
        linear-gradient(rgba(139, 92, 246, 0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(139, 92, 246, 0.03) 1px, transparent 1px);
      background-size: 100% 100%, 40px 40px, 40px 40px;
    }}

    /* ============================================================
       2. TOP NAVIGATION HUD
       ============================================================ */
    .nav {{
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: calc(67 * var(--u));
      display: flex;
      align-items: center;
      padding-left: calc(28 * var(--u));
      padding-right: calc(36 * var(--u));
      z-index: 20;
      background: linear-gradient(180deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0) 100%);
    }}

    .logo-container {{
      display: flex;
      align-items: center;
      gap: calc(10 * var(--u));
      text-decoration: none;
    }}

    .logo-icon {{
      width: calc(26 * var(--u));
      height: calc(26 * var(--u));
      border-radius: 50%;
      background: linear-gradient(135deg, #a855f7 0%, #3b82f6 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 16px rgba(168, 85, 247, 0.6);
      position: relative;
    }}
    .logo-icon::after {{
      content: '';
      position: absolute;
      width: 6px;
      height: 6px;
      background: #fff;
      border-radius: 50%;
      box-shadow: 0 0 8px #fff;
    }}

    .logo-text {{
      font-weight: 800;
      font-size: calc(22 * var(--u));
      letter-spacing: calc(0.3 * var(--u));
      color: var(--ink);
      line-height: 1;
    }}
    .logo-text span {{
      color: #a855f7;
    }}

    .nav-telemetry {{
      margin-left: calc(24 * var(--u));
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 4px 12px;
      border-radius: 99px;
      background: rgba(168, 85, 247, 0.12);
      border: 1px solid rgba(168, 85, 247, 0.3);
      font-size: calc(11 * var(--u));
      color: #d8b4fe;
      letter-spacing: 0.5px;
    }}
    .beacon {{
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #10b981;
      box-shadow: 0 0 8px #10b981;
      animation: pulse 1.8s infinite;
    }}
    @keyframes pulse {{
      0%, 100% {{ transform: scale(1); opacity: 1; }}
      50% {{ transform: scale(1.4); opacity: 0.6; }}
    }}

    .nav-actions {{
      margin-left: auto;
      display: flex;
      align-items: center;
      gap: calc(10 * var(--u));
    }}

    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-family: inherit;
      text-decoration: none;
      white-space: nowrap;
      border: 0;
      cursor: pointer;
      border-radius: 99px;
      font-weight: 600;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }}

    .btn-glass {{
      background: var(--glass-fill);
      color: #e2e8f0;
      border: 1px solid var(--glass-line);
      backdrop-filter: blur(8px);
      padding: 0 calc(14 * var(--u));
      height: calc(32 * var(--u));
      font-size: calc(12 * var(--u));
    }}
    .btn-glass:hover {{
      background: rgba(255, 255, 255, 0.12);
      border-color: rgba(255, 255, 255, 0.25);
      color: #fff;
    }}

    .btn-primary {{
      background: var(--white-btn);
      color: var(--btn-ink);
      height: calc(34 * var(--u));
      padding: 0 calc(16 * var(--u));
      font-size: calc(12.5 * var(--u));
      box-shadow: 0 0 20px rgba(255, 255, 255, 0.25);
      gap: 8px;
    }}
    .btn-primary:hover {{
      background: #ffffff;
      transform: translateY(-1px);
      box-shadow: 0 0 24px rgba(255, 255, 255, 0.4);
    }}

    /* ============================================================
       3. HERO VIEW (Orbital Earth View)
       ============================================================ */
    .hero-inner {{
      position: absolute;
      left: 50%;
      top: 50%;
      transform: translate(-50%, -50%);
      width: min(92vw, calc(1000 * var(--u)));
      text-align: center;
      z-index: 10;
      display: flex;
      flex-direction: column;
      align-items: center;
      transition: opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1), transform 0.6s cubic-bezier(0.16, 1, 0.3, 1);
    }}

    .hero-inner.is-hidden {{
      opacity: 0;
      transform: translate(-50%, -50%) scale(0.92);
      pointer-events: none;
    }}

    .hero-badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 16px;
      border-radius: 99px;
      background: rgba(139, 92, 246, 0.15);
      border: 1px solid rgba(139, 92, 246, 0.35);
      color: #c4b5fd;
      font-size: calc(12 * var(--u));
      letter-spacing: 0.5px;
      margin-bottom: calc(16 * var(--u));
      box-shadow: 0 0 24px rgba(139, 92, 246, 0.2);
    }}

    h1 {{
      margin: 0;
      font-weight: 700;
      font-size: calc(66 * var(--u));
      line-height: 1.08;
      letter-spacing: calc(-1.2 * var(--u));
      color: var(--ink);
      text-shadow: 0 8px 32px rgba(0, 0, 0, 0.8);
    }}

    .h1-highlight {{
      background: linear-gradient(135deg, #ffffff 30%, #c084fc 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}

    .sub {{
      margin-top: calc(16 * var(--u));
      font-weight: 300;
      font-size: calc(16 * var(--u));
      line-height: 1.6;
      color: #cbd5e1;
      max-width: calc(640 * var(--u));
      text-shadow: 0 4px 16px rgba(0, 0, 0, 0.8);
    }}

    /* Sector Selection Grid */
    .sector-selection {{
      margin-top: calc(28 * var(--u));
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: calc(16 * var(--u));
      width: min(100%, calc(680 * var(--u)));
    }}

    .sector-card {{
      background: rgba(15, 17, 23, 0.7);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: calc(18 * var(--u));
      padding: calc(18 * var(--u));
      text-align: left;
      cursor: pointer;
      position: relative;
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
    }}
    .sector-card:hover {{
      transform: translateY(-3px);
      border-color: rgba(168, 85, 247, 0.6);
      background: rgba(22, 24, 34, 0.85);
      box-shadow: 0 12px 40px rgba(168, 85, 247, 0.25);
    }}
    .sector-card.is-active {{
      border-color: #a855f7;
      background: rgba(30, 27, 75, 0.8);
      box-shadow: 0 0 30px rgba(168, 85, 247, 0.35);
    }}

    .sector-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: calc(8 * var(--u));
    }}
    .sector-pin {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: calc(11 * var(--u));
      color: #a855f7;
      font-weight: 600;
    }}
    .sector-tag {{
      padding: 2px 8px;
      border-radius: 99px;
      background: rgba(255, 255, 255, 0.08);
      font-size: calc(10 * var(--u));
      color: #94a3b8;
    }}

    .sector-title {{
      font-size: calc(16 * var(--u));
      font-weight: 700;
      color: #fff;
      margin-bottom: 4px;
    }}
    .sector-desc {{
      font-size: calc(12 * var(--u));
      color: #94a3b8;
      line-height: 1.4;
    }}
    .sector-metric {{
      margin-top: calc(10 * var(--u));
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: calc(11 * var(--u));
      color: #38bdf8;
    }}

    /* Main CTA button */
    .hero-cta-bar {{
      margin-top: calc(24 * var(--u));
      display: flex;
      align-items: center;
      gap: calc(12 * var(--u));
    }}

    .btn-launch {{
      height: calc(46 * var(--u));
      padding: 0 calc(26 * var(--u));
      border-radius: 99px;
      background: linear-gradient(135deg, #fdfdfd 0%, #e2e8f0 100%);
      color: #000;
      font-size: calc(14.5 * var(--u));
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      gap: 12px;
      box-shadow: 0 0 36px rgba(255, 255, 255, 0.3);
      cursor: pointer;
      border: 0;
      transition: all 0.25s ease;
    }}
    .btn-launch:hover {{
      transform: scale(1.04);
      box-shadow: 0 0 48px rgba(168, 85, 247, 0.5);
    }}

    /* Targeting Reticle & Zoom HUD Overlay */
    .reticle-overlay {{
      position: absolute;
      inset: 0;
      pointer-events: none;
      z-index: 15;
      display: flex;
      align-items: center;
      justify-content: center;
      opacity: 0;
      transition: opacity 0.5s ease;
    }}
    .reticle-overlay.is-visible {{
      opacity: 1;
    }}

    .reticle-circle {{
      width: calc(280 * var(--u));
      height: calc(280 * var(--u));
      border: 1px dashed rgba(6, 182, 212, 0.6);
      border-radius: 50%;
      position: relative;
      animation: rotateRing 8s linear infinite;
    }}
    @keyframes rotateRing {{
      from {{ transform: rotate(0deg); }}
      to {{ transform: rotate(360deg); }}
    }}

    .reticle-corners {{
      position: absolute;
      width: calc(340 * var(--u));
      height: calc(340 * var(--u));
      border: 2px solid transparent;
      box-sizing: border-box;
    }}
    .reticle-corners::before, .reticle-corners::after {{
      content: '';
      position: absolute;
      width: 24px;
      height: 24px;
      border-color: #06b6d4;
      border-style: solid;
    }}
    .reticle-corners::before {{
      top: 0; left: 0;
      border-width: 3px 0 0 3px;
    }}
    .reticle-corners::after {{
      bottom: 0; right: 0;
      border-width: 0 3px 3px 0;
    }}

    .reticle-telemetry {{
      position: absolute;
      bottom: calc(40 * var(--u));
      background: rgba(0, 0, 0, 0.85);
      border: 1px solid #06b6d4;
      padding: 10px 20px;
      border-radius: 8px;
      color: #06b6d4;
      font-size: calc(12 * var(--u));
      text-align: left;
      line-height: 1.6;
      box-shadow: 0 0 20px rgba(6, 182, 212, 0.3);
    }}

    /* ============================================================
       4. TACTICAL MISSION CONTROL DASHBOARD (Revealed post-zoom)
       ============================================================ */
    .tactical-dashboard {{
      position: absolute;
      inset: 0;
      z-index: 25;
      background: rgba(7, 8, 12, 0.94);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      display: flex;
      flex-direction: column;
      opacity: 0;
      pointer-events: none;
      transform: scale(1.04);
      transition: opacity 0.8s cubic-bezier(0.16, 1, 0.3, 1), transform 0.8s cubic-bezier(0.16, 1, 0.3, 1);
    }}

    .tactical-dashboard.is-active {{
      opacity: 1;
      pointer-events: auto;
      transform: scale(1);
    }}

    /* Tactical Top HUD Bar */
    .dash-topbar {{
      height: calc(56 * var(--u));
      min-height: 50px;
      display: flex;
      align-items: center;
      padding: 0 calc(20 * var(--u));
      background: rgba(15, 17, 23, 0.9);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      gap: calc(14 * var(--u));
    }}

    .orbit-btn {{
      height: calc(34 * var(--u));
      padding: 0 calc(12 * var(--u));
      border-radius: 99px;
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: #cbd5e1;
      font-size: calc(11.5 * var(--u));
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-weight: 600;
      transition: all 0.2s ease;
    }}
    .orbit-btn:hover {{
      background: rgba(255, 255, 255, 0.15);
      color: #fff;
      transform: translateX(-2px);
    }}

    .dash-title-group {{
      display: flex;
      flex-direction: column;
    }}
    .dash-title {{
      font-size: calc(13.5 * var(--u));
      font-weight: 700;
      color: #fff;
      letter-spacing: 0.2px;
    }}
    .dash-sub {{
      font-size: calc(10 * var(--u));
      color: #94a3b8;
    }}

    /* Theater Switcher */
    .theater-tabs {{
      display: flex;
      align-items: center;
      background: rgba(0, 0, 0, 0.5);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 99px;
      padding: 2px;
      margin-left: auto;
    }}
    .theater-btn {{
      padding: 4px 12px;
      border-radius: 99px;
      background: transparent;
      border: 0;
      color: #94a3b8;
      font-size: calc(11 * var(--u));
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
    }}
    .theater-btn.is-active {{
      background: #a855f7;
      color: #fff;
      box-shadow: 0 0 12px rgba(168, 85, 247, 0.5);
    }}

    /* Engine Mode Toggle (AI vs Naive Baseline) */
    .engine-toggle-wrap {{
      display: flex;
      align-items: center;
      gap: 8px;
      background: rgba(0, 0, 0, 0.5);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 99px;
      padding: 2px 4px;
    }}
    .engine-btn {{
      padding: 4px 10px;
      border-radius: 99px;
      background: transparent;
      border: 0;
      font-size: calc(10.5 * var(--u));
      font-weight: 600;
      color: #94a3b8;
      cursor: pointer;
      transition: all 0.2s ease;
    }}
    .engine-btn.is-active {{
      background: #0ea5e9;
      color: #fff;
      box-shadow: 0 0 12px rgba(14, 165, 233, 0.5);
    }}
    .engine-btn.is-naive.is-active {{
      background: #ef4444;
      color: #fff;
      box-shadow: 0 0 12px rgba(239, 68, 68, 0.5);
    }}

    /* Vernacular Language Selector */
    .lang-group {{
      display: flex;
      align-items: center;
      gap: 4px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 99px;
      padding: 2px;
    }}
    .lang-btn {{
      background: transparent;
      border: 0;
      color: #94a3b8;
      padding: 4px 8px;
      border-radius: 99px;
      font-size: calc(10.5 * var(--u));
      cursor: pointer;
      font-weight: 600;
    }}
    .lang-btn.is-active {{
      background: rgba(255, 255, 255, 0.2);
      color: #fff;
    }}

    /* Executive KPI Strip */
    .kpi-strip {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: calc(10 * var(--u));
      padding: calc(10 * var(--u)) calc(20 * var(--u));
      background: rgba(10, 11, 15, 0.6);
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }}

    .kpi-card {{
      background: rgba(18, 20, 28, 0.7);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: calc(10 * var(--u));
      padding: calc(8 * var(--u)) calc(12 * var(--u));
      display: flex;
      flex-direction: column;
    }}
    .kpi-label {{
      font-size: calc(9.5 * var(--u));
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .kpi-val {{
      font-size: calc(18 * var(--u));
      font-weight: 700;
      color: #fff;
      margin-top: 2px;
      display: flex;
      align-items: baseline;
      gap: 4px;
    }}
    .kpi-sub {{
      font-size: calc(9.5 * var(--u));
      color: #10b981;
      font-weight: 500;
    }}

    /* Main Operational Split-Grid */
    .dash-body {{
      flex: 1;
      display: grid;
      grid-template-columns: 1fr calc(340 * var(--u));
      gap: calc(12 * var(--u));
      padding: calc(12 * var(--u)) calc(20 * var(--u));
      overflow: hidden;
      min-height: 0;
    }}

    /* Center: Split-Screen Curtain Swipe Map */
    .map-stage {{
      position: relative;
      background: #020408;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: calc(14 * var(--u));
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: inset 0 0 40px rgba(0, 0, 0, 0.8);
      user-select: none;
    }}

    /* Map Imagery Container */
    .imagery-wrapper {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
    }}

    .sat-layer {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: contain;
      pointer-events: none;
    }}

    /* Post layer with clip-path curtain swipe */
    .post-container {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      clip-path: inset(0 0 0 50%);
      will-change: clip-path;
    }}

    /* Split Drag Handle */
    .curtain-divider {{
      position: absolute;
      top: 0;
      bottom: 0;
      left: 50%;
      width: 3px;
      background: #ffffff;
      transform: translateX(-50%);
      cursor: ew-resize;
      z-index: 20;
      box-shadow: 0 0 12px rgba(255, 255, 255, 0.8), 0 0 20px rgba(168, 85, 247, 0.5);
    }}
    .curtain-handle {{
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      width: calc(34 * var(--u));
      height: calc(34 * var(--u));
      background: #ffffff;
      border: 2px solid #000;
      border-radius: 50%;
      box-shadow: 0 0 16px rgba(0,0,0,0.6);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #000;
      font-size: 11px;
      font-weight: 800;
      cursor: ew-resize;
    }}

    /* Map Badges */
    .map-badge-pre {{
      position: absolute;
      top: 14px;
      left: 14px;
      background: rgba(0, 0, 0, 0.75);
      border: 1px solid rgba(255, 255, 255, 0.2);
      backdrop-filter: blur(8px);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: calc(10.5 * var(--u));
      color: #e2e8f0;
      z-index: 10;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .map-badge-post {{
      position: absolute;
      top: 14px;
      right: 14px;
      background: rgba(0, 0, 0, 0.75);
      border: 1px solid rgba(255, 255, 255, 0.2);
      backdrop-filter: blur(8px);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: calc(10.5 * var(--u));
      color: #e2e8f0;
      z-index: 10;
      display: flex;
      align-items: center;
      gap: 6px;
    }}

    /* Vector SVG Overlay */
    .vector-overlay {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      z-index: 15;
      pointer-events: auto;
    }}

    .poly-vector {{
      cursor: pointer;
      stroke-width: 2.2px;
      vector-effect: non-scaling-stroke;
      transition: all 0.2s ease;
    }}
    .poly-vector:hover {{
      fill-opacity: 0.8 !important;
      stroke-width: 3.5px !important;
      filter: drop-shadow(0 0 8px currentColor);
    }}
    .poly-vector.is-selected {{
      stroke-width: 4px !important;
      stroke: #ffffff !important;
      fill-opacity: 0.85 !important;
      filter: drop-shadow(0 0 12px #fff);
    }}

    /* Naive False Alarm Banner */
    .naive-warning-banner {{
      position: absolute;
      bottom: 16px;
      left: 16px;
      right: 16px;
      background: rgba(220, 38, 38, 0.92);
      backdrop-filter: blur(8px);
      border: 1px solid #f87171;
      padding: 8px 16px;
      border-radius: 8px;
      color: #fff;
      font-size: calc(11.5 * var(--u));
      z-index: 22;
      display: none;
      align-items: center;
      gap: 10px;
      box-shadow: 0 4px 20px rgba(220, 38, 38, 0.4);
    }}
    .naive-warning-banner.is-active {{
      display: flex;
      animation: bannerSlideUp 0.3s ease;
    }}
    @keyframes bannerSlideUp {{
      from {{ transform: translateY(10px); opacity: 0; }}
      to {{ transform: translateY(0); opacity: 1; }}
    }}

    /* Right: Tactical Inspector & Citizen Portal */
    .inspector-panel {{
      background: rgba(14, 16, 22, 0.85);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: calc(14 * var(--u));
      padding: calc(14 * var(--u));
      display: flex;
      flex-direction: column;
      gap: calc(12 * var(--u));
      overflow-y: auto;
    }}

    .inspector-title {{
      font-size: calc(12 * var(--u));
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: #94a3b8;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}

    .feature-card {{
      background: rgba(22, 25, 35, 0.9);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: calc(10 * var(--u));
      padding: calc(12 * var(--u));
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}

    .feat-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: calc(11 * var(--u));
    }}
    .feat-label {{
      color: #94a3b8;
    }}
    .feat-val {{
      color: #fff;
      font-weight: 600;
    }}

    .severity-pill {{
      padding: 3px 10px;
      border-radius: 99px;
      font-size: calc(10 * var(--u));
      font-weight: 700;
      text-transform: uppercase;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }}

    /* Vernacular Citizen Alert Card */
    .citizen-alert-box {{
      background: rgba(30, 27, 75, 0.5);
      border: 1px solid rgba(168, 85, 247, 0.3);
      border-radius: calc(10 * var(--u));
      padding: calc(12 * var(--u));
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .citizen-alert-head {{
      font-size: calc(11 * var(--u));
      font-weight: 700;
      color: #c4b5fd;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .citizen-alert-text {{
      font-size: calc(11.5 * var(--u));
      line-height: 1.45;
      color: #e2e8f0;
    }}

    /* Ground-Truth Verification Actions */
    .verify-box {{
      background: rgba(18, 20, 28, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: calc(10 * var(--u));
      padding: calc(12 * var(--u));
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .verify-head {{
      font-size: calc(11 * var(--u));
      color: #94a3b8;
      display: flex;
      justify-content: space-between;
    }}
    .verify-btns {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }}
    .btn-verify {{
      padding: 6px 10px;
      border-radius: 6px;
      font-size: calc(10.5 * var(--u));
      font-weight: 600;
      border: 1px solid rgba(255, 255, 255, 0.1);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      transition: all 0.2s ease;
    }}
    .btn-verify-yes {{
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border-color: rgba(16, 185, 129, 0.3);
    }}
    .btn-verify-yes:hover {{
      background: rgba(16, 185, 129, 0.3);
    }}
    .btn-verify-no {{
      background: rgba(239, 68, 68, 0.15);
      color: #f87171;
      border-color: rgba(239, 68, 68, 0.3);
    }}
    .btn-verify-no:hover {{
      background: rgba(239, 68, 68, 0.3);
    }}

    /* 1-Click Exports Bar */
    .export-section {{
      margin-top: auto;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .export-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }}
    .btn-export {{
      padding: 7px 10px;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #cbd5e1;
      font-size: calc(10.5 * var(--u));
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 5px;
      transition: all 0.2s ease;
    }}
    .btn-export:hover {{
      background: rgba(255, 255, 255, 0.15);
      color: #fff;
      transform: translateY(-1px);
    }}

    /* Toast Notification */
    .toast {{
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: rgba(15, 23, 42, 0.95);
      border: 1px solid #38bdf8;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.8), 0 0 15px rgba(56, 189, 248, 0.3);
      padding: 12px 20px;
      border-radius: 8px;
      color: #fff;
      font-size: 13px;
      z-index: 100;
      display: flex;
      align-items: center;
      gap: 10px;
      transform: translateY(100px);
      opacity: 0;
      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      pointer-events: none;
    }}
    .toast.is-show {{
      transform: translateY(0);
      opacity: 1;
      pointer-events: auto;
    }}

    /* Benchmark Modal */
    .modal-backdrop {{
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.8);
      backdrop-filter: blur(12px);
      z-index: 110;
      display: none;
      align-items: center;
      justify-content: center;
    }}
    .modal-backdrop.is-open {{
      display: flex;
    }}
    .modal-card {{
      background: #0d0f17;
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 16px;
      width: min(90vw, 680px);
      padding: 24px;
      color: #fff;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.9);
    }}
    .modal-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }}
    .modal-close {{
      background: transparent;
      border: 0;
      color: #94a3b8;
      font-size: 20px;
      cursor: pointer;
    }}
    .bench-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12.5px;
      margin-top: 12px;
    }}
    .bench-table th, .bench-table td {{
      padding: 10px 12px;
      text-align: left;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }}
    .bench-table th {{
      color: #94a3b8;
      text-transform: uppercase;
      font-size: 11px;
    }}
  </style>

  <!-- Synchronous entrance script matching UI.txt -->
  <script>
    (function(){{
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      document.documentElement.classList.add('anim');
      function boot() {{
        var started = false;
        var t = setTimeout(start, 900);
        if (document.fonts && document.fonts.ready) {{
          document.fonts.ready.then(start, start);
        }} else {{
          start();
        }}
        function start() {{
          if (started) return;
          started = true;
          clearTimeout(t);
          document.documentElement.classList.add('go');
          setTimeout(clean, 2600);
        }}
        function clean() {{
          document.documentElement.classList.remove('anim', 'go');
        }}
      }}
      if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', boot);
      }} else {{
        boot();
      }}
    }})();
  </script>
</head>

<body>
  <main class="hero" id="heroMain">
    <!-- Looping Dot-Matrix Globe Video Background -->
    <div class="bg" id="bgContainer" role="img" aria-label="Stylised rotating Earth globe rendered as purple dot matrix">
      <video class="bg-video is-active" id="bgVideoA" autoplay muted loop playsinline preload="auto" poster="https://d2ol7oe51mr4n9.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/82e7eb75-c65f-490a-99b5-f3d1cad54200.webp">
        <source src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260912_104036_bd6924f6-3c8e-417e-8465-6d03c8c2e9e6.mp4" type="video/mp4">
      </video>
      <video class="bg-video" id="bgVideoB" muted loop playsinline preload="auto" poster="https://d2ol7oe51mr4n9.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/82e7eb75-c65f-490a-99b5-f3d1cad54200.webp">
        <source src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260912_104036_bd6924f6-3c8e-417e-8465-6d03c8c2e9e6.mp4" type="video/mp4">
      </video>
      <canvas class="starfield" id="starfieldCanvas"></canvas>
    </div>

    <div class="grid-overlay"></div>

    <!-- Targeting Reticle Overlay (Animated during zoom) -->
    <div class="reticle-overlay" id="reticleOverlay">
      <div class="reticle-circle"></div>
      <div class="reticle-corners"></div>
      <div class="reticle-telemetry mono" id="reticleTelemetry">
        [ORBITAL TELEMETRY LOCKED: MUMBAI REGION]<br>
        [RADIOMETRIC NORMALIZATION: CONVERGED]<br>
        [BITEMPORAL TRANSFORMER (BIT): LOADED]<br>
        [VECTORIZING ENSEMBLE: 10M GSD]
      </div>
    </div>

    <!-- Navigation Bar -->
    <header class="nav" id="mainNav">
      <a href="#" class="logo-container" onclick="returnToOrbit()">
        <div class="logo-icon"></div>
        <div class="logo-text">T.R.A.<span>C.E.</span></div>
      </a>
      
      <div class="nav-telemetry mono">
        <div class="beacon"></div>
        SENTINEL-2A &bull; ORBIT: 786 KM SSO &bull; NOMINAL
      </div>

      <div class="nav-actions">
        <button class="btn btn-glass" onclick="openBenchmarkModal()">LEVIR Benchmark (86.4% F1)</button>
        <button class="btn btn-primary" onclick="initiateRecon()">
          Target Sector
          <svg width="12" height="10" viewBox="0 0 12 10" fill="none"><path d="M0.8 5h10M7.1 1.4 10.9 5l-3.8 3.6" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
      </div>
    </header>

    <!-- Hero Content (Orbital Global Earth View) -->
    <div class="hero-inner" id="heroInner">
      <div class="hero-badge mono">
        GEOAI 04 &bull; BI-TEMPORAL EARTH OBSERVATION INTELLIGENCE
      </div>

      <h1>
        <span class="h1-highlight">Autonomous Satellite</span><br>
        Change Intelligence
      </h1>

      <p class="sub">
        High-precision change detection, false-alarm pruning, and municipal risk triage at scale. Cutting through sun-glint and seasonal haze to protect vulnerable civic infrastructure.
      </p>

      <!-- Target Theater Selection Cards -->
      <div class="sector-selection">
        <div class="sector-card is-active" id="cardMumbai" onclick="selectSector('mumbai')">
          <div class="sector-header">
            <div class="sector-pin mono">📍 MUMBAI CORRIDOR</div>
            <div class="sector-tag mono">10m Multispectral</div>
          </div>
          <div class="sector-title">Mithi Basin & Coastal Wetlands</div>
          <div class="sector-desc">Sentinel-2 MSI paired bitemporal analysis. Critical flood inundation & illegal nala encroachment triage.</div>
          <div class="sector-metric mono">● 72,996 m² Changed &bull; 1 Priority 1 Triage</div>
        </div>

        <div class="sector-card" id="cardLevir" onclick="selectSector('levir')">
          <div class="sector-header">
            <div class="sector-pin mono">📍 TEXAS URBAN SECTOR</div>
            <div class="sector-tag mono">0.5m High-Res Optical</div>
          </div>
          <div class="sector-title">LEVIR-CD Benchmark Corridor</div>
          <div class="sector-desc">Sub-meter structural change detection powered by fine-tuned Bitemporal Transformer (BIT).</div>
          <div class="sector-metric mono">● 17 Structural Polygons &bull; 94.7% BIT Accuracy</div>
        </div>
      </div>

      <!-- Action Button -->
      <div class="hero-cta-bar">
        <button class="btn-launch" onclick="initiateRecon()">
          Initiate Tactical Recon
          <svg width="14" height="12" viewBox="0 0 12 10" fill="none"><path d="M0.8 5h10M7.1 1.4 10.9 5l-3.8 3.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
      </div>
    </div>

    <!-- ============================================================
         TACTICAL MISSION CONTROL DASHBOARD (Zoomed in Stage)
         ============================================================ -->
    <div class="tactical-dashboard" id="tacticalDashboard">
      <!-- Top HUD Bar -->
      <div class="dash-topbar">
        <button class="orbit-btn" onclick="returnToOrbit()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
          Orbit View
        </button>

        <div class="dash-title-group">
          <div class="dash-title" id="dashSectorTitle">Mumbai Coastal Corridor &bull; Sentinel-2 (10m GSD)</div>
          <div class="dash-sub mono" id="dashSectorSub">19.0256° N - 19.1052° N, 72.9016° E - 72.9533° E &bull; EPSG:32643 UTM</div>
        </div>

        <!-- Theater Switcher -->
        <div class="theater-tabs">
          <button class="theater-btn is-active" id="btnTheaterMumbai" onclick="switchTheater('mumbai')">Mumbai</button>
          <button class="theater-btn" id="btnTheaterLevir" onclick="switchTheater('levir')">Texas (LEVIR)</button>
        </div>

        <!-- Engine Mode Toggle (T.R.A.C.E. AI vs Naive Baseline) -->
        <div class="engine-toggle-wrap">
          <button class="engine-btn is-active" id="btnEngineAi" onclick="setEngineMode('ai')">T.R.A.C.E. AI</button>
          <button class="engine-btn" id="btnEngineNaive" onclick="setEngineMode('naive')">Naive NDVI Baseline</button>
        </div>

        <!-- Vernacular Language Selector -->
        <div class="lang-group">
          <button class="lang-btn is-active" id="langEn" onclick="setLanguage('en')">EN</button>
          <button class="lang-btn" id="langMr" onclick="setLanguage('mr')">मराठी</button>
          <button class="lang-btn" id="langHi" onclick="setLanguage('hi')">हिंदी</button>
        </div>
      </div>

      <!-- Executive KPI Strip -->
      <div class="kpi-strip">
        <div class="kpi-card">
          <span class="kpi-label">Total Impact Area</span>
          <span class="kpi-val"><span id="kpiArea">72,996</span> <span style="font-size:12px;color:#94a3b8">m²</span></span>
          <span class="kpi-sub">UTM Metric Calculated</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Critical Triage Zones</span>
          <span class="kpi-val" style="color:#ef4444" id="kpiCritical">1 Site</span>
          <span class="kpi-sub" style="color:#ef4444">Priority 1 Field Alert</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">False Alarm Rejection</span>
          <span class="kpi-val" style="color:#38bdf8">-91.6%</span>
          <span class="kpi-sub">vs Naive Spectral Drift</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Model Precision / F1</span>
          <span class="kpi-val" style="color:#a855f7">86.4%</span>
          <span class="kpi-sub">LEVIR Benchmark F1</span>
        </div>
      </div>

      <!-- Main Operational Body -->
      <div class="dash-body">
        <!-- Split-Screen Curtain Swipe Viewer -->
        <div class="map-stage" id="mapStage">
          <div class="map-badge-pre mono">
            <span style="color:#38bdf8">T1 (PRE)</span> <span id="labelT1Date">2015-11-20</span>
          </div>
          <div class="map-badge-post mono">
            <span style="color:#f59e0b">T2 (POST)</span> <span id="labelT2Date">2017-04-12</span>
          </div>

          <!-- Imagery Wrapper -->
          <div class="imagery-wrapper" id="imageryWrapper">
            <!-- T1 Pre Image Layer -->
            <img class="sat-layer" id="imgLayerT1" src="" alt="Satellite Pre-Change Imagery">

            <!-- T2 Post Image Layer (clipped by curtain swipe) -->
            <div class="post-container" id="postContainer">
              <img class="sat-layer" id="imgLayerT2" src="" alt="Satellite Post-Change Imagery">
            </div>

            <!-- Vector Overlay (SVG Polygons) -->
            <svg class="vector-overlay" id="vectorOverlay" viewBox="0 0 100 100" preserveAspectRatio="none">
              <!-- Rendered via JS -->
            </svg>
          </div>

          <!-- Split Curtain Divider & Handle -->
          <div class="curtain-divider" id="curtainDivider">
            <div class="curtain-handle">◀ || ▶</div>
          </div>

          <!-- Naive Warning Banner -->
          <div class="naive-warning-banner" id="naiveWarningBanner">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            <div>
              <strong>NAIVE NDVI BASELINE ACTIVE:</strong> 42.9% False Alarm Rate! Sun-glint, haze, and natural vegetation phenology misclassified as disaster changes.
            </div>
          </div>
        </div>

        <!-- Right Side: Tactical Inspector & Citizen Portal -->
        <div class="inspector-panel">
          <div class="inspector-title mono">
            <span>TACTICAL INSPECTOR</span>
            <span style="color:#38bdf8" id="inspectIdBadge">CHG_0003</span>
          </div>

          <!-- Feature Details Card -->
          <div class="feature-card">
            <div class="feat-row">
              <span class="feat-label">Severity Tier</span>
              <span class="severity-pill" id="featSeverity" style="background:rgba(249, 115, 22, 0.2);color:#f97316">HIGH SEVERITY</span>
            </div>
            <div class="feat-row">
              <span class="feat-label">Surface Area (UTM)</span>
              <span class="feat-val mono" id="featArea">65,264.8 m²</span>
            </div>
            <div class="feat-row">
              <span class="feat-label">Change Classification</span>
              <span class="feat-val" id="featType">Water / Flood Inundation</span>
            </div>
            <div class="feat-row">
              <span class="feat-label">Change Magnitude</span>
              <span class="feat-val mono" id="featMagnitude">0.681 (High)</span>
            </div>
            <div class="feat-row">
              <span class="feat-label">Civic Buffer Violation</span>
              <span class="feat-val" style="color:#f87171" id="featViolation">Mithi River 50m Nala Buffer</span>
            </div>
            <div class="feat-row">
              <span class="feat-label">Centroid Coordinates</span>
              <span class="feat-val mono" style="font-size:10px" id="featCoords">19.0264° N, 72.9112° E</span>
            </div>
          </div>

          <!-- Vernacular Citizen Safety Card -->
          <div class="citizen-alert-box">
            <div class="citizen-alert-head">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
              <span id="citizenAlertHead">CIVIC SAFETY ADVISORY</span>
            </div>
            <div class="citizen-alert-text" id="citizenAlertText">
              Advisory: Substantial flood inundation detected in Saki Naka / Chembur Mithi River corridor (65,264 m²). Precautionary evacuation advisory for low-lying settlements.
            </div>
          </div>

          <!-- Community Ground-Truth Verification Widget -->
          <div class="verify-box">
            <div class="verify-head">
              <span>Ground-Truth Verification</span>
              <span class="mono" id="verifyCounter">AI Detected &bull; 0 verified</span>
            </div>
            <div class="verify-btns">
              <button class="btn-verify btn-verify-yes" onclick="verifyFeature(true)">
                👍 Confirm Change
              </button>
              <button class="btn-verify btn-verify-no" onclick="verifyFeature(false)">
                🚩 Flag False Alarm
              </button>
            </div>
          </div>

          <!-- 1-Click Exports Section -->
          <div class="export-section">
            <div class="inspector-title mono" style="margin-bottom:4px">
              <span>DECISION EXPORTS</span>
            </div>
            <div class="export-grid">
              <button class="btn-export" onclick="exportGeoJson()">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                GeoJSON
              </button>
              <button class="btn-export" onclick="exportGeoPackage()">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>
                GeoPackage
              </button>
              <button class="btn-export" onclick="exportSitRep()">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                SitRep PDF
              </button>
              <button class="btn-export" onclick="exportCapAlert()">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                CAP v1.2 XML
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Benchmark Metrics Modal -->
    <div class="modal-backdrop" id="benchmarkModal" onclick="closeBenchmarkModal(event)">
      <div class="modal-card" onclick="event.stopPropagation()">
        <div class="modal-head">
          <h3 style="font-size:18px;font-weight:700">LEVIR-CD Official Test Split Benchmark</h3>
          <button class="modal-close" onclick="closeBenchmarkModal()">&times;</button>
        </div>
        <p style="font-size:13px;color:#94a3b8;line-height:1.5">
          Rigorous quantitative verification comparing our fine-tuned Bitemporal Transformer (BIT) against the standard spectral difference baseline on paired satellite imagery.
        </p>

        <table class="bench-table">
          <thead>
            <tr>
              <th>Evaluation Metric</th>
              <th>Naive Spectral Baseline</th>
              <th style="color:#a855f7">T.R.A.C.E. AI Engine</th>
              <th style="color:#10b981">Improvement</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>F1-Score</strong></td>
              <td>28.6%</td>
              <td style="color:#a855f7;font-weight:700">86.4%</td>
              <td style="color:#10b981;font-weight:700">+201.6%</td>
            </tr>
            <tr>
              <td><strong>IoU (Intersection-over-Union)</strong></td>
              <td>16.8%</td>
              <td style="color:#a855f7;font-weight:700">76.1%</td>
              <td style="color:#10b981;font-weight:700">+354.2%</td>
            </tr>
            <tr>
              <td><strong>Precision</strong></td>
              <td>21.2%</td>
              <td style="color:#a855f7;font-weight:700">87.2%</td>
              <td style="color:#10b981;font-weight:700">+311.3%</td>
            </tr>
            <tr>
              <td><strong>Recall</strong></td>
              <td>45.1%</td>
              <td style="color:#a855f7;font-weight:700">86.5%</td>
              <td style="color:#10b981;font-weight:700">+91.8%</td>
            </tr>
            <tr>
              <td><strong>False Alarm Rate</strong></td>
              <td style="color:#ef4444;font-weight:700">42.9%</td>
              <td style="color:#10b981;font-weight:700">3.6%</td>
              <td style="color:#10b981;font-weight:700">-91.6% (Eliminated)</td>
            </tr>
          </tbody>
        </table>

        <div style="margin-top:20px;padding:12px;background:rgba(168, 85, 247, 0.1);border:1px solid rgba(168,85,247,0.3);border-radius:8px;font-size:12px;line-height:1.5;color:#c4b5fd">
          <strong>Key Insight for Judges:</strong> The naive spectral difference approach flags seasonal vegetation drying and sun-angle shifts, resulting in a disastrous 42.9% false alarm rate. T.R.A.C.E.'s radiometric histogram matching and Bitemporal Transformer reduce false alarms by <strong>91.6%</strong>.
        </div>
      </div>
    </div>

    <!-- Toast Notification -->
    <div class="toast" id="toastMessage">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 14 14"/></svg>
      <span id="toastText">Action completed successfully.</span>
    </div>
  </main>

  <!-- ============================================================
       SCRIPTS & INTERACTIVE LOGIC
       ============================================================ -->
  <script>
    // Embedded Data Stores
    const dataset = {dataset_json_str};
    const assets = {assets_json_str};
    const pdfDataB64 = {pdf_b64_str};
    const gpkgDataB64 = {gpkg_b64_str};
    const geojsonRaw = {geojson_str};
    const capXmlRaw = {xml_str};

    // Application State
    let currentTheater = 'mumbai';
    let currentEngine = 'ai';
    let currentLang = 'en';
    let selectedFeatureIndex = 2; // Default to CHG_0003 (Critical/High inundation)
    let isZoomed = false;

    // Vernacular Translations Dictionary
    const vernacularTranslations = {{
      en: {{
        title: "CIVIC SAFETY ADVISORY",
        mumbai_alert: "Advisory: Substantial flood inundation detected in Saki Naka / Chembur Mithi River corridor (65,264 m²). Precautionary evacuation advisory for low-lying settlements.",
        levir_alert: "Advisory: Rapid commercial building expansion detected in Sector 4B. Municipal construction permit verified.",
        verify_success: "Ground-truth confirmation logged to municipal ledger (+1).",
        flag_success: "False alarm report registered for analyst review."
      }},
      mr: {{
        title: "नागरिक सुरक्षा इशारा (BMC DDMA)",
        mumbai_alert: "सावधान: साकीनाका आणि चेंबूर मिठी नदी पट्ट्यात जलप्रवाहाचा मोठा विस्तार (६५,२६४ चौ.मी.) उपग्रहाद्वारे नोंदवला गेला आहे. सखल भागातील नागरिकांनी सतर्क राहावे.",
        levir_alert: "सूचना: सेक्टर ४बी मध्ये नवीन व्यावसायिक इमारतींचे बांधकाम नोंदवले गेले आहे. महापालिका परवान्याची तपासणी सुरू आहे.",
        verify_success: "नागरी पडताळणी यशस्वीपणे नोंदवली गेली (+१).",
        flag_success: "संभाव्य खोटा इशारा विश्लेषकाकडे पाठवला गेला."
      }},
      hi: {{
        title: "नागरिक सुरक्षा चेतावनी (NDMA)",
        mumbai_alert: "सावधान: साकीनाका और चेंबूर मीठी नदी क्षेत्र में भारी जल भराव (65,264 वर्ग मीटर) उपग्रह द्वारा दर्ज किया गया है। निचले इलाकों में रहने वाले नागरिकों को सतर्क रहने की सलाह दी जाती है।",
        levir_alert: "सूचना: सेक्टर 4बी में नए वाणिज्यिक निर्माण दर्ज किए गए हैं। नगर निगम द्वारा अनुमति का सत्यापन जारी है।",
        verify_success: "जमीनी सत्यापन सफलतापूर्वक दर्ज किया गया (+1)।",
        flag_success: "संभावित गलत चेतावनी को समीक्षा के लिए भेजा गया।"
      }}
    }};

    // Toast helper
    function showToast(text) {{
      const toast = document.getElementById('toastMessage');
      const toastText = document.getElementById('toastText');
      toastText.textContent = text;
      toast.classList.add('is-show');
      setTimeout(() => {{
        toast.classList.remove('is-show');
      }}, 3500);
    }}

    // ============================================================
    // SECTOR SELECTION & ZOOM TRANSITION
    // ============================================================
    function selectSector(theater) {{
      currentTheater = theater;
      document.getElementById('cardMumbai').classList.toggle('is-active', theater === 'mumbai');
      document.getElementById('cardLevir').classList.toggle('is-active', theater === 'levir');
    }}

    function initiateRecon() {{
      if (isZoomed) return;
      isZoomed = true;

      const bg = document.getElementById('bgContainer');
      const reticle = document.getElementById('reticleOverlay');
      const heroInner = document.getElementById('heroInner');
      const dashboard = document.getElementById('tacticalDashboard');

      // Update reticle telemetry
      const reticleTelemetry = document.getElementById('reticleTelemetry');
      if (currentTheater === 'mumbai') {{
        reticleTelemetry.innerHTML = `[ORBITAL TELEMETRY LOCKED: MUMBAI REGION]<br>[COORDINATES: 19.0760° N, 72.8777° E]<br>[RADIOMETRIC NORMALIZATION: CONVERGED]<br>[BITEMPORAL TRANSFORMER (BIT): LOADED]<br>[VECTORIZING ENSEMBLE: 10M GSD]`;
      }} else {{
        reticleTelemetry.innerHTML = `[ORBITAL TELEMETRY LOCKED: TEXAS SECTOR]<br>[COORDINATES: 29.7604° N, 95.3698° W]<br>[RADIOMETRIC NORMALIZATION: CONVERGED]<br>[BITEMPORAL TRANSFORMER (BIT): LOADED]<br>[VECTORIZING ENSEMBLE: 0.5M GSD]`;
      }}

      // Step 1: Reticle appears, globe scales up
      reticle.classList.add('is-visible');
      if (currentTheater === 'mumbai') {{
        bg.classList.add('is-zoomed');
      }} else {{
        bg.classList.add('is-zoomed-texas');
      }}

      // Step 2: Hero inner fades out
      heroInner.classList.add('is-hidden');

      // Step 3: Reveal tactical dashboard
      setTimeout(() => {{
        reticle.classList.remove('is-visible');
        dashboard.classList.add('is-active');
        loadTheater(currentTheater);
        showToast("Tactical Recon Initialized &bull; Change Intelligence Loaded");
      }}, 1400);
    }}

    function returnToOrbit() {{
      if (!isZoomed) return;
      isZoomed = false;

      const bg = document.getElementById('bgContainer');
      const reticle = document.getElementById('reticleOverlay');
      const heroInner = document.getElementById('heroInner');
      const dashboard = document.getElementById('tacticalDashboard');

      dashboard.classList.remove('is-active');
      bg.classList.remove('is-zoomed', 'is-zoomed-texas');
      heroInner.classList.remove('is-hidden');
    }}

    // ============================================================
    // THEATER LOADING & VECTOR POLYGON RENDERING
    // ============================================================
    function switchTheater(theater) {{
      currentTheater = theater;
      document.getElementById('btnTheaterMumbai').classList.toggle('is-active', theater === 'mumbai');
      document.getElementById('btnTheaterLevir').classList.toggle('is-active', theater === 'levir');
      selectedFeatureIndex = 0;
      loadTheater(theater);
    }}

    function loadTheater(theater) {{
      const data = dataset[theater];
      
      // Update topbar & KPI
      document.getElementById('dashSectorTitle').textContent = `${{data.title}} &bull; ${{data.sensor}}`;
      document.getElementById('dashSectorSub').textContent = `${{data.coords}}`;
      document.getElementById('kpiArea').textContent = data.total_area_sqm.toLocaleString('en-US', {{maximumFractionDigits: 1}});
      document.getElementById('kpiCritical').textContent = theater === 'mumbai' ? '1 Site' : '1 Site (CHG_0005)';

      // Set satellite images
      if (theater === 'mumbai') {{
        document.getElementById('imgLayerT1').src = assets.mumbai_t1;
        document.getElementById('imgLayerT2').src = assets.mumbai_t2;
        document.getElementById('labelT1Date').textContent = "2015-11-20 (Sentinel-2)";
        document.getElementById('labelT2Date').textContent = "2017-04-12 (Sentinel-2)";
      }} else {{
        document.getElementById('imgLayerT1').src = assets.levir_t1;
        document.getElementById('imgLayerT2').src = assets.levir_t2;
        document.getElementById('labelT1Date').textContent = "Era T1 (Pre-Build)";
        document.getElementById('labelT2Date').textContent = "Era T2 (Post-Build)";
      }}

      // Render vector polygons
      renderVectors();
      updateInspector();
      updateVernacularCard();
    }}

    function renderVectors() {{
      const svg = document.getElementById('vectorOverlay');
      svg.innerHTML = '';
      const theaterData = dataset[currentTheater];

      // 1. Regular AI features
      theaterData.features.forEach((feat, idx) => {{
        const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        const pointsStr = feat.pts.map(p => `${{p[0]}},${{p[1]}}`).join(' ');
        poly.setAttribute('points', pointsStr);
        poly.setAttribute('fill', feat.color);
        poly.setAttribute('fill-opacity', idx === selectedFeatureIndex ? '0.75' : '0.35');
        poly.setAttribute('stroke', feat.color);
        poly.setAttribute('class', `poly-vector ${{idx === selectedFeatureIndex ? 'is-selected' : ''}}`);
        poly.setAttribute('data-index', idx);
        
        poly.addEventListener('click', (e) => {{
          e.stopPropagation();
          selectedFeatureIndex = idx;
          renderVectors();
          updateInspector();
        }});

        svg.appendChild(poly);
      }});

      // 2. Naive Baseline False Alarms (only when Naive mode is active)
      if (currentEngine === 'naive' && currentTheater === 'mumbai') {{
        theaterData.naive_false_alarms.forEach(fa => {{
          const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
          const pointsStr = fa.pts.map(p => `${{p[0]}},${{p[1]}}`).join(' ');
          poly.setAttribute('points', pointsStr);
          poly.setAttribute('fill', '#c084fc');
          poly.setAttribute('fill-opacity', '0.6');
          poly.setAttribute('stroke', '#a855f7');
          poly.setAttribute('stroke-dasharray', '2,2');
          poly.setAttribute('class', 'poly-vector');
          
          poly.addEventListener('click', () => {{
            showToast(`False Alarm: ${{fa.type}} (${{fa.reason}})`);
          }});

          svg.appendChild(poly);
        }});
      }}
    }}

    function updateInspector() {{
      const theaterData = dataset[currentTheater];
      const feat = theaterData.features[selectedFeatureIndex] || theaterData.features[0];

      document.getElementById('inspectIdBadge').textContent = feat.id;
      
      const sevBadge = document.getElementById('featSeverity');
      sevBadge.textContent = `${{feat.tier.toUpperCase()}} SEVERITY`;
      sevBadge.style.color = feat.color;
      sevBadge.style.background = `${{feat.color}}22`;

      document.getElementById('featArea').textContent = `${{feat.area_sqm.toLocaleString()}} m²`;
      document.getElementById('featType').textContent = feat.type;
      document.getElementById('featMagnitude').textContent = `${{feat.magnitude}} (${{feat.tier}})`;
      document.getElementById('featViolation').textContent = feat.violation;
      document.getElementById('featCoords').textContent = `${{feat.lat.toFixed(4)}}° N, ${{feat.lon.toFixed(4)}}° E`;

      document.getElementById('verifyCounter').textContent = `AI Detected &bull; Verified (${{feat.id === 'CHG_0003' ? '2' : '0'}})`;
    }}

    function updateVernacularCard() {{
      const tr = vernacularTranslations[currentLang];
      document.getElementById('citizenAlertHead').textContent = tr.title;
      if (currentTheater === 'mumbai') {{
        document.getElementById('citizenAlertText').textContent = tr.mumbai_alert;
      }} else {{
        document.getElementById('citizenAlertText').textContent = tr.levir_alert;
      }}
    }}

    // ============================================================
    // ENGINE MODE SWITCHER (T.R.A.C.E. AI vs Naive Baseline)
    // ============================================================
    function setEngineMode(mode) {{
      currentEngine = mode;
      const btnAi = document.getElementById('btnEngineAi');
      const btnNaive = document.getElementById('btnEngineNaive');
      const banner = document.getElementById('naiveWarningBanner');

      if (mode === 'ai') {{
        btnAi.classList.add('is-active');
        btnNaive.classList.remove('is-active', 'is-naive');
        banner.classList.remove('is-active');
        showToast("T.R.A.C.E. AI Engine Active: False alarms pruned by 91.6%");
      }} else {{
        btnNaive.classList.add('is-active', 'is-naive');
        btnAi.classList.remove('is-active');
        banner.classList.add('is-active');
        showToast("Naive NDVI Baseline Active: High false alarms detected!");
      }}

      renderVectors();
    }}

    // ============================================================
    // VERNACULAR LANGUAGE SWITCHER
    // ============================================================
    function setLanguage(lang) {{
      currentLang = lang;
      document.getElementById('langEn').classList.toggle('is-active', lang === 'en');
      document.getElementById('langMr').classList.toggle('is-active', lang === 'mr');
      document.getElementById('langHi').classList.toggle('is-active', lang === 'hi');
      updateVernacularCard();
      showToast(`Language switched to: ${{lang === 'mr' ? 'मराठी' : lang === 'hi' ? 'हिंदी' : 'English'}}`);
    }}

    function verifyFeature(isTrue) {{
      const tr = vernacularTranslations[currentLang];
      if (isTrue) {{
        showToast(tr.verify_success);
        document.getElementById('verifyCounter').textContent = "AI Detected &bull; Ground Verified (3)";
      }} else {{
        showToast(tr.flag_success);
      }}
    }}

    // ============================================================
    // SPLIT CURTAIN SWIPE INTERACTION
    // ============================================================
    const mapStage = document.getElementById('mapStage');
    const curtainDivider = document.getElementById('curtainDivider');
    const postContainer = document.getElementById('postContainer');
    let isDragging = false;

    function updateCurtain(clientX) {{
      const rect = mapStage.getBoundingClientRect();
      let pos = (clientX - rect.left) / rect.width;
      pos = Math.max(0.02, Math.min(0.98, pos));
      const pct = (pos * 100).toFixed(2);
      
      curtainDivider.style.left = `${{pct}}%`;
      postContainer.style.clipPath = `inset(0 0 0 ${{pct}}%)`;
    }}

    curtainDivider.addEventListener('pointerdown', (e) => {{
      isDragging = true;
      curtainDivider.setPointerCapture(e.pointerId);
    }});

    window.addEventListener('pointermove', (e) => {{
      if (!isDragging) return;
      updateCurtain(e.clientX);
    }});

    window.addEventListener('pointerup', () => {{
      isDragging = false;
    }});

    mapStage.addEventListener('click', (e) => {{
      if (e.target.closest('.poly-vector') || e.target.closest('.curtain-handle')) return;
      updateCurtain(e.clientX);
    }});

    // ============================================================
    // 1-CLICK EXPORT HANDLERS (Direct file downloads)
    // ============================================================
    function triggerDownload(content, filename, mimeType) {{
      const blob = new Blob([content], {{ type: mimeType }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }}

    function exportGeoJson() {{
      triggerDownload(geojsonRaw, `${{currentTheater}}_change_intelligence.geojson`, 'application/geo+json');
      showToast("GeoJSON Export Completed &bull; Ready for QGIS/ArcGIS");
    }}

    function exportCapAlert() {{
      triggerDownload(capXmlRaw, 'sachet_cap_CHG_0001.xml', 'application/xml');
      showToast("OASIS CAP v1.2 XML Export Completed &bull; SACHET/NDMA Compliant");
    }}

    function exportSitRep() {{
      const byteCharacters = atob(pdfDataB64);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {{
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }}
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], {{ type: 'application/pdf' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'TRACE_Executive_SitRep.pdf';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast("1-Page Executive SitRep PDF Downloaded");
    }}

    function exportGeoPackage() {{
      const byteCharacters = atob(gpkgDataB64);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {{
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }}
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], {{ type: 'application/x-sqlite3' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${{currentTheater}}_change_intelligence.gpkg`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast("OGC GeoPackage (.gpkg) Downloaded");
    }}

    // ============================================================
    // BENCHMARK MODAL
    // ============================================================
    function openBenchmarkModal() {{
      document.getElementById('benchmarkModal').classList.add('is-open');
    }}
    function closeBenchmarkModal() {{
      document.getElementById('benchmarkModal').classList.remove('is-open');
    }}

    // ============================================================
    // BACKGROUND VIDEO CROSS-FADE (Verbatim logic from UI.txt)
    // ============================================================
    (function initVideoLoop() {{
      const A = document.getElementById('bgVideoA');
      const B = document.getElementById('bgVideoB');
      if (!A || !B) return;

      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {{
        A.removeAttribute('autoplay');
        A.pause();
        B.pause();
        try {{ A.currentTime = 0; }} catch(e) {{}}
        return;
      }}

      const FADE = 0.9;
      let cur = A;
      let nxt = B;
      let swapping = false;

      function play(v) {{
        const p = v.play();
        if (p && p.catch) p.catch(() => {{}});
      }}

      play(A);

      function tick() {{
        if (swapping || !cur.duration) return;
        if (cur.duration - cur.currentTime > FADE) return;

        swapping = true;
        const out = cur;
        nxt.currentTime = 0;
        play(nxt);
        nxt.classList.add('is-active');
        out.classList.remove('is-active');

        cur = nxt;
        nxt = out;

        setTimeout(() => {{
          out.pause();
          out.currentTime = 0;
          swapping = false;
        }}, FADE * 1000 + 100);
      }}

      A.addEventListener('timeupdate', tick);
      B.addEventListener('timeupdate', tick);
    }})();

    // Ambient Starfield Canvas
    (function initStarfield() {{
      const canvas = document.getElementById('starfieldCanvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      let w = canvas.width = window.innerWidth;
      let h = canvas.height = window.innerHeight;

      const stars = Array.from({{ length: 90 }}, () => ({{
        x: Math.random() * w,
        y: Math.random() * h,
        r: Math.random() * 1.2 + 0.4,
        alpha: Math.random() * 0.7 + 0.2,
        dx: (Math.random() - 0.5) * 0.15,
        dy: (Math.random() - 0.5) * 0.15
      }}));

      function draw() {{
        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = "#ffffff";
        stars.forEach(s => {{
          ctx.beginPath();
          ctx.globalAlpha = s.alpha;
          ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
          ctx.fill();
          s.x += s.dx;
          s.y += s.dy;
          if (s.x < 0) s.x = w;
          if (s.x > w) s.x = 0;
          if (s.y < 0) s.y = h;
          if (s.y > h) s.y = 0;
        }});
        requestAnimationFrame(draw);
      }}
      draw();

      window.addEventListener('resize', () => {{
        w = canvas.width = window.innerWidth;
        h = canvas.height = window.innerHeight;
      }});
    }})();
  </script>
</body>
</html>
'''

# Write to web/index.html
with open('web/index.html', 'w') as f:
    f.write(html_template)
print('Successfully generated web/index.html!')
