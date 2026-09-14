# QA Automation Framework + SmartHealth Backend

This repository now includes both the original QA automation toolkit and the SmartHealth healthcare backend project.

## Included Projects

- `automation/` — API, UI, and performance automation tooling
- `file_formatting_scripts/` — document and format validation utilities
- `performanceTesting/` — load and performance testing scripts
- `healthcareproject/` — FastAPI-based healthcare platform with service-oriented backend architecture

## SmartHealth Backend

The `healthcareproject/` folder contains the healthcare operations and patient engagement platform for MediNova.

### Key areas

- `healthcareproject/services/` — service implementations for `profiles`, `booking`, `billing`, `analytics`, `notification`, and `audit`
- `healthcareproject/libs/` — shared libraries including JWT auth, Kafka helpers, metrics, logging, tracing, and rate limiting
- `healthcareproject/deploy/` — docker, Postgres, Prometheus, and Grafana setup files
- `healthcareproject/docs/` — architecture diagrams, design docs, and project reference materials
- `healthcareproject/postman/` — Postman collection for API exploration
- `healthcareproject/scripts/` — utility and setup scripts

### Documentation

The SmartHealth project documentation lives in `healthcareproject/README.md` and includes:

- architecture overview and technical flow reference
- service responsibilities and database model notes
- setup and local deployment instructions
- observability and monitoring guidance

See also:

- `healthcareproject/docs/smarthealth_tech_flow_reference.html`
- `healthcareproject/deploy/docker-manual-commands.md`

## 🚀 Quick Start

```bash
# Python setup for document testing
pip install -r requirements.txt
python file_formatting_scripts/comparison_scripts/image_verification.py

# API testing setup
cd automation/api_automation
npm install
npm test

# Performance testing
cd performanceTesting/k6_productCreationScript
k6 run mainSuite/main.js
```

## 📁 Project Structure

```
├── healthcareproject/               # SmartHealth backend platform
│   ├── docs/                       # Architecture, diagrams, and design docs
│   ├── deploy/                     # Deployment and observability configuration
│   ├── libs/                       # Shared Python libraries
│   ├── services/                   # FastAPI service modules
│   ├── scripts/                    # JWT and setup utilities
│   ├── postman/                    # API collection
│   ├── README.md                   # SmartHealth project overview
│   ├── docker-compose.yml          # Local orchestration config
│   └── Makefile                    # Common project tasks
├── file_formatting_scripts/         # Document verification tools
│   ├── comparison_scripts/
│   └── format_verification_scripts/
├── automation/
│   ├── api_automation/
│   └── uiAutomation/
├── performanceTesting/
│   ├── k6_productCreationScript/
│   └── chatWithDocumentScript/
├── requirements.txt
├── README.md
├── LICENSE
└── CONTRIBUTING.md
```

## 🛠 Technology Stack

| Component | Technologies |
|-----------|-------------|
| **Document Testing** | Python, PyMuPDF, pdfplumber, BeautifulSoup |
| **API Testing** | TypeScript, Mocha, Chai, Axios |
| **UI Testing** | WebdriverIO, Cucumber, TypeScript |
| **Performance Testing** | K6, JavaScript |
| **SmartHealth Backend** | Python, FastAPI, SQLAlchemy, PostgreSQL, Kafka, Temporal, Celery, Prometheus, Grafana, Jaeger |

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

The repository is now ready to contain both the automation toolkit and the SmartHealth healthcare backend project.