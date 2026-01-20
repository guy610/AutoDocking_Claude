# Technology Stack

**Project:** Cosmetic FTO Search Agent
**Researched:** 2026-01-20
**Overall Confidence:** HIGH

---

## Executive Summary

For a desktop FTO patent search application targeting chemists (non-developers), the recommended stack is **pure Python with PySide6 for GUI, packaged with PyInstaller**. This approach was chosen because:

1. **Chemists know Python** - Many chemists already have Python exposure from data analysis
2. **RDKit is Python-native** - The gold standard for chemical informatics runs natively in Python
3. **Single-language stack** - Simpler maintenance, no JavaScript/Rust learning curve
4. **Mature packaging** - PyInstaller produces reliable single-file executables

---

## Recommended Stack

### Core Framework: Python + PySide6

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|------------|
| **Python** | 3.12 | Core runtime | HIGH |
| **PySide6** | 6.10.1 | Desktop GUI framework | HIGH |
| **PyInstaller** | 6.18.0 | Executable packaging | HIGH |

**Why PySide6 over alternatives:**

| Alternative | Why Not |
|-------------|---------|
| Tkinter | Dated appearance, limited widgets, unprofessional for end-user app |
| PyQt6 | GPL license requires commercial license for proprietary use; PySide6 is LGPL |
| Electron/Tauri | Requires JavaScript, adds complexity, overkill for this use case |
| wxPython | Smaller community, less modern look than Qt |

**Rationale:** PySide6 is the official Qt for Python binding with LGPL licensing (no commercial license needed). Qt provides professional-looking native widgets, built-in styling, and excellent documentation. The Qt ecosystem includes Qt Designer for WYSIWYG UI design if needed.

