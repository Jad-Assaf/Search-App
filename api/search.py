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
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()

        # Use the pg_trgm operator "%" for fuzzy substring matching.
        # Note: In a Python f-string, we need to escape "%" as "%%".
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
                GREATEST(
                    similarity(title, %s),
                    similarity(product_type, %s),
                    similarity(tags, %s),
                    similarity(sku, %s)
                ) AS sim_score
            FROM products
            WHERE (title %% %s OR product_type %% %s OR tags %% %s OR sku %% %s)
            ORDER BY
                CASE WHEN product_type = 'Accessories' THEN 1 ELSE 0 END,
                sim_score DESC,
                title
            LIMIT %s OFFSET %s;
        """
        # We pass the search_term four times for the similarity() calls and four times for the WHERE clause.
        params = [search_term, search_term, search_term, search_term] + \
                 [search_term, search_term, search_term, search_term] + \
                 [limit, offset]
        cur.execute(sql, params)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in rows]

        # Count total matches for pagination
        count_sql = f"""
            SELECT COUNT(*)
            FROM products
            WHERE (title %% %s OR product_type %% %s OR tags %% %s OR sku %% %s);
        """
        cur.execute(count_sql, [search_term]*4)
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
