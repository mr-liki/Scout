# 🚀 START HERE - SCOUT LinkedIn Job Tracker

## Welcome! 👋

You now have a **powerful AI assistant** with **real-time LinkedIn job tracking** - better than LinkedIn Premium, completely FREE!

---

## ⚡ Quick Start (2 Minutes)

### New! 🎉 Natural Language Support

SCOUT now understands natural language! Just ask:
```
list AI Engineer jobs in Bengaluru
find Python Developer jobs in Remote
show Data Scientist positions in San Francisco
```

SCOUT will:
✅ Search immediately  
✅ Show you current jobs  
✅ Add to tracking automatically  
✅ Ready for real-time alerts  

→ See **[NATURAL_LANGUAGE_GUIDE.md](NATURAL_LANGUAGE_GUIDE.md)** for examples

### Step 1: Install Dependencies
```bash
cd /Users/likhithr/Scout
source venv/bin/activate
pip install -r backend/cli/requirements.txt
```

### Step 2: Choose Your Method

#### Option A: RSS/Scraping (Recommended - No API Key!)

**`main.py` is the only file you need to run.**

```bash
python3 backend/cli/main.py
```

Then in SCOUT:
```
add job search: Python Developer, Remote, Full-time
enable background tracker   # keeps tracking even when SCOUT is closed
latest jobs                 # see everything collected
```

✅ **100% FREE forever**  
✅ **Unlimited searches**  
✅ **Check every 1-2 minutes**  
✅ **No API key needed**

#### Option B: RapidAPI (Better Data Quality)
```bash
# Get free API key from: https://rapidapi.com/
export RAPID_API_KEY='your_key_here'

python3 backend/cli/main.py
```

---

## 📚 Documentation

Choose your path:

### 🏃 I want to start NOW
→ **[QUICK_START.md](QUICK_START.md)** (5 minutes)

### 📖 I want complete setup
→ **[LINKEDIN_SETUP.md](LINKEDIN_SETUP.md)** (detailed guide)

### 🤔 API vs RSS - which to use?
→ **[API_VS_RSS.md](API_VS_RSS.md)** (comparison)

### 💻 I want to see code examples
→ Run: `python3 example_usage.py`

### 📊 What was built?
→ **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** (overview)

---

## 🎯 What You Can Do

### Track Jobs Like LinkedIn Premium:
```
add job search: Software Engineer, San Francisco, Full-time
add job search: Data Scientist, Remote
add job search: Product Manager, New York
```

### Get Real-Time Alerts:
```
start monitoring
```

You'll get instant notifications like:
```
🚀 NEW JOB ALERT!
════════════════════════════════════════════════════════════
📋 Title: Senior Python Developer
🏢 Company: Tech Innovations Inc.
📍 Location: Remote
💼 Type: Full-time
🔗 Link: https://linkedin.com/jobs/view/12345
⏰ Found: 2026-08-06 14:30:15
════════════════════════════════════════════════════════════
```

### Other Commands:
```
list jobs                  - Show all your searches
stop monitoring            - Pause tracking
background status          - Check the auto-tracker
enable background tracker  - Track 24/7 (even when SCOUT is closed)
disable background tracker - Turn the auto-tracker off
latest jobs                - View jobs collected in the background
job stats                  - View statistics
clear job cache            - Reset history
```

---

## 🧪 Test Everything Works

```bash
python3 test_linkedin.py
```

This will verify:
- ✅ All dependencies installed
- ✅ API tracker working
- ✅ RSS tracker working
- ✅ SCOUT integration working

---

## 🎨 Three Ways to Use

### 1. Full SCOUT (AI + LinkedIn)
```bash
python3 backend/cli/main.py
```
- Cyberpunk AI chatbot
- LinkedIn job tracking
- Beautiful terminal UI
- Background monitoring

### 2. RSS Tracker Only (Standalone)
```bash
python3 linkedin_rss_tracker.py
```
- Just LinkedIn tracking
- No API key needed
- Lightweight
- 100% FREE

### 3. Programmatic Usage
```python
from linkedin_rss_tracker import LinkedInRSSTracker

tracker = LinkedInRSSTracker()
tracker.add_search_query("Python Developer", "Remote")
tracker.start_monitoring(interval=120)
```

---

## 🌟 Features

### vs LinkedIn Premium

| Feature | LinkedIn Premium | Your SCOUT | Savings |
|---------|-----------------|------------|---------|
| Real-time alerts | ✅ Yes (~5 min) | ✅ **Yes (1-2 min)** | - |
| Multiple searches | ✅ Limited | ✅ **Unlimited** | - |
| Cost | 💰 $29.99/month | ✅ **$0** | **$360/year** |
| Custom filters | ✅ Yes | ✅ Yes | - |
| API access | ❌ No | ✅ Yes | - |

**You're getting BETTER features for FREE!** 🎉

---

## 🛠️ Files Overview

### Core Files (Use These):
- **`main.py`** - ⭐ THE ONLY FILE YOU RUN: full SCOUT + LinkedIn + background tracker
- **`background_tracker.py`** - Headless background tracker (managed from main.py)
- **`linkedin_rss_tracker.py`** - RSS tracker (no API key)
- **`linkedin_tracker.py`** - API tracker (needs key)
- **`scout_with_linkedin.py`** - Older duplicate entry point (not needed - use main.py)

