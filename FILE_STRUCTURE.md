# 📁 SCOUT File Structure

## Overview

```
Scout/
├── 🎯 START HERE FIRST
│   └── START_HERE.md                    ← Read this first!
│
├── 🚀 MAIN PROGRAMS
│   ├── main.py                         ← ⭐ THE ONLY FILE YOU RUN - full SCOUT + LinkedIn + background tracker
│   ├── scout_with_linkedin.py          ← Older duplicate entry point (not needed - use main.py)
│   ├── linkedin_tracker.py             ← API-based tracker (needs key)
│   ├── linkedin_rss_tracker.py         ← RSS tracker (no key!) ⭐
│   ├── background_tracker.py           ← Headless background tracker (managed from main.py)
│   └── chatbot.py                      ← Simple chatbot
│
├── 🛠️ UTILITIES
│   ├── setup_linkedin.sh               ← Automated setup script
│   ├── test_linkedin.py                ← Test everything
│   └── example_usage.py                ← Code examples & demos
│
├── 📚 DOCUMENTATION - GETTING STARTED
│   ├── QUICK_START.md                  ← 5-minute quick start
│   ├── LINKEDIN_SETUP.md               ← Complete setup guide
│   └── API_VS_RSS.md                   ← Which method to choose?
│
├── 📚 DOCUMENTATION - REFERENCE
│   ├── IMPLEMENTATION_SUMMARY.md       ← Technical overview
│   ├── COMPLETION_REPORT.md            ← What was built
│   ├── FILE_STRUCTURE.md               ← This file
│   └── README.md                       ← Main project README
│
├── ⚙️ CONFIGURATION
│   ├── requirements.txt                ← Python dependencies
│   ├── .env.example                    ← Example environment variables
│   └── .env                            ← Your API keys (create this)
│
└── 💾 RUNTIME FILES (auto-generated)
    ├── jobs_cache.json                 ← Cached jobs (API method)
    ├── jobs_cache_rss.json             ← Cached jobs (RSS method)
    └── venv/                           ← Python virtual environment
```

---

## 📖 File Descriptions

### 🎯 Start Here
| File | Purpose | When to Use |
|------|---------|-------------|
| **START_HERE.md** | Navigation hub | First time setup |

### 🚀 Main Programs

| File | Purpose | API Key? | Cost | Best For |
|------|---------|----------|------|----------|
| **main.py** | Full SCOUT + LinkedIn + background tracker | Optional | Free | Everything ⭐ |
| **scout_with_linkedin.py** | Older duplicate entry point | Optional | Free | Legacy - use main.py |
| **linkedin_tracker.py** | API-based tracker | Yes | Free tier | Quality data |
| **linkedin_rss_tracker.py** | RSS scraping tracker | No | Free | Unlimited use ⭐ |
| **background_tracker.py** | Headless tracker (cron) | No | Free | Auto-tracking ⭐ |
| **chatbot.py** | Simple chatbot | Optional | Free | Basic chat |

### 🛠️ Utilities

| File | Purpose | When to Run |
|------|---------|-------------|
| **setup_linkedin.sh** | Automated setup | Once (first time) |
| **test_linkedin.py** | Verify installation | After setup |
| **example_usage.py** | Code examples | Learn how it works |

### 📚 Documentation - Getting Started

| File | Length | Level | Read Time |
|------|--------|-------|-----------|
| **QUICK_START.md** | Short | Beginner | 5 minutes |
| **LINKEDIN_SETUP.md** | Long | Intermediate | 15 minutes |
| **API_VS_RSS.md** | Medium | All levels | 10 minutes |

### 📚 Documentation - Reference

| File | Purpose | Audience |
|------|---------|----------|
| **IMPLEMENTATION_SUMMARY.md** | Technical details | Developers |
| **COMPLETION_REPORT.md** | What was delivered | Overview |
| **FILE_STRUCTURE.md** | This file | Navigation |
| **README.md** | Project overview | Everyone |

---

## 🎯 Which File Do I Need?

### "I just want to start NOW"
→ **START_HERE.md** → Then run **main.py**

### "I want step-by-step setup"
→ **QUICK_START.md**

### "I need complete documentation"
→ **LINKEDIN_SETUP.md**

### "Which method should I use?"
→ **API_VS_RSS.md**

### "Show me code examples"
→ Run **example_usage.py**

### "Is everything working?"
→ Run **test_linkedin.py**

### "I want to understand what was built"
→ **IMPLEMENTATION_SUMMARY.md**

---

## 🔄 Typical Workflow

### First Time Setup:
```bash
1. Read START_HERE.md
2. Run ./setup_linkedin.sh
3. Read QUICK_START.md
4. Run python3 test_linkedin.py
5. Choose method (read API_VS_RSS.md)
6. Run python3 backend/cli/main.py
```

