// node tests/test_caselogic.mjs
// #45 "done when": for real cases, every number in every copilot answer matches the case facts, and facts and
// hypotheses come back separately. Also checks the validator rejects invented numbers and the card has every part.
import { createRequire } from 'module';
import { readFileSync } from 'fs';
import assert from 'assert/strict';

const require = createRequire(import.meta.url);
const C = require('../web/caselogic.js');
const scenes = JSON.parse(readFileSync(new URL('../web/scenes.json', import.meta.url), 'utf8'));
const sev = scenes._severity;

const cases = [];
for (const [key, sc] of Object.entries(scenes)) {
  if (key === '_severity') continue;
  const fs = sc.features.concat(sc.creep ? sc.creep.features : []);
  // the first few of every sector, plus every case with temporal context
  fs.forEach((f, i) => { if (i < 3 || f.temporal) cases.push([key, sc, f]); });
}
assert.ok(cases.length >= 20, `need at least 20 test cases, have ${cases.length}`);

let answers = 0;
for (const [key, sc, f] of cases) {
  const F = C.facts(f, sc, {mode: sc.default_mode, weights: sev.weights, state: 'New'});
  const card = C.card(F);
  for (const part of ['what', 'firstSeen', 'whyPriority', 'assets', 'signal', 'comparability', 'cloud', 'seasonal', 'next'])
    assert.ok(card[part], `${key}/${f.id}: card.${part} empty`);
  for (const s of Object.values(card).flat().filter(x => typeof x === 'string'))
    assert.ok(C.validate(s, F).ok, `${key}/${f.id}: card sentence has an unverified number: "${s}" ${C.validate(s, F).unverified}`);
  for (const [id] of C.QUESTIONS) {
    const a = C.answer(id, F);
    assert.ok(a.facts.length > 0 && Array.isArray(a.hypotheses), `${key}/${f.id}/${id}: empty answer`);
    for (const s of a.facts.concat(a.hypotheses)) {
      const v = C.validate(s, F);
      assert.ok(v.ok, `${key}/${f.id}/${id}: unverified ${v.unverified} in "${s}"`);
    }
    answers++;
  }
}
// the validator does catch invented numbers
const [, sc0, f0] = cases[0];
const F0 = C.facts(f0, sc0, {mode: sc0.default_mode, weights: sev.weights});
assert.ok(!C.validate('It is 987,654 m² and 13 schools are nearby', F0).ok);
assert.equal(C.keepGrounded([`Area ${Math.round(f0.area_sqm).toLocaleString('en-US')} m².`, 'Grew 4,321% since 1990.'], F0).kept.length, 1);
assert.equal(C.match('could this just be the monsoon?'), 'seasonal');
assert.equal(C.match('why is it high priority'), 'why');
console.log(`caselogic ok: ${cases.length} cases, ${answers} answers, every number grounded`);
