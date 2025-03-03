import os
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS  # <-- Import Flask-Cors

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://macarabia.me"}})

DB_URI = os.environ.get("DB_URI")

@app.route("/api/search", methods=["GET"])
def search():
    search_term = request.args.get("q", "").strip()
    
    if not search_term:
        return jsonify({"error": "Missing 'q' query parameter."}), 400
    
    # Basic full-text search prep: split on whitespace, then join with " & "
    tokens = search_term.split()
    ts_query = " & ".join(tokens)

    try:
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()

        # We include description in the to_tsvector (for better relevance)
        # but do NOT select it, so it won't appear in the JSON response.
        sql = """
            SELECT
                product_id,
                title,
                handle,
                url,
                product_type,
                tags,
                sku,
                ts_rank_cd(
                    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                    setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
                    setweight(to_tsvector('english', coalesce(tags, '')), 'C') ||
                    setweight(to_tsvector('english', coalesce(sku, '')), 'D'),
                    to_tsquery('english', %s)
                ) AS rank
            FROM products
            WHERE
                setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(tags, '')), 'C') ||
                setweight(to_tsvector('english', coalesce(sku, '')), 'D')
                @@ to_tsquery('english', %s)
            -- Push 'Accessories' to the bottom while still sorting within each group by rank
            ORDER BY
                CASE WHEN product_type = 'Accessories' THEN 1 ELSE 0 END,
                rank DESC
        """

        cur.execute(sql, (ts_query, ts_query))
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in rows]

        cur.close()
        conn.close()
        return jsonify({"results": results}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
