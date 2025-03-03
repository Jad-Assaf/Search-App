import os
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_URI = os.environ.get("DB_URI")

@app.route("/api/search", methods=["GET"])
def search():
    search_term = request.args.get("q", "").strip()
    page_str = request.args.get("page", "0")
    limit_str = request.args.get("limit", "20")

    # Convert page/limit to integers (with defaults)
    try:
        page = int(page_str)
        limit = int(limit_str)
        if page < 0:
            page = 0
        if limit < 1:
            limit = 20
    except ValueError:
        page, limit = 0, 20

    if not search_term:
        return jsonify({"error": "Missing 'q' query parameter."}), 400

    pattern = f"%{search_term}%"
    offset = page * limit

    try:
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()

        # 1) Main query with pagination + push Accessories to the bottom
        sql = """
            SELECT product_id, title, handle, url, product_type, tags, sku
            FROM products
            WHERE title ILIKE %s
               OR product_type ILIKE %s
               OR tags ILIKE %s
               OR sku ILIKE %s
            ORDER BY
                CASE WHEN product_type = 'Accessories' THEN 1 ELSE 0 END,
                title
            LIMIT %s OFFSET %s;
        """
        cur.execute(sql, (pattern, pattern, pattern, pattern, limit, offset))
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in rows]

        # 2) Count total matches (for showing total pages, etc.)
        count_sql = """
            SELECT COUNT(*)
            FROM products
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
