#!/usr/bin/env python3
"""
LinkedIn Job Tracker - RSS/Web Scraping Alternative
No API key required! Uses LinkedIn's public job search
"""

import time
import json
import hashlib
import os
import re
from datetime import datetime
from typing import List, Dict, Set
import requests
from bs4 import BeautifulSoup
from colorama import Fore, Style, init

init(autoreset=True)


class LinkedInRSSTracker:
    """
    Alternative LinkedIn tracker using public job search
    No API key required - 100% free forever!
    """
    
    def __init__(self):
        """Initialize the RSS/scraping based tracker"""
        self.seen_jobs: Set[str] = set()
        self.jobs_file = "jobs_cache_rss.json"
        self.search_queries = []
        self.notification_callback = None
        self.check_interval = 120  # Check every 2 minutes
        
        # User agent to avoid blocking
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        
        self.load_seen_jobs()
    
    def load_seen_jobs(self):
        """Load previously seen jobs from cache"""
        if os.path.exists(self.jobs_file):
            try:
                with open(self.jobs_file, 'r') as f:
                    data = json.load(f)
                    self.seen_jobs = set(data.get('seen_jobs', []))
                    self.search_queries = data.get('search_queries', [])
                    print(Fore.GREEN + f"[RSS TRACKER] Loaded {len(self.seen_jobs)} previously seen jobs")
            except Exception as e:
                print(Fore.YELLOW + f"[RSS TRACKER] Could not load cache: {e}")
    
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
            print(Fore.RED + f"[RSS TRACKER] Could not save cache: {e}")
    
    def add_search_query(self, keywords: str, location: str = ""):
        """Add a job search query to monitor"""
        query = {
            'keywords': keywords,
            'location': location,
            'added_at': datetime.now().isoformat()
        }
        
        if query not in self.search_queries:
            self.search_queries.append(query)
            self.save_seen_jobs()
            print(Fore.GREEN + f"[RSS TRACKER] Added search: '{keywords}' in '{location or 'Any Location'}'")
            return True
        return False
    
    def remove_search_query(self, index: int):
        """Remove a search query by index"""
        if 0 <= index < len(self.search_queries):
            removed = self.search_queries.pop(index)
            self.save_seen_jobs()
            print(Fore.YELLOW + f"[RSS TRACKER] Removed search: '{removed['keywords']}'")
            return True
        return False
    
    def list_search_queries(self):
        """List all active search queries"""
        if not self.search_queries:
            print(Fore.YELLOW + "[RSS TRACKER] No active job searches")
            return
        
        print(Fore.CYAN + Style.BRIGHT + "\n[ACTIVE JOB SEARCHES - RSS MODE]")
        print(Fore.CYAN + "=" * 60)
        for i, query in enumerate(self.search_queries):
            print(Fore.WHITE + f"{i + 1}. Keywords: {Fore.GREEN}{query['keywords']}")
            if query.get('location'):
                print(Fore.WHITE + f"   Location: {query['location']}")
            print()
    
    def generate_job_id(self, job: Dict) -> str:
        """Generate unique ID for a job posting"""
        unique_string = f"{job.get('title', '')}_{job.get('company', '')}_{job.get('location', '')}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def build_linkedin_url(self, keywords: str, location: str = "", early_only: bool = False) -> str:
        """Build LinkedIn job search URL.

        early_only=True adds LinkedIn's free "early applicant" filter
        (f_EA=true) which only returns jobs where few people have applied —
        the free equivalent of Premium's "under 10 applicants" filter.
        """
        base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        
        # Clean up keywords and location
        keywords_clean = keywords.strip()
        location_clean = location.strip()
        
        params = []
        params.append(f"keywords={requests.utils.quote(keywords_clean)}")
        
        if location_clean:
            params.append(f"location={requests.utils.quote(location_clean)}")
        
        # Sort by most recent
        params.append("sortBy=DD")  # Date Descending
        params.append("f_TPR=r86400")  # Posted in last 24 hours
        if early_only:
            params.append("f_EA=true")  # Early applicant (low competition) jobs only
        params.append("start=0")
        
        url = base_url + "?" + "&".join(params)
        return url
    
    def parse_job_card(self, card) -> Dict:
        """Parse a job listing card from HTML"""
        try:
            job = {}
            
            # Job title
            title_elem = card.find('h3', class_='base-search-card__title')
            if title_elem:
                job['title'] = title_elem.text.strip()
            
            # Company name
            company_elem = card.find('h4', class_='base-search-card__subtitle')
            if company_elem:
                job['company'] = company_elem.text.strip()
            
            # Location
            location_elem = card.find('span', class_='job-search-card__location')
            if location_elem:
                job['location'] = location_elem.text.strip()
            
            # Job link
            link_elem = card.find('a', class_='base-card__full-link')
            if link_elem and link_elem.get('href'):
                job['link'] = link_elem['href']
                # Extract job ID from URL
                job_id_match = re.search(r'/(\d+)/', job['link'])
                if job_id_match:
                    job['job_id'] = job_id_match.group(1)
            
            # Posted date
            date_elem = card.find('time')
            if date_elem:
                job['posted_date'] = date_elem.get('datetime', '')
            
            # Low-competition badge ("Be an early applicant" = few applicants)
            benefits = card.find('span', class_='job-posting-benefits__text')
            if benefits and 'early applicant' in benefits.get_text(strip=True).lower():
                job['early_applicant'] = True
            else:
                job['early_applicant'] = False
            
            return job if job.get('title') else None
            
        except Exception as e:
            print(Fore.RED + f"[RSS TRACKER] Error parsing job card: {e}")
            return None
    
    def search_jobs(self, keywords: str, location: str = "", early_only: bool = False) -> List[Dict]:
        """
        Search LinkedIn jobs using web scraping
        No API key required!

        early_only=True filters to low-competition jobs ("Be an early applicant").
        """
        print(Fore.CYAN + f"[RSS TRACKER] Searching: '{keywords}' in '{location or 'Any Location'}'..." + (" [EARLY APPLICANTS ONLY]" if early_only else ""))
        
        url = self.build_linkedin_url(keywords, location, early_only=early_only)
        
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find job cards
            job_cards = soup.find_all('div', class_='base-card')
            
            if not job_cards:
                # Try alternative selector
                job_cards = soup.find_all('li', class_='jobs-search__results-list')
            
            jobs = []
            for card in job_cards:
                job = self.parse_job_card(card)
                if job:
                    # Belt-and-braces: even if the URL filter is ignored, only
                    # keep jobs that actually carry the early-applicant badge.
                    if early_only and not job.get('early_applicant'):
                        continue
                    jobs.append(job)
            
            print(Fore.GREEN + f"[RSS TRACKER] Found {len(jobs)} jobs" + (f" ({sum(1 for j in jobs if j.get('early_applicant'))} early-applicant)" if early_only else ""))
            return jobs
            
        except requests.exceptions.RequestException as e:
            print(Fore.RED + f"[RSS TRACKER] Request Error: {e}")
            return []
        except Exception as e:
            print(Fore.RED + f"[RSS TRACKER] Parse Error: {e}")
            return []
    
    def check_for_new_jobs(self) -> List[Dict]:
        """Check all search queries for new jobs"""
        new_jobs = []
        
        for query in self.search_queries:
            jobs = self.search_jobs(
                query['keywords'],
                query.get('location', '')
            )
            
            for job in jobs:
                job_id = self.generate_job_id(job)
                
                if job_id not in self.seen_jobs:
                    self.seen_jobs.add(job_id)
                    job['query'] = query['keywords']
                    job['found_at'] = datetime.now().isoformat()
                    new_jobs.append(job)
            
            # Be nice to LinkedIn - don't hammer their servers
            time.sleep(2)
        
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
        
        if job.get('posted_date'):
            lines.append(Fore.WHITE + f"📅 Posted: {job.get('posted_date')}")
        
        if job.get('link'):
            lines.append(Fore.YELLOW + f"🔗 Link: {job.get('link')}")
        
        lines.extend([
            Fore.MAGENTA + f"⏰ Found: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            Fore.GREEN + "💡 Apply fast to be one of the first applicants!",
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
            
            if self.notification_callback:
                try:
                    self.notification_callback(job)
                except Exception as e:
                    print(Fore.RED + f"[RSS TRACKER] Notification callback error: {e}")
    
    def start_monitoring(self, interval: int = 120):
        """Start continuous monitoring for new jobs"""
        self.check_interval = interval
        
        print(Fore.GREEN + Style.BRIGHT + "\n[RSS TRACKER] Starting LinkedIn Job Monitor (No API Key!)")
        print(Fore.CYAN + "═" * 60)
        print(Fore.WHITE + f"Check Interval: {interval} seconds")
        print(Fore.WHITE + f"Active Searches: {len(self.search_queries)}")
        print(Fore.GREEN + "✅ 100% FREE - No API limits!")
        print(Fore.CYAN + "═" * 60)
        print(Fore.YELLOW + "\nPress Ctrl+C to stop monitoring\n")
        
        if not self.search_queries:
            print(Fore.RED + "[RSS TRACKER] No search queries configured!")
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
            print(Fore.YELLOW + "\n\n[RSS TRACKER] Monitoring stopped by user")
            print(Fore.GREEN + f"Total jobs tracked: {len(self.seen_jobs)}")
    
    def get_statistics(self):
        """Get tracker statistics"""
        stats = {
            'total_jobs_seen': len(self.seen_jobs),
            'active_searches': len(self.search_queries),
            'check_interval': self.check_interval
        }
        
        print(Fore.CYAN + Style.BRIGHT + "\n[RSS TRACKER STATISTICS]")
        print(Fore.CYAN + "=" * 60)
        print(Fore.WHITE + f"Total Jobs Tracked: {stats['total_jobs_seen']}")
        print(Fore.WHITE + f"Active Searches: {stats['active_searches']}")
        print(Fore.WHITE + f"Check Interval: {stats['check_interval']} seconds")
        print(Fore.GREEN + "✅ 100% FREE - No API Costs!")
        print(Fore.CYAN + "=" * 60 + "\n")
        
        return stats
    
    def clear_cache(self):
        """Clear all cached jobs"""
        self.seen_jobs.clear()
        self.save_seen_jobs()
        print(Fore.GREEN + "[RSS TRACKER] Cache cleared!")


def main():
    """Test the RSS tracker"""
    print(Fore.CYAN + Style.BRIGHT + """
    ██╗     ██╗███╗   ██╗██╗  ██╗███████╗██████╗ ██╗███╗   ██╗
    ██║     ██║████╗  ██║██║ ██╔╝██╔════╝██╔══██╗██║████╗  ██║
    ██║     ██║██╔██╗ ██║█████╔╝ █████╗  ██║  ██║██║██╔██╗ ██║
    ██║     ██║██║╚██╗██║██╔═██╗ ██╔══╝  ██║  ██║██║██║╚██╗██║
    ███████╗██║██║ ╚████║██║  ██╗███████╗██████╔╝██║██║ ╚████║
    ╚══════╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚═════╝ ╚═╝╚═╝  ╚═══╝
    
    RSS TRACKER - 100% FREE (No API Key Needed!)
    """)
    
    tracker = LinkedInRSSTracker()
    
    # Example searches
    tracker.add_search_query("Python Developer", "Remote")
    tracker.add_search_query("Software Engineer", "San Francisco")
    
    tracker.list_search_queries()
    tracker.start_monitoring(interval=120)


if __name__ == "__main__":
    main()
