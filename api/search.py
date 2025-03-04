import os
import re
import psycopg2
from psycopg2.extensions import AsIs
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
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()

        # ------------------------------------------------------------------
        # Normalize the user's query:
        # 1) Lowercase + remove accents (PostgreSQL's unaccent is done inside the DB).
        # 2) Insert a space between letters and digits for consistency
        # ------------------------------------------------------------------
        normalized_query = search_term.lower()
        normalized_query = re.sub(r'([a-z])([0-9])', r'\1 \2', normalized_query)
        # e.g. "watch7" -> "watch 7", "iphone14" -> "iphone 14"

        # Split tokens for prefix searching:
        # "samsung watch 7" => ["samsung", "watch", "7"] => "samsung:* & watch:* & 7:*"
        tokens = normalized_query.split()
        if not tokens:
            return jsonify({"results": [], "page": page, "limit": limit, "total": 0}), 200
        
        ts_query = " & ".join(f"{token}:*" for token in tokens)

        # We also keep a "full_match" check. If you want the "full_match" to handle
        # the letter-digit separation, we can do something similar in the CASE expression.
        # For simplicity, we'll do a simpler approach: full_match checks the original
        # title ILIKE '%search_term%', or you can also choose to check the normalized one.
        full_wildcard = f"%{search_term}%"

        # Main query
        sql = """
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
            WHERE
                -- Use the stored tsvector column for super-fast lookups
                search_document @@ to_tsquery('english', %s)
            ORDER BY
                full_match DESC,
                CASE WHEN product_type = 'Accessories' THEN 1 ELSE 0 END,
                title
            LIMIT %s OFFSET %s;
        """
        cur.execute(sql, [full_wildcard, ts_query, limit, offset])
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in rows]

        # Count total matches
        count_sql = """
            SELECT COUNT(*)
            FROM products
            WHERE search_document @@ to_tsquery('english', %s)
        """
        cur.execute(count_sql, [ts_query])
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
