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
        # Build a ts_query for full-text search.
        # By appending :* to each token, we allow prefix matching.
        # For example, "iphno" becomes "iphno:*" and "iphone case" becomes "iphno:* & case:*"
        ts_query = " & ".join(token + ":*" for token in search_term.split())

        # Combine columns to search. Using coalesce to avoid nulls.
        text_expr = ("coalesce(title, '') || ' ' || "
                     "coalesce(product_type, '') || ' ' || "
                     "coalesce(tags, '') || ' ' || "
                     "coalesce(sku, '')")

        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()

        # Main query: search using to_tsquery with prefix matching.
        sql = f"""
            SELECT
                product_id,
                title,
                handle,
                url,
                product_type,
                tags,
                sku,
                ts_rank(
                    to_tsvector('english', {text_expr}),
                    to_tsquery('english', %s)
                ) AS rank
            FROM products
            WHERE to_tsvector('english', {text_expr}) @@ to_tsquery('english', %s)
            ORDER BY
                CASE WHEN product_type = 'Accessories' THEN 1 ELSE 0 END,
                rank DESC,
                title
            LIMIT %s OFFSET %s;
        """
        query_params = [ts_query, ts_query, limit, offset]
        cur.execute(sql, query_params)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in rows]

        # Count total matches for pagination
        count_sql = f"""
            SELECT COUNT(*)
            FROM products
            WHERE to_tsvector('english', {text_expr}) @@ to_tsquery('english', %s)
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
