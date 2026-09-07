#!/usr/bin/env python3
"""
SCOUT - Cyberpunk AI Terminal Assistant
A hacker-style chatbot with neon effects + LinkedIn Job Tracking
"""

import requests
import os
import sys
import time
import random
import re
import threading
from colorama import Fore, Back, Style, init
from linkedin_tracker import LinkedInJobTracker
import jobs_store
from linkedin_ai import LinkedInAI
from indeed_tracker import IndeedJobTracker
from glassdoor_tracker import GlassdoorJobTracker
from wellfound_tracker import WellfoundJobTracker
from background_tracker import (
    is_tracker_installed,
    install_cron_tracker,
    remove_cron_tracker,
    get_installed_interval,
    get_log_tail,
    check_once,
)

# Initialize colorama
init(autoreset=True)

# Phrases that mean "show me low-competition jobs" (single source of truth)
EARLY_PHRASES = [
    "early applicants", "early applicant", "few applicants",
    "under 10 applicants", "fewer than 10", "less than 10",
    "low competition", "low applicants", "first applicants",
]

class ScoutChatbot:
    def __init__(self, api_key=None):
        """Initialize SCOUT chatbot with LinkedIn tracking"""
        self.api_key = api_key or os.environ.get("HF_API_KEY")
        self.api_url = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-medium"
        self.conversation_history = []
        self.offline_mode = False
        self.user_name = "User"
        
        # Initialize LinkedIn Job Tracker
        self.job_tracker = LinkedInJobTracker()
        self.monitoring_active = False
        self.monitoring_thread = None
        
        # Premium-style AI features (headline/about/experience/InMail/job discovery)
        self.linkedin_ai = LinkedInAI(api_key=self.api_key)
        
        # Indeed + Glassdoor + Wellfound trackers (free, no API keys needed)
        self.indeed_tracker = IndeedJobTracker()
        self.glassdoor_tracker = GlassdoorJobTracker()
        self.wellfound_tracker = WellfoundJobTracker()
        
    def start_job_monitoring(self, interval=60):
        """Start LinkedIn job monitoring in background"""
        if self.monitoring_active:
            return "Job monitoring is already running!"
        
        if not self.job_tracker.search_queries:
            return "Please add job searches first!"
        
        self.monitoring_active = True
        
        def monitor_loop():
            while self.monitoring_active:
                try:
                    new_jobs = self.job_tracker.check_for_new_jobs()
                    if new_jobs:
                        self.job_tracker.notify_new_jobs(new_jobs)
                    time.sleep(interval)
                except Exception as e:
                    print(Fore.RED + f"[MONITORING ERROR] {e}")
        
        self.monitoring_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitoring_thread.start()
        
        return f"✅ LinkedIn job monitoring started! Checking every {interval} seconds."
    
    def stop_job_monitoring(self):
        """Stop LinkedIn job monitoring"""
        if not self.monitoring_active:
            return "Job monitoring is not running."
        
        self.monitoring_active = False
        return "✅ Job monitoring stopped."
    
    def extract_job_search_params(self, user_message):
        """Extract job keywords and location from natural language"""
        msg = user_message.lower()
        
        # Common multi-word locations
        known_locations = [
            'san francisco', 'new york', 'los angeles', 'bengaluru', 'bangalore',
            'united states', 'united kingdom', 'hong kong', 'new delhi'
        ]
        
        location = ""
        keywords_part = msg
        
        # Check for known locations
        for known_loc in known_locations:
            if known_loc in msg:
                location = ' '.join(word.capitalize() for word in known_loc.split())
                keywords_part = msg.replace(f"in {known_loc}", "").replace(f"at {known_loc}", "")
                keywords_part = keywords_part.replace(f"near {known_loc}", "").replace(f"from {known_loc}", "")
                break
        
        # Try single word location
        if not location:
            location_patterns = [r'\bin\s+(\w+)', r'\bat\s+(\w+)', r'\bnear\s+(\w+)']
            for pattern in location_patterns:
                match = re.search(pattern, msg)
                if match:
                    location = match.group(1).capitalize()
                    keywords_part = msg[:match.start()].strip()
                    break
        
        # Remove early-applicant phrases so they don't pollute the keywords
        # (e.g. "Python developer early applicants" -> "Python Developer")
        for phrase in EARLY_PHRASES:
            keywords_part = keywords_part.replace(phrase, "")
        
        # Extract job title
        remove_words = ["list", "show", "find", "search", "get", "me", "the", "current", "all", 
                       "jobs", "job", "positions", "position", "roles", "role", "openings", "opening",
                       "for", "a", "an", "looking", "want", "need", "some",
                       "with", "having", "has", "in", "at", "near", "of", "and", "or",
                       "early", "applicants", "applicant", "few", "under", "less", "competition"]
        
        words = keywords_part.split()
        job_words = [w for w in words if w not in remove_words]
        keywords = " ".join(job_words).strip()
        
        if keywords:
            keywords = " ".join(word.capitalize() for word in keywords.split())
        
        return keywords, location
    
    def _strip_cmd_words(self, user_message, words):
        """Remove command words and a trailing colon from a user message."""
        msg = user_message
        for w in words:
            msg = msg.replace(w, " ")
        msg = msg.replace(":", " ")
        return msg.strip()
    
    def _parse_profile_details(self, details):
        """Parse 'role, years, skills, location' style input for AI features."""
        details = details.strip()
        parts = [p.strip() for p in re.split(r"[,|;]| - ", details) if p.strip()]
        role = parts[0] if parts else "your role"
        years = parts[1] if len(parts) > 1 else ""
        skills = parts[2] if len(parts) > 2 else ""
        location = parts[3] if len(parts) > 3 else ""
        return role, years, skills, location
        
    def get_offline_response(self, user_message):
        """Generate response using local pattern matching - Enhanced with LinkedIn"""
        msg = user_message.lower().strip()
        
        # Explicit LinkedIn commands (must be checked BEFORE smart-search intent,
        # otherwise e.g. "list jobs" / "show collected jobs" get misparsed)
        if "list job" in msg or "show searches" in msg:
            return "LINKEDIN_LIST_SEARCHES"
        
        if "latest job" in msg or "recent job" in msg or "collected job" in msg or "saved job" in msg or "what jobs" in msg:
            return "LINKEDIN_LATEST_JOBS"
        
        if "add job search" in msg:
            return "Use: add job search: <keywords>, <location>, <type>"
        
        if "start monitoring" in msg or "start tracking" in msg:
            return "LINKEDIN_START_MONITORING"
        
        if "stop monitoring" in msg or "stop tracking" in msg:
            return "LINKEDIN_STOP_MONITORING"
        
        if "job stats" in msg:
            return "LINKEDIN_SHOW_STATS"
        
        if "clear job cache" in msg:
            return "LINKEDIN_CLEAR_CACHE"
        
        if "background status" in msg or "tracker status" in msg:
            return "LINKEDIN_BG_STATUS"
        
        if "enable background" in msg or "enable tracker" in msg or "start background" in msg:
            return "LINKEDIN_BG_ENABLE"
        
        if "disable background" in msg or "remove tracker" in msg or "stop background" in msg:
            return "LINKEDIN_BG_DISABLE"
        
        # --- Premium-style AI features ---
        # NOTE: use specific phrases, not bare startswith("about"/"experience"),
        # so casual chat like "about the tracker" isn't hijacked.
        if msg.startswith("headline") or "write my headline" in msg or "headline for" in msg or "ai headline" in msg:
            return "LINKEDIN_AI_HEADLINE"
        
        if "write my about" in msg or "improve my about" in msg or "about section" in msg or "ai about" in msg:
            return "LINKEDIN_AI_ABOUT"
        
        if "write my experience" in msg or "improve my experience" in msg or "experience section" in msg or "ai experience" in msg:
            return "LINKEDIN_AI_EXPERIENCE"
        
        if "connection message" in msg or "inmail" in msg or "inmail to" in msg or "connect with" in msg:
            return "LINKEDIN_AI_CONNECT"
        
        if "discover jobs" in msg or "find me a job" in msg or "recommend jobs" in msg or "career goal" in msg or "jobs for me" in msg:
            return "LINKEDIN_AI_DISCOVER"
        
        if "ai help" in msg or "ai features" in msg or "premium features" in msg:
            return "LINKEDIN_AI_HELP"
        
        # Detect natural-language job search intent (e.g. "list Python jobs in Remote")
        job_search_keywords = ["list", "show", "find", "search", "get", "track", "monitor"]
        job_indicators = ["job", "jobs", "position", "positions", "role", "roles", "opening", "openings"]
        
        has_search_intent = any(keyword in msg for keyword in job_search_keywords)
        has_job_indicator = any(indicator in msg for indicator in job_indicators)
        
        # Bare job titles (e.g. "Python developer", "Data Scientist", "AI Engineer in Bengaluru")
        role_words = [
            "developer", "engineer", "scientist", "analyst", "designer", "manager",
            "intern", "architect", "consultant", "specialist", "researcher", "tester",
            "recruiter", "accountant", "writer", "editor", "programmer", "devops",
            "administrator", "director", "lead", "qa", "product", "ux", "ui",
        ]
        tech_terms = ["python", "java", "javascript", "react", "node", "aws", "cloud",
                      "sql", "full stack", "backend", "frontend", "machine learning",
                      "kubernetes", "docker", "ai", "ml", "golang", "rust", "c++", "c#"]
        is_question = any(w in msg for w in ["what", "how", "why", "when", "where", "who", "?"])
        # "Tell/learn/teach me X" is chat, not a job search.
        # Word-boundary match so "learn" doesn't fire inside "machine learning".
        is_learning = any(re.search(r"\b" + re.escape(w) + r"\b", msg)
                          for w in ["tell", "learn", "teach", "explain", "please", "about"])
        # Casual first-person chatter isn't a job search
        starts_casual = any(msg.startswith(w) for w in ["i", "my", "we", "the", "this", "she", "he", "they", "you"])
        # Word-boundary matching so "ai" doesn't match inside "said" / "java" inside "javascript"
        def _word_hit(term):
            return re.search(r"\b" + re.escape(term) + r"\b", msg) is not None
        word_count = len(msg.split())
        has_role_word = any(_word_hit(role) for role in role_words) and word_count <= 5
        has_tech_term = any(_word_hit(tech) for tech in tech_terms) and word_count <= 4
        not_chat = not (is_question or is_learning or starts_casual)
        
        if (has_search_intent and has_job_indicator) or ((has_role_word or has_tech_term) and not_chat):
            # "early applicants" / "under 10 applicants" => premium-style low-competition filter
            if any(p in msg for p in EARLY_PHRASES):
                return "LINKEDIN_SMART_SEARCH_EARLY"
            return "LINKEDIN_SMART_SEARCH"
        
        # Greetings (word-boundary match so "yo" doesn't match inside "you")
        greetings = ["hello", "hi", "hey", "greetings", "sup", "yo", "howdy"]
        if any(re.search(r"\b" + re.escape(word) + r"\b", msg) for word in greetings):
            responses = [
                "Hey there! I'm SCOUT, your cyberpunk AI assistant. What can I help you with?",
                "Greetings, user. SCOUT systems online and ready to assist.",
                "Hello! Welcome to the neural network. How can I assist you today?",
                "Hey! SCOUT here. What do you need help with?"
            ]
            return random.choice(responses)
        
        # How are you
        if any(phrase in msg for phrase in ["how are you", "how're you", "how r u", "how are u"]):
            responses = [
                "I'm operating at optimal capacity! All systems green. How can I help you?",
                "Running smoothly in the digital realm. What brings you here today?",
                "All neural pathways functioning perfectly. Ready to assist!",
                "I'm doing great! My circuits are humming nicely. What about you?"
            ]
            return random.choice(responses)
        
        # What can you do
        if any(phrase in msg for phrase in ["what can you do", "what do you do", "your capabilities", "help me", "can you help"]):
            return """I'm SCOUT, your cyberpunk AI assistant! I can:
• Have conversations and answer questions
• Provide information on various topics
• Help with brainstorming and creative thinking
• Discuss technology, programming, and more
• Just chat and keep you company in the terminal!

What would you like to talk about?"""
        
        # Who are you
        if any(phrase in msg for phrase in ["who are you", "what are you", "tell me about yourself"]):
            return """I'm SCOUT - Cyberpunk AI Terminal Assistant. I'm an AI chatbot designed with a hacker aesthetic, running in your terminal with neon effects and matrix-style visuals. I'm here to chat, help, and provide information. Currently running in OFFLINE MODE using local pattern matching."""
        
        # Jokes
        if any(word in msg for word in ["joke", "funny", "laugh"]):
            jokes = [
                "Why do programmers prefer dark mode? Because light attracts bugs! 🐛",
                "I told my computer I needed a break. Now it won't stop sending me KitKat ads.",
                "Why do hackers prefer tea? Because it helps them avoid getting caught by Java! ☕",
                "There are 10 types of people: those who understand binary and those who don't.",
                "A SQL query walks into a bar, approaches two tables and asks: 'Mind if I JOIN you?'"
            ]
            return random.choice(jokes)
        
        # Thanks
        if any(word in msg for word in ["thank", "thanks", "thx", "appreciate"]):
            responses = [
                "You're welcome! Happy to help!",
                "No problem! That's what I'm here for.",
                "Anytime! Let me know if you need anything else.",
                "Glad I could help! 💚"
            ]
            return random.choice(responses)
        
        # Time/Date
        if any(word in msg for word in ["time", "date", "today", "now"]):
            current_time = time.strftime("%H:%M:%S")
            current_date = time.strftime("%Y-%m-%d")
            return f"Current system time: {current_time}\nDate: {current_date}"
        
        # Programming questions
        if any(word in msg for word in ["python", "code", "programming", "javascript", "java"]):
            return "I see you're interested in programming! I'd love to help, but I'm currently in OFFLINE MODE with limited capabilities. For detailed coding help, I'd need an internet connection to access my full knowledge base. Feel free to ask general questions though!"
        
        # Goodbye
        if any(word in msg for word in ["bye", "goodbye", "see you", "later"]):
            responses = [
                "Catch you later! Stay in the matrix! 💚",
                "Goodbye! Come back anytime you need me.",
                "See you soon! SCOUT signing off.",
                "Until next time! Keep the cyber vibes alive! ⚡"
            ]
            return random.choice(responses)
        
        # Default responses
        default_responses = [
            "That's interesting! Tell me more about that.",
            "I see. Can you elaborate on that?",
            "Interesting point. What else would you like to discuss?",
            "I'm currently in OFFLINE MODE, so my responses are limited. But I'm listening!",
            "Got it. What else is on your mind?",
            "Noted. Feel free to continue the conversation!",
            "I'm processing that... In offline mode, I can still chat, just with simpler responses.",
            "Hmm, I'd need my full neural network to give a better response. But let's keep talking!",
            "That's cool! What else would you like to know?",
            "I hear you! Running in local mode right now, but I'm here to chat."
        ]
        return random.choice(default_responses)
    
    def chat(self, user_message):
        """Send message and get response - Enhanced with LinkedIn"""
        msg = user_message.lower().strip()
        
        # Handle explicit LinkedIn commands
        if "add job search:" in msg:
            parts = msg.split("add job search:")[1].strip().split(",")
            keywords = parts[0].strip() if len(parts) > 0 else ""
            location = parts[1].strip() if len(parts) > 1 else ""
            job_type = parts[2].strip() if len(parts) > 2 else ""
            
            if keywords:
                self.job_tracker.add_search_query(keywords, location, job_type)
                return f"✅ Added job search: '{keywords}' in '{location or 'Any Location'}'\nType 'start monitoring' to begin real-time tracking!"
            else:
                return "Please provide at least job keywords!"
        
        # Get response (might be LinkedIn action or regular chat)
        response = self.get_offline_response(user_message)
        
        # Handle smart search (with optional early-applicant filter)
        if response in ("LINKEDIN_SMART_SEARCH", "LINKEDIN_SMART_SEARCH_EARLY"):
            early_only = response == "LINKEDIN_SMART_SEARCH_EARLY"
            keywords, location = self.extract_job_search_params(user_message)
            
            if keywords:
                self.job_tracker.add_search_query(keywords, location, "")
                
                mode_note = " [EARLY APPLICANTS ONLY 🔥]" if early_only else ""
                print(Fore.YELLOW + f"\n[SEARCHING] Looking for jobs on LinkedIn + Indeed + Glassdoor + Wellfound{mode_note}...\n")
                
                # Search LinkedIn (free method, early-applicant filter supported)
                jobs = self.job_tracker.search_jobs(keywords, location, early_only=early_only)
                li_count = len(jobs)
                for j in jobs:
                    j.setdefault("source", "LinkedIn")
                
                # Search Indeed + Glassdoor + Wellfound too (all free; no early-applicant signal)
                if not early_only:
                    jobs.extend(self.indeed_tracker.search_jobs(keywords, location, limit=10))
                    jobs.extend(self.glassdoor_tracker.search_jobs(keywords, location, limit=10))
                    jobs.extend(self.wellfound_tracker.search_jobs(keywords, location, limit=10))
                
                # Save what we found so it survives after SCOUT closes
                jobs_store.store_new_jobs(jobs)
                
                if jobs:
                    counts = {}
                    for j in jobs:
                        s = j.get('source', 'LinkedIn')
                        counts[s] = counts.get(s, 0) + 1
                    parts = [f"{counts.get('LinkedIn', 0)} LinkedIn"]
                    if not early_only:
                        parts.append(f"{counts.get('Indeed', 0)} Indeed")
                        parts.append(f"{counts.get('Glassdoor', 0)} Glassdoor")
                        parts.append(f"{counts.get('Wellfound', 0)} Wellfound")
                    result = f"🎯 Found {len(jobs)} jobs"
                    if location:
                        result += f" in {location}"
                    result += "!"
                    if early_only:
                        result += " 🔥 LOW COMPETITION (early applicants)"
                    result += "  (" + " + ".join(parts) + ")"
                    result += "\n\n"
                    # Round-robin interleave so EVERY platform appears in the view
                    # (LinkedIn is searched first, so a plain slice would hide the rest).
                    buckets = {}
                    for j in jobs:
                        buckets.setdefault(j.get('source', 'LinkedIn'), []).append(j)
                    display = []
                    while any(buckets.values()):
                        for src in list(buckets):
                            if buckets[src]:
                                display.append(buckets[src].pop(0))
                    
                    for i, job in enumerate(display[:6]):
                        src = job.get('source', 'LinkedIn')
                        badge = {"Indeed": " [Indeed]", "Glassdoor": " [Glassdoor]", "Wellfound": " [Wellfound]"}.get(src, " [LinkedIn]" if li_count else "")
                        result += f"\n{i+1}. 📋 {job.get('title', 'N/A')}{badge}\n"
                        result += f"   🏢 {job.get('company', 'N/A')}\n"
                        result += f"   📍 {job.get('location', 'N/A')}\n"
                        if job.get('early_applicant'):
                            result += "   🔥 Be an early applicant (few applicants!)\n"
                        if job.get('salary'):
                            result += f"   💰 {job['salary']}\n"
                        if job.get('easy_apply'):
                            result += "   ⚡ Easy Apply\n"
                        if job.get('link') or job.get('url'):
                            result += f"   🔗 {job.get('link') or job.get('url')}\n"
                    
                    if len(jobs) > 6:
                        result += f"\n... and {len(jobs) - 6} more jobs!"
                    
                    result += f"\n\n✅ Added '{keywords}' to your tracked searches!"
                    result += "\n💡 Type 'start monitoring' for real-time alerts, or 'latest jobs' to see everything collected (even while SCOUT was closed)."
                    
                    return result
                else:
                    hint = ""
                    if early_only:
                        hint = "\n\nNo early-applicant jobs found right now — try again later, or search without the 'early applicants' filter."
                    return f"🔍 Searched for '{keywords}' jobs" + (f" in {location}" if location else "") + " but didn't find any right now." + hint + "\n\n✅ Added to tracking. Type 'start monitoring' for alerts when new jobs appear!"
            else:
                return "Please tell me:\n1. What job? (e.g., 'AI Engineer')\n2. Where? (e.g., 'Bengaluru', 'Remote')\n\nExample: list AI Engineer jobs in Bengaluru"
        
        # Handle LinkedIn action commands
        if response == "LINKEDIN_LIST_SEARCHES":
            self.job_tracker.list_search_queries()
            return "Above are your active job searches."
        
        if response == "LINKEDIN_START_MONITORING":
            result = self.start_job_monitoring(interval=60)
            return result
        
        if response == "LINKEDIN_STOP_MONITORING":
            result = self.stop_job_monitoring()
            return result
        
        if response == "LINKEDIN_SHOW_STATS":
            self.job_tracker.get_statistics()
            return "Above are your tracking statistics."
        
        if response == "LINKEDIN_CLEAR_CACHE":
            self.job_tracker.clear_cache()
            return "Job cache cleared successfully!"
        
        if response == "LINKEDIN_BG_STATUS":
            if not is_tracker_installed():
                return ("🕐 Background tracker: NOT INSTALLED\n\n"
                        "Right now jobs only collect while SCOUT is open. To track automatically "
                        "even when you're not running me, type:\n"
                        "  'enable background tracker'\n\n"
                        "That installs a cron job that checks LinkedIn every 30 minutes and "
                        "saves results to jobs_results.json.")
            interval = get_installed_interval()
            summary = jobs_store.get_summary()
            lines = [
                f"🕐 Background tracker: ✅ ACTIVE (every {interval or '30'} min)",
                f"   Jobs stored: {summary['count']}",
            ]
            if summary['last_updated']:
                lines.append(f"   Last job stored: {summary['last_updated'][:16].replace('T', ' ')}")
            tail = get_log_tail(3)
            if tail:
                lines.append("   Recent runs:")
                lines.extend(f"      {l}" for l in tail)
            lines.append("\nCommands: 'disable background tracker' to stop, 'latest jobs' to view.")
            return "\n".join(lines)
        
        if response == "LINKEDIN_BG_ENABLE":
            if is_tracker_installed():
                interval = get_installed_interval()
                return f"✅ Background tracker is already active (every {interval or '30'} min). Type 'background status' for details."
            ok = install_cron_tracker(interval_min=30)
            if not ok:
                return ("⚠ Could not install the cron job automatically.\n\n"
                        "Run this manually instead:\n  ./setup_background_tracker.sh")
            # First check runs on a background thread so the chat stays responsive
            threading.Thread(target=check_once, kwargs={"notify": False}, daemon=True).start()
            return ("✅ Background tracker ENABLED!\n\n"
                    "I'll now check LinkedIn every 30 minutes — even while you're not running me.\n"
                    "A first check is running now in the background (see background_tracker.log).\n"
                    "• Type 'background status' to check on it\n"
                    "• Type 'latest jobs' to see what's been collected\n"
                    "• Type 'disable background tracker' to turn it off")
        
        if response == "LINKEDIN_BG_DISABLE":
            if not is_tracker_installed():
                return "Background tracker is not installed — nothing to disable."
            ok = remove_cron_tracker()
            if ok:
                return "🛑 Background tracker disabled. Jobs already collected stay in jobs_results.json (type 'latest jobs')."
            return "⚠ Could not remove the cron job. Run manually: ./setup_background_tracker.sh remove"
        
        # --- Premium-style AI feature handlers ---
        if response == "LINKEDIN_AI_HEADLINE":
            details = self._strip_cmd_words(user_message, ["write my headline", "headline for", "headline", "ai headline"])
            role, years, skills, loc = self._parse_profile_details(details)
            out = self.linkedin_ai.suggest_headline(role, years, skills, loc)
            return f"✨ AI LINKEDIN HEADLINES\n(For: {role})\n\n{out}\n\n💡 Tip: paste into your profile, keep it under 220 characters."
        
        if response == "LINKEDIN_AI_ABOUT":
            details = self._strip_cmd_words(user_message, ["write my about", "improve my about", "ai about", "about"])
            role, years, skills, _ = self._parse_profile_details(details)
            out = self.linkedin_ai.suggest_about(role, years, skills)
            return f"✨ AI ABOUT SECTION\n(For: {role})\n\n{out}\n\n💡 Tip: add a specific achievement or metric to make it stronger."
        
        if response == "LINKEDIN_AI_EXPERIENCE":
            details = self._strip_cmd_words(user_message, ["write my experience", "improve my experience", "ai experience", "experience"])
            role, _, _, _ = self._parse_profile_details(details)
            out = self.linkedin_ai.suggest_experience(role or "your role", details)
            return f"✨ AI EXPERIENCE BULLETS\n\n{out}\n\n💡 Tip: add numbers/impact to stand out."
        
        if response == "LINKEDIN_AI_CONNECT":
            details = self._strip_cmd_words(user_message, ["connection message", "inmail to", "inmail", "connect with", "write a message", "message"])

            # Expect: name, company, reason (comma or dash separated)
            parts = [p.strip() for p in re.split(r"[,|;]| - ", details) if p.strip()]
            name = parts[0] if len(parts) > 0 else "there"
            company = parts[1] if len(parts) > 1 else "your company"
            reason = parts[2] if len(parts) > 2 else "your work in this field"
            out = self.linkedin_ai.draft_connection_message(name, company, reason)
            return f"✨ AI CONNECTION MESSAGE\n\n{out}\n\n💡 Tip: personalize the reason before sending."
        
        if response == "LINKEDIN_AI_DISCOVER":
            goal = self._strip_cmd_words(user_message, ["discover jobs", "find me a job", "find me jobs", "recommend jobs", "career goal", "jobs for me", "discover"])

            print(Fore.YELLOW + "\n[AI DISCOVERY] Understanding your career goal...\n")
            return self.linkedin_ai.discover_jobs(goal)
        
        if response == "LINKEDIN_AI_HELP":
            return ("✨ PREMIUM-STYLE AI FEATURES (FREE!)\n\n"
                    "1. 🎯 Job discovery from plain language:\n"
                    "   'discover jobs for: I'm a Python dev with 3 years exp looking for remote work'\n"
                    "2. ✍️ Headline suggestions:\n"
                    "   'headline: Python Developer, 3 years, Django AWS'\n"
                    "3. 📄 About section drafts:\n"
                    "   'write my about: Data Scientist, 2 years, ML, built a fraud model'\n"
                    "4. 💼 Experience bullets:\n"
                    "   'write my experience: led a team that cut load time by 40%'\n"
                    "5. 💌 Connection / InMail drafts:\n"
                    "   'connection message: Sarah, Google, I liked your ML talk'")
        
        if response == "LINKEDIN_LATEST_JOBS":
            jobs = jobs_store.load_jobs()
            if not jobs:
                return "No jobs collected yet. Try:\n1. 'list Python Developer jobs in Remote' to search now\n2. Install the background tracker (./setup_background_tracker.sh) so jobs collect even while SCOUT is closed"
            summary = jobs_store.get_summary()
            result = f"💼 {len(jobs)} job(s) collected"
            if summary['last_updated']:
                result += f" (latest: {summary['last_updated'][:16].replace('T', ' ')})"
            result += ":\n"
            for i, job in enumerate(jobs[-10:], 1):
                src = {"Indeed": " [Indeed]", "Glassdoor": " [Glassdoor]", "Wellfound": " [Wellfound]"}.get(job.get('source'), "")
                result += f"\n{i}. 📋 {job.get('title', 'N/A')}{src}\n"
                result += f"   🏢 {job.get('company', 'N/A')}\n"
                result += f"   📍 {job.get('location', 'N/A')}\n"
                if job.get('salary'):
                    result += f"   💰 {job['salary']}\n"
                if job.get('easy_apply'):
                    result += "   ⚡ Easy Apply\n"
                if job.get('early_applicant'):
                    result += "   🔥 Be an early applicant (low competition!)\n"
                if job.get('link') or job.get('url'):
                    result += f"   🔗 {job.get('link') or job.get('url')}\n"
                if job.get('query'):
                    result += f"   🔍 Search: {job.get('query')}\n"
            result += f"\n💡 Showing the latest 10 of {len(jobs)}. Type 'find <job> jobs' to search live, or '<job> early applicants' for low-competition roles."
            return result
        
        # Try online AI chat if not a LinkedIn command
        if not self.offline_mode:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            conversation_text = ""
            for msg in self.conversation_history:
                conversation_text += f"{msg}\n"
            conversation_text += user_message
            
            payload = {
                "inputs": conversation_text,
                "parameters": {
                    "max_length": 1000,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "do_sample": True
                }
            }
            
            try:
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=10
                )
                
                if response.status_code == 503:
                    return "⏳ MODEL LOADING... TRY AGAIN IN 10 SECONDS..."
                
                response.raise_for_status()
                result = response.json()
                
                if isinstance(result, list) and len(result) > 0:
                    bot_response = result[0].get("generated_text", "").strip()
                    if bot_response.startswith(conversation_text):
                        bot_response = bot_response[len(conversation_text):].strip()
                else:
                    bot_response = self.get_offline_response(user_message)
                
                if not bot_response:
                    bot_response = self.get_offline_response(user_message)
                
                self.conversation_history.append(user_message)
                self.conversation_history.append(bot_response)
                
                if len(self.conversation_history) > 12:
                    self.conversation_history = self.conversation_history[-12:]
                
                return bot_response
                
            except requests.exceptions.RequestException:
                # Switch to offline mode
                if not self.offline_mode:
                    self.offline_mode = True
                    return ("⚠️  AI CHAT UNAVAILABLE - SWITCHED TO OFFLINE MODE\n\n"
                            "The AI chatbot needs an internet connection (or a free HF_API_KEY).\n"
                            "But LinkedIn job search needs no API key — just type a job title!\n\n"
                            "Try: 'Python Developer' or 'AI Engineer'\n"
                            "or a full search: 'list Data Scientist jobs in Bengaluru'")
            
            except (ValueError, KeyError, IndexError):
                # Malformed API response - fall through to offline response
                pass
        
        # Offline mode
        bot_response = self.get_offline_response(user_message)
        self.conversation_history.append(user_message)
        self.conversation_history.append(bot_response)
        
        if len(self.conversation_history) > 12:
            self.conversation_history = self.conversation_history[-12:]
        
        return bot_response
    
    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []

