"""Builds web/index.html: self-contained ChangeIntel console (globe landing + change dashboard).

Run from anywhere:  python scripts/build_frontend_light.py
Everything (imagery, Earth texture, export files) is inlined so the page works offline.
"""
import base64
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def b64(rel):
    return base64.b64encode((ROOT / rel).read_bytes()).decode()


# web/scenes.json is produced by scripts/build_scenes.py (runs the real pipeline)
scenes = json.loads((ROOT / 'web/scenes.json').read_text())
severity = scenes.pop('_severity', None)   # type weights + priorities, to explain scores in the inspector
OUT = 'data/outputs/'

DATA = {
    'scenes': scenes,
    'severity': severity,
    'benchmark': json.loads((ROOT / OUT / 'benchmark_metrics.json').read_text()),
    # src/models/stress_test.py; the chart is omitted when it hasn't been run
    'stress': json.loads((ROOT / OUT / 'stress_test.json').read_text()) if (ROOT / OUT / 'stress_test.json').exists() else None,
    # NASA Blue Marble (public domain), equirectangular 2048x1024
    'earth': 'data:image/jpeg;base64,' + b64('web/assets/earth_equirect.jpg'),
    'files': {k: {'geojson': (ROOT / OUT / sc['files']['geojson']).read_text(),
                  'gpkg': b64(OUT + sc['files']['gpkg']),
                  'sitrep': b64(OUT + sc['files']['sitrep'])} for k, sc in scenes.items()},
}

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>ChangeIntel — Change, mapped from orbit</title>
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
.left{grid-area:left} .right{grid-area:right}
.center{grid-area:center;display:flex;flex-direction:column;gap:12px;min-height:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
.card-h h3{margin:0}
.city-pick{font:inherit;font-size:12px;font-weight:600;border:1px solid var(--line);background:var(--card-2);border-radius:99px;padding:7px 12px;color:var(--ink);max-width:180px}
.city-pick.on{background:var(--card);box-shadow:0 1px 3px rgba(30,38,32,.14)}
.seg-sm button{padding:4px 9px;font-size:10.5px;letter-spacing:0;text-transform:none}
.card h3,.card-h{margin:0 0 10px;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);
  display:flex;align-items:center;justify-content:space-between;gap:8px}
.card-h .mono{letter-spacing:0;text-transform:none;font-weight:500}

