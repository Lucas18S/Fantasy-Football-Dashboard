import os
import sys
import time
import argparse
from datetime import datetime
import schedule

# Ensure current directory is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(SCRIPT_DIR)

from weekly_scraper import run_pipeline

LOG_FILE = os.path.join(SCRIPT_DIR, "scraper.log")

def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

def run_daily_scrape(reason: str = "Scheduled daily run"):
    """Run weekly_scraper pipeline and sync to Google Drive."""
    log(f"🚀 Starting daily projections scrape ({reason})...")
    start_t = time.time()
    try:
        run_pipeline()
        duration = time.time() - start_t
        log(f"✅ Projections scrape completed successfully in {duration:.1f}s.")
        
        # Trigger Google Drive sync
        log("☁️ Triggering Google Drive cloud backup...")
        try:
            import sync_to_gdrive
            sync_to_gdrive.sync_project_to_gdrive()
            log("✅ Cloud backup sync complete.")
        except Exception as e_sync:
            log(f"⚠️ Google Drive sync encountered an issue: {e_sync}")
            
    except Exception as e:
        log(f"❌ Scraper pipeline failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="Automated Fantasy Football Projections Scraper")
    parser.add_argument("--run-now", "-n", action="store_true", help="Execute scraper immediately and exit")
    parser.add_argument("--force", "-f", action="store_true", help="Force scrape execution")
    args = parser.parse_args()

    if args.run_now or args.force:
        run_daily_scrape(reason="Immediate CLI trigger (--run-now)")
        return

    log("📅 Starting Daily Fantasy Football Scraper Daemon...")
    
    # Daily morning update (Every day at 7:00 AM)
    schedule.every().day.at("07:00").do(run_daily_scrape, reason="Daily 07:00 AM morning cycle")
    
    # Thursday midday update (Prior to Thursday Night Football)
    schedule.every().thursday.at("12:00").do(run_daily_scrape, reason="Thursday 12:00 PM TNF cycle")
    
    # Sunday morning gameday update (Prior to 1:00 PM kickoff inactives)
    schedule.every().sunday.at("09:30").do(run_daily_scrape, reason="Sunday 09:30 AM Gameday inactives cycle")
    
    # Tuesday morning post-MNF update (Ingest latest box scores for backtesting)
    schedule.every().tuesday.at("07:30").do(run_daily_scrape, reason="Tuesday 07:30 AM Post-MNF box scores cycle")

    log("⏰ Configured Schedule:")
    log("   • Daily: 07:00 AM")
    log("   • Tuesday (Post-MNF Box Scores): 07:30 AM")
    log("   • Thursday (TNF Prep): 12:00 PM")
    log("   • Sunday (Gameday Inactives): 09:30 AM")
    log(f"🔄 Next scheduled run: {schedule.next_run()}")

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main()
