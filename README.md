# Restaurant Reservation Monitor

Automatically checks Resy and OpenTable every 10 minutes and emails you when
a table opens up at one of your watched restaurants.

---

## What you'll need before starting

- Python 3.10 or newer — download at https://www.python.org/downloads/
- A Resy account (resy.com) and/or an OpenTable account (opentable.com)
- A Gmail account with an App Password set up (instructions below)

---

## Step 1 — Install Python dependencies

Open **Terminal** (Mac/Linux) or **Command Prompt** (Windows), navigate to
this folder, then run:

```
pip install -r requirements.txt
```

---

## Step 2 — Create your configuration file

1. In this folder, find the file called `config.env.example`
2. Make a copy of it and name the copy exactly: `config.env`
3. Open `config.env` in any text editor (Notepad is fine)
4. Fill in each value — instructions for each are below

### Resy credentials
Your Resy email and password — the same ones you use to log in at resy.com.

### OpenTable credentials
Your OpenTable email and password. Leave blank if you only use Resy.

### Gmail (for email alerts)

The monitor sends alerts using Gmail's SMTP server. You'll need a Gmail App
Password — this is a separate password Gmail generates for apps, distinct from
your regular Gmail password.

1. Make sure your Gmail account has **2-Step Verification** enabled:
   Google Account → Security → 2-Step Verification
2. Go to https://myaccount.google.com/apppasswords
3. Under "App name", type something like `Restaurant Monitor`, then click **Create**
4. Copy the 16-character password shown (formatted as `xxxx xxxx xxxx xxxx`)
5. In `config.env`, fill in:
   - `GMAIL_ADDRESS` — your Gmail address (e.g. `you@gmail.com`)
   - `GMAIL_APP_PASSWORD` — the 16-character App Password from step 4
   - `ALERT_EMAIL_TO` — the email address that receives alerts (can be the same as `GMAIL_ADDRESS`, or any other address)

---

## Step 3 — Set up your watchlist

Open `watchlist.csv` in any text editor or spreadsheet app (Excel, Google Sheets).

Each row is one restaurant to monitor. The columns are:

| Column       | Description                                         | Example                                             |
|--------------|-----------------------------------------------------|-----------------------------------------------------|
| `name`       | Any label you want (used in your email alert)       | Le Bernardin                                        |
| `platform`   | Either `resy` or `opentable` (lowercase)            | resy                                                |
| `url`        | The restaurant's URL on Resy or OpenTable           | https://resy.com/cities/ny/venues/le-bernardin      |
| `date`       | The date you want, in YYYY-MM-DD format             | 2026-03-15                                          |
| `party_size` | Number of people                                    | 2                                                   |
| `time_start` | Start of your preferred time window (HH:MM, 24hr)  | 18:00                                               |
| `time_end`   | End of your preferred time window (HH:MM, 24hr)    | 20:00                                               |

### How to find the URL

**Resy:** Go to resy.com, search for the restaurant, open its page.
Copy the URL from your browser's address bar.
It will look like: `https://resy.com/cities/ny/venues/restaurant-name`

**OpenTable:** Go to opentable.com, search for the restaurant, open its page.
Copy the URL from your browser's address bar.
It will look like: `https://www.opentable.com/restaurant-name`
or: `https://www.opentable.com/restaurant/profile/12345`

### Example watchlist

```
name,platform,url,date,party_size,time_start,time_end
Le Bernardin,resy,https://resy.com/cities/ny/venues/le-bernardin,2026-03-15,2,18:00,20:00
Nobu Downtown,opentable,https://www.opentable.com/nobu-downtown,2026-03-20,4,19:00,21:00
```

You can add as many rows as you like. To stop monitoring a restaurant,
just delete its row (or add a `#` at the start of the line to comment it out).

---

## Step 4 — Run the monitor

In Terminal / Command Prompt, from inside this folder, run:

```
python monitor.py
```

You'll see it start checking immediately. Every 10 minutes it checks again.
When a table opens up in your time window, you'll get an email like:

```
Subject: Table available!

Table available!
Le Bernardin
2026-03-15 at 19:00
Party of 2
Book now: https://resy.com/cities/ny/venues/le-bernardin?date=2026-03-15&seats=2
```

To stop the monitor, press **Ctrl+C**.

---

## Keeping it running

The monitor only runs while the Terminal window is open. To keep it running
in the background (so you can close the Terminal), you have a few options:

**Mac/Linux:** Run it with `nohup`:
```
nohup python monitor.py &
```
To stop it later: `pkill -f monitor.py`

**Windows:** Right-click `monitor.py` → Open With → Python (or create a
`.bat` file that runs it), then minimize the window.

---

## Troubleshooting

**"config.env not found"**
Make sure you copied `config.env.example` to a new file named `config.env`
(not `config.env.txt`). On Windows, make sure file extensions are visible
in File Explorer.

**"Cannot parse Resy URL"**
Check that the URL in your watchlist follows the format:
`https://resy.com/cities/ny/venues/restaurant-slug`

**"Could not find restaurant ID" (OpenTable)**
Try using the direct profile URL. Go to the restaurant's OpenTable page and
look for a URL that contains `/restaurant/profile/` followed by a number.

**No emails arriving**
- Check your spam folder
- Confirm `ALERT_EMAIL_TO` is set correctly in `config.env`
- Make sure you used a Gmail **App Password** (not your regular Gmail password)
- Look at the terminal output — it shows what the monitor found and whether
  an email was sent

**API errors**
Both Resy and OpenTable use unofficial/undocumented APIs. Occasionally these
may change or become temporarily unavailable. The monitor will log the error
and continue checking other restaurants.

---

## File overview

```
restaurant-monitor/
├── monitor.py          ← The main program (run this)
├── requirements.txt    ← Python dependencies
├── config.env.example  ← Configuration template
├── config.env          ← Your actual credentials (you create this)
├── watchlist.csv       ← Your restaurant watchlist (edit this)
└── README.md           ← This file
```

The monitor also creates a hidden file `.notified.json` to track which
alerts it has already sent, so you don't get the same email repeatedly.
