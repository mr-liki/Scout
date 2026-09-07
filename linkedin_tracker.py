#!/usr/bin/env python3
"""
LinkedIn Job Tracker for SCOUT
Real-time job monitoring and notifications
"""

import time
import json
import hashlib
import os
from datetime import datetime
from typing import List, Dict, Set
import requests
from colorama import Fore, Style, init

init(autoreset=True)


class LinkedInJobTracker:
    def __init__(self, rapid_api_key=None):
        """
        Initialize LinkedIn Job Tracker
        
        Args:
            rapid_api_key: RapidAPI key for LinkedIn API access
        """
        self.rapid_api_key = rapid_api_key or os.environ.get("RAPID_API_KEY")
        self.seen_jobs: Set[str] = set()
        self.jobs_file = "jobs_cache.json"
        self.search_queries = []
        self.notification_callback = None
        self.check_interval = 60  # Check every 60 seconds (1 minute)
        
        # Load previously seen jobs
        self.load_seen_jobs()
        
    def load_seen_jobs(self):
        """Load previously seen jobs from cache"""
        if os.path.exists(self.jobs_file):
            try:
                with open(self.jobs_file, 'r') as f:
                    data = json.load(f)
                    self.seen_jobs = set(data.get('seen_jobs', []))
                    self.search_queries = data.get('search_queries', [])
                    print(Fore.GREEN + f"[TRACKER] Loaded {len(self.seen_jobs)} previously seen jobs")
            except Exception as e:
                print(Fore.YELLOW + f"[TRACKER] Could not load cache: {e}")
    
    def save_seen_jobs(self):
        """Save seen jobs to cache"""
        try:
            data = {
                'seen_jobs': list(self.seen_jobs),
                'search_queries': self.search_queries,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.jobs_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(Fore.RED + f"[TRACKER] Could not save cache: {e}")
    
    def add_search_query(self, keywords: str, location: str = "", job_type: str = ""):
        """
        Add a job search query to monitor
        
        Args:
            keywords: Job title or keywords (e.g., "Python Developer", "Machine Learning Engineer")
            location: Location filter (e.g., "United States", "Remote", "San Francisco")
            job_type: Job type filter (e.g., "Full-time", "Contract", "Internship")
        """
        query = {
            'keywords': keywords,
            'location': location,
            'job_type': job_type,
            'added_at': datetime.now().isoformat()
        }
        
        # Avoid duplicates
        if query not in self.search_queries:
            self.search_queries.append(query)
            self.save_seen_jobs()
            print(Fore.GREEN + f"[TRACKER] Added search: '{keywords}' in '{location or 'Any Location'}'")
            return True
        return False
    
    def remove_search_query(self, index: int):
        """Remove a search query by index"""
        if 0 <= index < len(self.search_queries):
            removed = self.search_queries.pop(index)
            self.save_seen_jobs()
            print(Fore.YELLOW + f"[TRACKER] Removed search: '{removed['keywords']}'")
            return True
        return False
    
    def list_search_queries(self):
        """List all active search queries"""
        if not self.search_queries:
            print(Fore.YELLOW + "[TRACKER] No active job searches")
            return
        
        print(Fore.CYAN + Style.BRIGHT + "\n[ACTIVE JOB SEARCHES]")
        print(Fore.CYAN + "=" * 60)
        for i, query in enumerate(self.search_queries):
            print(Fore.WHITE + f"{i + 1}. Keywords: {Fore.GREEN}{query['keywords']}")
            if query.get('location'):
                print(Fore.WHITE + f"   Location: {query['location']}")
            if query.get('job_type'):
                print(Fore.WHITE + f"   Type: {query['job_type']}")
            print()
    
    def generate_job_id(self, job: Dict) -> str:
        """Generate unique ID for a job posting"""
        # Create hash from job title, company, and location
        unique_string = f"{job.get('title', '')}_{job.get('company', '')}_{job.get('location', '')}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def search_jobs_rapidapi(self, keywords: str, location: str = "", job_type: str = "") -> List[Dict]:
        """
        Search LinkedIn jobs using RapidAPI
        
        Returns:
            List of job postings
        """
        if not self.rapid_api_key:
            print(Fore.RED + "[TRACKER] RapidAPI key not found. Set RAPID_API_KEY environment variable.")
            return []
        
        url = "https://linkedin-data-api.p.rapidapi.com/search-jobs"
        
        headers = {
            "X-RapidAPI-Key": self.rapid_api_key,
            "X-RapidAPI-Host": "linkedin-data-api.p.rapidapi.com"
        }
        
        querystring = {
            "keywords": keywords,
            "locationId": location,
            "datePosted": "past-24h",  # Only get recent jobs
            "sort": "recent"
        }
        
        if job_type:
            querystring["jobType"] = job_type.lower().replace("-", "")
        
        try:
            response = requests.get(url, headers=headers, params=querystring, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            jobs = data.get('data', [])
            
            return jobs
            
        except requests.exceptions.RequestException as e:
            print(Fore.RED + f"[TRACKER] API Error: {e}")
            return []
    
    def search_jobs_scraping(self, keywords: str, location: str = "") -> List[Dict]:
        """
        Fallback: Search LinkedIn jobs using web scraping (LinkedIn public job search)
        Note: This is a simplified version - real implementation may need more robust parsing
        
        Returns:
            List of job postings
        """
        # LinkedIn public job search URL
        base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        
        params = {
            'keywords': keywords,
            'location': location,
            'start': 0,
            'sortBy': 'DD'  # Date descending
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        try:
            response = requests.get(base_url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            
            # Parse HTML response (simplified - you'd need BeautifulSoup for real parsing)
            # This is a placeholder - actual implementation would parse HTML
            jobs = []
            
            # For now, return empty list - real implementation needs HTML parsing
            print(Fore.YELLOW + "[TRACKER] Web scraping not fully implemented - use RapidAPI")
            
            return jobs
            
        except Exception as e:
            print(Fore.RED + f"[TRACKER] Scraping Error: {e}")
            return []
    
    def search_jobs(self, keywords: str, location: str = "", job_type: str = "", early_only: bool = False) -> List[Dict]:
        """
        Main job search method - tries API first, then falls back to the
        FREE LinkedIn public search (no API key required).

        early_only=True filters to low-competition jobs ("Be an early applicant").
        """
        print(Fore.CYAN + f"[TRACKER] Searching: '{keywords}' in '{location or 'Any Location'}'..." + (" [EARLY APPLICANTS ONLY]" if early_only else ""))
        
        # Early-applicant filtering is only supported by the free LinkedIn search,
        # so when early_only is requested we go straight there (RapidAPI's
        # search-jobs endpoint doesn't apply the f_EA filter and lacks the badge).
        if early_only:
            return self._free_search(keywords, location, early_only=True)
        
        # Try RapidAPI first (only if a key is configured)
        if self.rapid_api_key:
            jobs = self.search_jobs_rapidapi(keywords, location, job_type)
            if jobs:
                return jobs
            print(Fore.YELLOW + "[TRACKER] RapidAPI returned nothing - falling back to free LinkedIn search")
        
        # Free fallback: LinkedIn public job search (no API key needed)
        return self._free_search(keywords, location, early_only=False)
    
    def _free_search(self, keywords: str, location: str, early_only: bool):
        """Free LinkedIn public search (no API key needed)."""
        try:
            from linkedin_rss_tracker import LinkedInRSSTracker
            rss = LinkedInRSSTracker()
            return rss.search_jobs(keywords, location, early_only=early_only)
        except Exception as e:
            print(Fore.RED + f"[TRACKER] Free search error: {e}")
            return []
    
    def check_for_new_jobs(self) -> List[Dict]:
        """
        Check all search queries for new jobs
        
        Returns:
            List of new job postings
        """
        new_jobs = []
        
        for query in self.search_queries:
            jobs = self.search_jobs(
                query['keywords'],
                query.get('location', ''),
                query.get('job_type', '')
            )
            
            for job in jobs:
                job_id = self.generate_job_id(job)
                
                if job_id not in self.seen_jobs:
                    self.seen_jobs.add(job_id)
                    job['query'] = query['keywords']
                    job['found_at'] = datetime.now().isoformat()
                    new_jobs.append(job)
        
        if new_jobs:
            self.save_seen_jobs()
        
        return new_jobs
    
    def format_job_notification(self, job: Dict) -> str:
        """Format a job posting for notification"""
        lines = [
            Fore.GREEN + Style.BRIGHT + "🚀 NEW JOB ALERT!",
            Fore.CYAN + "═" * 60,
            Fore.WHITE + Style.BRIGHT + f"📋 Title: {job.get('title', 'N/A')}",
            Fore.WHITE + f"🏢 Company: {job.get('company', 'N/A')}",
            Fore.WHITE + f"📍 Location: {job.get('location', 'N/A')}",
        ]
        
        if job.get('employmentType'):
            lines.append(Fore.WHITE + f"💼 Type: {job.get('employmentType')}")
        
        if job.get('description'):
            desc = job['description'][:200] + "..." if len(job['description']) > 200 else job['description']
            lines.append(Fore.WHITE + f"📝 Description: {desc}")
        
        if job.get('url') or job.get('link'):
            lines.append(Fore.YELLOW + f"🔗 Link: {job.get('url') or job.get('link')}")
        
        lines.extend([
            Fore.MAGENTA + f"⏰ Found: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            Fore.CYAN + "═" * 60
        ])
        
        return "\n".join(lines)
    
    def notify_new_jobs(self, jobs: List[Dict]):
        """Send notifications for new jobs"""
        if not jobs:
            return
        
        print(Fore.GREEN + Style.BRIGHT + f"\n🎉 FOUND {len(jobs)} NEW JOB(S)!\n")
        
        for job in jobs:
            notification = self.format_job_notification(job)
            print(notification)
            print()
            
            # Call custom notification callback if set
            if self.notification_callback:
                try:
                    self.notification_callback(job)
                except Exception as e:
                    print(Fore.RED + f"[TRACKER] Notification callback error: {e}")
    
    def start_monitoring(self, interval: int = 60):
        """
        Start continuous monitoring for new jobs
        
        Args:
            interval: Check interval in seconds (default: 60)
        """
        self.check_interval = interval
        
        print(Fore.GREEN + Style.BRIGHT + "\n[TRACKER] Starting LinkedIn Job Monitor")
        print(Fore.CYAN + "═" * 60)
        print(Fore.WHITE + f"Check Interval: {interval} seconds")
        print(Fore.WHITE + f"Active Searches: {len(self.search_queries)}")
        print(Fore.CYAN + "═" * 60)
        print(Fore.YELLOW + "\nPress Ctrl+C to stop monitoring\n")
        
        if not self.search_queries:
            print(Fore.RED + "[TRACKER] No search queries configured!")
            print(Fore.YELLOW + "Add searches using: tracker.add_search_query('keywords', 'location')")
            return
        
        check_count = 0
        
        try:
            while True:
                check_count += 1
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                print(Fore.CYAN + f"[{timestamp}] Check #{check_count} - Scanning for new jobs...")
                
                new_jobs = self.check_for_new_jobs()
                
                if new_jobs:
                    self.notify_new_jobs(new_jobs)
                else:
                    print(Fore.WHITE + f"No new jobs found. Next check in {interval} seconds.\n")
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print(Fore.YELLOW + "\n\n[TRACKER] Monitoring stopped by user")
            print(Fore.GREEN + f"Total jobs tracked: {len(self.seen_jobs)}")
    
    def get_statistics(self):
        """Get tracker statistics"""
        stats = {
            'total_jobs_seen': len(self.seen_jobs),
            'active_searches': len(self.search_queries),
            'check_interval': self.check_interval
        }
        
        print(Fore.CYAN + Style.BRIGHT + "\n[TRACKER STATISTICS]")
        print(Fore.CYAN + "═" * 60)
        print(Fore.WHITE + f"Total Jobs Tracked: {stats['total_jobs_seen']}")
        print(Fore.WHITE + f"Active Searches: {stats['active_searches']}")
        print(Fore.WHITE + f"Check Interval: {stats['check_interval']} seconds")
        print(Fore.CYAN + "═" * 60 + "\n")
        
        return stats
    
    def clear_cache(self):
        """Clear all cached jobs"""
        self.seen_jobs.clear()
        self.save_seen_jobs()
        print(Fore.GREEN + "[TRACKER] Cache cleared!")


def main():
    """Test the LinkedIn Job Tracker"""
    print(Fore.CYAN + Style.BRIGHT + """
    ██╗     ██╗███╗   ██╗██╗  ██╗███████╗██████╗ ██╗███╗   ██╗
    ██║     ██║████╗  ██║██║ ██╔╝██╔════╝██╔══██╗██║████╗  ██║
    ██║     ██║██╔██╗ ██║█████╔╝ █████╗  ██║  ██║██║██╔██╗ ██║
    ██║     ██║██║╚██╗██║██╔═██╗ ██╔══╝  ██║  ██║██║██║╚██╗██║
    ███████╗██║██║ ╚████║██║  ██╗███████╗██████╔╝██║██║ ╚████║
    ╚══════╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚═════╝ ╚═╝╚═╝  ╚═══╝
    
    JOB TRACKER for SCOUT
    """)
    
    # Initialize tracker
    tracker = LinkedInJobTracker()
    
    # Example: Add some search queries
    tracker.add_search_query("Python Developer", "Remote")
    tracker.add_search_query("Machine Learning Engineer", "United States")
    tracker.add_search_query("Data Scientist", "San Francisco")
    
    # List active searches
    tracker.list_search_queries()
    
    # Start monitoring
    tracker.start_monitoring(interval=90)  # Check every 90 seconds


if __name__ == "__main__":
    main()
