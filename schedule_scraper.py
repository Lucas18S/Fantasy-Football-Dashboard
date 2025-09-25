import schedule
import time
from datetime import datetime
import sys
import os

# Add the current directory to the path to import weekly_scraper
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from weekly_scraper import get_all_projections

def run_weekly_scrape():
    """Run the weekly scraper and log the execution"""
    print(f"🕐 Running weekly scrape at {datetime.now()}")
    try:
        get_all_projections()
        print("✅ Weekly scrape completed successfully")
    except Exception as e:
        print(f"❌ Weekly scrape failed: {e}")

def main():
    """Schedule the scraper to run every Thursday at 8:00 AM"""
    # Schedule the job for every Thursday at 8:00 AM
    schedule.every().thursday.at("08:00").do(run_weekly_scrape)
    
    print("📅 Scheduler started - will run every Thursday at 8:00 AM")
    print("🔄 Next run:", schedule.next_run())
    
    # Run immediately for testing (optional)
    print("🧪 Running initial test...")
    run_weekly_scrape()
    
    # Keep the scheduler running
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    main()