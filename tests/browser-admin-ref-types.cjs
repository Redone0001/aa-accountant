// Use the fictional local preview/session created by `python -m tests.preview`.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const {chromium} = require("playwright");

(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const context = await browser.newContext({viewport: {width: 1600, height: 1000}});
    await context.addCookies([{
      name: "sessionid", value: fs.readFileSync("output/preview-session.txt", "utf8").trim(),
      domain: "127.0.0.1", path: "/",
    }]);
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto("http://127.0.0.1:8000/admin/accountant/reftyperule/add/", {waitUntil: "networkidle"});
    const select = page.locator("#id_ref_type");
    const name = page.locator("#id_display_name");
    assert.equal(await select.locator("option").count(), 163); // 162 types and blank prompt.
    await select.selectOption("ess_escrow_transfer");
    assert.equal(await name.inputValue(), "ESS escrow transfer");
    await select.selectOption("cspaofflinerefund");
    assert.equal(await name.inputValue(), "CSPA offline refund");
    await name.fill("My custom contribution category");
    await select.selectOption("player_donation");
    assert.equal(await name.inputValue(), "My custom contribution category");
    await name.fill("");
    await select.selectOption("industry_job_tax");
    assert.equal(await name.inputValue(), "Industry job tax");
    await page.screenshot({path: "output/admin-ref-types.png"});

    await page.goto("http://127.0.0.1:8000/admin/accountant/dashboard/1/change/", {waitUntil: "networkidle"});
    const visibleSelects = page.locator('select[name$="-ref_type"]:visible');
    const originalCount = await visibleSelects.count();
    const firstLabel = await page.locator('input[name="ref_rules-0-display_name"]').inputValue();
    await page.locator("#ref_rules-group .add-row a").click();
    assert.equal(await visibleSelects.count(), originalCount + 1);
    const newSelect = visibleSelects.last();
    const nameInput = page.locator(`input[name="${(await newSelect.getAttribute("name")).replace(/ref_type$/, "display_name")}"]`);
    await newSelect.selectOption("sovereignity_bill");
    assert.equal(await nameInput.inputValue(), "Sovereignty bill");
    await nameInput.fill("Territory costs");
    await newSelect.selectOption("office_rental_fee");
    assert.equal(await nameInput.inputValue(), "Territory costs");
    assert.equal(await page.locator('input[name="ref_rules-0-display_name"]').inputValue(), firstLabel);
    assert.deepEqual(errors, []);
    console.log("Admin browser checks passed: all 162 types, default names, custom labels and dynamic inline rows.");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
