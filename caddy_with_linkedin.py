#!/usr/bin/env python3
"""
CADDY - Cyberpunk AI Terminal Assistant with LinkedIn Job Tracking
Enhanced version with real-time job monitoring
"""

import requests
import os
import sys
import time
import random
import threading
from colorama import Fore, Back, Style, init
from linkedin_tracker import LinkedInJobTracker
import jobs_store

# Initialize colorama
init(autoreset=True)


class CaddyWithLinkedIn:
    def __init__(self, api_key=None):
        """Initialize CADDY with LinkedIn tracking"""
        self.api_key = api_key or os.environ.get("HF_API_KEY")
        self.api_url = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-medium"
        self.conversation_history = []
        self.offline_mode = False
        self.user_name = "User"
        
        # Initialize LinkedIn Job Tracker
        self.job_tracker = LinkedInJobTracker()
        self.monitoring_active = False
        self.monitoring_thread = None
    
    def start_job_monitoring(self, interval=60):
        """Start LinkedIn job monitoring in background"""
        if self.monitoring_active:
            return "Job monitoring is already running!"
        
        if not self.job_tracker.search_queries:
            return "Please add job searches first using 'add job search' command!"
        
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
        
        return f"LinkedIn job monitoring started! Checking every {interval} seconds."
    
    def stop_job_monitoring(self):
        """Stop LinkedIn job monitoring"""
        if not self.monitoring_active:
            return "Job monitoring is not running."
        
        self.monitoring_active = False
        return "Job monitoring stopped."
    
    def extract_job_search_params(self, user_message):
        """Extract job keywords and location from natural language"""
        import re
        
        msg = user_message.lower()
        
        # Common multi-word locations (check these first)
        known_locations = [
            'san francisco', 'new york', 'los angeles', 'new jersey', 
            'united states', 'united kingdom', 'hong kong', 'new delhi',
            'saudi arabia', 'south africa', 'costa rica'
        ]
        
        location = ""
        keywords_part = msg
        
        # Check for known multi-word locations first
        for known_loc in known_locations:
            if known_loc in msg:
                location = ' '.join(word.capitalize() for word in known_loc.split())
                # Remove location from message
                keywords_part = msg.replace(f"in {known_loc}", "").replace(f"at {known_loc}", "")
                keywords_part = keywords_part.replace(f"near {known_loc}", "").replace(f"from {known_loc}", "")
                break
        
        # If no multi-word location found, try single word
        if not location:
            location_patterns = [
                r'\bin\s+(\w+)',
                r'\bat\s+(\w+)',
                r'\bnear\s+(\w+)',
                r'\baround\s+(\w+)',
                r'\bfrom\s+(\w+)',
            ]
            
            for pattern in location_patterns:
                match = re.search(pattern, msg)
                if match:
                    location = match.group(1).capitalize()
                    keywords_part = msg[:match.start()].strip()
                    break
        
        # Extract job title from keywords_part
        # Remove common words
        remove_words = ["list", "show", "find", "search", "get", "me", "the", "current", "all", 
                       "jobs", "job", "positions", "position", "roles", "role", "openings", "opening",
                       "for", "a", "an", "looking", "want", "need", "some"]
        
        words = keywords_part.split()
        job_words = [w for w in words if w not in remove_words]
        keywords = " ".join(job_words).strip()
        
        # Capitalize job title properly
        if keywords:
            keywords = " ".join(word.capitalize() for word in keywords.split())
        
        return keywords, location

    
    def get_offline_response(self, user_message):
        """Generate response using local pattern matching - Enhanced with LinkedIn commands"""
        msg = user_message.lower().strip()
        
        # Explicit LinkedIn commands (must be checked BEFORE smart-search intent,
        # otherwise e.g. "list jobs" / "show collected jobs" get misparsed)
        if "list job" in msg or "show searches" in msg or "my searches" in msg:
            return "LINKEDIN_LIST_SEARCHES"
        
        if "latest job" in msg or "recent job" in msg or "collected job" in msg or "saved job" in msg or "what jobs" in msg:
            return "LINKEDIN_LATEST_JOBS"
        
        if "add job search" in msg or "track job" in msg or "monitor job" in msg:
            return """To add a job search, please provide:
• Job keywords (e.g., "Python Developer", "Data Scientist")
• Location (optional, e.g., "Remote", "San Francisco", "United States")
• Job type (optional, e.g., "Full-time", "Contract")

Example: "add job search: Python Developer, Remote, Full-time"
"""
        
        if "start monitoring" in msg or "start tracking" in msg:
            return "LINKEDIN_START_MONITORING"
        
        if "stop monitoring" in msg or "stop tracking" in msg:
            return "LINKEDIN_STOP_MONITORING"
        
        if "job stats" in msg or "tracker stats" in msg:
            return "LINKEDIN_SHOW_STATS"
        
        if "clear job cache" in msg:
            return "LINKEDIN_CLEAR_CACHE"
        
        # Detect natural-language job search intent (e.g. "list Python jobs in Remote")
        job_search_keywords = ["list", "show", "find", "search", "get", "track", "monitor", "looking for"]
        job_indicators = ["job", "jobs", "position", "positions", "role", "roles", "opening", "openings"]
        
        has_search_intent = any(keyword in msg for keyword in job_search_keywords)
        has_job_indicator = any(indicator in msg for indicator in job_indicators)
        
        # If user is asking about jobs, trigger smart search
        if has_search_intent and has_job_indicator:
            return "LINKEDIN_SMART_SEARCH"
        
        # Greetings
        greetings = ["hello", "hi", "hey", "greetings", "sup", "yo", "howdy"]
        if any(word in msg for word in greetings):
            responses = [
                "Hey there! I'm CADDY with LinkedIn job tracking! Ask me to monitor jobs or just chat.",
                "Greetings! CADDY here - now with real-time LinkedIn job alerts! What can I help with?",
                "Hello! I'm CADDY - your AI assistant with LinkedIn job superpowers! Ready to help!",
            ]
            return random.choice(responses)
        
        # What can you do
        if any(phrase in msg for phrase in ["what can you do", "what do you do", "your capabilities", "help me"]):
            return """I'm CADDY with LinkedIn Job Tracking! I can:
• Chat and answer questions (AI-powered)
• 🔥 Track LinkedIn jobs in REAL-TIME
• 🚀 Send instant alerts for new job postings
• 📊 Monitor multiple job searches simultaneously
• 💼 Filter by keywords, location, and job type

LinkedIn Commands:
- "add job search" - Add a new job to track
- "list jobs" - Show all tracked searches
- "start monitoring" - Begin real-time tracking
- "stop monitoring" - Pause tracking
- "job stats" - View tracking statistics

What would you like to do?"""
        
        # Thanks
        if any(word in msg for word in ["thank", "thanks", "thx"]):
            return random.choice([
                "You're welcome! Happy job hunting! 💼",
                "No problem! Let me know if you need more job alerts!",
                "Anytime! Keep me running and I'll find you the perfect job! 🚀"
            ])
        
        # Time
        if any(word in msg for word in ["time", "date"]):
            return f"Current time: {time.strftime('%H:%M:%S')}\nDate: {time.strftime('%Y-%m-%d')}"
        
        # Default
        defaults = [
            "I'm listening! Ask me about LinkedIn job tracking or just chat.",
            "Interesting! Want me to help you track LinkedIn jobs?",
            "Got it! I can also monitor LinkedIn jobs for you in real-time.",
        ]
        return random.choice(defaults)
    
    def chat(self, user_message):
        """Send message and get response - Enhanced with LinkedIn commands"""
        msg = user_message.lower().strip()
        
        # Handle LinkedIn-specific commands
        if "add job search:" in msg:
            # Parse: "add job search: Python Developer, Remote, Full-time"
            parts = msg.split("add job search:")[1].strip().split(",")
            keywords = parts[0].strip() if len(parts) > 0 else ""
            location = parts[1].strip() if len(parts) > 1 else ""
            job_type = parts[2].strip() if len(parts) > 2 else ""
            
            if keywords:
                self.job_tracker.add_search_query(keywords, location, job_type)
                return f"✅ Added job search: '{keywords}' in '{location or 'Any Location'}'\nStart monitoring with: 'start monitoring'"
            else:
                return "Please provide at least job keywords!"
        
        # Get regular response
        response = self.get_offline_response(user_message)
        
        # Handle smart search detection
        if response == "LINKEDIN_SMART_SEARCH":
            # Extract job title and location from natural language
            keywords, location = self.extract_job_search_params(user_message)
            
            if keywords:
                # Automatically add the search
                self.job_tracker.add_search_query(keywords, location, "")
                
                # Perform one immediate search
                print(Fore.YELLOW + "\n[SEARCHING] Looking for jobs on LinkedIn...\n")
                jobs = self.job_tracker.search_jobs(keywords, location)
                
                # Save what we found so it survives after CADDY closes
                jobs_store.store_new_jobs(jobs)
                
                if jobs:
                    result = f"🎯 Found {len(jobs)} '{keywords}' jobs"
                    if location:
                        result += f" in {location}"
                    result += "!\n\n"
                    
                    # Show first 5 jobs
                    for i, job in enumerate(jobs[:5]):
                        result += f"\n{i+1}. 📋 {job.get('title', 'N/A')}\n"
                        result += f"   🏢 {job.get('company', 'N/A')}\n"
                        result += f"   📍 {job.get('location', 'N/A')}\n"
                        if job.get('link') or job.get('url'):
                            result += f"   🔗 {job.get('link') or job.get('url')}\n"
                    
                    if len(jobs) > 5:
                        result += f"\n... and {len(jobs) - 5} more jobs!"
                    
                    result += f"\n\n✅ Added '{keywords}' to your tracked searches!"
                    result += "\n💡 Type 'start monitoring' for real-time alerts, or 'latest jobs' to see everything collected (even while CADDY was closed)."
                    
                    return result
                else:
                    return f"🔍 Searched for '{keywords}' jobs" + (f" in {location}" if location else "") + " but didn't find any right now.\n\n" + \
                           "This could mean:\n" + \
                           "• No jobs posted recently\n" + \
                           "• Try broader keywords\n" + \
                           "• RAPID_API_KEY needed for better results\n\n" + \
                           "✅ I've added this search to tracking. Type 'start monitoring' to get alerts when new jobs appear!"
            else:
                return "I'd love to help you search for jobs! Please tell me:\n\n" + \
                       "1. What job are you looking for? (e.g., 'AI Engineer', 'Python Developer')\n" + \
                       "2. Where? (e.g., 'Bengaluru', 'Remote', 'San Francisco')\n\n" + \
                       "Example: 'list AI Engineer jobs in Bengaluru'"
        
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
        
        if response == "LINKEDIN_LATEST_JOBS":
            jobs = jobs_store.load_jobs()
            if not jobs:
                return "No jobs collected yet. Try:\n1. 'list Python Developer jobs in Remote' to search now\n2. Install the background tracker (./setup_background_tracker.sh) so jobs collect even while CADDY is closed"
            summary = jobs_store.get_summary()
            result = f"💼 {len(jobs)} job(s) collected"
            if summary['last_updated']:
                result += f" (latest: {summary['last_updated'][:16].replace('T', ' ')})"
            result += ":\n"
            for i, job in enumerate(jobs[-10:], 1):
                result += f"\n{i}. 📋 {job.get('title', 'N/A')}\n"
                result += f"   🏢 {job.get('company', 'N/A')}\n"
                result += f"   📍 {job.get('location', 'N/A')}\n"
                if job.get('link') or job.get('url'):
                    result += f"   🔗 {job.get('link') or job.get('url')}\n"
                if job.get('query'):
                    result += f"   🔍 Search: {job.get('query')}\n"
            result += f"\n💡 Showing the latest 10 of {len(jobs)}. Type 'find <job> jobs' to search live."
            return result
        
        # Try online AI chat if not a LinkedIn command
        if not self.offline_mode and response not in ["LINKEDIN_LIST_SEARCHES", "LINKEDIN_START_MONITORING"]:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            conversation_text = ""
            for msg_item in self.conversation_history:
                conversation_text += f"{msg_item}\n"
            conversation_text += user_message
            
            payload = {
                "inputs": conversation_text,
                "parameters": {"max_length": 1000, "temperature": 0.7}
            }
            
            try:
                api_response = requests.post(self.api_url, headers=headers, json=payload, timeout=10)
                
                if api_response.status_code == 200:
                    result = api_response.json()
                    if isinstance(result, list) and len(result) > 0:
                        bot_response = result[0].get("generated_text", "").strip()
                        if bot_response.startswith(conversation_text):
                            bot_response = bot_response[len(conversation_text):].strip()
                        if bot_response:
                            response = bot_response
            except:
                pass  # Fall back to offline response
        
        self.conversation_history.append(user_message)
        self.conversation_history.append(response)
        
        if len(self.conversation_history) > 12:
            self.conversation_history = self.conversation_history[-12:]
        
        return response
    
    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []


