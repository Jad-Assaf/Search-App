import os
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
app.config["DEBUG"] = True  # enable for debugging
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

    # Split the search query into tokens. Example: "iph cas" -> ["iph", "cas"]
    tokens = search_term.split()
    offset = page * limit

    try:
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()

        # For each token, we build two sets of parameters:
        #   - One for the WHERE condition using the pg_trgm similarity operator.
        #   - One for the similarity expression (for ordering).
        conditions = []
        similarity_exprs = []
        values = []
        for token in tokens:
            # Note: the similarity operator (%) must be escaped as %% so that psycopg2
            # treats it as a literal %.
            conditions.append("(title %% %s OR product_type %% %s OR tags %% %s OR sku %% %s)")
            similarity_exprs.append("""
                greatest(
                    similarity(title, %s),
                    similarity(product_type, %s),
                    similarity(tags, %s),
                    similarity(sku, %s)
                )
            """)
            # Bind 4 parameters for the condition...
            values.extend([token, token, token, token])
            # ...and 4 parameters for the similarity expression.
            values.extend([token, token, token, token])

        # All tokens must match in some column.
        where_clause = " AND ".join(conditions)
        # Sum the best similarity score per token.
        combined_similarity_expr = " + ".join(similarity_exprs)

        sql = f"""
            SELECT
                product_id,
                title,
                handle,
                url,
                product_type,
                tags,
                sku,
                ({combined_similarity_expr}) AS combined_similarity
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

        # If no matches, build "did you mean" suggestions.
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
        app.logger.error("Error in search endpoint: %s", e)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
