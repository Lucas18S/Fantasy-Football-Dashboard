# replit.md

## Overview

This is a **multi-user fantasy football dashboard** that provides week-specific start/sit advice using real-time projections from ESPN and Sleeper APIs. The system fetches matchup-adjusted weekly player projections and provides personalized recommendations based on users' Sleeper league rosters.

**Key Feature**: Users enter their own Sleeper League ID to get personalized advice for their specific league and roster.

## User Preferences

Preferred communication style: Simple, everyday language.

## Multi-User Setup

The dashboard is designed to be shared with friends and other fantasy football managers. Each user inputs their own Sleeper League ID through the sidebar to access their personal league data.

## System Architecture

### Core Application Structure
- **main.py**: Entry point for Sleeper API integration, handles league data retrieval including users, rosters, and matchups
- **projections.py**: CSV-based projection data handler with pandas for data processing and analysis
- **weekly_scraper.py**: Multi-source web scraping engine for collecting player projections from fantasy football websites
- **schedule_scraper.py**: Automated scheduler using the `schedule` library to run weekly data collection every Thursday at 8:00 AM

### Data Collection Strategy
The system uses a multi-source API approach to gather fantasy football data:
- **League Data**: User-specific Sleeper API data (roster, matchups, league settings)
- **Projection Sources**: 
  - ESPN API: Week-specific matchup-adjusted projections
  - Sleeper API: Weekly projections calculated with league-specific scoring settings
- **Data Validation**: Pandas-based data cleaning with error handling
- **No Hardcoded Data**: All league-specific data comes from user input (League IDs)

### Scheduling and Automation
- Automated weekly data collection scheduled for Thursday mornings (typical waiver wire day)
- Manual execution capabilities for testing and immediate data updates
- Error handling and logging for failed scraping attempts

### Data Storage Approach
- CSV-based storage for universal projection data (projections_combined.csv)
- Historical data preservation in dedicated history directory
- Fallback data mechanisms to ensure system reliability
- **No User Data Storage**: League data is fetched fresh per session via API calls
- **Privacy**: User league IDs are not stored or logged

### Error Handling and Reliability
- Multiple data source fallbacks to prevent single point of failure
- Data validation and cleaning to handle inconsistent web scraping results
- Graceful degradation when individual scraping sources fail

## External Dependencies

### APIs and Web Services
- **Sleeper API**: Primary fantasy football league data source for users, rosters, and matchups
- **FantasyPros**: Web scraping target for consensus player rankings
- **ESPN Fantasy**: Secondary projection source
- **The Athletic**: Additional fantasy football projections

### Python Libraries
- **requests**: HTTP client for API calls and web scraping
- **pandas**: Data manipulation and CSV processing
- **BeautifulSoup4**: HTML parsing for web scraping
- **schedule**: Task scheduling for automated data collection
- **datetime**: Time-based operations and logging

### Data Dependencies
- **projections.csv**: Local CSV file containing player projection data
- **history/** directory: Stores historical projection data for trend analysis