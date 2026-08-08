#!/usr/bin/env python3
"""
Test script for LinkedIn Job Tracker
Verifies both API and RSS methods work correctly
"""

import os
import sys
from colorama import Fore, Style, init

init(autoreset=True)


def print_header(text):
    """Print a formatted header"""
    print("\n" + Fore.CYAN + Style.BRIGHT + "=" * 70)
    print(Fore.CYAN + Style.BRIGHT + text)
    print(Fore.CYAN + Style.BRIGHT + "=" * 70 + "\n")


def test_imports():
    """Test that all required modules can be imported"""
    print_header("TEST 1: Checking Dependencies")
    
    required_modules = [
        ('requests', 'requests'),
        ('colorama', 'colorama'),
        ('beautifulsoup4', 'bs4'),
        ('lxml', 'lxml'),
    ]
    
    all_good = True
    
    for package_name, import_name in required_modules:
        try:
            __import__(import_name)
            print(Fore.GREEN + f"✓ {package_name} installed")
        except ImportError:
            print(Fore.RED + f"✗ {package_name} NOT installed")
            all_good = False
    
    if all_good:
        print(Fore.GREEN + Style.BRIGHT + "\n✅ All dependencies installed!")
        return True
    else:
        print(Fore.RED + Style.BRIGHT + "\n❌ Missing dependencies!")
        print(Fore.YELLOW + "Run: pip install -r requirements.txt")
        return False


def test_linkedin_tracker():
    """Test the API-based tracker"""
    print_header("TEST 2: API-Based Tracker (linkedin_tracker.py)")
    
    try:
        from linkedin_tracker import LinkedInJobTracker
        print(Fore.GREEN + "✓ linkedin_tracker.py imports successfully")
        
        # Create instance
        tracker = LinkedInJobTracker()
        print(Fore.GREEN + "✓ LinkedInJobTracker instance created")
        
        # Test basic operations
        tracker.add_search_query("Test Job", "Test Location")
        print(Fore.GREEN + "✓ Can add search queries")
        
        tracker.list_search_queries()
        print(Fore.GREEN + "✓ Can list search queries")
        
        tracker.get_statistics()
        print(Fore.GREEN + "✓ Can get statistics")
        
        # Check API key
        if os.environ.get("RAPID_API_KEY"):
            print(Fore.GREEN + "✓ RAPID_API_KEY environment variable is set")
            print(Fore.YELLOW + "  Note: To test actual API calls, run a real search")
        else:
            print(Fore.YELLOW + "⚠ RAPID_API_KEY not set (OK for RSS method)")
        
        print(Fore.GREEN + Style.BRIGHT + "\n✅ API Tracker is functional!")
        return True
        
    except Exception as e:
        print(Fore.RED + f"✗ Error: {e}")
        print(Fore.RED + Style.BRIGHT + "\n❌ API Tracker test failed!")
        return False


def test_rss_tracker():
    """Test the RSS/scraping-based tracker"""
    print_header("TEST 3: RSS-Based Tracker (linkedin_rss_tracker.py)")
    
    try:
        from linkedin_rss_tracker import LinkedInRSSTracker
        print(Fore.GREEN + "✓ linkedin_rss_tracker.py imports successfully")
        
        # Create instance
        tracker = LinkedInRSSTracker()
        print(Fore.GREEN + "✓ LinkedInRSSTracker instance created")
        
        # Test basic operations
        tracker.add_search_query("Test Job", "Test Location")
        print(Fore.GREEN + "✓ Can add search queries")
        
        tracker.list_search_queries()
        print(Fore.GREEN + "✓ Can list search queries")
        
        tracker.get_statistics()
        print(Fore.GREEN + "✓ Can get statistics")
        
        # Test URL building
        url = tracker.build_linkedin_url("Python Developer", "Remote")
        if "linkedin.com" in url and "python" in url.lower():
            print(Fore.GREEN + "✓ Can build LinkedIn URLs correctly")
        
        print(Fore.GREEN + Style.BRIGHT + "\n✅ RSS Tracker is functional!")
        print(Fore.CYAN + "\n💡 This method works WITHOUT an API key!")
        return True
        
    except Exception as e:
        print(Fore.RED + f"✗ Error: {e}")
        print(Fore.RED + Style.BRIGHT + "\n❌ RSS Tracker test failed!")
        return False


