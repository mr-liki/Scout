# SCOUT - Cyberpunk AI Terminal Assistant

A **hacker-style terminal chatbot** with neon effects, ASCII art, and a cyberpunk interface! 🌆⚡

## ✨ NEW: LinkedIn Job Tracker 🚀

**Track LinkedIn jobs in REAL-TIME like LinkedIn Premium!**
- ⚡ **1-2 minute updates** - Get instant alerts for new job postings
- 🎯 **Multiple searches** - Monitor unlimited job searches simultaneously  
- 📍 **Smart filtering** - By location, job type, and keywords
- 🔔 **Live notifications** - Terminal alerts when new jobs appear
- 💼 **Zero duplicates** - Smart caching prevents repeat notifications
- 🆓 **100% FREE** - Get premium features without the premium price!

## ✨ Core Features

- 🎨 **Neon Blue ASCII Logo** - Pixel-style "SCOUT" title
- 💚 **Matrix-Style Background** - Animated green hacking screen theme
- ⚡ **Cyberpunk Interface** - Glitch effects and neon colors
- 🤖 **AI Chatbot** - Powered by Hugging Face API
- 🎭 **Typing Effects** - Smooth animations and transitions
- 🔒 **Hacker Aesthetic** - Terminal-style prompts and messages
- 🔥 **LinkedIn Integration** - Real-time job tracking and alerts
- 🌍 **Multi-Platform** - Searches LinkedIn + Indeed + Glassdoor + Wellfound together

## 🚀 Quick Start

### Standard SCOUT (Chat Only)

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install requirements
pip install -r backend/cli/requirements.txt

# Run SCOUT
python backend/cli/main.py
```

### SCOUT with LinkedIn Job Tracking (Recommended — one file only)

**`main.py` is the only file you ever need to run.** Everything (chat, job search, background tracking) is controlled from inside it.

```bash
# 1. Install dependencies
source venv/bin/activate
pip install -r backend/cli/requirements.txt

