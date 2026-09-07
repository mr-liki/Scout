#!/usr/bin/env python3
"""
Example usage of LinkedIn Job Tracker
Demonstrates how to use the tracker programmatically
"""

from linkedin_tracker import LinkedInJobTracker
import time
from colorama import Fore, Style, init

init(autoreset=True)


def example_basic_usage():
    """Basic example of using the job tracker"""
    print(Fore.CYAN + Style.BRIGHT + "\n=== EXAMPLE 1: Basic Usage ===\n")
    
    # Initialize tracker
    tracker = LinkedInJobTracker()
    
    # Add some job searches
    print(Fore.YELLOW + "Adding job searches...")
    tracker.add_search_query("Python Developer", "Remote", "Full-time")
    tracker.add_search_query("Data Scientist", "San Francisco")
    tracker.add_search_query("Machine Learning Engineer", "United States", "Contract")
    
    # List active searches
    print(Fore.YELLOW + "\nActive searches:")
    tracker.list_search_queries()
    
    # Check for new jobs (one-time check)
    print(Fore.YELLOW + "Checking for new jobs...")
    new_jobs = tracker.check_for_new_jobs()
    
    if new_jobs:
        tracker.notify_new_jobs(new_jobs)
    else:
        print(Fore.WHITE + "No new jobs found.")
    
    # Show statistics
    tracker.get_statistics()


def example_continuous_monitoring():
    """Example of continuous monitoring (runs for 5 minutes)"""
    print(Fore.CYAN + Style.BRIGHT + "\n=== EXAMPLE 2: Continuous Monitoring ===\n")
    
    tracker = LinkedInJobTracker()
    
    # Add searches
    tracker.add_search_query("Software Engineer", "New York")
    tracker.add_search_query("DevOps Engineer", "Remote")
    
    print(Fore.GREEN + "Starting 5-minute monitoring demo...")
    print(Fore.YELLOW + "Press Ctrl+C to stop early\n")
    
    try:
        end_time = time.time() + 300  # Run for 5 minutes
        check_count = 0
        
        while time.time() < end_time:
            check_count += 1
            print(Fore.CYAN + f"\nCheck #{check_count} - Scanning...")
            
            new_jobs = tracker.check_for_new_jobs()
            
            if new_jobs:
                tracker.notify_new_jobs(new_jobs)
            else:
                print(Fore.WHITE + "No new jobs. Next check in 60 seconds...")
            
            time.sleep(60)  # Wait 1 minute
        
        print(Fore.GREEN + "\n5-minute demo completed!")
        tracker.get_statistics()
        
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\nMonitoring stopped by user")
        tracker.get_statistics()


def example_custom_notification():
    """Example with custom notification callback"""
    print(Fore.CYAN + Style.BRIGHT + "\n=== EXAMPLE 3: Custom Notifications ===\n")
    
    tracker = LinkedInJobTracker()
    
    # Define custom notification function
    def custom_alert(job):
        """Custom notification - could send email, SMS, Slack message, etc."""
        print(Fore.MAGENTA + Style.BRIGHT + f"\n🔔 CUSTOM ALERT: New {job.get('title')} position!")
        print(Fore.WHITE + f"   Company: {job.get('company')}")
        print(Fore.WHITE + f"   Location: {job.get('location')}")
        # Here you could add:
        # - send_email(job)
        # - send_sms(job)
        # - post_to_slack(job)
        # - etc.
    
    # Set custom callback
    tracker.notification_callback = custom_alert
    
    # Add search and check
    tracker.add_search_query("Full Stack Developer", "Remote")
    new_jobs = tracker.check_for_new_jobs()
    
    if new_jobs:
        tracker.notify_new_jobs(new_jobs)  # Will trigger custom_alert for each job
    else:
        print(Fore.WHITE + "No new jobs found.")


def example_manage_searches():
    """Example of managing search queries"""
    print(Fore.CYAN + Style.BRIGHT + "\n=== EXAMPLE 4: Managing Searches ===\n")
    
    tracker = LinkedInJobTracker()
    
    # Add several searches
    print(Fore.YELLOW + "Adding searches...")
    tracker.add_search_query("Backend Developer", "Seattle")
    tracker.add_search_query("Frontend Developer", "Seattle")
    tracker.add_search_query("QA Engineer", "Seattle")
    
    # List them
    print(Fore.YELLOW + "\nAll searches:")
    tracker.list_search_queries()
    
    # Remove one
    print(Fore.YELLOW + "Removing search #2...")
    tracker.remove_search_query(1)  # Index 1 = second item
    
    # List again
    print(Fore.YELLOW + "\nUpdated searches:")
    tracker.list_search_queries()
    
    # Clear cache
    print(Fore.YELLOW + "\nClearing cache...")
    tracker.clear_cache()
    
    # Show stats
    tracker.get_statistics()


def main():
    """Run all examples"""
    print(Fore.CYAN + Style.BRIGHT + """
    ╔═══════════════════════════════════════════════╗
    ║  LinkedIn Job Tracker - Usage Examples       ║
    ╚═══════════════════════════════════════════════╝
    """)
    
    print(Fore.WHITE + "Choose an example to run:")
    print(Fore.GREEN + "1. Basic Usage (quick demo)")
    print(Fore.GREEN + "2. Continuous Monitoring (5 minutes)")
    print(Fore.GREEN + "3. Custom Notifications")
    print(Fore.GREEN + "4. Managing Searches")
    print(Fore.GREEN + "5. Run All Examples")
    print(Fore.RED + "0. Exit")
    
    choice = input(Fore.YELLOW + "\nEnter choice (0-5): " + Fore.WHITE).strip()
    
    if choice == "1":
        example_basic_usage()
    elif choice == "2":
        example_continuous_monitoring()
    elif choice == "3":
        example_custom_notification()
    elif choice == "4":
        example_manage_searches()
    elif choice == "5":
        example_basic_usage()
        example_custom_notification()
        example_manage_searches()
        # Skip continuous monitoring in "run all" mode
    elif choice == "0":
        print(Fore.YELLOW + "Goodbye!")
    else:
        print(Fore.RED + "Invalid choice!")
    
    print(Fore.CYAN + "\n" + "=" * 50)
    print(Fore.GREEN + "Example completed!")
    print(Fore.WHITE + "For full SCOUT experience, run: python scout_with_linkedin.py")
    print(Fore.CYAN + "=" * 50 + "\n")


if __name__ == "__main__":
    main()
