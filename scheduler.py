import schedule
import time
from weekly_scraper import get_all_projections

def job():
    print("🕐 Running scheduled scraper...")
    get_all_projections()
    print("✅ Scheduled run complete!")

# Schedule for Thursday at noon (12:00 PM)
schedule.every().thursday.at("12:00").do(job)

print("📅 Scheduler started. Waiting for Thursday at noon...")
print("   (Runs continuously - keep Replit always-on)")

while True:
    schedule.run_pending()
    time.sleep(60)  # Check every minute