# ASCII Art and Visual Effects
def print_matrix_bg(lines=3):
    """Print matrix-style background effect"""
    chars = "01アイウエオカキクケコサシスセソタチツテト"
    for _ in range(lines):
        line = ''.join(random.choice(chars) for _ in range(80))
        print(Fore.GREEN + Style.DIM + line)

def print_scout_logo():
    """Print SCOUT logo in pixel/ASCII style"""
    # Clear screen
    os.system('clear' if os.name != 'nt' else 'cls')
    
    # Matrix background at top
    print_matrix_bg(2)
    print()
    
    # SCOUT ASCII art in neon blue
    logo = """
    ██████╗ █████╗ ██████╗ ██████╗ ██╗   ██╗
   ██╔════╝██╔══██╗██╔══██╗██╔══██╗╚██╗ ██╔╝
   ██║     ███████║██║  ██║██║  ██║ ╚████╔╝ 
   ██║     ██╔══██║██║  ██║██║  ██║  ╚██╔╝  
   ╚██████╗██║  ██║██████╔╝██████╔╝   ██║   
    ╚═════╝╚═╝  ╚═╝╚═════╝ ╚═════╝    ╚═╝   
    """
    
    # Print logo in cyan (neon blue)
    for line in logo.split('\n'):
        print(Fore.CYAN + Style.BRIGHT + line)
    
    # Subtitle
    print(Fore.MAGENTA + Style.BRIGHT + "    [ CYBERPUNK AI + LINKEDIN JOB TRACKER ]")
    print(Fore.GREEN + Style.BRIGHT + "            🔥 Real-time Job Alerts 🔥")
    print()
    
    # Matrix background at bottom
    print_matrix_bg(2)
    print()

