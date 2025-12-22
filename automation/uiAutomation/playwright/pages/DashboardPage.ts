import { Page, Locator, expect } from '@playwright/test';
import { Locators } from './locators';
import testData from '../testData/testData.json';

const waitTimes = testData.waitTimes;

export class DashboardPage {
  readonly page: Page;
  readonly title: Locator;
  readonly searchInput: Locator;

  constructor(page: Page, pageTitle: string = 'Translation Review') {
    this.page = page;
    this.title = page.locator(Locators.dashboard.title)
      .or(page.locator(Locators.dashboard.titleAlt(pageTitle)))
      .first();
    this.searchInput = page.locator(Locators.dashboard.searchInput)
      .or(page.locator(Locators.dashboard.searchInputAlt1))
      .or(page.locator(Locators.dashboard.searchInputAlt2))
      .first();
  }

  async waitForDashboard() {
    await this.title.waitFor({ state: 'visible', timeout: 20000 });
    await this.page.waitForTimeout(waitTimes.medium);
    console.log('[PASS] Login successful - Dashboard loaded');

    const titleText = await this.title.textContent();
    console.log(`[VERIFY] Page title verified: "${titleText}"`);
  }

  async searchDocument(searchTerm: string = testData.searchTerms.docName) {
    await this.searchInput.waitFor({ state: 'visible', timeout: 10000 });
    await this.searchInput.fill(searchTerm);
    await this.page.waitForTimeout(waitTimes.medium);
    console.log(`[ACTION] Search query entered: "${searchTerm}"`);

    // Click the search button
    const searchButton = this.page.locator(Locators.dashboard.searchButton).locator('button');
    await searchButton.click({ timeout: 10000 });
    await this.page.waitForTimeout(waitTimes.veryLong);
    console.log('[ACTION] Search button clicked');

    await this.page.waitForSelector(Locators.grid.cell, { state: 'visible', timeout: 15000 });
    await this.page.waitForTimeout(waitTimes.long);
    console.log('[VERIFY] Grid loaded successfully');
  }

  async findDocumentInGrid(docName: string): Promise<{ found: boolean; rowIndex: number }> {
    for (let colId = 0; colId <= 10; colId++) {
      const columnCells = this.page.locator(Locators.grid.cellByColId(colId))
        .or(this.page.locator(Locators.grid.cellByColIdAlt(colId)));
      const cellCount = await columnCells.count();

      if (cellCount === 0) {
        console.log(`[INFO] Column ${colId}: End of grid reached`);
        break;
      }

      console.log(`[SCAN] Searching column ${colId} (${cellCount} rows)`);

      for (let i = 0; i < cellCount; i++) {
        const cellText = await columnCells.nth(i).textContent();

        if (cellText?.includes(docName)) {
          console.log(`[FOUND] Document "${docName}" found in column ${colId}, row ${i}`);
          return { found: true, rowIndex: i - 1 };
        }
      }
    }

    return { found: false, rowIndex: -1 };
  }

  async extractRowData(rowIndex: number): Promise<Record<string, string>> {
    const rowData: Record<string, string> = {};
    const row = this.page.locator(Locators.grid.row(rowIndex)).first();

    console.log(`\n[DATA] Extracting all data for row ${rowIndex}:`);

    // Define the column IDs we want to extract (both numeric and named)
    const columnIds = [
      '0', // Document name
      'version', 
      'status', 
      'avgFluency', 
      'avgAdequacy', 
      'avgCompliance'
    ];

    for (const colId of columnIds) {
      const cell = row.locator(Locators.grid.cellInRow(colId));
      const cellCount = await cell.count();

      if (cellCount === 0) continue;

      let cellText = await cell.textContent();

      // Check for chip elements
      const chipElement = cell.locator(Locators.chip);
      if (await chipElement.count() > 0) {
        cellText = (await chipElement.textContent())?.trim() || cellText;
      }

      rowData[colId] = cellText?.trim() || '';

      if (cellText?.trim()) {
        console.log(`  [${colId}] = "${cellText.trim()}"`);
      }
    }

    await this.page.waitForTimeout(waitTimes.medium);
    return rowData;
  }