# 2. Run SCOUT — that's it!
python backend/cli/main.py
```

> 💡 No API keys required. SCOUT uses the free LinkedIn public search out of the box. Optional: set `HF_API_KEY` for smarter AI chat, or add a free [RapidAPI key](https://rapidapi.com/rockapis-rockapis-default/api/linkedin-data-api) for more robust results.

### 3. (Optional) Set API Key for Better AI Chat

```bash
# Get free token from: https://huggingface.co/settings/tokens
export HF_API_KEY='your_token_here'
```

## 🆕 NEW: Four Job Platforms (LinkedIn + Indeed + Glassdoor + Wellfound)

SCOUT now searches **LinkedIn, Indeed, Glassdoor AND Wellfound** together — quadruple the coverage, no extra setup:

```
> Python Developer                    # returns jobs from all four platforms
> AI Engineer early applicants        # early-applicant filter (LinkedIn signal)
> latest jobs                         # shows jobs from all, tagged [Indeed]/[Glassdoor]/[Wellfound]
```

- 🔍 Every search hits all four platforms and merges results (tagged `[LinkedIn]` / `[Indeed]` / `[Glassdoor]` / `[Wellfound]`)
- 💰 **Glassdoor + Wellfound results include salary estimates** (e.g. "$93K - $140K", "₹8L - ₹10L") and Glassdoor "Easy Apply" flags — bonuses LinkedIn and Indeed don't give you free
- 🚀 **Wellfound = startup jobs** — early-stage companies (with salary + equity) that rarely post on the big boards. Best coverage for startups in the US, India, and remote
- 🕐 The background tracker collects from all four too — `enable background tracker` covers LinkedIn + Indeed + Glassdoor + Wellfound
- 🌍 **Country-aware**: Indian locations route Glassdoor to `glassdoor.co.in` (₹ salaries), and Wellfound returns startup jobs worldwide including India
- 🆓 No API key needed for any platform

> ⚠️ Notes: (1) Indeed is scoped to the US job index — non-US locations return fewer/zero Indeed results. (2) Glassdoor is fetched through the free r.jina.ai reader proxy (bot-wall bypass), which has rate limits — SCOUT caches each search for 15 min, so normal use is well within the free tier. (3) Wellfound is behind Cloudflare, which is flaky — SCOUT retries with backoff and caches results, so it degrades gracefully (0 Wellfound) if blocked rather than failing.

## ✨ NEW: Premium AI Features (Free)

LinkedIn Premium adds AI tools for job hunting. SCOUT has them **free** — they work even without any AI API key (smart offline engine), and get smarter if you add a free `HF_API_KEY`:

```
> ai help                          # see all AI commands
> discover jobs: I'm a Python dev with 3 years exp looking for remote work
> headline: AI Engineer, 5 years, PyTorch AWS
> write my about: Data Scientist, 2 years, ML
> write my experience: led team that cut load time 40%
> connection message: Sarah, Google, liked your CUDA talk
```

- 🎯 **AI job discovery** — type a plain-language career goal, SCOUT parses it and returns ranked matching jobs (low-competition first)
- ✍️ **Headline / About / Experience** — professional drafts ready to paste
- 💌 **Connection / InMail messages** — personalized, non-robotic drafts

> Set a free [Hugging Face token](https://huggingface.co/settings/tokens) (`export HF_API_KEY=...`) to use a real AI model (Mistral-7B) for these. Without it, SCOUT uses a built-in expert template engine — both work offline.

## 🔥 NEW: Early-Applicant Filter (Free "Under 10 Applicants")

LinkedIn Premium charges $29.99/month to show jobs with few applicants. SCOUT gets you the same signal **for free** — LinkedIn marks low-competition jobs with a **"Be an early applicant"** badge, and SCOUT filters to exactly those:

```
> Python Developer early applicants
> AI Engineer under 10 applicants
> Data Scientist early applicants in Bengaluru
```

SCOUT will return only jobs where few people have applied — apply fast, beat the crowd! 🚀

> ⚠️ Honest note: LinkedIn only exposes the *badge* ("Be an early applicant") free — the exact applicant count and your ranking are Premium-only. The badge reliably indicates very low applicant counts (typically < 10), which is the signal that matters for getting noticed.

## 🕐 NEW: Track Jobs Even When SCOUT Is Closed

Don't want to keep the terminal open? Enable SCOUT's **background tracker** from inside the bot — no other file needed:

```
> enable background tracker      # installs a cron job (checks every 30 min)
> background status              # see if it's active, jobs stored, recent runs
> disable background tracker     # turn it off anytime
> latest jobs                    # view everything collected while you were away
```

Once enabled, SCOUT keeps checking LinkedIn **even when you close the terminal** and saves new jobs to `jobs_results.json` — so next time you open the bot, nothing is lost.

**Under the hood (optional, if you prefer the shell):**
- Install/uninstall manually: `./setup_background_tracker.sh` / `./setup_background_tracker.sh remove`
- Manual one-off check: `python background_tracker.py --once --notify`
- Run a custom interval: `python background_tracker.py --interval 3600`
- See logs: `tail -f background_tracker.log`

> ⚡ **Cloud option (24/7, even when your laptop is off):** push this repo to
> GitHub and enable `.github/workflows/job-tracker.yml` — it runs the same
> tracker in GitHub Actions on a schedule and commits new jobs to
> `jobs_results.json` automatically.

## 🎮 LinkedIn Job Tracking Usage

Once SCOUT with LinkedIn is running:

### Add Job Searches
```
add job search: Python Developer, Remote, Full-time
add job search: Data Scientist, San Francisco
add job search: Machine Learning Engineer, United States
```

### Start Monitoring
```
start monitoring
```

SCOUT will now check LinkedIn every 60 seconds and alert you instantly when new jobs appear! 🎉

### Other Commands
- `list jobs` - Show all tracked searches
- `stop monitoring` - Pause job tracking  
- `job stats` - View tracking statistics
- `clear job cache` - Reset job history

## 📱 Example: Real-Time Job Alert

```bash
[2026-08-06 14:30:00] Check #5 - Scanning for new jobs...

🎉 FOUND 1 NEW JOB!

