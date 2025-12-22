import { test, expect } from '@playwright/test';
import { LoginPage, DashboardPage, EditDetailsPage, Locators } from '../pages';
import testData from '../testData/testData.json';
import environments from '../testData/environments.json';

// Get environment configuration
const ENV = process.env.ENV || 'dev';
const envData = environments[ENV as keyof typeof environments] || environments.dev;
const baseURL = envData.baseURL;
const credentials = envData.credentials;

const lang = '_de'; 
let docName = testData.searchTerms.docName + lang;
const waitTimes = testData.waitTimes;

test.describe('User Edit Flow E2E Tests', { tag: '@userEditFlow' }, () => {
  
  test('Complete workflow with sequential steps', { tag: '@fullWorkflow' }, async ({ page }) => {
    await page.setViewportSize({ width: 1480, height: 720 });
    
    let dashboardPage: DashboardPage;
    let editDetailsPage: EditDetailsPage;
    let rowIndex: number;
    
    // Step 1: Login
    await test.step('Login and verify dashboard loads', async () => {
      console.log('\n========== STEP 1: LOGIN ==========\n');
      console.log(`Environment: ${ENV}`);
      console.log(`Base URL: ${baseURL}`);
      const loginPage = new LoginPage(page, baseURL, credentials);
      await loginPage.goto();
      await loginPage.login();
      
      dashboardPage = new DashboardPage(page, 'Dashboard');
      await dashboardPage.waitForDashboard();
      console.log('[PASS] Login successful - Dashboard loaded\n');
    });
    
    // Step 2: Search for document
    await test.step('Search and find document in grid', async () => {
      console.log('========== STEP 2: SEARCH ==========\n');
      await dashboardPage.searchDocument();
      
      const { found, rowIndex: foundRowIndex } = await dashboardPage.findDocumentInGrid(docName);
      expect(found).toBeTruthy();
      rowIndex = foundRowIndex;
      console.log(`[PASS] Document "${docName}" found at row ${rowIndex}\n`);
    });
    
    // Step 3: Verify baseline data
    await test.step('Verify baseline document data and scores', async () => {
      console.log('========== STEP 3: BASELINE VALIDATION ==========\n');
      const rowData = await dashboardPage.extractRowData(rowIndex);
      
      // Extract document name from col-id="0" and remove "New" tag if present
      const actualDocName = rowData['0']?.replace(/New$/, '').trim() || '';
      expect.soft(actualDocName).toBe(docName);
      
      const version = rowData['version'] || '';
      expect.soft(version).toBeTruthy();
      
      const status = rowData['status'] || '';
      expect.soft(status).toBe(testData.statusFilterTileTexts.awaitingReview);
      
      const avgFluency = parseFloat(rowData['avgFluency'] || '0');
      const avgAdequacy = parseFloat(rowData['avgAdequacy'] || '0');
      const avgCompliance = parseFloat(rowData['avgCompliance'] || '0');
      
      expect.soft(avgFluency).toBe(testData.scores.initial);
      expect.soft(avgAdequacy).toBe(testData.scores.initial);
      expect.soft(avgCompliance).toBe(testData.scores.initial);
      
      console.log(`  [✓] Document: ${actualDocName}`);
      console.log(`  [✓] Version: ${version}`);
      console.log(`  [✓] Status: ${status}`);
      console.log(`  [✓] Fluency: ${avgFluency}, Adequacy: ${avgAdequacy}, Compliance: ${avgCompliance}`);
      console.log('[PASS] All baseline validations passed\n');
    });
    
    // Step 4: Edit with simple text
    await test.step('Edit document with simple text', async () => {
      console.log('========== STEP 4: SIMPLE TEXT EDIT ==========\n');
      await dashboardPage.openContextMenu(rowIndex);
      await dashboardPage.selectEditDetails();
      
      editDetailsPage = new EditDetailsPage(page);
      await editDetailsPage.waitForEditor();
      await editDetailsPage.fillTextarea(testData.testContent.simpleText);
      await editDetailsPage.verifyTextareaValue(testData.testContent.simpleText);
      await editDetailsPage.saveChanges(dashboardPage.searchInput);
      
      console.log('[PASS] Simple text edit completed\n');
    });
    
    // Step 5: Edit with markdown and test cancel
    await test.step('Edit with markdown content and test cancel flow', async () => {
      console.log('========== STEP 5: MARKDOWN EDIT & CANCEL ==========\n');
      await dashboardPage.searchDocument();
      
      const { found, rowIndex: foundRowIndex } = await dashboardPage.findDocumentInGrid(docName);
      expect(found).toBeTruthy();
      rowIndex = foundRowIndex;
      
      await dashboardPage.openContextMenu(rowIndex);
      await dashboardPage.selectEditDetails();
      
      await editDetailsPage.waitForEditor();
      await editDetailsPage.fillTextarea(testData.testContent.markdownTable);
      await editDetailsPage.verifyTextareaValue(testData.testContent.markdownTable);
      await editDetailsPage.cancelChanges();
      
      console.log('[PASS] Markdown edit and cancel flow completed\n');
    });
    
    // Step 6: Navigate steppers
    await test.step('Navigate through document steppers', async () => {
      console.log('========== STEP 6: STEPPER NAVIGATION ==========\n');
      const isLastStepper = await editDetailsPage.navigateSteppers();
      expect(isLastStepper).toBeTruthy();
      console.log('[PASS] Stepper navigation completed\n');
    });
    
    // Step 7: Test Previous/Next buttons
    await test.step('Test Previous and Next navigation buttons', async () => {
      console.log('========== STEP 7: PREVIOUS/NEXT BUTTONS ==========\n');
      await editDetailsPage.testPreviousNextButtons(true);
      await editDetailsPage.saveAndExit(dashboardPage.searchInput)
      console.log('[PASS] Navigation buttons tested\n');
    });
    
    // Step 8: Edit scores
    await test.step('Edit document scores', async () => {
      console.log('========== STEP 8: EDIT SCORES ==========\n');
      await editDetailsPage.editScores(
        testData.scores.fluencyUpdated,
        testData.scores.adequacyUpdated,
        testData.scores.initial
      );
      await editDetailsPage.saveAndExit(dashboardPage.searchInput);
      console.log('[PASS] Scores edited and saved\n');
    });
    
    // Step 9: Verify updated scores
    await test.step('Verify updated scores in listing', async () => {
      console.log('========== STEP 9: VERIFY UPDATED SCORES ==========\n');
      await dashboardPage.searchDocument();
      
      const { found, rowIndex: foundRowIndex } = await dashboardPage.findDocumentInGrid(docName);
      expect(found).toBeTruthy();
      rowIndex = foundRowIndex;
      
      const updatedRowData = await dashboardPage.extractRowData(rowIndex);
      
      const updatedFluency = parseFloat(updatedRowData['avgFluency'] || '0');
      const updatedAdequacy = parseFloat(updatedRowData['avgAdequacy'] || '0');
      const updatedCompliance = parseFloat(updatedRowData['avgCompliance'] || '0');
      const updatedStatus = updatedRowData['status'] || '';
      
      expect.soft(updatedFluency).toBeLessThan(4.0);
      expect.soft(updatedFluency).toBeGreaterThan(0);
      expect.soft(updatedAdequacy).toBeLessThan(4.0);
      expect.soft(updatedAdequacy).toBeGreaterThan(0);
      expect.soft(updatedCompliance).toBeGreaterThanOrEqual(3.5);
      expect.soft(updatedStatus).toBe(testData.statusFilterTileTexts.awaitingPublication);
      
      console.log(`  [✓] Updated Fluency: ${updatedFluency} (expected <4.0)`);
      console.log(`  [✓] Updated Adequacy: ${updatedAdequacy} (expected <4.0)`);
      console.log(`  [✓] Updated Compliance: ${updatedCompliance} (expected ≥3.5)`);
      console.log(`  [✓] Status: ${updatedStatus}`);
      console.log('[PASS] Score updates verified\n');
    });
    
    // Step 10: Publish document
    await test.step('Publish document with cancel flow', async () => {
      console.log('========== STEP 10: PUBLISH DOCUMENT ==========\n');
      await dashboardPage.publishDocumentWithCancelTest(rowIndex);
      await dashboardPage.verifyPublishStatus(rowIndex);
      console.log('[PASS] Document published successfully\n');
    });
    
    // Step 11: Logout
    await test.step('Logout and verify session termination', async () => {
      console.log('========== STEP 11: LOGOUT ==========\n');
      await dashboardPage.logout();
      
      const emailInput = page.locator(Locators.login.emailInput);
      await emailInput.waitFor({ state: 'visible', timeout: 15000 });
      await page.waitForTimeout(waitTimes.medium);
      
      const currentUrl = page.url();
      expect(currentUrl).toContain('/login');
      
      console.log(`  [✓] Redirected to: ${currentUrl}`);
      console.log('[PASS] Logout successful\n');
    });
    
    console.log('✅ ALL STEPS COMPLETED SUCCESSFULLY\n');
  });
});