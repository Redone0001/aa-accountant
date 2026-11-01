// Run against the local preview created by `python -m tests.preview`.
// Requires Playwright's chromium installation. No live SSO or ESI is used.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const {chromium} = require("playwright");

(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const context = await browser.newContext({viewport: {width: 1920, height: 1200}});
    await context.addCookies([{
      name: "sessionid", value: fs.readFileSync("output/preview-session.txt", "utf8").trim(),
      domain: "127.0.0.1", path: "/",
    }]);
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto("http://127.0.0.1:8000/accountant/", {waitUntil: "networkidle"});
    await page.getByRole("link", {name: /Alliance treasury · Demo/}).click();
    await page.waitForSelector("[data-toggle-row]");
    assert.match(await page.locator("h1").innerText(), /Alliance treasury/);
    const category = page.locator('[data-toggle-row="revenue-player_donation"]');
    assert.equal(await category.getAttribute("aria-expanded"), "false");
    await category.click();
    const subrow = page.locator('tr[data-parent="revenue-player_donation"]').first();
    assert.equal(await subrow.isVisible(), true);
    await subrow.locator("button").click();
    const rowId = await subrow.getAttribute("data-row-id");
    const corpRows = page.locator(`tr[data-parent="${rowId}"]`);
    assert.equal(await corpRows.count(), 2);
    assert.equal(await corpRows.first().isVisible(), true);
    await category.click();
    assert.equal(await corpRows.first().isVisible(), false);
    await page.getByRole("button", {name: "Expand all", exact: true}).click();
    assert.equal(await page.locator("tr[data-row-id][hidden]").count(), 0);
    await page.screenshot({path: "output/dashboard-expanded.png", fullPage: true});
    await page.getByRole("button", {name: "Collapse all", exact: true}).click();
    assert.equal(await subrow.isVisible(), false);
    await page.screenshot({path: "output/dashboard.png", fullPage: true});
    await page.getByLabel("Unit").selectOption("isk");
    await page.getByRole("button", {name: "Apply", exact: true}).click();
    assert.match(await page.locator(".acct-summary").innerText(), /\d \d{3}/);
    const mobileContext = await browser.newContext({
      viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true,
      userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1",
    });
    await mobileContext.addCookies(await context.cookies());
    const mobile = await mobileContext.newPage();
    await mobile.goto(page.url(), {waitUntil: "networkidle"});
    assert.ok(await mobile.locator(".accountant").evaluate(el => el.clientWidth) > 340);
    await mobile.screenshot({path: "output/dashboard-mobile.png"});
    await mobile.locator(".acct-table-wrap").scrollIntoViewIfNeeded();
    await mobile.screenshot({path: "output/dashboard-mobile-statement.png"});
    const tableFits = await mobile.locator(".acct-table-wrap").evaluate(
      el => el.clientWidth <= window.innerWidth && el.scrollWidth > el.clientWidth
    );
    assert.ok(tableFits, "The full monthly statement must remain available by scrolling");
    const overflow = await mobile.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    assert.equal(overflow, false, "Only the financial table should scroll horizontally");
    assert.deepEqual(errors, []);
    console.log("Browser checks passed: nested corporation rows, collapse, unit switch, mobile layout.");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
