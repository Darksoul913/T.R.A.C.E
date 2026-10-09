"""Builds web/index.html: self-contained T.R.A.C.E. console (globe landing + change dashboard).

Run from anywhere:  python scripts/build_frontend_light.py
Everything (imagery, Earth texture, export files) is inlined so the page works offline.
"""
import base64
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def b64(rel):
    return base64.b64encode((ROOT / rel).read_bytes()).decode()


# web/scenes.json is produced by scripts/build_scenes.py (runs the real pipeline)
scenes = json.loads((ROOT / 'web/scenes.json').read_text(encoding='utf-8'))
severity = scenes.pop('_severity', None)   # type weights + priorities, to explain scores in the inspector
OUT = 'data/outputs/'

from src.exporters.cap_alert import EVENT_PROFILES

DATA = {
    'scenes': scenes,
    'severity': severity,
    'profiles': EVENT_PROFILES,
    'benchmark': json.loads((ROOT / OUT / 'benchmark_metrics.json').read_text(encoding='utf-8')),
    # src/models/stress_test.py; the chart is omitted when it hasn't been run
    'stress': json.loads((ROOT / OUT / 'stress_test.json').read_text(encoding='utf-8')) if (ROOT / OUT / 'stress_test.json').exists() else None,
    # NASA Blue Marble (public domain), equirectangular 2048x1024
    'earth': 'data:image/jpeg;base64,' + b64('web/assets/earth_equirect.jpg'),
    'files': {k: {'geojson': (ROOT / OUT / sc['files']['geojson']).read_text(encoding='utf-8'),
                  'gpkg': b64(OUT + sc['files']['gpkg']),
                  'sitrep': b64(OUT + sc['files']['sitrep'])} for k, sc in scenes.items()},
}

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>T.R.A.C.E. (Terrain Analysis & Change Evaluation) — Satellite Change Intelligence</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=block" rel="stylesheet">
<style>
/* ============ TOKENS — earth palette, light ============ */
:root{
  --u: min(calc(100vw / 1280), calc(100dvh / 760));
  --paper:#F2ECE1; --paper-2:#E7DFCF; --card:#FBF8F2; --card-2:#F5F0E6;
  --ink:#1E2620; --ink-2:#3B453C; --muted:#69705F; --faint:#9AA08F;
  --line:rgba(30,38,32,.11); --line-2:rgba(30,38,32,.2);
  --forest:#2F4A35; --forest-h:#253C2B; --moss:#5E7A3E; --ocean:#2D6A78; --clay:#B4612F; --sky:#DCE7E3;
  --crit:#A3382B; --high:#C46A2A; --mod:#B08A1E; --minor:#3A7C88; --fa:#7A4E7A; --unobs:#5F6670; --unobs-bg:rgba(214,217,220,.6);
  --unc:#4F5D8C; --heat:#FFC43D;
  --btn-ink:#F6F1E7;
  --glass-fill:rgba(251,248,242,.72); --glass-line:rgba(30,38,32,.14);
  --dx: 8.5; --dy: -40;
  --e-reveal: cubic-bezier(.16, 1, .3, 1);
  --e-soft:   cubic-bezier(.25, .8, .3, 1);
  --mono:'JetBrains Mono', ui-monospace, Menlo, monospace;
}
@supports not (height: 100dvh){ :root{ --u: min(calc(100vw / 1280), calc(100vh / 760)); } }

*{box-sizing:border-box}
html,body{height:100%;margin:0;padding:0;overflow:hidden}
body{
  font-family:'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;text-rendering:geometricPrecision;
  color:var(--ink);
  background:
    radial-gradient(90% 60% at 50% 100%, rgba(165,200,205,.35) 0%, transparent 70%),
    radial-gradient(120% 70% at 50% 0%, #F7F3EA 0%, transparent 60%),
    var(--paper);
}
button{font-family:inherit;color:inherit}
.mono{font-family:var(--mono)}
a:focus-visible,button:focus-visible,[tabindex]:focus-visible,input:focus-visible{outline:2px solid var(--ocean);outline-offset:3px;border-radius:99px}

/* ============ GLOBE + FLY LAYERS ============ */
#globe{position:fixed;inset:0;width:100vw;height:100dvh;z-index:1;pointer-events:none;display:block}
#flyTile{position:fixed;left:0;top:0;z-index:6;pointer-events:none;opacity:0;border-radius:2px;
  box-shadow:0 30px 80px rgba(30,38,32,.25);will-change:transform,width,height,opacity}
#flyLabel{position:fixed;left:0;top:0;z-index:6;pointer-events:none;opacity:0;white-space:nowrap;
  transform:translate(-50%,-100%);font-size:12px;font-weight:600;letter-spacing:.02em;color:var(--ink);
  background:var(--card);border:1px solid var(--line-2);border-radius:99px;padding:6px 12px;
  box-shadow:0 8px 24px rgba(30,38,32,.15)}
#flyLabel span{font-family:var(--mono);font-weight:500;color:var(--muted);margin-left:8px}

/* ============ HERO (UI.txt, earth light) ============ */
.hero{position:relative;width:100vw;height:100dvh;overflow:hidden;z-index:2;
  transition:opacity .55s ease, filter .55s ease}
@supports not (height: 100dvh){ .hero{height:100vh} }
.hero.leaving{opacity:0;filter:blur(6px);pointer-events:none}

.nav{position:absolute;top:0;left:0;right:0;height:calc(67 * var(--u));display:flex;align-items:center;
  padding-left:calc(24.5 * var(--u));padding-right:calc(50.7 * var(--u));z-index:3}
.logo{font-weight:800;font-size:calc(26 * var(--u));letter-spacing:calc(0.45 * var(--u));
  transform:translateY(calc(-2.4 * var(--u)));line-height:1;color:var(--ink);text-decoration:none;white-space:nowrap}
.logo b{color:var(--moss);font-weight:800}
.nav-links{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%) translateX(calc(-23 * var(--u)));
  display:flex;align-items:center;gap:calc(24.3 * var(--u));white-space:nowrap}
.nav-links a{color:var(--ink-2);text-decoration:none;font-size:calc(11.5 * var(--u));font-weight:500;
  letter-spacing:calc(-0.15 * var(--u));line-height:1;transition:color .18s ease;cursor:pointer}
.nav-links a:hover{color:var(--ink)}
.nav-actions{margin-left:auto;display:flex;align-items:center;gap:calc(6.8 * var(--u))}
.btn{display:inline-flex;align-items:center;justify-content:center;font-family:inherit;text-decoration:none;
  white-space:nowrap;border:0;cursor:pointer}
.btn-login{height:calc(28 * var(--u));padding:0 calc(12.9 * var(--u));border-radius:calc(14 * var(--u));
  background:var(--card);color:var(--ink-2);border:1px solid var(--line);font-size:calc(11.5 * var(--u));font-weight:500;
  letter-spacing:calc(-0.15 * var(--u));transition:background .18s ease,color .18s ease}
.btn-login:hover{background:#fff;color:var(--ink)}
.btn-nav-start{height:calc(28 * var(--u));padding-left:calc(13.5 * var(--u));padding-right:calc(14.5 * var(--u));
  border-radius:calc(14 * var(--u));background:var(--forest);color:var(--btn-ink);font-size:calc(11.1 * var(--u));
  font-weight:500;gap:calc(7 * var(--u));transition:background .18s ease}
.btn-nav-start:hover{background:var(--forest-h)}
.btn-nav-start .arw{width:calc(11.5 * var(--u));height:calc(9.6 * var(--u))}
.arw{flex:0 0 auto;display:block}
.burger{display:none;margin-left:auto;width:calc(40 * var(--u));height:calc(28 * var(--u));align-items:center;
  justify-content:center;background:var(--card);border:1px solid var(--line);border-radius:calc(14 * var(--u));cursor:pointer;padding:0}
.burger span{display:block;width:16px;height:1.5px;background:var(--ink);border-radius:2px;position:relative}
.burger span::before,.burger span::after{content:"";position:absolute;left:0;width:16px;height:1.5px;background:var(--ink);border-radius:2px}
.burger span::before{top:-5px} .burger span::after{top:5px}

.hero-inner{position:absolute;left:50%;top:50%;
  transform:translate(-50%,-50%) translate(calc(var(--dx) * var(--u)), calc(var(--dy) * var(--u)));
  width:max-content;text-align:center;z-index:2}
.ln,.ln-i{display:block} .ln-i{white-space:nowrap}
h1{margin:0;font-weight:500;font-size:calc(89 * var(--u));line-height:calc(90 * var(--u));
  letter-spacing:calc(-1 * var(--u));color:var(--ink)}
h1 .ln:nth-child(2) .ln-i{color:var(--forest)}
.sub{margin:calc(16.1 * var(--u)) 0 0;font-weight:300;font-size:calc(17.4 * var(--u));line-height:calc(27 * var(--u));
  letter-spacing:calc(-0.30 * var(--u));color:var(--ink-2)}
.ctas{margin-top:calc(21.8 * var(--u));display:flex;align-items:center;justify-content:center;
  transform:translateX(calc(-0.75 * var(--u)));gap:calc(7 * var(--u))}
.btn-lg{height:calc(39 * var(--u));border-radius:calc(19.5 * var(--u));font-size:calc(13.3 * var(--u));font-weight:500;
  letter-spacing:calc(-0.3 * var(--u));gap:calc(9 * var(--u))}
.btn-primary{background:var(--forest);color:var(--btn-ink);padding-left:calc(18.2 * var(--u));padding-right:calc(19.2 * var(--u));
  transition:background .18s ease,transform .18s ease}
.btn-primary:hover{background:var(--forest-h)}
.btn-ghost{background:var(--glass-fill);color:var(--ink-2);padding:0 calc(17.4 * var(--u));border:1px solid var(--glass-line);
  -webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px);transition:background .18s ease,border-color .18s ease}
.btn-ghost:hover{background:rgba(251,248,242,.95);border-color:var(--line-2)}
.btn-lg .arw{width:calc(13 * var(--u));height:calc(10.8 * var(--u))}
.meta{margin-top:calc(18 * var(--u));font-family:var(--mono);font-size:calc(10.5 * var(--u));color:var(--muted);letter-spacing:.02em}
.meta i{font-style:normal;color:var(--moss)}

.menu{display:none}
@keyframes menuIn{from{opacity:0;transform:translateY(-6px) scale(.985)}to{opacity:1;transform:none}}

@media (max-width:1160px){
  :root{ --u: min(max(0.9px, min(calc(100vw / 1280), calc(100dvh / 760))), calc((100vw - 72px) / 575), calc(100dvh / 620)); }
  .nav{height:max(58px, calc(67 * var(--u)));padding-left:max(24px, calc(28 * var(--u)));padding-right:max(24px, calc(28 * var(--u)))}
  .nav-links,.nav-actions{display:none}
  .burger{display:flex;width:max(46px, calc(48 * var(--u)));height:max(38px, calc(34 * var(--u)));border-radius:999px}
  .hero-inner{max-width:calc(100vw - 48px)}
  .sub{font-size:max(16px, calc(17.4 * var(--u)));line-height:max(25px, calc(27 * var(--u)))}
  .ctas{margin-top:max(26px, calc(21.8 * var(--u)));gap:max(10px, calc(7 * var(--u)))}
  .btn-lg{height:max(44px, calc(39 * var(--u)));border-radius:max(22px, calc(19.5 * var(--u)));font-size:max(15px, calc(13.3 * var(--u)));gap:max(10px, calc(9 * var(--u)))}
  .btn-primary{padding-left:max(21px, calc(18.2 * var(--u)));padding-right:max(22px, calc(19.2 * var(--u)))}
  .btn-ghost{padding-left:max(20px, calc(17.4 * var(--u)));padding-right:max(21px, calc(18.4 * var(--u)))}
  .btn-lg .arw{width:max(14px, calc(13 * var(--u)));height:max(11.6px, calc(10.8 * var(--u)))}
  .meta{font-size:max(11px, calc(10.5 * var(--u)))}
  .menu{position:absolute;top:calc(max(58px, calc(67 * var(--u))) - 6px);right:max(24px, calc(28 * var(--u)));
    width:min(320px, calc(100vw - 48px));background:rgba(251,248,242,.92);-webkit-backdrop-filter:blur(22px);backdrop-filter:blur(22px);
    border:1px solid var(--line);border-radius:20px;padding:10px 8px 12px;flex-direction:column;
    box-shadow:0 24px 60px rgba(30,38,32,.18);transform-origin:top right;z-index:5}
  .menu.open{display:flex;animation:menuIn .18s ease both}
  .menu a{color:var(--ink-2);text-decoration:none;font-size:15px;font-weight:500;padding:12px 14px;border-radius:12px;
    transition:background .18s ease,color .18s ease;cursor:pointer}
  .menu a:hover{background:rgba(30,38,32,.05);color:var(--ink)}
  .menu .divider{height:1px;background:var(--line);margin:8px 14px}
  .menu .m-start{display:flex;align-items:center;justify-content:center;gap:9px;background:var(--forest);color:var(--btn-ink);
    margin:6px 8px 0;padding:13px 16px;border-radius:14px;font-weight:600}
  .menu .m-start:hover{background:var(--forest-h);color:var(--btn-ink)}
  .menu .m-start .arw{width:13px;height:11px}
}
@media (max-width:552px){
  :root{--u:1px}
  .nav{height:56px;padding:0 20px}
  .logo{font-size:22px;letter-spacing:-.4px}
  .burger{width:42px;height:36px}
  .hero-inner{position:absolute;left:0;right:0;top:44%;width:auto;max-width:none;padding:0 20px;transform:translateY(-50%)}
  h1{font-size:min(68px, calc((100vw - 44px) / 8.4));line-height:1.04;letter-spacing:-.02em}
  .sub{margin-top:16px;font-size:clamp(15.5px, 4vw, 16.5px);line-height:1.6;letter-spacing:0;max-width:42ch;margin-left:auto;margin-right:auto}
  .sub br{display:none}
  .ctas{margin-top:24px;gap:10px;transform:none;flex-wrap:wrap}
  .btn-lg{height:46px;border-radius:23px;font-size:15px;gap:9px}
  .btn-primary{padding-left:20px;padding-right:21px}
  .btn-ghost{padding-left:19px;padding-right:20px}
  .btn-lg .arw{width:13px;height:11px}
  .meta{font-size:11px;margin-top:16px}
  .menu{top:50px;left:16px;right:16px;width:auto}
}
@media (max-width:353px){ .ctas{flex-direction:column;align-items:center} .btn-lg{width:min(100%,272px)} }
@media (max-width:552px) and (max-height:460px){
  h1{font-size:min(44px, calc((100vw - 44px) / 8.4))}
  .sub{margin-top:12px;font-size:15px;line-height:1.5}
  .ctas{margin-top:18px}
}

/* entrance */
html.anim .ln{overflow:hidden;padding-top:.26em;margin-top:-.26em}
html.anim .ln-i{transform:translateY(100%)}
html.anim .logo, html.anim .nav-links a, html.anim .nav-actions .btn,
html.anim .burger, html.anim .sub, html.anim .ctas .btn, html.anim .meta{opacity:0}
.ln-i,.logo,.nav-links a,.nav-actions .btn,.sub,.ctas .btn{will-change:transform,opacity}
@keyframes lineRise{from{transform:translateY(100%)}to{transform:translateY(0)}}
@keyframes subIn{from{opacity:0;transform:translateY(calc(14 * var(--u)));filter:blur(4px)}to{opacity:1;transform:none;filter:blur(0)}}
@keyframes subInFlat{from{opacity:0;transform:translateY(calc(12 * var(--u)))}to{opacity:1;transform:none}}
@keyframes pillIn{from{opacity:0;transform:translateY(calc(8 * var(--u))) scale(.972)}to{opacity:1;transform:none}}
@keyframes liftIn{from{opacity:0;transform:translateY(calc(9 * var(--u)))}to{opacity:1;transform:none}}
@keyframes logoIn{from{opacity:0;transform:translateY(calc(-2.4 * var(--u))) translateY(calc(9 * var(--u)))}
                  to{opacity:1;transform:translateY(calc(-2.4 * var(--u)))}}
html.anim.go .ln-i{animation:lineRise 1.05s var(--e-reveal) both}
html.anim.go .ln:nth-child(1) .ln-i{animation-delay:.12s}
html.anim.go .ln:nth-child(2) .ln-i{animation-delay:.22s}
html.anim.go .logo{animation:logoIn .62s var(--e-soft) .46s both}
html.anim.go .nav-links a{animation:liftIn .55s var(--e-soft) both}
html.anim.go .nav-links a:nth-child(1){animation-delay:.540s}
html.anim.go .nav-links a:nth-child(2){animation-delay:.585s}
html.anim.go .nav-links a:nth-child(3){animation-delay:.630s}
html.anim.go .sub{animation:subIn .85s var(--e-reveal) .58s both}
html.anim.go .meta{animation:liftIn .7s var(--e-soft) 1.0s both}
html.anim.go .btn-login{animation:pillIn .55s var(--e-soft) .68s both}
html.anim.go .burger{animation:pillIn .55s var(--e-soft) .68s both}
html.anim.go .btn-nav-start{animation:pillIn .55s var(--e-soft) .73s both}
html.anim.go .ctas .btn-primary{animation:pillIn .70s var(--e-reveal) .90s both}
html.anim.go .ctas .btn-ghost{animation:pillIn .70s var(--e-reveal) .97s both}
@media (max-width:552px){
  html.anim.go .sub{animation-name:subInFlat}
  html.anim.go .ln-i{animation-duration:.92s}
  html.anim.go .ctas .btn-primary{animation-delay:.84s}
  html.anim.go .ctas .btn-ghost{animation-delay:.90s}
}
@media (prefers-reduced-motion:reduce){
  html.anim .ln{overflow:visible;padding-top:0;margin-top:0}
  html.anim .ln-i{transform:none}
  html.anim .logo, html.anim .nav-links a, html.anim .nav-actions .btn,
  html.anim .burger, html.anim .sub, html.anim .ctas .btn, html.anim .meta{opacity:1}
  *{transition:none!important;animation:none!important}
}

/* ============ DASHBOARD ============ */
.dash{position:fixed;inset:0;z-index:3;background:var(--paper);display:grid;grid-template-rows:auto minmax(0,1fr);
  font-size:13px;opacity:0;visibility:hidden;transition:opacity .45s ease,visibility 0s linear .45s}
.dash.on{opacity:1;visibility:visible;transition:opacity .45s ease}
.dash .rise{opacity:0;transform:translateY(8px);transition:opacity .5s ease,transform .7s var(--e-reveal);
  transition-delay:calc(var(--d,0) * 55ms + 120ms)}
.dash.on .rise{opacity:1;transform:none}

