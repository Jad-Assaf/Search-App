import os
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS  # if you're doing cross-domain requests

app = Flask(__name__)
CORS(app)  # or configure allowed origins if needed

DB_URI = os.environ.get("DB_URI")

@app.route("/api/search", methods=["GET"])
def search():
    search_term = request.args.get("q", "").strip()
    page = request.args.get("page", "0")
    limit = request.args.get("limit", "20")

    try:
        # Convert page/limit to integers
        page = int(page)
        limit = int(limit)
        if page < 0:
            page = 0
        if limit < 1:
            limit = 20
    except ValueError:
        # If the user passed a non-integer, default to page=0, limit=20
        page, limit = 0, 20

    if not search_term:
        return jsonify({"error": "Missing 'q' query parameter."}), 400

    # We'll keep it simple, but still use ILIKE or FTS. Example with ILIKE:
    pattern = f"%{search_term}%"

    # Calculate OFFSET
    offset = page * limit

    try:
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()

        # If you're using the older ILIKE approach:
        sql = f"""
            SELECT product_id, title, handle, url, product_type, tags, sku
            FROM products
            WHERE title ILIKE %s
               OR product_type ILIKE %s
               OR tags ILIKE %s
               OR sku ILIKE %s
            ORDER BY title
            LIMIT %s OFFSET %s;
        """

        cur.execute(sql, (pattern, pattern, pattern, pattern, limit, offset))
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in rows]

        # Count total matches (optional, for showing how many total results exist)
        count_sql = """
            SELECT COUNT(*) FROM products
            WHERE title ILIKE %s
               OR product_type ILIKE %s
               OR tags ILIKE %s
               OR sku ILIKE %s
        """
        cur.execute(count_sql, (pattern, pattern, pattern, pattern))
        total_matches = cur.fetchone()[0]

        cur.close()
        conn.close()

        return jsonify({
            "results": results,
            "page": page,
            "limit": limit,
            "total": total_matches
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
