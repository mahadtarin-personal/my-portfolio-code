/**
 * Centralized Locators for Translation Review Application
 * All element selectors are defined here for easy maintenance
 */

export const Locators = {
  // Login Page
  login: {
    emailInput: 'input.en-c-text-field__input[name="email"]',
    passwordInput: 'input.en-c-text-field__input[name="password"]',
    submitButton: 'button[type="submit"]',
  },

  // Dashboard
  dashboard: {
    title: 'h1.heading',
    titleAlt: (pageTitle: string) => `h1:has-text("${pageTitle}")`,
    searchInput: 'input[placeholder="Search"]',
    searchInputAlt1: 'input.en-c-text-field__input[type="text"]',
    searchInputAlt2: 'input[type="text"]',
    searchButton: '.en-c-search-field__search-button',
  },

  // Grid/Table
  grid: {
    cell: 'div[role="gridcell"]',
    row: (rowId: number) => `div[role="row"][row-id="${rowId}"]`,
    cellByColId: (colId: number) => `div[role="gridcell"][col-id="${colId}"]`,
    cellByColIdAlt: (colId: number) => `[col-id="${colId}"]`,
    menuButton: (rowId: number) => `//div[@row-id=${rowId}]//span[contains(@class, 'flex-center') and contains(@class, 'menu-container')]`,
    cellByRowAndCol: (rowId: number, colId: string) => `div[role="row"][row-id="${rowId}"] div[role="gridcell"][col-id="${colId}"]`,
    cellInRow: (colId: string) => `div[role="gridcell"][col-id="${colId}"]`,
    statusCellInRow: (rowId: number) => `div[role="row"][row-id="${rowId}"]`,
  },

  // Context Menu
  menu: {
    listItem: (text: string) => `en-list-item-0-1-48:has-text("${text}")`,
    listItemButton: 'button >> span',
  },

  // Edit Details Page
  editDetails: {
    textarea: 'div.w-md-editor-text textarea',
    footerButton: (text: string) => `footer.footer en-button-0-1-48:has-text("${text}")`,
  },

  // Stepper Navigation
  stepper: {
    items: 'ul.stepper li.stepper-item',
    label: 'p.stepper-label',
  },

  // Scoring Section
  scoring: {
    container: 'div.comment-metrics-container',
    fluencyScore: (value: number) => `input#fluency2[name="fluency"][value="${value}"]`,
    adequacyScore: (value: number) => `input#adequacy4[name="adequacy"][value="${value}"]`,
    complianceScore: (value: number) => `input#compliance6[name="compliance"][value="${value}"]`,
  },

  // Dialogs/Modals
  dialog: {
    button: (text: string) => `en-button-0-1-48:has-text("${text}")`,
    buttonGroupButton: (text: string) => `en-button-group-0-1-48 en-button-0-1-48:has-text("${text}") >> button`,
  },

  // Navbar
  navbar: {
    logoutButton: 'div[role="banner"].navbar en-button-0-1-48 >> button',
  },

  // Generic filter locators that work for all filter types
  genericFilters: {
    metricsScore: 'Metrics Score',
    language: 'Language',
    status: 'Status',
    dropdown: (filterName: string) => `//div[@class="dropdown"]//button[contains(., "${filterName}")]`,
    checkBox: (value: string) => `input.en-c-checkbox-item__input[value="${value}"]`,
    selectedFilterTile: (text: string) => `//span[text()="${text}"]`,
    newFilterTile: (text: string) => `//div[@class="row-alike"]//span[contains(text(), "${text}")]`,
    clearAllButton: '//div[@class="dropdown__footer"] >> button:has-text("Clear All")',
    applyButton: '//div[@class="dropdown__footer"] >> button:has-text("Apply")',
    clearAllFiltersButton: '//button[contains(., "Clear all filters")]',
  },

  // Custom Elements
  chip: 'en-chip-0-1-48',
};
