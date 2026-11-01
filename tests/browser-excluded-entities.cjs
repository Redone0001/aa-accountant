// Verify per-dashboard storage exclusions using only the fictional local preview.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const {chromium} = require("playwright");

(async () => {
  const browser = await chromium.launch({headless: true});
  let page;
  let saved = false;
  async function removeExclusion() {
    await page.goto("http://127.0.0.1:8000/admin/accountant/dashboard/1/change/");
    const row = page.locator("#excluded_entities-group tr").filter({
      has: page.locator('input[name$="-entity_id"][value="90000020"]'),
    });
    await row.locator('input[name$="-DELETE"]').check();
    await page.locator('.submit-row input[name="_save"]').click();
    await page.waitForURL("**/admin/accountant/dashboard/");
    saved = false;
  }
  try {
    const context = await browser.newContext({viewport: {width: 1600, height: 1100}});
    await context.addCookies([{
      name: "sessionid", value: fs.readFileSync("output/preview-session.txt", "utf8").trim(),
      domain: "127.0.0.1", path: "/",
    }]);
    page = await context.newPage();
    await page.goto("http://127.0.0.1:8000/accountant/dashboard/1/");
    const original = await page.locator(".acct-net strong").innerText();
    assert.notEqual(original, "0.00 B. isk");
    await page.goto("http://127.0.0.1:8000/admin/accountant/dashboard/1/change/");
    await page.locator("#excluded_entities-group .add-row a").click();
    await page.locator('select[name$="-entity_type"]:visible').last().selectOption("character");
    await page.locator('input[name$="-entity_id"]:visible').last().fill("90000020");
    await page.locator('#excluded_entities-group input[name$="-display_name"]:visible').last().fill("Browser check storage");
    await page.locator('.submit-row input[name="_save"]').click();
    await page.waitForURL("**/admin/accountant/dashboard/");
    saved = true;
    await page.goto("http://127.0.0.1:8000/accountant/dashboard/1/");
    // Every fictional preview entry has the same second party, exercising either-party matching.
    assert.equal(await page.locator(".acct-net strong").innerText(), "0.00 B. isk");
    assert.equal(await page.getByText("Browser check storage (Character #90000020)").count(), 1);
    const notice = await page.locator(".acct-meta").innerText();
    assert.match(notice, /[1-9]\d* entries involving excluded entities/);
    await page.getByText("Excluded entities (1)", {exact: true}).click();
    await page.screenshot({path: "output/dashboard-storage-exclusion.png"});
    await removeExclusion();
    await page.goto("http://127.0.0.1:8000/accountant/dashboard/1/");
    assert.equal(await page.locator(".acct-net strong").innerText(), original);
    console.log("Storage exclusion browser checks passed: inline save, either-party exclusion, zero totals and restoration after removal.");
  } finally {
    if (saved) await removeExclusion();
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