# Utility functions for UI
def print_caddy_logo():
    """Print CADDY logo with LinkedIn badge"""
    os.system('clear' if os.name != 'nt' else 'cls')
    
    logo = """
    ██████╗ █████╗ ██████╗ ██████╗ ██╗   ██╗
   ██╔════╝██╔══██╗██╔══██╗██╔══██╗╚██╗ ██╔╝
   ██║     ███████║██║  ██║██║  ██║ ╚████╔╝ 
   ██║     ██╔══██║██║  ██║██║  ██║  ╚██╔╝  
   ╚██████╗██║  ██║██████╔╝██████╔╝   ██║   
    ╚═════╝╚═╝  ╚═╝╚═════╝ ╚═════╝    ╚═╝   
    """
    
    for line in logo.split('\n'):
        print(Fore.CYAN + Style.BRIGHT + line)
    
    print(Fore.MAGENTA + Style.BRIGHT + "    [ CYBERPUNK AI + LINKEDIN JOB TRACKER ]")
    print(Fore.GREEN + Style.BRIGHT + "            🔥 Real-time Job Alerts 🔥")
    print()


def print_border():
    """Print decorative border"""
    print(Fore.CYAN + Style.BRIGHT + "═" * 70)


def print_caddy_response(message):
    """Print CADDY's response with style"""
    print()
    print(Fore.CYAN + Style.BRIGHT + "┌─[" + Fore.MAGENTA + "CADDY" + Fore.CYAN + "]")
    print(Fore.CYAN + "└──> " + Fore.WHITE + Style.BRIGHT + message)
    print()


