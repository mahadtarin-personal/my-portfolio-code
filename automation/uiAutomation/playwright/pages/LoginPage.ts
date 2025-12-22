import { Page, Locator } from '@playwright/test';
import { Locators } from './locators';
import TestData from '../testData/testData.json';

const WaitTimes = TestData.waitTimes;

export class LoginPage {
  readonly page: Page;
  readonly emailInput: Locator;
  readonly passwordInput: Locator;
  readonly submitButton: Locator;
  private baseURL: string;
  private credentials: { email: string; password: string };

  constructor(page: Page, baseURL: string, credentials: { email: string; password: string }) {
    this.page = page;
    this.baseURL = baseURL;
    this.credentials = credentials;
    this.emailInput = page.locator(Locators.login.emailInput);
    this.passwordInput = page.locator(Locators.login.passwordInput);
    this.submitButton = page.locator(Locators.login.submitButton);
  }

  async goto() {
    await this.page.goto(`${this.baseURL}/login`, {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });
  }

  async login(email: string = this.credentials.email, password: string = this.credentials.password) {
    await this.emailInput.waitFor({ state: 'visible', timeout: 10000 });
    await this.emailInput.fill(email);
    console.log('[TEST] Email field populated successfully');

    await this.passwordInput.waitFor({ state: 'visible', timeout: 10000 });
    await this.passwordInput.fill(password);
    console.log('[TEST] Password field populated successfully');

    await this.submitButton.click();
    await this.page.waitForTimeout(WaitTimes.long);
    console.log('[ACTION] Login button clicked');
  }
}
