// Verify the reason match-mode admin dropdown using the fictional local preview.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const {chromium} = require("playwright");

(async () => {
  const browser = await chromium.launch({headless: true});
  let page, ruleUrl, original;
  let changed = false;
  async function updateReason(pattern, mode) {
    await page.goto(ruleUrl);
    const reason = page.locator('input[name$="-reason"]:visible').first();
    const modeName = (await reason.getAttribute("name")).replace(/reason$/, "match_type");
    await reason.fill(pattern);
    await page.locator(`select[name="${modeName}"]`).selectOption(mode);
    await page.locator('.submit-row input[name="_save"]').click();
    await page.waitForURL("**/admin/accountant/reftyperule/");
  }
  async function moonTotal() {
    await page.goto("http://127.0.0.1:8000/accountant/dashboard/1/");
    await page.getByRole("button", {name: "Expand all", exact: true}).click();
    const row = page.locator("tr[data-row-id]").filter({
      has: page.locator("button.acct-toggle").filter({hasText: "Moon rentals"}),
    });
    assert.equal(await row.count(), 1);
    return row.locator(".acct-row-total").innerText();
  }
  try {
    const context = await browser.newContext({viewport: {width: 1600, height: 1100}});
    await context.addCookies([{
      name: "sessionid", value: fs.readFileSync("output/preview-session.txt", "utf8").trim(),
      domain: "127.0.0.1", path: "/",
    }]);
    page = await context.newPage();
    const before = await moonTotal();
    const profit = await page.locator(".acct-net strong").innerText();
    await page.goto("http://127.0.0.1:8000/admin/accountant/reftyperule/");
    await page.getByRole("link", {name: "Contributions", exact: true}).click();
    ruleUrl = page.url();
    const reason = page.locator('input[name$="-reason"]:visible').first();
    const modeName = (await reason.getAttribute("name")).replace(/reason$/, "match_type");
    const mode = page.locator(`select[name="${modeName}"]`);
    assert.deepEqual(await mode.locator("option").evaluateAll(opts => opts.map(o => o.value)),
      ["exact", "iexact", "contains", "icontains"]);
    original = {pattern: await reason.inputValue(), mode: await mode.inputValue()};
    assert.equal(original.pattern, "moon_rent");
    changed = true;
    await updateReason("MOON", "icontains");
    assert.equal(await moonTotal(), before);
    assert.equal(await page.locator(".acct-net strong").innerText(), profit);
    await page.screenshot({path: "output/reason-match-contains.png"});
    await updateReason(original.pattern, original.mode);
    changed = false;
    assert.equal(await moonTotal(), before);
    console.log("Reason match browser check passed: four modes, saved case-insensitive substring matching, preserved totals and restored configuration.");
  } finally {
    if (changed && original) await updateReason(original.pattern, original.mode);
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
