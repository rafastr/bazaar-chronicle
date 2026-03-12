# Bazaar Chronicles

Bazaar Chronicles is a local run tracker for **The Bazaar** that records your runs, analyzes performance, and tracks achievements and item mastery.

The application runs locally on your machine and stores all data in a SQLite database. No external services are required.

---

## Features

### Run tracking
- Record runs automatically from game logs
- Saves screenshots when run ends
- Manually add or edit runs
- OCR support for extracting run data

### Board tracking
- Record final board items
- Board editor

### Statistics dashboard
- Rank evolution graph
- Win/loss history
- Hero performance stats

### Achievements
- Collection of achievements

### Item mastery
Track progress toward:

- Using every item in a win
- Using item with other heroes in a win

### Fully local
- SQLite database
- Local image cache
- No external accounts required
- Works offline

---

## Screenshots

*(Add screenshots here later)*

Dashboard  
Runs  
Items  
Achievements  

---

## Installation

### Requirements

- Python 3.11+
- pip

### Clone repository

```bash
git clone https://github.com/YOURNAME/bazaar-tracker.git
cd bazaar-tracker

Install dependencies

pip install -r requirements.txt

Run the application
python -m web.app

Open in browser:

http://127.0.0.1:5000
```