def animate_startup():
    """Startup animation sequence"""
    print_caddy_logo()
    
    init_messages = [
        "INITIALIZING NEURAL INTERFACE...",
        "LOADING AI CORE MODULES...",
        "CONNECTING TO LINKEDIN API...",
        "CADDY ONLINE - READY FOR JOB TRACKING!"
    ]
    
    for msg in init_messages:
        print(Fore.GREEN + Style.BRIGHT + "[▓▓▓▓▓▓▓▓▓▓] " + msg)
        time.sleep(0.4)
    
    print()
    print_border()
    print(Fore.CYAN + Style.BRIGHT + "  COMMANDS:")
    print(Fore.WHITE + "    • Chat normally or use LinkedIn job commands")
    print(Fore.YELLOW + "    • 'add job search: <keywords>, <location>, <type>'")
    print(Fore.YELLOW + "    • 'list jobs' - Show tracked searches")
    print(Fore.YELLOW + "    • 'start monitoring' - Begin job tracking")
    print(Fore.YELLOW + "    • 'latest jobs' - Show jobs collected in background")
    print(Fore.YELLOW + "    • 'stop monitoring' - Pause tracking")
    print(Fore.YELLOW + "    • 'job stats' - View statistics")
    print(Fore.WHITE + "    • 'clear' - Reset conversation")
    print(Fore.RED + "    • 'exit' - Disconnect")
    print_border()
    print()
    
    # Check API keys
    if os.environ.get("RAPID_API_KEY"):
        print(Fore.GREEN + "[SYSTEM] ✓ RapidAPI Key Detected - LinkedIn tracking enabled!")
    else:
        print(Fore.YELLOW + "[SYSTEM] ⚠ No RAPID_API_KEY - Limited LinkedIn access")
        print(Fore.WHITE + "  Get key at: https://rapidapi.com/rockapis-rockapis-default/api/linkedin-data-api")
    
    if os.environ.get("HF_API_KEY"):
        print(Fore.GREEN + "[SYSTEM] ✓ Hugging Face API Key Detected")
    
    # Show background tracker status (jobs collected while CADDY was closed)
    try:
        summary = jobs_store.get_summary()
        if summary["count"]:
            print(Fore.GREEN + f"[SYSTEM] ✓ {summary['count']} job(s) collected in background" + (f" (latest: {summary['last_updated'][:16].replace('T', ' ')})" if summary['last_updated'] else ""))
            print(Fore.WHITE + "  Type 'latest jobs' to see them.")
    except Exception:
        pass
    
    print()
    time.sleep(0.5)