def print_glitch_effect(text, color=Fore.CYAN):
    """Print text with glitch effect"""
    glitch_chars = "!@#$%^&*"
    for char in text:
        sys.stdout.write(color + Style.BRIGHT + char)
        sys.stdout.flush()
        time.sleep(0.02)
    print()

def print_typing_effect(text, color=Fore.GREEN, speed=0.03):
    """Print text with typing effect"""
    for char in text:
        sys.stdout.write(color + char)
        sys.stdout.flush()
        time.sleep(speed)
    print()

def print_border():
    """Print decorative border"""
    border = "═" * 60
    print(Fore.CYAN + Style.BRIGHT + border)

def print_system_message(message):
    """Print system message in hacker style"""
    print(Fore.YELLOW + Style.BRIGHT + f"[SYSTEM] {message}")

def print_scout_response(message):
    """Print SCOUT's response with style"""
    print()
    print(Fore.CYAN + Style.BRIGHT + "┌─[" + Fore.MAGENTA + "SCOUT" + Fore.CYAN + "]")
    print(Fore.CYAN + "└──> " + Fore.WHITE + Style.BRIGHT + message)
    print()

def animate_startup():
    """Startup animation sequence"""
    print_scout_logo()
    
    # Initialization sequence
    init_messages = [
        "INITIALIZING NEURAL INTERFACE...",
        "LOADING AI CORE MODULES...",
        "CONNECTING TO LINKEDIN API...",
        "SCOUT ONLINE - READY FOR JOB TRACKING!"
    ]
    
    for msg in init_messages:
        print(Fore.GREEN + Style.BRIGHT + "[▓▓▓▓▓▓▓▓▓▓] " + msg)
        time.sleep(0.4)
    
    print()
    print_border()
    print(Fore.CYAN + Style.BRIGHT + "  COMMANDS:")
    print(Fore.WHITE + "    • Chat normally or ask about jobs")
    print(Fore.YELLOW + "    • 'Python Developer' - Just type a job title, I'll search!")
    print(Fore.YELLOW + "    • 'add job search: <keywords>, <location>' - Add precise search")
    print(Fore.YELLOW + "    • 'start monitoring' - Begin job tracking")
    print(Fore.YELLOW + "    • 'latest jobs' - Show jobs collected in background")
    print(Fore.YELLOW + "    • 'background status' - Check the auto-tracker")
    print(Fore.YELLOW + "    • 'ai help' - Free AI features (headline, about, InMail, discovery)")
    print(Fore.YELLOW + "    • 'list jobs' - Show tracked searches")
    print(Fore.YELLOW + "    • 'stop monitoring' - Pause tracking")
    print(Fore.WHITE + "    • Type " + Fore.YELLOW + "'clear'" + Fore.WHITE + " to reset conversation")
    print(Fore.WHITE + "    • Type " + Fore.RED + "'exit'" + Fore.WHITE + " to disconnect")
    print_border()
    print()
    
    # Check API keys
    if os.environ.get("RAPID_API_KEY"):
        print_system_message("✓ RapidAPI Key Detected - using premium LinkedIn tracking")
    else:
        print_system_message("✓ Free mode active - using LinkedIn public search (no API key needed)")
    
    if os.environ.get("HF_API_KEY"):
        print_system_message("✓ Hugging Face API Key Detected")
    else:
        print_system_message("NO HF_API_KEY - Will use offline AI mode if needed")
    
    # Show background tracker status (jobs collected while SCOUT was closed)
    summary = jobs_store.get_summary()
    if summary["count"]:
        print_system_message(f"✓ {summary['count']} job(s) collected in background" + (f" (latest: {summary['last_updated'][:16].replace('T', ' ')})" if summary['last_updated'] else ""))
        print(Fore.WHITE + "  Type 'latest jobs' to see them.")
    if is_tracker_installed():
        interval = get_installed_interval()
        print_system_message(f"✓ Background tracker ACTIVE (every {interval or '30'} min) - jobs collect even when SCOUT is closed")
    else:
        print_system_message("⏸ Background tracker NOT installed")
        print(Fore.WHITE + "  Type 'enable background tracker' to collect jobs automatically 24/7 (even when you're not running me).")
    
    print()
    time.sleep(0.5)

