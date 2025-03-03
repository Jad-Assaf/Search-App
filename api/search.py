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

    offset = page * limit

    try:
        # Prepare the full wildcard search term for full_match computation.
        full_wildcard = f"%{search_term}%"
        
        # Tokenize search_term and build conditions with ILIKE wildcards.
        tokens = search_term.split()
        conditions = []
        values = []
        for token in tokens:
            wildcard = f"%{token}%"
            conditions.append("""
                (title ILIKE %s OR product_type ILIKE %s OR tags ILIKE %s OR sku ILIKE %s)
            """)
            values.extend([wildcard, wildcard, wildcard, wildcard])
        # Combine token conditions so every token must match somewhere.
        where_clause = " AND ".join(conditions)

        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()

        # Main query:
        # 1. Compute "full_match": 1 if title ILIKE the full search term, else 0.
        # 2. Apply the token-based conditions.
        # 3. Order by full_match DESC, then push Accessories to the bottom, then by title.
        sql = f"""
            SELECT
                product_id,
                title,
                handle,
                url,
                product_type,
                tags,
                sku,
                price,
                image_url,
                CASE WHEN title ILIKE %s THEN 1 ELSE 0 END AS full_match
            FROM products
            WHERE {where_clause}
            ORDER BY
                full_match DESC,
                CASE WHEN product_type = 'Accessories' THEN 1 ELSE 0 END,
                title
            LIMIT %s OFFSET %s;
        """
        # Build parameters:
        # First parameter for full_match, then token conditions, then limit and offset.
        query_params = [full_wildcard] + values + [limit, offset]
        cur.execute(sql, query_params)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in rows]

        # Count total matches for pagination (using the token conditions only).
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
