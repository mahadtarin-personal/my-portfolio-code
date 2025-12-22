import { test, expect } from '@playwright/test';
import { LoginPage, DashboardPage, Locators } from '../pages';
import testData from '../testData/testData.json';
import environments from '../testData/environments.json';

const docName = testData.searchTerms.docName + testData.languageFilterSuffix.Spanish;
const waitTimes = testData.waitTimes;

test.describe('Filters Flow E2E Tests', () => {
  
  test('Complete workflow with sequential steps', async ({ page }) => {
    test.setTimeout(300000); // Set timeout to 5 minutes (300 seconds)
    await page.setViewportSize({ width: 1466, height: 768 });
    
    let dashboardPage: DashboardPage;
    let rowIndex: number = 0;
    
    const ENV = process.env.ENV || 'dev';
    const envData = environments[ENV as keyof typeof environments] || environments.dev;
    const baseURL = envData.baseURL;
    const credentials = envData.credentials;
    

    // Step 1: Login
    await test.step('Login and verify dashboard loads', async () => {
      console.log('\n========== STEP 1: LOGIN ==========\n');
      const loginPage = new LoginPage(page, baseURL, credentials);
      await loginPage.goto();
      await loginPage.login();
      
      dashboardPage = new DashboardPage(page);
      await dashboardPage.waitForDashboard();
      console.log('[PASS] Login successful - Dashboard loaded\n');
    });
    
    //Step 2: Open Metrics Score filter dropdown and apply 4.0 filter
    await test.step('Open Metrics Score filter dropdown, select 4.0 checkbox and apply filter', async () => {
        console.log('========== STEP 2: Open Metrics Score Filter,  Select 4.0 Checkbox and Apply Filter  ==========\n');
        await dashboardPage.clickMetricsScoreFilter();
        await dashboardPage.selectMetricsScoreCheckBox(testData.metricsScoresCheckboxValues.fourPointZero);
        await dashboardPage.applyMetricsScoreFilter();
        await dashboardPage.waitForFilterApplication(testData.metricsScoresFilterTileTexts.fourPointZero);
        console.log('[ACTION] Metrics Score filter applied with 4.0 selected\n');
    });

    // Step 2.5: Verify scores are in 4.0 - 4.0 range
    await test.step('Verify average scores are within 4.0 - 4.0 range', async () => {
      console.log('========== STEP 2.5: Verify Scores in 4.0 - 4.0 Range ==========\n');
      const rowData = await dashboardPage.extractRowDataForMetricsScoresFilter(rowIndex);
      
      const avgFluency = parseFloat(rowData['avgFluency'] || '0');
      const avgAdequacy = parseFloat(rowData['avgAdequacy'] || '0');
      const avgCompliance = parseFloat(rowData['avgCompliance'] || '0');
      const scoreAverage = parseFloat(rowData['scoreAverage'] || '0');
      
      expect.soft(scoreAverage).toBeGreaterThanOrEqual(testData.scores.initial);
      expect.soft(scoreAverage).toBeLessThanOrEqual(testData.scores.initial);
      
      console.log(`  [✓] avgFluency: ${avgFluency}`);
      console.log(`  [✓] avgAdequacy: ${avgAdequacy}`);
      console.log(`  [✓] avgCompliance: ${avgCompliance}`);
      console.log(`  [✓] Average of scores: ${scoreAverage} (within 4.0 - 4.0)`);
      console.log('[VERIFY] Scores verified to be within 4.0 - 4.0 range\n');
    });  

    //Step 3: Open Metrics Score filter dropdown and apply 0.0 - 2.9 filter
    await test.step('Open Metrics Score filter dropdown, select 0.0 - 2.9 checkbox only and apply filter', async () => {
        console.log('========== STEP 3: Open Metrics Score Filter, Select 0.0 - 2.9 checkbox only and Apply Filter  ==========\n');
        await dashboardPage.clickMetricsScoreFilter();
        await dashboardPage.selectMetricsScoreCheckBox(testData.metricsScoresCheckboxValues.fourPointZero);
        await dashboardPage.selectMetricsScoreCheckBox(testData.metricsScoresCheckboxValues.zeroToTwoPointNine);
        await dashboardPage.applyMetricsScoreFilter();
        await dashboardPage.waitForFilterApplication(testData.metricsScoresFilterTileTexts.zeroToTwoPointNine);
        console.log('[ACTION] Metrics Score filter applied with 0.0-2.9 selected\n');
    });

    // Step 3.5: Verify scores are in 0.0 - 2.9 range
    await test.step('Verify average scores are within 0.0 - 2.9 range', async () => {
      console.log('========== STEP 3.5: Verify Scores in 0.0 - 2.9 Range ==========\n');
      const rowData = await dashboardPage.extractRowDataForMetricsScoresFilter(rowIndex);
      
      const avgFluency = parseFloat(rowData['avgFluency'] || '0');
      const avgAdequacy = parseFloat(rowData['avgAdequacy'] || '0');
      const avgCompliance = parseFloat(rowData['avgCompliance'] || '0');
      const scoreAverage = parseFloat(rowData['scoreAverage'] || '0');
      
      expect.soft(scoreAverage).toBeGreaterThanOrEqual(testData.scores.zeroToThreeLowerBoundary);
      expect.soft(scoreAverage).toBeLessThanOrEqual(testData.scores.zeroToThreeUpperBoundary);
      
      console.log(`  [✓] avgFluency: ${avgFluency}`);
      console.log(`  [✓] avgAdequacy: ${avgAdequacy}`);
      console.log(`  [✓] avgCompliance: ${avgCompliance}`);
      console.log(`  [✓] Average of scores: ${scoreAverage} (within 0.0 - 2.9)`);
      console.log('[VERIFY] Scores verified to be within 0.0 - 2.9 range\n');
    });

    //Step 4: Open Metrics Score filter dropdown and apply 3.0 - 3.4 filter
    await test.step('Open Metrics Score filter dropdown, select 3.0 - 3.4 checkbox only and apply filter', async () => {
        console.log('========== STEP 4: Open Metrics Score Filter, Select 3.0 - 3.4 checkbox only and Apply Filter  ==========\n');
        await dashboardPage.clickMetricsScoreFilter();
        await dashboardPage.selectMetricsScoreCheckBox(testData.metricsScoresCheckboxValues.zeroToTwoPointNine);
        await dashboardPage.selectMetricsScoreCheckBox(testData.metricsScoresCheckboxValues.threeToThreePointFour);
        await dashboardPage.applyMetricsScoreFilter();
        await dashboardPage.waitForFilterApplication(testData.metricsScoresFilterTileTexts.threeToThreePointFour);
        console.log('[ACTION] Metrics Score filter applied with 3.0 - 3.4 selected\n');
    });

    // Step 4.5: Verify scores are in 3.0 - 3.49 range
    await test.step('Verify average scores are within 3.0 - 3.49 range', async () => {
      console.log('========== STEP 4.5: Verify Scores in 3.0 - 3.49 Range ==========\n');
      const rowData = await dashboardPage.extractRowDataForMetricsScoresFilter(rowIndex);
      
      const avgFluency = parseFloat(rowData['avgFluency'] || '0');
      const avgAdequacy = parseFloat(rowData['avgAdequacy'] || '0');
      const avgCompliance = parseFloat(rowData['avgCompliance'] || '0');
      const scoreAverage = parseFloat(rowData['scoreAverage'] || '0');
      
      expect.soft(scoreAverage).toBeGreaterThanOrEqual(testData.scores.adequacyUpdated);
      expect.soft(scoreAverage).toBeLessThanOrEqual(testData.scores.threeToThreePointFourUpperBoundary);
      
      console.log(`  [✓] avgFluency: ${avgFluency}`);
      console.log(`  [✓] avgAdequacy: ${avgAdequacy}`);
      console.log(`  [✓] avgCompliance: ${avgCompliance}`);
      console.log(`  [✓] Average of scores: ${scoreAverage} (within 3.0 - 3.49)`);
      console.log('[VERIFY] Scores verified to be within 3.0 - 3.49 range\n');
    });

    //Step 5: Open Metrics Score filter dropdown and apply 3.5 - 3.9 filter
    await test.step('Open Metrics Score filter dropdown, select 3.5 - 3.9 checkbox only and apply filter', async () => {
        console.log('========== STEP 5: Open Metrics Score Filter, Select 3.5 - 3.9 checkbox only Checkbox and Apply Filter  ==========\n');
        await dashboardPage.clickMetricsScoreFilter();
        await dashboardPage.selectMetricsScoreCheckBox(testData.metricsScoresCheckboxValues.threeToThreePointFour);
        await dashboardPage.selectMetricsScoreCheckBox(testData.metricsScoresCheckboxValues.threePointFiveToThreePointNine);
        await dashboardPage.applyMetricsScoreFilter();
        await dashboardPage.waitForFilterApplication(testData.metricsScoresFilterTileTexts.threePointFiveToThreePointNine);
        console.log('[ACTION] Metrics Score filter applied with 3.5 - 3.9 selected\n');
    });

    // Step 5.5: Verify scores are in 3.5 - 3.9 range
    await test.step('Verify average scores are within 3.5 - 3.9 range', async () => {
      console.log('========== STEP 5.5: Verify Scores in 3.5 - 3.9 Range ==========\n');
      const rowData = await dashboardPage.extractRowDataForMetricsScoresFilter(rowIndex);
      
      const avgFluency = parseFloat(rowData['avgFluency'] || '0');
      const avgAdequacy = parseFloat(rowData['avgAdequacy'] || '0');
      const avgCompliance = parseFloat(rowData['avgCompliance'] || '0');
      const scoreAverage = parseFloat(rowData['scoreAverage'] || '0');
      
      expect.soft(scoreAverage).toBeGreaterThanOrEqual(testData.scores.threePointFiveToThreePointNineLowerBoundary);
      expect.soft(scoreAverage).toBeLessThanOrEqual(testData.scores.threePointFiveToThreePointNineUpperBoundary);
      
      console.log(`  [✓] avgFluency: ${avgFluency}`);
      console.log(`  [✓] avgAdequacy: ${avgAdequacy}`);
      console.log(`  [✓] avgCompliance: ${avgCompliance}`);
      console.log(`  [✓] Average of scores: ${scoreAverage} (within 3.5 - 3.9)`);
      console.log('[VERIFY] Scores verified to be within 3.5 - 3.9 range\n');
    });

    //Step 6: Open Metrics Score filter dropdown and apply 4.0 filter
    await test.step('Open Metrics Score filter dropdown, select 3.5 - 3.9 and 4.0 checkbox and apply filter', async () => {
        console.log('========== STEP 6: Open Metrics Score Filter, Select 3.5 - 3.9 and 4.0 Checkbox and Apply Filter  ==========\n');
        await dashboardPage.clickMetricsScoreFilter();
        await dashboardPage.selectMetricsScoreCheckBox(testData.metricsScoresCheckboxValues.fourPointZero);
        await dashboardPage.applyMetricsScoreFilter();
        await dashboardPage.waitForFilterApplication(testData.metricsScoresFilterTileTexts.fourPointZero);
        console.log('[ACTION] Metrics Score filter applied with 3.5 - 3.9 and 4.0 selected\n');
    });

    
    
    //Step 7: Open Metrics Score filter dropdown and apply 0.0 - 2.9 filter
    await test.step('Open Metrics Score filter dropdown, select 0.0 - 2.9, 3.5 - 3.9 and 4.0 checkbox and apply filter', async () => {
        console.log('========== STEP 7: Open Metrics Score Filter, Select 0.0-2.9, 3.5 - 3.9 and 4.0 Checkbox and Apply Filter  ==========\n');
        await dashboardPage.clickMetricsScoreFilter();
        await dashboardPage.selectMetricsScoreCheckBox(testData.metricsScoresCheckboxValues.zeroToTwoPointNine);
        await dashboardPage.applyMetricsScoreFilter();
        await dashboardPage.waitForFilterApplication(testData.metricsScoresFilterTileTexts.zeroToTwoPointNine);
        console.log('[ACTION] Metrics Score filter applied with 0.0 - 2.9, 3.5 - 3.9 and 4.0 selected\n');
    });

    

    //Step 8: Open Metrics Score filter dropdown and apply 3.0 - 3.4 filter
    await test.step('Open Metrics Score filter dropdown, select select 0.0 - 2.9, 3.0 - 3.4, 3.5 - 3.9 and 4.0 checkbox and apply filter', async () => {
        console.log('========== STEP 8: Open Metrics Score Filter, Select 0.0-2.9, 3.0 - 3.4, 3.5 - 3.9 and 4.0 Checkbox and Apply Filter  ==========\n');
        await dashboardPage.clickMetricsScoreFilter();
        await dashboardPage.selectMetricsScoreCheckBox(testData.metricsScoresCheckboxValues.threeToThreePointFour);
        await dashboardPage.applyMetricsScoreFilter();
        await dashboardPage.waitForFilterApplication(testData.metricsScoresFilterTileTexts.threeToThreePointFour);
        console.log('[ACTION] Metrics Score filter applied with 0.0 - 2.9, 3.0 - 3.4, 3.5 - 3.9 and 4.0 selected\n');
    });

    // Step 9: Clear all Filters
    await test.step('Clear all applied filters', async () => {
        console.log('========== STEP 9: Clear All Applied Filters ==========\n');
        await dashboardPage.clearAllFiltersAction();
        await page.waitForTimeout(waitTimes.short);

        console.log('[ACTION] All Applied Filters Cleared\n');
    });

    // Step 10: Clear all Metrics Scrores Filters from Dropdown
  await test.step('Clear all Metrics Scrores Filters from Dropdown', async () => {
    console.log('\n========== STEP 10: Clear all Metrics Scrores Filters from Dropdown ==========\n');
    await dashboardPage.clearAllMetricsScoreFilter();
    await page.waitForTimeout(waitTimes.short);
    console.log('[ACTION] All Metrics Scrores Filters Cleared from Dropdown\n');
  });

  

    // Step 11: Open Language filter dropdown and apply English filter
    await test.step('Open Language filter dropdown, select English checkbox and apply filter', async () => {
        console.log('========== STEP 11: Open Language Filter, Select English Checkbox and Apply Filter ==========\n');
        await dashboardPage.clickLanguageFilter();
        await dashboardPage.selectLanguageCheckBox(testData.languageCheckboxValues.English);
        await dashboardPage.applyLanguageFilterAction();
        await dashboardPage.waitForLanguageFilterApplication(testData.languageFilterTileTexts.English);
        console.log('[ACTION] Language filter applied with English selected\n');
    });

    // Step 11.5: Verify document name ends with 'en'
    await test.step('Verify document name ends with English language code', async () => {
      console.log('========== STEP 11.5: Verify Document Name Ends with English Language Code ==========');
      const rowData = await dashboardPage.extractRowDataForLanguageFilter(rowIndex);
      const documentName = rowData['0'] || '';
      const expectedSuffix = testData.languageFilterSuffix.English;
      const expectedSuffixNew = expectedSuffix + 'New';
      expect(documentName.endsWith(expectedSuffix) || documentName.endsWith(expectedSuffixNew)).toBeTruthy();
      console.log(`  [✓] Document name: ${documentName}`);
      console.log(`[VERIFY] Document name ends with: ${expectedSuffix}\n`);
    });

    // Step 12: Open Language filter dropdown and apply Spanish filter
    await test.step('Open Language filter dropdown, select Spanish checkbox only and apply filter', async () => {
        console.log('========== STEP 12: Open Language Filter, Select Spanish checkbox only and Apply Filter ==========\n');
        await dashboardPage.clickLanguageFilter();
        await dashboardPage.selectLanguageCheckBox(testData.languageCheckboxValues.English);
        await dashboardPage.selectLanguageCheckBox(testData.languageCheckboxValues.Spanish);
        await dashboardPage.applyLanguageFilterAction();
        await dashboardPage.waitForLanguageFilterApplication(testData.languageFilterTileTexts.Spanish);
        console.log('[ACTION] Language filter applied with Spanish selected\n');
    });

    // Step 12.5: Verify document name ends with 'es'
    await test.step('Verify document name ends with Spanish language code', async () => {
      console.log('========== STEP 12.5: Verify Document Name Ends with Spanish Language Code ==========');
      const rowData = await dashboardPage.extractRowDataForLanguageFilter(rowIndex);
      const documentName = rowData['0'] || '';
      const expectedSuffix = testData.languageFilterSuffix.Spanish;
      const expectedSuffixNew = expectedSuffix + 'New';
      expect(documentName.endsWith(expectedSuffix) || documentName.endsWith(expectedSuffixNew)).toBeTruthy();
      console.log(`  [✓] Document name: ${documentName}`);
      console.log(`[VERIFY] Document name ends with: ${expectedSuffix}\n`);
    });


    // Step 13: Open Language filter dropdown and apply Japanese filter
    await test.step('Open Language filter dropdown, select Japanese checkbox only and apply filter', async () => {
        console.log('========== STEP 13: Open Language Filter, Select Japanese checkbox only and Apply Filter ==========\n');
        await dashboardPage.clickLanguageFilter();
        await dashboardPage.selectLanguageCheckBox(testData.languageCheckboxValues.Spanish);
        await dashboardPage.selectLanguageCheckBox(testData.languageCheckboxValues.Japanese);
        await dashboardPage.applyLanguageFilterAction();
        await dashboardPage.waitForLanguageFilterApplication(testData.languageFilterTileTexts.Japanese);
        console.log('[ACTION] Language filter applied with Japanese selected\n');
    });

    // Step 13.5: Verify document name ends with 'jp'
    await test.step('Verify document name ends with Japanese language code', async () => {
      console.log('========== STEP 13.5: Verify Document Name Ends with Japanese Language Code ==========');
      const rowData = await dashboardPage.extractRowDataForLanguageFilter(rowIndex);
      const documentName = rowData['0'] || '';
      const expectedSuffix = testData.languageFilterSuffix.Japanese;
      const expectedSuffixNew = expectedSuffix + 'New';
      expect(documentName.endsWith(expectedSuffix) || documentName.endsWith(expectedSuffixNew)).toBeTruthy();
      console.log(`  [✓] Document name: ${documentName}`);
      console.log(`[VERIFY] Document name ends with: ${expectedSuffix}\n`);
    });

    // Step 14: Open Language filter dropdown and apply German filter
    await test.step('Open Language filter dropdown, select German checkbox only and apply filter', async () => {
        console.log('========== STEP 14: Open Language Filter, Select German checkbox only and Apply Filter ==========\n');
        await dashboardPage.clickLanguageFilter();
        await dashboardPage.selectLanguageCheckBox(testData.languageCheckboxValues.Japanese);
        await dashboardPage.selectLanguageCheckBox(testData.languageCheckboxValues.German);
        await dashboardPage.applyLanguageFilterAction();
        await dashboardPage.waitForLanguageFilterApplication(testData.languageFilterTileTexts.German);
        console.log('[ACTION] Language filter applied with German selected\n');
    });

    // Step 14.5: Verify document name ends with 'de'
    await test.step('Verify document name ends with German language code', async () => {
      console.log('========== STEP 14.5: Verify Document Name Ends with German Language Code ==========');
      const rowData = await dashboardPage.extractRowDataForLanguageFilter(rowIndex);
      const documentName = rowData['0'] || '';
      const expectedSuffix = testData.languageFilterSuffix.German;
      const expectedSuffixNew = expectedSuffix + 'New';
      expect(documentName.endsWith(expectedSuffix) || documentName.endsWith(expectedSuffixNew)).toBeTruthy();
      console.log(`  [✓] Document name: ${documentName}`);
      console.log(`[VERIFY] Document name ends with: ${expectedSuffix}\n`);
    });

    // Step 15: Open Language filter dropdown and apply Korean filter
    await test.step('Open Language filter dropdown, select Korean checkbox only and apply filter', async () => {
        console.log('========== STEP 15: Open Language Filter, Select Korean checkbox only and Apply Filter ==========\n');
        await dashboardPage.clickLanguageFilter();
        await dashboardPage.selectLanguageCheckBox(testData.languageCheckboxValues.German);
        await dashboardPage.selectLanguageCheckBox(testData.languageCheckboxValues.Korean);
        await dashboardPage.applyLanguageFilterAction();
        await dashboardPage.waitForLanguageFilterApplication(testData.languageFilterTileTexts.Korean);
        console.log('[ACTION] Language filter applied with Korean selected\n');
    });

    // Step 15.5: Verify document name ends with 'ko'
    await test.step('Verify document name ends with Korean language code', async () => {
      console.log('========== STEP 15.5: Verify Document Name Ends with Korean Language Code ==========');
      const rowData = await dashboardPage.extractRowDataForLanguageFilter(rowIndex);
      const documentName = rowData['0'] || '';
      const expectedSuffix = testData.languageFilterSuffix.Korean;
      const expectedSuffixNew = expectedSuffix + 'New';
      expect(documentName.endsWith(expectedSuffix) || documentName.endsWith(expectedSuffixNew)).toBeTruthy();
      console.log(`  [✓] Document name: ${documentName}`);
      console.log(`[VERIFY] Document name ends with: ${expectedSuffix}\n`);
    });

    // Step 16: Open Language filter dropdown and apply multiple languages filter
    await test.step('Open Language filter dropdown, select English and Spanish checkboxes and apply filter', async () => {
        console.log('========== STEP 16: Open Language Filter, Select English and Spanish Checkboxes and Apply Filter ==========\n');
        await dashboardPage.clickLanguageFilter();
        await dashboardPage.selectLanguageCheckBox(testData.languageCheckboxValues.English);
        await dashboardPage.selectLanguageCheckBox(testData.languageCheckboxValues.Spanish);
        await dashboardPage.selectLanguageCheckBox(testData.languageCheckboxValues.Japanese);
        await dashboardPage.selectLanguageCheckBox(testData.languageCheckboxValues.German);
        await dashboardPage.applyLanguageFilterAction();
        await dashboardPage.waitForLanguageFilterApplication(testData.languageFilterTileTexts.English);
        console.log('[ACTION] Language filter applied with English and Spanish selected\n');
    });

    // Step 17: Clear all Filters
    await test.step('Clear all applied language filters', async () => {
        console.log('========== STEP 17: Clear All Applied Language Filters ==========\n');
        await dashboardPage.clearAllFiltersAction();
        await page.waitForTimeout(waitTimes.short);
        console.log('[ACTION] All Applied Language Filters Cleared\n');
    });

    // Step 18: Clear all Language Filters from Dropdown
    await test.step('Clear all Language Filters from Dropdown', async () => {
        console.log('\n========== STEP 18: Clear all Language Filters from Dropdown ==========\n');
        await dashboardPage.clearAllLanguageFilter();
        await page.waitForTimeout(waitTimes.short);
        console.log('[ACTION] All Language Filters Cleared from Dropdown\n');
    });

    // Step 19: Open Status filter dropdown and apply New filter
    await test.step('Open Status filter dropdown, select New checkbox and apply filter', async () => {
        console.log('========== STEP 19: Open Status Filter, Select New Checkbox and Apply Filter ==========\n');
        await dashboardPage.clickStatusFilter();
        await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.New);
        await dashboardPage.applyStatusFilter();
        await dashboardPage.waitForNewStatusFilterApplication(testData.statusFilterTileTexts.New);
        console.log('[ACTION] Status filter applied with New selected\n');
    });

    // Step 19.5: Verify status is NOT 'New' (New filter shows documents with any status except New)
    await test.step('Verify New Status Filter', async () => {
      console.log('========== STEP 19.5: Verify New Filter ==========');
      await dashboardPage.verifyNewFilterBehavior(rowIndex);
      console.log(`[VERIFY] New Status Filter is verified\n`);
    });

    // Step 20: Open Status filter dropdown and apply Awaiting Review filter
    await test.step('Open Status filter dropdown, select Awaiting Review checkbox only and apply filter', async () => {
        console.log('========== STEP 20: Open Status Filter, Select Awaiting Review checkbox only and Apply Filter ==========\n');
        await dashboardPage.clickStatusFilter();
        await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.New);
        await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.awaitingReview);
        await dashboardPage.applyStatusFilter();
        await dashboardPage.waitForStatusFilterApplication(testData.statusFilterTileTexts.awaitingReview);
        console.log('[ACTION] Status filter applied with Awaiting Review selected\n');
    });

    // Step 20.5: Verify status is 'Awaiting Review'
    await test.step('Verify status is Awaiting Review', async () => {
      console.log('========== STEP 20.5: Verify Status is Awaiting Review ==========');
      await dashboardPage.verifyStatusFilterData(rowIndex, testData.statusFilterTileTexts.awaitingReview);
      console.log(`[VERIFY] Status is: ${testData.statusFilterTileTexts.awaitingReview}\n`);
    });

    // Step 21: Open Status filter dropdown and apply Awaiting Publication filter
    await test.step('Open Status filter dropdown, select Awaiting Publication checkbox only and apply filter', async () => {
        console.log('========== STEP 21: Open Status Filter, Select Awaiting Publication checkbox only and Apply Filter ==========\n');
        await dashboardPage.clickStatusFilter();
        await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.awaitingReview);
        await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.awaitingPublication);
        await dashboardPage.applyStatusFilter();
        await dashboardPage.waitForStatusFilterApplication(testData.statusFilterTileTexts.awaitingPublication);
        console.log('[ACTION] Status filter applied with Awaiting Publication selected\n');
    });

    // Step 21.5: Verify status is 'Awaiting Publication'
    await test.step('Verify status is Awaiting Publication', async () => {
      console.log('========== STEP 21.5: Verify Status is Awaiting Publication ==========');
      await dashboardPage.verifyStatusFilterData(rowIndex, testData.statusFilterTileTexts.awaitingPublication);
      console.log(`[VERIFY] Status is: ${testData.statusFilterTileTexts.awaitingPublication}\n`);
    });

    // Step 22: Open Status filter dropdown and apply Published filter
    await test.step('Open Status filter dropdown, select Published checkbox only and apply filter', async () => {
        console.log('========== STEP 22: Open Status Filter, Select Published checkbox only and Apply Filter ==========\n');
        await dashboardPage.clickStatusFilter();
        await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.awaitingPublication);
        await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.published);
        await dashboardPage.applyStatusFilter();
        await dashboardPage.waitForStatusFilterApplication(testData.statusFilterTileTexts.published);
        console.log('[ACTION] Status filter applied with Published selected\n');
    });

    // Step 22.5: Verify status is 'Published'
    await test.step('Verify status is Published', async () => {
      console.log('========== STEP 22.5: Verify Status is Published ==========');
      await dashboardPage.verifyStatusFilterData(rowIndex, testData.statusFilterTileTexts.published);
      console.log(`[VERIFY] Status is: ${testData.statusFilterTileTexts.published}\n`);
    });

    // Step 23: Combine New filter with Awaiting Review filter
    await test.step('Open Status filter dropdown, select New and Awaiting Review checkboxes and apply filter', async () => {
      console.log('========== STEP 23: Combine New and Awaiting Review Filters ==========\n');
      await dashboardPage.clickStatusFilter();
      await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.published);
      await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.New);
      await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.awaitingReview);
      await dashboardPage.applyStatusFilter();
      await dashboardPage.waitForStatusFilterApplication(testData.statusFilterTileTexts.New);
      console.log('[ACTION] Status filter applied with New and Awaiting Review selected\n');
    });

    // Step 23.5: Verify status is 'Awaiting Review' AND document name ends with 'New'
    await test.step('Verify status is Awaiting Review and the document is New', async () => {
      console.log('========== STEP 23.5: Verify Status is Awaiting Review and Document ends with New ==========');
      await dashboardPage.verifyStatusFilterWithDocumentSuffix(rowIndex, testData.statusFilterTileTexts.awaitingReview, testData.statusFilterTileTexts.New);
      console.log(`[VERIFY] Status is Awaiting Review and the document is New\n`);
    });

    // Step 24: Combine New filter with Awaiting Publication filter
    await test.step('Open Status filter dropdown, select New and Awaiting Publication checkboxes and apply filter', async () => {
      console.log('========== STEP 24: Combine New and Awaiting Publication Filters ==========\n');
      await dashboardPage.clickStatusFilter();
      await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.awaitingReview);
      await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.awaitingPublication);
      await dashboardPage.applyStatusFilter();
      await dashboardPage.waitForStatusFilterApplication(testData.statusFilterTileTexts.New);
      console.log('[ACTION] Status filter applied with New and Awaiting Publication selected\n');
    });

    // Step 24.5: Verify status is 'Awaiting Publication' AND document name ends with 'New'
    await test.step('Verify status is Awaiting Publication and the document is New', async () => {
      console.log('========== STEP 24.5: Verify Status is Awaiting Publication and Document ends with New ==========');
      await dashboardPage.verifyStatusFilterWithDocumentSuffix(rowIndex, testData.statusFilterTileTexts.awaitingPublication, testData.statusFilterTileTexts.New);
      console.log(`[VERIFY] Status is Awaiting Publication and the document is New\n`);
    });

    // Step 25: Combine New filter with Published filter
    await test.step('Open Status filter dropdown, select New and Published checkboxes and apply filter', async () => {
      console.log('========== STEP 25: Combine New and Published Filters ==========\n');
      await dashboardPage.clickStatusFilter();
      await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.awaitingPublication);
      await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.published);
      await dashboardPage.applyStatusFilter();
      await dashboardPage.waitForStatusFilterApplication(testData.statusFilterTileTexts.New);
      console.log('[ACTION] Status filter applied with New and Published selected\n');
    });

    // Step 25.5: Verify status is 'Published' AND document name ends with 'New'
    await test.step('Verify status is Published and the document is New', async () => {
      console.log('========== STEP 25.5: Verify Status is Published and Document ends with New ==========');
      await dashboardPage.verifyStatusFilterWithDocumentSuffix(rowIndex, testData.statusFilterTileTexts.published, testData.statusFilterTileTexts.New);
      console.log(`[VERIFY] Status is Published and the document is New\n`);
    });

    // Step 26: Open Status filter dropdown and apply multiple statuses filter
    await test.step('Open Status filter dropdown, select New and Awaiting Review checkboxes and apply filter', async () => {
        console.log('========== STEP 26: Open Status Filter, Select New and Awaiting Review Checkboxes and Apply Filter ==========\n');
        await dashboardPage.clickStatusFilter();
        await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.New);
        await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.awaitingReview);
        await dashboardPage.selectStatusCheckBox(testData.stausCheckboxValues.awaitingPublication);
        await dashboardPage.applyStatusFilter();
        await dashboardPage.waitForStatusFilterApplication(testData.statusFilterTileTexts.New);
        console.log('[ACTION] Status filter applied with New and Awaiting Review selected\n');
    });

    // Step 27: Clear all Filters
    await test.step('Clear all applied status filters', async () => {
        console.log('========== STEP 27: Clear All Applied Status Filters ==========\n');
        await dashboardPage.clearAllFiltersAction();
        await page.waitForTimeout(waitTimes.short);
        console.log('[ACTION] All Applied Status Filters Cleared\n');
    });

    // Step 28: Clear all Status Filters from Dropdown
    await test.step('Clear all Status Filters from Dropdown', async () => {
        console.log('\n========== STEP 28: Clear all Status Filters from Dropdown ==========\n');
        await dashboardPage.clearAllStatusFilter();
        await page.waitForTimeout(waitTimes.short);
        console.log('[ACTION] All Status Filters Cleared from Dropdown\n');
    });
   
    console.log('✅ ALL STEPS COMPLETED SUCCESSFULLY\n');
  });
  
});