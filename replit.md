# replit.md

## Overview

This is a fantasy football analytics application that scrapes player projections from multiple sources and integrates with the Sleeper fantasy football API. The system fetches weekly player projections, combines data from various fantasy football websites, and provides tools to analyze fantasy league data including rosters, matchups, and user information.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Application Structure
- **main.py**: Entry point for Sleeper API integration, handles league data retrieval including users, rosters, and matchups
- **projections.py**: CSV-based projection data handler with pandas for data processing and analysis
- **weekly_scraper.py**: Multi-source web scraping engine for collecting player projections from fantasy football websites
- **schedule_scraper.py**: Automated scheduler using the `schedule` library to run weekly data collection every Thursday at 8:00 AM

### Data Collection Strategy
The system uses a multi-source approach to gather fantasy football data:
- **Primary Data Source**: Sleeper API for real-time league information
- **Projection Sources**: Web scraping from FantasyPros, ESPN Fantasy, The Athletic, and other fantasy football sites
- **Data Validation**: Pandas-based data cleaning with error handling for malformed data

### Scheduling and Automation
- Automated weekly data collection scheduled for Thursday mornings (typical waiver wire day)
- Manual execution capabilities for testing and immediate data updates
- Error handling and logging for failed scraping attempts

### Data Storage Approach
- CSV-based storage for projection data (projections.csv, projections_combined.csv)
- Historical data preservation in dedicated history directory
- Fallback data mechanisms to ensure system reliability

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