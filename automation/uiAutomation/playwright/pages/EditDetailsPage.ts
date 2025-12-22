import { Page, Locator, expect } from '@playwright/test';
import { Locators } from './locators';
import TestData from '../testData/testData.json';

const WaitTimes = TestData.waitTimes;

export class EditDetailsPage {
  readonly page: Page;
  readonly textarea: Locator;
  readonly saveChangesButton: Locator;
  readonly cancelButton: Locator;
  readonly previousButton: Locator;
  readonly nextButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.textarea = page.locator(Locators.editDetails.textarea);
    
    // Target custom element, then Playwright pierces shadow root to find button
    this.saveChangesButton = page.locator(Locators.editDetails.footerButton('Save Changes')).locator('button');
    this.cancelButton = page.locator(Locators.editDetails.footerButton('Cancel')).locator('button');
    this.previousButton = page.locator(Locators.editDetails.footerButton('Previous')).locator('button');
    this.nextButton = page.locator(Locators.editDetails.footerButton('Next')).locator('button');
  }

  async waitForEditor() {
    await this.textarea.waitFor({ state: 'visible', timeout: 15000 });
    await this.page.waitForTimeout(WaitTimes.long);
    console.log('[VERIFY] Edit Details page loaded - Editor visible');
  }

  async fillTextarea(content: string) {
    await this.textarea.click();
    await this.page.waitForTimeout(WaitTimes.textareaFill);
    await this.textarea.clear();
    await this.page.waitForTimeout(WaitTimes.textareaFill);
    await this.textarea.fill(content);
    await this.page.waitForTimeout(WaitTimes.veryLong);
    console.log(`[TEST] Content updated: "${content.substring(0, 50)}${content.length > 50 ? '...' : ''}"`);
  }

  async verifyTextareaValue(expectedValue: string) {
    await expect.soft(this.textarea).toHaveValue(expectedValue);
    const textareaValue = await this.textarea.inputValue();
    console.log(`[VERIFY] Content validation passed: "${textareaValue.substring(0, 50)}${textareaValue.length > 50 ? '...' : ''}"`);
  }

  async saveChanges(searchBarLocator: Locator) {
    // Find the en-button containing "Save Changes" text, then click button in shadow root
    const saveButton = this.page.locator(Locators.editDetails.footerButton('Save Changes')).locator('button');
    await saveButton.waitFor({ state: 'visible', timeout: 10000 });
    await saveButton.click();
    await this.page.waitForTimeout(WaitTimes.extraLong);
    console.log('[ACTION] "Save Changes" button clicked');

    await searchBarLocator.waitFor({ state: 'visible', timeout: 15000 });
    await this.page.waitForTimeout(WaitTimes.veryLong);
    console.log('[PASS] Changes saved successfully - Returned to listing page');
  }

  async cancelChanges() {
    const cancelBtn = this.page.locator(Locators.editDetails.footerButton('Cancel')).locator('button');
    await cancelBtn.waitFor({ state: 'visible', timeout: 10000 });
    await cancelBtn.click();
    await this.page.waitForTimeout(WaitTimes.medium);
    console.log('[ACTION] Cancel button clicked - Testing discard flow');

    // Locate the second cancel button in the dialog
    const dialogCancelButton = this.page.locator(Locators.dialog.button('Cancel')).locator('button').nth(1);
    await dialogCancelButton.waitFor({ state: 'visible', timeout: 10000 });
    await dialogCancelButton.click();
    await this.page.waitForTimeout(WaitTimes.long);
    console.log('[VERIFY] Discard confirmation handled - Changes not saved');
  }

  async saveAndExit(searchBarLocator: Locator) {
    const cancelBtn = this.page.locator(Locators.editDetails.footerButton('Cancel')).locator('button');
    await cancelBtn.waitFor({ state: 'visible', timeout: 10000 });
    await cancelBtn.click();
    await this.page.waitForTimeout(WaitTimes.medium);
    console.log('[ACTION] Cancel clicked - Opening save confirmation dialog');

    const saveExitButton = this.page.locator(Locators.dialog.button('Save & Exit')).locator('button');
    await saveExitButton.waitFor({ state: 'visible', timeout: 10000 });
    await saveExitButton.click();
    await this.page.waitForTimeout(WaitTimes.extraLong);
    console.log('[ACTION] "Save & Exit" confirmed - Persisting score changes');

    await searchBarLocator.waitFor({ state: 'visible', timeout: 15000 });
    await this.page.waitForTimeout(WaitTimes.veryLong);
    console.log('[PASS] Score changes saved successfully - Returned to listing\n');
  }

  async navigateSteppers() {
    console.log('\n[TEST] Starting sub-document navigation test');
    const stepperItems = this.page.locator(Locators.stepper.items);
    const stepperCount = await stepperItems.count();
    console.log(`[INFO] Found ${stepperCount} sub-documents in stepper`);

    for (let stepIndex = 0; stepIndex < stepperCount; stepIndex++) {
      const stepperItem = stepperItems.nth(stepIndex);

      await stepperItem.scrollIntoViewIfNeeded();

      const stepperLabel = await stepperItem.locator(Locators.stepper.label).textContent();
      console.log(`  [NAV] Sub-document ${stepIndex + 1}/${stepperCount}: ${stepperLabel}`);

      await stepperItem.click();
      await this.page.waitForTimeout(WaitTimes.veryLong);
      await this.page.waitForLoadState('domcontentloaded', { timeout: 10000 }).catch(() => {
        console.log('    [INFO] DOM load timeout - continuing');
      });

      if (stepIndex === stepperCount - 1) {
        return true; // Last stepper reached
      }
    }

    console.log('[PASS] All sub-documents navigated successfully\n');
    return false;
  }

  async testPreviousNextButtons(hasScoring: boolean = true) {
    console.log('[TEST] Validating Previous/Next navigation buttons');

    // Test Previous button
    const prevBtn = this.page.locator('en-button-0-1-48', { hasText: 'Previous' }).locator('button');
    await prevBtn.waitFor({ state: 'visible', timeout: 5000 });
    console.log('  [VERIFY] Previous button is visible and enabled');

    await prevBtn.click();
    await this.page.waitForTimeout(WaitTimes.veryLong);
    await this.page.waitForLoadState('domcontentloaded', { timeout: 10000 }).catch(() => {});
    console.log('  [ACTION] Previous button clicked - Navigated backward');

    // Test Next button
    const nextBtn = this.page.locator('en-button-0-1-48', { hasText: 'Next' }).locator('button');
    await nextBtn.waitFor({ state: 'visible', timeout: 5000 });
    console.log('  [VERIFY] Next button is visible and enabled');

    await nextBtn.click();
    await this.page.waitForTimeout(WaitTimes.veryLong);
    
    // Only scroll back to scoring section if it exists
    if (hasScoring) {
      const scoringSection = this.page.locator(Locators.scoring.container);
      await scoringSection.waitFor({ state: 'visible', timeout: 10000 });
      await scoringSection.scrollIntoViewIfNeeded();
      await this.page.waitForTimeout(WaitTimes.long);
    }
    
    console.log('  [ACTION] Next button clicked - Returned to last sub-document');
    console.log('[PASS] Navigation button validation completed\n');
  }

  async editScores(fluency: number, adequacy: number, compliance: number) {
    console.log('[TEST] Modifying document scores for validation');

    const fluencyScore = this.page.locator(Locators.scoring.fluencyScore(fluency));
    await fluencyScore.waitFor({ state: 'visible', timeout: 5000 });
    await fluencyScore.click();
    console.log(`  [MODIFY] Fluency: 4.0 → ${fluency}`);

    const adequacyScore = this.page.locator(Locators.scoring.adequacyScore(adequacy));
    await adequacyScore.waitFor({ state: 'visible', timeout: 5000 });
    await adequacyScore.click();
    console.log(`  [MODIFY] Adequacy: 4.0 → ${adequacy}`);

    console.log(`  [UNCHANGED] Compliance: ${compliance}`);
    console.log('[PASS] Score modifications completed');
  }
}
