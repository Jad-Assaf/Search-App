from flask import Flask, request, jsonify
import os
import psycopg2
from psycopg2.extras import execute_values

app = Flask(__name__)

# Load DB URI from environment variables
DB_URI = os.environ.get("DB_URI")  # e.g., "postgres://avnadmin:...@host:port/defaultdb?sslmode=require"

@app.route("/api/search", methods=["GET"])
def search():
    # Get the search term from the query parameters
    search_term = request.args.get("q", "").strip()
    if not search_term:
        return jsonify({"error": "Missing 'q' query parameter."}), 400
    
    # Create a pattern for partial matching using ILIKE (case-insensitive)
    pattern = f"%{search_term}%"
    
    try:
        # Connect to the PostgreSQL database
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()
        
        # Execute the search query on the products table
        sql = """
            SELECT product_id, title, handle, url, description, product_type, tags, sku
            FROM products
            WHERE title ILIKE %s
               OR description ILIKE %s
               OR tags ILIKE %s
               OR sku ILIKE %s
            ORDER BY title
            LIMIT 50;
        """
        cur.execute(sql, (pattern, pattern, pattern, pattern))
        rows = cur.fetchall()
        # Build a list of dictionaries from the query result
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in rows]
        
        cur.close()
        conn.close()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    # Return search results as JSON
    return jsonify({"results": results}), 200

# Export the Flask app as the WSGI handler for Vercel
handler = app
