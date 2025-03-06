import os
import re
import psycopg2
from psycopg2 import pool
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_URI = os.environ.get("DB_URI")

# Set up a connection pool (min 1, max 20 connections)
db_pool = pool.SimpleConnectionPool(1, 20, DB_URI)

@app.route("/api/search", methods=["GET"])
def search():
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
        # Normalize input (e.g., "watch7" -> "watch 7")
        normalized_query = search_term.lower()
        normalized_query = re.sub(r'([a-z])([0-9])', r'\1 \2', normalized_query)

        # Split into tokens
        tokens = normalized_query.split()
        if not tokens:
            return jsonify({"results": [], "page": page, "limit": limit, "total": 0}), 200

        # Build a prefix-style ts_query for partial word matches via "token:*"
        ts_query = " & ".join(f"{token}:*" for token in tokens)

        # Also build substring "LIKE" checks for each token
        # We'll enforce that *all* tokens must match as substrings (AND).
        like_conditions = []
        for _ in tokens:
            like_conditions.append("""(
                LOWER(
                    COALESCE(title, '') || ' ' ||
                    COALESCE(product_type, '') || ' ' ||
                    COALESCE(tags, '') || ' ' ||
                    COALESCE(sku, '')
                ) LIKE %s
            )""")
        # Combine them with AND so that each token is found somewhere in the text
        substring_clause = " AND ".join(like_conditions)

        # Create the final WHERE condition:
        # Either the row matches the full-text search or it matches all tokens as substrings.
        # Use parentheses for clarity:
        where_clause = f"""
            (
                to_tsvector(
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
            )
            OR
            ({substring_clause})
        """

        # For a "full_match" check on title
        full_wildcard = f"%{search_term}%"

        # Build final SQL
        search_sql = f"""
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
                CASE WHEN title ILIKE %s THEN 1 ELSE 0 END AS full_match,
                COUNT(*) OVER() AS total_matches
            FROM products
            WHERE {where_clause}
            ORDER BY
                full_match DESC,
                CASE WHEN product_type = 'Accessories' THEN 1 ELSE 0 END,
                title
            LIMIT %s OFFSET %s
        """

        # Prepare parameters:
        # 1) the ts_query
        # 2..(1+len(tokens)) => substring parameters for each token
        # plus the full_wildcard, and then limit, offset
        params = []
        params.append(ts_query)
        for token in tokens:
            params.append(f"%{token}%")
        # The "full_match" ILIKE check
        params = [full_wildcard] + params
        params += [limit, offset]

        # Execute
        conn = db_pool.getconn()
        cur = conn.cursor()
        cur.execute(search_sql, params)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in rows]
        total_matches = results[0]["total_matches"] if results else 0

        cur.close()
        db_pool.putconn(conn)

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