**Source:** [PySide6 on PyPI](https://pypi.org/project/PySide6/), [Qt for Python Documentation](https://doc.qt.io/qtforpython-6/)

---

### Chemical Processing: RDKit

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|------------|
| **RDKit** | 2025.09.4 | SMILES parsing, structure visualization, similarity search | HIGH |

**Why RDKit:**
- Industry standard for cheminformatics in Python
- Native SMILES parsing with `Chem.MolFromSmiles()`
- Substructure search with `HasSubstructMatch()`
- Fingerprint-based similarity search (Morgan/ECFP fingerprints + Tanimoto)
- 2D structure rendering to images
- Actively maintained (current version 2025.09.4)

**Key capabilities for FTO search:**
```python
from rdkit import Chem
from rdkit.Chem import Draw

# Parse SMILES
mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")  # Aspirin

# Render structure image
img = Draw.MolToImage(mol, size=(300, 300))

# Substructure matching (find molecules containing benzene)
pattern = Chem.MolFromSmiles("c1ccccc1")
has_benzene = mol.HasSubstructMatch(pattern)
```

**Installation:**
```bash
# Recommended: Use conda for RDKit (handles C++ dependencies)
conda install -c conda-forge rdkit
```

**Source:** [RDKit Documentation](https://www.rdkit.org/docs/GettingStartedInPython.html)

---

### Patent Database Access

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|------------|
| **Playwright** | 1.57.0 | Web automation for patent searches | HIGH |
| **python-epo-ops-client** | 4.2.1 | EPO/Espacenet API access | HIGH |
| **requests** | latest | HTTP requests to PatentsView API | HIGH |

**Patent Database Strategy:**

| Database | Access Method | API Available | Notes |
|----------|---------------|---------------|-------|
| **USPTO PatentsView** | REST API | YES (free) | New PatentSearch API (legacy discontinued May 2025). 45 requests/minute with API key. |
| **EPO Espacenet** | REST API | YES (free with registration) | python-epo-ops-client library v4.2.1 provides full access |
| **Google Patents** | Web scraping | NO (unofficial only) | Use Playwright for reliable scraping; no official API |
| **WIPO PATENTSCOPE** | Paid API | YES (paid) | 2,000-3,900 CHF/year; recommend deferring to future phase |

**Why Playwright over Selenium:**
- Faster execution (0.4s vs 1.5s startup in benchmarks)
- Modern async API, cleaner code
- Auto-waits for elements (less flaky tests)
- Built-in browser management (no separate ChromeDriver)
- Better handling of JavaScript-heavy sites

**Google Patents scraping note:** Google Patents has no official API. The `google-patent-scraper` PyPI package exists but is fragile. Recommend building custom Playwright scraper with:
- Proper rate limiting (respect robots.txt)
- Retry logic for transient failures
- User-Agent rotation if needed

**Sources:**
- [PatentsView API](https://patentsview.org/apis/purpose)
- [python-epo-ops-client on PyPI](https://pypi.org/project/python-epo-ops-client/)
- [Playwright on PyPI](https://pypi.org/project/playwright/)

---

### PDF Generation: ReportLab

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|------------|
| **ReportLab** | 4.4.9 | PDF report generation | HIGH |

**Why ReportLab over alternatives:**

| Alternative | Why Not |
|-------------|---------|
| fpdf2 | Simpler but limited styling; ReportLab better for professional reports |
| WeasyPrint | HTML-to-PDF is overkill; adds complexity |
| pdfkit | Requires wkhtmltopdf system dependency |

**Rationale:** ReportLab provides precise canvas-based control for professional FTO reports with:
- Custom headers/footers
- Tables for patent data
- Embedded chemical structure images (from RDKit)
- Charts for analysis visualization

**Example usage:**
```python
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

c = canvas.Canvas("fto_report.pdf", pagesize=letter)
c.drawString(100, 750, "FTO Analysis Report")
c.drawImage("structure.png", 100, 500, width=200, height=200)
c.save()
```

**Source:** [ReportLab on PyPI](https://pypi.org/project/reportlab/), [ReportLab Documentation](https://docs.reportlab.com/)

---

### Excel Generation: XlsxWriter

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|------------|
| **XlsxWriter** | 3.2.9 | Excel report generation | HIGH |

**Why XlsxWriter over openpyxl:**

| Criterion | XlsxWriter | openpyxl |
|-----------|------------|----------|
| Write performance | Faster (3 min vs 9 min for 200K rows) | Slower |
| Read existing files | No | Yes |
| Advanced formatting | Better (rich text in cells) | Good |
| Our use case | Creating new reports | N/A |

**Rationale:** We only need to CREATE Excel files (not read/modify existing). XlsxWriter is optimized for this with better performance and formatting options.

**Example usage:**
```python
import xlsxwriter

workbook = xlsxwriter.Workbook('fto_patents.xlsx')
worksheet = workbook.add_worksheet('Patents')

# Headers with formatting
header_format = workbook.add_format({'bold': True, 'bg_color': '#4472C4', 'font_color': 'white'})
worksheet.write_row(0, 0, ['Patent ID', 'Title', 'Assignee', 'Priority Date', 'Risk Level'], header_format)

# Data rows
worksheet.write_row(1, 0, ['US10123456', 'Cosmetic composition', 'L\'Oreal', '2020-03-15', 'High'])

workbook.close()
```

**Source:** [XlsxWriter on PyPI](https://pypi.org/project/xlsxwriter/), [XlsxWriter Documentation](https://xlsxwriter.readthedocs.io/)

---

### Application Packaging: PyInstaller

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|------------|
| **PyInstaller** | 6.18.0 | Create Windows executable | HIGH |

**Why PyInstaller:**
- Most mature Python packaging tool
- Single-file executable option (`--onefile`)
- Works with PySide6 and RDKit (tested)
- Active maintenance, supports Python 3.8-3.14
- Used by production apps (Dropbox, BitTorrent clients)

**Build command:**
```bash
pyinstaller --onefile --windowed --name "FTO Search" --icon=icon.ico main.py
```

**Flags explained:**
- `--onefile`: Single executable (vs folder with dependencies)
- `--windowed`: No console window (GUI app)
- `--name`: Output executable name
- `--icon`: Windows icon

**RDKit packaging note:** RDKit with PyInstaller requires special handling due to C++ dependencies. Use a PyInstaller spec file with hidden imports:
```python
# fto_search.spec
hiddenimports=['rdkit', 'rdkit.Chem', 'rdkit.Chem.Draw']
```

**Source:** [PyInstaller on PyPI](https://pypi.org/project/pyinstaller/), [PyInstaller Documentation](https://www.pyinstaller.org/)

---

## Complete Stack Summary

```
┌─────────────────────────────────────────────────────────────┐
│                     FTO Search Agent                        │
├─────────────────────────────────────────────────────────────┤
│  GUI Layer                                                  │
│  └── PySide6 6.10.1 (Qt for Python, LGPL)                  │
├─────────────────────────────────────────────────────────────┤
│  Business Logic                                             │
│  ├── RDKit 2025.09.4 (SMILES processing)                   │
│  ├── Playwright 1.57.0 (Google Patents scraping)           │
│  ├── python-epo-ops-client 4.2.1 (Espacenet API)           │
│  └── requests (USPTO PatentsView API)                       │
├─────────────────────────────────────────────────────────────┤
│  Output Generation                                          │
│  ├── ReportLab 4.4.9 (PDF reports)                         │
│  └── XlsxWriter 3.2.9 (Excel spreadsheets)                 │
├─────────────────────────────────────────────────────────────┤
│  Packaging                                                  │
│  └── PyInstaller 6.18.0 (Windows executable)               │
└─────────────────────────────────────────────────────────────┘
```

---

## Installation

### Development Environment Setup

```bash
# Create conda environment (recommended for RDKit)
conda create -n fto-search python=3.12
conda activate fto-search

# Install RDKit via conda (handles C++ dependencies)
conda install -c conda-forge rdkit=2025.09.4

# Install other dependencies via pip
pip install PySide6==6.10.1
pip install playwright==1.57.0
pip install python-epo-ops-client==4.2.1
pip install reportlab==4.4.9
pip install xlsxwriter==3.2.9
pip install requests

# Install Playwright browsers
playwright install chromium

# Development tools
pip install pyinstaller==6.18.0
```

### requirements.txt

```
PySide6==6.10.1
playwright==1.57.0
python-epo-ops-client==4.2.1
reportlab==4.4.9
xlsxwriter==3.2.9
requests>=2.31.0
```

**Note:** RDKit should be installed via conda, not pip, for reliable C++ dependency management.

---

## Alternatives Considered

### GUI Framework Alternatives

| Framework | Considered | Rejected Because |
|-----------|------------|------------------|
| **Electron** | Yes | Requires JavaScript, 100MB+ bundle size, overkill |
| **Tauri** | Yes | Requires Rust for backend, steeper learning curve |
| **Tkinter** | Yes | Dated appearance, limited widgets |
| **PyQt6** | Yes | GPL licensing requires commercial license |
| **wxPython** | Yes | Smaller community, less modern |
| **Streamlit** | Yes | Web-based, not a desktop app |

### PDF Generation Alternatives

| Library | Considered | Rejected Because |
|---------|------------|------------------|
| **fpdf2** | Yes | Limited styling for professional reports |
| **WeasyPrint** | Yes | HTML-to-PDF adds unnecessary complexity |
| **pdfkit** | Yes | Requires wkhtmltopdf system dependency |

### Excel Generation Alternatives

| Library | Considered | Rejected Because |
|---------|------------|------------------|
| **openpyxl** | Yes | Slower for write-only use case |
| **pandas** | Yes | Overkill, adds heavy dependency |

### Web Automation Alternatives

| Library | Considered | Rejected Because |
|---------|------------|------------------|
| **Selenium** | Yes | Slower, requires separate ChromeDriver, more setup |
| **requests + BeautifulSoup** | Yes | Can't handle JavaScript-rendered patent pages |

---

## What NOT to Use

### Avoid These Technologies

| Technology | Why Avoid |
|------------|-----------|
| **PySimpleGUI** | No longer actively developed (deprecated in 2026) |
| **Tkinter** | Dated appearance inappropriate for end-user product |
| **Electron** | Overkill for this use case, massive bundle size |
| **google-patent-scraper** | Unmaintained, fragile; build custom Playwright scraper |
| **Paid patent APIs** | Out of scope for public database requirement |
| **Python 3.8/3.9** | Near end-of-life; use 3.12 for longevity |

---

## Risk Assessment

| Component | Risk Level | Mitigation |
|-----------|------------|------------|
| Google Patents scraping | MEDIUM | Rate limiting, retry logic, monitor for site changes |
| RDKit + PyInstaller | LOW | Well-documented, use spec file with hidden imports |
| USPTO API | LOW | Official API with documented rate limits |
| Espacenet API | LOW | Official client library, stable |
| PySide6 styling | LOW | Qt has excellent documentation, theming support |

---

## Sources

### Official Documentation (HIGH confidence)
- [RDKit Documentation](https://www.rdkit.org/docs/GettingStartedInPython.html) - Version 2025.09.4
- [PySide6 Documentation](https://doc.qt.io/qtforpython-6/) - Version 6.10.1
- [PyInstaller Documentation](https://www.pyinstaller.org/) - Version 6.18.0
- [ReportLab Documentation](https://docs.reportlab.com/) - Version 4.4.9
- [XlsxWriter Documentation](https://xlsxwriter.readthedocs.io/) - Version 3.2.9
- [Playwright Python Documentation](https://playwright.dev/python/docs/intro) - Version 1.57.0

### API Documentation (HIGH confidence)
- [USPTO PatentsView API](https://patentsview.org/apis/purpose) - Updated Q3 2025
- [EPO Open Patent Services](https://pypi.org/project/python-epo-ops-client/) - Version 4.2.1

### Comparison Articles (MEDIUM confidence)
- [Python GUI Framework Comparison 2026](https://www.pythonguis.com/faq/which-python-gui-library/)
- [Tauri vs Electron 2025](https://www.raftlabs.com/blog/tauri-vs-electron-pros-cons/)
- [Playwright vs Selenium 2025](https://www.browserless.io/blog/playwright-vs-selenium-2025-browser-automation-comparison)
- [Python PDF Libraries 2025](https://templated.io/blog/generate-pdfs-in-python-with-libraries/)
- [Python Excel Libraries 2025](https://sheetflash.com/blog/the-best-python-libraries-for-excel-in-2024)