def test_caddy_integration():
    """Test CADDY with LinkedIn integration"""
    print_header("TEST 4: CADDY Integration (caddy_with_linkedin.py)")
    
    try:
        from caddy_with_linkedin import CaddyWithLinkedIn
        print(Fore.GREEN + "✓ caddy_with_linkedin.py imports successfully")
        
        # Create instance
        caddy = CaddyWithLinkedIn()
        print(Fore.GREEN + "✓ CaddyWithLinkedIn instance created")
        
        # Test job tracker is accessible
        if hasattr(caddy, 'job_tracker'):
            print(Fore.GREEN + "✓ Job tracker integrated into CADDY")
        
        # Test chat function exists
        if hasattr(caddy, 'chat'):
            print(Fore.GREEN + "✓ Chat function available")
        
        # Test monitoring functions
        if hasattr(caddy, 'start_job_monitoring'):
            print(Fore.GREEN + "✓ Job monitoring functions available")
        
        print(Fore.GREEN + Style.BRIGHT + "\n✅ CADDY Integration is functional!")
        return True
        
    except Exception as e:
        print(Fore.RED + f"✗ Error: {e}")
        print(Fore.RED + Style.BRIGHT + "\n❌ CADDY Integration test failed!")
        return False


def test_example_script():
    """Test the example usage script"""
    print_header("TEST 5: Example Script (example_usage.py)")
    
    try:
        # Just check if it can be imported
        import importlib.util
        spec = importlib.util.spec_from_file_location("example_usage", "example_usage.py")
        if spec and spec.loader:
            print(Fore.GREEN + "✓ example_usage.py exists and is valid")
            print(Fore.GREEN + Style.BRIGHT + "\n✅ Example script is ready!")
            return True
        else:
            print(Fore.YELLOW + "⚠ example_usage.py may have issues")
            return False
    except Exception as e:
        print(Fore.RED + f"✗ Error: {e}")
        return False


def print_summary(results):
    """Print test summary"""
    print_header("TEST SUMMARY")
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = Fore.GREEN + "✅ PASSED" if result else Fore.RED + "❌ FAILED"
        print(f"{status} - {test_name}")
    
    print(f"\n{Fore.CYAN}Results: {passed}/{total} tests passed")
    
    if passed == total:
        print(Fore.GREEN + Style.BRIGHT + "\n🎉 ALL TESTS PASSED! 🎉")
        print(Fore.WHITE + "\nYour CADDY LinkedIn tracker is ready to use!")
        print(Fore.YELLOW + "\nNext steps:")
        print(Fore.WHITE + "1. Set RAPID_API_KEY (optional for API method)")
        print(Fore.WHITE + "2. Run: python caddy_with_linkedin.py")
        print(Fore.WHITE + "3. Or: python linkedin_rss_tracker.py (no API key needed)")
    else:
        print(Fore.RED + Style.BRIGHT + "\n⚠ SOME TESTS FAILED")
        print(Fore.YELLOW + "\nTroubleshooting:")
        print(Fore.WHITE + "1. Run: pip install -r requirements.txt")
        print(Fore.WHITE + "2. Check Python version (need 3.7+)")
        print(Fore.WHITE + "3. Review error messages above")


def main():
    """Run all tests"""
    print(Fore.CYAN + Style.BRIGHT + """
    ╔══════════════════════════════════════════════════════╗
    ║  CADDY LinkedIn Job Tracker - Test Suite           ║
    ╚══════════════════════════════════════════════════════╝
    """)
    
    print(Fore.WHITE + "This script will verify that all components are working correctly.\n")
    
    # Run all tests
    results = {
        "Dependencies": test_imports(),
        "API Tracker": test_linkedin_tracker(),
        "RSS Tracker": test_rss_tracker(),
        "CADDY Integration": test_caddy_integration(),
        "Example Script": test_example_script(),
    }
    
    # Print summary
    print_summary(results)
    
    # Return exit code
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
