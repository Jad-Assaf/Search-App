import os
import re
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_URI = os.environ.get("DB_URI")

@app.route("/api/search", methods=["GET"])
def search():
    search_term = request.args.get("q", "").strip()
    page_str    = request.args.get("page", "0")
    limit_str   = request.args.get("limit", "20")
    
    # Validate page/limit
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
        # 1) Normalize user input, e.g., "watch7" -> "watch 7"
        normalized_query = search_term.lower()
        normalized_query = re.sub(r'([a-z])([0-9])', r'\1 \2', normalized_query)

        # 2) Build a prefix-style ts_query for partial word matches
        tokens = normalized_query.split()
        if not tokens:
            return jsonify({"results": [], "page": page, "limit": limit, "total": 0}), 200
        ts_query = " & ".join(f"{token}:*" for token in tokens)

        # 3) For the "full_match" check, we can do a simple ILIKE
        full_wildcard = f"%{search_term}%"

        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()

        # 4) Use the SAME expression from the functional index in WHERE,
        #    so it can utilize the GIN index for speed.
        search_sql = """
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
            WHERE to_tsvector(
                    'english',
                    regexp_replace(
                        lower(
                            coalesce(title, '') || ' ' ||
                            coalesce(product_type, '') || ' ' ||
                            coalesce(tags, '') || ' ' ||
                            coalesce(sku, '')
                        ),
                        '([a-z])([0-9])',
                        '\\1 \\2',
                        'g'
                    )
                  ) @@ to_tsquery('english', %s)
            ORDER BY
                full_match DESC,
                CASE WHEN product_type = 'Accessories' THEN 1 ELSE 0 END,
                title
            LIMIT %s OFFSET %s
        """

        cur.execute(search_sql, [full_wildcard, ts_query, limit, offset])
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in rows]

        # Count total matches with the same expression
        count_sql = """
            SELECT COUNT(*)
            FROM products
            WHERE to_tsvector(
                    'english',
                    regexp_replace(
                        lower(
                            coalesce(title, '') || ' ' ||
                            coalesce(product_type, '') || ' ' ||
                            coalesce(tags, '') || ' ' ||
                            coalesce(sku, '')
                        ),
                        '([a-z])([0-9])',
                        '\\1 \\2',
                        'g'
                    )
                  ) @@ to_tsquery('english', %s)
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
