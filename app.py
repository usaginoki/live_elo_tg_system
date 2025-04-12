from flask import Flask, render_template, request, jsonify
import sqlite3
import math

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('ratings.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def home():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    conn = get_db_connection()
    
    # Count total players for pagination
    if search:
        count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE name || ' ' || surname LIKE ?", 
            (f'%{search}%',)
        ).fetchone()[0]
    else:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    
    # Calculate total pages
    total_pages = math.ceil(count / 10)
    
    # Get players for current page
    offset = (page - 1) * 10
    
    if search:
        players = conn.execute(
            """
            SELECT name, surname, elo, games_played, 
                   ROW_NUMBER() OVER (ORDER BY elo DESC) as rank
            FROM users 
            WHERE name || ' ' || surname LIKE ? 
            ORDER BY elo DESC LIMIT 10 OFFSET ?
            """, 
            (f'%{search}%', offset)
        ).fetchall()
    else:
        players = conn.execute(
            """
            SELECT name, surname, elo, games_played,
                   ROW_NUMBER() OVER (ORDER BY elo DESC) as rank
            FROM users 
            ORDER BY elo DESC LIMIT 10 OFFSET ?
            """, 
            (offset,)
        ).fetchall()
    
    conn.close()
    
    return render_template(
        'home.html', 
        players=players, 
        page=page, 
        total_pages=total_pages,
        search=search
    )

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contacts')
def contacts():
    return render_template('contacts.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0') 