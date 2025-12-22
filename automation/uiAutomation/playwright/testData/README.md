# Test Data

This folder contains all test data in JSON format for easy maintenance and configuration.

## 📄 testData.json

Contains all test data including:

### Credentials
- `email`: Login email address
- `password`: Login password

### URLs
- `loginPage`: Application login URL

### Search Terms
- `pipelineTesting`: Search query for documents

### Document Names
- `pipelineTestingDe`: German document name
- `pipelineTestingKo`: Korean document name
- `pipelineTestingEs`: Spanish document name

### Test Content
- `simpleText`: Simple text for first edit
- `markdownTable`: Complex markdown content for second edit

### Expected Statuses
- `awaitingReview`: Status before review
- `awaitingPublication`: Status after review
- `published`: Status after publishing

### Scores
- `initial`: Initial score value (4.0)
- `fluencyUpdated`: Updated fluency score (2.0)
- `adequacyUpdated`: Updated adequacy score (3.0)
- `complianceUpdated`: Updated compliance score (4.0)

### Wait Times (milliseconds)
- `short`: 500ms
- `medium`: 1000ms
- `long`: 1500ms
- `veryLong`: 2000ms
- `extraLong`: 2500ms
- `navigation`: 3000ms
- `textareaFill`: 800ms

## 🔧 How to Use

The test data is imported in `pages/locators.ts` and exported as `TestData` and `WaitTimes` constants.

```typescript
import { TestData, WaitTimes } from '../pages';

// Use in tests
await page.fill('input[name="email"]', TestData.credentials.email);
await page.waitForTimeout(WaitTimes.medium);
```

## 📝 Maintenance

To update test data:
1. Edit `testData.json` file
2. Save the file
3. Changes will be automatically available in all tests

No code changes needed!