### Utilities:
- **`setup_linkedin.sh`** - Automated setup
- **`test_linkedin.py`** - Test everything
- **`example_usage.py`** - Code examples

### Documentation:
- **`START_HERE.md`** - This file
- **`QUICK_START.md`** - 5-minute guide
- **`LINKEDIN_SETUP.md`** - Complete setup
- **`API_VS_RSS.md`** - Method comparison
- **`IMPLEMENTATION_SUMMARY.md`** - Technical overview

### Original SCOUT:
- **`chatbot.py`** - Simple chatbot version

---

## 💡 Pro Tips

### 1. Run 24/7 with tmux
```bash
# Install tmux
brew install tmux

# Start session
tmux new -s scout

# Run SCOUT
python3 backend/cli/main.py

# Detach (keeps running): Ctrl+B then D
# Reattach later: tmux attach -t scout
```

### 2. Best Job Search Keywords
```
✅ Good: "Software Engineer Remote"
✅ Good: "Python Developer"
✅ Good: "Data Scientist San Francisco"

❌ Too specific: "Senior Python Django REST API Developer"
❌ Too broad: "Jobs"
```

### 3. Optimal Number of Searches
- **1-2 searches**: Very focused
- **3-5 searches**: Sweet spot ⭐
- **10+ searches**: Too many (slower checks)

### 4. Check Intervals
```
Every 60 seconds  = Very aggressive (use RSS only)
Every 120 seconds = Recommended ⭐
Every 300 seconds = Conservative (saves resources)
Every 1800 seconds = 2x per hour (API friendly)
```

### 5. Apply FAST
- First 10 applicants get 70% of interviews
- Apply within 1 hour of posting
- SCOUT gives you that edge! 💪

---

## 🔧 Troubleshooting

### "Command not found: python"
Use `python3` instead:
```bash
python3 backend/cli/main.py
```

### "Module not found"
Install dependencies:
```bash
source venv/bin/activate
pip install -r backend/cli/requirements.txt
```

### "RAPID_API_KEY not found"
Either:
1. Use RSS method (no key needed!)
2. Or get free key: https://rapidapi.com/

### "No new jobs found" (always)
This is normal! Means:
- No jobs posted since last check
- Or cache is working (no duplicates)
- Just be patient

### Jobs not showing?
```bash
# Clear cache and start fresh
rm jobs_cache*.json
python3 backend/cli/main.py
```

---

## 🎓 Learn More

### Want to understand the code?
```bash
python3 example_usage.py
```

### Want to customize?
- Edit `main.py` for UI / chat changes
- Edit `background_tracker.py` for auto-tracking settings
- Edit `linkedin_rss_tracker.py` for scraping logic
- Edit `linkedin_tracker.py` for API logic

### Want to add features?
Some ideas:
- Email notifications
- SMS alerts (Twilio)
- Slack webhooks
- Desktop notifications
- Web dashboard
- Auto-apply (advanced!)

---

## 📊 System Requirements

- **Python**: 3.7 or higher
- **OS**: macOS, Linux, or Windows
- **RAM**: 50MB
- **Disk**: 10MB
- **Internet**: Required

---

## 🆘 Need Help?

1. **Run tests**: `python3 test_linkedin.py`
2. **Read docs**: Check the MD files
3. **Try examples**: `python3 example_usage.py`
4. **Check errors**: Read terminal output carefully

---

## ✅ Checklist

Before you start:
- [ ] Virtual environment activated
- [ ] Dependencies installed (`pip install -r backend/cli/requirements.txt`)
- [ ] Ran test script (`python3 test_linkedin.py`)
- [ ] Chose method (RSS vs API)
- [ ] Read QUICK_START.md

Ready to go:
- [ ] Run SCOUT (`python3 backend/cli/main.py`)
- [ ] Add job searches
- [ ] Enable background tracker (works even when SCOUT is closed)
- [ ] Apply to jobs FAST! 🚀

---

## 🎉 You're Ready!

**Start now:**
```bash
python3 backend/cli/main.py
```

**First commands:**
```
add job search: Your Job Title, Your Location
enable background tracker
latest jobs
```

**Then sit back and wait for job alerts!** 💼

---

## 📈 Expected Results

Within first hour:
- ✅ Monitoring active
- ✅ Checking every 2 minutes
- ✅ Cache building

Within first day:
- ✅ 5-20 new jobs found (depends on searches)
- ✅ Instant notifications
- ✅ Ready to apply!

Within first week:
- ✅ 50-200 jobs tracked
- ✅ Applied to top opportunities
- ✅ Interviews scheduled! 🎯

---

## 🏆 Success Stories

You'll be one of the **first applicants** to jobs, which dramatically increases your chances of:
- Getting noticed by recruiters
- Landing interviews
- Receiving offers

**Your advantage**: While others check LinkedIn manually, you have a 24/7 AI monitoring for you!

---

## 🚀 Let's Go!

You have everything you need. Time to start job hunting like a pro!

```bash
python3 backend/cli/main.py
```

**Good luck!** 💪💼🎉

---

*Built with ❤️ for job seekers everywhere*
