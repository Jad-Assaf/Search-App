import os
import psycopg2
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_URI = os.environ.get("DB_URI")

@app.route("/", methods=["GET"])
def search():
    search_term = request.args.get("q", "").strip()
    
    if not search_term:
        return jsonify({"error": "Missing 'q' query parameter."}), 400
    
    pattern = f"%{search_term}%"
    
    try:
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()
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
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in rows]
        
        cur.close()
        conn.close()
        return jsonify({"results": results}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
