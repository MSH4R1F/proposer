#!/usr/bin/env node
/**
 * Slow UI walkthrough with real prediction, expectation, and mediation dialogue.
 */

import { readFileSync, mkdirSync, readdirSync, statSync, renameSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { chromium } from 'playwright';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '../..');
const EXAMPLES = join(ROOT, 'docs/demo/example-cases');
const OUT_DIR = join(ROOT, 'docs/demo/videos');
const WEB = process.env.PROPOSER_WEB_URL || 'http://localhost:3000';
const API = process.env.PROPOSER_API_URL || 'http://localhost:8000';
const DOMAIN = 'housing.deposit.v1';

const PAUSE = {
  short: 2500,
  medium: 5000,
  long: 8000,
  prediction: 15000,
  mediation: 12000,
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function readCaseMarkdown(filename) {
  const raw = readFileSync(join(EXAMPLES, filename), 'utf8');
  const marker = '## Case text (copy into Proposer)';
  if (!raw.includes(marker)) return raw.trim();
  const after = raw.split(marker)[1].trim();
  const nextHeading = after.indexOf('\n## ');
  return (nextHeading >= 0 ? after.slice(0, nextHeading) : after).trim();
}

async function api(path, body, method = 'POST') {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${method} ${path} ${res.status}: ${text}`);
  return text ? JSON.parse(text) : {};
}

async function waitForPrediction(page) {
  await page
    .getByText(/Tenant Favored|Landlord Favored|Split Decision|Analyzing Your Case/i)
    .first()
    .waitFor({ timeout: 180000 });
  if (await page.getByText('Analyzing Your Case').isVisible().catch(() => false)) {
    await page
      .getByText(/Tenant Favored|Landlord Favored|Split Decision/i)
      .first()
      .waitFor({ timeout: 180000 });
  }
  await sleep(PAUSE.short);
}

/** Scroll the prediction page <main> (not window) through all sections slowly. */
async function scrollThroughPredictionPage(page) {
  const main = page.locator('main.overflow-y-auto');
  await main.waitFor({ timeout: 30000 });

  const scrollMain = async (top) => {
    await main.evaluate((el, y) => {
      el.scrollTo({ top: y, behavior: 'smooth' });
    }, top);
  };

  const maxScroll = await main.evaluate((el) => el.scrollHeight - el.clientHeight);

  // Top: outcome + disclaimer
  await scrollMain(0);
  await sleep(PAUSE.medium);

  // Summary + settlement range (~25%)
  await scrollMain(maxScroll * 0.22);
  await sleep(PAUSE.medium);

  // Strengths / weaknesses (~45%)
  await scrollMain(maxScroll * 0.42);
  await sleep(PAUSE.medium);

  // Per-issue breakdown (~60%)
  await scrollMain(maxScroll * 0.58);
  await sleep(PAUSE.medium);

  // Reasoning trace + expand first step
  await scrollMain(maxScroll * 0.68);
  await sleep(PAUSE.short);
  const reasoningSection = page.getByText('Reasoning Trace');
  if (await reasoningSection.isVisible().catch(() => false)) {
    await reasoningSection.scrollIntoViewIfNeeded();
    await sleep(PAUSE.short);
    const firstStep = main.locator('[data-state="closed"]').first();
    if (await firstStep.isVisible().catch(() => false)) {
      await firstStep.click();
      await sleep(PAUSE.medium);
      await scrollMain(maxScroll * 0.75);
      await sleep(PAUSE.medium);
    }
  }

  // Citations / trace bottom (~85%)
  await scrollMain(maxScroll * 0.82);
  await sleep(PAUSE.medium);

  // Proceed to mediation CTA
  await scrollMain(maxScroll);
  await sleep(PAUSE.long);

  // Brief scroll back up so the outcome is visible again before leaving
  await scrollMain(maxScroll * 0.15);
  await sleep(PAUSE.short);
}

async function waitForExpectation(page) {
  await page
    .getByText(/No expectation data found/i)
    .waitFor({ state: 'hidden', timeout: 60000 })
    .catch(() => {});
  await page
    .getByText(/Based on similar|midpoint estimate|settlement/i)
    .first()
    .waitFor({ timeout: 60000 });
  await sleep(PAUSE.long);
}

async function seedScenario(scenario) {
  const tenantText = readCaseMarkdown('tenant-deposit-cleaning-dispute.md');
  const landlordText = readCaseMarkdown('landlord-deposit-damage-dispute.md');

  if (scenario === 'tenant-led') {
    const creator = await api('/chat/bulk-intake', {
      role: 'tenant',
      case_text: tenantText,
      create_dispute: true,
      domain_id: DOMAIN,
    });
    const caseId = creator.case_file.case_id;
    const disputeId = creator.dispute.dispute_id;
    const invite = creator.dispute.invite_code;
    console.log(`  Generating prediction for ${caseId}...`);
    await api('/predictions/generate', { case_id: caseId, domain_id: DOMAIN });
    const joiner = await api('/chat/bulk-intake', {
      role: 'landlord',
      case_text: landlordText,
      invite_code: invite,
      create_dispute: false,
      domain_id: DOMAIN,
    });
    return {
      scenario,
      primaryRole: 'tenant',
      secondaryRole: 'landlord',
      caseId,
      disputeId,
      primarySession: creator.session_id,
      secondarySession: joiner.session_id,
      invite,
    };
  }

  const creator = await api('/chat/bulk-intake', {
    role: 'landlord',
    case_text: landlordText,
    create_dispute: true,
    domain_id: DOMAIN,
  });
  const caseId = creator.case_file.case_id;
  const disputeId = creator.dispute.dispute_id;
  const invite = creator.dispute.invite_code;
  console.log(`  Generating prediction for ${caseId}...`);
  await api('/predictions/generate', { case_id: caseId, domain_id: DOMAIN });
  const joiner = await api('/chat/bulk-intake', {
    role: 'tenant',
    case_text: tenantText,
    invite_code: invite,
    create_dispute: false,
    domain_id: DOMAIN,
  });
  return {
    scenario,
    primaryRole: 'landlord',
    secondaryRole: 'tenant',
    caseId,
    disputeId,
    primarySession: creator.session_id,
    secondarySession: joiner.session_id,
    invite,
  };
}

async function runMediationDialogue(seed) {
  const { disputeId, primarySession, secondarySession, primaryRole, secondaryRole } =
    seed;

  await api(`/mediation/${disputeId}/start`, { session_id: primarySession });

  const primaryMsg =
    primaryRole === 'tenant'
      ? 'I believe I should receive at least £1,100 back. There was no check-in inventory and the deductions look like fair wear and tear.'
      : 'I have documented damage and rent arrears. I am willing to return £250 but not the full deposit.';

  const secondaryMsg =
    secondaryRole === 'landlord'
      ? 'The checkout report shows cleaning and worktop damage beyond wear and tear. I cannot return more than £400.'
      : 'I left the flat in good condition. Your cleaning claim is excessive without a baseline inventory.';

  await api(`/mediation/${disputeId}/message`, {
    session_id: primarySession,
    content: primaryMsg,
  });
  await sleep(3000);

  await api(`/mediation/${disputeId}/message`, {
    session_id: secondarySession,
    content: secondaryMsg,
  });
  await sleep(3000);

  const offerAmount = primaryRole === 'tenant' ? 950 : 280;
  const offer = await api(`/mediation/${disputeId}/offer`, {
    session_id: primarySession,
    amount: offerAmount,
  });
  const offerId = offer.offer_id || offer.id;

  const counterAmount = primaryRole === 'tenant' ? 720 : 350;
  await api(`/mediation/${disputeId}/respond`, {
    session_id: secondarySession,
    offer_id: offerId,
    action: 'counter',
    counter_amount: counterAmount,
  });
  await sleep(2000);

  const settleAmount = Math.round((offerAmount + counterAmount) / 2);
  const messagesRes = await fetch(`${API}/mediation/${disputeId}/messages`);
  const messagesBody = messagesRes.ok
    ? await messagesRes.json()
    : { offers: [] };
  let latestOfferId = offerId;
  const pending = messagesBody.offers?.find((o) => o.status === 'pending');
  if (pending) latestOfferId = pending.id;

  await api(`/mediation/${disputeId}/respond`, {
    session_id: primarySession,
    offer_id: latestOfferId,
    action: 'accept',
  });

  return { offerAmount, counterAmount, settleAmount };
}

async function recordScenario(browser, seed) {
  mkdirSync(OUT_DIR, { recursive: true });
  const videoPath = join(OUT_DIR, `proposer-walkthrough-${seed.scenario}.webm`);
  const {
    caseId,
    disputeId,
    primarySession,
    primaryRole,
    scenario,
  } = seed;

  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    recordVideo: { dir: OUT_DIR, size: { width: 1280, height: 800 } },
  });
  const page = await context.newPage();
  page.setDefaultTimeout(180000);

  const q = new URLSearchParams({
    session: primarySession,
    dispute: disputeId,
  });

  // Landing
  await page.goto(WEB);
  await sleep(PAUSE.medium);

  // Intake tour (visual only — fall through to prediction if UI unavailable)
  await page.goto(`${WEB}/chat`, { waitUntil: 'networkidle' });
  await sleep(PAUSE.short);
  try {
    await page.getByText('Start New Dispute').click({ timeout: 15000 });
    await sleep(PAUSE.short);
    await page.getByRole('button', { name: /deposit/i }).click();
    await sleep(PAUSE.short);
    const rolePattern =
      primaryRole === 'tenant' ? /I'm the tenant/i : /I'm the landlord/i;
    await page.getByRole('button', { name: rolePattern }).click();
    await sleep(PAUSE.short);
    await page.getByRole('button', { name: /Paste All Details/i }).click();
    await sleep(PAUSE.medium);
  } catch {
    console.warn('  Intake tour skipped — continuing to prediction');
  }

  // Prediction (pre-generated — page loads existing result)
  await page.goto(`${WEB}/prediction/${caseId}?${q}`);
  await waitForPrediction(page);
  console.log('  Scrolling through prediction results...');
  await scrollThroughPredictionPage(page);

  // Expectation
  await page.goto(
    `${WEB}/mediation/${disputeId}/expectation?session=${primarySession}`
  );
  await waitForExpectation(page);
  await sleep(PAUSE.medium);

  // Start negotiation from expectation screen
  const negotiateBtn = page.getByRole('button', {
    name: /Start Mediation|Open Chat/i,
  });
  if (await negotiateBtn.first().isVisible().catch(() => false)) {
    await negotiateBtn.first().click();
    await sleep(PAUSE.short);
  }

  // Mediation chat with role param (required for sending messages)
  await page.goto(
    `${WEB}/mediation/${disputeId}/chat?session=${primarySession}&role=${primaryRole}`
  );
  await sleep(PAUSE.medium);

  console.log('  Running mediation dialogue via API...');
  await runMediationDialogue(seed);

  await page.reload();
  await sleep(PAUSE.mediation);
  await page.evaluate(() => {
    const el = document.querySelector('[class*="overflow-y"]');
    if (el) el.scrollTop = el.scrollHeight;
  });
  await sleep(PAUSE.long);

  // Session summary with invite code
  await page.goto(`${WEB}/chat/${primarySession}`);
  await sleep(PAUSE.medium);

  await context.close();

  const videos = readdirSync(OUT_DIR)
    .filter((f) => f.endsWith('.webm'))
    .map((f) => ({ f, m: statSync(join(OUT_DIR, f)).mtimeMs }))
    .sort((a, b) => b.m - a.m);
  if (videos.length) {
    const latest = join(OUT_DIR, videos[0].f);
    if (latest !== videoPath) renameSync(latest, videoPath);
    console.log(`Saved: ${videoPath}`);
  }
}

async function main() {
  const idx = process.argv.indexOf('--scenario');
  const only = idx >= 0 ? process.argv[idx + 1] : 'both';
  const scenarios = only === 'both' ? ['tenant-led', 'landlord-led'] : [only];

  const browser = await chromium.launch({ headless: true });
  for (const scenario of scenarios) {
    console.log(`\n=== ${scenario} ===`);
    const seed = await seedScenario(scenario);
    await recordScenario(browser, seed);
  }
  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
