/* caselogic.js - one case's facts and every sentence the console says about it.
 *
 * The Change-to-Action Card (#43), the attention views (#46) and the "Explain this change" copilot (#45)
 * all read the same facts bundle, so the card, the list and the copilot never disagree. Offline, the copilot
 * answers its suggested questions from the bundle; online (console served by src/server/app.py) free-text
 * questions go to /api/explain. Either way every number shown must be in the bundle: validate() is the same
 * rule as src/exporters/grounding.py.
 *
 * Inlined into web/index.html by scripts/build_frontend_light.py; tests/test_caselogic.mjs runs it on real cases.
 */
(function (root) {
  'use strict';

  const PLAIN = {
    'Water / Flood Inundation': 'New water: flooding or inundation',
    'Vegetation Loss / Clearing': 'Vegetation removed',
    'Vegetation Regrowth': 'Vegetation grew back',
    'New Building / Structure': 'New building or structure',
    'New Built-up Surface': 'New built-up surface (construction)',
    'Vegetation Cleared / Possible Construction': 'Land cleared, possibly for construction',
    'Ground Disturbance': 'Ground disturbed, no clear type',
    'Water-body Encroachment': 'Water body filled and built on',
    'Burn Scar': 'Burnt land',
    'Seasonal Vegetation Change': 'Seasonal vegetation change',
    'Slow Built-up Creep': 'Slow, year-by-year construction',
    'Precursor: Cleared Plot': 'Plot cleared, often the first step before building',
    'Precursor: New Track': 'New access track',
    'Structural Change': 'Structural change',
  };
  const BUILT = new Set(['New Built-up Surface', 'New Building / Structure', 'Vegetation Cleared / Possible Construction',
    'Water-body Encroachment', 'Slow Built-up Creep', 'Structural Change']);
  const INDEX_NAME = {ndbi: 'NDBI (built-up index)', ndvi: 'NDVI (vegetation index)', mndwi: 'MNDWI (water index)', nbr: 'NBR (burn index)'};
  const OPEN_STATES = new Set(['New', 'Under review', 'Field verification', 'Confirmed', 'Reported']);
  const VERIFIED = new Set(['Confirmed', 'Reported', 'Resolved']);
  // uncertainty rule (#46): any of these makes a case "Uncertain"
  const NEAR_THRESHOLD = 0.15, LOW_COMPARABILITY = 60, NEAR_CLOUD = 0.10;
  const RULES = {exposure_radius_m: 500, crz_buffer_m: 50, ndbi_rise: 0.10, ndvi_drop: 0.15, mndwi_rise: 0.20, nbr_drop: 0.25,
                 dnbr_burn: 0.27, comparability_low: LOW_COMPARABILITY};

  const r2 = v => Math.round(v * 100) / 100, r3 = v => Math.round(v * 1000) / 1000;
  const fmtN = (v, d = 0) => Number(v).toLocaleString('en-US', {maximumFractionDigits: d, minimumFractionDigits: d});
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const fmtDate = iso => { const [y, m, d] = iso.split('-').map(Number); return `${d} ${MON[m - 1]} ${y}`; };
  const monthYear = iso => { const [y, m] = iso.split('-').map(Number); return `${MON[m - 1]} ${y}`; };

  /* ---------- facts bundle ---------- */
  function facts(f, sc, ctx) {
    ctx = ctx || {};
    const mode = ctx.mode || sc.default_mode || 'encroachment';
    const weight = ctx.weights ? (ctx.weights[mode][f.type] ?? 0.5) : null;
    const det = sc.detector || {};
    const comp = sc.passport && sc.passport.comparability;
    const t = f.temporal, frames = sc.timeline ? sc.timeline.frames : null;
    const thr = f.thr != null ? f.thr : (det.threshold ?? 0.5);
    const margin = (f.magnitude - thr) / Math.max(1 - thr, 1e-6);
    const out = {
      id: f.id, sector: sc.label, place: sc.place,
      location: {near: f.place ? f.place.name : null, near_m: f.place ? f.place.dist_m : null, lat: f.lat, lon: f.lon},
      change: {type: f.type, plain: PLAIN[f.type] || f.type, summary: f.summary, area_sqm: Math.round(f.area_sqm),
               area_ha: r2(f.area_sqm / 1e4), before: sc.dates[0], after: sc.dates[1], layer: f.kind ? 'multi-year series' : 'image pair'},
      priority: {tier: f.tier, mode, score: r2(f.score / 100), action: f.priority,
                 parts: {area: f.parts.norm_area, signal: f.magnitude, type_weight: weight, exposure: f.parts.exposure}},
      exposure: {assets: f.exposure || null, buffer_check: f.violation || null, protected_share: f.zone ?? 0},
      reliability: {
        signal: r3(f.magnitude), threshold: r3(thr), margin: r2(margin),
        comparability: comp ? {score: comp.score, band: comp.band, main_factor: comp.factors[0].detail} : null,
        near_unobservable_pct: Math.round((f.near_unobs || 0) * 100),
        detector: {name: det.name, f1: det.f1 != null ? det.f1 : null, benchmark: det.benchmark || null,
                   object_precision: det.object_precision ?? null},
      },
      indices: f.idx || {},
      status: ctx.state || 'New', assignee: ctx.assignee || null,
      history: (ctx.log || []).map(e => ({when: e.ts.slice(0, 16).replace('T', ' '), who: e.actor ? `${e.actor} (${e.role})` : e.role,
                                          action: e.action || `${e.from} to ${e.to}`, note: e.note || null})),
      merged_fragments: ctx.fragments || [],
      duplicate_of: f.dup_of || null,
      rules: RULES,
    };
    if (t && t.assessed && frames) {
      if (t.recovery) {
        const rec = t.recovery, revisits = frames.slice(2);
        out.temporal = {kind: 'recovery', index: INDEX_NAME[t.index], metric: rec.metric, status: rec.status,
          revisits: revisits.map((fr, i) => ({date: fr.date, value: rec.per_revisit[i] == null ? null : Math.round(rec.per_revisit[i] * 100)}))};
      } else {
        const fs = t.first_seen != null ? frames[t.first_seen].date : null, lc = t.last_clear != null ? frames[t.last_clear].date : null;
        out.temporal = {kind: 'series', index: INDEX_NAME[t.index], first_seen: fs, last_clear: lc, pre_existing: !!t.pre_existing,
          persisted: t.persist ? t.persist[0] : 0, later_images: t.persist ? t.persist[1] : 0, persistent: t.persistent,
          reverted: t.reverted != null ? frames[t.reverted].date : null,
          seasonal: t.seasonal ? {verdict: t.seasonal.verdict, change: t.seasonal.change, swing: t.seasonal.swing, noise: t.seasonal.noise} : null,
          series_from: frames[0].date, series_to: frames[frames.length - 1].date};
      }
    } else out.temporal = null;
    return out;
  }

  /* ---------- uncertainty (#46) ---------- */
  function uncertain(F) {
    const why = [], R = F.reliability, T = F.temporal;
    if (R.margin < NEAR_THRESHOLD) why.push('signal close to the detection threshold');
    if (R.comparability && R.comparability.score < LOW_COMPARABILITY) why.push('the two images are hard to compare');
    if (F.change.type === 'Seasonal Vegetation Change' || (T && T.seasonal && T.seasonal.verdict === 'seasonal')) why.push('may be seasonal');
    if (T && T.seasonal && T.seasonal.verdict === 'not confirmed') why.push('the yearly images do not show it clearly');
    if (T && T.kind === 'series' && T.persistent === false) why.push('did not hold in later images');
    if (R.near_unobservable_pct >= NEAR_CLOUD * 100) why.push('cloud or missing data next to it');
    return why;
  }

  /* ---------- card sentences (#43) ---------- */
  const signalWord = m => m >= 0.5 ? 'Strong' : m >= NEAR_THRESHOLD ? 'Moderate' : 'Weak';
  function firstSeen(F) {
    const T = F.temporal;
    if (T && T.kind === 'series') {
      if (T.pre_existing) return `Already under way before the ${F.change.before} image: first visible by ${monthYear(T.first_seen || T.series_from)}.`;
      if (T.first_seen) return T.last_clear ? `First visible between ${monthYear(T.last_clear)} and ${monthYear(T.first_seen)}.`
                                            : `First visible by ${monthYear(T.first_seen)}.`;
      return `Not visible in the yearly images from ${monthYear(T.series_from)} to ${monthYear(T.series_to)}.`;
    }
    return `Between the ${F.change.before} and ${F.change.after} images.`;
  }
  function persistence(F) {
    const T = F.temporal;
    if (!T) return null;
    if (T.kind === 'recovery') {
      const last = [...T.revisits].reverse().find(r => r.value != null);
      if (!last) return null;
      return /water/.test(T.metric) ? `${last.value}% still under water on ${fmtDate(last.date)} (${T.status}).`
                                    : `${last.value}% of the lost vegetation signal back by ${fmtDate(last.date)} (${T.status}).`;
    }
    if (!T.later_images) return null;
    if (T.persistent) return T.persisted === T.later_images ? `Held in all ${T.later_images} later yearly images.`
                                                          : `Held in ${T.persisted} of ${T.later_images} later yearly images, including the latest.`;
    return T.reverted ? `Did not last: gone from ${monthYear(T.reverted)} onwards (held in ${T.persisted} of ${T.later_images} later images).`
                      : `Held in only ${T.persisted} of ${T.later_images} later images.`;
  }
  function whyPriority(F) {
    const P = F.priority, p = P.parts, bits = [];
    if (p.area >= 0.5) bits.push(`large (${fmtN(F.change.area_ha, 2)} ha)`); else if (p.area < 0.3) bits.push(`small (${fmtN(F.change.area_sqm)} m²)`);
    if (p.signal >= 0.8) bits.push('a strong change signal'); else if (p.signal < 0.6) bits.push('a weak change signal');
    if (p.type_weight != null && p.type_weight >= 0.8) bits.push(`a change type that weighs heavily in ${P.mode} mode`);
    else if (p.type_weight != null && p.type_weight <= 0.3) bits.push(`a change type that weighs little in ${P.mode} mode`);
    if (p.exposure > 1) bits.push(/protected|CRZ|encroach|wetland|nala/i.test(F.exposure.buffer_check || '') && !/^High Exposure/.test(F.exposure.assets || '')
      ? 'inside a protected or water buffer' : 'near a school or hospital, or inside a protected buffer');
    return `${P.tier} priority: ${bits.length ? bits.join(', ') : 'moderate size, signal and type'}.`;
  }
  function assets(F) {
    const a = F.exposure.assets;
    if (!a) return 'Nearby assets not assessed.';
    return a.replace(/^High Exposure: /, '').replace(/^No hospital or school within (\d+) m$/, 'No hospital or school within $1 m.');
  }
  function bufferNote(F) {
    const b = F.exposure.buffer_check;
    if (!b || /^No tidal water|^Not assessed/.test(b)) return null;
    return b;
  }
  function comparability(F) {
    const C = F.reliability.comparability;
    if (!C) return 'Image comparability not assessed: this tile has no acquisition dates.';
    return `${C.band} (${C.score}/100). Biggest factor: ${C.main_factor}.`;
  }
  function seasonal(F) {
    const T = F.temporal;
    if (F.change.type === 'Seasonal Vegetation Change') return 'The change rules already read this as seasonal vegetation.';
    if (F.change.layer === 'multi-year series' && T && T.kind === 'series')
      return `Not a seasonal swing: the multi-year scan only flags a steady rise across same-season images from ${monthYear(T.series_from)} to ${monthYear(T.series_to)}.`;
    if (!T || T.kind !== 'series' || !T.seasonal) return T && T.kind === 'recovery' ? 'Not needed: event pair, weeks apart.'
      : 'Not yet assessed: no yearly image series for this area.';
    const S = T.seasonal;
    if (S.verdict === 'real') return S.swing != null && S.change > S.swing
      ? `Not seasonal: the change (${fmtN(S.change, 2)}) is larger than this spot's own seasonal swing (${fmtN(S.swing, 2)})${T.persistent ? ' and it held in later years' : ''}.`
      : T.persistent ? `Not seasonal: it held in ${T.persisted} of ${T.later_images} later images taken in the same season.`
      : 'Not seasonal: larger than the year-to-year variation here.';
    if (S.verdict === 'seasonal') return `May be seasonal: the change (${fmtN(S.change, 2)}) is within the normal variation at this spot.`;
    return 'The yearly images do not show this change clearly.';
  }
  function signal(F) {
    const R = F.reliability;
    return `${signalWord(R.margin)} signal: ${fmtN(R.signal, 2)} against a threshold of ${fmtN(R.threshold, 2)}.`;
  }
  function cloud(F) {
    const u = F.reliability.near_unobservable_pct;
    return u ? `${u}% of its surroundings is cloud or missing data.` : 'Clear view: no cloud or missing data around it.';
  }
  function nextStep(F) {
    const st = F.status, type = F.change.type, why = uncertain(F);
    if (st === 'Dismissed') return 'Closed as a false alarm. Reopen it if new evidence appears.';
    if (st === 'Resolved') return 'Resolved. Nothing more to do.';
    if (st === 'Reported') return 'Reported to the DDMA. Mark it resolved once action is taken.';
    if (st === 'Confirmed') return 'Confirmed. File it with the DDMA; the CAP alert draft is ready to download.';
    if (st === 'Field verification') return `Waiting for the site visit${F.assignee ? ` by ${F.assignee}` : ''}.`;
    if (F.duplicate_of) return `Same spot as ${F.duplicate_of}: review that case instead.`;
    const base = {Critical: 'Send a field team today and inform the DDMA duty officer.', High: 'Inspect on site within 24 hours.',
                  Medium: 'Add it to the next scheduled survey round.', Low: 'Log it and check again with the next image.'}[F.priority.tier];
    let extra = '';
    if (why.includes('may be seasonal') || why.includes('did not hold in later images')) extra = ' Check the time-travel images first: it may not be lasting change.';
    else if (bufferNote(F) && BUILT.has(type)) extra = ' Check revenue, FTL and Development Plan records before any notice: satellite flags are screening, not proof.';
    else if (type === 'Water / Flood Inundation') extra = ' Check access roads and shelters at its edge.';
    else if (type === 'Burn Scar') extra = ' Check for active fire lines and homes at the edge of the burn.';
    else if (/^Precursor/.test(type)) extra = ' Visit before building starts: this is the cheapest moment to act.';
    return base + extra;
  }
  function card(F) {
    return {what: F.change.plain, firstSeen: firstSeen(F), persistence: persistence(F), whyPriority: whyPriority(F), assets: assets(F),
            buffer: bufferNote(F), signal: signal(F), comparability: comparability(F), cloud: cloud(F), seasonal: seasonal(F),
            next: nextStep(F), uncertain: uncertain(F)};
  }

  /* ---------- number validator (#14), same rule as src/exporters/grounding.py ---------- */
  const NUM = /(?<![\w.])[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?/g;
  const numbersIn = s => (String(s).replace(/\/\s*100\b/g, '').match(NUM) || []);
  const val = tok => parseFloat(tok.replace(/,/g, '').replace('−', '-'));
  const decimals = tok => tok.includes('.') ? tok.split('.')[1].length : 0;
  function allowed(F) {
    const out = new Set();
    (function walk(v) {
      if (v == null || typeof v === 'boolean') return;
      if (typeof v === 'number') [v, v * 100, v / 100, v / 1e4, v / 1e6, Math.abs(v), Math.abs(v) * 100].forEach(x => out.add(x));
      else if (typeof v === 'string') numbersIn(v).forEach(t => { out.add(val(t)); out.add(Math.abs(val(t))); });
      else if (Array.isArray(v)) v.forEach(walk);
      else if (typeof v === 'object') Object.values(v).forEach(walk);
    })(F);
    return [...out];
  }
  function supported(tok, al) {
    const x = Math.abs(val(tok)), tol = 0.5 * Math.pow(10, -decimals(tok)) + 1e-9;
    return al.some(a => Math.abs(x - Math.abs(a)) <= tol);
  }
  function validate(text, F, al) {
    al = al || allowed(F);
    const bad = numbersIn(text).filter(t => !supported(t, al));
    return {ok: !bad.length, unverified: bad};
  }
  function keepGrounded(items, F) {
    const al = allowed(F), kept = [], dropped = [];
    items.forEach(s => (validate(s, F, al).ok ? kept : dropped).push(s));
    return {kept, dropped};
  }

  /* ---------- offline copilot (#45) ---------- */
  const QUESTIONS = [
    ['why', 'Why does this have this priority?'],
    ['seasonal', 'Could this be seasonal?'],
    ['reliable', 'How reliable is this finding?'],
    ['when', 'When did it start, and did it stay?'],
    ['nearby', 'What is nearby that matters?'],
    ['next', 'What should I do next?'],
  ];
  const KEYWORDS = {why: /priority|why|critical|high|score|rank|important|urgent/i, seasonal: /season|monsoon|crop|harvest|natural|weather|dry/i,
    reliable: /reliab|confiden|trust|sure|accura|false|wrong|cloud|threshold/i, when: /when|start|date|year|first|stay|persist|still|recover|how long/i,
    nearby: /near|school|hospital|asset|people|road|protect|mangrove|wetland|lake|nala|crz|encroach/i, next: /next|do|action|step|recommend|should|visit|alert/i};
  function match(q) {
    const hit = QUESTIONS.map(([id]) => id).find(id => KEYWORDS[id].test(q));
    return hit || null;
  }
  function hypotheses(F) {
    const t = F.change.type, h = [];
    if (t === 'Vegetation Cleared / Possible Construction') h.push('Land cleared for a building site, a road or a plot boundary.', 'Dry-season browning of grass or scrub on open ground.');
    else if (t === 'New Built-up Surface' || t === 'New Building / Structure') h.push('New buildings, sheds or a paved yard.', 'Exposed soil or debris dumped on open land, which can look built-up from orbit.');
    else if (t === 'Water-body Encroachment') h.push('Part of the water body filled in and built on.', 'Water level lower than usual, exposing the bed or bank.');
    else if (t === 'Slow Built-up Creep') h.push('Gradual infill: a few structures added each year.', 'Slow change in surface materials, such as roofs or paving, over several years.');
    else if (/^Precursor/.test(t)) h.push('Preparation for construction: clearing, levelling or a new access path.', 'Grazing, cultivation or a seasonal footpath.');
    else if (t === 'Water / Flood Inundation') h.push('River or drain overflow onto low-lying land.', 'Standing rainwater, or irrigated fields that hold water.');
    else if (t === 'Burn Scar') h.push('Wildfire or a controlled burn.', 'Dark ground after harvest or clearing, which can resemble a burn.');
    else if (t === 'Seasonal Vegetation Change') h.push('Normal seasonal drying of vegetation.', 'Crop harvest or grass cutting.');
    else h.push('Earthworks, grading or dumping.', 'A difference in light or moisture between the two images.');
    return h;
  }
  function answer(id, F) {
    const C = card(F), facts = [], hyp = [];
    if (id === 'why') {
      facts.push(C.whyPriority, `Score ${fmtN(F.priority.score, 2)} = area ${fmtN(F.priority.parts.area, 2)} × signal ${fmtN(F.priority.parts.signal, 2)}`
        + (F.priority.parts.type_weight != null ? ` × type weight ${fmtN(F.priority.parts.type_weight, 2)}` : '') + ` × exposure ${fmtN(F.priority.parts.exposure, 2)}.`);
      if (C.buffer) facts.push(C.buffer);
      hyp.push(...hypotheses(F).slice(0, 1));
    } else if (id === 'seasonal') {
      facts.push(C.seasonal);
      if (F.reliability.comparability) facts.push(`The two images: ${C.comparability}`);
      if (F.temporal && F.temporal.kind === 'series' && C.persistence) facts.push(C.persistence);
      hyp.push(...hypotheses(F));
    } else if (id === 'reliable') {
      facts.push(C.signal, `Image comparability: ${C.comparability}`, C.cloud);
      const d = F.reliability.detector;
      if (d.f1 != null) facts.push(`${d.name}: F1 ${Math.round(d.f1 * 100)}% on ${d.benchmark}` + (d.object_precision != null ? `; ${Math.round(d.object_precision * 100)}% of its polygons were real changes.` : '.'));
      if (C.uncertain.length) hyp.push(`Treat with care: ${C.uncertain.join('; ')}.`);
      else hyp.push('No warning signs in the data; a site visit is still the only proof.');
    } else if (id === 'when') {
      facts.push(C.firstSeen);
      if (C.persistence) facts.push(C.persistence);
      if (!F.temporal) facts.push('No yearly or post-event images are stored for this area, so the date cannot be narrowed further.');
      hyp.push(F.temporal && F.temporal.pre_existing ? 'Work may have started before the before-image: check older records too.'
        : 'The first-visible date is when the change crossed the index threshold; work on the ground may have started a little earlier.');
    } else if (id === 'nearby') {
      facts.push(C.assets);
      if (C.buffer) facts.push(C.buffer);
      if (F.location.near) facts.push(`Nearest named place: ${F.location.near}, ${fmtN(F.location.near_m)} m away.`);
      hyp.push('OpenStreetMap can miss assets, especially in rural areas; check locally for schools, clinics and homes.');
    } else {
      facts.push(C.next, `Recorded status: ${F.status}${F.assignee ? `, assigned to ${F.assignee}` : ''}.`);
      hyp.push(...hypotheses(F).slice(0, 1).map(s => `On site, check whether it is: ${s.charAt(0).toLowerCase()}${s.slice(1)}`));
    }
    return {facts, hypotheses: hyp};
  }
  const lib = {PLAIN, BUILT, VERIFIED, OPEN_STATES, QUESTIONS, RULES, facts, uncertain, card, answer, match, validate, keepGrounded,
               numbersIn, fmtDate, monthYear, nextStep};
  if (typeof module !== 'undefined' && module.exports) module.exports = lib; else root.CaseLogic = lib;
})(this);
