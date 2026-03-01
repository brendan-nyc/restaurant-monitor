#!/usr/bin/env python3
"""
Restaurant Reservation Monitor — Web UI
========================================
Runs the Flask web interface on http://localhost:5000 and starts the background
availability monitor in a daemon thread.

Usage:  python app.py
"""

import os
import threading
import time

import schedule
from flask import Flask, redirect, render_template_string, request, url_for

from database import (
    init_db,
    get_all_restaurants,
    get_restaurant,
    add_restaurant,
    update_restaurant,
    delete_restaurant,
)
from monitor import CHECK_INTERVAL, check_all

app = Flask(__name__)

TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Restaurant Monitor</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #f5f5f5; color: #222; padding: 2rem; }
    h1 { margin-bottom: 0.25rem; font-size: 1.5rem; }
    .subtitle { color: #666; margin-bottom: 2rem; font-size: 0.9rem; }
    .status-bar { background: #e8f4fd; border: 1px solid #b3d9f5; border-radius: 6px;
                  padding: 0.6rem 1rem; margin-bottom: 1.5rem; font-size: 0.875rem; color: #1a5a8a; }
    .card { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; }
    h2 { font-size: 1.1rem; margin-bottom: 1rem; }
    table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
    th { text-align: left; padding: 0.5rem 0.75rem; background: #f0f0f0;
         border-bottom: 2px solid #ddd; white-space: nowrap; }
    td { padding: 0.5rem 0.75rem; border-bottom: 1px solid #eee; vertical-align: middle; }
    tr:last-child td { border-bottom: none; }
    .empty { color: #999; font-style: italic; padding: 0.75rem 0; }
.btn { display: inline-block; padding: 0.4rem 0.9rem; border: none; border-radius: 5px;
           cursor: pointer; font-size: 0.85rem; font-weight: 500; text-decoration: none; }
    .btn-danger { background: #e53e3e; color: #fff; }
    .btn-danger:hover { background: #c53030; }
    .btn-primary { background: #2b6cb0; color: #fff; padding: 0.5rem 1.2rem; font-size: 0.95rem; }
    .btn-primary:hover { background: #2c5282; }
    .btn-secondary { background: #718096; color: #fff; }
    .btn-secondary:hover { background: #4a5568; }
    .btn-warning { background: #d69e2e; color: #fff; }
    .btn-warning:hover { background: #b7791f; }
    form.inline { display: inline; }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem 1.25rem; }
    @media (max-width: 600px) { .form-grid { grid-template-columns: 1fr; } }
    .field label { display: block; font-size: 0.8rem; font-weight: 600;
                   color: #555; margin-bottom: 0.25rem; }
    .field input, .field select { width: 100%; padding: 0.4rem 0.6rem; border: 1px solid #ccc;
                                   border-radius: 5px; font-size: 0.9rem; }
    .field input:focus, .field select:focus { outline: 2px solid #2b6cb0; border-color: transparent; }
    .form-actions { margin-top: 1rem; display: flex; gap: 0.75rem; align-items: center; }
    .platform-resy    { background: #f6ad55; color: #7b341e; padding: 2px 7px;
                        border-radius: 4px; font-size: 0.8rem; font-weight: 600; }
    .platform-opentable { background: #68d391; color: #1c4532; padding: 2px 7px;
                           border-radius: 4px; font-size: 0.8rem; font-weight: 600; }
    .schedule-toggle { display: flex; gap: 1.5rem; margin-top: 0.25rem; }
    .schedule-toggle label { display: flex; align-items: center; gap: 0.4rem;
                              cursor: pointer; font-weight: normal; color: #222; }
    .day-checks { display: flex; gap: 0.4rem; flex-wrap: wrap; margin-top: 0.25rem; }
    .day-checks label { display: flex; align-items: center; gap: 0.3rem; background: #f0f0f0;
                        padding: 0.3rem 0.65rem; border-radius: 4px; cursor: pointer;
                        font-size: 0.85rem; font-weight: normal; color: #222; }
  </style>
</head>
<body>
  <h1>Restaurant Reservation Monitor</h1>
  <p class="subtitle">Checks Resy &amp; OpenTable every {{ interval }} minutes and emails you when a table opens up.</p>

  <div class="status-bar">
    Next scheduled check: <strong>{{ next_run }}</strong>
    &nbsp;&nbsp;|&nbsp;&nbsp;
    <form class="inline" method="post" action="/check">
      <button class="btn btn-secondary" style="padding:0.2rem 0.8rem;font-size:0.8rem;">Check Now</button>
    </form>
  </div>

  <!-- Watchlist table -->
  <div class="card">
    <h2>Watchlist ({{ restaurants|length }} restaurant{{ 's' if restaurants|length != 1 }})</h2>
    {% if restaurants %}
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Name</th>
          <th>Platform</th>
          <th>Schedule</th>
          <th>Party</th>
          <th>Time Window</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for r in restaurants %}
        <tr>
          <td>{{ loop.index }}</td>
          <td>{{ r.name }}</td>
          <td><span class="platform-{{ r.platform }}">{{ r.platform }}</span></td>
          <td>{% if r.days_of_week %}{{ r.days_of_week|replace(',',', ')|title }} · {{ r.look_ahead_days }}d{% else %}{{ r.date }}{% endif %}</td>
          <td>{{ r.party_size }}</td>
          <td>{{ r.time_start }} – {{ r.time_end }}</td>
          <td style="white-space:nowrap;">
            <a class="btn btn-primary" href="{{ r.url }}" target="_blank" rel="noopener">Book</a>
            <a class="btn btn-warning" href="/edit/{{ r.id }}">Edit</a>
            <form class="inline" method="post" action="/delete/{{ r.id }}"
                  onsubmit="return confirm('Remove {{ r.name }}?')">
              <button class="btn btn-danger">Delete</button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <p class="empty">No restaurants on the watchlist yet. Add one below.</p>
    {% endif %}
  </div>

  {% if edit_row %}
  <!-- Edit restaurant form -->
  <div class="card" id="edit-form" style="border-color:#d69e2e;">
    <h2>Edit Restaurant</h2>
    {% set is_rec = edit_row.days_of_week %}
    <form method="post" action="/edit/{{ edit_rid }}">
      <div class="form-grid">
        <div class="field">
          <label>Name</label>
          <input name="name" type="text" value="{{ edit_row.name }}" required>
        </div>
        <div class="field">
          <label>Platform</label>
          <select name="platform" required>
            <option value="resy" {{ 'selected' if edit_row.platform == 'resy' }}>Resy</option>
            <option value="opentable" {{ 'selected' if edit_row.platform == 'opentable' }}>OpenTable</option>
          </select>
        </div>
        <div class="field" style="grid-column: 1 / -1;">
          <label>Schedule</label>
          <div class="schedule-toggle">
            <label><input type="radio" name="schedule_type" value="specific" {{ 'checked' if not is_rec }} onchange="updateSchedule(this.closest('form'))"> Specific date</label>
            <label><input type="radio" name="schedule_type" value="recurring" {{ 'checked' if is_rec }} onchange="updateSchedule(this.closest('form'))"> Recurring</label>
          </div>
        </div>
        <div class="field specific-date-field">
          <label>Date</label>
          <input name="date" type="date" value="{{ edit_row.date or '' }}">
        </div>
        <div class="field recurring-fields" style="grid-column: 1 / -1;">
          <label>Days of week</label>
          <div class="day-checks">
            {% for abbr, label in [('mon','Mon'),('tue','Tue'),('wed','Wed'),('thu','Thu'),('fri','Fri'),('sat','Sat'),('sun','Sun')] %}
            <label><input type="checkbox" name="days_of_week" value="{{ abbr }}" {{ 'checked' if is_rec and abbr in edit_row.days_of_week }}> {{ label }}</label>
            {% endfor %}
          </div>
        </div>
        <div class="field recurring-fields">
          <label>Look-ahead (days)</label>
          <input name="look_ahead_days" type="number" min="1" max="90" value="{{ edit_row.look_ahead_days or 45 }}">
        </div>
        <div class="field">
          <label>Party Size</label>
          <input name="party_size" type="number" min="1" max="20" value="{{ edit_row.party_size }}" required>
        </div>
        <div class="field">
          <label>Earliest Time (HH:MM)</label>
          <input name="time_start" type="time" value="{{ edit_row.time_start }}" required>
        </div>
        <div class="field">
          <label>Latest Time (HH:MM)</label>
          <input name="time_end" type="time" value="{{ edit_row.time_end }}" required>
        </div>
        <div class="field" style="grid-column: 1 / -1;">
          <label>Restaurant URL</label>
          <input name="url" type="url" value="{{ edit_row.url }}" required>
        </div>
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" type="submit">Save Changes</button>
        <a class="btn btn-secondary" href="/">Cancel</a>
      </div>
    </form>
  </div>
  <script>
    function updateSchedule(form) {
      var recurring = form.querySelector('input[name="schedule_type"]:checked').value === 'recurring';
      form.querySelectorAll('.specific-date-field').forEach(function(el) { el.style.display = recurring ? 'none' : ''; });
      form.querySelectorAll('.recurring-fields').forEach(function(el) { el.style.display = recurring ? '' : 'none'; });
    }
    document.querySelectorAll('form').forEach(function(f) {
      if (f.querySelector('input[name="schedule_type"]')) updateSchedule(f);
    });
    document.getElementById('edit-form').scrollIntoView({behavior:'smooth'});
  </script>
  {% else %}
  <!-- Add restaurant form -->
  <div class="card">
    <h2>Add Restaurant</h2>
    <form method="post" action="/add">
      <div class="form-grid">
        <div class="field">
          <label>Name</label>
          <input name="name" type="text" placeholder="e.g. Odeon" required>
        </div>
        <div class="field">
          <label>Platform</label>
          <select name="platform" required>
            <option value="resy">Resy</option>
            <option value="opentable">OpenTable</option>
          </select>
        </div>
        <div class="field" style="grid-column: 1 / -1;">
          <label>Schedule</label>
          <div class="schedule-toggle">
            <label><input type="radio" name="schedule_type" value="specific" checked onchange="updateSchedule(this.closest('form'))"> Specific date</label>
            <label><input type="radio" name="schedule_type" value="recurring" onchange="updateSchedule(this.closest('form'))"> Recurring</label>
          </div>
        </div>
        <div class="field specific-date-field">
          <label>Date</label>
          <input name="date" type="date">
        </div>
        <div class="field recurring-fields" style="grid-column: 1 / -1; display:none;">
          <label>Days of week</label>
          <div class="day-checks">
            {% for abbr, label in [('mon','Mon'),('tue','Tue'),('wed','Wed'),('thu','Thu'),('fri','Fri'),('sat','Sat'),('sun','Sun')] %}
            <label><input type="checkbox" name="days_of_week" value="{{ abbr }}"> {{ label }}</label>
            {% endfor %}
          </div>
        </div>
        <div class="field recurring-fields" style="display:none;">
          <label>Look-ahead (days)</label>
          <input name="look_ahead_days" type="number" min="1" max="90" value="45">
        </div>
        <div class="field">
          <label>Party Size</label>
          <input name="party_size" type="number" min="1" max="20" value="2" required>
        </div>
        <div class="field">
          <label>Earliest Time (HH:MM)</label>
          <input name="time_start" type="time" value="18:00" required>
        </div>
        <div class="field">
          <label>Latest Time (HH:MM)</label>
          <input name="time_end" type="time" value="21:00" required>
        </div>
        <div class="field" style="grid-column: 1 / -1;">
          <label>Restaurant URL</label>
          <input name="url" type="url" placeholder="https://resy.com/cities/ny/venues/..." required>
        </div>
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" type="submit">Add to Watchlist</button>
      </div>
    </form>
  </div>
  <script>
    function updateSchedule(form) {
      var recurring = form.querySelector('input[name="schedule_type"]:checked').value === 'recurring';
      form.querySelectorAll('.specific-date-field').forEach(function(el) { el.style.display = recurring ? 'none' : ''; });
      form.querySelectorAll('.recurring-fields').forEach(function(el) { el.style.display = recurring ? '' : 'none'; });
    }
  </script>
  {% endif %}
</body>
</html>
"""

init_db()


def _next_run_str() -> str:
    job = next(iter(schedule.jobs), None)
    if job is None:
        return "not scheduled"
    next_run = job.next_run
    if next_run is None:
        return "unknown"
    return next_run.strftime("%Y-%m-%d %H:%M:%S")


@app.route("/")
def index():
    return render_template_string(
        TEMPLATE,
        restaurants=get_all_restaurants(),
        interval=CHECK_INTERVAL,
        next_run=_next_run_str(),
        edit_rid=None,
        edit_row=None,
    )


@app.route("/edit/<int:rid>")
def edit_form(rid: int):
    return render_template_string(
        TEMPLATE,
        restaurants=get_all_restaurants(),
        interval=CHECK_INTERVAL,
        next_run=_next_run_str(),
        edit_rid=rid,
        edit_row=get_restaurant(rid),
    )


def _form_to_data(form) -> dict:
    recurring = form.get("schedule_type") == "recurring"
    return {
        "name":           form["name"].strip(),
        "platform":       form["platform"].strip().lower(),
        "url":            form["url"].strip(),
        "date":           "" if recurring else form.get("date", "").strip(),
        "party_size":     form["party_size"].strip(),
        "time_start":     form["time_start"].strip(),
        "time_end":       form["time_end"].strip(),
        "days_of_week":   ",".join(form.getlist("days_of_week")) if recurring else "",
        "look_ahead_days": form.get("look_ahead_days", "45") if recurring else "",
    }


@app.route("/edit/<int:rid>", methods=["POST"])
def edit_save(rid: int):
    update_restaurant(rid, _form_to_data(request.form))
    return redirect(url_for("index"))


@app.route("/add", methods=["POST"])
def add():
    add_restaurant(_form_to_data(request.form))
    return redirect(url_for("index"))


@app.route("/delete/<int:rid>", methods=["POST"])
def delete(rid: int):
    delete_restaurant(rid)
    return redirect(url_for("index"))


@app.route("/check", methods=["POST"])
def check_now():
    threading.Thread(target=check_all, daemon=True).start()
    return redirect(url_for("index"))


def _background_monitor():
    """Run the schedule loop in a daemon thread."""
    check_all()
    schedule.every(CHECK_INTERVAL).minutes.do(check_all)
    while True:
        schedule.run_pending()
        time.sleep(30)


# Start the background monitor whether served by gunicorn or run directly.
# gunicorn imports this module but never executes __main__, so the thread
# must be started at module level.
_monitor_thread = threading.Thread(target=_background_monitor, daemon=True)
_monitor_thread.start()

if __name__ == "__main__":
    print()
    print("  Restaurant Reservation Monitor")
    print("  ================================")
    print(f"  Web UI:     http://localhost:5000")
    print(f"  Checking every {CHECK_INTERVAL} minutes (background thread)")
    print()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
