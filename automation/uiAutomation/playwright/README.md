# Translation Review UI Automation

Playwright-based UI automation tests for the Translation Review application using Page Object Model pattern.

## 📁 Project Structure

```
ui_automation/
├── pages/                      # Page Object Model
│   ├── locators.ts            # All element locators
│   ├── LoginPage.ts           # Login page actions
│   ├── DashboardPage.ts       # Dashboard/Grid actions
│   ├── EditDetailsPage.ts     # Edit details actions
│   └── index.ts               # Export all pages
├── testData/                   # Test data in JSON format
│   ├── testData.json          # All test data
│   └── README.md              # Test data documentation
├── tests/                      # Test specifications
│   ├── loginFlow.spec.ts           # Original test
│   └── loginFlow.refactored.spec.ts # Refactored test with POM
├── playwright.config.ts        # Playwright configuration
├── package.json               # Dependencies
└── README.md                  # This file
```

## 🚀 Getting Started

### Prerequisites
- Node.js (v16 or higher)
- npm

### Installation

1. Navigate to the ui_automation folder:
```powershell
cd e:\content-translation\test\qaAutomation\ui_automation
```

2. Install dependencies:
```powershell
npm install
```

3. Install Playwright browsers:
```powershell
npx playwright install chromium
```

### Running Tests

**Headless mode:**
```powershell
npm test
```

**Headed mode (see browser):**
```powershell
npm run test:headed
```

**Debug mode:**
```powershell
npm run test:debug
```

**UI mode:**
```powershell
npm run test:ui
```

**Specific test:**
```powershell
npx playwright test loginFlow.refactored.spec.ts --headed
```

## 📝 Page Object Model

### LoginPage (`pages/LoginPage.ts`)
- `goto()` - Navigate to login page
- `login(email?, password?)` - Perform login with credentials

### DashboardPage (`pages/DashboardPage.ts`)
- `waitForDashboard()` - Wait for dashboard to load
- `searchDocument(searchTerm?)` - Search for documents
- `findDocumentInGrid(docName)` - Find document in grid
- `extractRowData(rowIndex)` - Extract all row data
- `openContextMenu(rowIndex)` - Open 3-dot menu
- `selectEditDetails()` - Select Edit Details option
- `selectPublishDocument()` - Select Publish option
- `logout()` - Logout with confirmation

### EditDetailsPage (`pages/EditDetailsPage.ts`)
- `waitForEditor()` - Wait for editor to load
- `fillTextarea(content)` - Fill content in textarea
- `verifyTextareaValue(expected)` - Verify textarea content
- `saveChanges(searchBar)` - Save and return to dashboard
- `cancelChanges()` - Cancel without saving
- `saveAndExit(searchBar)` - Save via confirmation dialog
- `navigateSteppers()` - Navigate through sub-documents
- `testPreviousNextButtons()` - Test navigation buttons
- `editScores(fluency, adequacy, compliance)` - Edit document scores

## 🔧 Configuration

### Test Data (`testData/testData.json`)
All test data is centralized in JSON format for easy maintenance:
- **Credentials**: Login email and password
- **URLs**: Application URLs
- **Document names**: Test document identifiers
- **Test content**: Simple text and markdown content
- **Expected statuses**: Document status values
- **Scores**: Initial and updated score values
- **Wait times**: Standardized pause durations

To update test data, simply edit `testData/testData.json` - no code changes needed!

### Locators (`pages/locators.ts`)
All element selectors are defined in one central location:
- Login page elements
- Dashboard elements
- Grid/table elements
- Context menu elements
- Edit details page elements
- Dialog/modal elements
- Navigation elements

## 📊 Test Reports

**View HTML report:**
```powershell
npm run report
```
or
```powershell
npx playwright show-report
```

**View trace for debugging:**
```powershell
npx playwright show-trace test-results/[test-name]/trace.zip
```

## 🐛 Debugging

### Automatic Captures on Failure
- **Screenshots**: Saved in `test-results/`
- **Videos**: Recorded for failed tests
- **Traces**: Available for detailed debugging

### Debug Mode
Run tests with Playwright Inspector:
```powershell
npm run test:debug
```

### UI Mode
Interactive test runner:
```powershell
npm run test:ui
```

## ⚙️ Playwright Configuration (`playwright.config.ts`)

| Setting | Value |
|---------|-------|
| Test timeout | 600 seconds (10 minutes) |
| Browser | Chromium only |
| Viewport | 1466x768 |
| Navigation timeout | 90 seconds |
| Action timeout | 30 seconds |
| Retries | 0 (2 on CI) |
| HTTPS errors | Ignored (for self-signed certs) |

## 📚 Test Examples

### Refactored Test (Recommended)
`tests/loginFlow.refactored.spec.ts` - Clean test using Page Object Model

```typescript
import { LoginPage, DashboardPage, EditDetailsPage, TestData } from '../pages';

test('Complete E2E workflow', async ({ page }) => {
  const loginPage = new LoginPage(page);
  await loginPage.goto();
  await loginPage.login();
  
  const dashboardPage = new DashboardPage(page);
  await dashboardPage.waitForDashboard();
  await dashboardPage.searchDocument();
  // ... more actions
});
```

### Original Test
`tests/loginFlow.spec.ts` - Original implementation with inline locators

## 🎯 Benefits of Page Object Model

1. **Maintainability**: Change a locator once, updates everywhere
2. **Reusability**: Page objects can be used in multiple tests
3. **Readability**: Tests are cleaner and easier to understand
4. **Separation of Concerns**: Test logic separate from page logic
5. **Type Safety**: Full TypeScript support with IntelliSense

## 🔄 Continuous Integration

The project is CI-ready with:
- Automatic retries on failure (CI only)
- HTML report generation
- Screenshot and video capture
- Trace collection for debugging

## ✍️ Writing New Tests

1. Create a new `.spec.ts` file in `tests/` folder
2. Import page objects:
```typescript
import { test, expect } from '@playwright/test';
import { LoginPage, DashboardPage, TestData } from '../pages';
```
3. Write test using page objects
4. Run and verify

## 🛠️ Best Practices

1. ✅ Use Page Object Model for all tests
2. ✅ Store test data in `testData/testData.json`
3. ✅ Use meaningful test descriptions
4. ✅ Keep tests independent and isolated
5. ✅ Add appropriate assertions
6. ✅ Use soft assertions for non-critical checks
7. ✅ Handle dynamic waits properly
8. ✅ Document complex test logic

## 🔍 Troubleshooting

### Tests timeout
- Check if wait times in `testData.json` are appropriate
- Verify network connection speed
- Increase timeout in `playwright.config.ts` if needed

### Locator not found
- Verify locators in `pages/locators.ts`
- Check if Shadow DOM piercing is needed
- Use Playwright Inspector to identify elements

### Test data issues
- Verify `testData/testData.json` is valid JSON
- Check that TypeScript can resolve JSON imports
- Ensure `resolveJsonModule: true` in `tsconfig.json`

## 📖 Additional Resources

- [Playwright Documentation](https://playwright.dev/)
- [Page Object Model](https://playwright.dev/docs/pom)
- [Best Practices](https://playwright.dev/docs/best-practices)
- [Debugging Tests](https://playwright.dev/docs/debug)

## 📧 Support

For issues or questions, contact the QA team.