def main():
    """Main function"""
    try:
        animate_startup()
        
        # Initialize chatbot with LinkedIn
        caddy = CaddyWithLinkedIn()
        
        # Main loop
        while True:
            try:
                user_input = input(Fore.GREEN + Style.BRIGHT + "┌─[" + Fore.MAGENTA + "YOU" + Fore.GREEN + "]\n└──> " + Fore.WHITE).strip()
                
                if not user_input:
                    continue
                
                # Handle exit
                if user_input.lower() in ['exit', 'quit', 'bye']:
                    caddy.stop_job_monitoring()
                    print()
                    print(Fore.YELLOW + "[SYSTEM] DISCONNECTING...")
                    time.sleep(0.5)
                    print(Fore.RED + Style.BRIGHT + "╔═══════════════════════════════════════╗")
                    print(Fore.RED + Style.BRIGHT + "║  CONNECTION TERMINATED - GOODBYE     ║")
                    print(Fore.RED + Style.BRIGHT + "╚═══════════════════════════════════════╝")
                    break
                
                # Handle clear
                if user_input.lower() == 'clear':
                    caddy.clear_history()
                    print_caddy_logo()
                    print(Fore.YELLOW + "[SYSTEM] CONVERSATION MEMORY CLEARED")
                    print()
                    continue
                
                # Show processing
                print()
                print(Fore.YELLOW + Style.DIM + "[PROCESSING...]", end='', flush=True)
                
                # Get response
                response = caddy.chat(user_input)
                
                # Clear processing message
                print('\r' + ' ' * 20 + '\r', end='')
                
                # Display response
                print_caddy_response(response)
                
            except KeyboardInterrupt:
                print("\n")
                print(Fore.YELLOW + "[SYSTEM] INTERRUPT DETECTED")
                confirm = input(Fore.YELLOW + "Disconnect? (y/n): " + Fore.WHITE).strip().lower()
                if confirm == 'y':
                    caddy.stop_job_monitoring()
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
