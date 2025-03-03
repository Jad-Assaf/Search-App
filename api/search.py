import os
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_URI = os.environ.get("DB_URI")

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

    # Split the user query into tokens, e.g. "iph cas" => ["iph", "cas"]
    tokens = search_term.split()
    offset = page * limit

    try:
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()

        # Build the fuzzy search WHERE clause:
        # For each token, require that at least one of the columns is "similar" to it.
        conditions = []
        similarity_exprs = []
        values = []

        for token in tokens:
            conditions.append("(title % %s OR product_type % %s OR tags % %s OR sku % %s)")
            # For ordering, take the greatest similarity across columns for this token.
            similarity_exprs.append("""
                greatest(
                    similarity(title, %s),
                    similarity(product_type, %s),
                    similarity(tags, %s),
                    similarity(sku, %s)
                )
            """)
            # For each token, add it 4 times for the condition...
            values.extend([token, token, token, token])

        # All tokens must match in some column:
        where_clause = " AND ".join(conditions)
        # Sum the best similarity score per token:
        combined_similarity_expr = " + ".join(similarity_exprs)

        # Query for matching products with pagination.
        # Push products with product_type 'Accessories' to the bottom.
        sql = f"""
            SELECT
                product_id,
                title,
                handle,
                url,
                product_type,
                tags,
                sku,
                (
                    {combined_similarity_expr}
                ) AS combined_similarity
            FROM products
            WHERE {where_clause}
            ORDER BY
                CASE WHEN product_type = 'Accessories' THEN 1 ELSE 0 END,
                combined_similarity DESC,
                title
            LIMIT %s OFFSET %s;
        """
        query_params = values + [limit, offset]
        cur.execute(sql, query_params)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in rows]

        # Count total matches for pagination.
        count_sql = f"""
            SELECT COUNT(*)
            FROM products
            WHERE {where_clause}
        """
        cur.execute(count_sql, values)
        total_matches = cur.fetchone()[0]

        # If there are no matches, build "did you mean" suggestions.
        did_you_mean = []
        if total_matches == 0:
            for token in tokens:
                cur.execute("""
                    SELECT term
                    FROM dictionary
                    ORDER BY similarity(term, %s) DESC
                    LIMIT 3
                """, (token,))
                suggest_rows = cur.fetchall()
                suggestions = [r[0] for r in suggest_rows]
                if suggestions:
                    did_you_mean.append({
                        "original": token,
                        "suggestions": suggestions
                    })

        cur.close()
        conn.close()

        return jsonify({
            "results": results,
            "page": page,
            "limit": limit,
            "total": total_matches,
            "did_you_mean": did_you_mean
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
