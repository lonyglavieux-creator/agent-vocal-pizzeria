import os
import asyncpg
import asyncio

DATABASE_URL = os.environ.get("DATABASE_URL", "")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in environment")
    exit(1)

async def init_db():
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Read SQL script
        with open("init_db.sql", "r") as f:
            sql = f.read()
        
        # Execute
        await conn.execute(sql)
        print("✓ Schema initialized successfully")
        
        # Check tables
        rows = await conn.fetch("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        
        print("Tables created:")
        for row in rows:
            print(f"  - {row['table_name']}")
        
        await conn.close()
    except Exception as e:
        print(f"ERROR: {e}")
        exit(1)

asyncio.run(init_db())

