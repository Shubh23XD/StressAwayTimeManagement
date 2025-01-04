from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sqlite3
import pandas as pd
from io import BytesIO
import os
import logging
import threading
from shutil import copyfile

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change this to a secure secret key in production

# Configure session
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=31)
app.config['SESSION_TYPE'] = 'filesystem'

# Define base directory and database path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'employees.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')

# Configure logging
logging.basicConfig(
    filename=os.path.join(BASE_DIR, 'app.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Create database lock
db_lock = threading.Lock()

# Database initialization
def init_db():
    if not os.path.exists(DB_PATH):
        with db_lock:
            conn = sqlite3.connect(DB_PATH)
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
            logging.info("Database initialized successfully")

def get_db_connection():
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def backup_database():
    try:
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(BACKUP_DIR, f'employees_backup_{timestamp}.db')
        with db_lock:
            copyfile(DB_PATH, backup_file)
        logging.info(f"Database backed up successfully: {backup_file}")
    except Exception as e:
        logging.error(f"Backup failed: {str(e)}")

def validate_employee_data(name, action, ist_now):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM employees WHERE name = ?', (name,))
    employee = cursor.fetchone()
    conn.close()
    
    if employee:
        logging.info(f"Employee data accessed - Name: {name}, Action: {action}, Time: {ist_now}")
    else:
        logging.warning(f"Employee not found - Name: {name}, Action: {action}, Time: {ist_now}")
    
    return employee is not None

def verify_operation(name, action, expected_status):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM employees WHERE name = ?', (name,))
    result = cursor.fetchone()
    conn.close()
    
    if not result or result['status'] != expected_status:
        logging.error(f"Operation verification failed - Name: {name}, Action: {action}")
        return False
    return True

def is_allowed_time():
    ist_now = datetime.now(ZoneInfo('Asia/Kolkata')).time()
    start_time = datetime.strptime('10:00', '%H:%M').time()
    end_time = datetime.strptime('23:59', '%H:%M').time()
    
    return start_time <= ist_now <= end_time

@app.before_request
def check_database():
    if not os.path.exists(DB_PATH):
        init_db()

@app.route('/')
def index():
    if not is_allowed_time():
        return render_template('inactive.html')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM employees')
        employees = cursor.fetchall()
        conn.close()
        
        employees = [dict(row) for row in employees]
        for employee in employees:
            for time_field in ['in_time', 'out_time', 'last_clock_in_time', 'last_clock_out_time']:
                if employee[time_field]:
                    employee[time_field] = datetime.fromisoformat(employee[time_field])
        
        return render_template('index.html', employees=employees)
    except Exception as e:
        logging.error(f"Error in index route: {str(e)}")
        flash('An error occurred while loading employee data.')
        return render_template('index.html', employees=[])

@app.route('/clock', methods=['POST'])
def clock():
    if not is_allowed_time():
        flash('Clock in/out service is only available from 10 AM to 12 AM.')
        return redirect(url_for('index'))

    try:
        name = request.form['name']
        action = request.form['action']
        ist_now = datetime.now(ZoneInfo('Asia/Kolkata'))

        if not name or not action:
            flash('Invalid input data.')
            return redirect(url_for('index'))

        conn = get_db_connection()
        cursor = conn.cursor()

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
                    session['name'] = name
                    flash(f'{name} has clocked in.')
                else:
                    flash('Already clocked in.')
            else:
                cursor.execute('''
                    INSERT INTO employees (name, status, in_time, last_clock_in_time, last_clock_out_time)
                    VALUES (?, ?, ?, ?, NULL)
                ''', (name, 'clocked_in', ist_now.isoformat(), ist_now.isoformat()))
                conn.commit()
                session['name'] = name
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
        backup_database()  # Backup after successful operation
        
        # Verify the operation
        if action == 'Clock In':
            verify_operation(name, action, 'clocked_in')
        elif action == 'Clock Out':
            verify_operation(name, action, 'clocked_out')
            
        return redirect(url_for('index'))
        
    except Exception as e:
        logging.error(f"Error in clock route: {str(e)}")
        flash('An error occurred while processing your request.')
        return redirect(url_for('index'))

@app.route('/employees')
def display_employees():
    try:
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
    except Exception as e:
        logging.error(f"Error in display_employees route: {str(e)}")
        flash('An error occurred while retrieving employee data.')
        return render_template('employees.html', employees=[])

@app.route('/downloadTimeSheet')
def download_excel():
    try:
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT name, status, in_time, out_time FROM employees", conn)
        conn.close()
        
        # Convert datetime columns
        df['in_time'] = pd.to_datetime(df['in_time'], errors='coerce')
        df['out_time'] = pd.to_datetime(df['out_time'], errors='coerce')
        
        # Calculate duration if both in_time and out_time exist
        df['duration'] = None
        mask = df['in_time'].notna() & df['out_time'].notna()
        df.loc[mask, 'duration'] = (df.loc[mask, 'out_time'] - df.loc[mask, 'in_time']).astype(str)
        
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Employees')
            
            workbook = writer.book
            worksheet = writer.sheets['Employees']
            
            # Format datetime columns
            date_format = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm:ss'})
            worksheet.set_column('C:D', None, date_format)  # in_time and out_time
            
            # Format headers
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'border': 1
            })
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
        
        output.seek(0)
        
        return Response(
            output.read(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': 'attachment;filename=employees.xlsx'}
        )
    except Exception as e:
        logging.error(f"Error in download_excel route: {str(e)}")
        flash('An error occurred while generating the Excel file.')
        return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()  # Initialize database at startup
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    app.run(debug=True)