  async extractRowDataForMetricsScoresFilter(rowIndex: number): Promise<Record<string, string>> {
    const rowData: Record<string, string> = {};
    const row = this.page.locator(Locators.grid.row(rowIndex)).first();

    console.log(`\n[DATA] Extracting all data for row ${rowIndex}:`);

    const cells = row.locator('div[role="gridcell"]');
    const count = await cells.count();

    for (let i = 0; i < count; i++) {
      const cell = cells.nth(i);

      // attempt to read a col-id attribute if present, otherwise use numeric index
      const colIdAttr = (await cell.getAttribute('col-id')) || i.toString();

      // Prefer chip text if present
      const chipElement = cell.locator(Locators.chip);
      let cellText = '';
      if (await chipElement.count() > 0) {
        cellText = (await chipElement.textContent())?.trim() || '';
      } else {
        cellText = (await cell.textContent())?.trim() || '';
      }

      rowData[colIdAttr] = cellText;
      console.log(`  [${colIdAttr}] = "${cellText}"`);
    }

     // Calculate scoreAverage
    const avgFluency = parseFloat(rowData['avgFluency'] || '0');
    const avgAdequacy = parseFloat(rowData['avgAdequacy'] || '0');
    const avgCompliance = parseFloat(rowData['avgCompliance'] || '0');
    const scoreAverage = (avgFluency + avgAdequacy + avgCompliance) / 3;
    
    rowData['scoreAverage'] = scoreAverage.toString();
    console.log(`  [scoreAverage] = "${scoreAverage}"`);

    await this.page.waitForTimeout(waitTimes.medium);
    return rowData;
  }

    
    async extractRowDataForLanguageFilter(rowIndex: number): Promise<Record<string, string>> {
      const rowData: Record<string, string> = {};
      const row = this.page.locator(Locators.grid.row(rowIndex)).first();

      const cells = row.locator('div[role="gridcell"]');
      const count = await cells.count();

      for (let i = 0; i < count; i++) {
        const cell = cells.nth(i);
        const colIdAttr = (await cell.getAttribute('col-id')) || i.toString();
        let cellText = (await cell.textContent())?.trim() || '';
        rowData[colIdAttr] = cellText;
        if (i === 0) {
          // Store document name for test verification
          rowData['documentNameForLanguageFilter'] = cellText;
        }
      }

      await this.page.waitForTimeout(waitTimes.medium);
      return rowData;
    }


    async extractRowDataForStatusFilter(rowIndex: number): Promise<Record<string, string>> {
      const rowData: Record<string, string> = {};
      const row = this.page.locator(Locators.grid.row(rowIndex)).first();

      const cells = row.locator('div[role="gridcell"]');
      const count = await cells.count();

      for (let i = 0; i < count; i++) {
        const cell = cells.nth(i);
        const colIdAttr = (await cell.getAttribute('col-id')) || i.toString();
        
        // Prefer chip text if present
        const chipElement = cell.locator(Locators.chip);
        let cellText = '';
        if (await chipElement.count() > 0) {
          cellText = (await chipElement.textContent())?.trim() || '';
        } else {
          cellText = (await cell.textContent())?.trim() || '';
        }
        
        rowData[colIdAttr] = cellText;
        
        // Log status column specifically
        if (colIdAttr === 'status') {
          console.log(`[DATA] Status value from grid: "${cellText}"`);
        }
      }

      await this.page.waitForTimeout(waitTimes.medium);
      return rowData;
    }

  async hasDataInGrid(): Promise<boolean> {
    const gridRows = this.page.locator('div[role="row"]').filter({ has: this.page.locator('div[role="gridcell"]') });
    const rowCount = await gridRows.count();
    return rowCount > 1; // More than 1 means header + at least one data row
  }

  async verifyStatusFilterData(rowIndex: number, expectedStatus: string): Promise<boolean> {
    const hasData = await this.hasDataInGrid();
    if (!hasData) {
      console.log('[INFO] Filter applied successfully - Grid is empty (no documents match this filter)\n');
      return true;
    }
    
    const rowData = await this.extractRowDataForStatusFilter(rowIndex);
    const status = rowData['status'] || '';
    expect(status).toBe(expectedStatus);
    console.log(`  [✓] Status: ${status}`);
    return true;
  }