🚀 NEW JOB ALERT!
════════════════════════════════════════════════════════════
📋 Title: Senior Python Developer
🏢 Company: Tech Innovations Inc.
📍 Location: Remote
💼 Type: Full-time
📝 Description: Join our team building scalable Python applications...
🔗 Link: https://linkedin.com/jobs/view/12345
⏰ Found: 2026-08-06 14:30:15
════════════════════════════════════════════════════════════
```

## 🎮 Usage

### Standard SCOUT
Once SCOUT is running:

- **Chat**: Type your message and press ENTER
- **Clear History**: Type `clear` to reset the conversation
- **Exit**: Type `exit`, `quit`, or press Ctrl+C

### SCOUT with LinkedIn (main.py)
All standard commands PLUS:

- **Add Job Search**: `add job search: <keywords>, <location>, <type>`
- **List Searches**: `list jobs` or `show searches`
- **Start Tracking**: `start monitoring`
- **Stop Tracking**: `stop monitoring`
- **View Stats**: `job stats`
- **Clear Cache**: `clear job cache`
- **Latest Jobs**: `latest jobs` - show jobs collected in the background while SCOUT was closed
- **Early Applicants**: `Python Developer early applicants` - only low-competition jobs (free "under 10 applicants" filter)
- **Indeed + Glassdoor + Wellfound Too**: every search also covers Indeed, Glassdoor and Wellfound (results tagged `[Indeed]` / `[Glassdoor]` / `[Wellfound]`, with salary estimates from Glassdoor + Wellfound, and startup jobs from Wellfound)

> 💡 No RapidAPI key? No problem — SCOUT automatically falls back to the free LinkedIn search, so `list Python jobs in Remote` works out of the box.
> 💡 Premium AI features (headline, about, experience, InMail, job discovery) are built-in — see `ai help` inside SCOUT.

## 🎨 Visual Features

### Neon Blue SCOUT Logo
```
██████╗ █████╗ ██████╗ ██████╗ ██╗   ██╗
██╔════╝██╔══██╗██╔══██╗██╔══██╗╚██╗ ██╔╝
██║     ███████║██║  ██║██║  ██║ ╚████╔╝ 
██║     ██╔══██║██║  ██║██║  ██║  ╚██╔╝  
╚██████╗██║  ██║██████╔╝██████╔╝   ██║   
 ╚═════╝╚═╝  ╚═╝╚═════╝ ╚═════╝    ╚═╝   
```

### Matrix Background
- Animated green characters (binary + Japanese katakana)
- Scrolling hacker-style effects
- Dynamic terminal experience

### Color Scheme
- **Neon Blue (Cyan)**: SCOUT logo and borders
- **Neon Green**: Matrix background and user prompt
- **Magenta**: Highlights and accents
- **Yellow**: System messages
- **White**: Chat text

## 📦 Dependencies

- `requests` - API communication
- `colorama` - Terminal colors (cross-platform)
- `beautifulsoup4` - HTML parsing for web scraping
- `lxml` - Fast XML/HTML processing
- `pyfiglet` - ASCII art (optional, reserved for extensions)

## 🎯 Example Session

```
[Matrix background scrolling...]

    ██████╗ █████╗ ██████╗ ██████╗ ██╗   ██╗
   ██╔════╝██╔══██╗██╔══██╗██╔══██╗╚██╗ ██╔╝
   ...

[SYSTEM] INITIALIZING NEURAL INTERFACE...
[SYSTEM] SCOUT ONLINE - READY FOR INTERACTION

┌─[YOU]
└──> Hello SCOUT

┌─[SCOUT]
└──> Hello! I'm SCOUT, your cyberpunk AI assistant. How can I help you today?

┌─[YOU]
└──> exit

[SYSTEM] DISCONNECTING...
╔═══════════════════════════════════════╗
║  CONNECTION TERMINATED - GOODBYE     ║
╚═══════════════════════════════════════╝
```

## 🔧 Customization

### Change Colors

Edit `main.py` and modify the color constants:

```python
# Logo color
Fore.CYAN  # Change to Fore.GREEN, Fore.MAGENTA, etc.

# Background effect
Fore.GREEN  # The matrix rain color
```

### Adjust Animation Speed

```python
# In print_typing_effect()
time.sleep(0.03)  # Lower = faster, Higher = slower
```

### Use Different AI Model

```python
# In ScoutChatbot.__init__()
self.api_url = "https://api-inference.huggingface.co/models/facebook/blenderbot-400M-distill"
```

## 🐛 Troubleshooting

### Colors Not Showing

Colorama should work on all platforms, but if issues occur:
```bash
pip install --upgrade colorama
```

### Connection Errors

1. Check your internet connection
2. Wait 10-20 seconds for model to load (first time)
3. Get an API token for better reliability

### Slow Responses

- The first response takes 10-20 seconds (model loading)
- Subsequent responses are faster
- Consider using an API token for priority access

## 🌟 Why SCOUT?

- **No Local AI** - Everything runs in the cloud
- **Free Forever** - Hugging Face offers generous free tier
- **Cool Interface** - Stand out from boring chatbots
- **Easy Setup** - Just 3 commands to get started
- **Hackable** - Customize colors, effects, and models

## 📝 License

MIT License - Hack away!

## 🎯 Coming Soon

- [x] LinkedIn job tracking with real-time alerts
- [x] Multiple job search monitoring
- [ ] Email/SMS notifications for new jobs
- [ ] More visual effects
- [ ] Custom themes
- [ ] Voice output
- [ ] Command history
- [ ] Multi-language support
- [ ] Slack/Discord integration for job alerts

---

**Built with 💚 for terminal lovers and cyberpunk enthusiasts**
