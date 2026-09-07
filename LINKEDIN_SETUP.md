# 🚀 SCOUT LinkedIn Job Tracker Setup Guide

## Overview
SCOUT now includes **real-time LinkedIn job tracking** that monitors job postings and alerts you within 1-2 minutes of new listings!

## ✨ Features

### Premium-Like Features (FREE!)
- ⚡ **Real-time monitoring** - Check for new jobs every 60 seconds
- 🎯 **Multiple search tracking** - Monitor unlimited job searches simultaneously
- 📍 **Location filtering** - Track jobs by location or remote opportunities
- 💼 **Job type filtering** - Full-time, contract, internship, etc.
- 🔔 **Instant alerts** - Get notified immediately when new jobs appear
- 📊 **Smart caching** - Never see duplicate jobs
- 🎨 **Beautiful terminal UI** - Cyberpunk-style job notifications

### How It Works
1. Add job searches with keywords and filters
2. Start monitoring in the background
3. SCOUT checks LinkedIn every 60 seconds
4. New jobs trigger instant terminal notifications
5. All jobs are cached to avoid duplicates

## 🔧 Setup Instructions

### Step 1: Install Dependencies

```bash
# Activate your virtual environment
source venv/bin/activate  # macOS/Linux
# OR
venv\Scripts\activate     # Windows

# Install new requirements
pip install -r requirements.txt
```

### Step 2: Get RapidAPI LinkedIn Access (Recommended)

For the best experience and access to LinkedIn's official data:

1. **Sign up for RapidAPI** (FREE tier available)
   - Go to: https://rapidapi.com/
   - Create a free account

2. **Subscribe to LinkedIn Data API**
   - Visit: https://rapidapi.com/rockapis-rockapis-default/api/linkedin-data-api
   - Click "Subscribe to Test"
   - Choose the FREE plan (includes 50 requests/month)
   - Copy your RapidAPI key

3. **Set your API key**
   ```bash
   export RAPID_API_KEY='your_rapidapi_key_here'
   ```

4. **Make it permanent** (Optional)
   ```bash
   # Add to your ~/.zshrc or ~/.bashrc
   echo 'export RAPID_API_KEY="your_rapidapi_key_here"' >> ~/.zshrc
   source ~/.zshrc
   ```

### Step 3: Set up .env file

```bash
# Copy the example
cp .env.example .env

# Edit .env and add your keys
nano .env
```

Add these lines to `.env`:
```bash
RAPID_API_KEY=your_rapidapi_key_here
HF_API_KEY=your_huggingface_key_here  # Optional, for better AI chat
```

## 🎮 Usage Guide

### Starting SCOUT with LinkedIn Tracking

```bash
python scout_with_linkedin.py
```

### Basic Commands

#### 1. Add Job Searches
```
add job search: Python Developer, Remote, Full-time
add job search: Machine Learning Engineer, San Francisco
add job search: Data Scientist, United States, Contract
add job search: Software Engineer, New York
```

Format: `add job search: <keywords>, <location>, <job_type>`
- **keywords**: Required (e.g., "Python Developer", "Data Scientist")
- **location**: Optional (e.g., "Remote", "San Francisco", leave empty for any)
- **job_type**: Optional (e.g., "Full-time", "Contract", "Internship")

#### 2. View Your Searches
```
list jobs
show searches
my searches
```

#### 3. Start Real-Time Monitoring
```
start monitoring
start tracking
```

SCOUT will now check for new jobs every 60 seconds and alert you instantly!

#### 4. Stop Monitoring
```
stop monitoring
stop tracking
```

#### 5. View Statistics
```
job stats
tracker stats
```

#### 6. Clear Cache (Start Fresh)
```
clear job cache
```

## 📱 Example Session

```bash
$ python scout_with_linkedin.py

    ██████╗ █████╗ ██████╗ ██████╗ ██╗   ██╗
   ██╔════╝██╔══██╗██╔══██╗██╔══██╗╚██╗ ██╔╝
   ██║     ███████║██║  ██║██║  ██║ ╚████╔╝ 
   ██║     ██╔══██║██║  ██║██║  ██║  ╚██╔╝  
   ╚██████╗██║  ██║██████╔╝██████╔╝   ██║   
    ╚═════╝╚═╝  ╚═╝╚═════╝ ╚═════╝    ╚═╝   
    
    [ CYBERPUNK AI + LINKEDIN JOB TRACKER ]
            🔥 Real-time Job Alerts 🔥

[SYSTEM] ✓ RapidAPI Key Detected - LinkedIn tracking enabled!

┌─[YOU]
└──> add job search: Python Developer, Remote, Full-time

┌─[SCOUT]
└──> ✅ Added job search: 'Python Developer' in 'Remote'
     Start monitoring with: 'start monitoring'

┌─[YOU]
└──> start monitoring

┌─[SCOUT]
└──> LinkedIn job monitoring started! Checking every 60 seconds.

[2026-08-06 14:30:00] Check #1 - Scanning for new jobs...

🎉 FOUND 3 NEW JOB(S)!

🚀 NEW JOB ALERT!
════════════════════════════════════════════════════════════
📋 Title: Senior Python Developer
🏢 Company: Tech Corp
📍 Location: Remote
💼 Type: Full-time
📝 Description: Join our team building scalable Python applications...
🔗 Link: https://linkedin.com/jobs/view/12345
⏰ Found: 2026-08-06 14:30:15
════════════════════════════════════════════════════════════

[continues monitoring in background...]
```

