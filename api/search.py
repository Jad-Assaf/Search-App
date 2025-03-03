import os
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_URI = os.environ.get("DB_URI")

@app.route("/api/search", methods=["GET"])
def search():
    # Get parameters
    search_term = request.args.get("q", "").strip()
    page_str = request.args.get("page", "0")
    limit_str = request.args.get("limit", "20")

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

    # Use the whole term as one (no token splitting)
    wildcard = f"%{search_term}%"
    offset = page * limit

    try:
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()

        # Build a single WHERE clause that searches the entire term in the chosen columns.
        where_clause = """
            (title ILIKE %s
             OR product_type ILIKE %s
             OR tags ILIKE %s
             OR sku ILIKE %s)
        """
        values = [wildcard, wildcard, wildcard, wildcard]

        # Query the products and push 'Accessories' to the bottom, then sort by title.
        sql = f"""
            SELECT product_id, title, handle, url, product_type, tags, sku
            FROM products
            WHERE {where_clause}
            ORDER BY
                CASE WHEN product_type = 'Accessories' THEN 1 ELSE 0 END,
                title
            LIMIT %s OFFSET %s;
        """
        query_params = values + [limit, offset]
        cur.execute(sql, query_params)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in rows]

        # Count total matches (for pagination)
        count_sql = f"""
            SELECT COUNT(*)
            FROM products
            WHERE {where_clause}
        """
        cur.execute(count_sql, values)
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

if __name__ == '__main__':
    app.run(debug=True)
