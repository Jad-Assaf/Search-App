import os
import json
import psycopg2
from urllib.parse import urlparse, parse_qs

# Load the database URI from environment variables
DB_URI = os.environ.get("DB_URI")

def handler(event, context):
    """
    AWS Lambda-style handler function.
    Expects query parameters under event["queryStringParameters"].
    """
    query_params = event.get("queryStringParameters") or {}
    search_term = query_params.get("q", "").strip()
    
    if not search_term:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing 'q' query parameter."}),
            "headers": {"Content-Type": "application/json"}
        }
    
    # Create a pattern for partial matching using ILIKE (case-insensitive)
    pattern = f"%{search_term}%"
    
    try:
        # Connect to the PostgreSQL database
        conn = psycopg2.connect(DB_URI)
        cur = conn.cursor()
        
        # Execute the search query on the products table
        sql = """
            SELECT product_id, title, handle, url, description, product_type, tags, sku
            FROM products
            WHERE title ILIKE %s
               OR description ILIKE %s
               OR tags ILIKE %s
               OR sku ILIKE %s
            ORDER BY title
            LIMIT 50;
        """
        cur.execute(sql, (pattern, pattern, pattern, pattern))
        rows = cur.fetchall()
        # Get column names from the cursor description
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in rows]
        
        cur.close()
        conn.close()
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
            "headers": {"Content-Type": "application/json"}
        }
    
    return {
        "statusCode": 200,
        "body": json.dumps({"results": results}),
        "headers": {"Content-Type": "application/json"}
    }