.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:11px 14px}
.kpi-l{font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.kpi-v{font-size:22px;font-weight:700;letter-spacing:-.02em;margin-top:3px;font-variant-numeric:tabular-nums}
.kpi-v small{font-size:12px;color:var(--muted);font-weight:600;margin-left:3px}
.kpi-s{font-size:11px;color:var(--muted);margin-top:1px}

/* legend */
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
.halo{fill:none;stroke:#fff;stroke-width:7;stroke-opacity:.9;vector-effect:non-scaling-stroke;pointer-events:none}
.unobs{fill:url(#hatch);stroke:var(--unobs);stroke-width:1.2;vector-effect:non-scaling-stroke;pointer-events:visiblePainted;cursor:help}
.lg-row .sw.hatch{background:repeating-linear-gradient(45deg, var(--unobs) 0 1.5px, var(--unobs-bg) 1.5px 4px);border-color:var(--unobs)}
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

/* inspector */
.ins-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
.ins-id{font-family:var(--mono);font-size:20px;font-weight:600;letter-spacing:-.02em;margin:2px 0 8px}
.eyebrow{font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.stepper{display:flex;gap:4px;align-items:center}
.stepper span{font-family:var(--mono);font-size:11px;color:var(--muted);margin-right:4px}
.ibtn{width:30px;height:30px;border-radius:9px;border:1px solid var(--line);background:var(--card-2);display:grid;place-items:center;cursor:pointer;color:var(--ink-2)}
.ibtn:hover{background:#fff;color:var(--ink)}
.ibtn:focus-visible{border-radius:9px}
.tags{display:flex;flex-wrap:wrap;gap:6px}
.tag{display:inline-flex;align-items:center;gap:6px;border-radius:99px;padding:4px 10px;font-size:11.5px;font-weight:700;
  background:color-mix(in srgb, var(--c) 14%, transparent);color:var(--c)}
.tag.plain{--c:var(--ink-2);font-weight:600}
.summary{margin:10px 0 4px;font-size:12.5px;line-height:1.5;color:var(--ink-2)}
dl{margin:8px 0 0;display:grid;grid-template-columns:auto 1fr;gap:0}
dt,dd{padding:7px 0;border-top:1px solid var(--line);font-size:12px}
dt{color:var(--muted);padding-right:12px}
dd{margin:0;text-align:right;font-weight:600;min-width:0}
dd.mono{font-weight:500}
.bar{display:inline-block;width:70px;height:6px;border-radius:3px;background:var(--line);vertical-align:middle;margin-right:8px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--c)}
.actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
.abtn{display:inline-flex;align-items:center;justify-content:center;gap:7px;border:1px solid var(--line);background:var(--card-2);
  border-radius:10px;padding:9px 10px;font-size:12px;font-weight:600;cursor:pointer;color:var(--ink-2)}
.abtn:hover{background:#fff;color:var(--ink);border-color:var(--line-2)}
.abtn:focus-visible{border-radius:10px}
.abtn.primary{background:var(--forest);border-color:var(--forest);color:var(--btn-ink)}
.abtn.primary:hover{background:var(--forest-h)}
.abtn.good:hover{border-color:var(--moss);color:var(--moss)}
.abtn.bad:hover{border-color:var(--crit);color:var(--crit)}
.case-top{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
.role{font-size:11.5px;color:var(--muted);display:flex;align-items:center;gap:6px}
.role select,.filters select{font:inherit;font-size:12px;border:1px solid var(--line);background:var(--card-2);border-radius:8px;padding:5px 8px;color:var(--ink)}
.trail{list-style:none;margin:10px 0 8px;padding:0;font-size:11.5px;color:var(--ink-2);display:grid;gap:4px;max-height:96px;overflow:auto}
.trail li{display:flex;gap:6px}.trail time{font-family:var(--mono);color:var(--faint);flex:none}
.trail .empty{color:var(--muted)}
#cMoves .abtn{white-space:normal}
#cMoves .hint{grid-column:1/-1;font-size:11.5px;color:var(--muted);margin:0}
.case-foot{display:flex;justify-content:space-between;gap:8px;margin-top:8px;font-size:10.5px;color:var(--faint)}
.lnk{border:0;background:none;padding:0;font:inherit;font-size:11px;color:var(--ocean);cursor:pointer;text-decoration:underline}
.filters{display:grid;grid-template-columns:1.4fr 1fr;gap:6px}
.filters select{min-width:0;width:100%}
.tcard table{table-layout:fixed}
.tcard th:first-child{width:38%}.tcard th:last-child{width:24%}
.tcard td{overflow:hidden;text-overflow:ellipsis}
.filters .search{margin-bottom:8px}
.st{display:inline-block;margin-left:6px;font-size:9.5px;font-weight:700;padding:1px 5px;border-radius:4px;background:var(--card-2);color:var(--muted);vertical-align:1px}
.st.ok{background:color-mix(in srgb, var(--moss) 18%, transparent);color:var(--forest)}
.st.no{background:color-mix(in srgb, var(--crit) 14%, transparent);color:var(--crit)}
.poly.dismissed{opacity:.28}
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
  .dbody{grid-template-columns:minmax(0,1fr) 320px;grid-template-areas:"center right" "left right"}
  .left{flex-direction:row;overflow:visible} .left>.card{flex:1}
  .center{min-height:560px}
}
@media (max-width:820px){
  .dash{overflow:auto;display:block}
  .dbody{display:flex;flex-direction:column}
  .left{flex-direction:column}
  .col{overflow:visible}
  .center{min-height:0;order:-1}
  .map{flex:none;height:64vh}
  .kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
  .tscroll{max-height:320px}
  .tb-sep{display:none}
  .tb-title{flex-basis:100%;order:3}
  .hint{display:none}
  .tl .mono,.tr .mono{display:none}
}
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
    <a class="logo" href="#" data-act="noop">Change<b>Intel</b></a>
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
      <strong>Change<b>Intel</b></strong>
    </button>
    <span class="tb-sep"></span>
    <div class="tb-title"><div id="tbTitle"></div><div id="tbCoords"></div></div>
    <div class="seg" role="group" aria-label="Sector" id="sectorSeg"></div>
    <select class="city-pick" id="cityPick" aria-label="More OSCD cities" hidden></select>
    <div class="seg" role="group" aria-label="Detection engine">
      <button data-act="mode:ai">ChangeIntel AI</button><button data-act="mode:naive">Naive NDVI</button>
    </div>
    <button class="pill" data-act="bench">Benchmark</button>
  </header>

  <div class="dbody">
    <aside class="col left">
      <section class="card rise" style="--d:1">
        <div class="card-h"><h3>Layers</h3>
          <div class="seg seg-sm" role="group" aria-label="Priority mode" id="sevSeg"></div></div>
        <div class="legend" id="legend"></div>
        <label class="slider">Fill <input type="range" id="fill" min="0" max="80" value="35" aria-label="Polygon fill opacity"></label>
      </section>
      <section class="card tcard rise" style="--d:2">
        <div class="card-h"><span>Detections</span><span class="mono" id="tCount"></span></div>
        <div class="filters"><input class="search" id="search" type="search" placeholder="Filter by ID or change type" aria-label="Filter detections">
          <select class="search" id="stateF" aria-label="Filter by case state"></select></div>
        <div class="tscroll">
          <table>
            <thead><tr>
              <th><button data-sort="id">ID</button></th>
              <th><button data-sort="tier">Type</button></th>
              <th class="num"><button data-sort="area">Area m²</button></th>
            </tr></thead>
            <tbody id="tbody"></tbody>
          </table>
        </div>
      </section>
    </aside>

    <section class="center">
      <div class="kpis" id="kpis"></div>
      <div class="map" id="map" data-view="swipe">
        <div class="layer" id="layT1"><div class="world"><img id="imgT1" alt="Before imagery" draggable="false"></div></div>
        <div class="layer" id="layT2"><div class="world"><img id="imgT2" alt="After imagery" draggable="false"></div></div>
        <div class="layer"><div class="world" id="vecWorld"><svg id="vec" viewBox="0 0 100 100" preserveAspectRatio="none"><defs><pattern id="hatch" width="1.4" height="1.4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="1.4" height="1.4" fill="var(--unobs-bg)"/><line x1="0" y1="0" x2="0" y2="1.4" stroke="var(--unobs)" stroke-width=".45"/></pattern></defs><g id="unL"></g><g id="faL"></g><g id="ftL"></g></svg><div id="pins"></div></div></div>
        <div class="curtain" id="curtain"><div class="knob ctl" id="knob" role="slider" tabindex="0" aria-label="Before / after divider" aria-valuemin="0" aria-valuemax="100" aria-valuenow="50">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m9 6-6 6 6 6M15 6l6 6-6 6"/></svg></div></div>
        <div class="ctl tl"><span class="chip">Before<span class="mono" id="d1"></span></span></div>
        <div class="ctl tr"><span class="chip">After<span class="mono" id="d2"></span></span></div>
        <div class="ctl tc"><div class="seg" role="group" aria-label="Imagery view">
          <button data-act="view:before">Before</button><button data-act="view:swipe">Swipe</button><button data-act="view:after">After</button>
        </div></div>
        <div class="banner" id="banner"></div>
        <div class="ctl bl">
          <div class="scalebar"><i id="sbBar"></i><span id="sbTxt"></span></div>
          <span class="chip coords" id="coords">Hover for coordinates</span>
          <span class="hint">Scroll to zoom · drag to pan · ←/→ cycle · F fit</span>
        </div>
        <div class="ctl br">
          <button class="zbtn" data-act="zoom:in" aria-label="Zoom in">+</button>
          <button class="zbtn" data-act="zoom:out" aria-label="Zoom out">−</button>
          <button class="zbtn" data-act="zoom:fit" aria-label="Fit to tile">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg></button>
        </div>
        <div class="tip" id="tip"></div>
      </div>
    </section>

    <aside class="col right">
      <section class="card rise" style="--d:2">
        <div class="ins-top">
          <div><div class="eyebrow">Selected change</div><div class="ins-id" id="iId"></div></div>
          <div class="stepper"><span id="iPos"></span>
            <button class="ibtn" data-act="sel:prev" aria-label="Previous detection"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="m15 6-6 6 6 6"/></svg></button>
            <button class="ibtn" data-act="sel:next" aria-label="Next detection"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg></button>
          </div>
        </div>
        <div class="tags" id="iTags"></div>
        <p class="summary" id="iSum"></p>
        <dl id="iProps"></dl>
        <div class="actions">
          <button class="abtn primary" data-act="focus">Zoom to change</button>
          <button class="abtn" data-act="copy">Copy coordinates</button>
        </div>
      </section>
      <section class="card rise" style="--d:3">
        <div class="card-h"><span>Case</span><span class="mono" id="vBadge"></span></div>
        <div class="case-top"><span class="tag" id="cState"></span>
          <label class="role">Acting as <select id="role" aria-label="Role"></select></label></div>
        <ol class="trail" id="cTrail"></ol>
        <input class="search" id="cNote" type="text" placeholder="Note for the audit log (optional)" aria-label="Case note">
        <div class="actions" id="cMoves"></div>
        <div class="case-foot"><button class="lnk" data-act="case-undo">Undo last action</button><span>Roles are local to this browser, not authenticated.</span></div>
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
          <button class="abtn" data-act="dl:csv">Filtered table<small>.csv</small></button>
          <button class="abtn" data-act="dl:audit">Audit log<small>.json</small></button>
          <button class="abtn" data-act="dl:verdicts" style="grid-column:1/-1">Officer verdicts (training data)<small>.json</small></button>
        </div>
      </section>
    </aside>
  </div>
</div>

<dialog id="bench" aria-labelledby="benchH">
  <div class="dlg">
    <div class="dlg-h"><h2 id="benchH">LEVIR-CD benchmark</h2><button class="ibtn" data-act="bench-close" aria-label="Close">✕</button></div>
    <p id="benchP"></p>
    <table><thead><tr><th>Metric</th><th class="num">Naive spectral</th><th class="num">ChangeIntel AI</th><th class="num">Change</th></tr></thead><tbody id="benchRows"></tbody></table>
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
      <p id="bObjP"></p><table><thead><tr><th>Object size</th><th class="num">Objects</th><th class="num">ChangeIntel</th><th class="num">Naive</th></tr></thead><tbody id="bObjRows"></tbody></table></section>
    <section id="bCreep" hidden><div class="stress-h"><h3>Slow change: consecutive vs anchored comparison</h3></div>
      <p id="bCreepP"></p><div class="sleg" id="bCreepLeg"></div><div id="bCreepRows"></div><div class="note" id="bCreepNote"></div></section>
    <section id="bFar" hidden><div class="stress-h"><h3>False alarms per 100 km² of unchanged land</h3></div>
      <p id="bFarP"></p><table><thead><tr><th>Dataset</th><th class="num">ChangeIntel</th><th class="num">Naive NDVI</th><th class="num">Index rules</th></tr></thead><tbody id="bFarRows"></tbody></table>
      <div class="note" id="bFarNote"></div></section>
    <p class="fine" id="bRun"></p>
  </div>
</dialog>
<div class="toast" id="toast" role="status" aria-live="polite"></div>

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

const S = {th:KEYS[0], role:(() => { try { return localStorage.getItem('ci-role') || 'Analyst'; } catch (e) { return 'Analyst'; } })(), stF:'all', sev:'encroachment', sel:0, mode:'ai', lang:'en', view:'swipe', hidden:new Set(), q:'', sort:{k:'area', d:-1}, stage:'hero'};
const sc = () => D.scenes[S.th];
// creep & precursor polygons (multi-year series) join the detection list when their layer is on
const creepFeats = () => (sc().creep && !S.hideCreep) ? sc().creep.features : [];
const feats = () => sc().features.concat(creepFeats());
const FA = () => sc().naive.false_alarms;
/* Officer case workflow (Ideation Baseline #13, browser-only). The audit log is the single source of truth:
   a case's state is the "to" of its last entry. */
const CASE_STATES = ['New','Under review','Field verification','Confirmed','Reported','Resolved','Dismissed'];
const CASE_MOVES = [   // from, to, role allowed, button label
  ['New','Under review','Analyst','Start review'],
  ['Under review','Field verification','Analyst','Send for field check'],
  ['Under review','Dismissed','Analyst','Dismiss as false alarm'],
  ['Field verification','Confirmed','Field officer','Confirm on site'],
  ['Field verification','Dismissed','Field officer','Not found on site'],
  ['Confirmed','Reported','DDMA','Report / file with DDMA'],
  ['Reported','Resolved','DDMA','Mark resolved'],
  ['Dismissed','Under review','Analyst','Reopen'],
];
const ROLES = ['Analyst','Field officer','DDMA'];
const VERIFIED = new Set(['Confirmed','Reported','Resolved']);
const ST_SHORT = {'Under review':['REV',''], 'Field verification':['FLD',''], Confirmed:['✓','ok'], Reported:['RPT','ok'], Resolved:['RES','ok'], Dismissed:['✕','no']};
let audit = [];
try { audit = JSON.parse(localStorage.getItem('ci-audit') || '[]'); } catch (e) {}
const saveAudit = () => { try { localStorage.setItem('ci-audit', JSON.stringify(audit)); } catch (e) {} };
const caseLog = (f, th = S.th) => audit.filter(e => e.sector === th && e.case === f.id);
const caseState = f => { const l = caseLog(f); return l.length ? l[l.length - 1].to : 'New'; };
const stChip = f => { const st = ST_SHORT[caseState(f)]; return st ? `<span class="st ${st[1]}" title="${caseState(f)}">${st[0]}</span>` : ''; };

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
  V.s = s; V.x = r.width/2 - cx*s; V.y = r.height/2 - cy*s;
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
function rows(){
  const q = S.q, {k, d} = S.sort;
  return feats().map((f, i) => ({f, i}))
    .filter(({f}) => !S.hidden.has(f.tier) && (!q || `${f.id} ${f.type} ${f.tier}`.toLowerCase().includes(q))
      && (S.stF === 'all' || (S.stF === 'open' ? !['Dismissed', 'Resolved'].includes(caseState(f)) : caseState(f) === S.stF)))
    .sort((a, b) => d*(k === 'area' ? a.f.area_sqm - b.f.area_sqm
                     : k === 'tier' ? tierRank(a.f.tier) - tierRank(b.f.tier) || a.f.area_sqm - b.f.area_sqm
                     : a.f.id.localeCompare(b.f.id)));
}
function renderHeader(){
  const g = sc(), b = g.bounds;
  $('#tbTitle').textContent = `${g.label} · ${g.sensor}`;
  if ($('#cityPick')) { $('#cityPick').value = MORE.includes(S.th) ? S.th : ''; $('#cityPick').classList.toggle('on', MORE.includes(S.th)); }
  $('#sevSeg').innerHTML = Object.entries(SEV_MODES).map(([k, l]) => `<button data-act="sev:${k}">${l}</button>`).join('');
  $('#tbCoords').textContent = `${fLat(b.n)} – ${fLat(b.s)} · ${fLon(b.w)} – ${fLon(b.e)}`;
  [$('#d1').textContent, $('#d2').textContent] = g.dates;
  $$('[data-act]').forEach(b => {
    const [k, v] = b.dataset.act.split(':');
    const key = {th:'th', mode:'mode', lang:'lang', view:'view', sev:'sev'}[k];
    if (key) b.setAttribute('aria-pressed', S[key] === v);
  });
  map.dataset.view = S.view; map.classList.toggle('naive', S.mode === 'naive');
}
function renderKpis(){
  const fs = feats(), nv = sc().naive, naive = S.mode === 'naive';
  const sum = a => a.reduce((t, f) => t + f.area_sqm, 0), area = sum(fs);
  const crit = fs.filter(f => f.tier === 'Critical').length, high = fs.filter(f => f.tier === 'High').length;
  const k = naive ? [
    ['Regions flagged', fmt(nv.regions), '', `|ΔNDVI| > ${nv.threshold} · no filtering`],
    ['Area flagged', fmt(nv.area_sqm), 'm²', `${fmt(nv.area_sqm/area || 0, 1)}× ChangeIntel area`],
    ['False alarms', fmt(nv.false_alarms.length), '', nv.reference === 'ground truth' ? 'off ground truth' : 'unconfirmed by ChangeIntel'],
    ['False-alarm rate', pct(NV.false_alarm_rate), '', 'naive · LEVIR-CD'],
  ] : [
    ['Detections', fs.length, fs.length === 1 ? 'polygon' : 'polygons', `vs ${fmt(nv.regions)} naive regions`],
    ['Changed area', fmt(area), 'm²', `${fmt(area/10000, 2)} ha, UTM metric` + (sc().unobservable?.pct > 0 ? ` · ${sc().unobservable.pct.toFixed(1)}% not observable` : '')],
    ['Priority sites', crit + high, '', `${crit} critical · ${high} high`],
    ['False-alarm rate', pct(AI.false_alarm_rate), '', `vs ${pct(NV.false_alarm_rate)} naive · LEVIR-CD`],
  ];
  $('#kpis').innerHTML = k.map(([l, v, u, s], i) =>
    `<div class="kpi rise" style="--d:${i}"><div class="kpi-l">${l}</div><div class="kpi-v"${i === 3 || (naive && i === 2) ? ` style="color:${naive ? 'var(--fa)' : 'var(--forest)'}"` : ''}>${v}${u ? `<small>${u}</small>` : ''}</div><div class="kpi-s">${s}</div></div>`).join('');
}
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
  const u = sc().unobservable;
  if (u && u.pct > 0) h += `<label class="lg-row${S.hideUnobs ? ' off' : ''}"><input type="checkbox" data-layer="unobs"${S.hideUnobs ? '' : ' checked'}>
      <span class="sw hatch"></span>Unobservable<span class="n">${u.pct.toFixed(1)}%</span></label>`;
  if (S.mode === 'naive') h += `<div class="lg-row fa"><span class="sw" style="--c:var(--fa);margin-left:23px"></span>Naive false alarms<span class="n">${fa.length}</span></div>`;
  $('#legend').innerHTML = h;
}
function renderTable(){
  const r = rows();
  $('#tbody').innerHTML = r.length ? r.map(({f, i}) =>
    `<tr data-row="${i}" aria-selected="${i === S.sel}"><td class="mono">${f.id}${stChip(f)}</td><td><span class="dot" style="--c:${TIER_VAR[f.tier]}"></span>${SHORT[f.type] || f.type}</td><td class="num mono">${fmt(f.area_sqm)}</td></tr>`).join('')
    : `<tr><td colspan="3" class="empty">No detections match these filters.</td></tr>`;
  $('#tCount').textContent = `${r.length} of ${feats().length}`;
  $$('th button').forEach(b => b.textContent = b.textContent.replace(/ [↑↓]$/, '') + (b.dataset.sort === S.sort.k ? (S.sort.d < 0 ? ' ↓' : ' ↑') : ''));
}
const pts = a => a.map(p => p.join(',')).join(' ');
function renderUnobs(){
  const u = sc().unobservable;
  $('#unL').innerHTML = u && !S.hideUnobs ? u.polygons.map(p => `<polygon class="unobs" data-un="1" points="${pts(p)}"/>`).join('') : '';
}
function renderNaive(){
  $('#faL').innerHTML = S.mode === 'naive' ? FA().map((fa, i) => `<polygon class="fa" data-fa="${i}" points="${pts(fa.pts)}"/>`).join('') : '';
}
function faText(fa){
  const nv = sc().naive;
  const ref = nv.reference === 'ground truth'
    ? `${Math.round(fa.overlap*100)}% overlaps ground-truth change`
    : `not flagged by ChangeIntel (${Math.round(fa.overlap*100)}% overlap) · no ground truth for this tile`;
  return `${fa.id} · ${SHORT[fa.type] || fa.type} · ${fmt(fa.area_sqm)} m² · ${ref}`;
}
function renderMap(){
  let h = '';
  feats().forEach((f, i) => {
    if (S.hidden.has(f.tier)) return;
    if (i === S.sel) h += `<polygon class="halo" points="${pts(f.pts)}"/>`;
    h += `<polygon class="poly${f.kind ? ' creep' : ''}${caseState(f) === 'Dismissed' ? ' dismissed' : ''}${i === S.sel ? ' sel' : ''}" data-i="${i}" style="--c:${TIER_VAR[f.tier]}" points="${pts(f.pts)}"/>`;
  });
  $('#ftL').innerHTML = h;
  $('#pins').innerHTML = feats().map((f, i) =>
    `<span class="pin${i === S.sel ? ' sel' : ''}" data-i="${i}" style="--c:${TIER_VAR[f.tier]};left:${f.cx}%;top:${f.cy}%;${S.hidden.has(f.tier) ? 'display:none' : ''}"></span>`).join('');
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
function renderInspector(){
  const f = feats()[S.sel]; if (!f) return;
  const r = rows(), pos = r.findIndex(x => x.i === S.sel);
  $('#iId').textContent = f.id;
  $('#iPos').textContent = pos >= 0 ? `${pos + 1}/${r.length}` : '';
  $('#iTags').innerHTML = `<span class="tag" style="--c:${TIER_VAR[f.tier]}">${f.tier}</span><span class="tag plain">${f.type}</span>`;
  $('#iSum').textContent = f.summary;
  $('#iProps').innerHTML = (f.series ? `<dt>NDBI / year</dt><dd>${spark(f.series, sc().creep.years)}</dd>` : '') + [
    ['Area', `${fmt(f.area_sqm, 1)} m²`, 1],
    ['Magnitude', `<span class="bar" style="--c:${TIER_VAR[f.tier]}"><i style="width:${f.magnitude*100}%"></i></span>${f.magnitude.toFixed(3)}`, 1],
    ['Action', f.priority.replace(/^Priority (\d) - /, 'P$1 · ')],
    ['Score', `<span title="norm. area × magnitude × type weight (${SEV_MODES[S.sev]}) × exposure">${(f.score/100).toFixed(2)} = ${f.parts.norm_area.toFixed(2)} × ${f.magnitude.toFixed(2)} × ${(D.severity.weights[S.sev][f.type] ?? 0.5).toFixed(2)} × ${f.parts.exposure.toFixed(2)}</span>`, 1],
    ['Exposure', f.exposure],
    ['Buffer check', f.violation],
    ['Centroid', `${fLat(f.lat)}<br>${fLon(f.lon)}`, 1],
  ].filter(([, v]) => v).map(([k, v, m]) => `<dt>${k}</dt><dd${m ? ' class="mono"' : ''}>${v}</dd>`).join('');
  $('#capId').textContent = f.id;
  renderVerify();
}
function renderVerify(){
  const f = feats()[S.sel]; if (!f) return;
  const st = caseState(f), log = caseLog(f);
  // field precision for this sector: confirmed / (confirmed + dismissed), from officer verdicts
  const states = feats().map(caseState), ok = states.filter(x => VERIFIED.has(x)).length, no = states.filter(x => x === 'Dismissed').length;
  $('#vBadge').textContent = ok + no ? `field precision ${Math.round(ok / (ok + no) * 100)}% · ${ok}/${ok + no}` : 'no verdicts yet';
  $('#cState').textContent = `${f.id} · ${st}`;
  $('#cState').style.setProperty('--c', VERIFIED.has(st) ? 'var(--moss)' : st === 'Dismissed' ? 'var(--crit)' : 'var(--ocean)');
  $('#role').innerHTML = ROLES.map(r => `<option${r === S.role ? ' selected' : ''}>${r}</option>`).join('');
  $('#cTrail').innerHTML = log.length ? log.slice(-4).reverse().map(e =>
    `<li><time>${e.ts.slice(5, 16).replace('T', ' ')}</time><span>${e.role}: ${e.from} → <b>${e.to}</b>${e.note ? ` · ${xmlEsc(e.note)}` : ''}</span></li>`).join('')
    : '<li class="empty">AI detected · no officer action yet.</li>';
  const moves = CASE_MOVES.map((m, i) => [m, i]).filter(([m]) => m[0] === st && m[2] === S.role);
  const others = CASE_MOVES.filter(m => m[0] === st && m[2] !== S.role).map(m => m[2]);
  $('#cMoves').innerHTML = moves.length
    ? moves.map(([m, i]) => `<button class="abtn ${m[1] === 'Dismissed' ? 'bad' : 'good'}" data-act="case:${i}">${m[3]}</button>`).join('')
    : `<p class="hint">${st === 'Resolved' ? 'Case closed.' : `No ${S.role} action at this stage${others.length ? `; next step is for ${[...new Set(others)].join(' / ')}` : ''}.`}</p>`;
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
    + (nv.reference === 'ground truth' ? '' : ` <b>Note:</b> this tile has no usable ground truth, so naive regions are checked against ChangeIntel's own detections. Treat this view as a picture of baseline noise, not a measured accuracy score.`);
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
  $('#lkList').innerHTML = ps.map(p => `<option value="${placeName(p)}">`).join('');
  if (!ps.length) { out.hidden = false; out.style.removeProperty('--c'); out.textContent = l.off; return; }
  if (!S.lk) { out.hidden = true; return; }
  out.hidden = false;
  const pl = S.lk.place;
  if (!pl) { out.style.removeProperty('--c'); out.textContent = l.none(S.lk.q); return; }
  // citizens see officer-verified cases only (Ideation Baseline: unverified alerts must not reach the public)
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
function renderAll(){ renderHeader(); renderKpis(); renderLegend(); renderTable(); renderUnobs(); renderNaive(); renderMap(); renderInspector(); renderAdvisory(); renderLookup(); renderBanner(); }

function select(i, flyTo){
  S.sel = i; renderMap(); renderInspector(); renderAdvisory();
  $$('#tbody tr').forEach(tr => tr.setAttribute('aria-selected', +tr.dataset.row === i));
  $(`#tbody tr[data-row="${i}"]`)?.scrollIntoView({block:'nearest'});
  if (flyTo) flyToFeature(i);
}
function step(d){
  const r = rows(); if (!r.length) return;
  const pos = r.findIndex(x => x.i === S.sel);
  select(r[(pos + d + r.length) % r.length].i, true);
}

async function loadTheater(th){
  S.th = th; S.sev = sc().default_mode || 'encroachment'; applySev(); S.hidden.clear(); S.q = ''; $('#search').value = ''; S.lk = null; $('#lkIn').value = '';
  const fs = feats();
  fs.forEach(f => { const xs = f.pts.map(p => p[0]), ys = f.pts.map(p => p[1]);
    f._span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)); });
  S.sel = fs.map((f, i) => i).sort((a, b) => tierRank(fs[b].tier) - tierRank(fs[a].tier) || fs[b].area_sqm - fs[a].area_sqm)[0];
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
  const st = caseState(f), last = caseLog(f).filter(e => VERIFIED.has(e.to))[0];
  return VERIFIED.has(st)
    ? `Field-confirmed by ${last.role} on ${last.ts.slice(0, 10)}${last.note ? ` (${last.note})` : ''}; case state ${st}. Draft awaiting DDMA sign-off.`
    : `Draft alert generated by ChangeIntel AI. Not yet field-verified (case state: ${st}). Awaiting official verification and sign-off by the District Disaster Management Authority (DDMA).`;
}
function capXml(f){
  const crit = f.tier === 'Critical', la = f.lat, lo = f.lon;
  const sent = new Date().toISOString().replace(/\.\d+Z$/, '+00:00');
  const uid = Math.random().toString(16).slice(2, 8).toUpperCase();
  const ring = f.ring.slice();
  const [a, z] = [ring[0], ring[ring.length - 1]];
  if (a[0] !== z[0] || a[1] !== z[1]) ring.push(a);
  return `<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>IND-SACHET-${sent.slice(0, 10).replace(/-/g, '')}-${f.id}-${uid}</identifier>
  <sender>ChangeIntel-SatelliteEngine@ndma.gov.in</sender>
  <sent>${sent}</sent>
  <status>Draft</status>
  <msgType>Alert</msgType>
  <scope>Restricted</scope>
  <restriction>For Official Authorization Only</restriction>
  <note>${xmlEsc(capNote(f))}</note>
  <info>
    <language>en-IN</language>
    <category>Geo</category>
    <event>Rapid Structural Change / Damage Anomaly</event>
    <urgency>${crit ? 'Immediate' : 'Expected'}</urgency>
    <severity>${crit ? 'Extreme' : 'Severe'}</severity>
    <certainty>Observed</certainty>
    <headline>${xmlEsc(`Satellite Change Alert: ${f.area_sqm} m² ${f.type} Detected`)}</headline>
    <description>${xmlEsc(`Bi-temporal satellite intelligence detected a change footprint of ${f.area_sqm} m² at (${la.toFixed(6)}, ${lo.toFixed(6)}) with confidence ${(f.magnitude*100).toFixed(1)}%. Classification: ${f.type}. ${f.summary}`)}</description>
    <instruction>Field officers to verify on site. Satellite encroachment flags are screening results: check against Development Plan and CRZ maps before any regulatory action.</instruction>
    <area>
      <areaDesc>${xmlEsc(`${sc().label}: footprint near (${la.toFixed(6)}, ${lo.toFixed(6)})`)}</areaDesc>
      <polygon>${ring.map(([y, x]) => `${y.toFixed(6)},${x.toFixed(6)}`).join(' ')}</polygon>
    </area>
  </info>
</alert>
`;
}
function csv(){
  const q = v => `"${String(v).replace(/"/g, '""')}"`;
  const head = ['feature_id','severity_tier','change_type','area_sqm','magnitude','centroid_lat','centroid_lon','action_priority','case_state'];
  return [head.join(',')].concat(rows().map(({f}) => {
    return [f.id, f.tier, q(f.type), f.area_sqm, f.magnitude, f.lat.toFixed(6), f.lon.toFixed(6), q(f.priority), q(caseState(f))].join(',');
  })).join('\n');
}
const DL = {
  geojson: () => download(D.files[S.th].geojson, `${S.th}_change_intelligence.geojson`, 'application/geo+json'),
  gpkg: () => download(bytes(D.files[S.th].gpkg), `${S.th}_change_intelligence.gpkg`, 'application/geopackage+sqlite3'),
  cap: () => { const f = feats()[S.sel];
    if (caseState(f) === 'Dismissed') return toast(`${f.id} was dismissed as a false alarm: no alert drafted`);
    download(capXml(f), `sachet_cap_${S.th}_${f.id}.xml`, 'application/xml'); },
  audit: () => download(JSON.stringify(audit, null, 1), 'changeintel_audit_log.json', 'application/json'),
  verdicts: () => download(JSON.stringify(KEYS.flatMap(th => D.scenes[th].features.concat(D.scenes[th].creep ? D.scenes[th].creep.features : [])
      .map(f => [f, caseLog(f, th)]).filter(([, l]) => l.length && (VERIFIED.has(l[l.length - 1].to) || l[l.length - 1].to === 'Dismissed'))
      .map(([f, l]) => ({sector: th, id: f.id, verdict: l[l.length - 1].to === 'Dismissed' ? 'false_alarm' : 'confirmed',
        state: l[l.length - 1].to, decided_at: l[l.length - 1].ts, change_type: f.type, area_sqm: f.area_sqm, ring_latlon: f.ring}))), null, 1),
    'changeintel_officer_verdicts.json', 'application/json'),
  sitrep: () => download(bytes(D.files[S.th].sitrep), `ChangeIntel_SitRep_${S.th}.pdf`, 'application/pdf'),
  csv: () => download(csv(), `${S.th}_detections.csv`, 'text/csv'),
};

/* ============================================================
   ACTIONS (delegated)
   ============================================================ */
document.addEventListener('click', e => {
  const el = e.target.closest('[data-act]'); if (!el) return;
  e.preventDefault();
  const [k, v] = el.dataset.act.split(':');
  switch (k) {
    case 'fly': fly(v in D.scenes ? v : KEYS[0], 1); break;
    case 'back': if (S.stage === 'dash') fly(S.th, -1); break;
    case 'th': if (v !== S.th) { loadTheater(v).then(() => toast(`Loaded ${D.scenes[v].label}`)); } break;
    case 'mode': S.mode = v; renderHeader(); renderKpis(); renderLegend(); renderNaive(); break;
    case 'sev': S.sev = v; applySev(); renderAll(); toast(`${SEV_MODES[v]} priorities: tiers re-ranked`); break;
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
    case 'case': {
      const f = feats()[S.sel], [from, to] = CASE_MOVES[+v];
      if (caseState(f) !== from) break;
      audit.push({ts: new Date().toISOString(), sector: S.th, case: f.id, from, to, role: S.role, note: $('#cNote').value.trim()});
      saveAudit(); $('#cNote').value = '';
      renderVerify(); renderTable(); renderMap(); renderLookup();
      toast(`${f.id}: ${from} → ${to}`);
      break; }
    case 'case-undo': {
      const e = audit.pop(); if (!e) { toast('Nothing to undo'); break; }
      saveAudit(); renderVerify(); renderTable(); renderMap(); renderLookup();
      toast(`Undid ${e.case}: ${e.from} → ${e.to}`);
      break; }
    case 'dl': DL[v](); break;
    case 'bench': $('#bench').showModal(); break;
    case 'bench-close': $('#bench').close(); break;
    case 'stress': renderStress(v); break;
  }
});
$('#tbody').addEventListener('click', e => { const tr = e.target.closest('[data-row]'); if (tr) select(+tr.dataset.row, true); });
$('#tbody').addEventListener('pointerover', e => {
  const tr = e.target.closest('[data-row]');
  $$('.poly.hl').forEach(p => p.classList.remove('hl'));
  if (tr) $(`.poly[data-i="${tr.dataset.row}"]`)?.classList.add('hl');
});
$('#legend').addEventListener('change', e => {
  if (e.target.dataset.layer === 'unobs') { S.hideUnobs = !e.target.checked; renderLegend(); renderUnobs(); return; }
  if (e.target.dataset.layer === 'creep') { S.hideCreep = !e.target.checked; S.sel = Math.min(S.sel, feats().length - 1); renderAll(); return; }
  const t = e.target.dataset.tier; if (!t) return;
  e.target.checked ? S.hidden.delete(t) : S.hidden.add(t);
  renderLegend(); renderTable(); renderMap(); renderInspector();
});
$$('th button').forEach(b => b.addEventListener('click', () => {
  const k = b.dataset.sort; S.sort = {k, d:S.sort.k === k ? -S.sort.d : (k === 'id' ? 1 : -1)}; renderTable(); renderInspector();
}));
$('#lookup').addEventListener('submit', e => {
  e.preventDefault();
  const q = $('#lkIn').value.trim(); if (!q) return;
  S.lk = {q, place: findPlace(q)};
  renderLookup();
  if (S.lk.place && S.lk.nearest !== undefined) select(S.lk.nearest, true);
});
$('#role').addEventListener('change', e => { S.role = e.target.value; try { localStorage.setItem('ci-role', S.role); } catch (err) {} renderVerify(); });
$('#stateF').innerHTML = [['all','All states'],['open','Open cases'], ...CASE_STATES.map(x => [x, x])].map(([v, l]) => `<option value="${v}">${l}</option>`).join('');
$('#stateF').addEventListener('change', e => { S.stF = e.target.value; renderTable(); renderInspector(); });
$('#search').addEventListener('input', e => { S.q = e.target.value.trim().toLowerCase(); renderTable(); renderInspector(); });
$('#fill').addEventListener('input', e => $('#vec').style.setProperty('--fill', e.target.value/100));
$('#bench').addEventListener('click', e => { if (e.target === e.currentTarget) e.currentTarget.close(); });
addEventListener('keydown', e => {
  if (S.stage !== 'dash' || flying || e.target.closest('input, dialog[open]') || e.metaKey || e.ctrlKey) return;
  const r = map.getBoundingClientRect();
  const act = {ArrowRight:() => step(1), ArrowLeft:() => step(-1), j:() => step(1), k:() => step(-1),
    f:() => fitView(true), '+':() => zoomAt(1.6, r.width/2, r.height/2, true), '=':() => zoomAt(1.6, r.width/2, r.height/2, true),
    '-':() => zoomAt(1/1.6, r.width/2, r.height/2, true), '1':() => $('[data-act="view:before"]').click(),
    '2':() => $('[data-act="view:swipe"]').click(), '3':() => $('[data-act="view:after"]').click()}[e.key];
  if (act) { e.preventDefault(); act(); }
});
let rT; addEventListener('resize', () => { clearTimeout(rT); rT = setTimeout(() => { if (S.stage === 'dash') fitView(false); }, 120); });

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
const ST = D.stress, ST_M = [['ai_raw','ChangeIntel','var(--forest)'],['ai_stable','+ stable-pixel normalisation','var(--ocean)'],['ai_hist_matched','+ histogram matching','var(--minor)'],['naive','Naive spectral','var(--fa)']]
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
    $('#bObjP').textContent = `A ground-truth object counts as found when detections cover at least half of it. ${B.dataset}, ${fmt(a.gt_objects)} objects. Object precision (IoU > 0.5): ChangeIntel ${r(a.precision_iou50)}, naive ${r(n.precision_iou50)}.`;
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
  // in-domain (0.5 m) the low ChangeIntel figure is a win; at 10 m it is low because the model barely fires, so it is starred
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
    if (B.oscd) $('#bFarNote').innerHTML = `<b>* Not a win:</b> ChangeIntel's model was trained on 0.5 m aerial images and barely fires on 10 m Sentinel-2 (OSCD F1 ${r(B.oscd.changeintel_ai_engine.f1_score)}; naive ${r(B.oscd.naive_spectral_baseline.f1_score)}, index rules ${r(B.oscd.spectral_index_rules.f1_score)}), so it also flags almost nothing on unchanged land. Use LEVIR-CD for its accuracy. The seasonal row shows what naive NDVI does across a monsoon-to-dry-season pair.`;
  }
  if (B.runtime) $('#bRun').textContent = `Runtime: ${B.runtime.s_per_km2} s per km² at 0.5 m (${B.runtime.megapixels_per_s} megapixels/s, model inference on Apple M5 Max). At 10 m that is ${(B.runtime.s_per_km2 / 400).toFixed(4)} s per km².`;
})();

/* benchmark dialog + hero meta from data */
(() => {
  const rowsB = [['F1-score','f1_score'],['IoU','iou'],['Precision','precision'],['Recall','recall'],['False-alarm rate','false_alarm_rate']];
  $('#benchRows').innerHTML = rowsB.map(([l, k]) => {
    const lower = k === 'false_alarm_rate', rel = (AI[k] - NV[k])/NV[k]*100;
    return `<tr><td><b>${l}</b></td><td class="num mono${lower ? ' lose' : ''}">${pct(NV[k])}</td><td class="num mono win">${pct(AI[k])}</td><td class="num mono win">${rel > 0 ? '+' : ''}${rel.toFixed(1)}%</td></tr>`;
  }).join('');
  $('#benchP').textContent = `Fine-tuned Bitemporal Transformer (BIT) vs. a naive spectral-difference baseline, evaluated on the ${B.dataset || "LEVIR-CD test split"} (${B.evaluation_samples_count} image pairs, pixel counts pooled).`;
  $('#benchNote').innerHTML = `<b>Takeaway:</b> naive spectral differencing mistakes seasonal vegetation and sun-angle shifts for change (${pct(NV.false_alarm_rate)} false alarms). ChangeIntel cuts false alarms by <b>${B.false_alarm_reduction_percentage}%</b> to ${pct(AI.false_alarm_rate)}.`;
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

html = TEMPLATE.replace('/*__DATA__*/null', json.dumps(DATA, ensure_ascii=False).replace('</', '<\\/'))
(ROOT / 'web/index.html').write_text(html, encoding='utf-8')
print(f"Wrote web/index.html ({len(html) / 1e6:.2f} MB)")
