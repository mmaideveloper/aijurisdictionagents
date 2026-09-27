import { chromium } from '@playwright/test';
import fs from 'node:fs';
import assert from 'node:assert/strict';

const base = 'https://tests.jurisigta.eu';
const account = JSON.parse(fs.readFileSync('/run/secrets/synthetic.json', 'utf8'));
const browser = await chromium.launch({headless:true});
const page = await browser.newPage({viewport:{width:1440,height:1000}});
try {
  await page.goto(base + '/?question=E-1');
  await page.getByRole('button',{name:'Prihlásiť sa',exact:true}).waitFor();
  const reference = await (await page.request.get(base + '/api/questions/E-1')).json();
  assert.equal(reference.structure,'direct');
  await page.screenshot({path:'/evidence/public.png',fullPage:true});
  // Exercise the real one-use exchange with a freshly issued central device token.
  // Password + email OTP UI is covered by the mandatory local acceptance job.
  const start = await page.request.get(base + '/api/auth/start?return_path=/?question=E-1',{maxRedirects:0});
  assert.equal(start.status(),303);
  const redirect = new URL(start.headers().location);
  assert.equal(redirect.origin,'https://jurisdigta.eu');
  const auth = await page.request.post(base + '/api/auth/authorize',{
    headers:{Origin:redirect.origin},data:{state:redirect.searchParams.get('state'),
      user_id:account.user_id,device_id:account.device_id,device_token:account.device_token}});
  assert.equal(auth.status(),200);
  await page.goto((await auth.json()).redirect);
  await page.getByRole('button',{name:'Odhlásiť sa'}).waitFor();
  await page.getByRole('button',{name:'Precvičiť túto otázku'}).click();
  await page.locator('textarea').fill(reference.answer);
  const evaluated = page.waitForResponse(r=>r.url().endsWith('/api/attempts')&&r.request().method()==='POST',{timeout:120000});
  await page.getByRole('button',{name:'Vyhodnotiť odpoveď'}).click();
  const result = await (await evaluated).json();
  assert.equal(result.status,'completed');
  assert.equal(result.passed,true);
  assert.equal(result.provider,'azurefoundry');
  await page.getByText('✓ Úspešná odpoveď').waitFor();
  await page.screenshot({path:'/evidence/evaluated.png',fullPage:true});
  fs.writeFileSync('/evidence/smoke.json',JSON.stringify({status:'passed',source:'E-1',score:result.score,
    model:result.model,provider:result.provider,attemptId:result.id,retentionDays:14},null,2));
} catch {
  // Browser/API exception strings can contain authorization callback URLs.
  console.error('Production synthetic smoke failed. No sensitive browser trace retained.');
  process.exitCode=1;
} finally { await browser.close(); }
