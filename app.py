from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sqlite3

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Needed for flash messages

# Database initialization
def init_db():
    conn = sqlite3.connect('employees.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            name TEXT PRIMARY KEY,
            status TEXT,
            in_time TEXT,
            out_time TEXT,
            last_clock_in_time TEXT,
            last_clock_out_time TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect('employees.db')
    conn.row_factory = sqlite3.Row
    return conn

# Function to check if current time is within allowed hours (10 AM to 12 AM)
def is_allowed_time():
    ist_now = datetime.now(ZoneInfo('Asia/Kolkata')).time()
    start_time = datetime.strptime('10:00', '%H:%M').time()
    end_time = datetime.strptime('23:59', '%H:%M').time()
    
    return start_time <= ist_now <= end_time

@app.route('/')
def index():
    # Check if service is available
    if not is_allowed_time():
        return render_template('inactive.html')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM employees')
    employees = cursor.fetchall()
    conn.close()
    employees = [dict(row) for row in employees]
    for employee in employees:
        if employee['in_time']:
            employee['in_time'] = datetime.fromisoformat(employee['in_time'])
        if employee['out_time']:
            employee['out_time'] = datetime.fromisoformat(employee['out_time'])
        if employee['last_clock_in_time']:
            employee['last_clock_in_time'] = datetime.fromisoformat(employee['last_clock_in_time'])
        if employee['last_clock_out_time']:
            employee['last_clock_out_time'] = datetime.fromisoformat(employee['last_clock_out_time'])
    return render_template('index.html', employees=employees)

@app.route('/clock', methods=['POST'])
def clock():
    # Check if service is available
    if not is_allowed_time():
        flash('Clock in/out service is only available from 10 AM to 12 AM.')
        return redirect(url_for('index'))

    name = request.form['name']
    action = request.form['action']
    conn = get_db_connection()
    cursor = conn.cursor()

    # Use Indian Standard Time (IST)
    ist_now = datetime.now(ZoneInfo('Asia/Kolkata'))

    if action == 'Clock In':
        cursor.execute('SELECT last_clock_in_time, status FROM employees WHERE name = ?', (name,))
        result = cursor.fetchone()
        if result:
            last_clock_in_time_str = result['last_clock_in_time']
            status = result['status']
            if last_clock_in_time_str:
                last_clock_in_time = datetime.fromisoformat(last_clock_in_time_str).replace(tzinfo=ZoneInfo('Asia/Kolkata'))
                if ist_now - last_clock_in_time < timedelta(minutes=5):
                    flash('Already clocked in recently.')
                    conn.close()
                    return redirect(url_for('index'))
            if status != 'clocked_in':
                cursor.execute('''
                    UPDATE employees SET
                        status = ?,
                        in_time = ?,
                        last_clock_in_time = ?,
                        last_clock_out_time = NULL
                    WHERE name = ?
                ''', ('clocked_in', ist_now.isoformat(), ist_now.isoformat(), name))
                conn.commit()
                session['name'] = name  # Store the name in the session
                flash(f'{name} has clocked in.')
            else:
                flash('Already clocked in.')
        else:
            cursor.execute('''
                INSERT INTO employees (name, status, in_time, last_clock_in_time, last_clock_out_time)
                VALUES (?, ?, ?, ?, NULL)
            ''', (name, 'clocked_in', ist_now.isoformat(), ist_now.isoformat()))
            conn.commit()
            session['name'] = name  # Store the name in the session
            flash(f'{name} has clocked in.')
    elif action == 'Clock Out':
        cursor.execute('SELECT last_clock_out_time, status FROM employees WHERE name = ?', (name,))
        result = cursor.fetchone()
        if result:
            last_clock_out_time_str = result['last_clock_out_time']
            status = result['status']
            if last_clock_out_time_str:
                last_clock_out_time = datetime.fromisoformat(last_clock_out_time_str).replace(tzinfo=ZoneInfo('Asia/Kolkata'))
                if ist_now - last_clock_out_time < timedelta(minutes=5):
                    flash('Already clocked out recently.')
                    conn.close()
                    return redirect(url_for('index'))
            if status == 'clocked_in':
                cursor.execute('''
                    UPDATE employees SET
                        status = ?,
                        out_time = ?,
                        last_clock_out_time = ?
                    WHERE name = ?
                ''', ('clocked_out', ist_now.isoformat(), ist_now.isoformat(), name))
                conn.commit()
                flash(f'{name} has clocked out.')
            else:
                flash('Already clocked out.')
        else:
            flash('Employee not found.')
    else:
        flash('Invalid action.')
    conn.close()
    return redirect(url_for('index'))

@app.route('/employees')
def display_employees():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM employees')
    employees = cursor.fetchall()
    conn.close()
    employees = [dict(row) for row in employees]
    for employee in employees:
        if employee['in_time']:
            employee['in_time'] = datetime.fromisoformat(employee['in_time'])
        if employee['out_time']:
            employee['out_time'] = datetime.fromisoformat(employee['out_time'])
    return render_template('employees.html', employees=employees)
    

if __name__ == '__main__':
    app.run(debug=True)

# from flask import Flask, render_template, request, redirect, url_for, flash
# from datetime import datetime, timedelta

# app = Flask(__name__)
# app.secret_key = 'your_secret_key'  # Needed for flash messages

# # In-memory storage for employee data
# employees = {}

# @app.route('/')
# def index():
#     return render_template('index.html', employees=employees)

# @app.route('/clock', methods=['POST'])
# def clock():
#     name = request.form['name']
#     action = request.form['action']
#     if action == 'Clock In':
#         if name in employees:
#             last_clock_in_time = employees[name].get('last_clock_in_time')
#             if last_clock_in_time and datetime.now() - last_clock_in_time < timedelta(minutes=5):
#                 flash('Already clocked in recently.')
#                 return redirect(url_for('index'))
#         employees[name] = {
#             'status': 'clocked_in',
#             'in_time': datetime.now(),
#             'last_clock_in_time': datetime.now(),
#             'last_clock_out_time': None  # Reset if clocking in again
#         }
#         flash(f'{name} has clocked in.')
#     elif action == 'Clock Out':
#         if name in employees:
#             last_clock_out_time = employees[name].get('last_clock_out_time')
#             if last_clock_out_time and datetime.now() - last_clock_out_time < timedelta(minutes=5):
#                 flash('Already clocked out recently.')
#                 return redirect(url_for('index'))
#             if employees[name]['status'] == 'clocked_in':
#                 employees[name]['status'] = 'clocked_out'
#                 employees[name]['out_time'] = datetime.now()
#                 employees[name]['last_clock_out_time'] = datetime.now()
#                 flash(f'{name} has clocked out.')
#             else:
#                 flash('Already clocked out.')
#         else:
#             flash('Employee not found.')
#     else:
#         flash('Invalid action.')
#     return redirect(url_for('index'))

# if __name__ == '__main__':
#     app.run(debug=True)
