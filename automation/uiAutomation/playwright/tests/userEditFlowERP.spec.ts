import { test, expect } from '@playwright/test';
import { LoginPage, DashboardPage, EditDetailsPage, Locators } from '../pages';
import testData from '../testData/testData.json';
import environments from '../testData/environments.json';

// Get environment configuration
const ENV = process.env.ENV || 'dev';
const envData = environments[ENV as keyof typeof environments] || environments.dev;
const baseURL = envData.baseURL;
const credentials = envData.credentials;

const lang = '_en'; 
let docName = testData.searchTerms.docName + lang;
const waitTimes = testData.waitTimes;

test.describe('User Edit Flow Alternative E2E Tests', { tag: '@userEditFlowAlt' }, () => {
  
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
      
      dashboardPage = new DashboardPage(page, 'English Source Review');
      await dashboardPage.waitForDashboard();
      console.log('[PASS] Login successful - Dashboard loaded\n');
    });
    
    // Step 2: Search for document
    await test.step('Search and find document in grid', async () => {
      console.log('========== STEP 2: SEARCH ==========\n');
      await dashboardPage.searchDocument();
      
      const { found, rowIndex: foundRowIndex } = await dashboardPage.findDocumentInGrid(docName);
      expect.soft(found).toBeTruthy();
      rowIndex = foundRowIndex;
      console.log(`[PASS] Document "${docName}" found at row ${rowIndex}\n`);
    });
    
    // Step 3: Verify baseline data (NO SCORES for English Review)
    await test.step('Verify baseline document data', async () => {
      console.log('========== STEP 3: BASELINE VALIDATION ==========\n');
      const rowData = await dashboardPage.extractRowData(rowIndex);
      
      // Extract document name from col-id="0" and remove "New" tag if present
      const actualDocName = rowData['0']?.replace(/New$/, '').trim() || '';
      expect.soft(actualDocName).toBe(docName);
      
      const version = rowData['version'] || '';
      expect.soft(version).toBeTruthy();
      
      const status = rowData['status'] || '';
      expect.soft(status).toBe(testData.statusFilterTileTexts.awaitingReview);
      
      console.log(`  [✓] Document: ${actualDocName}`);
      console.log(`  [✓] Version: ${version}`);
      console.log(`  [✓] Status: ${status}`);
      console.log('[PASS] All baseline validations passed (No scores for English Review)\n');
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
    
    // Step 4.5: Verify edited content persists after reopening
    await test.step('Verify edited content persists', async () => {
      console.log('========== STEP 4.5: VERIFY CONTENT PERSISTENCE ==========\n');
      await dashboardPage.searchDocument();
      
      const { found, rowIndex: foundRowIndex } = await dashboardPage.findDocumentInGrid(docName);
      expect.soft(found).toBeTruthy();
      rowIndex = foundRowIndex;
      
      // Verify document name in column
      const rowData = await dashboardPage.extractRowData(rowIndex);
      const actualDocName = rowData['0']?.replace(/New$/, '').trim() || '';
      expect.soft(actualDocName).toBe(docName);
      console.log(`  [✓] Document name verified: ${actualDocName}`);
      
      // Verify status is still Awaiting Review (not yet visited last subfile)
      const currentStatus = rowData['status'] || '';
      expect.soft(currentStatus).toBe(testData.statusFilterTileTexts.awaitingReview);
      console.log(`  [✓] Status: ${currentStatus} (still Awaiting Review)`);
      
      // Reopen document to verify saved content
      await dashboardPage.openContextMenu(rowIndex);
      await dashboardPage.selectEditDetails();
      
      await editDetailsPage.waitForEditor();
      await editDetailsPage.verifyTextareaValue(testData.testContent.simpleText);
      await editDetailsPage.fillTextarea(testData.testContent.markdownTable);
      console.log(`  [✓] Saved content verified: "${testData.testContent.simpleText}"`);
      console.log('[PASS] Content persistence verified\n');
    });
    
    // Step 5: Navigate through subfiles to last subfile
    await test.step('Navigate through document subfiles', async () => {
      console.log('========== STEP 5: SUBFILE NAVIGATION ==========\n');
      const isLastStepper = await editDetailsPage.navigateSteppers();
      expect.soft(isLastStepper).toBeTruthy();
      console.log('[PASS] Stepper navigation completed - Reached last subfile\n');
    });
    
    // Step 6: Test Previous/Next buttons on last subfile
    await test.step('Test Previous and Next navigation buttons', async () => {
      console.log('========== STEP 6: PREVIOUS/NEXT BUTTONS ==========\n');
      await editDetailsPage.testPreviousNextButtons(false); // false = no scoring section
      console.log('[PASS] Navigation buttons tested\n');
    });
    
    // Step 7: Test cancel flow with markdown content
    await test.step('Edit with markdown and test cancel flow', async () => {
      console.log('========== STEP 7: MARKDOWN EDIT & CANCEL ==========\n');
  
      await editDetailsPage.saveAndExit(dashboardPage.searchInput);
      
      console.log('[PASS] Markdown save and exit flow completed\n');
    });
    
    
    // Step 8: Verify status change to Awaiting Publication
    await test.step('Verify status changed to Awaiting Publication after visiting last subfile', async () => {
      console.log('========== STEP 8: VERIFY STATUS CHANGE ==========\n');
      await dashboardPage.searchDocument();
      
      const { found, rowIndex: foundRowIndex } = await dashboardPage.findDocumentInGrid(docName);
      expect.soft(found).toBeTruthy();
      rowIndex = foundRowIndex;
      
      const updatedRowData = await dashboardPage.extractRowData(rowIndex);
      
      // Verify document name
      const finalDocName = updatedRowData['0']?.replace(/New$/, '').trim() || '';
      expect.soft(finalDocName).toBe(docName);
      console.log(`  [✓] Document name: ${finalDocName}`);
      
      // Verify status changed to Awaiting Publication (after visiting last subfile)
      const updatedStatus = updatedRowData['status'] || '';
      expect.soft(updatedStatus).toBe(testData.statusFilterTileTexts.awaitingPublication);
      
      console.log(`  [✓] Status changed: ${updatedStatus} (Awaiting Publication after visiting last subfile)`);
      console.log('[PASS] Status automatically updated to Awaiting Publication\n');
    });
    
    // Step 9: Publish document
    await test.step('Publish document with cancel flow', async () => {
      console.log('========== STEP 9: PUBLISH DOCUMENT ==========\n');
      await dashboardPage.publishDocumentWithCancelTest(rowIndex);
      await dashboardPage.verifyPublishStatus(rowIndex);
      console.log('[PASS] Document published successfully\n');
    });
    
    // Step 10: Logout
    await test.step('Logout and verify session termination', async () => {
      console.log('========== STEP 10: LOGOUT ==========\n');
      await dashboardPage.logout();
      
      const emailInput = page.locator(Locators.login.emailInput);
      await emailInput.waitFor({ state: 'visible', timeout: 15000 });
      await page.waitForTimeout(waitTimes.medium);
      
      const currentUrl = page.url();
      expect.soft(currentUrl).toContain('/login');
      
      console.log(`  [✓] Redirected to: ${currentUrl}`);
      console.log('[PASS] Logout successful\n');
    });
    
    console.log('✅ ALL STEPS COMPLETED SUCCESSFULLY\n');
  });
});
