# 🚀 Quick Start Guide - LinkedIn Job Tracking

## Get Started in 5 Minutes!

### Step 1: Run the Setup Script

```bash
chmod +x setup_linkedin.sh
./setup_linkedin.sh
```

This will:
- ✅ Create virtual environment
- ✅ Install all dependencies
- ✅ Create .env file

### Step 2: Get Your FREE API Key

1. **Go to RapidAPI**: https://rapidapi.com/
2. **Sign up** (100% free, no credit card needed)
3. **Find LinkedIn Data API**: 
   - Search for "LinkedIn Data API" or visit:
   - https://rapidapi.com/rockapis-rockapis-default/api/linkedin-data-api
4. **Subscribe to FREE Plan**:
   - Click "Subscribe to Test"
   - Choose "Basic" (FREE - 50 requests/month)
   - Copy your API key from the "X-RapidAPI-Key" header

### Step 3: Configure Your API Key

**Option A: Environment Variable (Quick)**
```bash
export RAPID_API_KEY='your_key_here'
```

**Option B: .env File (Permanent)**
```bash
# Edit .env file
nano .env

# Add this line:
RAPID_API_KEY=your_actual_key_here

# Save and exit (Ctrl+X, then Y, then Enter)

# Load it
set -a; source .env; set +a
```

### Step 4: Start CADDY with LinkedIn

**`main.py` is the only file you need to run.**

```bash
python main.py
```

> 💡 No API key required — CADDY uses the free LinkedIn public search automatically.

### Step 5: Add Your First Job Search

Once CADDY starts, type:
```
add job search: Python Developer, Remote, Full-time
```

### Step 6: Start Monitoring (and keep it running even when you close CADDY)

```
enable background tracker
```

This installs an automatic cron job that checks LinkedIn every 30 minutes **even while you're not running the bot**. When you come back, type `latest jobs` to see everything collected.

**That's it!** 🎉 You'll get alerts whenever new jobs are posted — even while CADDY is closed!

---

## Common Job Search Examples

```bash
# Remote positions
add job search: Software Engineer, Remote, Full-time
add job search: Data Analyst, Remote

# Specific locations
add job search: DevOps Engineer, San Francisco
add job search: Product Manager, New York, Full-time

# Entry-level positions
add job search: Junior Developer, United States
add job search: Software Engineer Intern, Remote, Internship

# Specific technologies
add job search: React Developer, Remote
add job search: Machine Learning Engineer, San Francisco
add job search: AWS Solutions Architect, United States

# Multiple keywords
add job search: Python Django Developer, Remote
add job search: Full Stack JavaScript, San Francisco
```

---

## Tips for Best Results

### 1. Start Broad, Then Narrow
```
✅ Good: "Software Engineer, Remote"
❌ Too specific: "Senior Python Django REST API Developer, Remote, Full-time"
```

### 2. Use 3-5 Job Searches
- Don't add too many (wastes API calls)
- Don't add too few (might miss opportunities)
- Sweet spot: 3-5 well-chosen searches

### 3. Monitor Your API Usage
- FREE plan: 50 requests/month
- Each search = 1 request per check
- With 5 searches every 60 seconds:
  - 5 requests/minute
  - 300 requests/hour
  - **Will hit limit in 10 minutes!**

**Solution**: Increase check interval
```
# In the code, change to 5 minutes (300 seconds)
# This gives you: 5 searches × 12 checks/hour = 60 requests/hour
# Or about 2 hours of continuous monitoring per month
```

### 4. Run During Peak Posting Times
Most jobs are posted:
- Monday-Thursday
- 9 AM - 5 PM (company local time)
- Especially Tuesday-Wednesday mornings

### 5. Keep CADDY Running 24/7

**Using tmux (Recommended)**:
```bash
# Install tmux
brew install tmux  # macOS

# Start a session
tmux new -s caddy

# Run CADDY
python main.py

# Detach (CADDY keeps running)
# Press: Ctrl+B, then D

# Reattach later
tmux attach -t caddy
```

**Using screen**:
```bash
# Start a session
screen -S caddy

# Run CADDY
python main.py

# Detach (CADDY keeps running)
# Press: Ctrl+A, then D

# Reattach later
screen -r caddy
```

**Using nohup**:
```bash
# Run in background
nohup python main.py > caddy.log 2>&1 &

# Check the log
tail -f caddy.log

# Stop it
pkill -f main.py
```

---

## Troubleshooting

### "RAPID_API_KEY not found"
```bash
# Check if it's set
echo $RAPID_API_KEY

# If empty, set it:
export RAPID_API_KEY='your_key_here'

# Or load from .env:
set -a; source .env; set +a
```

### "No new jobs found" (always)
Possible reasons:
1. Search criteria too narrow - broaden your keywords
2. No jobs posted recently - normal, be patient
3. API key issue - check it's correct
4. Rate limit reached - check RapidAPI dashboard

### Check API Usage
Visit: https://rapidapi.com/developer/billing
- See remaining requests
- View usage history
- Upgrade if needed

### Jobs Not Appearing
```bash
# Clear the cache to start fresh
rm jobs_cache.json

# Restart CADDY
python main.py
```

---

## Advanced: Optimize for FREE Tier

To maximize your 50 free requests/month:

### Strategy 1: Smart Scheduling
Run CADDY only during peak hours:
```bash
# Monday-Friday, 9 AM - 5 PM
# 8 hours × 5 days = 40 hours/week

# Check every 10 minutes
# 6 checks/hour × 40 hours = 240 checks/week

# With 3 searches:
# 3 × 240 = 720 requests/week ❌ Too much!

# Check every 30 minutes instead:
# 2 checks/hour × 40 hours = 80 checks/week
# 3 × 80 = 240 requests/week ❌ Still too much!

# Check every 2 hours:
# 0.5 checks/hour × 40 hours = 20 checks/week
# 3 × 20 = 60 requests/week
# Monthly: ~240 requests/month ❌ Over limit!

# OPTIMAL: Check every 4 hours during business hours
# 0.25 checks/hour × 40 hours = 10 checks/week
# 3 × 10 = 30 requests/week
# Monthly: ~120 requests/month ❌ Still over!

# BEST FOR FREE: Check 2x per day (morning & afternoon)
# 2 checks/day × 20 workdays = 40 checks/month
# 1 search × 40 = 40 requests/month ✅ Under limit!
```

### Strategy 2: Use Cron Job
```bash
# Edit crontab
crontab -e

# Add this line to check twice daily (10 AM and 2 PM)
0 10,14 * * 1-5 cd /Users/likhithr/Caddy && /Users/likhithr/Caddy/venv/bin/python linkedin_tracker.py

# Save and exit
```

### Strategy 3: Upgrade to Paid Plan
If you need real-time alerts:
- **Pro Plan**: $10/month = 500 requests
- **Ultra Plan**: $30/month = 3000 requests

With 500 requests/month:
- 5 searches every 2 minutes
- ~3 hours continuous monitoring per month
- Or spread throughout the month strategically

---

## What's Next?

1. ✅ Set up your searches
2. ✅ Start monitoring
3. 💼 Apply to jobs immediately when alerted!
4. 🎯 Customize check intervals based on your needs
5. 📧 Add email/SMS notifications (see advanced guides)

**Good luck with your job search!** 🚀

---

## Need Help?

- **Full Setup Guide**: See `LINKEDIN_SETUP.md`
- **Code Examples**: Run `python example_usage.py`
- **Test Commands**: Try `list jobs`, `job stats`, etc.

---

**Pro Tip**: The real value of this tool is getting notified FAST. Even with limited API calls, being one of the first applicants significantly increases your chances!
