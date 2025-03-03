import os
import psycopg2
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_URI = os.environ.get("DB_URI")

@app.route("/api/search", methods=["GET"])
def search():
    search_term = request.args.get("q", "").strip()
    
    if not search_term:
        return jsonify({"error": "Missing 'q' query parameter."}), 400
    
    # Transform user input into a form suitable for full text search.
    # e.g. "iphone case" => "iphone & case"
    # Basic approach splits on whitespace.
    tokens = search_term.split()
    ts_query = " & ".join(tokens)

    # Using an English dictionary for better tokenization/stemming,
    # but you can use plain 'simple' if your data is not in English.
    try:
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()

        sql = """
            SELECT
                product_id,
                title,
                handle,
                url,
                description,
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
            ORDER BY rank DESC;
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