### Daily Use:
```bash
1. python3 backend/cli/main.py
2. add job search: Your Job, Location
3. enable background tracker   (track even when SCOUT is closed)
4. latest jobs                (see what was collected)
```

---

## 📊 File Statistics

### By Type:
- **Python files**: 6 files (~1,200 lines)
- **Documentation**: 9 files (~4,000 lines)
- **Shell scripts**: 1 file
- **Config files**: 2 files

### By Purpose:
- **Core functionality**: 3 files (trackers + SCOUT)
- **Original SCOUT**: 2 files (main.py, chatbot.py)
- **Utilities**: 3 files (setup, test, examples)
- **Documentation**: 9 files (guides, refs, reports)
- **Configuration**: 2 files (requirements, env)

### Total:
- **15 new files created**
- **3 files updated**
- **~5,200 total lines**

---

## 🎨 File Size Reference

### Small Files (<5KB):
- .env.example
- requirements.txt
- FILE_STRUCTURE.md

### Medium Files (5-10KB):
- linkedin_tracker.py
- linkedin_rss_tracker.py
- API_VS_RSS.md
- QUICK_START.md
- START_HERE.md
- test_linkedin.py

### Large Files (10-15KB):
- scout_with_linkedin.py
- main.py
- LINKEDIN_SETUP.md
- IMPLEMENTATION_SUMMARY.md
- COMPLETION_REPORT.md

---

## 🔍 Finding Specific Information

### Setup & Installation:
- Quick: **QUICK_START.md**
- Detailed: **LINKEDIN_SETUP.md**
- Automated: **setup_linkedin.sh**

### Usage & Commands:
- Quick ref: **START_HERE.md**
- Examples: **example_usage.py**
- Full guide: **LINKEDIN_SETUP.md**

### Technical Details:
- Architecture: **IMPLEMENTATION_SUMMARY.md**
- What was built: **COMPLETION_REPORT.md**
- Method comparison: **API_VS_RSS.md**

### Troubleshooting:
- Quick fixes: **START_HERE.md** (bottom)
- Detailed: **LINKEDIN_SETUP.md** (troubleshooting section)
- Test issues: **test_linkedin.py** output

---

## 🎓 Learning Path

### Beginner:
1. START_HERE.md (overview)
2. QUICK_START.md (setup)
3. Run main.py (use it)

### Intermediate:
1. LINKEDIN_SETUP.md (detailed setup)
2. API_VS_RSS.md (understand methods)
3. example_usage.py (see code)

### Advanced:
1. IMPLEMENTATION_SUMMARY.md (architecture)
2. Read source code (linkedin_*.py)
3. Customize & extend

---

## 🔧 Customization Guide

### Want to modify checking interval?
→ Edit **background_tracker.py** (`install_cron_tracker`)

### Want to change notification format?
→ Edit **linkedin_tracker.py** or **linkedin_rss_tracker.py** (format_job_notification)

### Want to add custom actions?
→ Edit **main.py** (chat method)

### Want different UI colors?
→ Edit any .py file (Fore.COLOR constants)

---

## 💡 Pro Tips

### Keep These Files:
✅ All .py files (programs)
✅ All .md files (documentation)
✅ requirements.txt (dependencies)
✅ .env (your API keys)

### Can Delete These:
❌ jobs_cache*.json (will regenerate)
❌ __pycache__/ (Python cache)
❌ *.pyc (compiled Python)

### Should Backup:
💾 .env (your API keys)
💾 Custom modifications to .py files
💾 jobs_cache*.json (if you want history)

---

## 🎯 Quick Command Reference

```bash
# Setup
./setup_linkedin.sh                    # Run setup
pip install -r backend/cli/requirements.txt        # Install deps

# Testing
python3 test_linkedin.py               # Test all
python3 example_usage.py               # See examples

# Running
python3 backend/cli/main.py                        # ⭐ Full SCOUT (chat + jobs + background tracker)
python3 background_tracker.py --once   # One-off background check
python3 linkedin_rss_tracker.py        # RSS only

# Maintenance
rm jobs_cache*.json                    # Clear cache
source venv/bin/activate               # Activate venv
pip list                               # See installed packages
```

---

## 📱 Mobile-Friendly Navigation

### I'm on my phone reading this:

**Just getting started?**
→ START_HERE.md

**Need quick setup?**
→ QUICK_START.md

**Choosing a method?**
→ API_VS_RSS.md

**Want to see what it does?**
→ IMPLEMENTATION_SUMMARY.md

**Got an error?**
→ LINKEDIN_SETUP.md (bottom section)

---

## 🎉 You're All Set!

You now understand the file structure. Time to get started!

**Next step**: Open **START_HERE.md** and follow the instructions.

**Or jump right in**:
```bash
python3 backend/cli/main.py
```

Happy job hunting! 🚀💼
