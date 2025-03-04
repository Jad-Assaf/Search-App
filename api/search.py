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

    # Prepare data for the query
    # 1) Full-match wildcard for the "full_match" CASE check
    full_wildcard = f"%{search_term}%"

    # 2) Construct a tsquery string for prefix matches: each token as "token:*"
    tokens = search_term.split()
    # Safely build an AND-based to_tsquery expression
    # Example: searching "red shoes" => "red:* & shoes:*"
    ts_query = " & ".join(f"{token}:*" for token in tokens)

    # In case you want to handle special characters or sanitization:
    #   from psycopg2.extensions import AsIs
    #   Or parse tokens carefully. For now, we trust simple splits.

    try:
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()

        # Main query:
        #   - Use to_tsvector(...) @@ to_tsquery(...) for fast matching
        #   - Keep the "Accessories to bottom" rule
        #   - Keep a "full_match" check if title ILIKE the entire search
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
            WHERE to_tsvector(
                    'english',
                    COALESCE(title, '') || ' ' ||
                    COALESCE(product_type, '') || ' ' ||
                    COALESCE(tags, '') || ' ' ||
                    COALESCE(sku, '')
                  ) @@ to_tsquery('english', %s)
            ORDER BY
                full_match DESC,
                CASE WHEN product_type = 'Accessories' THEN 1 ELSE 0 END,
                title
            LIMIT %s OFFSET %s
        """

        cur.execute(sql, [full_wildcard, ts_query, limit, offset])
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in rows]

        # Count total matches
        count_sql = f"""
            SELECT COUNT(*)
            FROM products
            WHERE to_tsvector(
                    'english',
                    COALESCE(title, '') || ' ' ||
                    COALESCE(product_type, '') || ' ' ||
                    COALESCE(tags, '') || ' ' ||
                    COALESCE(sku, '')
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