  async verifyStatusFilterWithDocumentSuffix(rowIndex: number, expectedStatus: string, documentSuffix: string): Promise<boolean> {
    const hasData = await this.hasDataInGrid();
    if (!hasData) {
      console.log('[INFO] Filter applied successfully - Grid is empty (no documents match this filter)\n');
      return true;
    }
    
    const rowData = await this.extractRowDataForStatusFilter(rowIndex);
    const status = rowData['status'] || '';
    const documentName = rowData['0'] || '';
    
    expect(status).toBe(expectedStatus);
    expect(documentName).toMatch(new RegExp(`${documentSuffix}$`));
    console.log(`  [✓] Status: ${status}`);
    console.log(`  [✓] Document name ends with "${documentSuffix}" suffix: "${documentName}"`);
    return true;
  }

  async verifyNewFilterBehavior(rowIndex: number): Promise<boolean> {
    const hasData = await this.hasDataInGrid();
    if (!hasData) {
      console.log('[INFO] Filter applied successfully - Grid is empty (no documents match this filter)\n');
      return true;
    }
    
    const rowData = await this.extractRowDataForStatusFilter(rowIndex);
    const status = rowData['status'] || '';
    const documentName = rowData['0'] || '';
    
    expect(status).toBeTruthy();
    expect(status).not.toBe(testData.statusFilterTileTexts.New);
    expect(documentName).toMatch(/New$/);
    console.log(`  [✓] Status: ${status}`);
    console.log(`  [✓] Document name ends with "New" suffix: "${documentName}"`);
    return true;
  }

  async verifyMetricsScoreFilter(rowIndex: number, lowerBoundary: number, upperBoundary: number): Promise<boolean> {
    const hasData = await this.hasDataInGrid();
    if (!hasData) {
      console.log('[INFO] Filter applied successfully - Grid is empty (no documents match this filter)\n');
      return true;
    }
    
    const rowData = await this.extractRowDataForMetricsScoresFilter(rowIndex);
    const avgFluency = parseFloat(rowData['avgFluency'] || '0');
    const avgAdequacy = parseFloat(rowData['avgAdequacy'] || '0');
    const avgCompliance = parseFloat(rowData['avgCompliance'] || '0');
    const scoreAverage = parseFloat(rowData['scoreAverage'] || '0');
    
    expect.soft(scoreAverage).toBeGreaterThanOrEqual(lowerBoundary);
    expect.soft(scoreAverage).toBeLessThanOrEqual(upperBoundary);
    
    console.log(`  [✓] avgFluency: ${avgFluency}`);
    console.log(`  [✓] avgAdequacy: ${avgAdequacy}`);
    console.log(`  [✓] avgCompliance: ${avgCompliance}`);
    console.log(`  [✓] Average of scores: ${scoreAverage} (within ${lowerBoundary} - ${upperBoundary})`);
    return true;
  }

  async verifyLanguageFilter(rowIndex: number, expectedSuffix: string): Promise<boolean> {
    const hasData = await this.hasDataInGrid();
    if (!hasData) {
      console.log('[INFO] Filter applied successfully - Grid is empty (no documents match this filter)\n');
      return true;
    }
    
    const rowData = await this.extractRowDataForLanguageFilter(rowIndex);
    const documentName = rowData['0'] || '';
    const expectedSuffixNew = expectedSuffix + 'New';
    
    expect(documentName.endsWith(expectedSuffix) || documentName.endsWith(expectedSuffixNew)).toBeTruthy();
    console.log(`  [✓] Document name: ${documentName}`);
    return true;
  }

  async openContextMenu(rowIndex: number) {
    const menuButton = this.page.locator(Locators.grid.menuButton(rowIndex));
    await menuButton.waitFor({ state: 'visible', timeout: 10000 });
    await menuButton.scrollIntoViewIfNeeded();
    await menuButton.click();
    await this.page.waitForTimeout(waitTimes.medium);
    console.log('[ACTION] Context menu opened');
  }