.topbar{display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--card);border-bottom:1px solid var(--line);flex-wrap:wrap}
.tb-ctl{display:contents}
.tb-brand{display:flex;align-items:center;gap:8px;border:0;background:none;cursor:pointer;padding:6px 10px 6px 6px;border-radius:99px}
.tb-brand:hover{background:var(--card-2)}
.tb-brand svg{color:var(--forest)}
.tb-brand strong{font-weight:800;font-size:15px}
.tb-brand strong b{color:var(--moss)}
.tb-sep{width:1px;height:26px;background:var(--line)}
.tb-title{min-width:0;margin-right:auto}
.tb-title div:first-child{font-weight:700;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tb-title div:last-child{font-family:var(--mono);font-size:11px;color:var(--muted);white-space:nowrap}
.seg{display:inline-flex;background:var(--card-2);border:1px solid var(--line);border-radius:99px;padding:3px;gap:2px}
.seg button{border:0;background:none;padding:6px 12px;border-radius:99px;font-size:12px;font-weight:600;color:var(--muted);cursor:pointer;white-space:nowrap}
.seg button:hover{color:var(--ink)}
.seg button[aria-pressed="true"]{background:var(--card);color:var(--ink);box-shadow:0 1px 3px rgba(30,38,32,.14)}
.seg button[data-act="mode:naive"][aria-pressed="true"]{background:var(--fa);color:#fff}
.pill{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--card);border-radius:99px;
  padding:7px 13px;font-size:12px;font-weight:600;cursor:pointer;color:var(--ink-2);white-space:nowrap}
.pill:hover{background:#fff;color:var(--ink)}

.dbody{display:grid;grid-template-columns:290px minmax(0,1fr) 330px;grid-template-areas:"left center right";
  gap:12px;padding:12px;min-height:0}
.col{display:flex;flex-direction:column;gap:12px;min-height:0;overflow:auto;scrollbar-width:thin}
.col>.card{flex-shrink:0}   /* the column scrolls; cards keep their height */
.left>.tcard{flex-shrink:1}
.left{grid-area:left} .right{grid-area:right}
.center{grid-area:center;display:flex;flex-direction:column;gap:12px;min-height:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
.card-h h3{margin:0}
.city-pick{font:inherit;font-size:12px;font-weight:600;border:1px solid var(--line);background:var(--card-2);border-radius:99px;padding:7px 12px;color:var(--ink);max-width:180px}
.city-pick.on{background:var(--card);box-shadow:0 1px 3px rgba(30,38,32,.14)}
.seg-sm button{padding:4px 9px;font-size:10.5px;letter-spacing:0;text-transform:none}
.card h3,.card-h{margin:0 0 10px;font-size:13px;font-weight:700;letter-spacing:-.005em;color:var(--ink);
  display:flex;align-items:center;justify-content:space-between;gap:8px}
.card-h .mono{font-size:11px;font-weight:500;color:var(--muted)}

/* ---- semantic sets (#43 design principle): priority, uncertainty, workflow status; never colour alone ---- */
.tierm{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:700;color:var(--c)}
.tierm::before{content:"";width:9px;height:9px;background:var(--c);flex:none}
.tierm[data-t="Critical"]{--c:var(--crit)} .tierm[data-t="Critical"]::before{clip-path:polygon(50% 0,100% 100%,0 100%)}
.tierm[data-t="High"]{--c:var(--high)} .tierm[data-t="High"]::before{transform:rotate(45deg) scale(.82)}
.tierm[data-t="Medium"]{--c:var(--mod)} .tierm[data-t="Medium"]::before{border-radius:2px}
.tierm[data-t="Low"]{--c:var(--minor)} .tierm[data-t="Low"]::before{border-radius:50%}
.stm{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:600;color:var(--c,var(--muted));white-space:nowrap}
.stm i{font-style:normal;font-weight:700}
.stm[data-s="New"]{--c:var(--muted)} .stm[data-s="Under review"]{--c:var(--ocean)} .stm[data-s="Field verification"]{--c:var(--clay)}
.stm[data-s="Confirmed"],.stm[data-s="Reported"],.stm[data-s="Resolved"]{--c:var(--forest)} .stm[data-s="Dismissed"]{--c:var(--faint)}
.uncm{display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:600;color:var(--unc);white-space:nowrap}
.uncm::before{content:"?";display:grid;place-items:center;width:13px;height:13px;border:1.4px dashed var(--unc);border-radius:50%;font-size:9px;font-weight:800}

/* ---- mission figures (#41) ---- */
.mission{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}
.mfig{display:flex;flex-direction:column;align-items:flex-start;gap:1px;text-align:left;border:1px solid var(--line);background:var(--card);
  border-radius:12px;padding:9px 12px;cursor:pointer;min-width:0}
.mfig:hover{border-color:var(--line-2);background:#fff}
.mfig b{font-size:21px;font-weight:800;letter-spacing:-.02em;font-variant-numeric:tabular-nums;line-height:1.1;color:var(--c,var(--ink))}
.mfig span{font-size:11.5px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.mfig[aria-pressed="true"]{border-color:var(--forest);box-shadow:inset 0 0 0 1px var(--forest)}
.mfig.static{cursor:default}.mfig.static:hover{background:var(--card);border-color:var(--line)}

/* overview, shown where the globe lands */
.overview{position:absolute;z-index:8;left:14px;top:14px;bottom:14px;width:min(430px, calc(100% - 28px));overflow:auto;
  background:color-mix(in srgb, var(--card) 94%, transparent);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);
  border:1px solid var(--line-2);border-radius:18px;padding:22px 22px 18px;box-shadow:0 24px 60px rgba(30,38,32,.22);cursor:default;
  display:flex;flex-direction:column}
.overview[hidden]{display:none}
.ov-place{font-size:13px;font-weight:600;color:var(--ink-2)}
.ov-dates{font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:2px}
.ov-sit{margin:16px 0 14px;font-size:24px;line-height:1.22;font-weight:700;letter-spacing:-.015em;color:var(--ink);text-wrap:balance}
.ov-rows{list-style:none;margin:0;padding:0;border-top:1px solid var(--line)}
.ov-row{display:grid;grid-template-columns:76px 1fr auto;align-items:baseline;gap:10px;width:100%;border:0;border-bottom:1px solid var(--line);
  background:none;padding:11px 2px;text-align:left;cursor:pointer;font:inherit}
.ov-row:hover{background:color-mix(in srgb, var(--forest) 5%, transparent)}
.ov-row b{font-size:32px;font-weight:800;letter-spacing:-.03em;font-variant-numeric:tabular-nums;line-height:1;color:var(--c,var(--ink))}
.ov-row span{font-size:14px;font-weight:600;color:var(--ink)}
.ov-row small{display:block;font-size:11.5px;font-weight:500;color:var(--muted);margin-top:2px}
.ov-row em{font-style:normal;font-size:12px;font-weight:600;color:var(--ocean)}
.ov-row.static{cursor:default}.ov-row.static:hover{background:none}
.ov-acts{display:flex;gap:8px;margin-top:16px;flex-wrap:wrap}
.ov-acts .abtn{flex:1;min-width:150px;padding:11px 12px;font-size:13px}
.ov-area{margin-top:auto;padding-top:14px;display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted)}
.ov-area select{flex:1;min-width:0;font:inherit;font-size:12.5px;border:1px solid var(--line);background:var(--card-2);border-radius:8px;padding:6px 8px;color:var(--ink)}
html:not(.reduced) .overview.show .ov-row{animation:liftIn .5s var(--e-soft) both;animation-delay:calc(var(--d) * 70ms + 120ms)}
html:not(.reduced) .overview.show{animation:pillIn .45s var(--e-soft) both}

/* ---- attention views + case list (#46) ---- */
.views{display:flex;flex-direction:column;gap:1px;margin:0 -6px 10px}
.vbtn{display:flex;align-items:center;gap:8px;border:0;background:none;padding:8px 8px;border-radius:9px;font:inherit;font-size:13px;
  font-weight:600;color:var(--ink-2);cursor:pointer;text-align:left}
.vbtn:hover{background:var(--card-2);color:var(--ink)}
.vbtn[aria-pressed="true"]{background:color-mix(in srgb, var(--forest) 10%, transparent);color:var(--forest)}
.vbtn .n{margin-left:auto;font-family:var(--mono);font-size:11.5px;font-weight:500;color:var(--muted)}
.vbtn small{display:block;font-size:11px;font-weight:500;color:var(--muted)}
.vbtn:focus-visible{border-radius:9px}
.clist{list-style:none;margin:0 -6px;padding:0;overflow:auto;flex:1;min-height:0;scrollbar-width:thin}
.case{display:grid;grid-template-columns:1fr auto;gap:2px 8px;width:100%;border:0;border-top:1px solid var(--line);background:none;
  padding:9px 8px;text-align:left;font:inherit;cursor:pointer;color:var(--ink)}
.case:hover{background:var(--card-2)}
.case[aria-current="true"]{background:color-mix(in srgb, var(--forest) 9%, transparent);box-shadow:inset 3px 0 0 var(--forest)}
.case:focus-visible{border-radius:6px}
.case .ct{grid-column:1/-1;font-size:12.5px;font-weight:600;line-height:1.3}
.case .cm{font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.case .cr{display:flex;gap:8px;justify-content:flex-end;align-items:center}
.case .ch{display:flex;gap:8px;align-items:center;grid-column:1/-1}
.case.dim{opacity:.55}
.tcard{display:flex;flex-direction:column;min-height:240px;flex:1}
.tfoot{font-size:11px;color:var(--muted);padding-top:8px}
.empty{padding:18px 6px;color:var(--muted);text-align:center;font-size:12.5px;line-height:1.5}
.sevrow{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0 0 10px;font-size:12px;color:var(--muted)}

/* legend (map layers popover) */
.legend{display:flex;flex-direction:column;gap:2px}
.lg-row{display:flex;align-items:center;gap:10px;padding:6px 8px;border-radius:8px;cursor:pointer;user-select:none}
.lg-row:hover{background:var(--card-2)}
.lg-row input{margin:0;accent-color:var(--forest)}
.sw{width:12px;height:12px;border-radius:3px;background:color-mix(in srgb, var(--c) 35%, transparent);border:2px solid var(--c);flex:none}
.lg-row .n{margin-left:auto;font-family:var(--mono);font-size:11.5px;color:var(--muted)}
.lg-row.off{opacity:.45}
.lg-row.fa .sw{border-style:dashed}
.slider{display:flex;align-items:center;gap:10px;margin-top:10px;padding:0 8px;font-size:12px;color:var(--muted)}
.slider input{flex:1;accent-color:var(--forest)}

/* table */
.tcard{display:flex;flex-direction:column;min-height:240px;flex:1}
.search{width:100%;border:1px solid var(--line);background:var(--card-2);border-radius:9px;padding:8px 10px;font:inherit;font-size:12.5px;color:var(--ink);margin-bottom:8px}
.search:focus-visible{border-radius:9px}
.tscroll{overflow:auto;flex:1;min-height:0;margin:0 -6px;scrollbar-width:thin}
table{width:100%;border-collapse:collapse;font-size:12px}
th{position:sticky;top:0;background:var(--card);text-align:left;font-weight:600;color:var(--muted);font-size:11px;padding:0}
th button{border:0;background:none;padding:6px;font:inherit;color:inherit;cursor:pointer;width:100%;text-align:inherit}
th button:hover{color:var(--ink)}
th.num,td.num{text-align:right}
td{padding:7px 6px;border-top:1px solid var(--line);white-space:nowrap}
tbody tr{cursor:pointer}
tbody tr:hover td{background:var(--card-2)}
tbody tr[aria-selected="true"] td{background:color-mix(in srgb, var(--forest) 9%, transparent)}
td .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--c);margin-right:7px;vertical-align:1px}
.tfoot{font-size:11px;color:var(--muted);padding-top:8px}
.empty{padding:18px 6px;color:var(--muted);text-align:center}

/* map */
.map{position:relative;flex:1;min-height:320px;border-radius:14px;overflow:hidden;border:1px solid var(--line);touch-action:none;cursor:grab;
  background:var(--paper-2) radial-gradient(rgba(30,38,32,.09) 1px, transparent 1.2px) 0 0/14px 14px;user-select:none;-webkit-user-select:none}
.map.grabbing{cursor:grabbing}
.layer{position:absolute;inset:0;pointer-events:none}
.world{position:absolute;left:0;top:0;transform-origin:0 0}
.world img{display:block;width:100%;height:100%;-webkit-user-drag:none}
#layT2{transition:opacity .2s ease}
#pins{position:absolute;inset:0}
#vec{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.poly{fill:var(--c);fill-opacity:var(--fill,.35);stroke:var(--c);stroke-width:1.6;vector-effect:non-scaling-stroke;pointer-events:visiblePainted;cursor:pointer;transition:fill-opacity .15s}
.poly:hover,.poly.hl{fill-opacity:calc(var(--fill,.35) + .25)}
.poly.creep{stroke-dasharray:2 3;stroke-width:2.2;fill-opacity:calc(var(--fill,.35) * .6)}
.lg-row .sw.dot{border-style:dotted;border-width:2px}
.spark{display:block;width:100%;height:28px;overflow:visible}
.spark polyline{fill:none;stroke:var(--clay);stroke-width:1.6;vector-effect:non-scaling-stroke}
.spark-l{display:flex;justify-content:space-between;font:10px var(--mono);color:var(--muted);margin-top:2px}
.poly.sel{stroke-width:3;fill-opacity:calc(var(--fill,.35) + .2)}
.poly.sel.wide{fill-opacity:0}   /* a tile-spanning case: outline only, so its imagery stays readable */
.halo{fill:none;stroke:#fff;stroke-width:7;stroke-opacity:.9;vector-effect:non-scaling-stroke;pointer-events:none}
.unobs{fill:url(#hatch);stroke:var(--unobs);stroke-width:1.2;vector-effect:non-scaling-stroke;pointer-events:visiblePainted;cursor:help}
.lg-row .sw.hatch{background:repeating-linear-gradient(45deg, var(--unobs) 0 1.5px, var(--unobs-bg) 1.5px 4px);border-color:var(--unobs)}
.ref-poly{fill:rgba(99,102,241,.06);stroke:#6366f1;stroke-width:1.5;stroke-dasharray:4 3;vector-effect:non-scaling-stroke;pointer-events:none}
.lg-row .sw.outline{background:rgba(99,102,241,.12);border:1.5px dashed #6366f1}
.sev-hint{font-size:11px;color:var(--muted);padding:4px 2px 2px 2px;line-height:1.3}
.fa{fill:var(--fa);fill-opacity:.32;stroke:var(--fa);stroke-width:1.8;stroke-dasharray:5 4;vector-effect:non-scaling-stroke;pointer-events:visiblePainted;cursor:help}
.pin{position:absolute;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;border:2.5px solid var(--c);
  background:color-mix(in srgb, var(--c) 30%, #fff);box-shadow:0 0 0 2px rgba(255,255,255,.85),0 2px 6px rgba(0,0,0,.3);
  transform:scale(var(--inv,1));pointer-events:auto;cursor:pointer}
.pin.big{display:none}
.pin.sel{width:20px;height:20px;margin:-10px 0 0 -10px;background:var(--c)}
.pin.sel::after{content:"";position:absolute;inset:-8px;border-radius:50%;border:2px solid var(--c);animation:ping 1.6s ease-out infinite}
@keyframes ping{from{transform:scale(.6);opacity:1}to{transform:scale(1.5);opacity:0}}

.curtain{position:absolute;top:0;bottom:0;left:50%;width:0;z-index:4}
.curtain::before{content:"";position:absolute;top:0;bottom:0;left:-1px;width:2px;background:#fff;box-shadow:0 0 0 1px rgba(30,38,32,.25),0 0 12px rgba(0,0,0,.25)}
.knob{position:absolute;top:50%;left:0;transform:translate(-50%,-50%);width:36px;height:36px;border-radius:50%;background:var(--card);
  border:1px solid var(--line-2);box-shadow:0 4px 14px rgba(30,38,32,.25);display:grid;place-items:center;cursor:ew-resize;touch-action:none}
.knob:focus-visible{border-radius:50%}
.map[data-view="before"] .curtain,.map[data-view="after"] .curtain{display:none}
.map[data-view="before"] #layT2{opacity:0}

.ctl{position:absolute;z-index:5;display:flex;align-items:center;gap:6px;cursor:default}
.chip{background:rgba(251,248,242,.92);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);border:1px solid var(--line);border-radius:99px;
  padding:6px 11px;font-size:11.5px;font-weight:600;color:var(--ink-2);box-shadow:0 2px 8px rgba(30,38,32,.1);white-space:nowrap}
.chip .mono{font-weight:500;color:var(--muted);margin-left:5px}
.tl{top:10px;left:10px} .tr{top:10px;right:10px} .tc{top:10px;left:50%;transform:translateX(-50%)}
.bl{bottom:10px;left:10px;flex-direction:column;align-items:flex-start;gap:6px} .br{bottom:10px;right:10px;flex-direction:column}
.map[data-view="before"] .tr,.map[data-view="after"] .tl{display:none}
.tc .seg{background:rgba(251,248,242,.92);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);box-shadow:0 2px 8px rgba(30,38,32,.1)}
.zbtn{width:34px;height:34px;border-radius:10px;border:1px solid var(--line);background:rgba(251,248,242,.95);display:grid;place-items:center;
  cursor:pointer;box-shadow:0 2px 8px rgba(30,38,32,.1);font-size:17px;font-weight:600;color:var(--ink-2)}
.zbtn:hover{background:#fff;color:var(--ink)}
.zbtn:focus-visible{border-radius:10px}
.scalebar{display:flex;flex-direction:column;gap:3px}
.scalebar i{display:block;height:6px;border:2px solid var(--ink);border-top:0;background:rgba(251,248,242,.6)}
.scalebar span{font-family:var(--mono);font-size:10.5px;font-weight:600;text-shadow:0 0 3px #fff,0 0 3px #fff}
.coords{font-family:var(--mono);font-size:11px}
.hint{font-size:10.5px;color:var(--muted);font-weight:500}
.banner{position:absolute;z-index:5;top:54px;left:50%;transform:translateX(-50%);max-width:min(560px, calc(100% - 20px));
  background:var(--fa);color:#fff;border-radius:10px;padding:9px 13px;font-size:12px;line-height:1.45;box-shadow:0 8px 24px rgba(60,30,60,.25);display:none}
.map.naive .banner{display:block}
.tip{position:absolute;z-index:7;pointer-events:none;background:var(--ink);color:var(--card);font-size:11.5px;padding:6px 9px;border-radius:7px;
  white-space:nowrap;opacity:0;transform:translate(12px,12px);transition:opacity .1s}
.tip.on{opacity:1}
.tip b{font-family:var(--mono);font-weight:600}

/* ---- Change-to-Action Card (#43) ---- */
.stepper{display:flex;gap:4px;align-items:center}
.stepper span{font-family:var(--mono);font-size:11px;color:var(--muted);margin-right:4px;white-space:nowrap}
.ibtn{width:30px;height:30px;border-radius:9px;border:1px solid var(--line);background:var(--card-2);display:grid;place-items:center;cursor:pointer;color:var(--ink-2)}
.ibtn:hover{background:#fff;color:var(--ink)}
.ibtn:focus-visible{border-radius:9px}
.tag{display:inline-flex;align-items:center;gap:6px;border-radius:99px;padding:4px 10px;font-size:11.5px;font-weight:700;
  background:color-mix(in srgb, var(--c) 14%, transparent);color:var(--c)}
.cac{padding:0;overflow:hidden}
.cac-h{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;padding:14px 14px 10px}
.cac-id{font-family:var(--mono);font-size:12px;color:var(--muted)}
.cac-what{margin:3px 0 7px;font-size:17px;line-height:1.25;font-weight:700;letter-spacing:-.01em;text-wrap:balance}
.cac-badges{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center}
.q{padding:11px 14px 12px;border-top:1px solid var(--line)}
.q h3{margin:0 0 6px;font-size:12px;font-weight:700;color:var(--muted)}
.q p{margin:0;font-size:13px;line-height:1.5;color:var(--ink)}
.q ul{list-style:none;margin:6px 0 0;padding:0;display:grid;gap:4px}
.q li{font-size:12.5px;line-height:1.45;color:var(--ink-2);padding-left:14px;position:relative}
.q li::before{content:"";position:absolute;left:3px;top:.6em;width:4px;height:4px;border-radius:50%;background:var(--faint)}
.q li.flag{color:var(--crit)} .q li.flag::before{background:var(--crit);border-radius:1px;transform:rotate(45deg)}
.rel{display:grid;grid-template-columns:76px 1fr;gap:7px 10px;margin:2px 0 0}
.rel dt{font-size:11.5px;color:var(--muted);padding:1px 0 0;border:0}
.rel dd{margin:0;padding:0;border:0;font-size:12.5px;line-height:1.45;font-weight:500;text-align:left;color:var(--ink-2)}
.meter{position:relative;height:6px;border-radius:3px;background:var(--line);margin:5px 0 2px;max-width:220px}
.meter i{position:absolute;left:0;top:0;bottom:0;border-radius:3px;background:var(--c,var(--forest))}
.meter b{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--ink);border-radius:1px}
.callout{margin-top:9px;padding:8px 10px;border-radius:9px;border:1.4px dashed var(--unc);color:var(--unc);font-size:12px;line-height:1.45;font-weight:500}
.next>p{font-weight:600}
.acting{display:flex;align-items:center;gap:6px;margin:10px 0 8px;font-size:11.5px;color:var(--muted);flex-wrap:wrap}
.acting select,.acting input{font:inherit;font-size:12px;border:1px solid var(--line);background:var(--card-2);border-radius:8px;padding:5px 7px;color:var(--ink);min-width:0}
.acting input{flex:1;min-width:90px}
.acts{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.acts .abtn{white-space:normal;line-height:1.25;min-height:38px}
.abtn[disabled]{opacity:.42;cursor:not-allowed}
.abtn[disabled]:hover{background:var(--card-2);color:var(--ink-2);border-color:var(--line)}
.acts .wide{grid-column:1/-1}
.hint2{font-size:11.5px;color:var(--muted);margin:6px 0 0;line-height:1.45}
.assign{display:none;grid-template-columns:1fr auto;gap:6px;margin-top:6px}
.assign.on{display:grid}
.assign select,.assign input{font:inherit;font-size:12px;border:1px solid var(--line);background:var(--card-2);border-radius:8px;padding:7px 8px;color:var(--ink);min-width:0}
.note{width:100%;margin-top:6px;border:1px solid var(--line);background:var(--card-2);border-radius:9px;padding:8px 10px;font:inherit;font-size:12.5px;color:var(--ink)}
.note:focus-visible{border-radius:9px}
.hist{list-style:none;margin:10px 0 0;padding:0;display:grid;gap:6px;font-size:11.5px;color:var(--ink-2)}
.q .hist li{display:grid;grid-template-columns:auto 1fr;gap:2px 8px;padding-left:0;font-size:11.5px}
.q .hist li::before{display:none}
.hist time{font-family:var(--mono);color:var(--faint);font-size:10.5px;padding-top:1px}
.hist .ph{display:flex;gap:4px;grid-column:2;margin-top:3px}
.hist .ph img{width:46px;height:46px;object-fit:cover;border-radius:6px;border:1px solid var(--line);cursor:zoom-in}
.case-foot{display:flex;justify-content:space-between;gap:8px;margin-top:8px;font-size:10.5px;color:var(--faint);flex-wrap:wrap}
.lnk{border:0;background:none;padding:0;font:inherit;font-size:11.5px;color:var(--ocean);cursor:pointer;text-decoration:underline;text-underline-offset:2px}
.field{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:6px}
.field .abtn{text-decoration:none}
.outbox{margin-top:8px;font-size:11.5px;color:var(--ink-2);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.outbox b{color:var(--clay)}
details.more{border-top:1px solid var(--line)}
details.more summary{padding:11px 14px;font-size:12.5px;font-weight:600;color:var(--ocean);cursor:pointer;list-style:none}
details.more summary::-webkit-details-marker{display:none}
details.more summary::before{content:"+";display:inline-block;width:14px;font-weight:700}
details.more[open] summary::before{content:"\2212"}
.more-b{padding:0 14px 14px}
.more-b h4{margin:12px 0 4px;font-size:11.5px;font-weight:700;color:var(--muted)}
dl.kv{margin:0;display:grid;grid-template-columns:auto 1fr;gap:0}
dl.kv dt,dl.kv dd{padding:6px 0;border-top:1px solid var(--line);font-size:12px}
dl.kv dt{color:var(--muted);padding-right:12px}
dl.kv dd{margin:0;text-align:right;font-weight:600;min-width:0;overflow-wrap:anywhere}
dl.kv dd.mono{font-weight:500;font-size:11.5px}
.spark{display:block;width:100%;height:28px;overflow:visible}
.spark polyline{fill:none;stroke:var(--clay);stroke-width:1.6;vector-effect:non-scaling-stroke}
.spark-l{display:flex;justify-content:space-between;font:10px var(--mono);color:var(--muted);margin-top:2px}

/* ---- copilot (#45) ---- */
.ask .chips{display:flex;flex-wrap:wrap;gap:6px}
.chipq{border:1px solid var(--line);background:var(--card-2);border-radius:99px;padding:6px 10px;font:inherit;font-size:12px;font-weight:600;color:var(--ink-2);cursor:pointer;text-align:left}
.chipq:hover{background:#fff;color:var(--ink);border-color:var(--line-2)}
.askf{display:flex;gap:6px;margin-top:8px}
.askf input{flex:1;min-width:0;border:1px solid var(--line);background:var(--card-2);border-radius:9px;padding:8px 10px;font:inherit;font-size:12.5px;color:var(--ink)}
.askf input:focus-visible{border-radius:9px}
.answer{margin-top:10px;display:grid;gap:8px}
.answer[hidden]{display:none}
.ans-q{font-size:12.5px;font-weight:700}
.ans-g h4{margin:0 0 3px;font-size:11.5px;font-weight:700;color:var(--forest)}
.ans-g.hyp h4{color:var(--unc)}
.ans-g ul{list-style:none;margin:0;padding:0;display:grid;gap:4px}
.ans-g li{font-size:12.5px;line-height:1.45;color:var(--ink-2);padding-left:10px;border-left:2px solid color-mix(in srgb, var(--forest) 40%, transparent)}
.ans-g.hyp li{border-left:2px dashed color-mix(in srgb, var(--unc) 60%, transparent)}
.ans-src{font-size:11px;color:var(--muted)}

/* ---- map: layers popover, changed pixels, spotlight ---- */
.lay-pop{position:absolute;z-index:9;right:54px;bottom:10px;width:256px;max-height:calc(100% - 20px);overflow:auto;background:var(--card);
  border:1px solid var(--line-2);border-radius:14px;padding:12px;box-shadow:0 16px 40px rgba(30,38,32,.22);cursor:default}
.lay-pop[hidden]{display:none}
.lay-pop h3{margin:0 0 6px;font-size:12.5px}
#spot{fill:rgba(24,30,26,.42);pointer-events:none}
#heatImg{pointer-events:none}
.lg-row .sw.heat{background:linear-gradient(90deg, rgba(255,196,61,.5), rgba(255,246,200,.95));border-color:var(--heat)}

/* ---- time travel (#47) ---- */
.tt{padding:10px 14px 12px}
.tt[hidden]{display:none}
.tt-h{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.tt-h h3{margin:0}
.tt-h .sub2{font-size:11.5px;color:var(--muted)}
.tt-h .sub2 b{color:var(--ink);font-weight:700}
.tt-h .abtn{margin-left:auto;padding:6px 11px}
.tt-ticks{display:flex;gap:3px;margin-top:9px;overflow-x:auto;scrollbar-width:thin;padding-bottom:2px}
.tick{flex:1 0 auto;min-width:46px;border:1px solid var(--line);background:var(--card-2);border-radius:8px;padding:5px 6px 4px;font:inherit;
  font-size:11.5px;font-weight:600;color:var(--ink-2);cursor:pointer;text-align:center;line-height:1.15}
.tick small{display:block;font-size:9.5px;font-weight:500;color:var(--muted);font-family:var(--mono)}
.tick:hover{background:#fff}
.tick:focus-visible{border-radius:8px}
.tick[aria-pressed="true"]{background:var(--forest);border-color:var(--forest);color:var(--btn-ink)}
.tick[aria-pressed="true"] small{color:color-mix(in srgb, var(--btn-ink) 75%, transparent)}
.tick.pair{box-shadow:inset 0 -2px 0 var(--ocean)}
.tick.first{box-shadow:inset 0 -2px 0 var(--clay)}
.tt-spark{display:block;width:100%;height:46px;margin-top:8px;overflow:visible}
.tt-note{margin:4px 0 0;font-size:12px;color:var(--ink-2);line-height:1.45}
.tt-leg{display:flex;gap:12px;flex-wrap:wrap;font-size:10.5px;color:var(--muted);margin-top:4px}
.tt-leg i{display:inline-block;width:10px;height:3px;vertical-align:2px;margin-right:4px;background:var(--c)}

/* ---- impact tracker (#48) ---- */
.imp-figs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:12px 0}
.imp-figs div{border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.imp-figs b{display:block;font-size:24px;font-weight:800;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.imp-figs span{font-size:11.5px;color:var(--muted)}
.imp-trend{display:block;width:100%;height:56px;margin:4px 0 2px}
.imp-trend rect{fill:var(--forest)}
@media (max-width:560px){.imp-figs{grid-template-columns:1fr 1fr}}

.adv{background:linear-gradient(0deg, color-mix(in srgb, var(--clay) 7%, var(--card)), var(--card))}
.adv p{margin:0;font-size:13px;line-height:1.6;color:var(--ink-2)}
.lookup{display:flex;gap:6px;margin-top:12px}
.lookup[hidden]{display:none}
.lookup .search{margin:0}
.lookup .abtn{flex:none}
.lk-out{margin-top:8px;padding:9px 11px;border-radius:9px;border-left:3px solid var(--c, var(--line));background:var(--card-2);font-size:12.5px;line-height:1.55}
.exports{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.exports .abtn{justify-content:flex-start}
.exports .abtn small{margin-left:auto;font-family:var(--mono);font-weight:500;color:var(--faint);font-size:10.5px}

/* modal + toast */
dialog{border:0;padding:0;border-radius:18px;background:var(--card);color:var(--ink);width:min(680px, calc(100vw - 32px));
  max-height:calc(100dvh - 32px);overflow:auto;box-shadow:0 40px 100px rgba(30,38,32,.35)}
dialog::backdrop{background:rgba(30,38,32,.35);-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px)}
.dlg{padding:22px 24px 24px}
.dlg h2{margin:0;font-size:18px;font-weight:700;letter-spacing:-.01em}
.dlg p{font-size:13px;line-height:1.55;color:var(--ink-2)}
.dlg table{font-size:13px;margin:6px 0 14px}
.dlg th{position:static;background:none;padding:8px 6px;font-size:11px;text-transform:uppercase;letter-spacing:.06em}
.dlg td{padding:9px 6px}
.dlg .win{color:var(--forest);font-weight:700}
.dlg .lose{color:var(--crit)}
.stress-h{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:20px}
.stress-h h3{margin:0;font-size:14px;font-weight:700}
.sleg{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--muted);margin:10px 0 6px}
.sleg i,.sbar i{display:inline-block;background:var(--c)}
.sleg i{width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.srow{display:grid;grid-template-columns:118px 1fr;gap:4px 10px;align-items:center;padding:6px 0;border-top:1px solid var(--line);font-size:12px}
.srow b{font-weight:600}
.sbars{display:grid;gap:3px}
.sbar{display:grid;grid-template-columns:1fr 52px;gap:6px;align-items:center}
.sbar span{height:8px;background:var(--card-2);border-radius:4px;overflow:hidden}
.sbar i{height:100%;border-radius:4px}
.sbar em{font-style:normal;font-family:var(--mono);font-size:11px;text-align:right;color:var(--ink-2)}
@media (max-width:520px){.srow{grid-template-columns:1fr}}
.fine{font-size:11.5px;color:var(--muted);margin:14px 0 0}
.dlg-h{display:flex;justify-content:space-between;align-items:center;gap:12px}
.note{background:color-mix(in srgb, var(--moss) 10%, var(--card));border:1px solid color-mix(in srgb, var(--moss) 30%, transparent);border-radius:10px;padding:11px 13px;font-size:12.5px;line-height:1.55}
.toast{position:fixed;left:50%;bottom:22px;z-index:20;transform:translate(-50%,20px);opacity:0;pointer-events:none;background:var(--ink);color:var(--card);
  padding:10px 16px;border-radius:99px;font-size:12.5px;font-weight:500;box-shadow:0 12px 30px rgba(30,38,32,.3);transition:opacity .2s, transform .25s var(--e-soft)}
.toast.on{opacity:1;transform:translate(-50%,0)}

@media (max-width:1180px){
  .dbody{grid-template-columns:270px minmax(0,1fr);grid-template-areas:"left center" "right right"}
  .right{flex-direction:row;flex-wrap:wrap;overflow:visible;align-items:flex-start}
  .right>.card{flex:1 1 340px}
  .dash{overflow:auto}
  .dbody{min-height:100%}
  .center{min-height:620px}
  .mission{grid-template-columns:repeat(3,minmax(0,1fr))}
}
/* phones: field verification mode (#31) - map, then the card, then the list; big touch targets */
@media (max-width:820px){
  .dash{overflow:auto;display:block}
  .dbody{display:flex;flex-direction:column;padding:10px 16px 24px}
  .col{overflow:visible}
  .center{min-height:0;order:-1}
  .right{order:0;flex-direction:column}
  .right>.card{flex:none;width:100%}
  .left{order:1}
  .map{flex:none;height:52vh;min-height:300px}
  .mission{grid-template-columns:repeat(2,minmax(0,1fr))}
  .mission .mfig:last-child{grid-column:1/-1}
  .clist{max-height:none;overflow:visible}
  .tcard{min-height:0}
  .topbar{gap:6px 8px;padding:8px 12px}
  .tb-sep{display:none}
  .tb-title{flex:1;min-width:0}
  .tb-ctl{display:flex;gap:6px;flex-basis:100%;overflow-x:auto;scrollbar-width:none;padding-bottom:2px}
  .tb-ctl>*{flex:none}
  .tb-ctl .analyst{display:none}
  .hint{display:none}
  .tl .mono,.tr .mono{display:none}
  .overview{left:8px;right:8px;top:8px;bottom:8px;width:auto;padding:18px 16px}
  .ov-sit{font-size:21px}
  .ov-row b{font-size:28px}
  .acts .abtn,.field .abtn,.vbtn,.case{min-height:44px}
  .lay-pop{right:50px;width:min(256px, calc(100% - 64px))}
}
@media (max-width:520px){ .map .tl,.map .tr{display:none} }
</style>

<script>
/* A) entrance — arms synchronously */
(function(){
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var d=document.documentElement, done=false, cleaned=false, bootT, safeT;
  d.classList.add('anim');
  function clean(){ if(cleaned) return; cleaned=true; clearTimeout(safeT); document.removeEventListener('animationend', onEnd, true); d.classList.remove('anim','go'); }
  function onEnd(e){ if(e.animationName==='pillIn' && e.target.classList.contains('btn-ghost')) clean(); }
  function start(){ if(done) return; done=true; clearTimeout(bootT); document.addEventListener('animationend', onEnd, true); safeT=setTimeout(clean, 2600); d.classList.add('go'); }
  function boot(){ bootT=setTimeout(start, 900); if(document.fonts && document.fonts.ready) document.fonts.ready.then(start, start); else start(); }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
</script>
</head>

<body>
<canvas id="globe" aria-hidden="true"></canvas>
<img id="flyTile" alt="" aria-hidden="true">
<div id="flyLabel" aria-hidden="true"></div>

<!-- ======================= LANDING ======================= -->
<main class="hero" id="hero">
  <header class="nav">
    <a class="logo" href="#" data-act="noop" title="T.R.A.C.E. (Terrain Analysis & Change Evaluation)">T.R.A.<b>C.E.</b></a>
    <nav class="nav-links" aria-label="Primary" id="navLinks"></nav>
    <div class="nav-actions">
      <button class="btn btn-login" data-act="bench" id="navF1"></button>
      <button class="btn btn-nav-start" data-act="fly:first">Open console
        <svg class="arw" viewBox="0 0 12 10" fill="none" aria-hidden="true"><path d="M0.8 5h10M7.1 1.4 10.9 5l-3.8 3.6" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
    </div>
    <button class="burger" id="burger" aria-label="Open menu" aria-expanded="false" aria-controls="menu"><span></span></button>
  </header>
  <nav class="menu" id="menu" aria-label="Mobile">
    <div id="menuLinks" style="display:contents"></div>
    <div class="divider"></div>
    <a class="m-start" data-act="fly:first">Open console
      <svg class="arw" viewBox="0 0 12 10" fill="none" aria-hidden="true"><path d="M0.8 5h10M7.1 1.4 10.9 5l-3.8 3.6" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </a>
  </nav>

  <div class="hero-inner">
    <h1><span class="ln"><span class="ln-i">Change, mapped</span></span><span class="ln"><span class="ln-i">from orbit</span></span></h1>
    <p class="sub">Two satellite passes in, GIS-ready change polygons out. <br>False alarms filtered, area measured in square metres, <br>severity scored and alert drafts ready for the district cell.</p>
    <div class="ctas" id="ctas"></div>
    <div class="meta" id="heroMeta"></div>
  </div>
</main>

<!-- ======================= DASHBOARD ======================= -->
<div class="dash" id="dash" aria-label="Change intelligence console">
  <header class="topbar">
    <button class="tb-brand" data-act="back" title="Back to globe">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9.5"/><path d="M2.5 12h19M12 2.5c2.6 2.7 3.9 5.9 3.9 9.5s-1.3 6.8-3.9 9.5c-2.6-2.7-3.9-5.9-3.9-9.5S9.4 5.2 12 2.5z"/></svg>
      <strong>T.R.A.<b>C.E.</b></strong>
    </button>
    <span class="tb-sep"></span>
    <div class="tb-title"><div id="tbTitle"></div><div id="tbCoords"></div></div>
    <div class="tb-ctl">
      <div class="seg" role="group" aria-label="Sector" id="sectorSeg"></div>
      <select class="city-pick" id="cityPick" aria-label="More OSCD cities" hidden></select>
      <div class="seg analyst" role="group" aria-label="Detection engine">
        <button data-act="mode:ai">T.R.A.C.E. AI</button><button data-act="mode:naive">Naive NDVI</button>
      </div>
      <button class="pill" data-act="overview">Overview</button>
      <button class="pill" data-act="impact">Team progress</button>
      <button class="pill analyst" data-act="bench">Benchmark</button>
    </div>
  </header>

  <div class="dbody">
    <aside class="col left">
      <section class="card tcard rise" style="--d:1" aria-label="Cases">
        <div class="card-h"><h3 style="margin:0">Cases</h3><span class="mono" id="tCount"></span></div>
        <div class="sevrow"><span>Rank for</span><div class="seg seg-sm" role="group" aria-label="Priority mode" id="sevSeg"></div></div>
        <div class="views" id="views" role="group" aria-label="Case views"></div>
        <input class="search" id="search" type="search" placeholder="Search ID, type or place" aria-label="Search cases">
        <ol class="clist" id="clist" aria-label="Case list"></ol>
      </section>
    </aside>

    <section class="center">
      <div class="mission" id="mission" aria-label="Situation"></div>
      <div class="map" id="map" data-view="swipe">
        <div class="layer" id="layT1"><div class="world"><img id="imgT1" alt="Before imagery" draggable="false"></div></div>
        <div class="layer" id="layT2"><div class="world"><img id="imgT2" alt="After imagery" draggable="false"></div></div>
        <div class="layer"><div class="world" id="vecWorld"><svg id="vec" viewBox="0 0 100 100" preserveAspectRatio="none"><defs><pattern id="hatch" width="1.4" height="1.4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="1.4" height="1.4" fill="var(--unobs-bg)"/><line x1="0" y1="0" x2="0" y2="1.4" stroke="var(--unobs)" stroke-width=".45"/></pattern><clipPath id="selClip" clipPathUnits="userSpaceOnUse"><polygon id="selClipP" points=""/></clipPath></defs><g id="unL"></g><g id="refL"></g><g id="faL"></g><path id="spot" fill-rule="evenodd" d=""/><g id="ftL"></g><image id="heatImg" x="0" y="0" width="100" height="100" preserveAspectRatio="none" clip-path="url(#selClip)"/></svg><div id="pins"></div></div></div>
        <div class="curtain" id="curtain"><div class="knob ctl" id="knob" role="slider" tabindex="0" aria-label="Before / after divider" aria-valuemin="0" aria-valuemax="100" aria-valuenow="50">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m9 6-6 6 6 6M15 6l6 6-6 6"/></svg></div></div>
        <div class="ctl tl"><span class="chip">Before<span class="mono" id="d1"></span></span></div>
        <div class="ctl tr"><span class="chip">After<span class="mono" id="d2"></span></span></div>
        <div class="ctl tc" style="display:flex;align-items:center;gap:8px">
          <div class="seg" role="group" aria-label="Imagery view">
            <button data-act="view:before">Before</button><button data-act="view:swipe">Swipe</button><button data-act="view:after">After</button>
          </div>
          <div class="seg" style="display:flex;align-items:center;gap:6px;padding:3px 10px;background:var(--card);border:1px solid var(--line);border-radius:100px;font-size:11px;font-weight:600;box-shadow:0 2px 6px rgba(0,0,0,.06)">
            <span style="color:var(--muted);white-space:nowrap">Fill</span>
            <input type="range" id="fillDirect" min="0" max="100" value="35" aria-label="Polygon fill opacity" style="width:70px;cursor:pointer">
            <span class="mono" id="fillVal" style="font-size:10px;min-width:24px;color:var(--ink)">35%</span>
          </div>
        </div>
        <div class="banner" id="banner"></div>
        <div class="ctl bl">
          <div class="scalebar"><i id="sbBar"></i><span id="sbTxt"></span></div>
          <span class="chip coords" id="coords">Hover for coordinates</span>
          <span class="hint">Scroll to zoom · drag to pan · ←/→ next case · F fit</span>
        </div>
        <div class="ctl br">
          <button class="zbtn" data-act="layers" aria-label="Map layers" aria-expanded="false" aria-controls="layPop" title="Map layers">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m12 3 9 5-9 5-9-5 9-5z"/><path d="m3 13 9 5 9-5"/></svg></button>
          <button class="zbtn" data-act="zoom:in" aria-label="Zoom in">+</button>
          <button class="zbtn" data-act="zoom:out" aria-label="Zoom out">−</button>
          <button class="zbtn" data-act="zoom:fit" aria-label="Fit to tile">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg></button>
        </div>
        <div class="lay-pop ctl" id="layPop" hidden>
          <h3>Map layers</h3>
          <div class="legend" id="legend"></div>
          <label class="slider" style="display:flex;align-items:center;justify-content:space-between;margin-top:6px"><span>Fill opacity: <b id="fillPopVal" class="mono">35%</b></span><input type="range" id="fill" min="0" max="100" value="35" aria-label="Polygon fill opacity" style="width:85px"></label>
        </div>
        <div class="tip" id="tip"></div>
        <section class="overview ctl" id="overview" hidden aria-labelledby="ovSit"></section>
      </div>
      <section class="card tt" id="tt" hidden aria-label="Time travel"></section>
    </section>

    <aside class="col right">
      <section class="card cac rise" style="--d:2" id="cac" aria-label="Selected case"></section>
      <section class="card ask rise" style="--d:3" aria-labelledby="askH">
        <h3 id="askH">Explain this change</h3>
        <div class="chips" id="askChips"></div>
        <form class="askf" id="askForm" autocomplete="off">
          <input id="askIn" type="text" placeholder="Ask about this case" aria-label="Ask about this case" maxlength="300">
          <button class="abtn" type="submit">Ask</button>
        </form>
        <div class="answer" id="answer" role="status" aria-live="polite" hidden></div>
      </section>
      <section class="card adv rise" style="--d:4">
        <div class="card-h"><span id="advTitle"></span>
          <div class="seg" role="group" aria-label="Advisory language"><button data-act="lang:en">EN</button><button data-act="lang:mr">मराठी</button><button data-act="lang:hi">हिंदी</button></div>
        </div>
        <p id="advBody"></p>
        <form class="lookup" id="lookup" autocomplete="off">
          <input class="search" id="lkIn" type="search" list="lkList" aria-label="Look up a pincode or area">
          <button class="abtn" type="submit" id="lkBtn"></button>
        </form>
        <datalist id="lkList"></datalist>
        <div class="lk-out" id="lkOut" role="status" aria-live="polite" hidden></div>
      </section>
      <section class="card rise" style="--d:5">
        <h3>Exports</h3>
        <div class="exports">
          <button class="abtn" data-act="dl:geojson">GeoJSON<small>.geojson</small></button>
          <button class="abtn" data-act="dl:gpkg">GeoPackage<small>.gpkg</small></button>
          <button class="abtn" data-act="dl:cap">CAP alert<small id="capId"></small></button>
          <button class="abtn" data-act="dl:sitrep">SitRep<small>.pdf</small></button>
          <button class="abtn" data-act="dl:csv">Case list<small>.csv</small></button>
          <button class="abtn" data-act="dl:audit">Decision history<small>.json</small></button>
          <button class="abtn" data-act="dl:verdicts">Officer verdicts<small>.json</small></button>
          <button class="abtn" data-act="dl:pack">Field pack<small>.json</small></button>
          <button class="abtn" data-act="pack-import" style="grid-column:1/-1">Import a field pack</button>
        </div>
      </section>
    </aside>
  </div>
</div>
<input type="file" id="photoIn" accept="image/*" capture="environment" hidden>
<input type="file" id="packIn" accept=".json,application/json" hidden>

<dialog id="impact" aria-labelledby="impactH">
  <div class="dlg">
    <div class="dlg-h"><h2 id="impactH">Team progress</h2><button class="ibtn" data-act="impact-close" aria-label="Close">✕</button></div>
    <p>Decisions and site visits recorded in the case history, across every area. These are process measures: they count work done, not damage prevented.</p>
    <div class="seg" role="group" aria-label="Period" id="impPeriod"><button data-act="imp:7">Last 7 days</button><button data-act="imp:30">Last 30 days</button><button data-act="imp:all">All time</button></div>
    <div class="imp-figs" id="impFigs"></div>
    <div id="impTrend"></div>
    <div class="stress-h"><h3>Oldest open cases</h3></div>
    <table><thead><tr><th>Case</th><th>Area · zone</th><th>Team</th><th>Status</th><th class="num">Days open</th></tr></thead><tbody id="impOld"></tbody></table>
    <div class="stress-h"><h3>By zone and team</h3></div>
    <table><thead><tr><th>Zone or team</th><th class="num">Open</th><th class="num">Closed</th><th class="num">Median days open</th></tr></thead><tbody id="impBy"></tbody></table>
    <div class="exports" style="margin-top:14px"><button class="abtn" data-act="dl:impact">Export for administrators<small>.csv</small></button></div>
  </div>
</dialog>

<dialog id="bench" aria-labelledby="benchH">
  <div class="dlg">
    <div class="dlg-h"><h2 id="benchH">LEVIR-CD benchmark</h2><button class="ibtn" data-act="bench-close" aria-label="Close">✕</button></div>
    <p id="benchP"></p>
    <table><thead><tr><th>Metric</th><th class="num">Naive spectral</th><th class="num">T.R.A.C.E. AI</th><th class="num">Change</th></tr></thead><tbody id="benchRows"></tbody></table>
    <div class="note" id="benchNote"></div>
    <section id="stress" hidden>
      <div class="stress-h"><h3>Robustness stress test</h3>
        <div class="seg" role="group" aria-label="Stress metric"><button data-act="stress:f1_score" aria-pressed="true">F1</button><button data-act="stress:false_alarm_rate" aria-pressed="false">False alarms</button></div></div>
      <p id="stressP"></p>
      <div class="sleg" id="stressLeg"></div>
      <div id="stressRows"></div>
      <div class="note" id="stressNote"></div>
    </section>
    <section id="bObj" hidden><div class="stress-h"><h3>Missed changes: object recall by size</h3></div>
      <p id="bObjP"></p><table><thead><tr><th>Object size</th><th class="num">Objects</th><th class="num">T.R.A.C.E.</th><th class="num">Naive</th></tr></thead><tbody id="bObjRows"></tbody></table></section>
    <section id="bCreep" hidden><div class="stress-h"><h3>Slow change: consecutive vs anchored comparison</h3></div>
      <p id="bCreepP"></p><div class="sleg" id="bCreepLeg"></div><div id="bCreepRows"></div><div class="note" id="bCreepNote"></div></section>
    <section id="bFar" hidden><div class="stress-h"><h3>False alarms per 100 km² of unchanged land</h3></div>
      <p id="bFarP"></p><table><thead><tr><th>Dataset</th><th class="num">T.R.A.C.E.</th><th class="num">Naive NDVI</th><th class="num">Index rules</th></tr></thead><tbody id="bFarRows"></tbody></table>
      <div class="note" id="bFarNote"></div></section>
    <section id="bEvent" hidden><div class="stress-h"><h3>Disaster event validation vs Copernicus EMS</h3></div>
      <p id="bEventP"></p><table><thead><tr><th>Event</th><th class="num">Scope</th><th class="num">T.R.A.C.E. F1</th><th class="num">Naive NDVI</th><th class="num">Track B (urban)</th></tr></thead><tbody id="bEventRows"></tbody></table>
      <div class="note" id="bEventNote"></div></section>
    <section id="bTrackB" hidden><div class="stress-h"><h3>Track B: Sentinel-2 urban change (leave-one-city-out)</h3></div>
      <p id="bTrackBP"></p><table><thead><tr><th>Evaluation fold</th><th class="num">F1-score</th><th class="num">Precision</th><th class="num">Recall</th><th class="num">Threshold</th></tr></thead><tbody id="bTrackBRows"></tbody></table>
      <div class="note" id="bTrackBNote"></div></section>
    <p class="fine" id="bRun"></p>
  </div>
</dialog>
<div class="toast" id="toast" role="status" aria-live="polite"></div>

<script>/*__CASELOGIC__*/</script>
<script>
/* ============================================================
   DATA + CONSTANTS
   ============================================================ */
const D = /*__DATA__*/null;
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
const TIERS = ['Critical','High','Medium','Low'];
const TIER_VAR = {Critical:'var(--crit)', High:'var(--high)', Medium:'var(--mod)', Low:'var(--minor)'};
// Severity mode (Ideation Baseline §5.3): every polygon carries a tier per mode; switching re-ranks in place
const SEV_MODES = {encroachment:'Encroachment', disaster:'Disaster'};
function applySev(){
  Object.values(D.scenes).forEach(sc => sc.features.concat(sc.creep ? sc.creep.features : []).forEach(f => {
    f.tier = f.tiers[S.sev]; f.score = f.scores[S.sev]; f.priority = D.severity.priority[f.tier]; }));
}
const tierRank = t => 3 - TIERS.indexOf(t);
const KEYS = Object.keys(D.scenes);
// OSCD benchmark cities (scripts/build_scenes.py OSCD_PLACES) are labelled "<City> · OSCD"
const FEATURED = KEYS.filter(k => !/· OSCD$/.test(D.scenes[k].label)), MORE = KEYS.filter(k => !FEATURED.includes(k));
const city = k => D.scenes[k].nav || D.scenes[k].place.split(',')[0];
const SHORT = {'Water / Flood Inundation':'Flood / water','Vegetation Loss / Clearing':'Vegetation loss','Vegetation Regrowth':'Vegetation regrowth',
  'New Building / Structure':'New structure','New Built-up Surface':'New built-up','Vegetation Cleared / Possible Construction':'Cleared / build?','Ground Disturbance':'Ground disturbance',
  'Water-body Encroachment':'Water-body encr.','Burn Scar':'Burn scar','Seasonal Vegetation Change':'Seasonal veg.',
  'Slow Built-up Creep':'Slow creep','Precursor: Cleared Plot':'Cleared plot','Precursor: New Track':'New track'};
// Advisory = template x selected detection. Only the phrasing is hand-written.
const TYPE_I18N = {
  'Water / Flood Inundation':{en:'flood inundation', mr:'पूर / जलसाठा', hi:'जल भराव / बाढ़'},
  'Vegetation Loss / Clearing':{en:'vegetation clearing', mr:'वनस्पती तोड', hi:'वनस्पति कटाई'},
  'Vegetation Regrowth':{en:'vegetation regrowth', mr:'वनस्पती वाढ', hi:'वनस्पति वृद्धि'},
  'New Building / Structure':{en:'new construction', mr:'नवीन बांधकाम', hi:'नया निर्माण'},
  'New Built-up Surface':{en:'new built-up surface', mr:'नवीन बांधकाम क्षेत्र', hi:'नया निर्मित क्षेत्र'},
  'Vegetation Cleared / Possible Construction':{en:'vegetation clearing, possibly construction', mr:'वनस्पती तोड, संभाव्य बांधकाम', hi:'वनस्पति कटाई, संभावित निर्माण'},
  'Ground Disturbance':{en:'ground disturbance', mr:'जमिनीतील बदल', hi:'भूमि में बदलाव'},
  'Water-body Encroachment':{en:'encroachment on a water body', mr:'जलसाठ्यावर अतिक्रमण', hi:'जल निकाय पर अतिक्रमण'},
  'Burn Scar':{en:'burnt area', mr:'जळालेले क्षेत्र', hi:'जला हुआ क्षेत्र'},
  'Slow Built-up Creep':{en:'slow, year-on-year construction', mr:'हळूहळू वाढणारे बांधकाम', hi:'धीरे-धीरे बढ़ता निर्माण'},
  'Precursor: Cleared Plot':{en:'a newly cleared plot', mr:'नव्याने साफ केलेला भूखंड', hi:'नया साफ़ किया गया भूखंड'},
  'Precursor: New Track':{en:'a new access track', mr:'नवीन कच्चा रस्ता', hi:'नया कच्चा रास्ता'},
  'Seasonal Vegetation Change':{en:'seasonal vegetation change', mr:'हंगामी वनस्पती बदल', hi:'मौसमी वनस्पति बदलाव'},
};
const ADV = {
  en:{title:'Civic advisory', body:(f, t, a, p) => `Advisory: ${t} of ${a} m² detected near ${p} (${f.id}, ${f.tier.toLowerCase()} severity). `,
      urgent:'Residents of low-lying areas should stay alert; a field team is being dispatched.', routine:'Scheduled for municipal survey review.'},
  mr:{title:'नागरिक सुरक्षा इशारा', body:(f, t, a, p) => `सूचना: ${p} जवळ ${a} चौ.मी. क्षेत्रात ${t} उपग्रहाद्वारे नोंदवले गेले (${f.id}). `,
      urgent:'सखल भागातील नागरिकांनी सतर्क राहावे; पाहणी पथक रवाना होत आहे.', routine:'महापालिका सर्वेक्षणात तपासणी केली जाईल.'},
  hi:{title:'नागरिक सुरक्षा चेतावनी', body:(f, t, a, p) => `सूचना: ${p} के पास ${a} वर्ग मीटर क्षेत्र में ${t} उपग्रह द्वारा दर्ज किया गया (${f.id})। `,
      urgent:'निचले इलाकों के नागरिक सतर्क रहें; जाँच दल रवाना किया जा रहा है।', routine:'नगर निगम सर्वेक्षण में इसकी जाँच की जाएगी।'},
};
// Citizen lookup: pincode / area -> nearest detection, from the OSM place list built per sector
const TIER_I18N = {Critical:{en:'Critical', mr:'अतिगंभीर', hi:'अति गंभीर'}, High:{en:'High', mr:'गंभीर', hi:'गंभीर'},
  Medium:{en:'Medium', mr:'मध्यम', hi:'मध्यम'}, Low:{en:'Low', mr:'किरकोळ', hi:'मामूली'}};
const LK = {
  en:{ph:'Pincode or area, e.g. ', btn:'Check', unit:['m','km'],
      near:(p, d, f, t, tier) => `${tier} severity: ${t} detected ${d} from ${p} (${f.id}). Shown on the map.`,
      far:(p, d) => `No detected change within 1 km of ${p}. The nearest detection is ${d} away.`,
      none:q => `“${q}” isn't in this sector's pincode or area list.`, off:'Area lookup needs a georeferenced sector.',
      noneVerified:'No officer-verified changes in this sector yet: changes appear here only after field confirmation.',
      pending:n => ` ${n} unverified detection${n === 1 ? '' : 's'} within 1 km ${n === 1 ? 'is' : 'are'} awaiting field checks and not shown.`},
  mr:{ph:'पिनकोड किंवा परिसर, उदा. ', btn:'तपासा', unit:['मी.','किमी'],
      near:(p, d, f, t, tier) => `${p} पासून ${d} अंतरावर ${t} आढळले (${f.id}, तीव्रता: ${tier}). नकाशावर दाखवले आहे.`,
      far:(p, d) => `${p} पासून 1 किमी परिसरात कोणताही बदल आढळला नाही. सर्वात जवळचा बदल ${d} अंतरावर आहे.`,
      none:q => `“${q}” हे या क्षेत्राच्या पिनकोड / परिसर यादीत नाही.`, off:'परिसर शोधासाठी भू-संदर्भित क्षेत्र आवश्यक आहे.',
      noneVerified:'या क्षेत्रात अद्याप अधिकाऱ्यांनी पडताळलेला कोणताही बदल नाही; प्रत्यक्ष पडताळणीनंतरच बदल येथे दिसतात.',
      pending:n => ` 1 किमी परिसरातील ${n} अपुष्ट बदल पडताळणीच्या प्रतीक्षेत आहेत आणि दाखवलेले नाहीत.`},
  hi:{ph:'पिनकोड या इलाका, जैसे ', btn:'जाँचें', unit:['मी','किमी'],
      near:(p, d, f, t, tier) => `${p} से ${d} की दूरी पर ${t} दर्ज किया गया (${f.id}, गंभीरता: ${tier})। नक्शे पर दिखाया गया है।`,
      far:(p, d) => `${p} के 1 किमी के दायरे में कोई बदलाव दर्ज नहीं हुआ। सबसे नज़दीकी बदलाव ${d} दूर है।`,
      none:q => `“${q}” इस क्षेत्र की पिनकोड / इलाका सूची में नहीं है।`, off:'इलाका खोज के लिए भू-संदर्भित क्षेत्र आवश्यक है।',
      noneVerified:'इस क्षेत्र में अभी तक कोई अधिकारी-सत्यापित बदलाव नहीं है; ज़मीनी पुष्टि के बाद ही बदलाव यहाँ दिखते हैं।',
      pending:n => ` 1 किमी के भीतर ${n} अपुष्ट बदलाव जाँच की प्रतीक्षा में हैं और दिखाए नहीं गए हैं।`},
};
const NEAR_M = 1000;
const haversine = (a, b, c, d) => { const r = Math.PI/180, x = Math.sin((c-a)*r/2)**2 + Math.cos(a*r)*Math.cos(c*r)*Math.sin((d-b)*r/2)**2;
  return 2 * 6371000 * Math.asin(Math.sqrt(x)); };
const B = D.benchmark, AI = B.changeintel_ai_engine, NV = B.naive_spectral_baseline;
const pct = v => (v*100).toFixed(1) + '%';
const fmt = (v, d=0) => v.toLocaleString('en-US', {maximumFractionDigits:d});
const clamp = (v, a=0, b=1) => Math.min(b, Math.max(a, v));
const ease = t => t<.5 ? 4*t*t*t : 1 - Math.pow(-2*t+2, 3)/2;
const latLon = (b, x, y) => [b.n - y/100*(b.n-b.s), b.w + x/100*(b.e-b.w)];   // cursor readout only
const fLat = v => `${Math.abs(v).toFixed(5)}° ${v>=0?'N':'S'}`;
const fLon = v => `${Math.abs(v).toFixed(5)}° ${v>=0?'E':'W'}`;

const store = {
  get: (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
};
const ROLES = ['Analyst','Field officer','DDMA'];
const PROFILE = store.get('ci-profile', null) || {role: (() => { try { return localStorage.getItem('ci-role') || 'Analyst'; } catch (e) { return 'Analyst'; } })(), name: ''};
if (!ROLES.includes(PROFILE.role)) PROFILE.role = 'Analyst';
const S = {th:KEYS[0], sev:'encroachment', sel:0, mode:'ai', lang:'en', view:'swipe', hidden:new Set(), hideRef:false, q:'',
  av:'matters', stage:'hero', tt:null, spot:true, heat:true, seen:new Set()};
const sc = () => D.scenes[S.th];
// creep & precursor polygons (multi-year series) join the case list when their layer is on
const creepFeats = () => (sc().creep && !S.hideCreep) ? sc().creep.features : [];
const feats = () => sc().features.concat(creepFeats());
const FA = () => sc().naive.false_alarms;

/* Officer case workflow (#13, #44). The decision history is the single source of truth: a case's status is the
   "to" of its last entry, its assignee the last assignment. Entries are append-only (undo appends a reversal),
   carry a uid so phones and the analyst desk can merge them (#31 sync), and stay in this browser until synced. */
const CASE_STATES = ['New','Under review','Field verification','Confirmed','Reported','Resolved','Dismissed'];
const VERIFIED = CaseLogic.VERIFIED;
const OPENING = ['New','Under review','Field verification'];
const ACTIONS = {   // #44: the four decisions, then the DDMA steps that follow a confirmation
  confirm: {label:r => r === 'Field officer' ? 'Confirmed on site' : 'Confirm change', to:'Confirmed', from:OPENING, roles:['Analyst','Field officer'], tone:'good', done:'confirmed'},
  dismiss: {label:r => r === 'Field officer' ? 'Not found on site' : 'Mark as false alarm', to:'Dismissed', from:OPENING, roles:['Analyst','Field officer'], tone:'bad', done:'marked as a false alarm'},
  inspect: {label:() => 'Request field inspection', to:'Field verification', from:['New','Under review'], roles:['Analyst','DDMA'], done:'sent for field inspection'},
  assign:  {label:() => 'Assign case', from:['New','Under review','Field verification','Confirmed','Reported'], roles:['Analyst','DDMA'], done:'assigned'},
  report:  {label:() => 'Report to DDMA', to:'Reported', from:['Confirmed'], roles:['DDMA'], done:'reported to the DDMA'},
  resolve: {label:() => 'Mark resolved', to:'Resolved', from:['Reported'], roles:['DDMA'], done:'resolved'},
  reopen:  {label:() => 'Reopen case', to:'Under review', from:['Dismissed','Resolved'], roles:['Analyst','DDMA'], done:'reopened'},
};
const newId = () => (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2));
let audit = store.get('ci-audit', []);
audit.forEach(e => { e.uid = e.uid || newId(); e.action = e.action || `${e.from} to ${e.to}`; });
const saveAudit = () => store.set('ci-audit', audit);
const caseLog = (f, th = S.th) => audit.filter(e => e.sector === th && e.case === f.id);
const caseState = (f, th) => { const l = caseLog(f, th); return l.length ? l[l.length - 1].to : 'New'; };
const assigneeOf = (f, th) => { const a = caseLog(f, th).filter(e => 'assignee' in e).pop(); return a ? a.assignee : null; };
const actorName = () => PROFILE.name.trim() || PROFILE.role;
function record(f, fields){
  const st = caseState(f);
  const e = {uid:newId(), ts:new Date().toISOString(), sector:S.th, case:f.id, from:st, to:st, role:PROFILE.role, actor:actorName(), ...fields};
  audit.push(e); saveAudit(); Sync.soon();
  return e;
}
// designations, not people: Mumbai's BMC wards around Chembur-Ghatkopar, a generic team elsewhere
const ROSTER = th => /^mumbai/.test(th)
  ? ['Ward officer, L ward (Kurla)', 'Ward officer, M/East ward (Govandi–Mankhurd)', 'Ward officer, M/West ward (Chembur)', 'Ward officer, N ward (Ghatkopar)', 'DDMA field team, Mumbai Suburban']
  : D.scenes[th].event ? ['District control room', 'Field team 1', 'Field team 2', 'SDRF liaison'] : ['Field team 1', 'Field team 2', 'Planning office'];
let rosterExtra = store.get('ci-roster', []);

/* Site photos (#31) live in IndexedDB: localStorage is too small. Offline-first: nothing here needs a network. */
const PhotoDB = (() => {
  let dbp = null;
  const open = () => dbp || (dbp = new Promise((res, rej) => {
    const r = indexedDB.open('trace-field', 1);
    r.onupgradeneeded = () => r.result.createObjectStore('photos', {keyPath:'id'});
    r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
  }));
  const run = (mode, fn) => open().then(db => new Promise((res, rej) => {
    const t = db.transaction('photos', mode), req = fn(t.objectStore('photos'));
    t.oncomplete = () => res(req && req.result); t.onerror = () => rej(t.error);
  }));
  return {put:p => run('readwrite', s => s.put(p)), get:id => run('readonly', s => s.get(id)), all:() => run('readonly', s => s.getAll())};
})();
const photoCache = new Map();
async function photoURL(id){
  if (photoCache.has(id)) return photoCache.get(id);
  let p = null;
  try { p = await PhotoDB.get(id); } catch (e) {}
  if (!p && Sync.server) { try { const r = await fetch(`api/field/photo/${encodeURIComponent(id)}`); if (r.ok) { p = await r.json(); PhotoDB.put(p).catch(() => {}); } } catch (e) {} }
  const url = p ? p.data : null; photoCache.set(id, url); return url;
}
function downsize(file, max = 1280){
  return new Promise((res, rej) => {
    const img = new Image(), url = URL.createObjectURL(file);
    img.onload = () => {
      const k = Math.min(1, max / Math.max(img.width, img.height)), c = document.createElement('canvas');
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height); URL.revokeObjectURL(url);
      res(c.toDataURL('image/jpeg', 0.72));
    };
    img.onerror = () => { URL.revokeObjectURL(url); rej(new Error('not an image')); };
    img.src = url;
  });
}

/* Sync (#31): when the console is served by src/server/app.py and online, the outbox goes to /api/field/sync
   and everyone else's entries come back. Opened as a file or offline, the outbox waits; a field pack (.json)
   carries it by hand. */
const Sync = {
  server:false, synced:new Set(store.get('ci-synced', [])), t:null,
  pending(){ return audit.filter(e => !this.synced.has(e.uid)); },
  merge(entries){
    const have = new Set(audit.map(e => e.uid)); let n = 0;
    entries.forEach(e => { if (e && e.uid && !have.has(e.uid) && e.case && e.to) { audit.push(e); n++; } });
    if (n) { audit.sort((a, b) => a.ts.localeCompare(b.ts)); saveAudit(); }
    return n;
  },
  soon(){ clearTimeout(this.t); this.t = setTimeout(() => this.push(), 800); renderOutbox(); },
  async push(){
    if (!this.server || !navigator.onLine) { renderOutbox(); return false; }
    try {
      const photos = (await PhotoDB.all().catch(() => [])).filter(p => !this.synced.has(p.id));
      const sent = this.pending();
      const r = await fetch('api/field/sync', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({entries:sent, photos})});
      if (!r.ok) throw new Error(r.status);
      const j = await r.json();
      sent.forEach(e => this.synced.add(e.uid)); photos.forEach(p => this.synced.add(p.id));
      const got = this.merge(j.entries); j.entries.forEach(e => this.synced.add(e.uid));
      store.set('ci-synced', [...this.synced]);
      if (got && S.stage === 'dash') { renderCases(); renderMission(); renderMap(); renderCard(); toast(`Synced: ${got} new decision${got === 1 ? '' : 's'} from the team`); }
      renderOutbox(); return true;
    } catch (e) { renderOutbox(); return false; }
  },
  async probe(){
    if (!location.protocol.startsWith('http')) return;
    try { const r = await fetch('api/health'); this.server = r.ok; } catch (e) { this.server = false; }
    if (this.server) { this.push(); setInterval(() => this.push(), 30000); }
  },
};
addEventListener('online', () => Sync.push());
addEventListener('offline', () => renderOutbox());

function toast(msg){
  const t = $('#toast'); t.textContent = msg; t.classList.add('on');
  clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove('on'), 2600);
}

/* ============================================================
   GLOBE — WebGL orthographic sphere, NASA Blue Marble texture
   ============================================================ */
const Globe = (() => {
  const cv = $('#globe');
  const gl = cv.getContext('webgl', {alpha:true, premultipliedAlpha:true, antialias:false});
  const api = {ok:!!gl, ready:false, spin:true, lon:20, ring:0, pose:null, tgt:{lat:0, lon:0}};
  api.heroPose = lon => {
    const W = innerWidth, H = innerHeight, R = Math.max(W*0.56, 520);
    return {cx:W/2, cy:H*0.745 + R, R, lat:-24, lon};
  };
  api.show = on => { cv.style.display = on ? 'block' : 'none'; api.visible = on; };
  if (!gl) { cv.style.display = 'none'; return api; }
  api.visible = true;

  const vs = 'attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}';
  const fs = `precision highp float;
    uniform sampler2D T; uniform vec2 C; uniform float R, LON, LAT, RING, DPR; uniform vec3 TG;
    const float PI=3.14159265;
    void main(){
      vec2 p=(gl_FragCoord.xy-C)/R; float r=length(p);
      if(r>1.){ float d=(r-1.)*R/DPR; float a=.55*exp(-d/max(R/DPR*.05,1.)); gl_FragColor=vec4(vec3(.64,.79,.84)*a,a); return; }
      float z=sqrt(1.-r*r); vec3 n=vec3(p,z);
      float c=cos(LAT), s=sin(LAT);
      vec3 q=vec3(n.x, n.y*c+n.z*s, -n.y*s+n.z*c);
      float lat=asin(clamp(q.y,-1.,1.)), lon=atan(q.x,q.z)+LON;
      vec3 col=texture2D(T, vec2(fract(lon/(2.*PI)+.5), .5-lat/PI)).rgb;
      col=mix(col, vec3(dot(col,vec3(.3,.59,.11))), .08)*1.04;
      col*=.62+.45*max(dot(n,normalize(vec3(-.35,.45,.82))),0.);
      col=mix(col, vec3(.82,.89,.89), pow(1.-z,2.2)*.65);
      float dpx=acos(clamp(dot(q,TG),-1.,1.))*R/DPR;
      float ring=RING*clamp(smoothstep(2.2,.6,abs(dpx-15.))+smoothstep(5.,3.5,dpx),0.,1.);
      col=mix(col, vec3(.98,.95,.88), ring);
      float a=clamp((1.-r)*R,0.,1.);
      gl_FragColor=vec4(col*a,a);
    }`;
  const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; };
  const pr = gl.createProgram();
  gl.attachShader(pr, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(pr);
  if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) { api.ok = false; cv.style.display = 'none'; return api; }
  gl.useProgram(pr);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(pr, 'p'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const U = {}; ['T','C','R','LON','LAT','RING','DPR','TG'].forEach(k => U[k] = gl.getUniformLocation(pr, k));

  const img = new Image();
  img.onload = () => {
    gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, img);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    api.ready = true;
  };
  img.src = D.earth;

  const rad = d => d*Math.PI/180;
  function draw(p){
    const dpr = Math.min(devicePixelRatio || 1, 2), W = innerWidth, H = innerHeight;
    if (cv.width !== Math.round(W*dpr) || cv.height !== Math.round(H*dpr)) { cv.width = Math.round(W*dpr); cv.height = Math.round(H*dpr); }
    gl.viewport(0, 0, cv.width, cv.height);
    gl.clearColor(0,0,0,0); gl.clear(gl.COLOR_BUFFER_BIT);
    const dl = rad(api.tgt.lon - p.lon), tl = rad(api.tgt.lat);
    gl.uniform1i(U.T, 0);
    gl.uniform2f(U.C, p.cx*dpr, (H - p.cy)*dpr);
    gl.uniform1f(U.R, p.R*dpr); gl.uniform1f(U.LON, rad(p.lon)); gl.uniform1f(U.LAT, rad(p.lat));
    gl.uniform1f(U.RING, api.ring); gl.uniform1f(U.DPR, dpr);
    gl.uniform3f(U.TG, Math.cos(tl)*Math.sin(dl), Math.sin(tl), Math.cos(tl)*Math.cos(dl));
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }
  let last = performance.now();
  (function frame(now){
    requestAnimationFrame(frame);
    const dt = Math.min((now - last)/1000, .1); last = now;
    if (!api.ready || !api.visible) return;
    if (api.spin) { if (!REDUCED) api.lon = (api.lon + dt*3.2) % 360; api.pose = api.heroPose(api.lon); }
    if (api.pose) draw(api.pose);
  })(last);
  return api;
})();

/* ============================================================
   CINEMATIC FLY: hero globe → sector framed → zoom into tile
   ============================================================ */
const FLY = {frame:1.3, gap:0.2, zoom:2.0};
FLY.total = FLY.frame + FLY.gap + FLY.zoom;
const lerp = (a, b, t) => a + (b - a)*t;
function lerpPose(a, b, t){
  const dl = ((b.lon - a.lon) % 360 + 540) % 360 - 180;
  return {cx:lerp(a.cx,b.cx,t), cy:lerp(a.cy,b.cy,t), R:Math.exp(lerp(Math.log(a.R), Math.log(b.R), t)), lat:lerp(a.lat,b.lat,t), lon:a.lon + dl*t};
}
let flying = false;

async function fly(th, dir){
  if (flying) return; flying = true;
  const hero = $('#hero'), dash = $('#dash'), tile = $('#flyTile'), label = $('#flyLabel'), cv = $('#globe');
  $('#menu').classList.remove('open');
  if (dir > 0) await loadTheater(th); else fitView(false);
  const g = sc(), b = g.bounds, tgt = {lat:(b.n+b.s)/2, lon:(b.e+b.w)/2};

  const finishIn = () => {
    dash.classList.add('on'); S.stage = 'dash';
    showOverview(false);  // default view does not overlap overview over tile
    setTimeout(() => { tile.style.opacity = 0; Globe.show(false); cv.style.filter = ''; cv.style.opacity = ''; }, 460);
    flying = false;
  };
  if (REDUCED || !Globe.ok) {
    if (dir > 0) { hero.classList.add('leaving'); finishIn(); }
    else { dash.classList.remove('on'); hero.classList.remove('leaving'); Globe.show(true); Globe.spin = true; S.stage = 'hero'; flying = false; }
    return;
  }

  const W = innerWidth, H = innerHeight, m = $('#map').getBoundingClientRect();
  const wr = {x:m.left + V.x, y:m.top + V.y, w:V.iw*V.s, h:V.ih*V.s};
  const dlat = (b.n - b.s)*Math.PI/180, aspect = V.iw/V.ih;
  const P0 = Globe.heroPose(dir > 0 ? Globe.lon : tgt.lon);
  const P1 = {cx:W/2, cy:H/2, R:Math.min(W, H)*0.34, lat:tgt.lat, lon:tgt.lon};
  const P2 = {cx:wr.x + wr.w/2, cy:wr.y + wr.h/2, R:wr.h/dlat, lat:tgt.lat, lon:tgt.lon};
  const pose = t => t <= FLY.frame + FLY.gap ? lerpPose(P0, P1, ease(clamp(t/FLY.frame)))
                                             : lerpPose(P1, P2, ease(clamp((t - FLY.frame - FLY.gap)/FLY.zoom)));

  Globe.spin = false; Globe.tgt = tgt; Globe.show(true);
  tile.src = g.images.t2;
  label.innerHTML = `${g.place}<span>${tgt.lat.toFixed(2)}°, ${tgt.lon.toFixed(2)}°</span>`;
  if (dir > 0) hero.classList.add('leaving'); else { dash.classList.remove('on'); S.stage = 'hero'; }

  const t0 = performance.now();
  await new Promise(done => requestAnimationFrame(function step(now){
    const k = clamp((now - t0)/1000/FLY.total), t = (dir > 0 ? k : 1 - k)*FLY.total, p = pose(t);
    Globe.pose = p;
    const ring = clamp((t - .7)/.4) * (1 - clamp((t - 1.9)/.5));
    Globe.ring = ring;
    label.style.opacity = ring; label.style.transform = `translate(${p.cx}px, ${p.cy - 26}px) translate(-50%,-100%)`;
    const th_ = p.R*dlat, tw = th_*aspect;
    tile.style.width = tw + 'px'; tile.style.height = th_ + 'px';
    tile.style.transform = `translate(${p.cx - tw/2}px, ${p.cy - th_/2}px)`;
    tile.style.opacity = clamp((th_ - H*0.04)/(H*0.25));
    const texel = p.R*2*Math.PI/2048;
    cv.style.filter = texel > 2.5 ? `blur(${Math.min((texel - 2.5)/8, 4).toFixed(2)}px)` : '';
    cv.style.opacity = 1 - 0.75*clamp((th_ - H*0.12)/(H*0.5));
    if (dir < 0 && t < 1.1) hero.classList.remove('leaving');
    if (k < 1) requestAnimationFrame(step); else done();
  }));

  if (dir > 0) finishIn();
  else { tile.style.opacity = 0; Globe.ring = 0; Globe.lon = tgt.lon; Globe.spin = true; cv.style.filter = ''; cv.style.opacity = ''; flying = false; }
}

/* ============================================================
   MAP VIEW: pan / zoom / swipe
   ============================================================ */
const map = $('#map'), worlds = $$('.world');
const V = {s:1, x:0, y:0, iw:100, ih:100, fit:1};

function applyView(anim){
  worlds.forEach(w => {
    w.style.transition = anim && !REDUCED ? 'transform .6s cubic-bezier(.2,.8,.2,1)' : 'none';
    w.style.transform = `translate(${V.x}px, ${V.y}px) scale(${V.s})`;
  });
  $('#vecWorld').style.setProperty('--inv', (1/V.s).toFixed(4));
  const big = Math.max(V.iw, V.ih)*V.s/100;
  feats().forEach((f, i) => {
    const pin = $('#pins').children[i]; if (!pin) return;
    pin.classList.toggle('big', f._span*big > 22);
  });
  // scale bar: metres per screen px
  const b = sc().bounds, mpp = (b.n - b.s)*111320/(V.ih*V.s);
  const target = mpp*110, pow = Math.pow(10, Math.floor(Math.log10(target)));
  const nice = [5, 2, 1].map(k => k*pow).find(v => v <= target) || pow;
  $('#sbBar').style.width = (nice/mpp).toFixed(1) + 'px';
  $('#sbTxt').textContent = nice >= 1000 ? `${nice/1000} km` : `${nice} m`;
}
function fitView(anim){
  const r = map.getBoundingClientRect();
  const s = Math.min(r.width/V.iw, r.height/V.ih)*0.94;
  V.fit = V.s = s; V.x = (r.width - V.iw*s)/2; V.y = (r.height - V.ih*s)/2;
  applyView(anim);
}
function zoomAt(f, mx, my, anim){
  const s = clamp(V.s*f, V.fit*0.6, V.fit*40), k = s/V.s;
  V.x = mx - (mx - V.x)*k; V.y = my - (my - V.y)*k; V.s = s;
  applyView(anim);
}
function flyToFeature(i){
  const f = feats()[i]; if (!f) return;
  const xs = f.pts.map(p => p[0]*V.iw/100), ys = f.pts.map(p => p[1]*V.ih/100);
  const bw = Math.max(...xs) - Math.min(...xs), bh = Math.max(...ys) - Math.min(...ys);
  const r = map.getBoundingClientRect();
  const s = clamp(Math.min(r.width/(bw || 1), r.height/(bh || 1))*0.4, V.fit*1.5, V.fit*12);
  const cx = (Math.max(...xs) + Math.min(...xs))/2, cy = (Math.max(...ys) + Math.min(...ys))/2;
  // #42: the case lands under the swipe divider, so the before/after split falls on it without another click
  const sx = S.view === 'swipe' ? r.width * (S.curtain || 50) / 100 : r.width / 2;
  // ...and above the divider's knob (at mid-height), so the knob never covers it
  V.s = s; V.x = sx - cx*s; V.y = r.height*0.38 - cy*s;
  applyView(true);
}
function setCurtain(p){
  p = clamp(p, 1, 99); S.curtain = p;
  $('#curtain').style.left = p + '%';
  $('#knob').setAttribute('aria-valuenow', Math.round(p));
  $('#layT2').style.clipPath = S.view === 'swipe' ? `inset(0 0 0 ${p}%)` : 'none';
}

// pointer: pan, pinch, click-select, curtain drag
const ptrs = new Map(); let moved = false, down = null, curtainDrag = false;
map.addEventListener('pointerdown', e => {
  if (e.button > 0) return;
  if (e.target.closest('#knob')) { curtainDrag = true; e.preventDefault(); return; }
  if (e.target.closest('.ctl')) return;
  ptrs.set(e.pointerId, {x:e.clientX, y:e.clientY}); moved = false; down = {x:e.clientX, y:e.clientY};
  map.classList.add('grabbing');
});
addEventListener('pointermove', e => {
  const r = map.getBoundingClientRect();
  if (curtainDrag) { setCurtain((e.clientX - r.left)/r.width*100); return; }
  if (S.stage === 'dash' && e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom) {
    const fx = (e.clientX - r.left - V.x)/(V.iw*V.s)*100, fy = (e.clientY - r.top - V.y)/(V.ih*V.s)*100;
    $('#coords').textContent = fx >= 0 && fx <= 100 && fy >= 0 && fy <= 100
      ? (([la, lo]) => `${fLat(la)}  ${fLon(lo)}`)(latLon(sc().bounds, fx, fy)) : 'Outside tile';
    const tip = $('#tip');
    if (tip.classList.contains('on')) tip.style.transform = `translate(${e.clientX - r.left + 14}px, ${e.clientY - r.top + 14}px)`;
  }
  const p = ptrs.get(e.pointerId); if (!p) return;
  if (ptrs.size === 2) {
    const [a, b] = [...ptrs.values()], od = Math.hypot(a.x - b.x, a.y - b.y);
    p.x = e.clientX; p.y = e.clientY;
    const nd = Math.hypot(a.x - b.x, a.y - b.y);
    zoomAt(nd/(od || 1), (a.x + b.x)/2 - r.left, (a.y + b.y)/2 - r.top, false); moved = true; return;
  }
  if (Math.hypot(e.clientX - down.x, e.clientY - down.y) > 4) moved = true;
  if (moved) { V.x += e.clientX - p.x; V.y += e.clientY - p.y; applyView(false); }
  p.x = e.clientX; p.y = e.clientY;
});
function endPtr(e){
  if (curtainDrag) { curtainDrag = false; return; }
  if (!ptrs.delete(e.pointerId)) return;
  if (!ptrs.size) map.classList.remove('grabbing');
  if (moved || e.type === 'pointercancel') return;
  const hit = e.target.closest && e.target.closest('[data-i],[data-fa]');
  if (hit && hit.dataset.i) select(+hit.dataset.i, false);
  else if (hit) toast(faText(FA()[+hit.dataset.fa]));
  else if (S.view === 'swipe') { const r = map.getBoundingClientRect(); setCurtain((e.clientX - r.left)/r.width*100); }
}
addEventListener('pointerup', endPtr); addEventListener('pointercancel', endPtr);
map.addEventListener('wheel', e => {
  if (e.target.closest('.ctl')) return;   // let the overview and layer panels scroll
  e.preventDefault(); const r = map.getBoundingClientRect();
  zoomAt(Math.exp(-e.deltaY*0.0018), e.clientX - r.left, e.clientY - r.top, false);
}, {passive:false});
$('#knob').addEventListener('keydown', e => {
  const d = {ArrowLeft:-2, ArrowRight:2}[e.key]; if (d) { e.preventDefault(); e.stopPropagation(); setCurtain(S.curtain + d); }
});
map.addEventListener('pointerover', e => {
  const el = e.target.closest('[data-i],[data-fa],[data-un]'), tip = $('#tip');
  $$('.poly.hl').forEach(p => p.classList.remove('hl'));
  if (!el) { tip.classList.remove('on'); return; }
  if (el.dataset.i) {
    const f = feats()[+el.dataset.i];
    $(`.poly[data-i="${el.dataset.i}"]`)?.classList.add('hl');
    tip.innerHTML = `<b>${f.id}</b> · ${f.tier} · ${SHORT[f.type] || f.type} · ${fmt(f.area_sqm)} m²`;
  } else if (el.dataset.un) tip.innerHTML = '<b>Unobservable</b> · cloud, shadow or no data on either date · not assessed';
  else tip.innerHTML = faText(FA()[+el.dataset.fa]).replace(/^(\S+)/, '<b>$1</b>');
  tip.classList.add('on');
});
map.addEventListener('pointerleave', () => { $('#tip').classList.remove('on'); $('#coords').textContent = 'Hover for coordinates'; });

/* ============================================================
   RENDERING
   ============================================================ */
/* ---------- one facts bundle per case: the list, the card and the copilot all read it (web/caselogic.js) ---------- */
const factsOf = (f, th = S.th) => CaseLogic.facts(f, D.scenes[th], {mode:S.sev, weights:D.severity.weights, state:caseState(f, th),
  assignee:assigneeOf(f, th), log:caseLog(f, th), fragments:f._frags || []});
const ST_ICON = {New:'○', 'Under review':'◐', 'Field verification':'⌖', Confirmed:'✓', Reported:'↗', Resolved:'●', Dismissed:'✕'};
// decision times are stored in UTC (ISO) and shown in the officer's local time
const MON3 = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const localTs = iso => { const d = new Date(iso), p = n => String(n).padStart(2, '0'); return `${d.getDate()} ${MON3[d.getMonth()]} ${p(d.getHours())}:${p(d.getMinutes())}`; };
const localDay = iso => { const d = new Date(iso); return `${d.getDate()} ${MON3[d.getMonth()]} ${d.getFullYear()}`; };
const stMark = st => `<span class="stm" data-s="${st}"><i aria-hidden="true">${ST_ICON[st]}</i>${st}</span>`;
const tierMark = (t, suffix = '') => `<span class="tierm" data-t="${t}">${t}${suffix}</span>`;
const isOpen = f => !['Dismissed', 'Resolved'].includes(caseState(f));
const redundant = f => !!(f.part_of || f.dup_of);
const urgent = f => f.tier === 'Critical' || f.tier === 'High';
const areaText = a => a >= 1e6 ? `${fmt(a / 1e6, 2)} km² (${fmt(a / 1e4)} ha)` : a >= 10000 ? `${fmt(a / 1e4, 2)} ha (${fmt(a)} m²)` : `${fmt(a)} m²`;
const placeText = f => f.place ? `${f.place.name}` : '';

/* ---------- attention views (#46) ---------- */
const VIEWS = {
  // the default (#46): only what needs a decision now - urgent cases, cases already in progress, and possible
  // encroachment inside a protected or water buffer. Uncertain low-tier cases wait in their own view.
  matters:   {label:'What matters', hint:'Urgent, in progress, or possible encroachment in a protected buffer',
              test:f => OPENING.includes(caseState(f)) && !redundant(f) && (urgent(f) || caseState(f) !== 'New'
                || (f.zone >= 0.5 && CaseLogic.BUILT.has(f.type) && f.tier !== 'Low'))},
  high:      {label:'High priority', hint:'Critical and high, still open', test:f => isOpen(f) && !redundant(f) && urgent(f)},
  uncertain: {label:'Uncertain', hint:'Near the threshold, hard to compare, maybe seasonal, or beside cloud', test:f => isOpen(f) && f._unc.length > 0},
  verify:    {label:'Needs verification', hint:'Not yet confirmed or dismissed', test:f => OPENING.includes(caseState(f)) && !redundant(f)},
  mine:      {label:'Assigned to me', hint:'Your site visits', test:f => isOpen(f) && (assigneeOf(f) === actorName()
                || (PROFILE.role === 'Field officer' && caseState(f) === 'Field verification'))},
  all:       {label:'All changes', hint:'Everything detected, fragments and duplicates included', test:() => true},
};
const showMine = () => PROFILE.role === 'Field officer' || feats().some(f => assigneeOf(f) === actorName());
const firstSeenDate = f => {
  const t = f.temporal, tl = sc().timeline;
  return t && t.first_seen != null && tl ? tl.frames[t.first_seen].date : (sc().iso_dates ? sc().iso_dates[1] : '9999');
};
// priority first, then age (oldest change first), then score
const byPriority = (a, b) => tierRank(b.f.tier) - tierRank(a.f.tier) || firstSeenDate(a.f).localeCompare(firstSeenDate(b.f)) || b.f.score - a.f.score;
function viewRows(view = S.av){
  const q = S.q, v = VIEWS[view] || VIEWS.all;
  return feats().map((f, i) => ({f, i}))
    .filter(({f}) => v.test(f) && (!q || `${f.id} ${f.type} ${CaseLogic.PLAIN[f.type] || ''} ${f.tier} ${placeText(f)} ${caseState(f)}`.toLowerCase().includes(q)))
    .sort(byPriority);
}

function renderHeader(){
  const g = sc(), b = g.bounds;
  $('#tbTitle').textContent = `${g.label} · ${g.sensor}`;
  if ($('#cityPick')) { $('#cityPick').value = MORE.includes(S.th) ? S.th : ''; $('#cityPick').classList.toggle('on', MORE.includes(S.th)); }
  $('#sevSeg').innerHTML = Object.entries(SEV_MODES).map(([k, l]) => `<button data-act="sev:${k}">${l}</button>`).join('');
  $('#tbCoords').textContent = `${g.dates[0]} → ${g.dates[1]} · ${fLat(b.n)} – ${fLat(b.s)}`;
  $('#d1').textContent = g.dates[0];
  $('#d2').textContent = S.tt != null && g.timeline ? g.timeline.frames[S.tt].label : g.dates[1];
  $$('[data-act]').forEach(b => {
    const [k, v] = b.dataset.act.split(':');
    const key = {th:'th', mode:'mode', lang:'lang', view:'view', sev:'sev'}[k];
    if (key) b.setAttribute('aria-pressed', S[key] === v);
  });
  map.dataset.view = S.view; map.classList.toggle('naive', S.mode === 'naive');
}

/* ---------- situation figures (#41): the strip above the map and the overview share them ---------- */
function situation(){
  const fs = feats().filter(f => !redundant(f) && caseState(f) !== 'Dismissed');
  const area = fs.reduce((t, f) => t + f.area_sqm, 0);
  const merged = feats().filter(redundant).length;
  return {n:fs.length, area, merged, high:viewRows('high').length, verify:viewRows('verify').length,
          unc:viewRows('uncertain').length, matters:viewRows('matters').length, unobs:sc().unobservable ? sc().unobservable.pct : 0};
}
const areaShort = a => a >= 1e6 ? `${fmt(a / 1e6, 1)} km²` : `${fmt(a / 1e4, 1)} ha`;
function renderMission(){
  const el = $('#mission');
  if (S.mode === 'naive') {
    const nv = sc().naive, ai = feats().reduce((t, f) => t + f.area_sqm, 0);
    el.innerHTML = [[fmt(nv.regions), `regions flagged by |ΔNDVI| > ${nv.threshold}`], [areaShort(nv.area_sqm), `flagged, ${fmt(nv.area_sqm / ai || 0, 1)}× T.R.A.C.E.`],
      [fmt(nv.false_alarms.length), nv.reference === 'ground truth' ? 'false alarms vs ground truth' : 'not confirmed by T.R.A.C.E.'], ['Naive NDVI', 'fixed threshold, no learning']]
      .map(([v, l]) => `<div class="mfig static"><b style="--c:var(--fa)">${v}</b><span>${l}</span></div>`).join('');
    return;
  }
  const s = situation();
  const tile = (v, l, view, c, title) => `<button class="mfig" data-act="av:${view}" aria-pressed="${S.av === view}" title="${xmlEsc(title || l)}"><b${c ? ` style="--c:${c}"` : ''}>${v}</b><span>${l}</span></button>`;
  el.innerHTML = tile(s.n, `changes · ${areaShort(s.area)}`, 'all', null, 'Show all changes')
    + tile(s.high, 'high priority', 'high', 'var(--high)', 'Show critical and high-priority cases')
    + tile(s.verify, 'to verify', 'verify', 'var(--ocean)', 'Show cases not yet confirmed or dismissed')
    + tile(s.unc, 'uncertain', 'uncertain', 'var(--unc)', 'Show cases that need a closer look')
    + `<button class="mfig" data-act="unobs-toggle" title="Cloud, shadow or missing data: never counted as no change"><b style="--c:var(--unobs)">${fmt(s.unobs, 1)}%</b><span>not observable</span></button>`;
}
function renderOverview(){
  const el = $('#overview'); if (el.hidden) return;
  const g = sc(), s = situation(), ev = !!g.event;
  const lead = ev ? `${areaShort(s.area)} affected between ${g.dates[0]} and ${g.dates[1]}.` : `${s.n} change${s.n === 1 ? '' : 's'} between ${g.dates[0]} and ${g.dates[1]}.`;
  const tail = s.matters ? ` ${s.matters} need${s.matters === 1 ? 's' : ''} a decision first.` : ' Nothing needs a decision right now.';
  const row = (d, v, c, label, sub, act) => `<li><${act ? `button class="ov-row" data-act="${act}"` : 'div class="ov-row static"'} style="--d:${d}"><b${c ? ` style="--c:${c}"` : ''}>${v}</b><span>${label}<small>${sub}</small></span>${act ? '<em>Show</em>' : '<em></em>'}</${act ? 'button' : 'div'}></li>`;
  el.innerHTML = `<div class="ov-place">${xmlEsc(g.place)}</div><div class="ov-dates">${xmlEsc(g.sensor)} · ${g.dates[0]} → ${g.dates[1]}</div>
    <h2 class="ov-sit" id="ovSit">${lead}${tail}</h2>
    <ul class="ov-rows">
      ${row(0, s.n, null, 'changes detected', `${areaShort(s.area)} in total${s.merged ? ` · ${s.merged} fragments and repeats folded into their cases` : ''}`, 'ov:all')}
      ${row(1, s.high, 'var(--high)', 'high-priority sites', 'critical and high, still open', 'ov:high')}
      ${row(2, s.verify, 'var(--ocean)', 'awaiting verification', 'not yet confirmed or dismissed by an officer', 'ov:verify')}
      ${row(3, s.unc, 'var(--unc)', 'uncertain', 'near the threshold, maybe seasonal, or beside cloud', 'ov:uncertain')}
      ${row(4, `${fmt(s.unobs, 1)}%`, 'var(--unobs)', 'not observable', 'cloud, shadow or no data: never counted as no change', null)}
    </ul>
    <div class="ov-acts"><button class="abtn primary" data-act="ov:matters">Start with what matters</button><button class="abtn" data-act="ov:close">Explore the map</button></div>
    <label class="ov-area">Area <select id="ovArea" aria-label="Choose an area">${KEYS.map(k => `<option value="${k}"${k === S.th ? ' selected' : ''}>${xmlEsc(city(k))} · ${xmlEsc(D.scenes[k].place)}</option>`).join('')}</select></label>`;
}
function showOverview(on){
  const el = $('#overview');
  el.hidden = !on; el.classList.remove('show');
  if (on) { renderOverview(); void el.offsetWidth; el.classList.add('show'); setTimeout(() => el.querySelector('.abtn.primary')?.focus({preventScroll:true}), 60); }
}

/* ---------- case list ---------- */
const LIST_STEP = 150;
function renderViews(){
  const ids = Object.keys(VIEWS).filter(k => k !== 'mine' || showMine());
  $('#views').innerHTML = ids.map(k => `<button class="vbtn" data-act="av:${k}" aria-pressed="${S.av === k}" title="${VIEWS[k].hint}"><span>${VIEWS[k].label}</span><span class="n">${viewRows(k).length}</span></button>`).join('');
}
function renderCases(){
  renderViews();
  const r = viewRows(), shown = r.slice(0, S.listN || LIST_STEP);
  $('#clist').innerHTML = shown.length ? shown.map(({f, i}) => {
    const st = caseState(f);
    return `<li><button class="case${st === 'Dismissed' || redundant(f) ? ' dim' : ''}" data-row="${i}" aria-current="${i === S.sel}">
      <span class="ch">${tierMark(f.tier)}${f._unc.length ? '<span class="uncm">Uncertain</span>' : ''}</span>
      <span class="ct">${xmlEsc(CaseLogic.PLAIN[f.type] || f.type)}</span>
      <span class="cm">${f.id}${f.place ? ` · ${xmlEsc(f.place.name)}` : ''} · ${areaShort(f.area_sqm)}${f.part_of ? ` · part of ${f.part_of}` : ''}${f.dup_of ? ` · same spot as ${f.dup_of}` : ''}</span>
      <span class="cr">${stMark(st)}</span></button></li>`;
  }).join('') + (r.length > shown.length ? `<li><button class="case" data-act="more-cases"><span class="ct" style="color:var(--ocean)">Show ${Math.min(LIST_STEP, r.length - shown.length)} more of ${r.length - shown.length}</span></button></li>` : '')
    : `<li class="empty">${S.q ? 'No case matches this search.' : S.av === 'matters' ? 'Nothing needs a decision right now. Open “All changes” to look through everything detected.' : 'No cases in this view.'}</li>`;
  $('#tCount').textContent = `${r.length} of ${feats().length}`;
}

/* ---------- map layers ---------- */
function renderLegend(){
  const fs = feats(), fa = FA();
  let h = TIERS.map(t => {
    const n = fs.filter(f => f.tier === t).length;
    return `<label class="lg-row${S.hidden.has(t) ? ' off' : ''}"><input type="checkbox" data-tier="${t}"${S.hidden.has(t) ? '' : ' checked'}>
      <span class="sw" style="--c:${TIER_VAR[t]}"></span>${t}<span class="n">${n}</span></label>`;
  }).join('');
  const cr = sc().creep;
  if (cr && cr.features.length) h += `<label class="lg-row${S.hideCreep ? ' off' : ''}"><input type="checkbox" data-layer="creep"${S.hideCreep ? '' : ' checked'}>
      <span class="sw dot" style="--c:var(--clay)"></span>Creep &amp; precursors<span class="n">${cr.features.length}</span></label>`;
  if (sc().heat) h += `<label class="lg-row${S.heat ? '' : ' off'}"><input type="checkbox" data-layer="heat"${S.heat ? ' checked' : ''}>
      <span class="sw heat"></span>Changed pixels, selected case</label>`;
  h += `<label class="lg-row${S.spot ? '' : ' off'}"><input type="checkbox" data-layer="spot"${S.spot ? ' checked' : ''}>
      <span class="sw" style="--c:var(--ink-2)"></span>Dim around the selected case</label>`;
  const u = sc().unobservable;
  if (u && u.pct > 0) h += `<label class="lg-row${S.hideUnobs ? ' off' : ''}"><input type="checkbox" data-layer="unobs"${S.hideUnobs ? '' : ' checked'}>
      <span class="sw hatch"></span>Unobservable<span class="n">${u.pct.toFixed(1)}%</span></label>`;
  const ref = sc().reference;
  if (ref && ref.polygons && ref.polygons.length) h += `<label class="lg-row${S.hideRef ? ' off' : ''}"><input type="checkbox" data-layer="ref"${S.hideRef ? '' : ' checked'}>
      <span class="sw outline"></span>EMS reference outline<span class="n">${ref.polygons.length}</span></label>`;
  if (S.mode === 'naive') h += `<div class="lg-row fa"><span class="sw" style="--c:var(--fa);margin-left:23px"></span>Naive false alarms<span class="n">${fa.length}</span></div>`;
  if (S.sev === 'disaster' && !sc().event) h += `<div class="sev-hint">Disaster mode on a non-event area re-ranks priorities only.</div>`;
  $('#legend').innerHTML = h;
}
const pts = a => a.map(p => p.join(',')).join(' ');
function renderUnobs(){
  const u = sc().unobservable;
  $('#unL').innerHTML = u && !S.hideUnobs ? u.polygons.map(p => `<polygon class="unobs" data-un="1" points="${pts(p)}"/>`).join('') : '';
}
function renderRef(){
  const ref = sc().reference, el = $('#refL');
  if (!el) return;
  el.innerHTML = ref && !S.hideRef ? ref.polygons.map(p => `<polygon class="ref-poly" points="${pts(p)}"/>`).join('') : '';
}
function renderNaive(){
  $('#faL').innerHTML = S.mode === 'naive' ? FA().map((fa, i) => `<polygon class="fa" data-fa="${i}" points="${pts(fa.pts)}"/>`).join('') : '';
}
function faText(fa){
  const nv = sc().naive;
  const ref = nv.reference === 'ground truth'
    ? `${Math.round(fa.overlap*100)}% overlaps ground-truth change`
    : `not flagged by T.R.A.C.E. (${Math.round(fa.overlap*100)}% overlap) · no ground truth for this tile`;
  return `${fa.id} · ${SHORT[fa.type] || fa.type} · ${fmt(fa.area_sqm)} m² · ${ref}`;
}
function renderMap(){
  let h = '';
  feats().forEach((f, i) => {
    if (S.hidden.has(f.tier)) return;
    if (i === S.sel) h += `<polygon class="halo" points="${pts(f.pts)}"/>`;
    h += `<polygon class="poly${f.kind ? ' creep' : ''}${caseState(f) === 'Dismissed' ? ' dismissed' : ''}${i === S.sel ? ' sel' : ''}${f._span >= 25 ? ' wide' : ''}" data-i="${i}" style="--c:${TIER_VAR[f.tier]}" points="${pts(f.pts)}"/>`;
  });
  $('#ftL').innerHTML = h;
  $('#pins').innerHTML = feats().map((f, i) =>
    `<span class="pin${i === S.sel ? ' sel' : ''}" data-i="${i}" style="--c:${TIER_VAR[f.tier]};left:${f.cx}%;top:${f.cy}%;${S.hidden.has(f.tier) || (redundant(f) && i !== S.sel) ? 'display:none' : ''}"></span>`).join('');
  // #42: the selected case's own changed pixels, and the rest of the tile dimmed
  // skipped for a case spanning most of the tile (a 366 km² burn): there the highlight would hide the imagery itself
  const f = feats()[S.sel], on = f && S.mode !== 'naive' && f._span < 25;
  $('#selClipP').setAttribute('points', on ? pts(f.pts) : '');
  $('#heatImg').setAttribute('href', on && S.heat && sc().heat ? sc().heat : '');
  $('#spot').setAttribute('d', on && S.spot ? `M0,0H100V100H0Z M${f.pts.map(p => p.join(',')).join('L')}Z` : '');
  applyView(false);
}
// inline SVG sparkline of a per-year series (creep polygons): first / last year labelled
function spark(v, years){
  const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1, n = v.length - 1;
  const xy = v.map((y, i) => [i / n * 100, 30 - (y - lo) / span * 28]);
  return `<svg class="spark" viewBox="0 0 100 32" preserveAspectRatio="none" role="img" aria-label="NDBI ${v[0]} in ${years[0]} to ${v[n]} in ${years[n]}">
    <polyline points="${xy.map(p => p.join(',')).join(' ')}"/></svg>
    <div class="spark-l"><span>${years[0]} · ${v[0].toFixed(2)}</span><span>${years[n]} · ${v[n].toFixed(2)}</span></div>`;
}

/* ---------- Change-to-Action Card (#43) + verification actions and history (#44) ---------- */
function actionButton(key, f, st){
  const a = ACTIONS[key], roleOk = a.roles.includes(PROFILE.role), stateOk = a.from.includes(st);
  const why = !stateOk ? `Not available while the case is ${st.toLowerCase()}.` : !roleOk ? `For the ${a.roles.join(' or ')}.` : '';
  return `<button class="abtn ${a.tone || ''}" data-act="act:${key}"${why ? ` disabled title="${why}"` : ''}>${a.label(PROFILE.role)}</button>`;
}
function undoable(f){
  const log = caseLog(f), last = log[log.length - 1];
  return last && !last.undo_of ? last : null;
}
function historyHTML(f){
  const log = caseLog(f);
  if (!log.length) return '<li><time>—</time><span>Detected by T.R.A.C.E. No officer decision yet.</span></li>';
  return log.slice(-6).reverse().map(e => `<li><time datetime="${e.ts}">${localTs(e.ts)}</time><span><b>${xmlEsc(e.actor || e.role)}</b>${e.actor && e.actor !== e.role ? ` (${e.role})` : ''}: ${xmlEsc(e.action)}${e.from !== e.to ? ` → ${e.to}` : ''}${e.assignee ? ` · ${xmlEsc(e.assignee)}` : ''}${e.note ? ` · “${xmlEsc(e.note)}”` : ''}</span>${(e.photos || []).length ? `<span class="ph">${e.photos.map(id => `<img data-photo="${id}" alt="Site photo for ${f.id}">`).join('')}</span>` : ''}</li>`).join('')
    + (log.length > 6 ? `<li><time></time><span>${log.length - 6} earlier entries in the exported history.</span></li>` : '');
}
function renderCard(){
  const el = $('#cac'), f = feats()[S.sel];
  if (!f) { el.innerHTML = `<div class="q"><p>No case selected. Pick one from the list or click a polygon on the map.</p></div>`; return; }
  const F = factsOf(f), C = CaseLogic.card(F), st = F.status, r = viewRows(), pos = r.findIndex(x => x.i === S.sel);
  const g = sc(), det = g.detector || {}, pp = g.passport;
  const thr = F.reliability.threshold, frags = f._frags || [];
  const roster = [...new Set(ROSTER(S.th).concat(rosterExtra))];
  const extra = ['report', 'resolve', 'reopen'].filter(k => ACTIONS[k].from.includes(st));
  const navURL = `https://www.google.com/maps/dir/?api=1&destination=${f.lat},${f.lon}`;
  const idxRows = Object.entries(f.idx || {}).map(([k, v]) => `<dt>Δ${{d_ndvi:'NDVI', d_mndwi:'MNDWI', d_ndbi:'NDBI', d_nbr:'NBR'}[k]}</dt><dd class="mono">${v > 0 ? '+' : ''}${v.toFixed(3)}</dd>`).join('');
  const passportRows = pp ? [
      ['Sensor', `${xmlEsc(pp.sensor)} · ${xmlEsc(pp.processing_level)} · ${pp.resolution_m} m`],
      ...(pp.images || []).map((im, i) => [i ? 'After image' : 'Before image', `${CaseLogic.fmtDate(im.date)}${im.scene_id ? ` · <span class="mono">${xmlEsc(im.scene_id)}</span>` : ''}<br>sun ${im.sun_elevation}° (${xmlEsc(im.sun_source)}) · ${xmlEsc(im.season)}${im.crop_stage ? `, ${xmlEsc(im.crop_stage)}` : ''}`]),
      ...(pp.comparability ? [['Comparability', `${pp.comparability.score}/100 · ${pp.comparability.factors.filter(x => x.cost > 0).map(x => `${xmlEsc(x.detail)} (−${x.cost})`).join('; ') || 'no factor costs points'}`]] : []),
      ['Misregistration', pp.misregistration_px != null ? `${pp.misregistration_px} px, corrected` : 'not measured'],
      ['Source', xmlEsc(pp.source)], ['Licence', xmlEsc(pp.licence)],
      ...Object.entries(pp.checksums || {}).slice(0, 2).map(([n, h]) => [n, `<span class="mono" title="${h}">sha256 ${h.slice(0, 16)}…</span>`]),
      ...(pp.note ? [['Note', xmlEsc(pp.note)]] : []),
    ].map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('') : '';
  el.innerHTML = `
    <header class="cac-h"><div style="min-width:0">
        <div class="cac-id">${f.id}${f.kind ? ' · multi-year series' : ''}</div>
        <h2 class="cac-what">${xmlEsc(C.what)}</h2>
        <div class="cac-badges">${tierMark(f.tier, ' priority')}${stMark(st)}${C.uncertain.length ? '<span class="uncm">Uncertain</span>' : ''}</div>
      </div>
      <div class="stepper"><span>${pos >= 0 ? `${pos + 1} of ${r.length}` : 'not in this view'}</span>
        <button class="ibtn" data-act="sel:prev" aria-label="Previous case"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="m15 6-6 6 6 6"/></svg></button>
        <button class="ibtn" data-act="sel:next" aria-label="Next case"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg></button>
      </div></header>
    <section class="q"><h3>What changed</h3><ul>
      <li>${areaText(f.area_sqm)}${f.place ? ` near ${xmlEsc(f.place.name)} (${fmt(f.place.dist_m)} m)` : ''}.</li>
      <li>${xmlEsc(C.firstSeen)}</li>
      ${C.persistence ? `<li>${xmlEsc(C.persistence)}</li>` : ''}
      ${frags.length ? `<li>Includes ${frags.length} small fragment${frags.length === 1 ? '' : 's'} beside it: ${frags.slice(0, 6).join(', ')}${frags.length > 6 ? ` and ${frags.length - 6} more` : ''}.</li>` : ''}
      ${f.part_of ? `<li>A fragment of ${f.part_of}; decide it with that case.</li>` : ''}
      ${f.dup_of ? `<li>The same spot as ${f.dup_of}, found again by the multi-year scan.</li>` : ''}
    </ul><p class="hint2"><button class="lnk" data-act="focus">Zoom to it</button> · <button class="lnk" data-act="copy">Copy coordinates</button></p></section>
    <section class="q"><h3>Why it matters</h3><p>${xmlEsc(C.whyPriority)}</p><ul>
      <li>${xmlEsc(C.assets)}</li>${C.buffer ? `<li class="flag">${xmlEsc(C.buffer)}</li>` : ''}</ul></section>
    <section class="q"><h3>How reliable</h3><dl class="rel">
      <dt>Signal</dt><dd>${xmlEsc(C.signal)}<div class="meter" style="--c:${F.reliability.margin < 0.15 ? 'var(--unc)' : 'var(--forest)'}" role="img" aria-label="signal ${f.magnitude.toFixed(2)}, threshold ${thr.toFixed(2)}"><i style="width:${f.magnitude * 100}%"></i><b style="left:${thr * 100}%"></b></div></dd>
      <dt>Images</dt><dd>${xmlEsc(C.comparability)}</dd>
      <dt>Cloud</dt><dd>${xmlEsc(C.cloud)}</dd>
      <dt>Season</dt><dd>${xmlEsc(C.seasonal)}</dd>
    </dl>${C.uncertain.length ? `<div class="callout">Uncertain: ${xmlEsc(C.uncertain.join('; '))}. Look closer before you decide.</div>` : ''}</section>
    <section class="q next"><h3>What to do next</h3><p>${xmlEsc(C.next)}</p>
      <div class="acting"><label for="role">Acting as</label><select id="role">${ROLES.map(x => `<option${x === PROFILE.role ? ' selected' : ''}>${x}</option>`).join('')}</select>
        <input id="actor" type="text" placeholder="Your name (for the history)" value="${xmlEsc(PROFILE.name)}" aria-label="Your name"></div>
      <div class="acts">${['confirm', 'dismiss', 'inspect', 'assign'].map(k => actionButton(k, f, st)).join('')}
        ${extra.map(k => `<button class="abtn primary wide" data-act="act:${k}"${ACTIONS[k].roles.includes(PROFILE.role) ? '' : ` disabled title="For the ${ACTIONS[k].roles.join(' or ')}."`}>${ACTIONS[k].label(PROFILE.role)}</button>`).join('')}</div>
      <div class="assign" id="assignBox"><select id="asSel" aria-label="Assign to">${roster.map(x => `<option>${xmlEsc(x)}</option>`).join('')}<option value="__other">Someone else…</option></select>
        <button class="abtn primary" data-act="do-assign">Assign</button><input id="asOther" type="text" placeholder="Name or team" aria-label="Assignee name" hidden></div>
      ${PROFILE.role === 'Field officer' ? `<div class="field"><a class="abtn" href="${navURL}" target="_blank" rel="noopener">Navigate to site</a><button class="abtn" data-act="photo">Add site photo</button></div>` : ''}
      <input class="note" id="cNote" type="text" placeholder="Why? Add a note to the history (optional)" aria-label="Note for the history" maxlength="280">
      <p class="hint2">${F.assignee ? `Assigned to ${xmlEsc(F.assignee)}. ` : ''}${ROLES.filter(x => x !== PROFILE.role).length ? `Roles are local to this device and not signed in.` : ''}</p>
      <ol class="hist" aria-label="Decision history">${historyHTML(f)}</ol>
      <div class="case-foot"><button class="lnk" data-act="case-undo"${undoable(f) ? '' : ' disabled'}>Undo last action</button><span class="outbox" id="outbox"></span></div>
    </section>
    <details class="more" id="more"${S.moreOpen ? ' open' : ''}><summary>Show details</summary><div class="more-b">
      <h4>Change rules</h4><dl class="kv">${idxRows || '<dt>Indices</dt><dd>not available for RGB imagery</dd>'}<dt>Rule output</dt><dd style="font-weight:500">${xmlEsc(f.summary)}</dd></dl>
      <h4>Priority score</h4><dl class="kv">
        <dt>${SEV_MODES[S.sev]} mode</dt><dd class="mono">${(f.score / 100).toFixed(2)} = ${f.parts.norm_area.toFixed(2)} × ${f.magnitude.toFixed(2)} × ${(D.severity.weights[S.sev][f.type] ?? 0.5).toFixed(2)} × ${f.parts.exposure.toFixed(2)}</dd>
        <dt>Reads as</dt><dd style="font-weight:500">area × signal × type weight × exposure</dd>
        ${Object.entries(SEV_MODES).map(([m, l]) => `<dt>${l} tier</dt><dd>${f.tiers[m]} · ${(f.scores[m] / 100).toFixed(2)}</dd>`).join('')}
        <dt>Action</dt><dd>${xmlEsc(f.priority)}</dd></dl>
      <h4>Detector</h4><dl class="kv">
        <dt>Model</dt><dd>${xmlEsc(det.name || '')}</dd>
        <dt>Benchmark</dt><dd>${det.f1 != null ? `F1 ${pct(det.f1)} · ` : ''}${xmlEsc(det.benchmark || '')}</dd>
        <dt>Threshold</dt><dd class="mono">${thr.toFixed(3)}${det.threshold_base != null && det.threshold !== det.threshold_base ? ` (raised from ${det.threshold_base} for image comparability)` : ''}</dd>
        <dt>Protected zone</dt><dd>${Math.round((f.zone || 0) * 100)}% inside a protected or water buffer${f.zone >= 0.5 ? ': recall-first threshold' : ''}</dd></dl>
      ${f.series && sc().creep ? `<h4>Built-up index by year</h4>${spark(f.series, sc().creep.years)}` : ''}
      ${passportRows ? `<h4>Scene Passport</h4><dl class="kv">${passportRows}</dl>` : ''}
      <h4>Location</h4><dl class="kv"><dt>Centroid</dt><dd class="mono">${fLat(f.lat)}<br>${fLon(f.lon)}</dd></dl>
    </div></details>`;
  $('#capId').textContent = f.id;
  $('#more').addEventListener('toggle', e => { S.moreOpen = e.target.open; });
  el.querySelectorAll('img[data-photo]').forEach(async im => { const u = await photoURL(im.dataset.photo); if (u) im.src = u; else im.alt = 'Photo not synced to this device yet'; });
  renderOutbox();
}
function renderOutbox(){
  const el = $('#outbox'); if (!el) return;
  const n = Sync.pending().length;
  el.innerHTML = !n ? (Sync.server ? 'All decisions synced' : '') : Sync.server && navigator.onLine
    ? `<b>${n}</b> waiting to sync`
    : `<b>${n}</b> ${navigator.onLine ? 'saved on this device' : 'queued offline'} · <button class="lnk" data-act="dl:pack">Share field pack</button>`;
}

/* ---------- "Explain this change" (#45) ---------- */
function renderAsk(){
  const f = feats()[S.sel];
  $('#askChips').innerHTML = f ? CaseLogic.QUESTIONS.map(([id, q]) => `<button class="chipq" data-act="ask:${id}">${q.replace('this priority', `${f.tier.toLowerCase()} priority`)}</button>`).join('') : '';
  const a = $('#answer');
  if (!S.answer || !f || S.answer.id !== f.id) { a.hidden = true; a.innerHTML = ''; return; }
  const A = S.answer, li = xs => xs.map(s => `<li>${xmlEsc(s)}</li>`).join('');
  a.hidden = false;
  a.innerHTML = `<div class="ans-q">${xmlEsc(A.q)}</div>
    ${A.facts.length ? `<div class="ans-g"><h4>Observed in the data</h4><ul>${li(A.facts)}</ul></div>` : ''}
    ${A.hyp.length ? `<div class="ans-g hyp"><h4>Possible explanations, to check on the ground</h4><ul>${li(A.hyp)}</ul></div>` : ''}
    <div class="ans-src">${xmlEsc(A.src)}</div>`;
}
async function ask(q, qid){
  const f = feats()[S.sel]; if (!f) return;
  const F = factsOf(f);
  const offline = (id, src) => { const r = CaseLogic.answer(id, F); return {id:f.id, q, facts:r.facts, hyp:r.hypotheses, src}; };
  if (qid) { S.answer = offline(qid, 'Answered from this case’s facts. Every number is checked against them.'); renderAsk(); return; }
  if (Sync.server) {
    S.answer = {id:f.id, q, facts:['Checking the case facts…'], hyp:[], src:''}; renderAsk();
    try {
      const r = await fetch('api/explain', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question:q, facts:F})});
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.status);
      const j = await r.json();
      if (j.refused) throw new Error('the model declined this question');
      const a = CaseLogic.keepGrounded(j.observed_facts, F), b = CaseLogic.keepGrounded(j.possible_explanations, F);
      const removed = (j.removed || 0) + a.dropped.length + b.dropped.length;
      S.answer = {id:f.id, q, facts:a.kept.length ? a.kept : ['The answer did not survive the fact check. Try one of the suggested questions.'], hyp:b.kept,
        src:`Answered by ${j.model} from this case’s facts only.${removed ? ` ${removed} sentence${removed === 1 ? '' : 's'} with numbers not in the facts removed.` : ' Every number checked against the facts.'}`};
      renderAsk(); return;
    } catch (e) {
      const id = CaseLogic.match(q);
      S.answer = id ? offline(id, `The language model is unavailable (${e.message}); answered offline from the closest suggested question.`)
        : {id:f.id, q, facts:[`The language model is unavailable (${e.message}).`], hyp:[], src:'Pick a suggested question to get an offline answer.'};
      renderAsk(); return;
    }
  }
  const id = CaseLogic.match(q);
  S.answer = id ? offline(id, 'Offline: answered from the closest suggested question, using this case’s facts only.')
    : {id:f.id, q, facts:['Offline, I can answer the suggested questions above. Free-text questions need the console to be served by the T.R.A.C.E. server with a language model configured.'], hyp:[], src:''};
  renderAsk();
}

/* ---------- time travel (#47) ---------- */
function frameImage(fr){ return fr.img || (fr.role === 'pre' ? sc().images.t1 : sc().images.t2); }
function showFrame(k){
  const tl = sc().timeline; if (!tl) return;
  S.tt = k == null ? null : clamp(k, 0, tl.frames.length - 1);
  const fr = S.tt == null ? null : tl.frames[S.tt];
  $('#imgT2').src = fr ? frameImage(fr) : sc().images.t2;
  $('#d2').textContent = fr ? (tl.kind === 'series' ? CaseLogic.monthYear(fr.date) : CaseLogic.fmtDate(fr.date)) : sc().dates[1];
  if (S.view === 'before') { S.view = 'swipe'; renderHeader(); setCurtain(S.curtain); }
  renderTT();
}
function ttSpark(t, frames, k){
  const v = t.values, ok = v.map((x, i) => [x, i]).filter(([x]) => x != null);
  if (ok.length < 2) return '';
  const lo = Math.min(...ok.map(([x]) => x)), hi = Math.max(...ok.map(([x]) => x)), span = hi - lo || 1, n = frames.length - 1;
  const X = i => i / n * 100, Y = x => 40 - (x - lo) / span * 32;
  const line = ok.map(([x, i]) => `${X(i)},${Y(x)}`).join(' ');
  const pair = t.pair_frames || [0, 1];
  const fs = t.first_seen;
  return `<svg class="tt-spark" viewBox="0 -2 100 48" preserveAspectRatio="none" role="img" aria-label="${xmlEsc((t.index || '').toUpperCase())} for the selected case across the image dates">
    ${pair.map(i => `<line x1="${X(i)}" x2="${X(i)}" y1="0" y2="44" stroke="var(--ocean)" stroke-width="1" stroke-dasharray="2 2" vector-effect="non-scaling-stroke"/>`).join('')}
    ${k != null ? `<line x1="${X(k)}" x2="${X(k)}" y1="-2" y2="46" stroke="var(--forest)" stroke-width="2" vector-effect="non-scaling-stroke"/>` : ''}
    <polyline points="${line}" fill="none" stroke="var(--clay)" stroke-width="1.8" vector-effect="non-scaling-stroke"/>
    ${ok.map(([x, i]) => `<circle cx="${X(i)}" cy="${Y(x)}" r="${i === fs ? 1.9 : 1.1}" fill="${i === fs ? 'var(--clay)' : 'var(--card)'}" stroke="var(--clay)" stroke-width="1" vector-effect="non-scaling-stroke"/>`).join('')}
  </svg>`;
}
function renderTT(){
  const el = $('#tt'), tl = sc().timeline;
  if (!tl || S.mode === 'naive') { el.hidden = true; return; }
  el.hidden = false;
  const fr = tl.frames, k = S.tt, f = feats()[S.sel], t = f && f.temporal && f.temporal.values ? f.temporal : null;
  const pair = new Set(tl.pair_frames), first = t && t.first_seen != null ? t.first_seen : null;
  const lbl = (x, i) => tl.kind === 'series' ? x.label : (x.role === 'pre' ? 'Before' : x.role === 'post' ? 'After' : CaseLogic.monthYear(x.date));
  const showing = k == null ? `the after image, ${sc().dates[1]}` : `${tl.kind === 'series' ? CaseLogic.monthYear(fr[k].date) : CaseLogic.fmtDate(fr[k].date)}`;
  let note = '';
  if (f && t && f.temporal.assessed) {
    const F = factsOf(f), C = CaseLogic.card(F);
    note = `${f.id} · ${xmlEsc(F.temporal ? F.temporal.index : '')}: ${xmlEsc(tl.kind === 'series' ? C.firstSeen : '')} ${xmlEsc(C.persistence || '')}`;
  } else if (f) note = `${f.id}: no index history for this case.`;
  el.innerHTML = `<div class="tt-h"><h3>Time travel</h3><span class="sub2">Right of the divider: <b>${showing}</b> · left: ${sc().dates[0]}</span>
      <button class="abtn" data-act="tt-play">${S.ttPlay ? 'Pause' : 'Play'}</button></div>
    <div class="tt-ticks" role="group" aria-label="Image dates">${fr.map((x, i) => x.usable ? `<button class="tick${pair.has(i) ? ' pair' : ''}${i === first ? ' first' : ''}" data-act="tt:${i}" aria-pressed="${i === k}" title="${x.id || ''}">${lbl(x, i)}<small>${tl.kind === 'series' ? CaseLogic.monthYear(x.date).slice(0, 3) : x.date.slice(2)}</small></button>` : '').join('')}</div>
    ${t ? ttSpark(t, fr, k) : ''}
    <p class="tt-note">${note}</p>
    <div class="tt-leg"><span><i style="--c:var(--ocean)"></i>the image pair</span>${tl.kind === 'series' ? '<span><i style="--c:var(--clay)"></i>first visible</span>' : ''}<span>Only dates with a usable, cloud-free image are listed.</span></div>`;
}
let ttTimer = null;
function ttPlay(){
  const tl = sc().timeline; if (!tl) return;
  if (S.ttPlay) { clearInterval(ttTimer); S.ttPlay = false; renderTT(); return; }
  const use = tl.frames.map((x, i) => x.usable ? i : -1).filter(i => i >= 0);
  let p = S.tt == null ? 0 : Math.max(0, use.indexOf(S.tt) + 1);
  if (p >= use.length) p = 0;
  S.ttPlay = true; showFrame(use[p]);
  ttTimer = setInterval(() => { p++; if (p >= use.length) { clearInterval(ttTimer); S.ttPlay = false; renderTT(); return; } showFrame(use[p]); }, REDUCED ? 1800 : 1100);
}

/* ---------- Team progress (#48): counts and ageing from the decision history; process measures only ---------- */
const featIndex = () => { const m = new Map(); KEYS.forEach(th => D.scenes[th].features.concat(D.scenes[th].creep ? D.scenes[th].creep.features : []).forEach(f => m.set(`${th}/${f.id}`, f))); return m; };
function impactData(period){
  const since = period === 'all' ? '' : new Date(Date.now() - (+period) * 864e5).toISOString();
  const ev = audit.filter(e => e.ts >= since && !e.undo_of);
  const undone = new Set(audit.filter(e => e.undo_of).map(e => e.undo_of));
  const real = ev.filter(e => !undone.has(e.uid));
  const idx = featIndex(), cases = new Map();
  audit.forEach(e => { const k = `${e.sector}/${e.case}`; if (!cases.has(k)) cases.set(k, []); cases.get(k).push(e); });
  const now = Date.now(), rows = [];
  cases.forEach((log, k) => {
    const [th, id] = k.split('/'), f = idx.get(k), last = log[log.length - 1], a = log.filter(e => 'assignee' in e).pop();
    rows.push({th, id, zone:f && f.place ? f.place.name : '—', team:a && a.assignee ? a.assignee : 'Unassigned', state:last.to,
      days:Math.floor((now - Date.parse(log[0].ts)) / 864e5), first:log[0].ts, last:last.ts, n:log.length});
  });
  return {
    reviewed:new Set(real.map(e => `${e.sector}/${e.case}`)).size,
    dismissed:real.filter(e => e.to === 'Dismissed' && e.from !== 'Dismissed').length,
    inspected:real.filter(e => e.from === 'Field verification' && (e.to === 'Confirmed' || e.to === 'Dismissed')).length,
    resolved:real.filter(e => e.to === 'Resolved' && e.from !== 'Resolved').length,
    days:period === 'all' ? 30 : +period, events:real, rows,
  };
}
function renderImpact(period){
  S.impP = period;
  $$('[data-act^="imp:"]').forEach(b => b.setAttribute('aria-pressed', b.dataset.act === `imp:${period}`));
  const d = impactData(period);
  $('#impFigs').innerHTML = [[d.reviewed, 'cases reviewed'], [d.dismissed, 'false alarms dismissed'], [d.inspected, 'field inspections completed'], [d.resolved, 'cases resolved']]
    .map(([v, l]) => `<div><b>${v}</b><span>${l}</span></div>`).join('');
  const day = 864e5, today = Math.floor(Date.now() / day), counts = Array(d.days).fill(0);
  d.events.forEach(e => { const k = d.days - 1 - (today - Math.floor(Date.parse(e.ts) / day)); if (k >= 0 && k < d.days) counts[k]++; });
  const mx = Math.max(1, ...counts), w = 100 / d.days;
  $('#impTrend').innerHTML = `<svg class="imp-trend" viewBox="0 0 100 40" preserveAspectRatio="none" role="img" aria-label="Decisions per day, last ${d.days} days">${counts.map((c, i) => `<rect x="${i * w + w * .15}" y="${40 - c / mx * 38}" width="${w * .7}" height="${c / mx * 38}"/>`).join('')}</svg>
    <p class="fine" style="margin:2px 0 0">Decisions per day, last ${d.days} days. Busiest day: ${Math.max(...counts)}.</p>`;
  const open = d.rows.filter(r => !['Dismissed', 'Resolved'].includes(r.state)).sort((a, b) => b.days - a.days);
  $('#impOld').innerHTML = open.length ? open.slice(0, 8).map(r => `<tr><td class="mono">${r.id}</td><td>${xmlEsc(city(r.th))} · ${xmlEsc(r.zone)}</td><td>${xmlEsc(r.team)}</td><td>${stMark(r.state)}</td><td class="num mono">${r.days}</td></tr>`).join('')
    : '<tr><td colspan="5" class="empty">No open cases with officer activity yet.</td></tr>';
  const med = a => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor((s.length - 1) / 2)] : '–'; };
  const group = key => { const m = new Map(); d.rows.forEach(r => { const g = m.get(r[key]) || {open:[], closed:0}; ['Dismissed', 'Resolved'].includes(r.state) ? g.closed++ : g.open.push(r.days); m.set(r[key], g); }); return [...m]; };
  const by = group('zone').map(([k, g]) => [`Zone: ${k}`, g]).concat(group('team').map(([k, g]) => [`Team: ${k}`, g]));
  $('#impBy').innerHTML = by.length ? by.map(([k, g]) => `<tr><td>${xmlEsc(k)}</td><td class="num mono">${g.open.length}</td><td class="num mono">${g.closed}</td><td class="num mono">${med(g.open)}</td></tr>`).join('')
    : '<tr><td colspan="4" class="empty">Decisions recorded on any case appear here.</td></tr>';
}

function renderAdvisory(){
  const a = ADV[S.lang], f = feats()[S.sel];
  $('#advTitle').textContent = a.title;
  $('#advBody').textContent = f ? a.body(f, (TYPE_I18N[f.type] || {})[S.lang] || f.type, fmt(f.area_sqm), sc().place)
    + (f.tier === 'Critical' || f.tier === 'High' ? a.urgent : a.routine) : '';
  $('#advBody').lang = S.lang === 'en' ? 'en' : S.lang;
}
function renderBanner(){
  const nv = sc().naive;
  $('#banner').innerHTML = `<b>Naive NDVI baseline:</b> |ΔNDVI| > ${nv.threshold} flags ${fmt(nv.regions)} regions (${fmt(nv.area_sqm)} m²). `
    + `${fmt(nv.false_alarms.length)} of them barely touch ${nv.reference} (<20% overlap) and are drawn dashed. `
    + `Benchmark false-alarm rate ${pct(NV.false_alarm_rate)} vs ${pct(AI.false_alarm_rate)}.`
    + (nv.reference === 'ground truth' ? '' : ` <b>Note:</b> this tile has no usable ground truth, so naive regions are checked against T.R.A.C.E.'s own detections. Treat this view as a picture of baseline noise, not a measured accuracy score.`);
}
const places = () => sc().georeferenced === false ? [] : (sc().places || []);
const placeName = pl => pl[`name_${S.lang}`] || pl.name;
function findPlace(q){
  const k = q.trim().toLowerCase(), names = pl => [pl.name, pl.name_mr, pl.name_hi].filter(Boolean).map(n => n.toLowerCase());
  return places().find(pl => names(pl).includes(k)) || (k.length > 2 && places().find(pl => names(pl).some(n => n.includes(k))));
}
function renderLookup(){
  const l = LK[S.lang], ps = places(), out = $('#lkOut');
  $('#lookup').hidden = !ps.length;
  $('#lkBtn').textContent = l.btn;
  const pin = ps.find(p => p.kind === 'pincode'), area = ps.find(p => p.kind === 'suburb') || ps[0];
  $('#lkIn').placeholder = ps.length ? l.ph + [pin && pin.name, area && placeName(area)].filter(Boolean).join(' / ') : '';
  $('#lkList').innerHTML = ps.map(p => `<option value="${xmlEsc(placeName(p))}">`).join('');
  if (!ps.length) { out.hidden = false; out.style.removeProperty('--c'); out.textContent = l.off; return; }
  if (!S.lk) { out.hidden = true; return; }
  out.hidden = false;
  const pl = S.lk.place;
  if (!pl) { out.style.removeProperty('--c'); out.textContent = l.none(S.lk.q); return; }
  // citizens see officer-verified cases only (unverified alerts must not reach the public)
  const all = feats(), near = f => haversine(pl.lat, pl.lon, f.lat, f.lon);
  const pending = all.filter(f => !VERIFIED.has(caseState(f)) && caseState(f) !== 'Dismissed' && near(f) <= NEAR_M).length;
  const vis = all.map((f, i) => [f, i, near(f)]).filter(([f]) => VERIFIED.has(caseState(f))).sort((a, b) => a[2] - b[2]);
  S.lk.nearest = undefined;
  if (!vis.length) { out.style.removeProperty('--c'); out.textContent = l.noneVerified + (pending ? l.pending(pending) : ''); return; }
  const [f, i, m] = vis[0], d = m < 1000 ? `${Math.round(m / 10) * 10} ${l.unit[0]}` : `${(m / 1000).toFixed(1)} ${l.unit[1]}`;
  out.style.setProperty('--c', m <= NEAR_M ? TIER_VAR[f.tier] : 'var(--forest)');
  out.textContent = (m <= NEAR_M
    ? l.near(placeName(pl), d, f, (TYPE_I18N[f.type] || {})[S.lang] || f.type, TIER_I18N[f.tier][S.lang])
    : l.far(placeName(pl), d)) + (pending ? l.pending(pending) : '');
  if (m <= NEAR_M) S.lk.nearest = i;
}
function renderAll(){ renderHeader(); renderMission(); renderCases(); renderLegend(); renderUnobs(); renderRef(); renderNaive(); renderMap(); renderCard(); renderAsk(); renderTT(); renderAdvisory(); renderLookup(); renderBanner(); renderOverview(); }
function renderDecision(){ renderMission(); renderCases(); renderMap(); renderCard(); renderLookup(); renderOverview(); }

function select(i, flyTo){
  if (i == null || !feats()[i]) return;
  const changed = i !== S.sel;
  S.sel = i; renderMap(); renderCard(); renderAdvisory(); renderTT();
  if (changed) { S.answer = null; renderAsk(); } else renderAsk();
  $$('#clist .case[data-row]').forEach(b => b.setAttribute('aria-current', +b.dataset.row === i));
  $(`#clist .case[data-row="${i}"]`)?.scrollIntoView({block:'nearest'});
  if (flyTo) flyToFeature(i);
}
function step(d){
  const r = viewRows(); if (!r.length) return;
  const pos = r.findIndex(x => x.i === S.sel);
  select(r[(pos + d + r.length) % r.length].i, true);
}
function setView(v, pick){
  S.av = v; S.listN = LIST_STEP; renderMission(); renderCases(); renderCard();
  const r = viewRows();
  if (pick && r.length) select(r[0].i, true);
}

async function loadTheater(th){
  S.th = th; S.sev = sc().default_mode || 'encroachment'; applySev(); S.hidden.clear(); S.hideRef = false; S.q = ''; $('#search').value = ''; S.lk = null; $('#lkIn').value = '';
  S.tt = null; S.answer = null; S.av = 'matters'; S.listN = LIST_STEP; clearInterval(ttTimer); S.ttPlay = false; $('#layPop').hidden = true;
  const every = sc().features.concat(sc().creep ? sc().creep.features : []), byId = new Map(every.map(f => [f.id, f]));
  every.forEach(f => {
    const xs = f.pts.map(p => p[0]), ys = f.pts.map(p => p[1]);
    f._span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
    f._unc = CaseLogic.uncertain(CaseLogic.facts(f, sc())); f._frags = [];
  });
  every.forEach(f => { if (f.part_of && byId.has(f.part_of)) byId.get(f.part_of)._frags.push(f.id); });
  const first = viewRows('matters')[0] || viewRows('all')[0];
  S.sel = first ? first.i : 0;
  const t1 = $('#imgT1'), t2 = $('#imgT2');
  t1.src = sc().images.t1; t2.src = sc().images.t2;
  await Promise.all([t1.decode().catch(() => {}), t2.decode().catch(() => {})]);
  V.iw = t1.naturalWidth || 100; V.ih = t1.naturalHeight || 100;
  worlds.forEach(w => { w.style.width = V.iw + 'px'; w.style.height = V.ih + 'px'; });
  renderAll(); fitView(false); setCurtain(50);
}

/* ============================================================
   EXPORTS
   ============================================================ */
function download(data, name, mime){
  const url = URL.createObjectURL(new Blob([data], {type:mime}));
  const a = Object.assign(document.createElement('a'), {href:url, download:name});
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast(`Downloaded ${name}`);
}
const bytes = b64 => Uint8Array.from(atob(b64), c => c.charCodeAt(0));
const xmlEsc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function capNote(f){
  const st = caseState(f), last = caseLog(f).filter(e => VERIFIED.has(e.to)).pop();
  return VERIFIED.has(st)
    ? `Confirmed by ${last.actor || last.role} (${last.role}, ${last.role === 'Field officer' ? 'site visit' : 'imagery review'}) on ${localDay(last.ts)}${last.note ? ` (${last.note})` : ''}; case state ${st}. Draft awaiting DDMA sign-off.`
    : `Draft alert generated by T.R.A.C.E. AI. Not yet verified by an officer (case state: ${st}). Awaiting official verification and sign-off by the District Disaster Management Authority (DDMA).`;
}
function capXml(f){
  const crit = f.tier === 'Critical', la = f.lat, lo = f.lon;
  const sent = new Date().toISOString().replace(/\.\d+Z$/, '+00:00');
  const uid = Math.random().toString(16).slice(2, 8).toUpperCase();
  const ring = f.ring.slice();
  const [a, z] = [ring[0], ring[ring.length - 1]];
  if (a[0] !== z[0] || a[1] !== z[1]) ring.push(a);
  const ev = sc().event || 'encroachment';
  const prof = (D.profiles && D.profiles[ev]) || {
    cap_category: 'Env',
    cap_event: 'Land-use change / possible encroachment',
    instruction: 'Field officers to verify on site. Satellite encroachment flags are screening results: check against Development Plan and CRZ maps before any regulatory action.'
  };
  return `<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>IND-SACHET-${sent.slice(0, 10).replace(/-/g, '')}-${f.id}-${uid}</identifier>
  <sender>TRACE-SatelliteEngine@ndma.gov.in</sender>
  <sent>${sent}</sent>
  <status>Draft</status>
  <msgType>Alert</msgType>
  <scope>Restricted</scope>
  <restriction>For Official Authorization Only</restriction>
  <note>${xmlEsc(capNote(f))}</note>
  <info>
    <language>en-IN</language>
    <category>${xmlEsc(prof.cap_category)}</category>
    <event>${xmlEsc(prof.cap_event)}</event>
    <urgency>${crit ? 'Immediate' : 'Expected'}</urgency>
    <severity>${crit ? 'Extreme' : 'Severe'}</severity>
    <certainty>Observed</certainty>
    <headline>${xmlEsc(`Satellite Change Alert: ${f.area_sqm} m² ${f.type} Detected`)}</headline>
    <description>${xmlEsc(`Bi-temporal satellite intelligence detected a change footprint of ${f.area_sqm} m² at (${la.toFixed(6)}, ${lo.toFixed(6)}) with confidence ${(f.magnitude*100).toFixed(1)}%. Classification: ${f.type}. ${f.summary}`)}</description>
    <instruction>${xmlEsc(prof.instruction)}</instruction>
    <area>
      <areaDesc>${xmlEsc(`${sc().label}: footprint near (${la.toFixed(6)}, ${lo.toFixed(6)})`)}</areaDesc>
      <polygon>${ring.map(([y, x]) => `${y.toFixed(6)},${x.toFixed(6)}`).join(' ')}</polygon>
    </area>
  </info>
</alert>
`;
}
function csv(){
  const q = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const head = ['feature_id','priority','change','change_type','area_sqm','first_seen','uncertain','near','centroid_lat','centroid_lon','status','assignee','action_priority'];
  return [head.join(',')].concat(viewRows().map(({f}) => [f.id, f.tier, q(CaseLogic.PLAIN[f.type] || f.type), q(f.type), f.area_sqm,
    firstSeenDate(f) !== (sc().iso_dates || [])[1] ? firstSeenDate(f) : '', q(f._unc.join('; ')), q(f.place ? f.place.name : ''),
    f.lat.toFixed(6), f.lon.toFixed(6), q(caseState(f)), q(assigneeOf(f)), q(f.priority)].join(','))).join('\n');
}
async function fieldPack(){
  const ids = new Set(audit.flatMap(e => e.photos || []));
  const photos = (await PhotoDB.all().catch(() => [])).filter(p => ids.has(p.id));
  return JSON.stringify({format:'trace-field-pack', version:1, exported:new Date().toISOString(), by:`${actorName()} (${PROFILE.role})`, entries:audit, photos});
}
function impactCSV(){
  const d = impactData(S.impP || 30), q = v => `"${String(v).replace(/"/g, '""')}"`;
  return ['area,case,zone,team,status,first_action,last_action,days_open,decisions'].concat(d.rows.map(r =>
    [q(city(r.th)), r.id, q(r.zone), q(r.team), q(r.state), r.first, r.last, ['Dismissed', 'Resolved'].includes(r.state) ? '' : r.days, r.n].join(','))).join('\n');
}
const DL = {
  geojson: () => download(D.files[S.th].geojson, `${S.th}_change_intelligence.geojson`, 'application/geo+json'),
  gpkg: () => download(bytes(D.files[S.th].gpkg), `${S.th}_change_intelligence.gpkg`, 'application/geopackage+sqlite3'),
  cap: () => { const f = feats()[S.sel];
    if (caseState(f) === 'Dismissed') return toast(`${f.id} was marked as a false alarm: no alert drafted`);
    download(capXml(f), `sachet_cap_${S.th}_${f.id}.xml`, 'application/xml'); },
  audit: () => download(JSON.stringify(audit, null, 1), 'trace_decision_history.json', 'application/json'),
  verdicts: () => download(JSON.stringify(KEYS.flatMap(th => D.scenes[th].features.concat(D.scenes[th].creep ? D.scenes[th].creep.features : [])
      .map(f => [f, caseLog(f, th)]).filter(([, l]) => l.length && (VERIFIED.has(l[l.length - 1].to) || l[l.length - 1].to === 'Dismissed'))
      .map(([f, l]) => ({sector: th, id: f.id, verdict: l[l.length - 1].to === 'Dismissed' ? 'false_alarm' : 'confirmed',
        state: l[l.length - 1].to, decided_at: l[l.length - 1].ts, decided_by: l[l.length - 1].actor || l[l.length - 1].role,
        change_type: f.type, area_sqm: f.area_sqm, ring_latlon: f.ring}))), null, 1),
    'trace_officer_verdicts.json', 'application/json'),
  sitrep: () => download(bytes(D.files[S.th].sitrep), `TRACE_SitRep_${S.th}.pdf`, 'application/pdf'),
  csv: () => download(csv(), `${S.th}_${S.av}_cases.csv`, 'text/csv'),
  pack: async () => download(await fieldPack(), `trace_field_pack_${new Date().toISOString().slice(0, 10)}.json`, 'application/json'),
  impact: () => download(impactCSV(), 'trace_team_progress.csv', 'text/csv'),
};

/* ============================================================
   ACTIONS (delegated)
   ============================================================ */
function decide(key){
  const f = feats()[S.sel], a = ACTIONS[key], st = caseState(f);
  if (!a || !a.from.includes(st) || !a.roles.includes(PROFILE.role)) return;
  if (key === 'assign') { const box = $('#assignBox'); box.classList.toggle('on'); box.querySelector('select').focus(); return; }
  const note = $('#cNote').value.trim();
  record(f, {action:a.label(PROFILE.role), to:a.to, note, method:PROFILE.role === 'Field officer' ? 'site visit' : 'imagery review'});
  renderDecision();
  toast(`${f.id} ${a.done}`);
}
function doAssign(){
  const f = feats()[S.sel], sel = $('#asSel'), other = $('#asOther');
  if (sel.value === '__other' && other.hidden) { other.hidden = false; other.focus(); return; }
  const who = (sel.value === '__other' ? other.value : sel.value).trim();
  if (!who) { other.focus(); toast('Type a name or team to assign the case to'); return; }
  if (sel.value === '__other' && !ROSTER(S.th).includes(who)) { rosterExtra = [...new Set(rosterExtra.concat(who))]; store.set('ci-roster', rosterExtra); }
  const st = caseState(f);
  record(f, {action:'Assign case', to:st === 'New' ? 'Under review' : st, assignee:who, note:$('#cNote').value.trim()});
  renderDecision(); renderViews();
  toast(`${f.id} assigned to ${who}`);
}
function undo(){
  const f = feats()[S.sel], last = undoable(f);
  if (!last) { toast('Nothing to undo on this case'); return; }
  const before = caseLog(f).filter(e => e !== last && 'assignee' in e).pop();
  record(f, {action:`Undo: ${last.action}`, from:last.to, to:last.from, undo_of:last.uid, ...('assignee' in last ? {assignee:before ? before.assignee : null} : {})});
  renderDecision();
  toast(`Undid “${last.action}” on ${f.id}`);
}
async function addPhoto(file){
  const f = feats()[S.sel]; if (!f || !file) return;
  try {
    const data = await downsize(file), id = newId();
    await PhotoDB.put({id, sector:S.th, case:f.id, ts:new Date().toISOString(), data});
    photoCache.set(id, data);
    record(f, {action:'Site photo added', photos:[id], note:$('#cNote').value.trim()});
    renderCard(); toast(`Photo saved to ${f.id}${Sync.server && navigator.onLine ? '' : ': it will sync when you are back online'}`);
  } catch (e) { toast('That file could not be read as a photo'); }
}
async function importPack(file){
  try {
    const j = JSON.parse(await file.text());
    if (j.format !== 'trace-field-pack' || !Array.isArray(j.entries)) throw new Error('not a field pack');
    const n = Sync.merge(j.entries);
    let m = 0;
    for (const p of (j.photos || [])) if (p && p.id && typeof p.data === 'string' && p.data.startsWith('data:image/')) { await PhotoDB.put(p).catch(() => {}); m++; }
    renderDecision();
    toast(n || m ? `Imported ${n} decision${n === 1 ? '' : 's'} and ${m} photo${m === 1 ? '' : 's'} from ${j.by || 'a field pack'}` : 'Nothing new in that field pack');
  } catch (e) { toast(`Could not import: ${e.message}`); }
}
document.addEventListener('click', e => {
  const el = e.target.closest('[data-act]'); if (!el || el.disabled) return;
  if (el.tagName !== 'INPUT' && el.tagName !== 'A') e.preventDefault();
  const [k, v] = el.dataset.act.split(':');
  switch (k) {
    case 'fly': fly(v in D.scenes ? v : KEYS[0], 1); break;
    case 'back': if (S.stage === 'dash') { showOverview(false); fly(S.th, -1); } break;
    case 'th': if (v !== S.th) { loadTheater(v).then(() => { showOverview(false); }); } break;
    case 'mode': S.mode = v; renderHeader(); renderMission(); renderLegend(); renderNaive(); renderMap(); renderTT(); break;
    case 'sev': S.sev = v; applySev(); renderAll(); toast(v === 'disaster' && !sc().event ? 'Disaster mode re-ranks the existing changes (not an event area)' : `Ranked for ${SEV_MODES[v].toLowerCase()} work`); break;
    case 'lang': S.lang = v; renderHeader(); renderAdvisory(); renderLookup(); break;
    case 'view': S.view = v; renderHeader(); setCurtain(S.curtain); break;
    case 'zoom': { const r = map.getBoundingClientRect();
      v === 'fit' ? fitView(true) : zoomAt(v === 'in' ? 1.6 : 1/1.6, r.width/2, r.height/2, true); break; }
    case 'sel': step(v === 'next' ? 1 : -1); break;
    case 'focus': flyToFeature(S.sel); break;
    case 'copy': {
      const f = feats()[S.sel], txt = `${f.lat.toFixed(6)}, ${f.lon.toFixed(6)}`;
      (navigator.clipboard ? navigator.clipboard.writeText(txt) : Promise.reject()).then(() => toast(`Copied ${txt}`), () => toast(txt));
      break; }
    case 'av': setView(v, true); break;
    case 'ov': showOverview(false); if (v !== 'close') setView(v, true); break;
    case 'overview': showOverview($('#overview').hidden); break;
    case 'more-cases': S.listN = (S.listN || LIST_STEP) + LIST_STEP; renderCases(); break;
    case 'unobs-toggle': S.hideUnobs = !S.hideUnobs; renderLegend(); renderUnobs(); toast(S.hideUnobs ? 'Unobservable areas hidden' : 'Unobservable areas shown hatched on the map'); break;
    case 'layers': { const p = $('#layPop'); p.hidden = !p.hidden; el.setAttribute('aria-expanded', !p.hidden); break; }
    case 'act': decide(v); break;
    case 'do-assign': doAssign(); break;
    case 'case-undo': undo(); break;
    case 'photo': $('#photoIn').click(); break;
    case 'pack-import': $('#packIn').click(); break;
    case 'ask': ask(CaseLogic.QUESTIONS.find(x => x[0] === v)[1].replace('this priority', `${feats()[S.sel].tier.toLowerCase()} priority`), v); break;
    case 'tt': showFrame(+v); break;
    case 'tt-play': ttPlay(); break;
    case 'impact': renderImpact(S.impP || 30); $('#impact').showModal(); break;
    case 'impact-close': $('#impact').close(); break;
    case 'imp': renderImpact(v === 'all' ? 'all' : +v); break;
    case 'dl': DL[v](); break;
    case 'bench': $('#bench').showModal(); break;
    case 'bench-close': $('#bench').close(); break;
    case 'stress': renderStress(v); break;
  }
});
$('#clist').addEventListener('click', e => {
  const b = e.target.closest('[data-row]'); if (!b) return;
  select(+b.dataset.row, true);
  if (innerWidth <= 820) map.scrollIntoView({behavior:REDUCED ? 'auto' : 'smooth', block:'start'});   // phones: the list sits below the map
});
$('#clist').addEventListener('pointerover', e => {
  const b = e.target.closest('[data-row]');
  $$('.poly.hl').forEach(p => p.classList.remove('hl'));
  if (b) $(`.poly[data-i="${b.dataset.row}"]`)?.classList.add('hl');
});
$('#legend').addEventListener('change', e => {
  const L = e.target.dataset.layer;
  if (L === 'ref') { S.hideRef = !e.target.checked; renderLegend(); renderRef(); return; }
  if (L === 'unobs') { S.hideUnobs = !e.target.checked; renderLegend(); renderUnobs(); return; }
  if (L === 'heat') { S.heat = e.target.checked; renderLegend(); renderMap(); return; }
  if (L === 'spot') { S.spot = e.target.checked; renderLegend(); renderMap(); return; }
  if (L === 'creep') { S.hideCreep = !e.target.checked; S.sel = Math.min(S.sel, feats().length - 1); renderAll(); return; }
  const t = e.target.dataset.tier; if (!t) return;
  e.target.checked ? S.hidden.delete(t) : S.hidden.add(t);
  renderLegend(); renderMap();
});
// role and name live in the card, which re-renders: delegate
document.addEventListener('change', e => {
  if (e.target.id === 'role') { PROFILE.role = e.target.value; store.set('ci-profile', PROFILE); renderCard(); renderViews(); toast(`Acting as ${PROFILE.role}`); }
  if (e.target.id === 'actor') { PROFILE.name = e.target.value.trim().slice(0, 60); store.set('ci-profile', PROFILE); renderViews(); }
  if (e.target.id === 'asSel') { $('#asOther').hidden = e.target.value !== '__other'; if (e.target.value === '__other') $('#asOther').focus(); }
  if (e.target.id === 'ovArea' && e.target.value !== S.th) loadTheater(e.target.value).then(() => showOverview(false));
});
document.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.id === 'asOther') { e.preventDefault(); doAssign(); } });
$('#photoIn').addEventListener('change', e => { addPhoto(e.target.files[0]); e.target.value = ''; });
$('#packIn').addEventListener('change', e => { if (e.target.files[0]) importPack(e.target.files[0]); e.target.value = ''; });
$('#askForm').addEventListener('submit', e => { e.preventDefault(); const q = $('#askIn').value.trim(); if (q) ask(q); });
$('#lookup').addEventListener('submit', e => {
  e.preventDefault();
  const q = $('#lkIn').value.trim(); if (!q) return;
  S.lk = {q, place: findPlace(q)};
  renderLookup();
  if (S.lk.place && S.lk.nearest !== undefined) select(S.lk.nearest, true);
});
$('#search').addEventListener('input', e => { S.q = e.target.value.trim().toLowerCase(); S.listN = LIST_STEP; renderCases(); renderCard(); });
function setPolyFill(val) {
  const v = Math.max(0, Math.min(100, parseInt(val, 10) || 0));
  $('#vec').style.setProperty('--fill', (v / 100).toFixed(2));
  const fd = $('#fillDirect'), f = $('#fill'), fv = $('#fillVal'), fp = $('#fillPopVal');
  if (fd && fd.value != v) fd.value = v;
  if (f && f.value != v) f.value = v;
  if (fv) fv.textContent = v + '%';
  if (fp) fp.textContent = v + '%';
}
$('#fill')?.addEventListener('input', e => setPolyFill(e.target.value));
$('#fillDirect')?.addEventListener('input', e => setPolyFill(e.target.value));
['#bench', '#impact'].forEach(id => $(id).addEventListener('click', e => { if (e.target === e.currentTarget) e.currentTarget.close(); }));
document.addEventListener('click', e => {   // close the layers popover from outside
  const p = $('#layPop');
  if (!p.hidden && !p.contains(e.target) && !e.target.closest('[data-act="layers"]')) { p.hidden = true; $('[data-act="layers"]').setAttribute('aria-expanded', 'false'); }
});
addEventListener('keydown', e => {
  if (S.stage !== 'dash' || flying || e.metaKey || e.ctrlKey) return;
  if (e.key === 'Escape') {
    if (!$('#overview').hidden) { showOverview(false); return; }
    if (!$('#layPop').hidden) { $('#layPop').hidden = true; return; }
  }
  if (e.target.closest('input, select, textarea, dialog[open]')) return;
  const r = map.getBoundingClientRect(), tl = sc().timeline;
  const ttStep = d => { if (!tl) return; const use = tl.frames.map((x, i) => x.usable ? i : -1).filter(i => i >= 0);
    const p = S.tt == null ? use.indexOf(tl.pair_frames[1]) : use.indexOf(S.tt); showFrame(use[clamp(p + d, 0, use.length - 1)]); };
  const act = {ArrowRight:() => step(1), ArrowLeft:() => step(-1), j:() => step(1), k:() => step(-1),
    f:() => fitView(true), '+':() => zoomAt(1.6, r.width/2, r.height/2, true), '=':() => zoomAt(1.6, r.width/2, r.height/2, true),
    '-':() => zoomAt(1/1.6, r.width/2, r.height/2, true), '1':() => $('[data-act="view:before"]').click(),
    '2':() => $('[data-act="view:swipe"]').click(), '3':() => $('[data-act="view:after"]').click(),
    '[':() => ttStep(-1), ']':() => ttStep(1)}[e.key];
  if (act) { e.preventDefault(); act(); }
});
let rT; addEventListener('resize', () => { clearTimeout(rT); rT = setTimeout(() => { if (S.stage === 'dash') fitView(false); }, 120); });
Sync.probe();

/* sector-driven chrome: nav, CTAs, switcher */
(() => {
  const arw = '<svg class="arw" viewBox="0 0 12 10" fill="none" aria-hidden="true"><path d="M0.8 5h10M7.1 1.4 10.9 5l-3.8 3.6" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  // featured sectors get buttons / nav links; the OSCD benchmark cities go in one dropdown so 20+ sectors fit
  const links = FEATURED.map(k => `<a data-act="fly:${k}">${city(k)}</a>`).join('') + '<a data-act="bench">Benchmark</a>';
  $('#navLinks').innerHTML = links; $('#menuLinks').innerHTML = links;
  if (MORE.length) {
    $('#cityPick').hidden = false;
    $('#cityPick').innerHTML = `<option value="">More cities (${MORE.length})</option>` + MORE.map(k => `<option value="${k}">${city(k)}</option>`).join('');
    $('#cityPick').addEventListener('change', e => { const k = e.target.value; if (k && k !== S.th) loadTheater(k).then(() => { renderHeader(); toast(`Loaded ${D.scenes[k].label}`); }); });
  }
  $('#ctas').innerHTML = KEYS.slice(0, 2).map((k, i) =>
    `<button class="btn btn-lg ${i ? 'btn-ghost' : 'btn-primary'}" data-act="fly:${k}">${i ? `${city(k)} tile` : `Zoom into ${city(k)}`}${arw}</button>`).join('');
  $('#sectorSeg').innerHTML = FEATURED.map(k => `<button data-act="th:${k}">${city(k)}</button>`).join('');
  $('#navF1').textContent = `F1 ${pct(AI.f1_score)}`;
})();

/* stress test chart: T2 perturbed, ground truth unchanged */
const ST = D.stress, ST_M = [['ai_raw','T.R.A.C.E.','var(--forest)'],['ai_stable','+ stable-pixel normalisation','var(--ocean)'],['ai_hist_matched','+ histogram matching','var(--minor)'],['naive','Naive spectral','var(--fa)']]
  .filter(([k]) => !ST || k in ST.conditions[0]);
function renderStress(metric){
  $$('[data-act^="stress:"]').forEach(b => b.setAttribute('aria-pressed', b.dataset.act === `stress:${metric}`));
  const max = Math.max(...ST.conditions.flatMap(c => ST_M.map(([k]) => c[k][metric]))) || 1;
  $('#stressRows').innerHTML = ST.conditions.map(c => `<div class="srow"><b>${c.name}</b><div class="sbars">${ST_M.map(([k, l, col]) =>
    `<div class="sbar" title="${l}"><span><i style="--c:${col};width:${c[k][metric]/max*100}%"></i></span><em>${pct(c[k][metric])}</em></div>`).join('')}</div></div>`).join('');
}
if (ST) {
  $('#stress').hidden = false;
  $('#stressP').textContent = `T2 is brightened, darkened or shadowed while ground truth stays the same, so anything newly flagged is a false alarm. ${ST.dataset}, ${ST.samples} pairs.`;
  $('#stressLeg').innerHTML = ST_M.map(([, l, c]) => `<span><i style="--c:${c}"></i>${l}</span>`).join('');
  const by = k => ST.conditions.find(c => c.name === k), clean = by('Clean'),
    worst = k => ST.conditions.reduce((a, c) => c[k].f1_score < a[k].f1_score ? c : a);
  $('#stressNote').innerHTML = ST_M.map(([k, l]) => { const w = worst(k);
    return `<b>${l}:</b> F1 ${pct(clean[k].f1_score)} clean, lowest ${pct(w[k].f1_score)} (${w.name.toLowerCase()}).`; }).join('<br>')
    + (ST.misregistration ? `<br><b>Misregistration:</b> before image shifted ${ST.misregistration.shift_px.join('×')} px: F1 ${pct(ST.misregistration.ai_raw.f1_score)}; after registering it onto the after image ${pct(ST.misregistration.ai_registered.f1_score)}.` : '');
  renderStress('f1_score');
}

/* benchmark dialog: misses by object size, slow change, false alarms per area, runtime */
(() => {
  const r = v => v == null ? '–' : pct(v);
  if (B.objects) {
    const a = B.objects.ai, n = B.objects.naive;
    $('#bObj').hidden = false;
    $('#bObjP').textContent = `A ground-truth object counts as found when detections cover at least half of it. ${B.dataset}, ${fmt(a.gt_objects)} objects. Object precision (IoU > 0.5): T.R.A.C.E. ${r(a.precision_iou50)}, naive ${r(n.precision_iou50)}.`;
    $('#bObjRows').innerHTML = a.recall_by_size.map((b, i) => `<tr><td>${b.bin}</td><td class="num mono">${fmt(b.objects)}</td><td class="num mono win">${r(b.recall_hit50)}</td><td class="num mono">${r(n.recall_by_size[i].recall_hit50)}</td></tr>`).join('')
      + `<tr><td><b>All</b></td><td class="num mono">${fmt(a.gt_objects)}</td><td class="num mono win">${r(a.recall_hit50)}</td><td class="num mono">${r(n.recall_hit50)}</td></tr>`;
  }
  const C = B.creep_vs_sudden;
  if (C) {
    $('#bCreep').hidden = false;
    $('#bCreepP').textContent = `Each LEVIR-CD test pair (${C.pairs} with change) becomes a ${C.steps}-step sequence where every new building appears gradually. A system that compares each new image only with the previous one sees ${100 / C.steps}% of the change per step; one anchored to the first image sees it accumulate. Synthetic blending, not real staged construction.`;
    const S2 = [['consecutive_recall_hit50', 'Consecutive images', 'var(--fa)'], ['anchored_recall_hit50', 'Anchored to first image', 'var(--forest)']];
    $('#bCreepLeg').innerHTML = S2.map(([, l, c]) => `<span><i style="--c:${c}"></i>${l}</span>`).join('');
    $('#bCreepRows').innerHTML = C.per_step.map(s => `<div class="srow"><b>Step ${s.step}</b><div class="sbars">${S2.map(([k, l, col]) =>
      `<div class="sbar" title="${l}"><span><i style="--c:${col};width:${(s[k] || 0) * 100}%"></i></span><em>${r(s[k])}</em></div>`).join('')}</div></div>`).join('');
    $('#bCreepNote').innerHTML = `<b>Objects found at any step, consecutive comparison:</b> ${r(C.consecutive_any_step_recall_hit50)}. <b>Anchored, final step:</b> ${r(C.anchored_final_recall_hit50)}. This is why the Sentinel-2 creep detector compares the whole series, not neighbouring years.`;
  }
  const rows = [];
  // in-domain (0.5 m) the low T.R.A.C.E. figure is a win; at 10 m it is low because the model barely fires, so it is starred
  const far = (label, d, note, inDomain) => d && rows.push(`<tr><td>${label}${note ? `<br><small>${note}</small>` : ''}</td>${['ai', 'naive', 'spectral'].map((k, i) =>
    `<td class="num mono${i === 0 && inDomain ? ' win' : ''}">${d[k] == null ? '–' : d[k].toFixed(2)}${i === 0 && !inDomain ? '*' : ''}</td>`).join('')}</tr>`);
  far(B.dataset, B.false_alarm_km2_per_100km2, '0.5 m aerial', true);
  if (B.oscd) far(`OSCD, ${B.oscd.cities.length} cities`, B.oscd.false_alarm_km2_per_100km2, '10 m Sentinel-2');
  const SN = B.seasonal_no_change;
  if (SN) far(`Mumbai, ${SN.dates ? SN.dates.join(' → ') : 'seasonal pair'}`, SN.flagged_km2_per_100km2, 'post-monsoon vs dry season · all flagged area, an upper bound');
  if (rows.length) {
    $('#bFar').hidden = false;
    $('#bFarP').textContent = 'Area wrongly flagged, measured on land the ground truth marks unchanged. Index rules are the training-free Sentinel-2 detector built from the change-type indices.';
    $('#bFarRows').innerHTML = rows.join('');
    if (B.oscd) $('#bFarNote').innerHTML = `<b>* Not a win:</b> T.R.A.C.E.'s model was trained on 0.5 m aerial images and barely fires on 10 m Sentinel-2 (OSCD F1 ${r(B.oscd.changeintel_ai_engine.f1_score)}; naive ${r(B.oscd.naive_spectral_baseline.f1_score)}, index rules ${r(B.oscd.spectral_index_rules.f1_score)}), so it also flags almost nothing on unchanged land. Use LEVIR-CD for its accuracy. The seasonal row shows what naive NDVI does across a monsoon-to-dry-season pair.`;
  }
  if (B.runtime) $('#bRun').textContent = `Runtime: ${B.runtime.s_per_km2} s per km² at 0.5 m (${B.runtime.megapixels_per_s} megapixels/s, model inference on Apple M5 Max). At 10 m that is ${(B.runtime.s_per_km2 / 400).toFixed(4)} s per km².`;
  if (B.event_validation) {
    $('#bEvent').hidden = false;
    $('#bEventP').textContent = 'Validation of event-specific spectral detectors against Copernicus Emergency Management Service (EMS) satellite delineations on final vectorized polygons within observable reference bounds.';
    $('#bEventRows').innerHTML = Object.entries(B.event_validation).map(([k, ev]) => {
      const ci = ev.changeintel, nv = ev.naive_ndvi, tb = ev.track_b_urban;
      return `<tr><td><b>${ev.event}</b></td><td class="num mono">${ev.scope_km2} km²</td><td class="num mono win">${r(ci.f1_score)} <small>(P ${r(ci.precision)}, R ${r(ci.recall)})</small></td><td class="num mono">${r(nv.f1_score)}</td><td class="num mono">${tb ? r(tb.f1_score) : '–'}</td></tr>`;
    }).join('');
    $('#bEventNote').innerHTML = '<b>Method:</b> Event detectors use fixed literature index thresholds (burn severity dNBR &ge; 0.27 for wildfire, new water MNDWI &gt; 0 for flood) without event tuning. Naive NDVI detects wildfire well but lacks severity classification; Track B is built for urban change and does not transfer to disasters.';
  }
  if (B.track_b_loco) {
    const tb = B.track_b_loco, p = tb.pooled;
    $('#bTrackB').hidden = false;
    $('#bTrackBP').textContent = `Leave-one-city-out (LOCO) over 14 labelled OSCD cities at 10 m Sentinel-2. The model scoring a city never saw that city during training. Contrast with BIT (0.5 m aerial), which scores F1 0.00 on 10 m OSCD.`;
    const rowsTb = tb.per_city.map(c => {
      const cName = (D.scenes && D.scenes[c.city]) ? (D.scenes[c.city].nav || D.scenes[c.city].place.split(',')[0]) : (c.city.charAt(0).toUpperCase() + c.city.slice(1));
      return `<tr><td>${cName}</td><td class="num mono win">${r(c.f1_score)}</td><td class="num mono">${r(c.precision)}</td><td class="num mono">${r(c.recall)}</td><td class="num mono">${c.threshold.toFixed(3)}</td></tr>`;
    }).join('') + `<tr><td><b>Pooled (${tb.cities} cities)</b></td><td class="num mono win"><b>${r(p.f1_score)}</b></td><td class="num mono"><b>${r(p.precision)}</b></td><td class="num mono"><b>${r(p.recall)}</b></td><td class="num mono"><b>–</b></td></tr>`;
    $('#bTrackBRows').innerHTML = rowsTb;
    $('#bTrackBNote').innerHTML = `<b>Triage performance:</b> Operating threshold favours precision (F0.5). With polygon cleanup (${tb.objects.cleanup}), object precision reaches <b>${pct(tb.objects.object_precision)}</b> with <b>${tb.objects.polygons_per_city}</b> polygons/city and ${pct(tb.objects.objects_found)} of labelled objects found. False alarms: <b>${tb.false_alarm_km2_per_100km2} km² per 100 km²</b>.`;
  }
})();

/* benchmark dialog + hero meta from data */
(() => {
  const rowsB = [['F1-score','f1_score'],['IoU','iou'],['Precision','precision'],['Recall','recall'],['False-alarm rate','false_alarm_rate']];
  $('#benchRows').innerHTML = rowsB.map(([l, k]) => {
    const lower = k === 'false_alarm_rate', rel = (AI[k] - NV[k])/NV[k]*100;
    return `<tr><td><b>${l}</b></td><td class="num mono${lower ? ' lose' : ''}">${pct(NV[k])}</td><td class="num mono win">${pct(AI[k])}</td><td class="num mono win">${rel > 0 ? '+' : ''}${rel.toFixed(1)}%</td></tr>`;
  }).join('');
  $('#benchP').textContent = `Fine-tuned Bitemporal Transformer (BIT) vs. a naive spectral-difference baseline, evaluated on the ${B.dataset || "LEVIR-CD test split"} (${B.evaluation_samples_count} image pairs, pixel counts pooled).`;
  $('#benchNote').innerHTML = `<b>Takeaway:</b> naive spectral differencing mistakes seasonal vegetation and sun-angle shifts for change (${pct(NV.false_alarm_rate)} false alarms). T.R.A.C.E. cuts false alarms by <b>${B.false_alarm_reduction_percentage}%</b> to ${pct(AI.false_alarm_rate)}.`;
  $('#heroMeta').innerHTML = `LEVIR-CD F1 <i>${pct(AI.f1_score)}</i> · false alarms <i>${pct(AI.false_alarm_rate)}</i> vs ${pct(NV.false_alarm_rate)} naive`;
})();
</script>

<script>
/* B) burger */
(function(){
  var b = document.getElementById('burger'), m = document.getElementById('menu'); if (!b || !m) return;
  function set(open){ m.classList.toggle('open', open); b.setAttribute('aria-expanded', open); b.setAttribute('aria-label', open ? 'Close menu' : 'Open menu'); }
  b.addEventListener('click', function(e){ e.stopPropagation(); set(!m.classList.contains('open')); });
  m.addEventListener('click', function(e){ if (e.target.closest('a')) set(false); });
  document.addEventListener('click', function(e){ if (m.classList.contains('open') && !m.contains(e.target) && !b.contains(e.target)) set(false); });
  document.addEventListener('keydown', function(e){ if (e.key === 'Escape' && m.classList.contains('open')) { set(false); b.focus(); } });
})();
</script>
</body>
</html>
"""

# case facts, card sentences, uncertainty rule and the offline copilot: one file the console and the tests share
caselogic = (ROOT / 'web/caselogic.js').read_text(encoding='utf-8')
assert '</script' not in caselogic
html = TEMPLATE.replace('/*__CASELOGIC__*/', caselogic).replace('/*__DATA__*/null', json.dumps(DATA, ensure_ascii=False).replace('</', '<\\/'))
(ROOT / 'web/index.html').write_text(html, encoding='utf-8')
print(f"Wrote web/index.html ({len(html) / 1e6:.2f} MB)")