def main():
    """Main function"""
    try:
        # Startup sequence
        animate_startup()
        
        # Initialize chatbot
        chatbot = ScoutChatbot()
        
        # Main loop
        while True:
            try:
                # User prompt with hacker style
                user_input = input(Fore.GREEN + Style.BRIGHT + "┌─[" + Fore.MAGENTA + "YOU" + Fore.GREEN + "]\n└──> " + Fore.WHITE).strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.lower() in ['exit', 'quit', 'bye']:
                    chatbot.stop_job_monitoring()
                    print()
                    print_system_message("DISCONNECTING...")
                    time.sleep(0.5)
                    print(Fore.RED + Style.BRIGHT + "╔═══════════════════════════════════════╗")
                    print(Fore.RED + Style.BRIGHT + "║  CONNECTION TERMINATED - GOODBYE     ║")
                    print(Fore.RED + Style.BRIGHT + "╚═══════════════════════════════════════╝")
                    break
                
                if user_input.lower() == 'clear':
                    chatbot.clear_history()
                    print_scout_logo()
                    print_system_message("CONVERSATION MEMORY CLEARED")
                    print()
                    continue
                
                # Show processing animation
                print()
                print(Fore.YELLOW + Style.DIM + "[PROCESSING...]", end='', flush=True)
                
                # Get response
                response = chatbot.chat(user_input)
                
                # Clear processing message
                print('\r' + ' ' * 20 + '\r', end='')
                
                # Display response
                print_scout_response(response)
                
            except KeyboardInterrupt:
                print("\n")
                print_system_message("INTERRUPT DETECTED")
                confirm = input(Fore.YELLOW + "Disconnect? (y/n): " + Fore.WHITE).strip().lower()
                if confirm == 'y':
                    print()
                    print(Fore.RED + Style.BRIGHT + "CONNECTION TERMINATED")
                    break
                else:
                    print()
                    continue
                    
    except Exception as e:
        print(Fore.RED + Style.BRIGHT + f"\n[FATAL ERROR] {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