## ⚙️ Configuration Options

### Adjust Check Interval

In `scout_with_linkedin.py`, modify:
```python
# Check every 60 seconds (1 minute)
self.start_job_monitoring(interval=60)

# Check every 120 seconds (2 minutes) - saves API calls
self.start_job_monitoring(interval=120)

# Check every 30 seconds (more aggressive)
self.start_job_monitoring(interval=30)
```

### Add Custom Notifications

You can add custom notification callbacks in `linkedin_tracker.py`:

```python
def my_notification(job):
    """Send email, Slack message, SMS, etc."""
    print(f"New job: {job['title']} at {job['company']}")
    # Add your notification code here

tracker.notification_callback = my_notification
```

## 💡 Tips & Best Practices

### 1. API Rate Limits
- Free RapidAPI tier: 50 requests/month
- Each search query = 1 request
- With 3 searches checked every 60 seconds:
  - 3 requests/minute
  - 180 requests/hour
  - **Rate limit reached in ~16 minutes**

**Solution**: Increase check interval
```python
# Check every 5 minutes instead (more sustainable)
self.start_job_monitoring(interval=300)
```

### 2. Optimize Your Searches
- Be specific with keywords to reduce noise
- Use location filters to focus on relevant jobs
- Combine similar searches to save API calls

### 3. Run in Background
Keep SCOUT running 24/7:

```bash
# Using tmux (recommended)
tmux new -s scout
python scout_with_linkedin.py
# Press Ctrl+B then D to detach

# Using nohup
nohup python scout_with_linkedin.py > scout.log 2>&1 &

# Using screen
screen -S scout
python scout_with_linkedin.py
# Press Ctrl+A then D to detach
```

### 4. Multiple Keywords Per Search
Instead of:
```
add job search: Python Developer, Remote
add job search: Python Engineer, Remote
```

Use one search:
```
add job search: Python Developer Engineer, Remote
```

## 🐛 Troubleshooting

### Issue: "RapidAPI key not found"
**Solution**: 
```bash
export RAPID_API_KEY='your_key_here'
# Or add to .env file
```

### Issue: "No new jobs found" repeatedly
**Possible causes**:
1. No new jobs in your search criteria
2. API rate limit reached
3. Network connection issues

**Solution**: 
- Check your searches are broad enough
- Verify API key is valid
- Check internet connection
- Review RapidAPI dashboard for quota

### Issue: Duplicate job notifications
**Solution**: Delete cache file
```bash
rm jobs_cache.json
```

### Issue: Too many API calls
**Solution**: Increase check interval
```python
# In scout_with_linkedin.py
self.start_job_monitoring(interval=300)  # 5 minutes
```

## 🚀 Advanced Usage

### Standalone Job Tracker

You can use the tracker independently:

```bash
python linkedin_tracker.py
```

Or import it in your own scripts:

```python
from linkedin_tracker import LinkedInJobTracker

tracker = LinkedInJobTracker()
tracker.add_search_query("Data Scientist", "Remote")
tracker.start_monitoring(interval=60)
```

### Export Job Data

Jobs are cached in `jobs_cache.json`:

```python
import json

with open('jobs_cache.json', 'r') as f:
    data = json.load(f)
    print(f"Total jobs tracked: {len(data['seen_jobs'])}")
```

## 📊 Monitoring Performance

The tracker maintains statistics:
- Total jobs seen
- Active searches
- Check interval
- Last update timestamp

View anytime with: `job stats`

## 🎯 Next Steps

1. Set up your API keys
2. Add 2-3 relevant job searches
3. Start monitoring
4. Let it run in the background
5. Get instant alerts for new opportunities!

## 🤝 Support

If you encounter issues:
1. Check your API keys are correct
2. Verify internet connection
3. Review RapidAPI quota
4. Check the logs/output for error messages

---

**Happy Job Hunting! 🎉**

Made with 💚 by SCOUT - Your Cyberpunk Career Assistant