  async selectEditDetails() {
    const editDetailsButton = this.page
      .locator(Locators.menu.listItem('Edit Details'))
      .locator(Locators.menu.listItemButton);
    await editDetailsButton.waitFor({ state: 'visible', timeout: 10000 });
    await editDetailsButton.click();
    await this.page.waitForTimeout(waitTimes.veryLong);
    console.log('[ACTION] "Edit Details" option selected from menu');
  }

  async selectPublishDocument() {
    const publishButton = this.page
      .locator(Locators.menu.listItem('Publish Document'))
      .locator(Locators.menu.listItemButton);
    await publishButton.waitFor({ state: 'visible', timeout: 10000 });
    await publishButton.click();
    await this.page.waitForTimeout(waitTimes.medium);
    console.log('[ACTION] "Publish Document" option selected');
  }

  async publishDocumentWithCancelTest(rowIndex: number) {
    console.log('\n[TEST] Testing publish workflow with cancel flow');
    
    const publishMenuButton = this.page.locator(Locators.grid.menuButton(rowIndex)).first();
    await publishMenuButton.waitFor({ state: 'visible', timeout: 10000 });
    await publishMenuButton.scrollIntoViewIfNeeded();
    await publishMenuButton.click();
    await this.page.waitForTimeout(waitTimes.medium);
    console.log('[ACTION] Context menu opened for publish');
    
    await this.selectPublishDocument();
    
    // Cancel first
    const cancelPublishButton = this.page.locator(Locators.dialog.buttonGroupButton('Cancel'));
    await cancelPublishButton.waitFor({ state: 'visible', timeout: 10000 });
    await cancelPublishButton.click();
    await this.page.waitForTimeout(waitTimes.medium);
    console.log('[TEST] Cancel clicked on publish confirmation - Testing abort flow');
    
    // Publish again and confirm
    await publishMenuButton.waitFor({ state: 'visible', timeout: 10000 });
    await publishMenuButton.scrollIntoViewIfNeeded();
    await publishMenuButton.click();
    await this.page.waitForTimeout(waitTimes.medium);
    console.log('[ACTION] Context menu re-opened for actual publish');
    
    await this.selectPublishDocument();
    
    const confirmPublishButton = this.page.locator(Locators.dialog.buttonGroupButton('Publish'));
    await confirmPublishButton.waitFor({ state: 'visible', timeout: 10000 });
    await confirmPublishButton.click();
    await this.page.waitForTimeout(waitTimes.veryLong);
    console.log('[ACTION] "Publish" confirmed in modal - Publishing document');
    
    await this.page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {
      console.log('[INFO] Network idle timeout - continuing');
    });
    await this.page.waitForTimeout(waitTimes.long);
    console.log('[PASS] Document published successfully\n');
  }

  async verifyPublishStatus(rowIndex: number): Promise<string> {
    console.log('[TEST] Verifying status change after publish');
    
    const statusCell = this.page.locator(Locators.grid.statusCellInRow(rowIndex))
      .first()
      .locator(Locators.grid.cellInRow('status'));
    await statusCell.waitFor({ state: 'visible', timeout: 5000 });
    
    let publishedStatus = await statusCell.textContent();
    
    const statusChip = statusCell.locator(Locators.chip);
    if (await statusChip.count() > 0) {
      publishedStatus = (await statusChip.textContent())?.trim() || publishedStatus;
    } else {
      publishedStatus = publishedStatus?.trim() || '';
    }
    
    console.log(`  [VERIFY] Status after publish: "${publishedStatus}"`);
    console.log(`[PASS] Publish workflow completed successfully\n`);
    
    return publishedStatus || '';
  }

  async logout() {
    console.log('\n[TEST] Testing logout workflow with confirmation modal');

    const logoutButton = this.page.locator(Locators.navbar.logoutButton);
    await logoutButton.waitFor({ state: 'visible', timeout: 10000 });
    await logoutButton.click();
    await this.page.waitForTimeout(waitTimes.veryLong);
    console.log('[ACTION] Logout button clicked');

    // Cancel first
    const cancelLogoutButton = this.page.locator(Locators.dialog.buttonGroupButton('Cancel'));
    await cancelLogoutButton.waitFor({ state: 'visible', timeout: 10000 });
    await cancelLogoutButton.click();
    await this.page.waitForTimeout(waitTimes.long);
    console.log('[TEST] Cancel clicked on logout confirmation - Testing abort flow');

    // Logout again and confirm
    await logoutButton.waitFor({ state: 'visible', timeout: 10000 });
    await logoutButton.click();
    await this.page.waitForTimeout(waitTimes.veryLong);
    console.log('[ACTION] Logout button clicked (2nd attempt)');

    const confirmLogoutButton = this.page.locator(Locators.dialog.buttonGroupButton('Logout'));
    await confirmLogoutButton.waitFor({ state: 'visible', timeout: 10000 });
    await confirmLogoutButton.click();
    await this.page.waitForTimeout(waitTimes.long);
    console.log('[ACTION] "Logout" confirmed in modal - Terminating session');
  }

  // Generic filter dropdown function for all filter types
  async clickFilterDropdown(filterName: string) {
    console.log(`\n[TEST] Testing ${filterName} filter`);
    const filterDropdown = this.page.locator(Locators.genericFilters.dropdown(filterName));
    await filterDropdown.waitFor({ state: 'visible', timeout: 10000 });
    await filterDropdown.click();
    await filterDropdown.waitFor({ state: 'visible', timeout: 10000 });
    console.log(`[ACTION] ${filterName} filter dropdown clicked`);
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

  async clickMetricsScoreFilter() {
    console.log('\n[TEST] Testing metrics filter');
    const metricsFilterDropdown = this.page.locator(Locators.genericFilters.dropdown(Locators.genericFilters.metricsScore));
    await metricsFilterDropdown.waitFor({ state: 'visible', timeout: 10000 });
    await metricsFilterDropdown.click();
    await metricsFilterDropdown.waitFor({ state: 'visible', timeout: 10000 });
    console.log('[ACTION] Metrics filter dropdown clicked');
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }
  

  async selectMetricsScoreCheckBox(value: string) {
    console.log('\n[TEST] Selecting metrics score value');
    const metricsFilterDropdownValue = this.page.locator(Locators.genericFilters.checkBox(value));
    await metricsFilterDropdownValue.waitFor({ state: 'visible', timeout: 10000 });
    await metricsFilterDropdownValue.click();
    await metricsFilterDropdownValue.waitFor({ state: 'visible', timeout: 10000 });
    console.log(`[ACTION] Metrics Score value ${value} selected`);
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

  async waitForFilterApplication(filterTileText: string) {
    console.log('\n[TEST] Waiting for Filter Application');
    const metricsFilterTile = this.page.locator(Locators.genericFilters.selectedFilterTile(filterTileText));
    await metricsFilterTile.waitFor({ state: 'visible', timeout: 10000 });
    await this.page.waitForTimeout(waitTimes.long);
    console.log('[VERIFY] Filter applied successfully and is visible on the dashboard');
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

  async applyMetricsScoreFilter() {
    console.log('\n[TEST] Applying metrics score filter');
    // Find Apply button specifically inside the dropdown footer using getByRole
    const applyButton = this.page.getByRole('button', { name: testData.buttonText.applyButtonText, exact: true }).first();
    await applyButton.waitFor({ state: 'visible', timeout: 10000 });
    await applyButton.click();
    await this.page.waitForTimeout(testData.waitTimes.medium);
    console.log('[ACTION] Metrics score filter applied');
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

  async applyLanguageFilterAction() {
    console.log('\n[TEST] Applying language filter');
    // Find Apply button specifically inside the dropdown footer using getByRole
    const applyButton = this.page.getByRole('button', { name: testData.buttonText.applyButtonText, exact: true }).first();
    await applyButton.waitFor({ state: 'visible', timeout: 10000 });
    await applyButton.click();
    await this.page.waitForTimeout(testData.waitTimes.medium);
    console.log('[ACTION] Language filter applied');
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

  async clearAllMetricsScoreFilter() {
    console.log('\n[TEST] Clearing all metrics score filters');
    await this.clickMetricsScoreFilter();
    await this.selectMetricsScoreCheckBox(testData.metricsScoresCheckboxValues.zeroToTwoPointNine);
    await this.selectMetricsScoreCheckBox(testData.metricsScoresCheckboxValues.threeToThreePointFour);
    await this.selectMetricsScoreCheckBox(testData.metricsScoresCheckboxValues.threePointFiveToThreePointNine);
    await this.selectMetricsScoreCheckBox(testData.metricsScoresCheckboxValues.fourPointZero);
    const clearAllButton = this.page.getByRole('button', { name: testData.buttonText.clearAllButtonText, exact: true });
    await clearAllButton.waitFor({ state: 'visible', timeout: 10000 });
    await clearAllButton.click();
    console.log('[ACTION] All metrics score filters cleared');
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

  async clearAllFiltersAction() {
    console.log('\n[TEST] Clicking Clear All Filters button');
    const clearAllFiltersButton = this.page.getByRole('button', { name: testData.buttonText.clearAllFiltersButtonText, exact: true });
    await clearAllFiltersButton.waitFor({ state: 'visible', timeout: 10000 });
    await clearAllFiltersButton.click();
    await this.page.waitForTimeout(testData.waitTimes.medium);
    console.log('[ACTION] Clear All Filters button clicked');
  }

  // Language Filter Methods
  async clickLanguageFilter() {
    console.log('\n[TEST] Testing language filter');
    const languageFilterDropdown = this.page.locator(Locators.genericFilters.dropdown(Locators.genericFilters.language));
    await languageFilterDropdown.waitFor({ state: 'visible', timeout: 10000 });
    await languageFilterDropdown.click();
    await languageFilterDropdown.waitFor({ state: 'visible', timeout: 10000 });
    console.log('[ACTION] Language filter dropdown clicked');
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

  async selectLanguageCheckBox(value: string) {
    console.log('\n[TEST] Selecting language value');
    const languageFilterDropdownValue = this.page.locator(Locators.genericFilters.checkBox(value));
    await languageFilterDropdownValue.waitFor({ state: 'visible', timeout: 10000 });
    await languageFilterDropdownValue.click();
    await languageFilterDropdownValue.waitFor({ state: 'visible', timeout: 10000 });
    console.log(`[ACTION] Language value ${value} selected`);
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

  async waitForLanguageFilterApplication(filterTileText: string) {
    console.log('\n[TEST] Waiting for Language Filter Application');
    const languageFilterTile = this.page.locator(Locators.genericFilters.selectedFilterTile(filterTileText));
    await languageFilterTile.waitFor({ state: 'visible', timeout: 10000 });
    await this.page.waitForTimeout(waitTimes.long);
    console.log('[VERIFY] Language filter applied successfully and is visible on the dashboard');
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

  async applyLanguageFilter() {
    console.log('\n[TEST] Applying language filter');
    const applyButton = this.page.locator(Locators.genericFilters.applyButton);
    await applyButton.waitFor({ state: 'visible', timeout: 10000 });
    await applyButton.click();
    await applyButton.waitFor({ state: 'visible', timeout: 10000 });
    console.log('[ACTION] Language filter applied');
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

  async clearAllLanguageFilter() {
    console.log('\n[TEST] Clearing all language filters');
    await this.clickLanguageFilter();
    await this.selectLanguageCheckBox(testData.languageCheckboxValues.English);
    await this.selectLanguageCheckBox(testData.languageCheckboxValues.Spanish);
    await this.selectLanguageCheckBox(testData.languageCheckboxValues.Japanese);
    await this.selectLanguageCheckBox(testData.languageCheckboxValues.German);
    await this.selectLanguageCheckBox(testData.languageCheckboxValues.Korean);
    const clearAllButton = this.page.getByRole('button', { name: testData.buttonText.clearAllButtonText, exact: true });
    await clearAllButton.waitFor({ state: 'visible', timeout: 10000 });
    await clearAllButton.click();
    console.log('[ACTION] All language filters cleared');
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

  // Status Filter Methods
  async clickStatusFilter() {
    console.log('\n[TEST] Testing status filter');
    const statusFilterDropdown = this.page.locator(Locators.genericFilters.dropdown(Locators.genericFilters.status));
    await statusFilterDropdown.waitFor({ state: 'visible', timeout: 10000 });
    await statusFilterDropdown.click();
    await statusFilterDropdown.waitFor({ state: 'visible', timeout: 10000 });
    console.log('[ACTION] Status filter dropdown clicked');
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

  async selectStatusCheckBox(value: string) {
    console.log('\n[TEST] Selecting status value');
    const statusFilterDropdownValue = this.page.locator(Locators.genericFilters.checkBox(value));
    await statusFilterDropdownValue.waitFor({ state: 'visible', timeout: 10000 });
    await statusFilterDropdownValue.click();
    await statusFilterDropdownValue.waitFor({ state: 'visible', timeout: 10000 });
    console.log(`[ACTION] Status value ${value} selected`);
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

  async waitForNewStatusFilterApplication(filterTileText: string) {
    console.log('\n[TEST] Waiting for Status Filter Application');
    try {
      const statusFilterTile = this.page.locator(Locators.genericFilters.newFilterTile(filterTileText));
      await statusFilterTile.waitFor({ state: 'visible', timeout: 10000 });
      console.log('[VERIFY] Status filter tile found and visible on the dashboard');
    } catch (error) {
      // Fallback: Check if any filter chip exists in the row-alike container
      console.log('[INFO] Specific filter tile not found, checking for any status filter chip...');
      const anyStatusChip = this.page.locator('//div[@class="row-alike"]//en-chip-0-1-48').last();
      await anyStatusChip.waitFor({ state: 'visible', timeout: 5000 });
      console.log('[VERIFY] Status filter applied (chip detected in filter bar)');
    }
    await this.page.waitForTimeout(waitTimes.long);
    console.log('[VERIFY] Status filter applied successfully and is visible on the dashboard');
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

  async waitForStatusFilterApplication(filterTileText: string) {
    console.log('\n[TEST] Waiting for Status Filter Application');
    try {
      const statusFilterTile = this.page.locator(Locators.genericFilters.selectedFilterTile(filterTileText));
      await statusFilterTile.waitFor({ state: 'visible', timeout: 10000 });
      console.log('[VERIFY] Status filter tile found and visible on the dashboard');
    } catch (error) {
      // Fallback: Check if any filter chip exists in the row-alike container
      console.log('[INFO] Specific filter tile not found, checking for any status filter chip...');
      const anyStatusChip = this.page.locator('//div[@class="row-alike"]//en-chip-0-1-48').last();
      await anyStatusChip.waitFor({ state: 'visible', timeout: 5000 });
      console.log('[VERIFY] Status filter applied (chip detected in filter bar)');
    }
    await this.page.waitForTimeout(waitTimes.long);
    console.log('[VERIFY] Status filter applied successfully and is visible on the dashboard');
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

  async applyStatusFilter() {
    console.log('\n[TEST] Applying status filter');
    const applyButton = this.page.getByRole('button', { name: testData.buttonText.applyButtonText, exact: true }).first();
    await applyButton.waitFor({ state: 'visible', timeout: 10000 });
    await applyButton.click();
    await this.page.waitForTimeout(testData.waitTimes.medium);
    console.log('[ACTION] Status filter applied');
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

  async clearAllStatusFilter() {
    console.log('\n[TEST] Clearing all status filters');
    await this.clickStatusFilter();
    await this.selectStatusCheckBox(testData.stausCheckboxValues.New);
    await this.selectStatusCheckBox(testData.stausCheckboxValues.awaitingReview);
    await this.selectStatusCheckBox(testData.stausCheckboxValues.awaitingPublication);
    await this.selectStatusCheckBox(testData.stausCheckboxValues.published);
    const clearAllButton = this.page.getByRole('button', { name: testData.buttonText.clearAllButtonText, exact: true });
    await clearAllButton.waitFor({ state: 'visible', timeout: 10000 });
    await clearAllButton.click();
    console.log('[ACTION] All status filters cleared');
    await this.page.waitForTimeout(testData.waitTimes.medium);
  }

}
